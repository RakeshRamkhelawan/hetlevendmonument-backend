"""Type definitions for Memory Management."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

# Lazy imports
_numpy: Any = None


def _get_numpy() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Lazy-load numpy library"""
    global _numpy
    if _numpy is None:
        import numpy as np_lib

        _numpy = np_lib
    return _numpy


@dataclass
class MemoryEntry:
    """Base memory entry structure with optional embedding encryption.

    P2 FIX: Embeddings can be encrypted to prevent data exposure in FAISS indices.
    """

    id: str
    timestamp: datetime
    agent_type: Any  # AgentType  # TODO(TYPE): replace Any with concrete type
    content: str
    embedding: Any | None = None  # numpy.ndarray when ML features enabled  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    _is_embedding_encrypted: bool = False

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for JSON storage"""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        if self.embedding is not None:
            if self._is_embedding_encrypted:
                data["embedding"] = self.embedding
            elif hasattr(self.embedding, "tolist"):
                data["embedding"] = self.embedding.tolist()
            else:
                try:
                    data["embedding"] = list(self.embedding)
                except TypeError:
                    data["embedding"] = self.embedding
        # Remove internal flag from serialization
        data.pop("_is_embedding_encrypted", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":  # TODO(TYPE): replace Any with concrete type
        """Create from dictionary"""
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        if isinstance(data.get("embedding"), (list, tuple)):
            data["embedding"] = _get_numpy().array(data["embedding"])
        return cls(**data)

    def encrypt_embedding(self, encryption_service: Any) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Encrypt the embedding using the provided encryption service.

        P2 FIX: Encrypt embeddings before storage to prevent data exposure.

        Args:
            encryption_service: EncryptionService instance

        Returns:
            True if encryption was successful, False otherwise
        """
        if self.embedding is None or self._is_embedding_encrypted:
            return False

        encrypted = encryption_service.encrypt_embedding(self.embedding)
        if encrypted:
            self.embedding = encrypted
            self._is_embedding_encrypted = True
            return True
        return False

    def decrypt_embedding(self, encryption_service: Any) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Decrypt the embedding using the provided encryption service.

        P2 FIX: Decrypt embeddings after retrieval from storage.

        Args:
            encryption_service: EncryptionService instance

        Returns:
            True if decryption was successful, False otherwise
        """
        if self.embedding is None or not self._is_embedding_encrypted:
            return False

        decrypted = encryption_service.decrypt_embedding(self.embedding)
        if decrypted is not None:
            self.embedding = decrypted
            self._is_embedding_encrypted = False
            return True
        return False


@dataclass
class StrategicMemory(MemoryEntry):
    """CVA strategic memory for delegation patterns"""

    context_similarity: float = 0.0
    orchestration_pattern: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    strategy_type: str = ""
    success_rate: float = 0.0


@dataclass
class TacticalMemory(MemoryEntry):
    """Orchestrator tactical memory for operation patterns"""

    task_type: str = ""
    agent_assignments: list[str] = field(default_factory=list)
    execution_time: float = 0.0
    resource_efficiency: float = 0.0

    def __post_init__(self) -> None:
        if self.agent_assignments is None:
            self.agent_assignments = []


@dataclass
class EpisodicMemory(MemoryEntry):
    """SubAgent episodic memory for task execution history"""

    error_patterns: list[str] | None = None
    task_id: str = ""
    execution_steps: list[dict[str, Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    success: bool = False

    def __post_init__(self) -> None:
        if self.error_patterns is None:
            self.error_patterns = []
        if self.execution_steps is None:
            self.execution_steps = []
