"""
Knowledge Graph - Relationship and entity management for knowledge entries
Implements graph-based knowledge representation with entity linking
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.shared.production_logging import SafeLogger

from .knowledge_base import KnowledgeEntry

logger = SafeLogger(__name__)


class EntityType(Enum):
    """Types of entities in the knowledge graph"""

    PERSON = "person"
    ORGANIZATION = "organization"
    CONCEPT = "concept"
    EVENT = "event"
    LOCATION = "location"
    DOCUMENT = "document"
    TOPIC = "topic"
    SKILL = "skill"
    TOOL = "tool"


class RelationshipType(Enum):
    """Types of relationships between entities"""

    RELATED_TO = "related_to"
    PART_OF = "part_o"
    INSTANCE_OF = "instance_o"
    CAUSED_BY = "caused_by"
    DEPENDS_ON = "depends_on"
    SIMILAR_TO = "similar_to"
    CONTRADICTS = "contradicts"
    MENTIONS = "mentions"
    CREATED_BY = "created_by"
    LOCATED_IN = "located_in"


@dataclass
class Entity:
    """Entity in the knowledge graph"""

    entity_id: str
    name: str
    entity_type: EntityType
    properties: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    confidence: float = 1.0
    created_at: datetime = field(default_factory=datetime.now)
    knowledge_entries: set[str] = field(default_factory=set)  # Entry IDs that mention this entity

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for serialization"""
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "entity_type": self.entity_type.value,
            "properties": self.properties,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "knowledge_entries": list(self.knowledge_entries),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Entity":  # TODO(TYPE): replace Any with concrete type
        """Create entity from dictionary"""
        data["entity_type"] = EntityType(data["entity_type"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["knowledge_entries"] = set(data.get("knowledge_entries", []))
        return cls(**data)


@dataclass
class Relationship:
    """Relationship between entities"""

    relationship_id: str
    source_entity_id: str
    target_entity_id: str
    relationship_type: RelationshipType
    properties: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    confidence: float = 1.0
    created_at: datetime = field(default_factory=datetime.now)
    knowledge_entries: set[str] = field(
        default_factory=set
    )  # Entry IDs that support this relationship

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for serialization"""
        return {
            "relationship_id": self.relationship_id,
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
            "relationship_type": self.relationship_type.value,
            "properties": self.properties,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "knowledge_entries": list(self.knowledge_entries),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Relationship":  # TODO(TYPE): replace Any with concrete type
        """Create relationship from dictionary"""
        data["relationship_type"] = RelationshipType(data["relationship_type"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["knowledge_entries"] = set(data.get("knowledge_entries", []))
        return cls(**data)


class KnowledgeGraph:
    """
    Knowledge graph for managing entities and relationships
    Provides graph-based knowledge representation and traversal
    """

    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}
        self.relationships: dict[str, Relationship] = {}
        self.entity_index: dict[str, set[str]] = {}  # name -> entity_ids (for name-based lookup)
        self.type_index: dict[EntityType, set[str]] = {}  # type -> entity_ids
        self.adjacency_list: dict[str, set[str]] = {}  # entity_id -> connected_entity_ids
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize knowledge graph"""
        try:
            self._build_indexes()
            self._initialized = True
            logger.info("Knowledge graph initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize knowledge graph: {e}")
            return False

    async def add_entity(self, entity: Entity) -> bool:
        """Add entity to the graph"""
        try:
            self.entities[entity.entity_id] = entity
            self._update_entity_indexes(entity)
            logger.debug(f"Added entity: {entity.entity_id} ({entity.name})")
            return True
        except Exception as e:
            logger.error(f"Failed to add entity {entity.entity_id}: {e}")
            return False

    async def add_relationship(self, relationship: Relationship) -> bool:
        """Add relationship to the graph"""
        try:
            # Verify that source and target entities exist
            if (
                relationship.source_entity_id not in self.entities
                or relationship.target_entity_id not in self.entities
            ):
                logger.warning("Cannot add relationship: missing entities")
                return False

            self.relationships[relationship.relationship_id] = relationship
            self._update_adjacency_list(relationship)
            logger.debug(f"Added relationship: {relationship.relationship_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add relationship {relationship.relationship_id}: {e}")
            return False

    async def find_entity_by_name(
        self, name: str, entity_type: EntityType | None = None
    ) -> list[Entity]:
        """Find entities by name (case-insensitive)"""
        try:
            name_lower = name.lower()
            matching_entities: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # Check exact name matches
            if name_lower in self.entity_index:
                for entity_id in self.entity_index[name_lower]:
                    entity = self.entities.get(entity_id)
                    if entity and (entity_type is None or entity.entity_type == entity_type):
                        matching_entities.append(entity)

            # Check partial name matches
            for indexed_name, entity_ids in self.entity_index.items():
                if name_lower in indexed_name or indexed_name in name_lower:
                    for entity_id in entity_ids:
                        entity = self.entities.get(entity_id)
                        if (
                            entity
                            and entity not in matching_entities
                            and (entity_type is None or entity.entity_type == entity_type)
                        ):
                            matching_entities.append(entity)

            return matching_entities
        except Exception as e:
            logger.error(f"Failed to find entity by name '{name}': {e}")
            return []

    async def get_entity_relationships(self, entity_id: str) -> list[Relationship]:
        """Get all relationships for an entity"""
        try:
            relationships: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for relationship in self.relationships.values():
                if (
                    relationship.source_entity_id == entity_id
                    or relationship.target_entity_id == entity_id
                ):
                    relationships.append(relationship)
            return relationships
        except Exception as e:
            logger.error(f"Failed to get relationships for entity {entity_id}: {e}")
            return []

    async def get_connected_entities(self, entity_id: str, max_depth: int = 2) -> set[str]:
        """Get entities connected to given entity within max_depth"""
        try:
            if entity_id not in self.entities:
                return set()

            connected = set()
            current_level = {entity_id}
            visited = set()

            for depth in range(max_depth):
                next_level = set()
                for current_entity in current_level:
                    if current_entity in visited:
                        continue

                    visited.add(current_entity)
                    if current_entity != entity_id:  # Don't include the starting entity
                        connected.add(current_entity)

                    # Get directly connected entities
                    adjacent_entities = self.adjacency_list.get(current_entity, set())
                    next_level.update(adjacent_entities)

                current_level = next_level

            return connected
        except Exception as e:
            logger.error(f"Failed to get connected entities for {entity_id}: {e}")
            return set()

    async def find_path(
        self, source_entity_id: str, target_entity_id: str, max_depth: int = 3
    ) -> list[str]:
        """Find shortest path between two entities"""
        try:
            if source_entity_id not in self.entities or target_entity_id not in self.entities:
                return []

            # BFS to find shortest path
            queue = [(source_entity_id, [source_entity_id])]
            visited = {source_entity_id}

            while queue:
                current_entity, path = queue.pop(0)

                if current_entity == target_entity_id:
                    return path

                if len(path) >= max_depth:
                    continue

                # Explore adjacent entities
                adjacent_entities = self.adjacency_list.get(current_entity, set())
                for adjacent_entity in adjacent_entities:
                    if adjacent_entity not in visited:
                        visited.add(adjacent_entity)
                        new_path = path + [adjacent_entity]
                        queue.append((adjacent_entity, new_path))

            return []  # No path found
        except Exception as e:
            logger.error(f"Failed to find path from {source_entity_id} to {target_entity_id}: {e}")
            return []

    async def add_knowledge_entry(self, entry_id: str, entry: KnowledgeEntry) -> bool:
        """Extract entities and relationships from knowledge entry"""
        try:
            # Simple entity extraction (in a full implementation, use NLP)
            extracted_entities = await self._extract_entities_from_text(entry.content, entry_id)
            extracted_relationships = await self._extract_relationships_from_text(
                entry.content, entry_id
            )

            # Add extracted entities
            for entity in extracted_entities:
                entity.knowledge_entries.add(entry_id)
                await self.add_entity(entity)

            # Add extracted relationships
            for relationship in extracted_relationships:
                relationship.knowledge_entries.add(entry_id)
                await self.add_relationship(relationship)

            logger.debug(
                f"Processed knowledge entry {entry_id}: {len(extracted_entities)} entities, {len(extracted_relationships)} relationships"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to add knowledge entry to graph: {e}")
            return False

    async def remove_entry(self, entry_id: str) -> bool:
        """Remove knowledge entry references from graph"""
        try:
            # Remove entry from entities
            entities_to_remove: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for entity in self.entities.values():
                entity.knowledge_entries.discard(entry_id)
                # Remove entity if no longer referenced by any entries
                if not entity.knowledge_entries:
                    entities_to_remove.append(entity.entity_id)

            for entity_id in entities_to_remove:
                await self.remove_entity(entity_id)

            # Remove entry from relationships
            relationships_to_remove: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for relationship in self.relationships.values():
                relationship.knowledge_entries.discard(entry_id)
                # Remove relationship if no longer referenced by any entries
                if not relationship.knowledge_entries:
                    relationships_to_remove.append(relationship.relationship_id)

            for relationship_id in relationships_to_remove:
                await self.remove_relationship(relationship_id)

            return True
        except Exception as e:
            logger.error(f"Failed to remove entry {entry_id} from graph: {e}")
            return False

    async def remove_entity(self, entity_id: str) -> bool:
        """Remove entity and its relationships"""
        try:
            if entity_id not in self.entities:
                return False

            entity = self.entities[entity_id]

            # Remove from indexes
            self._remove_entity_from_indexes(entity)

            # Remove relationships involving this entity
            relationships_to_remove: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for relationship_id, relationship in self.relationships.items():
                if (
                    relationship.source_entity_id == entity_id
                    or relationship.target_entity_id == entity_id
                ):
                    relationships_to_remove.append(relationship_id)

            for relationship_id in relationships_to_remove:
                await self.remove_relationship(relationship_id)

            # Remove entity
            del self.entities[entity_id]

            logger.debug(f"Removed entity: {entity_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove entity {entity_id}: {e}")
            return False

    async def remove_relationship(self, relationship_id: str) -> bool:
        """Remove relationship from graph"""
        try:
            if relationship_id not in self.relationships:
                return False

            relationship = self.relationships[relationship_id]

            # Update adjacency list
            source_id = relationship.source_entity_id
            target_id = relationship.target_entity_id

            if source_id in self.adjacency_list:
                self.adjacency_list[source_id].discard(target_id)
            if target_id in self.adjacency_list:
                self.adjacency_list[target_id].discard(source_id)

            # Remove relationship
            del self.relationships[relationship_id]

            logger.debug(f"Removed relationship: {relationship_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove relationship {relationship_id}: {e}")
            return False

    async def get_related_entries(
        self, entry_id: str, limit: int = 5, similarity_threshold: float = 0.6
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Get knowledge entries related through the graph"""
        try:
            # Find entities mentioned in the entry
            related_entity_ids = set()
            for entity in self.entities.values():
                if entry_id in entity.knowledge_entries:
                    related_entity_ids.add(entity.entity_id)

            # Find connected entities
            all_connected = set()
            for entity_id in related_entity_ids:
                connected = await self.get_connected_entities(entity_id, max_depth=2)
                all_connected.update(connected)

            # Find entries that mention connected entities
            related_entry_ids = set()
            for entity_id in all_connected:
                if entity_id in self.entities:
                    entity = self.entities[entity_id]
                    related_entry_ids.update(entity.knowledge_entries)

            # Remove the original entry
            related_entry_ids.discard(entry_id)

            # Convert to SearchResult-like objects (placeholder implementation)
            # In a full implementation, these would be proper SearchResult objects
            return list(related_entry_ids)[:limit]

        except Exception as e:
            logger.error(f"Failed to get related entries for {entry_id}: {e}")
            return []

    async def get_graph_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get knowledge graph statistics"""
        try:
            entity_types_count: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            for entity_type, entity_ids in self.type_index.items():
                entity_types_count[entity_type.value] = len(entity_ids)

            relationship_types_count: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            for relationship in self.relationships.values():
                rel_type = relationship.relationship_type.value
                relationship_types_count[rel_type] = relationship_types_count.get(rel_type, 0) + 1

            return {
                "total_entities": len(self.entities),
                "total_relationships": len(self.relationships),
                "entity_types": entity_types_count,
                "relationship_types": relationship_types_count,
                "average_connections_per_entity": self._calculate_average_connections(),
                "most_connected_entities": await self._get_most_connected_entities(5),
            }
        except Exception as e:
            logger.error(f"Failed to get graph stats: {e}")
            return {}

    def _build_indexes(self) -> None:
        """Build search indexes"""
        self.entity_index.clear()
        self.type_index.clear()
        self.adjacency_list.clear()

        for entity in self.entities.values():
            self._update_entity_indexes(entity)

        for relationship in self.relationships.values():
            self._update_adjacency_list(relationship)

    def _update_entity_indexes(self, entity: Entity) -> None:
        """Update indexes when adding entity"""
        # Name index
        name_lower = entity.name.lower()
        if name_lower not in self.entity_index:
            self.entity_index[name_lower] = set()
        self.entity_index[name_lower].add(entity.entity_id)

        # Type index
        if entity.entity_type not in self.type_index:
            self.type_index[entity.entity_type] = set()
        self.type_index[entity.entity_type].add(entity.entity_id)

        # Initialize adjacency list
        if entity.entity_id not in self.adjacency_list:
            self.adjacency_list[entity.entity_id] = set()

    def _remove_entity_from_indexes(self, entity: Entity) -> None:
        """Remove entity from indexes"""
        # Name index
        name_lower = entity.name.lower()
        if name_lower in self.entity_index:
            self.entity_index[name_lower].discard(entity.entity_id)
            if not self.entity_index[name_lower]:
                del self.entity_index[name_lower]

        # Type index
        if entity.entity_type in self.type_index:
            self.type_index[entity.entity_type].discard(entity.entity_id)
            if not self.type_index[entity.entity_type]:
                del self.type_index[entity.entity_type]

        # Adjacency list
        if entity.entity_id in self.adjacency_list:
            del self.adjacency_list[entity.entity_id]

    def _update_adjacency_list(self, relationship: Relationship) -> None:
        """Update adjacency list when adding relationship"""
        source_id = relationship.source_entity_id
        target_id = relationship.target_entity_id

        if source_id not in self.adjacency_list:
            self.adjacency_list[source_id] = set()
        if target_id not in self.adjacency_list:
            self.adjacency_list[target_id] = set()

        self.adjacency_list[source_id].add(target_id)
        self.adjacency_list[target_id].add(source_id)

    async def _extract_entities_from_text(self, text: str, entry_id: str) -> list[Entity]:
        """Extract entities from text (simplified implementation)"""
        # This is a simplified implementation
        # In a full system, use NLP libraries like spaCy or transformers
        entities: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Simple keyword-based entity extraction
        keywords = {
            "Python": EntityType.TOOL,
            "FastAPI": EntityType.TOOL,
            "Redis": EntityType.TOOL,
            "PostgreSQL": EntityType.TOOL,
            "machine learning": EntityType.CONCEPT,
            "artificial intelligence": EntityType.CONCEPT,
            "knowledge management": EntityType.CONCEPT,
        }

        text_lower = text.lower()
        for keyword, entity_type in keywords.items():
            if keyword.lower() in text_lower:
                entity_id = f"entity_{keyword.replace(' ', '_').lower()}"
                entity = Entity(
                    entity_id=entity_id,
                    name=keyword,
                    entity_type=entity_type,
                    confidence=0.8,
                )
                entities.append(entity)

        return entities

    async def _extract_relationships_from_text(
        self, text: str, entry_id: str
    ) -> list[Relationship]:
        """Extract relationships from text (simplified implementation)"""
        # This is a simplified implementation
        # In a full system, use dependency parsing and relation extraction models
        relationships: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Simple pattern-based relationship extraction
        # This would be much more sophisticated in a real implementation

        return relationships

    def _calculate_average_connections(self) -> float:
        """Calculate average number of connections per entity"""
        if not self.adjacency_list:
            return 0.0

        total_connections = sum(len(connections) for connections in self.adjacency_list.values())
        return total_connections / len(self.adjacency_list)

    async def _get_most_connected_entities(self, limit: int = 5) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get entities with the most connections"""
        try:
            entity_connections: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for entity_id, connections in self.adjacency_list.items():
                if entity_id in self.entities:
                    entity = self.entities[entity_id]
                    entity_connections.append(
                        {
                            "entity_id": entity_id,
                            "name": entity.name,
                            "entity_type": entity.entity_type.value,
                            "connections": len(connections),
                        }
                    )

            # Sort by number of connections
            entity_connections.sort(key=lambda x: x["connections"], reverse=True)
            return entity_connections[:limit]

        except Exception as e:
            logger.error(f"Failed to get most connected entities: {e}")
            return []

    async def export_graph(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Export graph data for backup"""
        try:
            return {
                "entities": [entity.to_dict() for entity in self.entities.values()],
                "relationships": [
                    relationship.to_dict() for relationship in self.relationships.values()
                ],
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to export graph: {e}")
            return {}

    async def import_graph(self, graph_data: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Import graph data from backup"""
        try:
            # Import entities
            for entity_data in graph_data.get("entities", []):
                entity = Entity.from_dict(entity_data)
                await self.add_entity(entity)

            # Import relationships
            for relationship_data in graph_data.get("relationships", []):
                relationship = Relationship.from_dict(relationship_data)
                await self.add_relationship(relationship)

            logger.info("Graph data imported successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to import graph: {e}")
            return False
