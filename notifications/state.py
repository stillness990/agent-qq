import json
import os
import time
from pathlib import Path
from typing import Any


class NotificationStateStore:
    def __init__(self, state_dir: Path, ttl_seconds: int = 86400) -> None:
        self.state_dir = state_dir
        self.ttl_seconds = ttl_seconds

    def ensure_dir(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def session_path(self, session_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in session_id)[:120]
        return self.state_dir / f"{safe or 'default'}.json"

    def global_path(self) -> Path:
        return self.state_dir / "global.json"

    def read_session(self, session_id: str) -> dict[str, Any]:
        return self._read_json(self.session_path(session_id))

    def write_session(self, session_id: str, state: dict[str, Any]) -> None:
        self._write_json(self.session_path(session_id), state)

    def read_global(self) -> dict[str, Any]:
        return self._read_json(self.global_path())

    def write_global(self, state: dict[str, Any]) -> None:
        self._write_json(self.global_path(), state)

    def cleanup_expired(self, now: float | None = None) -> int:
        now = now or time.time()
        self.ensure_dir()
        removed = 0
        for path in self.state_dir.glob("*.json"):
            if path.name == "global.json":
                continue
            state = self._read_json(path)
            updated_at = float(state.get("updated_at", path.stat().st_mtime) or 0)
            if now - updated_at > self.ttl_seconds:
                path.unlink(missing_ok=True)
                removed += 1
        for path in self.state_dir.glob("*.lock"):
            try:
                if now - path.stat().st_mtime > self.ttl_seconds:
                    path.unlink(missing_ok=True)
                    removed += 1
            except FileNotFoundError:
                continue
        return removed

    def acquire_monitor_lock(self, session_id: str, ttl_seconds: int, now: float | None = None) -> bool:
        now = now or time.time()
        self.ensure_dir()
        lock = self.session_path(session_id).with_suffix(".lock")
        if lock.exists():
            try:
                data = self._read_json(lock)
                updated_at = float(data.get("updated_at", lock.stat().st_mtime) or 0)
                if now - updated_at <= ttl_seconds:
                    return False
            except Exception:
                pass
            lock.unlink(missing_ok=True)
        self._write_json(lock, {"pid": os.getpid(), "updated_at": now})
        return True

    def refresh_monitor_lock(self, session_id: str, now: float | None = None) -> None:
        lock = self.session_path(session_id).with_suffix(".lock")
        self._write_json(lock, {"pid": os.getpid(), "updated_at": now or time.time()})

    def release_monitor_lock(self, session_id: str) -> None:
        self.session_path(session_id).with_suffix(".lock").unlink(missing_ok=True)

    def _read_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        self.ensure_dir()
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
