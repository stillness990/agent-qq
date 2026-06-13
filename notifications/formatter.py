import hashlib
from pathlib import Path
from typing import Any


IMPORTANT_SUCCESS_KINDS = {"test", "git-push", "git-commit", "docker-deploy", "docker-build"}


def trim_message(message: str, max_len: int) -> str:
    message = " ".join(str(message).replace("\n", " ").split())
    if len(message) > max_len:
        return message[: max_len - 1] + "…"
    return message


def summarize_prompt(prompt: str | None, max_len: int = 60) -> str:
    text = trim_message(prompt or "", max_len)
    return text or "未命名任务"


def file_hint(tool_input: dict[str, Any]) -> str:
    for key in ("file_path", "path", "notebook_path"):
        value = tool_input.get(key)
        if value:
            return Path(str(value)).name
    return ""


def classify_stage(tool_name: str | None, tool_input: dict[str, Any]) -> tuple[str, str]:
    tool = tool_name or ""
    command = str(tool_input.get("command", ""))
    lowered = command.lower()

    if tool in {"Read", "Glob", "Grep"}:
        hint = file_hint(tool_input)
        return (f"正在分析资料：{hint}" if hint else "正在分析资料", "read")
    if tool in {"WebFetch", "WebSearch"}:
        return "正在搜索资料", "web"
    if tool in {"Write", "Edit", "NotebookEdit"}:
        hint = file_hint(tool_input)
        return (f"正在修改文件：{hint}" if hint else "正在修改文件", "write")
    if tool == "Bash":
        return classify_bash(lowered)
    if tool in {"Agent", "Workflow"}:
        return "正在调度 Agent 任务", "agent"
    if tool in {"TaskCreate", "TaskUpdate"}:
        return "正在整理任务进度", "task"
    if tool in {"AskUserQuestion", "EnterPlanMode", "ExitPlanMode"}:
        return "正在分析需求", "plan"
    return f"正在使用 {tool or '工具'}", tool or "tool"


def classify_bash(command: str) -> tuple[str, str]:
    if any(word in command for word in ("pytest", "npm test", "pnpm test", "yarn test", "cargo test", "go test", "python -m pytest")):
        return "正在运行测试", "test"
    if "git push" in command or "gh repo" in command or "gh pr" in command:
        return "正在推送代码", "git-push"
    if "git commit" in command:
        return "正在提交变更", "git-commit"
    if any(word in command for word in ("git status", "git diff", "git log", "git branch")):
        return "正在检查 Git 状态", "git-check"
    if "docker compose up" in command or "docker compose restart" in command:
        return "正在部署服务", "docker-deploy"
    if "docker compose build" in command or "docker build" in command:
        return "正在构建镜像", "docker-build"
    if any(word in command for word in ("pip install", "uv pip install", "npm install", "pnpm install", "yarn install")):
        return "正在安装依赖", "install"
    if command.startswith(("find ", "grep ", "rg ")):
        return "正在扫描文件", "scan"
    if command.startswith(("cp ", "mv ", "rsync ")):
        return "正在同步文件", "file-sync"
    if command.startswith(("python ", "python3 ", "node ", "bash ")):
        return "正在运行脚本", "script"
    return "正在执行命令", "bash"


def extract_failure_reason(tool_name: str | None, tool_response: Any, max_len: int) -> str:
    reason = ""
    if isinstance(tool_response, dict):
        reason = str(
            tool_response.get("error")
            or tool_response.get("stderr")
            or tool_response.get("message")
            or tool_response.get("output")
            or ""
        )
    elif tool_response is not None:
        reason = str(tool_response)
    if not reason:
        reason = f"{tool_name or '工具'} 执行失败"
    return trim_message(reason, max_len)


def failure_hash(tool_name: str | None, reason: str) -> str:
    raw = f"{tool_name or ''}:{reason}".encode("utf-8", "ignore")
    return hashlib.sha256(raw).hexdigest()[:16]


def format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}时{minutes}分{sec}秒"
    if minutes:
        return f"{minutes}分{sec}秒"
    return f"{sec}秒"


def format_start(prefix: str, title: str) -> str:
    return f"{prefix}开始：{title}"


def format_stage(prefix: str, stage: str) -> str:
    return f"{prefix}阶段：{stage}"


def format_success(prefix: str, stage: str) -> str:
    return f"{prefix}完成：{stage}"


def format_failure(prefix: str, reason: str) -> str:
    return f"{prefix}失败：{reason}"


def format_heartbeat(prefix: str, state: dict[str, Any], now: float) -> str:
    elapsed = format_elapsed(now - float(state.get("started_at", now) or now))
    stage = str(state.get("last_stage") or "持续执行中")
    tools = int(state.get("tool_count", 0) or 0)
    failures = int(state.get("failure_count", 0) or 0)
    return f"{prefix}仍在执行 {elapsed}：{stage}；工具 {tools} 次，失败 {failures} 次"


def format_stop(prefix: str, state: dict[str, Any], now: float) -> str:
    elapsed = format_elapsed(now - float(state.get("started_at", now) or now))
    tools = int(state.get("tool_count", 0) or 0)
    success = int(state.get("success_count", 0) or 0)
    failures = int(state.get("failure_count", 0) or 0)
    suppressed = int(state.get("suppressed_count", 0) or 0)
    recent = state.get("recent_stages") if isinstance(state.get("recent_stages"), list) else []
    flow = " → ".join(str(item) for item in recent[-5:])
    message = f"{prefix}本轮完成，用时 {elapsed}；工具 {tools} 次，成功 {success}，失败 {failures}"
    if flow:
        message += f"；流程：{flow}"
    if suppressed:
        message += f"；已合并 {suppressed} 条高频通知"
    return message
