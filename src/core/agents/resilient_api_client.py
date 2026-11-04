#!/usr/bin/env python3
"""
Resilient API Client with Circuit Breaker Pattern for M-MDP
Production-ready error handling, retries, and failure isolation
Enhanced for M-MDP learning system integration
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, TypedDict, cast

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("ResilientAPI")


class CircuitBreakerMetricsDict(TypedDict):
    """Metrics for a single circuit breaker instance."""

    total_requests: int
    successful_requests: int
    failed_requests: int
    success_rate: float
    average_response_time: float
    circuit_opens: int


class CircuitBreakerStatusDict(TypedDict):
    """Status snapshot for a single circuit breaker."""

    state: str
    failure_count: int
    metrics: CircuitBreakerMetricsDict


class HealthSummaryDict(TypedDict, total=False):
    """Health summary across all subsystems."""

    system_health: dict[str, object]
    learning_health: dict[str, object]
    safety_health: dict[str, object]
    circuit_breakers: dict[str, CircuitBreakerStatusDict]
    overall_health_score: float
    status: str
    error: str


class CircuitState(Enum):
    """Circuit breaker states"""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""

    failure_threshold: int = 5  # Failures before opening circuit
    recovery_timeout: int = 30  # Seconds before trying half-open
    success_threshold: int = 2  # Successes needed to close circuit
    timeout: int = 10  # Request timeout in seconds


@dataclass
class RetryConfig:
    """Configuration for retry behavior"""

    max_retries: int = 3
    backoff_factor: float = 2.0  # Exponential backoff multiplier
    retry_on_status: list[int] = field(default_factory=lambda: [500, 502, 503, 504])


@dataclass
class HealthMetrics:
    """Health metrics for monitoring"""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    circuit_opens: int = 0
    last_failure_time: datetime | None = None
    average_response_time: float = 0.0
    response_times: list[float] = field(default_factory=list)


class CircuitBreaker:
    """
    Circuit breaker implementation for API resilience
    Prevents cascading failures by temporarily blocking requests to failing services
    """

    def __init__(self, name: str, config: CircuitBreakerConfig) -> None:
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.success_count = 0
        self.metrics = HealthMetrics()

    def call(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> (
        # TODO(TYPE): replace Any with concrete type
        Any
    ):  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
        """Execute function call through circuit breaker"""
        self.metrics.total_requests += 1

        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info(f"Circuit breaker {self.name} moving to HALF_OPEN")
            else:
                logger.warning(f"Circuit breaker {self.name} is OPEN - blocking request")
                raise CircuitBreakerOpenException(f"Circuit breaker {self.name} is OPEN")

        try:
            start_time = time.time()
            result = func(*args, **kwargs)
            response_time = time.time() - start_time

            self._record_success(response_time)
            return result

        except Exception as e:
            self._record_failure(e)
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.last_failure_time is None:
            return True
        return datetime.now(timezone.utc) - self.last_failure_time > timedelta(
            seconds=self.config.recovery_timeout
        )

    def _record_success(self, response_time: float) -> None:
        """Record successful request"""
        self.metrics.successful_requests += 1
        self.metrics.response_times.append(response_time)

        # Update rolling average (keep last 100 responses)
        if len(self.metrics.response_times) > 100:
            self.metrics.response_times = self.metrics.response_times[-100:]
        self.metrics.average_response_time = sum(self.metrics.response_times) / len(
            self.metrics.response_times
        )

        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                logger.info(f"Circuit breaker {self.name} moving to CLOSED (recovered)")
                self._reset()
        else:
            self.failure_count = 0  # Reset failure count on success

    def _record_failure(self, exception: Exception) -> None:
        """Record failed request"""
        self.metrics.failed_requests += 1
        self.metrics.last_failure_time = datetime.now(timezone.utc)
        self.last_failure_time = datetime.now(timezone.utc)
        self.failure_count += 1

        logger.warning(f"Circuit breaker {self.name} recorded failure: {exception}")

        if self.failure_count >= self.config.failure_threshold:
            logger.error(f"Circuit breaker {self.name} moving to OPEN (failure threshold reached)")
            self.state = CircuitState.OPEN
            self.metrics.circuit_opens += 1

    def _reset(self) -> None:
        """Reset circuit breaker to closed state"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0


class CircuitBreakerOpenException(Exception):
    """Exception raised when circuit breaker is open"""


