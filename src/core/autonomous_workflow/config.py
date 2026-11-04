"""Configuration for autonomous workflow components."""


from pydantic import BaseModel, ConfigDict


class WorkflowConfig(BaseModel):
    """Configuration for autonomous workflow."""

    model_name: str = "codellama:13b"
    model_temperature: float = 0.2
    max_tokens: int = 2048
    feedback_threshold: float = 0.7
    batch_size: int = 32
    training_epochs: int = 10

    # Database settings
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Training settings
    learning_rate: float = 0.001
    weight_decay: float = 0.01

    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 9090

    model_config = ConfigDict(extra="allow")
