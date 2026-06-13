from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str = ""


class NotificationLimiter:
    def __init__(
        self,
        *,
        stage_cooldown_seconds: int,
        failure_cooldown_seconds: int,
        min_interval_seconds: int,
        max_per_10_minutes: int,
        max_per_hour: int,
        session_budget: int,
        start_dedupe_seconds: int,
        stop_dedupe_seconds: int,
        success_mode: str,
    ) -> None:
        self.stage_cooldown_seconds = stage_cooldown_seconds
        self.failure_cooldown_seconds = failure_cooldown_seconds
        self.min_interval_seconds = min_interval_seconds
        self.max_per_10_minutes = max_per_10_minutes
        self.max_per_hour = max_per_hour
        self.session_budget = session_budget
        self.start_dedupe_seconds = start_dedupe_seconds
        self.stop_dedupe_seconds = stop_dedupe_seconds
        self.success_mode = success_mode

    def should_send_start(self, state: dict[str, Any], now: float) -> RateLimitDecision:
        last = float(state.get("start_sent_at", 0) or 0)
        if last and now - last < self.start_dedupe_seconds:
            return RateLimitDecision(False, "start-dedupe")
        return self._budget_decision(state)

    def should_send_stage(self, state: dict[str, Any], stage: str, now: float) -> RateLimitDecision:
        if not self._budget_decision(state).allowed:
            return RateLimitDecision(False, "session-budget")
        last_stage = str(state.get("last_notified_stage") or "")
        last_at = float(state.get("last_stage_at", 0) or 0)
        if stage == last_stage and now - last_at < self.stage_cooldown_seconds:
            return RateLimitDecision(False, "stage-cooldown")
        return RateLimitDecision(True)

    def should_send_success(self, state: dict[str, Any], kind: str, now: float) -> RateLimitDecision:
        if self.success_mode == "off":
            return RateLimitDecision(False, "success-off")
        if self.success_mode == "important" and kind not in {"test", "git-push", "git-commit", "docker-deploy", "docker-build"}:
            return RateLimitDecision(False, "success-not-important")
        return self._budget_decision(state)

    def should_send_failure(self, state: dict[str, Any], failure_hash: str, now: float) -> RateLimitDecision:
        last_hash = str(state.get("last_failure_hash") or "")
        last_at = float(state.get("last_failure_at", 0) or 0)
        if failure_hash == last_hash and now - last_at < self.failure_cooldown_seconds:
            return RateLimitDecision(False, "failure-cooldown")
        return RateLimitDecision(True)

    def should_send_stop(self, state: dict[str, Any], now: float) -> RateLimitDecision:
        last = float(state.get("stop_sent_at", 0) or 0)
        if state.get("done") and last:
            return RateLimitDecision(False, "already-done")
        if last and now - last < self.stop_dedupe_seconds:
            return RateLimitDecision(False, "stop-dedupe")
        return RateLimitDecision(True)

    def should_send_global(self, global_state: dict[str, Any], recipient_id: int, now: float) -> RateLimitDecision:
        key = str(recipient_id)
        recipients = global_state.setdefault("recipients", {})
        history = recipients.setdefault(key, [])
        history[:] = [float(item) for item in history if now - float(item) <= 3600]
        if history and now - history[-1] < self.min_interval_seconds:
            return RateLimitDecision(False, "global-min-interval")
        if len([item for item in history if now - item <= 600]) >= self.max_per_10_minutes:
            return RateLimitDecision(False, "global-10min-budget")
        if len(history) >= self.max_per_hour:
            return RateLimitDecision(False, "global-hour-budget")
        return RateLimitDecision(True)

    def record_global_send(self, global_state: dict[str, Any], recipient_id: int, now: float) -> None:
        key = str(recipient_id)
        recipients = global_state.setdefault("recipients", {})
        history = recipients.setdefault(key, [])
        history.append(now)
        history[:] = [float(item) for item in history if now - float(item) <= 3600]

    def _budget_decision(self, state: dict[str, Any]) -> RateLimitDecision:
        if int(state.get("sent_count", 0) or 0) >= self.session_budget:
            return RateLimitDecision(False, "session-budget")
        return RateLimitDecision(True)
