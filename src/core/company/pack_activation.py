"""Pack Activation Scorer - Golden Rule R2 Implementation.

This module implements the PackActivationScorer which automatically scores
and activates domain packs based on department signals.

Golden Rule R2: No pack activation without explainable match.
Every activation MUST have:
- match_reason (human-readable explanation)
- confidence level (EXACT, HIGH, MEDIUM, LOW, NONE)
- score_breakdown (how the score was calculated)
- audit_log_id (reference to audit trail)
"""

import logging
import uuid
from difflib import SequenceMatcher
from typing import Any, cast

from pydantic import BaseModel, Field

from src.core.monitoring.pack_metrics import record_alignment_score, record_selector_request
from src.core.observability.tracing import HAS_OPENTELEMETRY

try:
    from src.core.config import settings
except ImportError:
    settings = None  # type: ignore[assignment]


def _get_ml_prediction_service() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Lazy import of ML prediction service to avoid heavy sklearn load."""
    try:
        from src.ml.prediction_service import ml_prediction_service

        return ml_prediction_service
    except ImportError:
        return None


logger = logging.getLogger(__name__)

# Dutch stopwords for tokenization
DUTCH_STOPWORDS = {
    "de",
    "het",
    "een",
    "van",
    "in",
    "op",
    "te",
    "en",
    "voor",
    "met",
    "aan",
    "door",
    "over",
    "naar",
    "uit",
    "bij",
    "om",
    "zoals",
    "tussen",
    "tijdens",
    "na",
    "zonder",
    "onder",
    "boven",
    "tussen",
    "achter",
    "voor",
    "binnen",
    "buiten",
}

ENGLISH_STOPWORDS = {
    "the",
    "a",
    "an",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "by",
    "from",
    "as",
    "and",
    "or",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
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
}


class ActivationSignals(BaseModel):
    """Input signals for pack activation scoring."""

    department_name: str = Field(description="Name of the department")
    company_type: str = Field(description="Company type: mkb, zzp, enterprise")
    sector: str = Field(description="Business sector")
    sector_tags: list[str] = Field(default_factory=list, description="Additional sector tags")
    explicit_pack_ids: list[str] = Field(
        default_factory=list, description="Explicitly requested pack IDs"
    )
    board_role: str | None = Field(default=None, description="Board role of the department head")
    domain_pack_ids: list[str] = Field(
        default_factory=list, description="Domain-specific pack IDs for the department"
    )


class PackScore(BaseModel):
    """Score result for a single pack."""

    pack_id: str = Field(description="Unique pack identifier")
    pack_name: str = Field(description="Human-readable pack name")
    score: float = Field(ge=0.0, le=1.0, description="Overall match score (0.0-1.0)")
    confidence: str = Field(description="EXACT, HIGH, MEDIUM, LOW, or NONE")
    reasons: list[str] = Field(default_factory=list, description="Human-readable match reasons")
    input_signals: list[str] = Field(default_factory=list, description="Which signals matched")
    activated_automatically: bool = Field(
        default=False, description="True if score >= 0.70 (auto-activation threshold)"
    )
    # ML-enhanced fields
    ml_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="ML prediction score (0.0-1.0)"
    )
    heuristic_score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Heuristic score before blending (0.0-1.0)",
    )
    score_source: str = Field(
        default="heuristic",
        description="Source of score: heuristic, ml_blend, or ml_only",
    )
    # Golden Rule R2 fields -- required by pack_selector_router
    match_reason: str = Field(
        default="", description="Human-readable explanation of match (Golden Rule R2)"
    )
    score_breakdown: dict[str, float] = Field(
        default_factory=dict, description="Detailed score breakdown per signal"
    )
    audit_log_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Reference to audit log entry (Golden Rule R2)",
    )


class PackActivationResult(BaseModel):
    """Result of a pack activation with audit trail reference."""

    pack_id: str = Field(description="Unique pack identifier")
    pack_name: str = Field(description="Human-readable pack name")
    confidence: float = Field(ge=0.0, le=1.0, description="Numeric confidence score")
    match_reason: str = Field(description="Human-readable explanation (Golden Rule R2)")
    input_signals: list[str] = Field(description="Input signals that contributed")
    score_breakdown: dict[str, float] = Field(description="Detailed score breakdown")
    audit_log_id: uuid.UUID = Field(description="Reference to audit log entry (Golden Rule R2)")
    activated_automatically: bool = Field(description="Whether pack was auto-activated")
    user_confirmed: bool | None = Field(
        default=None, description="None for auto, True/False for manual confirmation"
    )


class PackActivationScorer:
    """Scores domain packs against department signals for activation.

    Implements Golden Rule R2: Every activation must have an explainable match
    with confidence level and audit trail reference.

    Scoring weights:
    - Department match: 0.40 (exact) or up to 0.40 (fuzzy)
    - Company type match: 0.20
    - Sector match: 0.20
    - Explicit request: 0.20

    ML Integration:
    - Uses ML predictions when available and enabled
    - Blends ML score (70%) with heuristic score (30%)
    - Falls back to heuristic-only if ML unavailable or low confidence
    """

    # Scoring weights (must sum to 1.0)
    WEIGHT_DEPARTMENT = 0.40
    WEIGHT_COMPANY_TYPE = 0.20
    WEIGHT_SECTOR = 0.20
    WEIGHT_EXPLICIT = 0.20

    # ML Blending weights
    ML_BLEND_WEIGHT = 0.70
    HEURISTIC_BLEND_WEIGHT = 0.30

    # Thresholds
    AUTO_ACTIVATE_THRESHOLD = 0.70
    SUGGESTION_THRESHOLD = 0.30
    FUZZY_MATCH_THRESHOLD = 0.70

    def __init__(self) -> None:
        """Initialize scorer with ML availability check."""
        self._ml_enabled = self._check_ml_enabled()

    def _check_ml_enabled(self) -> bool:
        """Check if ML recommendations are enabled."""
        svc = _get_ml_prediction_service()
        if svc is None:
            return False
        if settings is None:
            return False
        return getattr(settings, "ml_recommendations_enabled", False)

    def _get_ml_min_confidence(self) -> float:
        """Get minimum ML confidence threshold from settings."""
        if settings is None:
            return 0.50  # Default threshold
        return getattr(settings, "ml_min_confidence_threshold", 0.50)

    async def score_with_ml(
        self,
        pack: Any,  # TODO(TYPE): replace Any with concrete type
        signals: ActivationSignals,
        company_id: str | None = None,
        department_id: str | None = None,
    ) -> PackScore:
        """Score a single pack with ML-enhanced blending.

        Args:
            pack: DomainPack object with pack_id, name, department, intent_tags
            signals: ActivationSignals containing department info and context
            company_id: Optional company ID for ML prediction
            department_id: Optional department ID for ML prediction

        Returns:
            PackScore with ML-blended or heuristic-only score
        """
        # Calculate heuristic score first
        heuristic_score = self._calculate_heuristic_score(pack, signals)

        # Try ML prediction if enabled
        ml_score: float | None = None
        if self._ml_enabled and company_id and department_id:
            try:
                ml_score = await self._get_ml_score(pack.pack_id, company_id, department_id)
            except Exception as e:
                logger.warning(f"ML prediction failed for pack {pack.pack_id}: {e}")

        # Blend scores or use heuristic-only
        min_confidence = self._get_ml_min_confidence()
        if ml_score is not None and ml_score >= min_confidence and heuristic_score is not None:
            final_score = (
                self.ML_BLEND_WEIGHT * ml_score + self.HEURISTIC_BLEND_WEIGHT * heuristic_score
            )
            score_source = "ml_blend"
        else:
            final_score = heuristic_score
            score_source = "heuristic"

        # Determine confidence level
        confidence = self._calculate_confidence(final_score)

        # Determine auto-activation
        activated = final_score >= self.AUTO_ACTIVATE_THRESHOLD

        # Build reasons based on score source
        reasons = self._build_score_reasons(pack, signals, score_source, ml_score, heuristic_score)

        return PackScore(
            pack_id=pack.pack_id,
            pack_name=pack.name,
            score=round(final_score, 4),
            confidence=confidence,
            reasons=reasons,
            input_signals=self._get_matched_signals(pack, signals),
            activated_automatically=activated,
            ml_score=ml_score,
            heuristic_score=heuristic_score,
            score_source=score_source,
        )

    async def _get_ml_score(
        self, pack_id: str, company_id: str, department_id: str
    ) -> float | None:
        """Get ML prediction score for pack.

        Args:
            pack_id: Pack identifier
            company_id: Company identifier
            department_id: Department identifier

        Returns:
            ML prediction score (0.0-1.0) or None if unavailable
        """
        svc = _get_ml_prediction_service()
        if svc is None:
            return None

        return cast(
            float | None,
            await svc.predict(
                company_id=company_id,
                department_id=department_id,
                pack_id=pack_id,
            ),
        )

    def _calculate_heuristic_score(
        self,
        pack: Any,  # TODO(TYPE): replace Any with concrete type
        signals: ActivationSignals,  # TODO(TYPE): replace Any with concrete type
    ) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate heuristic score using original logic.

        Args:
            pack: DomainPack object
            signals: ActivationSignals

        Returns:
            Heuristic score (0.0-1.0)
        """
        scores: list[float] = []

        # 1. Department match (0.40 weight)
        dept_score = self._match_department(pack.department, signals.department_name)
        if dept_score == 1.0:
            scores.append(self.WEIGHT_DEPARTMENT)
        elif dept_score >= self.FUZZY_MATCH_THRESHOLD:
            scores.append(self.WEIGHT_DEPARTMENT * dept_score)

        # 2. Company type match (0.20 weight)
        if self._matches_company_type(pack.pack_id, signals.company_type):
            scores.append(self.WEIGHT_COMPANY_TYPE)

        # 3. Sector match via intent_tags (0.20 weight)
        sector_score = self._match_sector(pack.intent_tags, signals.sector, signals.sector_tags)
        if sector_score > 0:
            scores.append(self.WEIGHT_SECTOR * sector_score)

        # 4. Explicit pack request (0.20 weight)
        if pack.pack_id in signals.explicit_pack_ids:
            scores.append(self.WEIGHT_EXPLICIT)

        return sum(scores)

    def _build_score_reasons(
        self,
        pack: Any,  # TODO(TYPE): replace Any with concrete type
        signals: ActivationSignals,
        score_source: str,
        ml_score: float | None,
        heuristic_score: float,
    ) -> list[str]:
        """Build human-readable reasons for the score.

        Args:
            pack: DomainPack object
            signals: ActivationSignals
            score_source: Source of the score
            ml_score: ML prediction score (may be None)
            heuristic_score: Heuristic calculation score

        Returns:
            List of reason strings
        """
        reasons: list[str] = []

        # Add ML info if used
        if score_source == "ml_blend" and ml_score is not None:
            reasons.append(
                f"ML-enhanced score: {ml_score:.2f} (blended with heuristic: {heuristic_score:.2f})"
            )
        else:
            reasons.append(f"Heuristic score: {heuristic_score:.2f}")

        # Add signal matches
        dept_score = self._match_department(pack.department, signals.department_name)
        if dept_score == 1.0:
            reasons.append(f"Exact department match: {pack.department}")
        elif dept_score >= self.FUZZY_MATCH_THRESHOLD:
            reasons.append(f"Fuzzy department match: {pack.department} ~ {signals.department_name}")

        if self._matches_company_type(pack.pack_id, signals.company_type):
            reasons.append(f"Company type match: {signals.company_type}")

        sector_score = self._match_sector(pack.intent_tags, signals.sector, signals.sector_tags)
        if sector_score > 0:
            reasons.append(f"Sector match: {signals.sector}")

        if pack.pack_id in signals.explicit_pack_ids:
            reasons.append(f"Explicitly requested: {pack.pack_id}")

        if len(reasons) == 1:  # Only has score reason
            reasons.append("No additional matching signals found")

        return reasons

    def _get_matched_signals(
        self,
        pack: Any,  # TODO(TYPE): replace Any with concrete type
        signals: ActivationSignals,  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Get list of matched signal types.

        Args:
            pack: DomainPack object
            signals: ActivationSignals

        Returns:
            List of matched signal type strings
        """
        matched: list[str] = []

        dept_score = self._match_department(pack.department, signals.department_name)
        if dept_score == 1.0:
            matched.append("department")
        elif dept_score >= self.FUZZY_MATCH_THRESHOLD:
            matched.append("department_fuzzy")

        if self._matches_company_type(pack.pack_id, signals.company_type):
            matched.append("company_type")

        sector_score = self._match_sector(pack.intent_tags, signals.sector, signals.sector_tags)
        if sector_score > 0:
            matched.append("sector")

        if pack.pack_id in signals.explicit_pack_ids:
            matched.append("explicit")

        return matched

    def score(
        self,
        pack: Any,  # TODO(TYPE): replace Any with concrete type
        signals: ActivationSignals,  # TODO(TYPE): replace Any with concrete type
    ) -> PackScore:  # TODO(TYPE): replace Any with concrete type
        """Score a single pack against activation signals (heuristic-only).

        This is the synchronous version without ML. Use score_with_ml for
        ML-enhanced scoring.

        Args:
            pack: DomainPack object with pack_id, name, department, intent_tags
            signals: ActivationSignals containing department info and context

        Returns:
            PackScore with calculated score, confidence, and match reasons
        """
        # Start OpenTelemetry span for pack scoring
        if HAS_OPENTELEMETRY:
            try:
                from opentelemetry import trace

                active_tracer = trace.get_tracer(
                    instrumenting_module_name="sanskritisetu.pack_activation"
                )
                with active_tracer.start_as_current_span(
                    "PackActivationScorer.score_department"
                ) as span:
                    span.set_attribute("pack.id", pack.pack_id)
                    span.set_attribute("pack.name", pack.name)
                    span.set_attribute("department.name", signals.department_name)
                    return self._execute_score(pack, signals, span)
            except Exception:
                return self._execute_score(pack, signals, None)
        else:
            return self._execute_score(pack, signals, None)

    def _execute_score(
        self,
        pack: Any,  # TODO(TYPE): replace Any with concrete type
        signals: ActivationSignals,
        span: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> PackScore:  # TODO(TYPE): replace Any with concrete type
        """Execute the scoring logic."""
        scores: list[tuple[float, str]] = []
        reasons: list[str] = []
        matched_signals: list[str] = []
        # 1. Department match (0.40 weight)
        dept_score = self._match_department(pack.department, signals.department_name)
        if dept_score == 1.0:
            scores.append((self.WEIGHT_DEPARTMENT, "department_exact"))
            reasons.append(f"Exact department match: {pack.department}")
            matched_signals.append("department")
        elif dept_score >= self.FUZZY_MATCH_THRESHOLD:
            weighted = self.WEIGHT_DEPARTMENT * dept_score
            scores.append((weighted, "department_fuzzy"))
            reasons.append(f"Fuzzy department match: {pack.department} ~ {signals.department_name}")
            matched_signals.append("department_fuzzy")

        # 2. Company type match (0.20 weight)
        if self._matches_company_type(pack.pack_id, signals.company_type):
            scores.append((self.WEIGHT_COMPANY_TYPE, "company_type"))
            reasons.append(f"Company type match: {signals.company_type}")
            matched_signals.append("company_type")

        # 3. Sector match via intent_tags (0.20 weight)
        sector_score = self._match_sector(pack.intent_tags, signals.sector, signals.sector_tags)
        if sector_score > 0:
            weighted = self.WEIGHT_SECTOR * sector_score
            scores.append((weighted, "sector"))
            reasons.append(f"Sector match: {signals.sector}")
            matched_signals.append("sector")

        # 4. Explicit pack request (0.20 weight)
        if pack.pack_id in signals.explicit_pack_ids:
            scores.append((self.WEIGHT_EXPLICIT, "explicit"))
            reasons.append(f"Explicitly requested: {pack.pack_id}")
            matched_signals.append("explicit")

        # Calculate total score
        total_score = sum(s[0] for s in scores)

        # Determine confidence level
        confidence = self._calculate_confidence(total_score)

        # Determine auto-activation
        activated = total_score >= self.AUTO_ACTIVATE_THRESHOLD

        # Default reason if none provided
        if not reasons:
            reasons.append("No matching signals found")

        # Add span event for alignment check
        if span is not None and hasattr(span, "add_event"):
            span.add_event("alignment.check", {"alignment.score": total_score})

        return PackScore(
            pack_id=pack.pack_id,
            pack_name=pack.name,
            score=round(total_score, 4),
            confidence=confidence,
            reasons=reasons,
            input_signals=matched_signals,
            activated_automatically=activated,
            ml_score=None,
            heuristic_score=round(total_score, 4),
            score_source="heuristic",
        )

    def score_all_packs(
        self,
        packs: list[Any],  # TODO(TYPE): replace Any with concrete type
        signals: ActivationSignals,
        company_id: str | None = None,
        department_id: str | None = None,
        use_ml: bool = False,
    ) -> list[PackScore]:
        """Score all packs and return sorted results (highest first).

        Args:
            packs: List[Any] of DomainPack objects  # TODO(TYPE): replace Any with concrete type
            signals: ActivationSignals for matching
            company_id: Optional company ID for metrics
            department_id: Optional department ID for metrics
            use_ml: Whether to use ML-enhanced scoring (default: False, sync)

        Returns: List[Any] of PackScore objects, sorted by score descending,  # TODO(TYPE): replace Any with concrete type
            filtered to only include scores >= 0.30
        """
        # Record selector request start
        if company_id:
            try:
                record_selector_request(company_id=company_id, status="success")
            except Exception:
                pass  # Metrics should not break business logic

        try:
            # Use heuristic-only scoring (synchronous)
            scores = [self.score(pack, signals) for pack in packs]

            # Record alignment scores for metrics
            if department_id:
                for pack_score in scores:
                    try:
                        record_alignment_score(
                            department_id=department_id,
                            pack_id=pack_score.pack_id,
                            score=pack_score.score,
                        )
                    except Exception:
                        pass  # Metrics should not break business logic

            # Filter out low scores
            scores = [s for s in scores if s.score >= self.SUGGESTION_THRESHOLD]

            # Sort by score descending
            scores.sort(key=lambda x: x.score, reverse=True)

            # Add span event for audit log creation
            if HAS_OPENTELEMETRY:
                try:
                    from opentelemetry import trace as otel_trace

                    current_span = otel_trace.get_current_span()
                    if current_span is not None and hasattr(current_span, "add_event"):
                        current_span.add_event(
                            "audit_log.created",
                            {
                                "audit_log.entry_count": len(scores),
                                "audit_log.department": signals.department_name,
                            },
                        )
                except Exception:
                    pass  # Tracing errors should not break business logic

            return scores
        except Exception:
            # Record error status on failure
            if company_id:
                try:
                    record_selector_request(company_id=company_id, status="error")
                except Exception:
                    pass
            raise

    def _match_department(self, pack_dept: str, signal_dept: str) -> float:
        """Match department names with fuzzy matching.

        Returns:
            1.0 for exact match, 0.0-1.0 for fuzzy match, 0.0 for no match
        """
        pack_lower = pack_dept.lower().strip()
        signal_lower = signal_dept.lower().strip()

        # Exact match
        if pack_lower == signal_lower:
            return 1.0

        # Fuzzy match using SequenceMatcher
        similarity = SequenceMatcher(None, pack_lower, signal_lower).ratio()
        return similarity if similarity >= self.FUZZY_MATCH_THRESHOLD else 0.0

    def _matches_company_type(self, pack_id: str, company_type: str) -> bool:
        """Check if pack matches company type via pack_id prefix."""
        return pack_id.lower().startswith(f"{company_type.lower()}.")

    def _match_sector(self, intent_tags: list[str], sector: str, sector_tags: list[str]) -> float:
        """Match sector against intent tags.

        Returns:
            1.0 if any match, 0.0 otherwise
        """
        all_tags = [sector.lower()] + [t.lower() for t in sector_tags]
        intent_lower = [t.lower() for t in intent_tags]

        for tag in all_tags:
            if tag in intent_lower:
                return 1.0
            # Check for partial matches
            for intent in intent_lower:
                if tag in intent or intent in tag:
                    return 0.8  # Partial match

        return 0.0

    def _calculate_confidence(self, score: float) -> str:
        """Calculate confidence level from score.

        Thresholds:
        - >= 0.90: EXACT
        - >= 0.70: HIGH
        - >= 0.50: MEDIUM
        - >= 0.30: LOW
        - < 0.30: NONE
        """
        if score >= 0.90:
            return "EXACT"
        elif score >= 0.70:
            return "HIGH"
        elif score >= 0.50:
            return "MEDIUM"
        elif score >= 0.30:
            return "LOW"
        else:
            return "NONE"

    def _tokenize(self, text: str, language: str = "nl") -> set[str]:
        """Tokenize text and remove stopwords.

        Args:
            text: Input text to tokenize
            language: "nl" for Dutch (default) or "en" for English

        Returns: Set[Any] of tokens with stopwords removed  # TODO(TYPE): replace Any with concrete type
        """
        # Normalize text
        text = text.lower()

        # Simple tokenization (split on non-alphanumeric)
        import re

        tokens = set(re.findall(r"\b[a-z]+\b", text))

        # Remove stopwords
        if language == "nl":
            stopwords = DUTCH_STOPWORDS
        elif language == "en":
            stopwords = ENGLISH_STOPWORDS
        else:
            stopwords = DUTCH_STOPWORDS  # Default to Dutch

        return tokens - stopwords


# Convenience function for direct usage
def score_packs_for_department(
    packs: list[Any],  # TODO(TYPE): replace Any with concrete type
    department_name: str,
    company_type: str,
    sector: str,
    **kwargs: Any,  # TODO(TYPE): replace with concrete type
) -> list[PackScore]:
    """Convenience function to score packs for a department.

    Args:
        packs: List[Any] of DomainPack objects  # TODO(TYPE): replace Any with concrete type
        department_name: Name of the department
        company_type: mkb, zzp, or enterprise
        sector: Business sector
        **kwargs: Additional signals (sector_tags, explicit_pack_ids)

    Returns: List[Any] of PackScore objects sorted by score  # TODO(TYPE): replace Any with concrete type
    """
    signals = ActivationSignals(
        department_name=department_name,
        company_type=company_type,
        sector=sector,
        sector_tags=kwargs.get("sector_tags", []),
        explicit_pack_ids=kwargs.get("explicit_pack_ids", []),
    )

    scorer = PackActivationScorer()
    return scorer.score_all_packs(packs, signals)


# Async convenience function with ML support
async def score_packs_for_department_async(
    packs: list[Any],  # TODO(TYPE): replace Any with concrete type
    department_name: str,
    company_type: str,
    sector: str,
    company_id: str | None = None,
    department_id: str | None = None,
    use_ml: bool = True,
    **kwargs: Any,
) -> list[PackScore]:
    """Async convenience function to score packs with ML support.

    Args:
        packs: List[Any] of DomainPack objects  # TODO(TYPE): replace Any with concrete type
        department_name: Name of the department
        company_type: mkb, zzp, or enterprise
        sector: Business sector
        company_id: Optional company ID for ML predictions
        department_id: Optional department ID for ML predictions
        use_ml: Whether to use ML-enhanced scoring (default: True)
        **kwargs: Additional signals (sector_tags, explicit_pack_ids)

    Returns: List[Any] of PackScore objects sorted by score  # TODO(TYPE): replace Any with concrete type
    """
    signals = ActivationSignals(
        department_name=department_name,
        company_type=company_type,
        sector=sector,
        sector_tags=kwargs.get("sector_tags", []),
        explicit_pack_ids=kwargs.get("explicit_pack_ids", []),
    )

    scorer = PackActivationScorer()
    return scorer.score_all_packs(packs, signals, company_id, department_id, use_ml=use_ml)
