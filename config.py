from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    onebot_ws_url: str = Field(default="ws://127.0.0.1:3001", alias="ONEBOT_WS_URL")
    onebot_access_token: str = Field(default="", alias="ONEBOT_ACCESS_TOKEN")
    enable_private_chat: bool = Field(default=True, alias="ENABLE_PRIVATE_CHAT")
    admin_qq_ids: Annotated[set[int], NoDecode] = Field(default_factory=set, alias="ADMIN_QQ_IDS")

    claude_cli_command: str = Field(default="claude", alias="CLAUDE_CLI_COMMAND")
    claude_timeout_seconds: int = Field(default=180, alias="CLAUDE_TIMEOUT_SECONDS")
    claude_workdir: Path = Field(default=Path("/workspace"), alias="CLAUDE_WORKDIR")

    enable_shell_command: bool = Field(default=False, alias="ENABLE_SHELL_COMMAND")
    shell_allowed_prefixes: Annotated[tuple[str, ...], NoDecode] = Field(default=("pwd", "ls"), alias="SHELL_ALLOWED_PREFIXES")

    message_dedupe_ttl_seconds: int = Field(default=300, alias="MESSAGE_DEDUPE_TTL_SECONDS")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO", alias="LOG_LEVEL")
    reconnect_initial_seconds: int = Field(default=2, alias="RECONNECT_INITIAL_SECONDS")
    reconnect_max_seconds: int = Field(default=60, alias="RECONNECT_MAX_SECONDS")
    qq_reply_chunk_size: int = Field(default=1800, alias="QQ_REPLY_CHUNK_SIZE")

    claude_notify_enabled: bool = Field(default=True, alias="CLAUDE_NOTIFY_ENABLED")
    claude_notify_qq_ids: Annotated[set[int], NoDecode] = Field(default_factory=set, alias="CLAUDE_NOTIFY_QQ_IDS")
    claude_notify_prefix: str = Field(default="【Claude】", alias="CLAUDE_NOTIFY_PREFIX")
    claude_notify_state_dir: Path = Field(default=Path("data/notify-state"), alias="CLAUDE_NOTIFY_STATE_DIR")
    claude_notify_message_max_len: int = Field(default=180, alias="CLAUDE_NOTIFY_MESSAGE_MAX_LEN")
    claude_notify_stage_cooldown_seconds: int = Field(default=60, alias="CLAUDE_NOTIFY_STAGE_COOLDOWN_SECONDS")
    claude_notify_success_mode: Literal["off", "important", "all"] = Field(default="important", alias="CLAUDE_NOTIFY_SUCCESS_MODE")
    claude_notify_failure_cooldown_seconds: int = Field(default=180, alias="CLAUDE_NOTIFY_FAILURE_COOLDOWN_SECONDS")
    claude_notify_min_interval_seconds: int = Field(default=8, alias="CLAUDE_NOTIFY_MIN_INTERVAL_SECONDS")
    claude_notify_max_per_10_minutes: int = Field(default=20, alias="CLAUDE_NOTIFY_MAX_PER_10_MINUTES")
    claude_notify_max_per_hour: int = Field(default=60, alias="CLAUDE_NOTIFY_MAX_PER_HOUR")
    claude_notify_session_budget: int = Field(default=25, alias="CLAUDE_NOTIFY_SESSION_BUDGET")
    claude_notify_start_dedupe_seconds: int = Field(default=30, alias="CLAUDE_NOTIFY_START_DEDUPE_SECONDS")
    claude_notify_stop_dedupe_seconds: int = Field(default=30, alias="CLAUDE_NOTIFY_STOP_DEDUPE_SECONDS")
    claude_notify_long_task_seconds: int = Field(default=600, alias="CLAUDE_NOTIFY_LONG_TASK_SECONDS")
    claude_notify_heartbeat_seconds: int = Field(default=300, alias="CLAUDE_NOTIFY_HEARTBEAT_SECONDS")
    claude_notify_monitor_interval_seconds: int = Field(default=30, alias="CLAUDE_NOTIFY_MONITOR_INTERVAL_SECONDS")
    claude_notify_monitor_lock_ttl_seconds: int = Field(default=120, alias="CLAUDE_NOTIFY_MONITOR_LOCK_TTL_SECONDS")
    claude_notify_state_ttl_seconds: int = Field(default=86400, alias="CLAUDE_NOTIFY_STATE_TTL_SECONDS")
    claude_notify_allowed_cwd_prefixes: Annotated[tuple[str, ...], NoDecode] = Field(default=(), alias="CLAUDE_NOTIFY_ALLOWED_CWD_PREFIXES")

    # --- Plan state machine ---
    plan_history_max: int = Field(default=50, alias="PLAN_HISTORY_MAX")
    plan_data_dir: Path = Field(default=Path("data"), alias="PLAN_DATA_DIR")
    plan_status_log_max_age_hours: int = Field(default=24, alias="PLAN_STATUS_LOG_MAX_AGE_HOURS")

    # --- Circuit breaker ---
    circuit_breaker_enabled: bool = Field(default=True, alias="CIRCUIT_BREAKER_ENABLED")
    circuit_breaker_max_retries: int = Field(default=3, alias="CIRCUIT_BREAKER_MAX_RETRIES")
    circuit_breaker_task_timeout_minutes: int = Field(default=30, alias="CIRCUIT_BREAKER_TASK_TIMEOUT_MINUTES")

    # --- Weather push ---
    weather_push_script: Path = Field(
        default=Path("/path/to/weather_wechat_push/weather_wechat_push.py"),
        alias="WEATHER_PUSH_SCRIPT",
    )

    # --- Background monitor ---
    monitor_enabled: bool = Field(default=True, alias="MONITOR_ENABLED")
    monitor_poll_interval_seconds: int = Field(default=5, alias="MONITOR_POLL_INTERVAL_SECONDS")
    monitor_network_test_hosts: Annotated[tuple[str, ...], NoDecode] = Field(default=("github.com", "api.anthropic.com", "baidu.com"), alias="MONITOR_NETWORK_TEST_HOSTS")

    @field_validator("admin_qq_ids", "claude_notify_qq_ids", mode="before")
    @classmethod
    def parse_admin_qq_ids(cls, value: object) -> set[int]:
        if value is None or value == "":
            return set()
        if isinstance(value, set):
            return {int(item) for item in value}
        if isinstance(value, str):
            return {int(item.strip()) for item in value.split(",") if item.strip()}
        if isinstance(value, list | tuple):
            return {int(item) for item in value}
        raise TypeError("ADMIN_QQ_IDS must be a comma separated string")

    @field_validator("shell_allowed_prefixes", "claude_notify_allowed_cwd_prefixes", mode="before")
    @classmethod
    def parse_comma_separated_tuple(cls, value: object) -> tuple[str, ...]:
        if value is None or value == "":
            return tuple()
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        if isinstance(value, list | tuple):
            return tuple(str(item).strip() for item in value if str(item).strip())
        raise TypeError("value must be a comma separated string")

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_qq_ids

    def notification_recipients(self) -> set[int]:
        return self.claude_notify_qq_ids or self.admin_qq_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()
