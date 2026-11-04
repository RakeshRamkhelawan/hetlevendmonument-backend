"""
Ethical Knowledge Graph - TASK-120
Advanced knowledge graph system for ethical concepts, relationships, and reasoning paths
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import networkx as nx
    import numpy as np
    from networkx.algorithms import community
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

# Optional graph libraries
try:
    import networkx as nx
    from networkx.algorithms import community

    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False

# Optional advanced graph processing
try:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from src.core.shared.llm_client import LLMClient, LLMMessage, create_llm_client

logger = logging.getLogger(__name__)


class NodeType(Enum):
    """Types of nodes in the ethical knowledge graph"""

    CONCEPT = "concept"  # Ethical concepts (privacy, autonomy, etc.)
    PRINCIPLE = "principle"  # Ethical principles (beneficence, non-maleficence)
    FRAMEWORK = "framework"  # Ethical frameworks (deontological, consequentialist)
    RULE = "rule"  # Specific ethical rules
    CASE = "case"  # Historical cases/scenarios
    STAKEHOLDER = "stakeholder"  # Affected parties
    OUTCOME = "outcome"  # Potential consequences
    ACTION = "action"  # Specific actions or decisions
    CONTEXT = "context"  # Contextual factors
    METRIC = "metric"  # Measurement criteria


class RelationshipType(Enum):
    """Types of relationships in the ethical knowledge graph"""

    IMPLIES = "implies"  # A implies B
    CONFLICTS_WITH = "conflicts_with"  # A conflicts with B
    SUPPORTS = "supports"  # A supports B
    REQUIRES = "requires"  # A requires B
    PART_OF = "part_of"  # A is part of B
    SIMILAR_TO = "similar_to"  # A is similar to B
    CAUSES = "causes"  # A causes B
    PREVENTS = "prevents"  # A prevents B
    APPLIES_TO = "applies_to"  # A applies to B
    MEASURED_BY = "measured_by"  # A is measured by B
    DEPENDS_ON = "depends_on"  # A depends on B
    VIOLATES = "violates"  # A violates B
    EXEMPLIFIES = "exemplifies"  # A exemplifies B


@dataclass
class KnowledgeNode:
    """Represents a node in the ethical knowledge graph"""

    node_id: str
    node_type: NodeType
    name: str
    description: str
    properties: dict[str, Any]  # heterogeneous node properties - best possible type  # TODO(TYPE): replace Any with concrete type
    confidence_score: float
    creation_timestamp: str
    last_updated: str
    source: str
    tags: list[str]


@dataclass
class KnowledgeRelationship:
    """Represents a relationship between nodes in the knowledge graph"""

    relationship_id: str
    source_node_id: str
    target_node_id: str
    relationship_type: RelationshipType
    weight: float
    confidence: float
    evidence: list[str]
    context: dict[str, Any]  # heterogeneous relationship context - best possible type  # TODO(TYPE): replace Any with concrete type
    creation_timestamp: str


@dataclass
class GraphQuery:
    """Represents a query against the knowledge graph"""

    query_id: str
    query_text: str
    query_type: str  # 'path', 'similarity', 'neighbors', 'subgraph'
    parameters: dict[str, Any]  # query parameters vary by query_type - best possible type  # TODO(TYPE): replace Any with concrete type
    timestamp: str


@dataclass
class QueryResult:
    """Results from a knowledge graph query"""

    query_id: str
    nodes: list[KnowledgeNode]
    relationships: list[KnowledgeRelationship]
    paths: list[list[str]]
    metrics: dict[str, float]
    explanation: str


class EthicalKnowledgeGraph:
    """Advanced knowledge graph for ethical concepts and reasoning"""

    def __init__(self, graph_path: str = "models/knowledge_graph") -> None:
        self.graph_path = Path(graph_path)
        self.graph_path.mkdir(parents=True, exist_ok=True)

        # Core graph structures
        self.nodes: dict[str, KnowledgeNode] = {}
        self.relationships: dict[str, KnowledgeRelationship] = {}
        self.graph: Any | None = None  # nx.MultiDiGraph when NETWORKX_AVAILABLE, else None  # TODO(TYPE): replace Any with concrete type

        # Indexing and search
        self.node_index: dict[str, set[str]] = defaultdict(set)  # Concept -> node_ids
        self.type_index: dict[NodeType, set[str]] = defaultdict(set)  # Type -> node_ids
        self.relationship_index: dict[str, set[str]] = defaultdict(
            set
        )  # Source -> relationship_ids

        # Vector embeddings and similarity
        self.node_embeddings: dict[
            str, np.ndarray[Any, Any]  # TODO(TYPE): replace Any with concrete type
        ] = {}  # dense float32 embedding per node
        self.vectorizer: Any | None = None  # TfidfVectorizer when SKLEARN_AVAILABLE, else None  # TODO(TYPE): replace Any with concrete type

        # Query and reasoning
        self.query_history: list[GraphQuery] = []
        self.reasoning_cache: dict[str, Any] = {}  # polymorphic cache - best possible type  # TODO(TYPE): replace Any with concrete type

        # Graph analytics
        self.centrality_scores: dict[str, float] = {}
        self.community_clusters: dict[str, int] = {}
        self.graph_metrics: dict[str, float] = {}

        # LLM for advanced reasoning
        self.llm_client: LLMClient | None = None

        logger.info("Ethical Knowledge Graph initialized")

    async def initialize(self) -> bool:
        """Initialize the knowledge graph system"""
        try:
            # Initialize LLM client
            self.llm_client = create_llm_client("anthropic")

            # Initialize graph structure
            if NETWORKX_AVAILABLE:
                self.graph = nx.MultiDiGraph()
                logger.info("NetworkX graph initialized")

            # Load existing knowledge graph
            await self._load_knowledge_graph()

            # Initialize with core ethical concepts if empty
            if not self.nodes:
                await self._initialize_core_ethical_concepts()

            # Build embeddings and indexes
            await self._build_embeddings_and_indexes()

            # Calculate graph analytics
            await self._calculate_graph_analytics()

            logger.info(
                f"Knowledge graph initialized with {len(self.nodes)} nodes and {len(self.relationships)} relationships"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Ethical Knowledge Graph: {e}")
            return False

    async def add_concept(
        self,
        name: str,
        description: str,
        concept_type: NodeType = NodeType.CONCEPT,
        properties: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        tags: list[str] | None = None,
    ) -> str:
        """Add a new ethical concept to the knowledge graph"""
        try:
            node_id = self._generate_node_id(name, concept_type)

            node = KnowledgeNode(
                node_id=node_id,
                node_type=concept_type,
                name=name,
                description=description,
                properties=properties or {},
                confidence_score=0.8,  # Default confidence
                creation_timestamp=datetime.now(timezone.utc).isoformat(),
                last_updated=datetime.now(timezone.utc).isoformat(),
                source="manual_input",
                tags=tags or [],
            )

            self.nodes[node_id] = node

            # Update indexes
            self._update_indexes_for_node(node)

            # Add to NetworkX graph if available
            if self.graph is not None:
                self.graph.add_node(node_id, **asdict(node))

            logger.info(f"Added concept: {name} ({node_id})")
            return node_id

        except Exception as e:
            logger.error(f"Error adding concept {name}: {e}")
            raise

    async def add_relationship(
        self,
        source_concept: str,
        target_concept: str,
        relationship_type: RelationshipType,
        weight: float = 1.0,
        confidence: float = 0.8,
        evidence: list[str] | None = None,
        context: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Add a relationship between concepts"""
        try:
            # Find node IDs
            source_id = await self._find_node_id(source_concept)
            target_id = await self._find_node_id(target_concept)

            if not source_id or not target_id:
                raise ValueError(f"Could not find nodes for {source_concept} -> {target_concept}")

            relationship_id = self._generate_relationship_id(
                source_id, target_id, relationship_type
            )

            relationship = KnowledgeRelationship(
                relationship_id=relationship_id,
                source_node_id=source_id,
                target_node_id=target_id,
                relationship_type=relationship_type,
                weight=weight,
                confidence=confidence,
                evidence=evidence or [],
                context=context or {},
                creation_timestamp=datetime.now(timezone.utc).isoformat(),
            )

            self.relationships[relationship_id] = relationship

            # Update indexes
            self.relationship_index[source_id].add(relationship_id)
            self.relationship_index[target_id].add(relationship_id)

            # Add to NetworkX graph if available
            if self.graph is not None:
                self.graph.add_edge(
                    source_id,
                    target_id,
                    relationship_type=relationship_type.value,
                    weight=weight,
                    confidence=confidence,
                )

            logger.info(
                f"Added relationship: {source_concept} -{relationship_type.value}-> {target_concept}"
            )
            return relationship_id

        except Exception as e:
            logger.error(f"Error adding relationship {source_concept} -> {target_concept}: {e}")
            raise

    async def find_ethical_path(
        self, start_concept: str, end_concept: str, max_depth: int = 5
    ) -> list[list[str]]:
        """Find reasoning paths between ethical concepts"""
        try:
            start_id = await self._find_node_id(start_concept)
            end_id = await self._find_node_id(end_concept)

            if not start_id or not end_id:
                return []

            paths: list[list[str]] = []

            if NETWORKX_AVAILABLE and self.graph is not None:
                try:
                    # Find all simple paths up to max_depth
                    all_paths = nx.all_simple_paths(self.graph, start_id, end_id, cutoff=max_depth)

                    for path in all_paths:
                        # Convert node IDs to concept names
                        concept_path: list[str] = []
                        for node_id in path:
                            if node_id in self.nodes:
                                concept_path.append(self.nodes[node_id].name)
                        paths.append(concept_path)

                        # Limit number of paths to avoid explosion
                        if len(paths) >= 10:
                            break

                except nx.NetworkXNoPath:
                    pass
            else:
                # Fallback: breadth-first search
                paths = await self._find_paths_bfs(start_id, end_id, max_depth)

            return paths

        except Exception as e:
            logger.error(f"Error finding path from {start_concept} to {end_concept}: {e}")
            return []

    async def get_similar_concepts(
        self, concept: str, similarity_threshold: float = 0.7, limit: int = 10
    ) -> list[tuple[str, float]]:
        """Find concepts similar to the given concept"""
        try:
            concept_id = await self._find_node_id(concept)
            if not concept_id:
                return []

            similar_concepts: list[tuple[str, float]] = []
            if SKLEARN_AVAILABLE and self.node_embeddings and concept_id in self.node_embeddings:
                # Use vector similarity
                concept_vector = self.node_embeddings[concept_id]

                for other_id, other_vector in self.node_embeddings.items():
                    if other_id != concept_id:
                        similarity = cosine_similarity([concept_vector], [other_vector])[0][0]

                        if similarity >= similarity_threshold:
                            other_name = self.nodes[other_id].name
                            similar_concepts.append((other_name, float(similarity)))

                # Sort by similarity
                similar_concepts.sort(key=lambda x: x[1], reverse=True)
                return similar_concepts[:limit]

            else:
                # Fallback: use graph neighbors and shared relationships
                return await self._find_similar_concepts_fallback(concept_id, limit)

        except Exception as e:
            logger.error(f"Error finding similar concepts to {concept}: {e}")
            return []

    async def analyze_concept_relationships(self, concept: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze all relationships for a given concept"""
        try:
            concept_id = await self._find_node_id(concept)
            if not concept_id:
                return {}

            analysis: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "concept": concept,
                "node_id": concept_id,
                "outgoing_relationships": [],
                "incoming_relationships": [],
                "relationship_summary": {},
                "centrality_measures": {},
                "community_info": {},
            }

            # Analyze outgoing relationships
            if concept_id in self.relationship_index:
                for rel_id in self.relationship_index[concept_id]:
                    rel = self.relationships[rel_id]

                    if rel.source_node_id == concept_id:
                        target_name = self.nodes[rel.target_node_id].name
                        analysis["outgoing_relationships"].append(
                            {
                                "target": target_name,
                                "type": rel.relationship_type.value,
                                "weight": rel.weight,
                                "confidence": rel.confidence,
                            }
                        )

                    elif rel.target_node_id == concept_id:
                        source_name = self.nodes[rel.source_node_id].name
                        analysis["incoming_relationships"].append(
                            {
                                "source": source_name,
                                "type": rel.relationship_type.value,
                                "weight": rel.weight,
                                "confidence": rel.confidence,
                            }
                        )

            # Relationship type summary
            rel_types: defaultdict[str, int] = defaultdict(int)
            for rel in analysis["outgoing_relationships"] + analysis["incoming_relationships"]:
                rel_types[rel["type"]] += 1
            analysis["relationship_summary"] = dict(rel_types)

            # Add centrality measures if available
            if concept_id in self.centrality_scores:
                analysis["centrality_measures"]["betweenness"] = self.centrality_scores.get(
                    f"{concept_id}_betweenness", 0
                )
                analysis["centrality_measures"]["closeness"] = self.centrality_scores.get(
                    f"{concept_id}_closeness", 0
                )
                analysis["centrality_measures"]["degree"] = self.centrality_scores.get(
                    f"{concept_id}_degree", 0
                )

            # Community information
            if concept_id in self.community_clusters:
                analysis["community_info"]["cluster_id"] = self.community_clusters[concept_id]
                analysis["community_info"]["cluster_size"] = len(
                    [
                        n
                        for n, c in self.community_clusters.items()
                        if c == self.community_clusters[concept_id]
                    ]
                )

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing relationships for {concept}: {e}")
            return {}

    async def query_subgraph(self, center_concepts: list[str], depth: int = 2) -> QueryResult:
        """Extract a subgraph around specified concepts"""
        try:
            query_id = f"subgraph_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

            # Find center node IDs
            center_ids: list[str] = []
            for concept in center_concepts:
                node_id = await self._find_node_id(concept)
                if node_id:
                    center_ids.append(node_id)

            if not center_ids:
                return QueryResult(query_id, [], [], [], {}, "No center concepts found")

            # Collect nodes within specified depth
            subgraph_nodes = set(center_ids)
            current_level = set(center_ids)

            for d in range(depth):
                next_level = set()

                for node_id in current_level:
                    # Add neighbors
                    neighbors = await self._get_node_neighbors(node_id)
                    next_level.update(neighbors)

                subgraph_nodes.update(next_level)
                current_level = next_level

            # Collect relevant relationships
            subgraph_relationships: list[KnowledgeRelationship] = []
            for rel_id, rel in self.relationships.items():
                if rel.source_node_id in subgraph_nodes and rel.target_node_id in subgraph_nodes:
                    subgraph_relationships.append(rel)

            # Create result
            result_nodes = [
                self.nodes[node_id] for node_id in subgraph_nodes if node_id in self.nodes
            ]

            return QueryResult(
                query_id=query_id,
                nodes=result_nodes,
                relationships=subgraph_relationships,
                paths=[],
                metrics={
                    "node_count": len(result_nodes),
                    "relationship_count": len(subgraph_relationships),
                    "depth": depth,
                    "center_concepts": len(center_concepts),
                },
                explanation=f"Subgraph with {len(result_nodes)} nodes and {len(subgraph_relationships)} relationships",
            )

        except Exception as e:
            error_query_id = (
                f"subgraph_error_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            )
            logger.error(f"Error querying subgraph: {e}")
            return QueryResult(error_query_id, [], [], [], {}, f"Error: {str(e)}")

    async def detect_ethical_conflicts(self, scenario_concepts: list[str]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Detect potential conflicts between ethical concepts in a scenario"""
        try:
            conflicts: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
            concept_ids: list[str] = []
            # Find concept IDs
            for concept in scenario_concepts:
                node_id = await self._find_node_id(concept)
                if node_id:
                    concept_ids.append(node_id)

            # Look for conflict relationships
            for i, id1 in enumerate(concept_ids):
                for j, id2 in enumerate(concept_ids):
                    if i < j:  # Avoid duplicate checks
                        conflict_rels = await self._find_relationships_between_nodes(
                            id1, id2, [RelationshipType.CONFLICTS_WITH]
                        )

                        if conflict_rels:
                            conflicts.append(
                                {
                                    "concept1": self.nodes[id1].name,
                                    "concept2": self.nodes[id2].name,
                                    "conflict_type": conflict_rels[0].relationship_type.value,
                                    "confidence": conflict_rels[0].confidence,
                                    "evidence": conflict_rels[0].evidence,
                                }
                            )

            # Analyze conflict severity
            conflict_analysis: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "conflicts_detected": len(conflicts),
                "conflict_details": conflicts,
                "overall_conflict_score": (
                    len(conflicts) / max(1, len(concept_ids)) if concept_ids else 0
                ),
                "resolution_strategies": [],
            }

            # Generate resolution strategies
            for conflict in conflicts:
                strategies = await self._generate_conflict_resolution_strategies(conflict)
                conflict_analysis["resolution_strategies"].extend(strategies)

            return conflict_analysis

        except Exception as e:
            logger.error(f"Error detecting ethical conflicts: {e}")
            return {"error": str(e)}

    async def enrich_concept_knowledge(self, concept: str, additional_info: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Enrich an existing concept with additional knowledge"""
        try:
            concept_id = await self._find_node_id(concept)
            if not concept_id:
                return False

            node = self.nodes[concept_id]

            # Update properties
            node.properties.update(additional_info.get("properties", {}))

            # Update tags
            new_tags = additional_info.get("tags", [])
            node.tags.extend([tag for tag in new_tags if tag not in node.tags])

            # Update description if provided
            if "description" in additional_info:
                node.description = additional_info["description"]

            # Update confidence if provided
            if "confidence_score" in additional_info:
                node.confidence_score = additional_info["confidence_score"]

            node.last_updated = datetime.now(timezone.utc).isoformat()

            # Rebuild embeddings for this node
            if SKLEARN_AVAILABLE:
                await self._update_node_embedding(concept_id)

            logger.info(f"Enriched concept: {concept}")
            return True

        except Exception as e:
            logger.error(f"Error enriching concept {concept}: {e}")
            return False

    async def generate_ethical_insights(self, query_concepts: list[str]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate insights about ethical relationships and implications"""
        try:
            insights: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "query_concepts": query_concepts,
                "concept_analysis": {},
                "relationship_insights": [],
                "graph_patterns": {},
                "recommendations": [],
                "confidence_scores": {},
            }

            # Analyze each concept
            for concept in query_concepts:
                analysis = await self.analyze_concept_relationships(concept)
                insights["concept_analysis"][concept] = analysis

            # Find interesting patterns
            patterns = await self._identify_graph_patterns(query_concepts)
            insights["graph_patterns"] = patterns

            # Generate relationship insights
            for i, concept1 in enumerate(query_concepts):
                for j, concept2 in enumerate(query_concepts):
                    if i < j:
                        relationship_insight = await self._analyze_concept_pair(concept1, concept2)
                        if relationship_insight:
                            insights["relationship_insights"].append(relationship_insight)

            # Generate recommendations using LLM if available
            if self.llm_client:
                recommendations = await self._generate_llm_insights(query_concepts, insights)
                insights["recommendations"] = recommendations

            return insights

        except Exception as e:
            logger.error(f"Error generating ethical insights: {e}")
            return {"error": str(e)}

    # Private helper methods

    def _generate_node_id(self, name: str, node_type: NodeType) -> str:
        """Generate unique node ID"""
        content = f"{name}_{node_type.value}_{datetime.now(timezone.utc).isoformat()}"
        return f"node_{hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:12]}"

    def _generate_relationship_id(
        self, source_id: str, target_id: str, rel_type: RelationshipType
    ) -> str:
        """Generate unique relationship ID"""
        content = f"{source_id}_{target_id}_{rel_type.value}"
        return f"rel_{hashlib.md5(content.encode(), usedforsecurity=False).hexdigest()[:12]}"

    async def _find_node_id(self, concept_name: str) -> str | None:
        """Find node ID by concept name"""
        concept_lower = concept_name.lower()

        # Exact match first
        for node_id, node in self.nodes.items():
            if node.name.lower() == concept_lower:
                return node_id

        # Partial match
        for node_id, node in self.nodes.items():
            if concept_lower in node.name.lower() or node.name.lower() in concept_lower:
                return node_id

        # Check aliases in properties
        for node_id, node in self.nodes.items():
            aliases = node.properties.get("aliases", [])
            for alias in aliases:
                if alias.lower() == concept_lower:
                    return node_id

        return None

    def _update_indexes_for_node(self, node: KnowledgeNode) -> None:
        """Update search indexes for a node"""
        # Type index
        self.type_index[node.node_type].add(node.node_id)

        # Concept name index
        words = node.name.lower().split()
        for word in words:
            self.node_index[word].add(node.node_id)

        # Tags index
        for tag in node.tags:
            self.node_index[tag.lower()].add(node.node_id)

    async def _find_paths_bfs(self, start_id: str, end_id: str, max_depth: int) -> list[list[str]]:
        """Find paths using breadth-first search (fallback method)"""
        paths: list[list[str]] = []
        queue = deque([(start_id, [start_id])])
        visited = set()

        while queue and len(paths) < 10:  # Limit paths
            current_id, path = queue.popleft()

            if len(path) > max_depth:
                continue

            if current_id == end_id and len(path) > 1:
                concept_path = [self.nodes[nid].name for nid in path if nid in self.nodes]
                paths.append(concept_path)
                continue

            if current_id in visited:
                continue

            visited.add(current_id)

            # Add neighbors
            neighbors = await self._get_node_neighbors(current_id)
            for neighbor_id in neighbors:
                if neighbor_id not in path:  # Avoid cycles
                    queue.append((neighbor_id, path + [neighbor_id]))

        return paths

    async def _get_node_neighbors(self, node_id: str) -> set[str]:
        """Get all neighboring nodes"""
        neighbors = set()

        if node_id in self.relationship_index:
            for rel_id in self.relationship_index[node_id]:
                rel = self.relationships[rel_id]

                if rel.source_node_id == node_id:
                    neighbors.add(rel.target_node_id)
                elif rel.target_node_id == node_id:
                    neighbors.add(rel.source_node_id)

        return neighbors

    async def _find_similar_concepts_fallback(
        self, concept_id: str, limit: int
    ) -> list[tuple[str, float]]:
        """Find similar concepts using graph structure (fallback)"""
        similar: list[tuple[str, float]] = []
        concept_node = self.nodes[concept_id]

        # Find concepts with shared relationships
        neighbors = await self._get_node_neighbors(concept_id)

        neighbor_concepts: defaultdict[str, int] = defaultdict(int)

        for neighbor_id in neighbors:
            neighbor_neighbors = await self._get_node_neighbors(neighbor_id)

            for nn_id in neighbor_neighbors:
                if nn_id != concept_id:
                    neighbor_concepts[nn_id] += 1

        # Score by shared neighbors and type similarity
        for other_id, shared_count in neighbor_concepts.items():
            if other_id in self.nodes:
                other_node = self.nodes[other_id]

                # Base similarity from shared neighbors
                similarity = shared_count / max(len(neighbors), 1)

                # Type similarity bonus
                if other_node.node_type == concept_node.node_type:
                    similarity += 0.2

                # Tag similarity bonus
                shared_tags = set(concept_node.tags) & set(other_node.tags)
                similarity += len(shared_tags) * 0.1

                similar.append((other_node.name, similarity))

        similar.sort(key=lambda x: x[1], reverse=True)
        return similar[:limit]

    async def _find_relationships_between_nodes(
        self,
        node1_id: str,
        node2_id: str,
        relationship_types: list[RelationshipType] | None = None,
    ) -> list[KnowledgeRelationship]:
        """Find relationships between two specific nodes"""
        relationships: list[KnowledgeRelationship] = []
        # Check all relationships involving node1
        if node1_id in self.relationship_index:
            for rel_id in self.relationship_index[node1_id]:
                rel = self.relationships[rel_id]

                # Check if this relationship connects to node2
                connects_to_node2 = (
                    rel.source_node_id == node1_id and rel.target_node_id == node2_id
                ) or (rel.source_node_id == node2_id and rel.target_node_id == node1_id)

                if connects_to_node2:
                    if relationship_types is None or rel.relationship_type in relationship_types:
                        relationships.append(rel)

        return relationships

    async def _generate_conflict_resolution_strategies(self, conflict: dict[str, Any]) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Generate strategies for resolving ethical conflicts"""
        strategies: list[str] = []
        concept1 = conflict["concept1"].lower()
        concept2 = conflict["concept2"].lower()

        # Common conflict resolution patterns
        if "privacy" in concept1 and "transparency" in concept2:
            strategies.extend(
                [
                    "Implement selective transparency that protects individual privacy",
                    "Use anonymization techniques to enable transparency without privacy violations",
                    "Establish clear privacy boundaries for transparency requirements",
                ]
            )

        elif "autonomy" in concept1 and "beneficence" in concept2:
            strategies.extend(
                [
                    "Respect individual choice while providing clear benefit information",
                    "Implement opt-in mechanisms that preserve autonomy",
                    "Balance paternalistic interventions with respect for personal agency",
                ]
            )

        elif "justice" in concept1 and "efficiency" in concept2:
            strategies.extend(
                [
                    "Optimize efficiency within fairness constraints",
                    "Implement gradual transitions that balance both values",
                    "Use efficiency gains to support justice initiatives",
                ]
            )

        else:
            # Generic strategies
            strategies.extend(
                [
                    f"Find middle ground between {concept1} and {concept2}",
                    "Implement contextual decision-making that considers both values",
                    "Establish clear priority frameworks for conflict resolution",
                ]
            )

        return strategies

    async def _identify_graph_patterns(self, concepts: list[str]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Identify interesting patterns in the graph around given concepts"""
        patterns: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "hubs": [],  # Highly connected concepts
            "bridges": [],  # Concepts that bridge different clusters
            "clusters": {},  # Concept clusters
            "outliers": [],  # Isolated concepts
        }

        if not self.centrality_scores or not NETWORKX_AVAILABLE:
            return patterns

        concept_ids: list[str] = []
        for concept in concepts:
            node_id = await self._find_node_id(concept)
            if node_id:
                concept_ids.append(node_id)

        # Find hubs (high degree centrality)
        for concept_id in concept_ids:
            degree_key = f"{concept_id}_degree"
            if degree_key in self.centrality_scores and self.centrality_scores[degree_key] > 0.7:
                patterns["hubs"].append(self.nodes[concept_id].name)

        # Find bridges (high betweenness centrality)
        for concept_id in concept_ids:
            between_key = f"{concept_id}_betweenness"
            if between_key in self.centrality_scores and self.centrality_scores[between_key] > 0.7:
                patterns["bridges"].append(self.nodes[concept_id].name)

        return patterns

    async def _analyze_concept_pair(self, concept1: str, concept2: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Analyze the relationship between two concepts"""
        id1 = await self._find_node_id(concept1)
        id2 = await self._find_node_id(concept2)

        if not id1 or not id2:
            return None

        # Find direct relationships
        direct_rels = await self._find_relationships_between_nodes(id1, id2)

        # Find paths
        paths = await self.find_ethical_path(concept1, concept2, max_depth=3)

        if direct_rels or paths:
            return {
                "concept1": concept1,
                "concept2": concept2,
                "direct_relationships": [
                    {
                        "type": rel.relationship_type.value,
                        "confidence": rel.confidence,
                        "weight": rel.weight,
                    }
                    for rel in direct_rels
                ],
                "connection_paths": paths[:3],  # Top 3 paths
                "connection_strength": len(direct_rels) + len(paths),
            }

        return None

    async def _generate_llm_insights(
        self,
        concepts: list[str],
        analysis: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:
        """Generate insights using LLM reasoning"""
        if not self.llm_client:
            return []

        try:
            # Create context for LLM
            context = f"""
            Ethical Concept Analysis:

            Concepts: {", ".join(concepts)}

            Graph Analysis Summary:
            - Total concepts analyzed: {len(analysis.get("concept_analysis", {}))}
            - Relationship insights found: {len(analysis.get("relationship_insights", []))}
            - Graph patterns identified: {len(analysis.get("graph_patterns", {}))}

            Key Relationships:
            """

            for insight in analysis.get("relationship_insights", [])[:3]:
                context += f"- {insight.get('concept1')} and {insight.get('concept2')}: {len(insight.get('direct_relationships', []))} direct connections\n"

            prompt = f"""
            {context}

            Based on this ethical knowledge graph analysis, provide 3-5 key insights about:
            1. The most important ethical relationships
            2. Potential areas of concern or conflict
            3. Recommendations for ethical decision-making
            4. Patterns that might affect ethical reasoning

            Keep each insight concise (1-2 sentences) and actionable.
            """

            messages = [LLMMessage(role="user", content=prompt)]
            response = await self.llm_client.chat_completion(messages)

            # Parse insights from response
            insights_text = response.content.strip()
            insights = [
                insight.strip()
                for insight in insights_text.split("\n")
                if insight.strip() and not insight.startswith("#")
            ]

            return insights[:5]  # Limit to 5 insights

        except Exception as e:
            logger.error(f"Error generating LLM insights: {e}")
            return []

    # Initialization methods

    async def _initialize_core_ethical_concepts(self) -> None:
        """Initialize the graph with core ethical concepts"""
        try:
            # Core ethical principles
            principles = [
                (
                    "Autonomy",
                    "Respect for individual self-determination and freedom of choice",
                    NodeType.PRINCIPLE,
                ),
                (
                    "Beneficence",
                    "Obligation to act in the best interest of others",
                    NodeType.PRINCIPLE,
                ),
                ("Non-maleficence", "Obligation to do no harm", NodeType.PRINCIPLE),
                (
                    "Justice",
                    "Fair distribution of benefits and burdens",
                    NodeType.PRINCIPLE,
                ),
                (
                    "Privacy",
                    "Right to control personal information and maintain confidentiality",
                    NodeType.CONCEPT,
                ),
                (
                    "Transparency",
                    "Openness and clarity in processes and decision-making",
                    NodeType.CONCEPT,
                ),
                (
                    "Accountability",
                    "Responsibility for decisions and their consequences",
                    NodeType.CONCEPT,
                ),
                (
                    "Dignity",
                    "Inherent worth and respect for all persons",
                    NodeType.CONCEPT,
                ),
                (
                    "Consent",
                    "Voluntary agreement based on understanding",
                    NodeType.CONCEPT,
                ),
                ("Fairness", "Impartial and just treatment", NodeType.CONCEPT),
            ]

            # Add principle nodes
            principle_ids: dict[str, str] = {}
            for name, desc, node_type in principles:
                node_id = await self.add_concept(
                    name, desc, node_type, tags=["core", "fundamental"]
                )
                principle_ids[name.lower()] = node_id

            # Core relationships
            relationships = [
                ("autonomy", "consent", RelationshipType.REQUIRES, 0.9),
                ("beneficence", "non-maleficence", RelationshipType.SUPPORTS, 0.8),
                ("privacy", "transparency", RelationshipType.CONFLICTS_WITH, 0.7),
                ("justice", "fairness", RelationshipType.SIMILAR_TO, 0.9),
                ("accountability", "transparency", RelationshipType.REQUIRES, 0.8),
                ("dignity", "autonomy", RelationshipType.SUPPORTS, 0.8),
                ("consent", "transparency", RelationshipType.REQUIRES, 0.7),
            ]

            # Add relationships
            for source, target, rel_type, weight in relationships:
                try:
                    await self.add_relationship(
                        source,
                        target,
                        rel_type,
                        weight,
                        evidence=["core_ethical_theory"],
                    )
                except Exception as e:
                    logger.warning(f"Could not add relationship {source} -> {target}: {e}")

            logger.info("Initialized core ethical concepts and relationships")

        except Exception as e:
            logger.error(f"Error initializing core concepts: {e}")

    async def _build_embeddings_and_indexes(self) -> None:
        """Build vector embeddings and search indexes"""
        if not SKLEARN_AVAILABLE:
            return

        try:
            # Prepare text data for embeddings
            texts: list[str] = []
            node_ids: list[str] = []
            for node_id, node in self.nodes.items():
                text = f"{node.name} {node.description} {' '.join(node.tags)}"
                texts.append(text)
                node_ids.append(node_id)

            if texts:
                # Create TF-IDF vectorizer
                vectorizer: Any = TfidfVectorizer(  # TODO(TYPE): replace Any with concrete type
                    max_features=1000, stop_words="english", ngram_range=(1, 2)
                )
                self.vectorizer = vectorizer

                # Fit and transform
                embeddings = vectorizer.fit_transform(texts)

                # Store embeddings
                for i, node_id in enumerate(node_ids):
                    # embeddings[i] is a scipy sparse matrix, convert to dense array
                    embedding_row: Any = embeddings[i]  # scipy sparse matrix row  # TODO(TYPE): replace Any with concrete type
                    self.node_embeddings[node_id] = embedding_row.toarray()[0]

                logger.info(f"Built embeddings for {len(texts)} concepts")

        except Exception as e:
            logger.error(f"Error building embeddings: {e}")

    async def _update_node_embedding(self, node_id: str) -> None:
        """Update embedding for a single node"""
        if self.vectorizer is None:
            return

        try:
            node = self.nodes[node_id]
            text = f"{node.name} {node.description} {' '.join(node.tags)}"

            # Transform using existing vectorizer
            vectorizer: Any = self.vectorizer  # TfidfVectorizer -- optional dependency  # TODO(TYPE): replace Any with concrete type
            embedding_matrix: Any = vectorizer.transform(  # TODO(TYPE): replace Any with concrete type
                [text]
            )  # scipy sparse matrix
            self.node_embeddings[node_id] = embedding_matrix.toarray()[0]

        except Exception as e:
            logger.error(f"Error updating embedding for {node_id}: {e}")

    async def _calculate_graph_analytics(self) -> None:
        """Calculate graph-wide analytics and metrics"""
        if not NETWORKX_AVAILABLE or not self.graph:
            return

        try:
            # Basic metrics
            self.graph_metrics = {
                "node_count": self.graph.number_of_nodes(),
                "edge_count": self.graph.number_of_edges(),
                "density": nx.density(self.graph),
                "is_connected": nx.is_weakly_connected(self.graph),
            }

            # Centrality measures
            if self.graph.number_of_nodes() > 0:
                # Degree centrality
                degree_centrality = nx.degree_centrality(self.graph)
                for node, score in degree_centrality.items():
                    self.centrality_scores[f"{node}_degree"] = score

                # Betweenness centrality
                betweenness_centrality = nx.betweenness_centrality(self.graph)
                for node, score in betweenness_centrality.items():
                    self.centrality_scores[f"{node}_betweenness"] = score

                # Closeness centrality (for strongly connected components)
                try:
                    closeness_centrality = nx.closeness_centrality(self.graph)
                    for node, score in closeness_centrality.items():
                        self.centrality_scores[f"{node}_closeness"] = score
                except Exception as e:
                    logger.debug(
                        f"Failed to calculate closeness centrality: {str(e)}",
                        exc_info=False,
                    )

            # Community detection
            try:
                # Convert to undirected for community detection
                undirected = self.graph.to_undirected()
                communities = community.greedy_modularity_communities(undirected)

                for i, comm in enumerate(communities):
                    for node in comm:
                        self.community_clusters[node] = i

                self.graph_metrics["community_count"] = len(communities)

            except Exception as e:
                logger.warning(f"Community detection failed: {e}")

            logger.info(
                f"Calculated analytics for graph with {self.graph_metrics['node_count']} nodes"
            )

        except Exception as e:
            logger.error(f"Error calculating graph analytics: {e}")

    async def _load_knowledge_graph(self) -> None:
        """Load existing knowledge graph from storage"""
        try:
            # Load nodes
            nodes_file = self.graph_path / "nodes.json"
            if nodes_file.exists():
                with open(nodes_file) as f:
                    nodes_data = json.load(f)

                    for node_data in nodes_data:
                        node_data["node_type"] = NodeType(node_data["node_type"])
                        node = KnowledgeNode(**node_data)
                        self.nodes[node.node_id] = node
                        self._update_indexes_for_node(node)

            # Load relationships
            relationships_file = self.graph_path / "relationships.json"
            if relationships_file.exists():
                with open(relationships_file) as f:
                    relationships_data = json.load(f)

                    for rel_data in relationships_data:
                        rel_data["relationship_type"] = RelationshipType(
                            rel_data["relationship_type"]
                        )
                        rel = KnowledgeRelationship(**rel_data)
                        self.relationships[rel.relationship_id] = rel

                        # Update indexes
                        self.relationship_index[rel.source_node_id].add(rel.relationship_id)
                        self.relationship_index[rel.target_node_id].add(rel.relationship_id)

            # Rebuild NetworkX graph
            if NETWORKX_AVAILABLE:
                self.graph = nx.MultiDiGraph()

                # Add nodes
                for node_id, node in self.nodes.items():
                    self.graph.add_node(node_id, **asdict(node))

                # Add edges
                for rel in self.relationships.values():
                    self.graph.add_edge(
                        rel.source_node_id,
                        rel.target_node_id,
                        relationship_type=rel.relationship_type.value,
                        weight=rel.weight,
                        confidence=rel.confidence,
                    )

            if self.nodes:
                logger.info(
                    f"Loaded knowledge graph with {len(self.nodes)} nodes and {len(self.relationships)} relationships"
                )

        except Exception as e:
            logger.error(f"Error loading knowledge graph: {e}")

    async def save_knowledge_graph(self) -> None:
        """Save knowledge graph to storage"""
        try:
            # Save nodes
            nodes_data: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
            for node in self.nodes.values():
                node_dict = asdict(node)
                node_dict["node_type"] = node.node_type.value
                nodes_data.append(node_dict)

            with open(self.graph_path / "nodes.json", "w") as f:
                json.dump(nodes_data, f, indent=2)

            # Save relationships
            relationships_data: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
            for rel in self.relationships.values():
                rel_dict = asdict(rel)
                rel_dict["relationship_type"] = rel.relationship_type.value
                relationships_data.append(rel_dict)

            with open(self.graph_path / "relationships.json", "w") as f:
                json.dump(relationships_data, f, indent=2)

            # Save graph metrics
            with open(self.graph_path / "graph_metrics.json", "w") as f:
                json.dump(
                    {
                        "graph_metrics": self.graph_metrics,
                        "centrality_scores": self.centrality_scores,
                        "community_clusters": self.community_clusters,
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                    },
                    f,
                    indent=2,
                )

            logger.info("Knowledge graph saved successfully")

        except Exception as e:
            logger.error(f"Error saving knowledge graph: {e}")

    async def get_graph_statistics(
        self,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive graph statistics"""
        return {
            "node_count": len(self.nodes),
            "relationship_count": len(self.relationships),
            "node_types": {nt.value: len(ids) for nt, ids in self.type_index.items()},
            "relationship_types": {
                rt.value: len([r for r in self.relationships.values() if r.relationship_type == rt])
                for rt in RelationshipType
            },
            "graph_metrics": self.graph_metrics,
            "centrality_available": bool(self.centrality_scores),
            "embeddings_available": bool(self.node_embeddings),
            "networkx_available": NETWORKX_AVAILABLE,
            "sklearn_available": SKLEARN_AVAILABLE,
            "query_history_size": len(self.query_history),
        }


# Factory function
async def create_ethical_knowledge_graph() -> EthicalKnowledgeGraph:
    """Create and initialize ethical knowledge graph"""
    kg = EthicalKnowledgeGraph()
    await kg.initialize()
    return kg
