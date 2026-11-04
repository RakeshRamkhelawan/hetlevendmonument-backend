"""
Data Quality Sentinel Agent - Data & AI Governance

CRITICAL PRIORITY
Technology: ML
Function: Data quality monitoring, anomaly detection, validation
"""

import logging
from datetime import datetime, timezone
from typing import Any, cast

from src.core.als.agents.departments.base_department_agent import DepartmentType, MLAgent
from src.core.als.agents.symbiotic_agent import ExecutionResult

logger = logging.getLogger(__name__)


class DataQualitySentinelAgent(MLAgent):
    """
    Data Quality Sentinel Agent

    Responsibilities:
    - Data quality monitoring
    - Schema validation
    - Anomaly detection in datasets
    - Data drift detection
    - Quality score calculation

    Capabilities:
    - Statistical quality metrics
    - Pattern validation
    - Completeness checking
    - Consistency verification
    """

    department = DepartmentType.DATA_AI_GOVERNANCE
    priority = "critical"

    QUALITY_DIMENSIONS = [
        "completeness",
        "accuracy",
        "consistency",
        "timeliness",
        "validity",
        "uniqueness",
    ]

    department_capabilities = [
        "data_quality_assessment",
        "schema_validation",
        "anomaly_detection",
        "data_drift_monitoring",
        "quality_score_calculation",
        "completeness_check",
        "consistency_verification",
        "duplicate_detection",
    ]

    def __init__(self, agent_id: str, tenant_id: int, **kwargs: object) -> None:
        super().__init__(agent_id, tenant_id, **kwargs)

        self.quality_thresholds = {
            "completeness": 0.95,
            "accuracy": 0.90,
            "consistency": 0.95,
        }

        logger.info(f"DataQualitySentinelAgent {agent_id} initialized")

    async def orient(
        self,
        observation: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze data quality."""
        payload = observation.get("payload", {})

        dataset = payload.get("dataset", {})
        schema = payload.get("schema", {})

        analysis = {
            **observation,
            "record_count": len(dataset.get("records", [])),
            "field_count": len(schema.get("fields", [])),
            "completeness_score": self._check_completeness(dataset),
            "anomalies_found": self._detect_data_anomalies(dataset),
            "schema_violations": self._validate_schema(dataset, schema),
            "overall_quality_score": 0.0,  # Calculated below
        }

        analysis["overall_quality_score"] = self._calculate_overall_score(analysis)

        return analysis

    async def decide(
        self,
        orientation: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Decide data quality action."""
        quality_score = orientation.get("overall_quality_score", 0)
        anomalies = orientation.get("anomalies_found", [])
        violations = orientation.get("schema_violations", [])

        if quality_score < 0.7 or len(violations) > 10:
            return "quarantine_data"
        elif quality_score < 0.9 or len(anomalies) > 5:
            return "flag_for_review"
        elif len(violations) > 0:
            return "apply_data_cleansing"
        else:
            return "approve_data"

    async def act(self, decision: str) -> ExecutionResult:
        """Execute data quality action."""
        logger.info(f"DataQualitySentinel acting: {decision}")

        return ExecutionResult(
            task_id=f"quality_{self.agent_id}_{id(decision)}",
            success=True,
            result_data={
                "action": decision,
                "data_status": "processed",
                "applied_rules": self.quality_thresholds,
                "agent_type": "data_quality_sentinel",
                "check_timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _check_completeness(
        self,
        dataset: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate completeness score."""
        records = dataset.get("records", [])
        if not records:
            return 0.0

        total_fields = 0
        filled_fields = 0

        for record in records:
            for key, value in record.items():
                total_fields += 1
                if value is not None and value != "":
                    filled_fields += 1

        return filled_fields / total_fields if total_fields > 0 else 0.0

    def _detect_data_anomalies(
        self,
        dataset: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Detect anomalies in data."""
        anomalies: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        records = dataset.get("records", [])

        # Simple outlier detection for numeric fields
        numeric_values: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for record in records:
            for key, value in record.items():
                if isinstance(value, (int, float)):
                    numeric_values.append(value)

        if numeric_values:
            mean = sum(numeric_values) / len(numeric_values)
            std = (sum((x - mean) ** 2 for x in numeric_values) / len(numeric_values)) ** 0.5

            for i, record in enumerate(records):
                for key, value in record.items():
                    if isinstance(value, (int, float)) and abs(value - mean) > 3 * std:
                        anomalies.append(
                            {
                                "record_index": i,
                                "field": key,
                                "value": value,
                                "type": "outlier",
                            }
                        )

        return anomalies

    def _validate_schema(
        self,
        dataset: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        schema: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Validate data against schema."""
        violations: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        records = dataset.get("records", [])
        fields = schema.get("fields", [])

        required_fields = [f["name"] for f in fields if f.get("required")]

        for i, record in enumerate(records):
            for field in required_fields:
                if field not in record or record[field] is None:
                    violations.append(
                        {
                            "record_index": i,
                            "field": field,
                            "issue": "missing_required",
                        }
                    )

        return violations

    def _calculate_overall_score(
        self,
        analysis: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> float:  # TODO(TYPE): replace Any with concrete type
        """Calculate overall quality score."""
        completeness = analysis.get("completeness_score", 0)
        anomaly_penalty = len(analysis.get("anomalies_found", [])) * 0.01
        violation_penalty = len(analysis.get("schema_violations", [])) * 0.02

        score = completeness - anomaly_penalty - violation_penalty
        return cast(float, max(score, 0.0))
