import datetime
import json
from typing import Any


class StateBuilder:
    """
    Builds a normalized numerical state vector from system parameters.
    This vector serves as input for the PPO Reinforcement Learning model.
    """

    def build_state_vector(
        self, tool_name: str, payload: dict[str, Any], current_time: datetime.datetime  # TODO(TYPE): replace Any with concrete type
    ) -> list[float]:
        """
        Constructs a normalized state vector.

        Args:
            tool_name: The name of the tool being requested.
            payload: The parameters for the tool.
            current_time: The current timestamp.

        Returns:
            A list of floats representing the normalized state vector.
        """
        state_vector: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # 1. Tool Name Feature (simple hash for numerical representation)
        # In a real system, this would be a more sophisticated embedding or one-hot encoding
        tool_name_hash = hash(tool_name) % (10**5)  # Limit hash size
        state_vector.append(tool_name_hash / (10**5))  # Normalize to 0-1

        # 2. Payload Size Feature (proxy for complexity/data volume)
        payload_str = json.dumps(payload)
        payload_size = len(payload_str)
        # Normalize payload size (e.g., assuming max payload size of 10KB for now)
        normalized_payload_size = min(payload_size / 10000.0, 1.0)  # Cap at 1.0
        state_vector.append(normalized_payload_size)

        # 3. Time of Day Feature (hour of day, normalized)
        hour_of_day = current_time.hour
        normalized_hour = hour_of_day / 23.0  # Normalize to 0-1 (0-23 hours)
        state_vector.append(normalized_hour)

        # 4. Day of Week Feature (normalized)
        day_of_week = current_time.weekday()  # Monday is 0, Sunday is 6
        normalized_day_of_week = day_of_week / 6.0  # Normalize to 0-1
        state_vector.append(normalized_day_of_week)

        # Add more features as needed (e.g., agent load, historical performance, etc.)
        # For now, this provides a basic, normalized vector.

        return state_vector
