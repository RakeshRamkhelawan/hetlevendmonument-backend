"""
Text Processor - Advanced text processing and transformation system
ASCII-only compliance enforced
"""

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Union, cast
from collections.abc import Callable

logger = logging.getLogger(__name__)


class TextTransformation(Enum):
    """Text transformation types."""

    NORMALIZE = "normalize"
    CLEAN = "clean"
    FORMAT = "format"
    EXTRACT = "extract"
    REPLACE = "replace"
    ANALYZE = "analyze"
    SUMMARIZE = "summarize"
    ENHANCE = "enhance"


@dataclass
class ProcessingRule:
    """Rule for text processing operations."""

    name: str
    pattern: str
    replacement: str | Callable[..., Any]  # TODO(TYPE): replace Any with concrete type
    transformation: TextTransformation
    flags: int = 0
    priority: int = 0
    enabled: bool = True
    description: str = ""


@dataclass
class TextAnalytics:
    """Text analytics and metrics."""

    character_count: int
    word_count: int
    sentence_count: int
    paragraph_count: int
    readability_score: float
    complexity_score: float
    ascii_compliance: bool
    detected_language: str = "unknown"
    sentiment_score: float = 0.0
    keywords: list[str] = field(default_factory=list)


@dataclass
class ProcessingResult:
    """Result of text processing operation."""

    processed_text: str
    original_text: str
    transformations_applied: list[str]
    analytics: TextAnalytics
    processing_time: float
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class TextProcessor:
    """
    Advanced text processing system for M-MDP architecture.
    Handles text normalization, cleaning, formatting, and analysis.
    """

    def __init__(self, cache_layer: Any | None = None) -> None:  # TODO(TYPE): replace Any with concrete type
        """Initialize the text processor."""
        self.cache_layer = cache_layer
        self.processing_rules: dict[TextTransformation, list[ProcessingRule]] = {}
        self.custom_processors: dict[str, Callable[..., Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.stats: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "texts_processed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "transformation_counts": {},
            "average_processing_time": 0.0,
            "average_word_count": 0.0,
        }

        # Initialize default processing rules
        self._initialize_default_rules()

        logger.info("TextProcessor initialized with comprehensive rule set")

    def _initialize_default_rules(self) -> None:
        """Initialize default text processing rules."""

        # Normalization rules
        self.processing_rules[TextTransformation.NORMALIZE] = [
            ProcessingRule(
                name="unicode_normalization",
                pattern="",
                replacement="",
                transformation=TextTransformation.NORMALIZE,
                priority=1,
                description="Normalize Unicode characters",
            ),
            ProcessingRule(
                name="whitespace_normalization",
                pattern=r"\s+",
                replacement=" ",
                transformation=TextTransformation.NORMALIZE,
                priority=2,
                description="Normalize whitespace characters",
            ),
            ProcessingRule(
                name="line_ending_normalization",
                pattern=r"\r\n|\r|\n",
                replacement="\n",
                transformation=TextTransformation.NORMALIZE,
                priority=3,
                description="Normalize line endings",
            ),
        ]

        # Cleaning rules
        self.processing_rules[TextTransformation.CLEAN] = [
            ProcessingRule(
                name="remove_html_tags",
                pattern=r"<[^>]+>",
                replacement="",
                transformation=TextTransformation.CLEAN,
                priority=1,
                description="Remove HTML tags",
            ),
            ProcessingRule(
                name="remove_urls",
                pattern=r"https?://\S+|www\.\S+",
                replacement="[URL]",
                transformation=TextTransformation.CLEAN,
                priority=2,
                description="Replace URLs with placeholder",
            ),
            ProcessingRule(
                name="remove_email_addresses",
                pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
                replacement="[EMAIL]",
                transformation=TextTransformation.CLEAN,
                priority=3,
                description="Replace email addresses with placeholder",
            ),
            ProcessingRule(
                name="remove_extra_punctuation",
                pattern=r"[.]{3,}",
                replacement="...",
                transformation=TextTransformation.CLEAN,
                priority=4,
                description="Normalize excessive punctuation",
            ),
            ProcessingRule(
                name="remove_non_ascii",
                pattern=r"[^\x00-\x7F]+",
                replacement="",
                transformation=TextTransformation.CLEAN,
                priority=5,
                description="Remove non-ASCII characters",
            ),
        ]

        # Formatting rules
        self.processing_rules[TextTransformation.FORMAT] = [
            ProcessingRule(
                name="sentence_spacing",
                pattern=r"\.(\S)",
                replacement=r". \1",
                transformation=TextTransformation.FORMAT,
                priority=1,
                description="Add proper spacing after sentences",
            ),
            ProcessingRule(
                name="capitalize_sentences",
                pattern=r"(^|[.!?]\s+)([a-z])",
                replacement=lambda m: m.group(1) + m.group(2).upper(),
                transformation=TextTransformation.FORMAT,
                priority=2,
                description="Capitalize sentence beginnings",
            ),
            ProcessingRule(
                name="trim_whitespace",
                pattern=r"^\s+|\s+$",
                replacement="",
                transformation=TextTransformation.FORMAT,
                priority=3,
                description="Trim leading and trailing whitespace",
            ),
        ]

        # Extraction rules
        self.processing_rules[TextTransformation.EXTRACT] = [
            ProcessingRule(
                name="extract_numbers",
                pattern=r"\b\d+\.?\d*\b",
                replacement="",
                transformation=TextTransformation.EXTRACT,
                priority=1,
                description="Extract numeric values",
            ),
            ProcessingRule(
                name="extract_dates",
                pattern=r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
                replacement="",
                transformation=TextTransformation.EXTRACT,
                priority=2,
                description="Extract date patterns",
            ),
            ProcessingRule(
                name="extract_phone_numbers",
                pattern=r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
                replacement="",
                transformation=TextTransformation.EXTRACT,
                priority=3,
                description="Extract phone number patterns",
            ),
        ]

    def process_text(
        self,
        text: str,
        transformations: list[TextTransformation],
        custom_rules: list[ProcessingRule] | None = None,
    ) -> ProcessingResult:
        """
        Process text using specified transformations.

        Args:
            text: Input text to process
            transformations: list[Any] of transformations to apply  # TODO(TYPE): replace Any with concrete type
            custom_rules: Additional custom processing rules

        Returns:
            ProcessingResult with processed text and analytics
        """
        start_time = datetime.now(timezone.utc)
        original_text = text

        try:
            # Check cache first
            cache_key = self._generate_cache_key(text, transformations, custom_rules)
            if self.cache_layer:
                cached_result = self.cache_layer.get(f"text_proc_{cache_key}")
                if cached_result:
                    self.stats["cache_hits"] += 1
                    logger.debug(f"Cache hit for text processing: {cache_key}")
                    return cast(ProcessingResult, cached_result)

                self.stats["cache_misses"] += 1

            processed_text = text
            applied_transformations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            # Apply each transformation in order
            for transformation in transformations:
                if transformation in self.processing_rules:
                    processed_text, transformation_names = self._apply_transformation(
                        processed_text, transformation, custom_rules
                    )
                    applied_transformations.extend(transformation_names)

            # Analyze processed text
            analytics = self._analyze_text(processed_text)

            # Calculate processing time
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Create result
            result = ProcessingResult(
                processed_text=processed_text,
                original_text=original_text,
                transformations_applied=applied_transformations,
                analytics=analytics,
                processing_time=processing_time,
                metadata={
                    "transformations_count": len(applied_transformations),
                    "text_reduction_ratio": (
                        len(processed_text) / len(original_text) if original_text else 0
                    ),
                },
            )

            # Check for warnings
            warnings = self._check_processing_warnings(original_text, processed_text, analytics)
            result.warnings = warnings

            # Cache result
            if self.cache_layer:
                self.cache_layer.set(f"text_proc_{cache_key}", result, ttl=3600)

            # Update statistics
            self._update_stats(processing_time, analytics.word_count, applied_transformations)

            logger.debug(
                f"Processed text with {len(applied_transformations)} transformations in {processing_time:.3f}s"
            )
            return result

        except Exception as e:
            error_msg = f"Text processing error: {str(e)}"
            logger.error(error_msg)

            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            return ProcessingResult(
                processed_text=original_text,
                original_text=original_text,
                transformations_applied=[],
                analytics=self._analyze_text(original_text),
                processing_time=processing_time,
                warnings=[error_msg],
            )

    def _apply_transformation(
        self,
        text: str,
        transformation: TextTransformation,
        custom_rules: list[ProcessingRule] | None = None,
    ) -> tuple[str, list[str]]:
        """Apply a specific transformation to text."""
        processed_text = text
        applied_rules: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Get rules for this transformation
        rules = self.processing_rules.get(transformation, [])

        # Add custom rules if provided
        if custom_rules:
            rules.extend([rule for rule in custom_rules if rule.transformation == transformation])

        # Sort rules by priority
        rules = sorted([rule for rule in rules if rule.enabled], key=lambda r: r.priority)

        # Apply each rule
        for rule in rules:
            try:
                if (
                    transformation == TextTransformation.NORMALIZE
                    and rule.name == "unicode_normalization"
                ):
                    processed_text = self._normalize_unicode(processed_text)
                elif transformation == TextTransformation.EXTRACT:
                    extracted_items = self._extract_pattern(processed_text, rule.pattern)
                    if extracted_items:
                        applied_rules.append(f"{rule.name}: {len(extracted_items)} items")
                elif callable(rule.replacement):
                    processed_text = re.sub(
                        rule.pattern, rule.replacement, processed_text, flags=rule.flags
                    )
                else:
                    old_text = processed_text
                    processed_text = re.sub(
                        rule.pattern, rule.replacement, processed_text, flags=rule.flags
                    )
                    if old_text != processed_text:
                        applied_rules.append(rule.name)

            except Exception as e:
                logger.warning(f"Rule '{rule.name}' failed: {e}")

        return processed_text, applied_rules

    def _normalize_unicode(self, text: str) -> str:
        """Normalize Unicode characters to ASCII-compatible form."""
        # Normalize Unicode to decomposed form
        normalized = unicodedata.normalize("NFD", text)

        # Remove combining characters (accents, etc.)
        ascii_text = "".join(char for char in normalized if unicodedata.category(char) != "Mn")

        # Replace common Unicode quotes and dashes
        replacements = {
            "\u2018": "'",  # Left single quotation mark
            "\u2019": "'",  # Right single quotation mark
            "\u201c": '"',  # Left double quotation mark
            "\u201d": '"',  # Right double quotation mark
            "\u2013": "-",  # En dash
            "\u2014": "--",  # Em dash
            "\u2026": "...",  # Horizontal ellipsis
        }

        for unicode_char, ascii_replacement in replacements.items():
            ascii_text = ascii_text.replace(unicode_char, ascii_replacement)

        return ascii_text

    def _extract_pattern(self, text: str, pattern: str) -> list[str]:
        """Extract items matching a pattern from text."""
        try:
            matches = re.findall(pattern, text)
            return matches
        except Exception as e:
            logger.warning(f"Pattern extraction failed: {e}")
            return []

    def _analyze_text(self, text: str) -> TextAnalytics:
        """Analyze text and generate metrics."""
        # Basic counts
        character_count = len(text)
        words = text.split()
        word_count = len(words)

        # Sentence count (approximate)
        sentence_endings = r"[.!?]+(?:\s|$)"
        sentences = re.split(sentence_endings, text)
        sentence_count = len([s for s in sentences if s.strip()])

        # Paragraph count
        paragraphs = text.split("\n\n")
        paragraph_count = len([p for p in paragraphs if p.strip()])

        # ASCII compliance check
        ascii_compliance = all(ord(char) < 128 for char in text)

        # Readability score (simplified Flesch formula)
        if sentence_count > 0 and word_count > 0:
            avg_sentence_length = word_count / sentence_count
            # Simplified syllable count (approximate)
            syllable_count = sum(self._count_syllables(word) for word in words)
            avg_syllables_per_word = syllable_count / word_count if word_count > 0 else 0

            readability_score = (
                206.835 - (1.015 * avg_sentence_length) - (84.6 * avg_syllables_per_word)
            )
            readability_score = max(0, min(100, readability_score))  # Clamp between 0-100
        else:
            readability_score = 0.0

        # Complexity score (based on word length and sentence structure)
        if word_count > 0:
            avg_word_length = sum(len(word) for word in words) / word_count
            long_words = sum(1 for word in words if len(word) > 6)
            complexity_score = (avg_word_length * 10) + (long_words / word_count * 50)
            complexity_score = min(100, complexity_score)  # Cap at 100
        else:
            complexity_score = 0.0

        # Extract keywords (simple frequency-based)
        keywords = self._extract_keywords(words)

        # Basic language detection (very simplified)
        detected_language = self._detect_language(text)

        return TextAnalytics(
            character_count=character_count,
            word_count=word_count,
            sentence_count=sentence_count,
            paragraph_count=paragraph_count,
            readability_score=readability_score,
            complexity_score=complexity_score,
            ascii_compliance=ascii_compliance,
            detected_language=detected_language,
            keywords=keywords,
        )

    def _count_syllables(self, word: str) -> int:
        """Count syllables in a word (simplified algorithm)."""
        word = word.lower()
        vowels = "aeiouy"
        syllable_count = 0
        previous_was_vowel = False

        for char in word:
            is_vowel = char in vowels
            if is_vowel and not previous_was_vowel:
                syllable_count += 1
            previous_was_vowel = is_vowel

        # Handle silent 'e'
        if word.endswith("e") and syllable_count > 1:
            syllable_count -= 1

        return max(1, syllable_count)  # Every word has at least one syllable

    def _extract_keywords(self, words: list[str], max_keywords: int = 10) -> list[str]:
        """Extract keywords from text based on frequency."""
        # Filter out short words and common stop words
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "can",
            "may",
            "might",
            "must",
            "this",
            "that",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "me",
            "him",
            "her",
            "us",
            "them",
            "my",
            "your",
            "his",
            "hers",
            "its",
            "our",
            "their",
        }

        # Count word frequencies
        word_freq: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for word in words:
            clean_word = re.sub(r"[^\w]", "", word.lower())
            if len(clean_word) > 3 and clean_word not in stop_words:
                word_freq[clean_word] = word_freq.get(clean_word, 0) + 1

        # Sort by frequency and return top keywords
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        return [word for word, freq in sorted_words[:max_keywords]]

    def _detect_language(self, text: str) -> str:
        """Detect language of text (very simplified)."""
        # This is a very basic implementation
        # In practice, you would use a proper language detection library

        if not text.strip():
            return "unknown"

        # Check for common English patterns
        english_indicators = [
            "the",
            "and",
            "that",
            "have",
            "for",
            "not",
            "with",
            "you",
            "this",
            "but",
        ]
        text_lower = text.lower()
        english_score = sum(1 for indicator in english_indicators if indicator in text_lower)

        if english_score >= 3:
            return "english"

        return "unknown"

    def _check_processing_warnings(
        self, original: str, processed: str, analytics: TextAnalytics
    ) -> list[str]:
        """Check for potential processing issues and generate warnings."""
        warnings: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check for significant text reduction
        reduction_ratio = len(processed) / len(original) if original else 1
        if reduction_ratio < 0.5:
            warnings.append("Significant text reduction detected (>50%)")

        # Check ASCII compliance
        if not analytics.ascii_compliance:
            warnings.append("Text contains non-ASCII characters")

        # Check readability
        if analytics.readability_score < 30:
            warnings.append("Text may be difficult to read (low readability score)")

        # Check for very short or very long text
        if analytics.word_count < 5:
            warnings.append("Text is very short (fewer than 5 words)")
        elif analytics.word_count > 10000:
            warnings.append("Text is very long (more than 10,000 words)")

        return warnings

    def _generate_cache_key(
        self,
        text: str,
        transformations: list[TextTransformation],
        custom_rules: list[ProcessingRule] | None,
    ) -> str:
        """Generate cache key for text processing operation."""
        key_data = {
            "text_hash": hashlib.md5(
                text.encode("utf-8", errors="ignore"), usedforsecurity=False
            ).hexdigest(),
            "transformations": [t.value for t in transformations],
            "custom_rules": len(custom_rules) if custom_rules else 0,
        }

        key_string = str(key_data)
        return hashlib.md5(key_string.encode("ascii"), usedforsecurity=False).hexdigest()

    def _update_stats(
        self, processing_time: float, word_count: int, transformations: list[str]
    ) -> None:
        """Update text processing statistics."""
        self.stats["texts_processed"] += 1

        # Update average processing time
        current_avg_time = self.stats["average_processing_time"]
        count = self.stats["texts_processed"]
        self.stats["average_processing_time"] = (
            (current_avg_time * (count - 1)) + processing_time
        ) / count

        # Update average word count
        current_avg_words = self.stats["average_word_count"]
        self.stats["average_word_count"] = ((current_avg_words * (count - 1)) + word_count) / count

        # Update transformation counts
        for transformation in transformations:
            if transformation not in self.stats["transformation_counts"]:
                self.stats["transformation_counts"][transformation] = 0
            self.stats["transformation_counts"][transformation] += 1

    def add_processing_rule(self, rule: ProcessingRule) -> None:
        """Add a custom processing rule."""
        if rule.transformation not in self.processing_rules:
            self.processing_rules[rule.transformation] = []

        self.processing_rules[rule.transformation].append(rule)
        logger.info(f"Added processing rule: {rule.name}")

    def remove_processing_rule(self, transformation: TextTransformation, rule_name: str) -> None:
        """Remove a processing rule."""
        if transformation in self.processing_rules:
            self.processing_rules[transformation] = [
                rule for rule in self.processing_rules[transformation] if rule.name != rule_name
            ]
            logger.info(f"Removed processing rule: {rule_name}")

    def register_custom_processor(self, name: str, processor_func: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register a custom text processing function."""
        self.custom_processors[name] = processor_func
        logger.info(f"Registered custom processor: {name}")

    def get_available_transformations(self) -> list[TextTransformation]:
        """Get list of available transformations."""
        return list(TextTransformation)

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get text processing statistics."""
        return self.stats.copy()

    def reset_stats(self) -> None:
        """Reset text processing statistics."""
        self.stats = {
            "texts_processed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "transformation_counts": {},
            "average_processing_time": 0.0,
            "average_word_count": 0.0,
        }
        logger.info("Text processing statistics reset")


def create_text_processor(cache_layer: Any | None = None) -> TextProcessor:  # TODO(TYPE): replace Any with concrete type
    """Factory function to create a TextProcessor instance."""
    return TextProcessor(cache_layer=cache_layer)
