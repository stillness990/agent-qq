"""Plan state machine with JSON persistence.

Commands:
  /plan <description>  → AI returns outline only, saves pending_plan.json, status=PENDING
  /plan-status         → read pending_plan.json, return content
  /plan-start          → confirm and execute pending plan → mark EXECUTED, archive
  /plan-cancel         → discard pending plan → mark CANCELLED, archive
  /plan-log            → read plan_history.json, return log with status markers
"""

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from config import Settings

logger = logging.getLogger(__name__)

PlanStatus = Literal["PENDING", "EXECUTED", "CANCELLED", "EXCEPTION"]


@dataclass
class PlanRecord:
    id: str
    description: str
    outline: str = ""
    status: PlanStatus = "PENDING"
    user_id: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    result: str = ""


class PlanStateMachine:
    """Manages the /plan lifecycle with JSON file persistence."""

    def __init__(self, settings: Settings) -> None:
        self._data_dir = settings.plan_data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._history_max = settings.plan_history_max
        self._pending_path = self._data_dir / "pending_plan.json"
        self._history_path = self._data_dir / "plan_history.json"
        self._counter = int(time.time() * 1000)  # ms timestamp as seed

    # ------------------------------------------------------------------
    # /plan  — create a pending plan (AI outline only, no execution)
    # ------------------------------------------------------------------
    def create_pending(self, description: str, outline: str, user_id: int) -> PlanRecord:
        if self.has_pending():
            raise PendingPlanExistsError("已有待确认的计划，请先 /plan-start 或 /plan-cancel")

        self._counter += 1
        now = time.time()
        record = PlanRecord(
            id=f"plan_{self._counter}",
            description=description,
            outline=outline,
            status="PENDING",
            user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        self._write_pending(record)
        logger.info("Plan created: %s", record.id)
        return record

    # ------------------------------------------------------------------
    # /plan-status — read pending plan
    # ------------------------------------------------------------------
    def read_pending(self) -> PlanRecord | None:
        if not self._pending_path.exists():
            return None
        try:
            data = json.loads(self._pending_path.read_text(encoding="utf-8"))
            return PlanRecord(**data)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Failed to read pending plan: %s", exc)
            return None

    def has_pending(self) -> bool:
        return self.read_pending() is not None

    # ------------------------------------------------------------------
    # /plan-start — confirm and mark for execution
    # ------------------------------------------------------------------
    def confirm_pending(self) -> PlanRecord:
        record = self.read_pending()
        if record is None:
            raise NoPendingPlanError("没有待确认的计划。请先 /plan 创建。")
        record.status = "EXECUTED"
        record.updated_at = time.time()
        self._archive(record)
        self._delete_pending()
        logger.info("Plan confirmed: %s", record.id)
        return record

    # ------------------------------------------------------------------
    # /plan-cancel — discard pending plan
    # ------------------------------------------------------------------
    def cancel_pending(self) -> PlanRecord:
        record = self.read_pending()
        if record is None:
            raise NoPendingPlanError("没有待确认的计划。请先 /plan 创建。")
        record.status = "CANCELLED"
        record.updated_at = time.time()
        self._archive(record)
        self._delete_pending()
        logger.info("Plan cancelled: %s", record.id)
        return record

    # ------------------------------------------------------------------
    # Exception rollback — called by circuit breaker
    # ------------------------------------------------------------------
    def rollback_running_to_exception(self, plan_id: str, reason: str) -> PlanRecord | None:
        """Mark a running plan as EXCEPTION and archive it."""
        now = time.time()
        record = PlanRecord(
            id=plan_id,
            description=f"异常任务 (原ID: {plan_id})",
            outline="",
            status="EXCEPTION",
            user_id=0,
            created_at=now,
            updated_at=now,
            result=reason,
        )
        self._archive(record)
        logger.warning("Plan rolled back to EXCEPTION: %s — %s", plan_id, reason)
        return record

    # ------------------------------------------------------------------
    # /plan-log — read history
    # ------------------------------------------------------------------
    def read_history(self, limit: int = 20) -> list[PlanRecord]:
        entries = self._read_history_file()
        entries.reverse()  # newest first
        return entries[:limit]

    # ------------------------------------------------------------------
    # Mark an executed plan's result after AI completes
    # ------------------------------------------------------------------
    def update_executed_result(self, plan_id: str, result: str) -> None:
        entries = self._read_history_file()
        for entry in entries:
            if entry.get("id") == plan_id:
                entry["result"] = result
                entry["updated_at"] = time.time()
                self._write_history_file(entries)
                return
        logger.warning("Plan %s not found in history for result update", plan_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _write_pending(self, record: PlanRecord) -> None:
        self._pending_path.write_text(
            json.dumps(self._record_to_dict(record), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _delete_pending(self) -> None:
        try:
            self._pending_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _archive(self, record: PlanRecord) -> None:
        entries = self._read_history_file()
        entries.append(self._record_to_dict(record))
        self._write_history_file(entries)

    def _read_history_file(self) -> list[dict]:
        if not self._history_path.exists():
            return []
        try:
            return json.loads(self._history_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read plan history: %s", exc)
            return []

    def _write_history_file(self, entries: list[dict]) -> None:
        # Rotate if exceeds max
        if len(entries) > self._history_max:
            entries = entries[-self._history_max :]
        self._history_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _record_to_dict(record: PlanRecord) -> dict:
        return {
            "id": record.id,
            "description": record.description,
            "outline": record.outline,
            "status": record.status,
            "user_id": record.user_id,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "result": record.result,
        }


# ------------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------------
class PlanError(Exception):
    """Base error for plan state machine."""


class PendingPlanExistsError(PlanError):
    """A pending plan already exists."""


class NoPendingPlanError(PlanError):
    """No pending plan to act on."""
