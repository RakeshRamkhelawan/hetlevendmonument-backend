"""
Corrective RAG (CRAG) Graph Implementation
Defines the state and structure for the adaptive RAG workflow.
"""

import logging
from typing import Any, TypedDict

from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.graph import END, START, StateGraph

from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.search.hybrid_search import HybridSearchConfig, hybrid_search

logger = logging.getLogger(__name__)

# --- Prompts ---
GRADING_PROMPT = """You are a grader assessing relevance of a retrieved document to a user question.
If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant.
It does not need to be a stringent test. The goal is to filter out erroneous retrievals.

Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question.

User Question: {question}
Retrieved Document: {document}

Score (yes/no):"""

GENERATE_PROMPT = """You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.

Question: {question}
Context: {context}
Answer:"""

TRANSFORM_QUERY_PROMPT = """You are a query transformer. Your task is to rewrite a user question to be more effective for a web search engine.
The goal is to improve the quality of search results by clarifying ambiguities and adding relevant keywords.

Original Question: {question}
Optimized Search Query:"""


class GraphState(TypedDict):
    """
    Represents the state of our graph.
    """

    query: str
    documents: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    web_search_needed: bool
    generation: str
    tenant_id: int
    metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type


async def retrieve(state: GraphState) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Retrieve documents using hybrid search (Vector + BM25).
    """
    query = state["query"]
    tenant_id = state["tenant_id"]

    logger.info(f"--- RETRIEVING DOCUMENTS FOR TENANT {tenant_id} ---")

    config = HybridSearchConfig(fusion_method="rrf")
    results = await hybrid_search(tenant_id=tenant_id, query=query, top_k=5, config=config)

    documents = [
        {
            "id": r.document_id,
            "content": r.content,
            "metadata": r.metadata,
            "score": r.hybrid_score,
        }
        for r in results
    ]

    return {"documents": documents, "query": query}


async def grade_documents(state: GraphState) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Determines whether the retrieved documents are relevant to the question.
    """
    query = state["query"]
    documents = state["documents"]

    logger.info("--- GRADING DOCUMENTS ---")
    llm_service = TenantTaalmodel(state["tenant_id"])

    filtered_docs: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    web_search = False

    for doc in documents:
        prompt = GRADING_PROMPT.format(question=query, document=doc["content"])
        response = await llm_service.generate_response(prompt, max_tokens=10, temperature=0)
        score = str(response.get("content", "no")).strip().lower()

        if "yes" in score:
            logger.info(f"Document {doc.get('id')} graded RELEVANT")
            filtered_docs.append(doc)
        else:
            logger.info(f"Document {doc.get('id')} graded IRRELEVANT")

    if not filtered_docs:
        web_search = True
        logger.warning("All documents filtered out. Web search needed.")

    return {"documents": filtered_docs, "query": query, "web_search_needed": web_search}


async def transform_query(state: GraphState) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Transform the query to produce a better web search result.
    """
    logger.info("--- TRANSFORMING QUERY ---")
    query = state["query"]

    llm_service = TenantTaalmodel(state["tenant_id"])
    prompt = TRANSFORM_QUERY_PROMPT.format(question=query)

    response = await llm_service.generate_response(prompt, max_tokens=100, temperature=0)

    transformed_query = str(response.get("content", query)).strip()
    logger.info(f"Transformed query: '{transformed_query}'")

    return {"query": transformed_query}


async def web_search(state: GraphState) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Web search based on the query.
    """
    query = state["query"]
    documents = state["documents"]

    logger.info("--- WEB SEARCH ---")

    search_tool = TavilySearchResults(max_results=3)

    logger.info(f"Searching web for: '{query}'")
    search_results = await search_tool.ainvoke({"query": query})

    web_results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for r in search_results:
        content = r.get("content", "")
        url = r.get("url", "unknown")
        web_results.append(
            {
                "id": f"web_{hash(url)}",
                "content": content,
                "metadata": {"source": "web", "url": url},
            }
        )

    if documents is None:
        documents = []
    documents.extend(web_results)

    return {"documents": documents, "query": query}


async def generate(state: GraphState) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Generate answer using retrieved context.
    """
    logger.info("--- GENERATING ANSWER ---")
    query = state["query"]
    documents = state["documents"]

    context = "\n\n".join([doc["content"] for doc in documents])
    prompt = GENERATE_PROMPT.format(question=query, context=context)

    llm_service = TenantTaalmodel(state["tenant_id"])
    response = await llm_service.generate_response(prompt)

    return {"generation": response.get("content", ""), "documents": documents}


def decide_to_generate(state: GraphState) -> str:
    """
    Determines whether to generate an answer or perform a web search.
    """
    if state["web_search_needed"]:
        return "web_search"
    else:
        return "generate"


def create_crag_graph() -> Any:  # TODO(TYPE): replace Any with concrete type
    """
    Assembles the Corrective RAG (CRAG) graph.
    """
    workflow = StateGraph(GraphState)

    # Define the nodes
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("grade_documents", grade_documents)
    workflow.add_node("generate", generate)
    workflow.add_node("transform_query", transform_query)
    workflow.add_node("web_search", web_search)

    # Build the graph
    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "grade_documents")

    # Conditional edge
    workflow.add_conditional_edges(
        "grade_documents",
        decide_to_generate,
        {
            "web_search": "transform_query",
            "generate": "generate",
        },
    )

    workflow.add_edge("transform_query", "web_search")
    workflow.add_edge("web_search", "generate")
    workflow.add_edge("generate", END)

    # Compile
    app = workflow.compile()
    return app
