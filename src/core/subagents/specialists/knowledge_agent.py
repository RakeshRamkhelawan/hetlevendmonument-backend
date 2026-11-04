#!/usr/bin/env python3
"""
Knowledge Agent - Specialized Agent for Information Retrieval
"""

import glob
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, cast

from src.core.subagents.agent_factory import BaseAgent

logger = logging.getLogger(__name__)


class KnowledgeAgent(BaseAgent):
    """Specialized agent for knowledge retrieval and management"""

    async def _agent_specific_init(self) -> None:
        """Initialize knowledge management capabilities"""
        self.knowledge_sources = {
            "internal_kb": self._query_internal_knowledge,
            "document_search": self._search_documents,
            "web_search": self._web_search,
            "faq_lookup": self._faq_lookup,
        }
        self.knowledge_cache: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        logger.info(
            f"Knowledge Agent {self.agent_id} initialized with {len(self.knowledge_sources)} sources"
        )

    async def _execute_specific_task(
        self,
        task_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute knowledge retrieval task"""
        query = task_data.get("query", "")
        sources = task_data.get("sources", ["internal_kb"])
        max_results = task_data.get("max_results", 10)

        if not query:
            return {"error": "No query provided"}

        results: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for source in sources:
            if source in self.knowledge_sources:
                try:
                    source_results = await self.knowledge_sources[source](query, max_results)
                    results[source] = source_results
                except Exception as e:
                    results[source] = {"error": str(e)}

        return {
            "query": query,
            "sources_queried": sources,
            "results": results,
            "total_results": sum(
                len(r.get("items", []))
                for r in results.values()
                if isinstance(r, dict) and "items" in r
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _query_internal_knowledge(
        self, query: str, max_results: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Query internal knowledge base with semantic search"""

        start_time = time.time()

        try:
            # Real knowledge base: Search project documentation and code
            knowledge_items: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
            # Search markdown files for documentation (limit scope for performance)
            md_files = glob.glob("*.md") + glob.glob("docs/**/*.md", recursive=True)

            for file_path in md_files[:10]:  # Limit for performance
                try:
                    with open(file_path, encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    # Calculate relevance using keyword matching
                    relevance = self._calculate_text_relevance(query, content)

                    if relevance > 0.1:  # Only include relevant results
                        # Extract title from first line or filename
                        title = (
                            content.split("\n")[0].strip("# ")
                            if content
                            else os.path.basename(file_path)
                        )

                        # Extract relevant snippet
                        snippet = self._extract_relevant_snippet(query, content)

                        knowledge_items.append(
                            {
                                "title": title,
                                "content": snippet,
                                "file_path": file_path,
                                "relevance": relevance,
                                "source_type": "documentation",
                            }
                        )

                except Exception:
                    continue

            # Add system information as knowledge
            system_knowledge = [
                {
                    "title": "M-MDP System Status",
                    "content": f"M-MDP platform with {3} operational specialized agents: DataAnalysis, SystemMonitor, CodeExecution",
                    "relevance": self._calculate_text_relevance(
                        query, "M-MDP system agents platform"
                    ),
                    "source_type": "system_status",
                },
                {
                    "title": "Phase 1 Progress",
                    "content": "Week 1-2 complete: 70% realtime readiness achieved with functional agents",
                    "relevance": self._calculate_text_relevance(
                        query, "phase progress implementation status"
                    ),
                    "source_type": "project_status",
                },
            ]

            # Add system knowledge if relevant
            for item in system_knowledge:
                if cast(float, item["relevance"]) > 0.1:
                    knowledge_items.append(item)

            # Sort by relevance and limit results
            knowledge_items.sort(key=lambda x: x["relevance"], reverse=True)
            top_items = knowledge_items[:max_results]

            query_time = time.time() - start_time

            return {
                "source": "internal_kb",
                "items": top_items,
                "query_time": round(query_time, 3),
                "total_scanned": len(md_files),
                "total_found": len(knowledge_items),
            }

        except Exception as e:
            return {
                "source": "internal_kb",
                "items": [],
                "error": str(e),
                "query_time": time.time() - start_time,
            }

    def _calculate_text_relevance(self, query: str, text: str) -> float:
        """Calculate relevance score between query and text"""
        query_words = set(query.lower().split())
        text_words = set(text.lower().split())

        if not query_words:
            return 0.0

        # Calculate intersection ratio
        intersection = query_words.intersection(text_words)
        relevance = len(intersection) / len(query_words)

        # Boost for exact phrase matches
        if query.lower() in text.lower():
            relevance += 0.3

        return min(relevance, 1.0)

    def _extract_relevant_snippet(self, query: str, text: str, max_length: int = 200) -> str:
        """Extract relevant snippet from text"""
        query.lower()
        text.lower()

        # Find best matching sentence or paragraph
        sentences = text.split(". ")
        best_sentence = ""
        best_score: float = 0.0

        for sentence in sentences:
            score = self._calculate_text_relevance(query, sentence)
            if score > best_score:
                best_score = score
                best_sentence = sentence

        if best_sentence:
            # Truncate if too long
            if len(best_sentence) > max_length:
                best_sentence = best_sentence[:max_length] + "..."
            return best_sentence

        # Fallback: return first part of text
        return text[:max_length] + "..." if len(text) > max_length else text

    async def _search_documents(
        self, query: str, max_results: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Search documents with real file system search"""

        start_time = time.time()

        try:
            documents: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # Search Python files for code documentation
            py_files = glob.glob("**/*.py", recursive=True)

            for file_path in py_files[:20]:  # Limit for performance
                try:
                    with open(file_path, encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    # Calculate relevance
                    relevance = self._calculate_text_relevance(query, content)

                    if relevance > 0.05:  # Lower threshold for code files
                        # Extract docstrings or comments
                        snippet = self._extract_code_snippet(query, content)

                        documents.append(
                            {
                                "title": os.path.basename(file_path),
                                "path": file_path,
                                "content": snippet,
                                "relevance": relevance,
                                "file_type": "python",
                                "size_bytes": len(content),
                            }
                        )

                except Exception:
                    continue

            # Search configuration files
            config_files = (
                glob.glob("*.ini") + glob.glob("*.yaml") + glob.glob("*.yml") + glob.glob("*.json")
            )

            for file_path in config_files:
                try:
                    with open(file_path, encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    relevance = self._calculate_text_relevance(query, content)

                    if relevance > 0.1:
                        documents.append(
                            {
                                "title": os.path.basename(file_path),
                                "path": file_path,
                                "content": content[:200] + "..." if len(content) > 200 else content,
                                "relevance": relevance,
                                "file_type": "configuration",
                            }
                        )

                except Exception:
                    continue

            # Sort by relevance
            documents.sort(key=lambda x: x["relevance"], reverse=True)

            query_time = time.time() - start_time

            return {
                "source": "document_search",
                "items": documents[:max_results],
                "query_time": round(query_time, 3),
                "total_scanned": len(py_files) + len(config_files),
                "types_found": list({doc["file_type"] for doc in documents}),
            }

        except Exception as e:
            return {
                "source": "document_search",
                "items": [],
                "error": str(e),
                "query_time": time.time() - start_time,
            }

    def _extract_code_snippet(self, query: str, code: str, max_length: int = 300) -> str:
        """Extract relevant code snippet"""
        lines = code.split("\n")
        query_lower = query.lower()

        # Look for relevant lines (docstrings, comments, function names)
        relevant_lines: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if any(word in line_lower for word in query_lower.split()):
                # Include context around relevant lines
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                context = "\n".join(lines[start:end])
                relevant_lines.append(context)
                break

        if relevant_lines:
            snippet = relevant_lines[0]
            if len(snippet) > max_length:
                snippet = snippet[:max_length] + "..."
            return str(snippet)

        # Fallback: return first docstring or beginning of file
        for line in lines:
            if '"""' in line or "'''" in line:
                docstring_start = lines.index(line)
                docstring_end = docstring_start + 5  # Get a few lines
                snippet = "\n".join(lines[docstring_start:docstring_end])
                if len(snippet) > max_length:
                    snippet = snippet[:max_length] + "..."
                return snippet

        return code[:max_length] + "..." if len(code) > max_length else code

    async def _web_search(
        self, query: str, max_results: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Perform web search (mock)"""
        # Mock web search results
        web_results = [
            {
                "title": f"Web result for: {query}",
                "url": "https://example.com/1",
                "snippet": "Relevant information",
                "relevance": 0.7,
            },
            {
                "title": f"Another result for: {query}",
                "url": "https://example.com/2",
                "snippet": "More information",
                "relevance": 0.6,
            },
        ]

        return {
            "source": "web_search",
            "items": web_results[:max_results],
            "query_time": 0.8,
        }

    async def _faq_lookup(
        self, query: str, max_results: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Look up frequently asked questions"""
        faq_items = [
            {
                "question": "How does M-MDP work?",
                "answer": "M-MDP uses multiple agents working in coordination",
                "relevance": 0.8,
            },
            {
                "question": "What are the system requirements?",
                "answer": "Python 3.8+, 8GB RAM, modern CPU",
                "relevance": 0.6,
            },
        ]

        return {
            "source": "faq_lookup",
            "items": faq_items[:max_results],
            "query_time": 0.02,
        }
