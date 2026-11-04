from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExperimentVariant(BaseModel):
    name: str = Field(..., description="Name of the variant (e.g. 'Control', 'Friendly')")
    description: str | None = None
    traffic: float = Field(..., gt=0, le=1.0, description="Traffic share (0.0 - 1.0)")
    is_control: bool = False
    content: str | None = Field(None, description="The prompt text content for this variant")
    configuration: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Configuration overrides"
    )


class CreateExperimentRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: str
    prompt_template_id: int
    variants: list[ExperimentVariant]
    min_sample_size: int = Field(default=100, ge=30)

    @field_validator("variants")
    def validate_traffic_sum(cls, v: list["ExperimentVariant"]) -> list["ExperimentVariant"]:
        total = sum(var.traffic for var in v)
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Traffic must sum to 1.0, got {total}")
        if not any(var.is_control for var in v):
            raise ValueError("Must have at least one control variant")
        return v


class RecordFeedbackRequest(BaseModel):
    experiment_id: str
    variant_id: str
    user_id: int
    score: float = Field(..., ge=1, le=5)
    comment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class ExperimentResponse(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    start_time: datetime
    end_time: datetime | None = None
    prompt_template_id: int

    model_config = ConfigDict(from_attributes=True)


class PromoteRequest(BaseModel):
    template_id: int