class ResilientAPIClient:
    """
    Production-ready API client with circuit breaker, retries, and comprehensive error handling
    Enhanced for M-MDP learning system endpoints
    """

    def __init__(
        self,
        base_url: str,
        circuit_config: CircuitBreakerConfig | None = None,
        retry_config: RetryConfig | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.circuit_config = circuit_config or CircuitBreakerConfig()
        self.retry_config = retry_config or RetryConfig()

        # Setup circuit breakers for different endpoint categories (M-MDP enhanced)
        self.circuit_breakers = {
            "dashboard": CircuitBreaker("dashboard", self.circuit_config),
            "agents": CircuitBreaker("agents", self.circuit_config),
            "tasks": CircuitBreaker("tasks", self.circuit_config),
            "health": CircuitBreaker(
                "health", CircuitBreakerConfig(failure_threshold=10)
            ),  # More tolerant
            "learning": CircuitBreaker("learning", self.circuit_config),  # M-MDP
            "meta_learning": CircuitBreaker("meta_learning", self.circuit_config),  # M-MDP
            "safety": CircuitBreaker(
                "safety", CircuitBreakerConfig(failure_threshold=2)
            ),  # Less tolerant
            "prediction": CircuitBreaker("prediction", self.circuit_config),  # M-MDP
            "monitoring": CircuitBreaker("monitoring", self.circuit_config),  # M-MDP
        }

        # Setup requests session with retry strategy
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retry configuration"""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=self.retry_config.max_retries,
            backoff_factor=self.retry_config.backoff_factor,
            status_forcelist=self.retry_config.retry_on_status,
            raise_on_status=False,
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update(
            {
                "Content-Type": "application/json",
                "User-Agent": "Resilient-MMDP-Client/3.0",
            }
        )

        return session

    def get_dashboard(self) -> dict[str, object]:
        """Get system dashboard with circuit breaker protection"""
        return cast(
            dict[str, object],
            self.circuit_breakers["dashboard"].call(
                self._make_request, "GET", "/api/v1/orchestrator/dashboard"
            ),
        )

    def get_agents(self) -> dict[str, object]:
        """Get agent information with circuit breaker protection"""
        return cast(
            dict[str, object],
            self.circuit_breakers["agents"].call(
                self._make_request, "GET", "/api/v1/orchestrator/agents"
            ),
        )

    def create_task(self, task_data: dict[str, object]) -> dict[str, object]:
        """Create task with circuit breaker protection"""
        return cast(
            dict[str, object],
            self.circuit_breakers["tasks"].call(
                self._make_request, "POST", "/api/v1/tasks", json=task_data
            ),
        )

    def health_check(self) -> dict[str, object]:
        """Perform health check with circuit breaker protection"""
        return cast(
            dict[str, object],
            self.circuit_breakers["health"].call(self._make_request, "GET", "/health"),
        )

    # M-MDP Specific Methods
    def get_learning_status(self) -> dict[str, object]:
        """Get M-MDP learning system status"""
        return cast(
            dict[str, object],
            self.circuit_breakers["learning"].call(
                self._make_request, "GET", "/api/v1/learning/status"
            ),
        )

    def start_training(self, config: dict[str, object]) -> dict[str, object]:
        """Start M-MDP training with circuit breaker protection"""
        return cast(
            dict[str, object],
            self.circuit_breakers["learning"].call(
                self._make_request, "POST", "/api/v1/learning/train", json=config
            ),
        )

    def get_meta_learning_status(
        self,
    ) -> dict[str, object]:
        """Get meta-learning system status"""
        return cast(
            dict[str, object],
            self.circuit_breakers["meta_learning"].call(
                self._make_request, "GET", "/api/v1/learning/meta/status"
            ),
        )

    def get_safety_status(self) -> dict[str, object]:
        """Get safety system status with high priority circuit breaker"""
        return cast(
            dict[str, object],
            self.circuit_breakers["safety"].call(
                self._make_request, "GET", "/api/v1/learning/safety/status"
            ),
        )

    def get_predictions(self, prediction_type: str = "performance") -> dict[str, object]:
        """Get predictive system forecasts"""
        return cast(
            dict[str, object],
            self.circuit_breakers["prediction"].call(
                self._make_request, "GET", f"/api/v1/learning/predict/{prediction_type}"
            ),
        )

    def get_monitoring_report(self) -> dict[str, object]:
        """Get advanced monitoring report"""
        return cast(
            dict[str, object],
            self.circuit_breakers["monitoring"].call(
                self._make_request, "GET", "/api/v1/monitoring/report"
            ),
        )

    def trigger_safety_check(self) -> dict[str, object]:
        """Trigger immediate safety validation"""
        return cast(
            dict[str, object],
            self.circuit_breakers["safety"].call(
                self._make_request, "POST", "/api/v1/learning/safety/check"
            ),
        )

    def update_learning_parameters(self, parameters: dict[str, object]) -> dict[str, object]:
        """Update learning system parameters"""
        return cast(
            dict[str, object],
            self.circuit_breakers["learning"].call(
                self._make_request, "PUT", "/api/v1/learning/config", json=parameters
            ),
        )

    def _make_request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, object]:
        """Make HTTP request with comprehensive error handling"""
        url = f"{self.base_url}{endpoint}"
        kwargs["timeout"] = self.circuit_config.timeout

        try:
            response = self.session.request(method, url, **kwargs)

            # Handle different response scenarios
            if response.status_code == 200:
                try:
                    json_data: dict[str, object] = response.json()
                    return json_data
                except ValueError:
                    # Handle non-JSON responses
                    return {"data": response.text, "status": "success"}
            elif response.status_code == 404:
                raise APINotFoundException(f"Endpoint not found: {endpoint}")
            elif response.status_code == 429:
                raise APIRateLimitException("Rate limit exceeded")
            elif response.status_code >= 500:
                raise APIServerException(f"Server error: {response.status_code}")
            else:
                raise APIClientException(f"Client error: {response.status_code}")

        except requests.exceptions.Timeout:
            raise APITimeoutException(f"Request timeout after {self.circuit_config.timeout}s")
        except requests.exceptions.ConnectionError:
            raise APIConnectionException(f"Could not connect to {self.base_url}")
        except requests.exceptions.RequestException as e:
            raise APIException(f"Request failed: {str(e)}")

    def get_circuit_breaker_status(
        self,
    ) -> dict[str, CircuitBreakerStatusDict]:
        """Get status of all circuit breakers for monitoring"""
        status: dict[str, CircuitBreakerStatusDict] = {}
        for name, cb in self.circuit_breakers.items():
            status[name] = {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "metrics": {
                    "total_requests": cb.metrics.total_requests,
                    "successful_requests": cb.metrics.successful_requests,
                    "failed_requests": cb.metrics.failed_requests,
                    "success_rate": (
                        cb.metrics.successful_requests / max(cb.metrics.total_requests, 1)
                    )
                    * 100,
                    "average_response_time": cb.metrics.average_response_time,
                    "circuit_opens": cb.metrics.circuit_opens,
                },
            }
        return status

    def get_health_summary(self) -> HealthSummaryDict:
        """Get comprehensive health summary across all systems"""
        try:
            health_data: HealthSummaryDict = {
                "system_health": self.health_check(),
                "learning_health": self.get_learning_status(),
                "safety_health": self.get_safety_status(),
                "circuit_breakers": self.get_circuit_breaker_status(),
            }

            # Calculate overall health score
            cb_data: dict[str, CircuitBreakerStatusDict] = health_data["circuit_breakers"]
            cb_success_rates = [
                cb["metrics"]["success_rate"]
                for cb in cb_data.values()
                if cb["metrics"]["total_requests"] > 0
            ]
            overall_health = (
                sum(cb_success_rates) / len(cb_success_rates) if cb_success_rates else 100
            )

            health_data["overall_health_score"] = overall_health
            health_data["status"] = (
                "healthy"
                if overall_health > 90
                else "degraded"
                if overall_health > 70
                else "unhealthy"
            )

            return health_data

        except Exception as e:
            logger.error(f"Health summary failed: {e}")
            return cast(
                HealthSummaryDict,
                {
                    "status": "unknown",
                    "error": str(e),
                    "circuit_breakers": self.get_circuit_breaker_status(),
                },
            )


# Custom exceptions for different error types
class APIException(Exception):
    """Base API exception"""


class APITimeoutException(APIException):
    """Request timeout exception"""


class APIConnectionException(APIException):
    """Connection error exception"""


class APINotFoundException(APIException):
    """404 Not Found exception"""


class APIRateLimitException(APIException):
    """Rate limit exceeded exception"""


class APIServerException(APIException):
    """Server error (5xx) exception"""


class APIClientException(APIException):
    """Client error (4xx) exception"""


# Usage example and testing for M-MDP
if __name__ == "__main__":
    # Test the resilient API client with M-MDP features
    from src.config import get_api_base_url

    client = ResilientAPIClient(get_api_base_url())

    try:
        print("=== RESILIENT M-MDP API CLIENT TEST ===")

        # Test health check
        health = client.health_check()
        print(f"Health check: {health.get('status', 'unknown')}")

        # Test M-MDP specific endpoints
        try:
            learning_status = client.get_learning_status()
            print(f"Learning system: {learning_status.get('status', 'unknown')}")
        except Exception as e:
            print(f"Learning status unavailable: {e}")

        try:
            safety_status = client.get_safety_status()
            print(f"Safety system: {safety_status.get('status', 'unknown')}")
        except Exception as e:
            print(f"Safety status unavailable: {e}")

        # Test comprehensive health summary
        health_summary = client.get_health_summary()
        print(
            f"Overall health: {health_summary.get('status', 'unknown')} "
            f"(score: {health_summary.get('overall_health_score', 0):.1f}%)"
        )

        # Show circuit breaker status
        cb_status = client.get_circuit_breaker_status()
        for name, status in cb_status.items():
            print(
                f"Circuit breaker {name}: {status['state']} "
                f"(success rate: {status['metrics']['success_rate']:.1f}%)"
            )

    except Exception as e:
        print(f"API call failed: {e}")
        # Show circuit breaker status after failure
        cb_status = client.get_circuit_breaker_status()
        for name, status in cb_status.items():
            if status["metrics"]["failed_requests"] > 0:
                print(f"Circuit breaker {name} has {status['metrics']['failed_requests']} failures")
