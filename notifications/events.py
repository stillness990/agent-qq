import json
import sys
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ClaudeHookEvent:
    command: str
    session_id: str
    cwd: str | None = None
    transcript_path: str | None = None
    prompt: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_response: Any = None
    raw: dict[str, Any] = field(default_factory=dict)


def read_stdin_json() -> dict[str, Any]:
    try:
        text = sys.stdin.read()
        if not text.strip():
            return {}
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def parse_hook_event(command: str, payload: dict[str, Any]) -> ClaudeHookEvent:
    tool_input = payload.get("tool_input")
    return ClaudeHookEvent(
        command=command,
        session_id=str(payload.get("session_id") or "default"),
        cwd=str(payload.get("cwd") or payload.get("workspace", {}).get("current_dir") or "") or None,
        transcript_path=str(payload.get("transcript_path") or "") or None,
        prompt=str(payload.get("prompt") or payload.get("user_prompt") or payload.get("message") or "") or None,
        tool_name=str(payload.get("tool_name") or "") or None,
        tool_input=tool_input if isinstance(tool_input, dict) else {},
        tool_response=payload.get("tool_response") or payload.get("error"),
        raw=payload,
    )
