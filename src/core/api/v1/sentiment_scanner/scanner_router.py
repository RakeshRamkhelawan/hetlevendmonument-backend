# orphan:exempt
"""Sentiment Scanner sub-router (ADR-033 Laag 1).

All 5 routes migrated from src/core/api/sentiment_scanner_endpoints.py.
Prefix replicates the legacy double-prefix:
  agents.py adds /api/v1/agents at Laag 3,
  this sub-router retains /api/v1/sentiment-scanner as its own prefix.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency as get_current_user,
    require_scopes,
    OAuth2Scope,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/sentiment-scanner",
    tags=["sentiment-scanner", "cva-breakthrough"],
    responses={404: {"description": "Not found"}},
)


class SanskritiSentimentScanner:
    """CVA Breakthrough: Sanskriti Sentiment Scanner for cultural institutions."""

    def __init__(self) -> None:
        self.name = "Sanskriti Sentiment Scanner"
        self.version = "1.0.0 - CVA Breakthrough"
        self.positive_words = [
            "geweldig",
            "prachtig",
            "mooi",
            "fantastisch",
            "uitstekend",
            "perfect",
            "interessant",
            "boeiend",
            "inspirerend",
            "indrukwekkend",
            "aanrader",
            "amazing",
            "beautiful",
            "excellent",
            "fantastic",
            "great",
            "wonderful",
            "impressive",
            "inspiring",
            "outstanding",
            "brilliant",
        ]
        self.negative_words = [
            "slecht",
            "teleurstellend",
            "saai",
            "duur",
            "rommelig",
            "onduidelijk",
            "vervelend",
            "frustrerend",
            "chaos",
            "verspilling",
            "bad",
            "terrible",
            "disappointing",
            "boring",
            "expensive",
            "messy",
            "unclear",
            "annoying",
            "frustrating",
            "waste",
            "poor",
        ]

    def analyze_cultural_feedback(self, text: str, source: str = "review") -> dict[str, Any]:
        """Analyze sentiment of cultural institution feedback."""
        text_lower = text.lower()
        positive_count = sum(1 for word in self.positive_words if word in text_lower)
        negative_count = sum(1 for word in self.negative_words if word in text_lower)

        total_sentiment_words = positive_count + negative_count
        if total_sentiment_words == 0:
            polarity = 0.0
            sentiment = "neutral"
            confidence = 0.0
        else:
            polarity = (positive_count - negative_count) / len(text_lower.split()) * 10
            polarity = max(-1.0, min(1.0, polarity))
            if polarity > 0.1:
                sentiment = "positive"
            elif polarity < -0.1:
                sentiment = "negative"
            else:
                sentiment = "neutral"
            confidence = min(100.0, (total_sentiment_words / len(text_lower.split())) * 100 * 5)

        return {
            "text": text,
            "sentiment": sentiment,
            "polarity": round(polarity, 3),
            "confidence": round(confidence, 2),
            "positive_indicators": positive_count,
            "negative_indicators": negative_count,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scanner_version": self.version,
        }

    def batch_analyze(self, feedback_list: list[Any]) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze multiple feedback items."""
        results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for item in feedback_list:
            if isinstance(item, dict):
                text = item.get("text", "")
                source = item.get("source", "unknown")
            else:
                text = str(item)
                source = "api_input"
            results.append(self.analyze_cultural_feedback(text, source))
        return results

    def generate_report(self, analyses: list[Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate comprehensive sentiment report."""
        if not analyses:
            return {"error": "No analyses provided"}

        total = len(analyses)
        positive = sum(1 for a in analyses if a["sentiment"] == "positive")
        negative = sum(1 for a in analyses if a["sentiment"] == "negative")
        neutral = sum(1 for a in analyses if a["sentiment"] == "neutral")

        avg_confidence = sum(a["confidence"] for a in analyses) / total
        avg_polarity = sum(a["polarity"] for a in analyses) / total
        pos_rate = (positive / total) * 100
        neg_rate = (negative / total) * 100

        recommendations: list[str] = []
        if pos_rate > 70:
            recommendations.append(
                "Excellent visitor satisfaction! Consider highlighting positive aspects in marketing."
            )
        elif pos_rate < 30:
            recommendations.append(
                "Low satisfaction detected. Investigate specific concerns raised in negative feedback."
            )
        if neg_rate > 30:
            recommendations.append("High negative sentiment detected. Urgent attention needed.")
        if neutral / total > 0.6:
            recommendations.append(
                "Many neutral responses. Consider enhancing visitor engagement strategies."
            )

        return {
            "report_generated": datetime.now(timezone.utc).isoformat(),
            "scanner_info": {"name": self.name, "version": self.version},
            "analysis_summary": {
                "total_feedback": total,
                "average_confidence": round(avg_confidence, 2),
                "average_polarity": round(avg_polarity, 3),
            },
            "sentiment_breakdown": {
                "positive": {"count": positive, "percentage": round((positive / total) * 100, 1)},
                "negative": {"count": negative, "percentage": round((negative / total) * 100, 1)},
                "neutral": {"count": neutral, "percentage": round((neutral / total) * 100, 1)},
            },
            "recommendations": recommendations,
        }


_scanner = SanskritiSentimentScanner()


class FeedbackAnalysisRequest(BaseModel):
    """Request model for single feedback analysis."""

    text: str = Field(..., description="Feedback text to analyze")
    source: str = Field("api", description="Source of feedback (review, social_media, etc.)")


class BatchAnalysisRequest(BaseModel):
    """Request model for batch feedback analysis."""

    feedback_list: list[dict[str, str]] = Field(
        ..., description="List of feedback items to analyze"
    )


class SentimentAnalysisResponse(BaseModel):
    """Response model for sentiment analysis."""

    text: str
    sentiment: str
    polarity: float
    confidence: float
    positive_indicators: int
    negative_indicators: int
    source: str
    timestamp: str
    scanner_version: str


class BatchAnalysisResponse(BaseModel):
    """Response model for batch analysis."""

    results: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    total_analyzed: int
    processing_time: float


class SentimentReportResponse(BaseModel):
    """Response model for sentiment report."""

    report_generated: str
    scanner_info: dict[str, str]
    analysis_summary: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    sentiment_breakdown: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    recommendations: list[str]


@router.get("/status")
async def get_scanner_status(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get Sanskriti Sentiment Scanner status and information. Requires: OAuth2Scope.AGENTS_READ"""
    logger.info("User %s getting scanner status", current_user.id)
    return {
        "scanner_name": _scanner.name,
        "version": _scanner.version,
        "status": "operational",
        "breakthrough_type": "CVA Autonomous Innovation",
        "supported_languages": ["Dutch", "English"],
        "capabilities": [
            "Cultural feedback sentiment analysis",
            "Batch processing",
            "Confidence scoring",
            "Automated reporting",
            "Actionable recommendations",
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/analyze", response_model=SentimentAnalysisResponse)
async def analyze_feedback(
    request: FeedbackAnalysisRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> SentimentAnalysisResponse:
    """Analyze sentiment of single cultural institution feedback. Requires: OAuth2Scope.AGENTS_WRITE"""
    logger.info("User %s analyzing feedback", current_user.id)
    try:
        result = _scanner.analyze_cultural_feedback(request.text, request.source)
        return SentimentAnalysisResponse(**result)
    except Exception as e:
        logger.error("Sentiment analysis failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Sentiment analysis failed") from e


@router.post("/batch-analyze", response_model=BatchAnalysisResponse)
async def batch_analyze_feedback(
    request: BatchAnalysisRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
) -> BatchAnalysisResponse:
    """Batch analysis of multiple cultural feedback items. Requires: OAuth2Scope.AGENTS_WRITE"""
    logger.info("User %s batch analyzing feedback", current_user.id)
    try:
        start_time = datetime.now(timezone.utc)
        results = _scanner.batch_analyze(request.feedback_list)
        processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        return BatchAnalysisResponse(
            results=results,
            total_analyzed=len(results),
            processing_time=processing_time,
        )
    except Exception as e:
        logger.error("Batch analysis failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Batch analysis failed") from e


@router.post("/generate-report", response_model=SentimentReportResponse)
async def generate_sentiment_report(
    request: BatchAnalysisRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> SentimentReportResponse:
    """Generate comprehensive sentiment analysis report. Requires: OAuth2Scope.AGENTS_READ"""
    logger.info("User %s generating sentiment report", current_user.id)
    try:
        results = _scanner.batch_analyze(request.feedback_list)
        report = _scanner.generate_report(results)
        return SentimentReportResponse(**report)
    except Exception as e:
        logger.error("Report generation failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Report generation failed") from e


@router.get("/demo")
async def demo_sentiment_scanner(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Demonstration of Sanskriti Sentiment Scanner capabilities. Requires: OAuth2Scope.AGENTS_READ"""
    logger.info("User %s running scanner demo", current_user.id)
    try:
        sample_feedback = [
            {"text": "De tentoonstelling was prachtig en zeer informatief!", "source": "review"},
            {
                "text": "Beautiful exhibition but the audio guide was broken",
                "source": "feedback_form",
            },
            {
                "text": "Not impressed with the layout, felt rushed and disappointing",
                "source": "social_media",
            },
            {"text": "Geweldige ervaring, zeker een aanrader voor families", "source": "review"},
            {"text": "Fantastisch museum, zeer inspirerend en boeiend", "source": "review"},
        ]
        results = _scanner.batch_analyze(sample_feedback)
        report = _scanner.generate_report(results)
        return {
            "demo_title": "Sanskriti Sentiment Scanner - CVA Breakthrough Demo",
            "description": "Real sentiment analysis for cultural institutions",
            "sample_analyses": results,
            "comprehensive_report": report,
            "breakthrough_info": {
                "innovation_type": "CVA Autonomous Ideation",
                "development_time": "21.43 seconds (real LLM)",
                "implementation_status": "Production Ready",
                "zero_simulation": True,
            },
        }
    except Exception as e:
        logger.error("Demo failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Demo failed") from e
