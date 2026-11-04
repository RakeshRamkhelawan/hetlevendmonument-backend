from typing import Any


class TrainingPipeline:
    """Stub TrainingPipeline -- the real implementation lives in the sibling training.py,
    which is shadowed by this package. Exposed here so orchestrator.py imports resolve."""

    def __init__(self, config: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        self.config = config

    async def train_on_experiences(self, experiences: list[Any], epochs: int = 1) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {}

    def save_model(self, path: str) -> None:
        pass
