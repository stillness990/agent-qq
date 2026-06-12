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

    @field_validator("admin_qq_ids", mode="before")
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

    @field_validator("shell_allowed_prefixes", mode="before")
    @classmethod
    def parse_shell_allowed_prefixes(cls, value: object) -> tuple[str, ...]:
        if value is None or value == "":
            return tuple()
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        if isinstance(value, list | tuple):
            return tuple(str(item).strip() for item in value if str(item).strip())
        raise TypeError("SHELL_ALLOWED_PREFIXES must be a comma separated string")

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_qq_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()
