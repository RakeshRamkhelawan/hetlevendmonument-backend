"""
Nonprofit Vertical - Donor Metrics & Engagement
Implements churn prediction and re-engagement recommendations.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class ChurnRisk(Enum):
    """Donor churn risk levels"""

    LOW = "low"  # <0.3 probability
    MEDIUM = "medium"  # 0.3-0.7 probability
    HIGH = "high"  # >0.7 probability


class EngagementAction(Enum):
    """Recommended re-engagement actions"""

    EMAIL = "re_engagement_email"
    EVENT_INVITE = "event_invitation"
    THANK_YOU_CALL = "personalized_call"
    NO_ACTION = "no_action_needed"


@dataclass
class DonorProfile:
    """Donor profile with engagement history"""

    donor_id: str
    name: str
    total_donations: float
    last_donation_date: datetime
    email_opens_90d: int
    event_attendance_count: int
    years_active: int
    consent_marketing: bool


class NonprofitEngagementAgent:
    """
    Nonprofit fundraiser AI agent.
    Predicts donor churn and recommends re-engagement strategies.
    """

    CHURN_PREDICTION_PROMPT = """
You are a nonprofit fundraiser AI.
Donor profile: {donor_data}
Task: Analyze engagement trends and predict if likely to churn in 90 days.
Output: {{"churn_risk": 0-1, "recommendation": "action_string", "reason": "explanation"}}
Recommend: re-engagement email, event invite, or personalized thank-you call.

Analysis Factors:
1. Last donation date (weight: 40%)
2. Email engagement rate (weight: 25%)
3. Event attendance (weight: 20%)
4. Years active (weight: 15%)

Thresholds:
- High Risk: >180 days since donation, <20% email open rate
- Medium Risk: 90-180 days, 20-50% email open rate
- Low Risk: <90 days, >50% email open rate
"""

    def __init__(self, audit_service: Any | None = None) -> None:  # TODO(TYPE): replace Any with concrete type
        self.audit_service = audit_service

    def analyze_churn_risk(self, donor: DonorProfile) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Analyze donor engagement and predict churn probability.

        Args:
            donor: Donor profile with engagement history

        Returns:
            Churn analysis with risk score and recommendation
        """
        # Simple heuristic model (in production, use ML model)
        days_since_donation = (datetime.now(timezone.utc) - donor.last_donation_date).days
        email_engagement_rate = donor.email_opens_90d / 10.0  # Assume 10 emails sent

        # Calculate risk score (0-1)
        risk_score: float = 0.0

        # Factor 1: Recency (40%)
        if days_since_donation > 180:
            risk_score += 0.4
        elif days_since_donation > 90:
            risk_score += 0.2

        # Factor 2: Email engagement (25%)
        if email_engagement_rate < 0.2:
            risk_score += 0.25
        elif email_engagement_rate < 0.5:
            risk_score += 0.125

        # Factor 3: Event attendance (20%)
        if donor.event_attendance_count == 0:
            risk_score += 0.2
        elif donor.event_attendance_count < 2:
            risk_score += 0.1

        # Factor 4: Loyalty (15%)
        if donor.years_active < 1:
            risk_score += 0.15
        elif donor.years_active < 3:
            risk_score += 0.075

        # Determine risk level and recommendation
        if risk_score > 0.7:
            risk_level = ChurnRisk.HIGH
            recommendation = EngagementAction.THANK_YOU_CALL
            reason = f"High churn risk ({risk_score:.2f}): {days_since_donation} days inactive, low engagement"
        elif risk_score > 0.3:
            risk_level = ChurnRisk.MEDIUM
            recommendation = EngagementAction.EVENT_INVITE
            reason = (
                f"Medium churn risk ({risk_score:.2f}): Declining engagement, needs re-connection"
            )
        else:
            risk_level = ChurnRisk.LOW
            recommendation = EngagementAction.NO_ACTION
            reason = f"Low churn risk ({risk_score:.2f}): Active and engaged donor"

        return {
            "donor_id": donor.donor_id,
            "churn_risk": risk_score,
            "risk_level": risk_level.value,
            "recommendation": recommendation.value,
            "reason": reason,
            "days_since_donation": days_since_donation,
            "email_engagement_rate": email_engagement_rate,
        }

    async def trigger_re_engagement(
        self, donor: DonorProfile, action: EngagementAction
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Trigger re-engagement action (email, event invite, call).

        Args:
            donor: Donor profile
            action: Recommended engagement action

        Returns:
            Action result with tracking ID
        """
        if not donor.consent_marketing:
            raise PermissionError(f"Donor {donor.donor_id} has not consented to marketing")

        # Log action to audit trail
        if self.audit_service:
            await self.audit_service.log_action(
                tenant_id="nonprofit_tenant",
                action="DONOR_RE_ENGAGEMENT",
                resource=f"donor:{donor.donor_id}",
                details={
                    "action": action.value,
                    "churn_risk": self.analyze_churn_risk(donor)["churn_risk"],
                },
            )

        return {
            "action_id": f"ENG_{donor.donor_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            "donor_id": donor.donor_id,
            "action": action.value,
            "status": "scheduled",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def get_prompt_template() -> str:
        """Return the LLM prompt template for churn prediction"""
        return NonprofitEngagementAgent.CHURN_PREDICTION_PROMPT
