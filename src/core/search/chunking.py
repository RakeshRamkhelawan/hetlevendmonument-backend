"""
Smart Document Chunking Pipeline

Provides:
- Multiple chunking strategies (fixed, semantic, code, markdown)
- Automatic document type detection
- Chunk deduplication
- Metadata enrichment
"""

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class Chunk:
    """A document chunk."""

    text: str
    start_offset: int
    end_offset: int
    chunk_index: int
    total_chunks: int
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    doc_id: str | None = None
    hash: str | None = None

    def __post_init__(self) -> None:
        if self.hash is None:
            self.hash = hashlib.sha256(self.text.encode()).hexdigest()[:16]


class ChunkingStrategy(ABC):
    """Base class for chunking strategies."""

    @abstractmethod
    def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[Chunk]:  # TODO(TYPE): replace Any with concrete type
        """Chunk text into pieces."""
        pass


class FixedSizeChunker(ChunkingStrategy):
    """Fixed-size chunker with overlap."""

    def __init__(self, chunk_size: int = 512, overlap: int = 64) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[Chunk]:  # TODO(TYPE): replace Any with concrete type
        """Create fixed-size chunks with overlap."""
        chunks: list[Chunk] = []
        step = self.chunk_size - self.overlap

        # Simple word-based chunking (approximate)
        words = text.split()
        total_words = len(words)

        for i in range(0, total_words, step):
            chunk_words = words[i : i + self.chunk_size]
            chunk_text = " ".join(chunk_words)

            start_offset = len(" ".join(words[:i])) if i > 0 else 0
            end_offset = start_offset + len(chunk_text)

            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    chunk_index=len(chunks),
                    total_chunks=0,  # Set later
                    metadata=metadata or {},
                )
            )

        # Update total_chunks
        for chunk in chunks:
            chunk.total_chunks = len(chunks)

        return chunks


class SemanticChunker(ChunkingStrategy):
    """Semantic chunker that splits on natural boundaries."""

    def __init__(self, max_chunk_size: int = 512) -> None:
        self.max_chunk_size = max_chunk_size

    def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[Chunk]:  # TODO(TYPE): replace Any with concrete type
        """Split on paragraphs and sections."""
        # Split on double newlines (paragraphs)
        paragraphs = re.split(r"\n\s*\n", text)

        chunks: list[Chunk] = []
        current_chunk: list[str] = []
        current_size: int = 0

        for para in paragraphs:
            para_words = para.split()
            para_size = len(para_words)

            if current_size + para_size > self.max_chunk_size and current_chunk:
                # Flush current chunk
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(self._create_chunk(chunk_text, len(chunks), metadata))
                current_chunk = []
                current_size = 0

            current_chunk.append(para)
            current_size += para_size

        # Flush remaining
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append(self._create_chunk(chunk_text, len(chunks), metadata))

        # Update total_chunks
        for chunk in chunks:
            chunk.total_chunks = len(chunks)

        return chunks

    def _create_chunk(self, text: str, index: int, metadata: dict[str, Any] | None) -> Chunk:  # TODO(TYPE): replace Any with concrete type
        return Chunk(
            text=text,
            start_offset=0,  # Would need proper tracking
            end_offset=len(text),
            chunk_index=index,
            total_chunks=0,
            metadata=metadata or {},
        )


class CodeChunker(ChunkingStrategy):
    """Code-aware chunker that splits on functions/classes."""

    def __init__(self, language: str | None = None) -> None:
        self.language = language

    def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[Chunk]:  # TODO(TYPE): replace Any with concrete type
        """Split code on function/class boundaries."""
        # Python-style function/class patterns
        patterns = [
            r"(def\s+\w+\s*\([^)]*\):.*?)(?=\ndef\s+|\nclass\s+|\Z)",
            r"(class\s+\w+[^:]*:.*?)(?=\nclass\s+|\ndef\s+|\Z)",
        ]

        chunks: list[Chunk] = []
        seen: set[str] = set()

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.DOTALL):
                chunk_text = match.group(1).strip()
                if chunk_text and chunk_text not in seen:
                    seen.add(chunk_text)
                    chunks.append(
                        Chunk(
                            text=chunk_text,
                            start_offset=match.start(),
                            end_offset=match.end(),
                            chunk_index=len(chunks),
                            total_chunks=0,
                            metadata={**(metadata or {}), "type": "code_block"},
                        )
                    )

        # If no function/class found, fall back to fixed size
        if not chunks:
            return FixedSizeChunker(chunk_size=512).chunk(text, metadata)

        for chunk in chunks:
            chunk.total_chunks = len(chunks)

        return chunks


