"""Circuit breaker — detect task anomalies and trigger rollback.

Monitors:
- Token exhaustion (Claude returns specific error patterns)
- Network failures (consecutive connection errors)
- Task timeout (running longer than configured max)

On anomaly: terminate task → send QQ notification → rollback state.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from plan_state import PlanStateMachine

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerConfig:
    enabled: bool = True
    max_retries: int = 3
    task_timeout_minutes: int = 30


@dataclass
class BreakerState:
    failure_count: int = 0
    last_failure_time: float = 0.0
    last_failure_reason: str = ""
    is_open: bool = False
    open_since: float = 0.0


class CircuitBreaker:
    """Detects anomalies and triggers emergency stop + state rollback."""

    # Claude token-exhaustion patterns
    TOKEN_EXHAUSTION_PATTERNS = [
        "token budget",
        "token limit",
        "rate limit",
        "usage exceeds",
        "maximum context",
        "context length",
        "too many tokens",
    ]

    # Network error patterns
    NETWORK_ERROR_PATTERNS = [
        "Connection refused",
        "Connection reset",
        "TLS handshake",
        "connect timeout",
        "name resolution",
        "no route to host",
        "ConnectionError",
        "aiohttp",
    ]

    def __init__(
        self,
        config: CircuitBreakerConfig,
        plan_state: PlanStateMachine,
        notification_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._config = config
        self._plan_state = plan_state
        self._notify = notification_callback
        self._state = BreakerState()

    @property
    def is_open(self) -> bool:
        return self._state.is_open

    def reset(self) -> None:
        """Reset breaker after successful recovery."""
        self._state = BreakerState()
        logger.info("Circuit breaker reset")

    def check_health(self, task_id: str, elapsed_seconds: float) -> str | None:
        """Check if a running task is healthy. Returns error reason or None."""
        if not self._config.enabled:
            return None

        # Timeout check
        timeout_seconds = self._config.task_timeout_minutes * 60
        if elapsed_seconds > timeout_seconds:
            reason = f"任务超时（运行 {elapsed_seconds / 60:.1f} 分钟，阈值 {self._config.task_timeout_minutes} 分钟）"
            self._trip(task_id, reason)
            return reason

        return None

    def check_claude_response(self, task_id: str, response: str) -> str | None:
        """Check Claude response for token exhaustion or other fatal errors."""
        if not self._config.enabled:
            return None

        response_lower = response.lower()

        for pattern in self.TOKEN_EXHAUSTION_PATTERNS:
            if pattern.lower() in response_lower:
                reason = f"Token 耗尽：检测到「{pattern}」"
                self._trip(task_id, reason)
                return reason

        return None

    def check_network_error(self, task_id: str, error_message: str) -> str | None:
        """Check if error is a network-level failure warranting circuit break."""
        if not self._config.enabled:
            return None

        for pattern in self.NETWORK_ERROR_PATTERNS:
            if pattern.lower() in error_message.lower():
                self._state.failure_count += 1
                self._state.last_failure_time = time.time()
                self._state.last_failure_reason = error_message[:200]

                if self._state.failure_count >= self._config.max_retries:
                    reason = (
                        f"网络异常（连续 {self._state.failure_count} 次失败）："
                        f"{error_message[:150]}"
                    )
                    self._trip(task_id, reason)
                    return reason
                else:
                    logger.warning(
                        "Network failure %d/%d: %s",
                        self._state.failure_count,
                        self._config.max_retries,
                        error_message[:100],
                    )
                    return None

        # Not a network error → reset counter
        self._state.failure_count = 0
        return None

    def _trip(self, task_id: str, reason: str) -> None:
        """Open the circuit breaker and trigger rollback."""
        self._state.is_open = True
        self._state.open_since = time.time()
        logger.error("Circuit breaker TRIPPED for %s: %s", task_id, reason)

        # Rollback plan state
        self._plan_state.rollback_running_to_exception(task_id, reason)

        # Send QQ notification if callback available
        if self._notify:
            try:
                self._notify(f"⚠️ 异常熔断：{reason}\n任务 ID：{task_id}")
            except Exception as exc:
                logger.error("Failed to send breaker notification: %s", exc)
