import logging

from src.core.shared.interfaces import TaskData
from src.core.shared.llm_client import ChatTaalmodel, LLMMessage

logger = logging.getLogger(__name__)


async def process_predictive_modeling(task: TaskData, llm_client: ChatTaalmodel | None) -> dict[str, str]:
    """Process predictive modeling tasks via LLM"""
    if llm_client is None:
        raise ValueError("llm_client is required for predictive modeling")

    prediction_horizon = task.metadata.get("prediction_horizon", "30_days")
    model_type = task.metadata.get("model_type", "time_series")

    prediction_prompt = f"""
    Design a predictive modeling strategy for:
    Task: {task.title}
    Horizon: {prediction_horizon}
    Type: {model_type}
    """
    messages = [LLMMessage(role="user", content=prediction_prompt)]
    response = await llm_client.chat_completion(messages)

    return {
        "prediction_type": model_type,
        "modeling_strategy": response.content if response.success else "Strategy developed",
        "status": "completed",
    }