class MarkdownChunker(ChunkingStrategy):
    """Markdown-aware chunker that splits on headers."""

    def __init__(self) -> None:
        self.header_pattern = re.compile(r"^(#{1,6}\s+.+)$", re.MULTILINE)

    def chunk(self, text: str, metadata: dict[str, Any] | None = None) -> list[Chunk]:  # TODO(TYPE): replace Any with concrete type
        """Split markdown on headers."""
        # Find all headers
        headers = list(self.header_pattern.finditer(text))

        if not headers:
            # No headers, use semantic chunking
            return SemanticChunker().chunk(text, metadata)

        chunks: list[Chunk] = []

        # First chunk: before first header or everything up to first header
        if headers[0].start() > 0:
            intro_text = text[: headers[0].start()].strip()
            if intro_text:
                chunks.append(
                    Chunk(
                        text=intro_text,
                        start_offset=0,
                        end_offset=headers[0].start(),
                        chunk_index=len(chunks),
                        total_chunks=0,
                        metadata={**(metadata or {}), "section": "intro"},
                    )
                )

        # Chunks per header section
        for i, header_match in enumerate(headers):
            start = header_match.start()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(text)

            section_text = text[start:end].strip()
            header_text = header_match.group(1)

            if section_text:
                chunks.append(
                    Chunk(
                        text=section_text,
                        start_offset=start,
                        end_offset=end,
                        chunk_index=len(chunks),
                        total_chunks=0,
                        metadata={
                            **(metadata or {}),
                            "section": header_text,
                            "header_level": header_text.count("#"),
                        },
                    )
                )

        for chunk in chunks:
            chunk.total_chunks = len(chunks)

        return chunks


class HybridChunker(ChunkingStrategy):
    """Auto-detects document type and routes to appropriate chunker."""

    def __init__(self) -> None:
        self.chunkers = {
            "code": CodeChunker(),
            "markdown": MarkdownChunker(),
            "text": SemanticChunker(),
        }

    def detect_type(self, text: str, filename: str | None = None) -> str:
        """Detect document type."""
        if filename:
            ext = filename.split(".")[-1].lower() if "." in filename else ""
            if ext in ["py", "js", "ts", "java", "cpp", "c", "go", "rs", "rb"]:
                return "code"
            if ext in ["md", "markdown", "mdx"]:
                return "markdown"

        # Content-based detection
        if re.search(r"^\s*(def|class|function|import|from)\s+", text, re.MULTILINE):
            return "code"

        if re.search(r"^#{1,6}\s+", text, re.MULTILINE):
            return "markdown"

        return "text"

    def chunk(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        doc_type: str | None = None,
        filename: str | None = None,
    ) -> list[Chunk]:
        """Chunk with auto-detected strategy."""
        if doc_type is None:
            doc_type = self.detect_type(text, filename)

        chunker = self.chunkers.get(doc_type, self.chunkers["text"])

        # Add doc_type to metadata
        meta = {**(metadata or {}), "doc_type": doc_type}

        return chunker.chunk(text, meta)


class ChunkingPipeline:
    """Pipeline for processing documents into chunks."""

    def __init__(self, chunker: ChunkingStrategy | None = None) -> None:
        self.chunker = chunker or HybridChunker()
        self._dedup_cache: dict[str, Chunk] = {}

    async def process_document(
        self,
        doc_id: str,
        content: str,
        doc_type: str | None = None,
        filename: str | None = None,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> list[Chunk]:
        """
        Process a document into chunks.

        Args:
            doc_id: Document ID
            content: Document content
            doc_type: Document type (auto-detected if None)
            filename: Original filename
            metadata: Additional metadata

        Returns: List[Any] of chunks (deduplicated)  # TODO(TYPE): replace Any with concrete type
        """
        # Prepare metadata
        meta = {
            "doc_id": doc_id,
            "filename": filename,
            **(metadata or {}),
        }

        # Chunk
        if isinstance(self.chunker, HybridChunker):
            chunks = self.chunker.chunk(content, meta, doc_type, filename)
        else:
            chunks = self.chunker.chunk(content, meta)

        # Set doc_id on all chunks
        for chunk in chunks:
            chunk.doc_id = doc_id

        # Deduplicate
        unique_chunks = self._deduplicate(chunks)

        return unique_chunks

    def _deduplicate(self, chunks: list[Chunk]) -> list[Chunk]:
        """Remove duplicate chunks based on hash."""
        unique: list[Chunk] = []
        seen_hashes: set[str] = set()

        for chunk in chunks:
            if chunk.hash is not None and chunk.hash not in seen_hashes:
                seen_hashes.add(chunk.hash)
                unique.append(chunk)

        return unique
