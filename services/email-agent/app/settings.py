"""Application configuration: non-secret settings from config.yaml, secrets from .env."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent


class MailSettings(BaseModel):
    provider: str = "graph"  # graph|mail|fake
    mailbox_upn: str = ""
    poll_interval_seconds: float = 30.0
    move_to_folder: Optional[str] = None
    max_body_chars_to_llm: int = 4000


class AuthorisationSettings(BaseModel):
    require_auth_pass: bool = True
    group_owners: dict[str, int] = Field(default_factory=dict)

    @field_validator("group_owners", mode="before")
    @classmethod
    def _lowercase_keys(cls, v: dict) -> dict:
        return {str(k).strip().lower(): int(val) for k, val in (v or {}).items()}


class LlmSettings(BaseModel):
    provider: str = "ollama"
    host: str = "http://localhost:11434"
    model: str = "qwen2.5:14b"
    request_timeout_seconds: float = 60.0
    max_parse_retries: int = 2


class BackendSettings(BaseModel):
    base_url: str = "http://localhost:8000"
    request_timeout_seconds: float = 10.0
    max_retry_attempts: int = 3
    retry_backoff_seconds: float = 1.0


class GithubRaginatorSettings(BaseModel):
    base_url: str = "http://localhost:8010"
    # /query does retrieval + a full LLM generation over the repo's activity - measured at
    # 200s+ on CPU against a repo with an unusually large issue history. Raise further for a
    # bigger/slower local model or an especially active repo.
    request_timeout_seconds: float = 120.0
    max_retry_attempts: int = 3
    retry_backoff_seconds: float = 1.0


class LimitsSettings(BaseModel):
    max_attachment_size_mb: float = 20.0
    allowed_attachment_extensions: list[str] = Field(default_factory=lambda: [".vtt"])
    max_email_body_chars: int = 20000


class StorageSettings(BaseModel):
    incoming: Path = REPO_ROOT / "data" / "incoming"
    processing: Path = REPO_ROOT / "data" / "processing"
    completed: Path = REPO_ROOT / "data" / "completed"
    failed: Path = REPO_ROOT / "data" / "failed"
    db_path: Path = REPO_ROOT / "data" / "app.db"
    default_timezone: str = "UTC"


class AdminSettings(BaseModel):
    alert_cooldown_minutes: float = 15.0


class InternalApiSettings(BaseModel):
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8080
    max_body_chars: int = 20000


class WeeklyUpdateSettings(BaseModel):
    enabled: bool = False
    weekday: int = 0
    hour: int = 8
    minute: int = 0
    lookback_days: int = 7
    recipient_mode: str = "group_owners"


class LoggingSettings(BaseModel):
    level: str = "INFO"
    log_email_bodies: bool = False
    log_dir: Path = REPO_ROOT / "data" / "logs"


class Settings(BaseModel):
    mail: MailSettings = Field(default_factory=MailSettings)
    authorisation: AuthorisationSettings = Field(default_factory=AuthorisationSettings)
    llm: LlmSettings = Field(default_factory=LlmSettings)
    backend: BackendSettings = Field(default_factory=BackendSettings)
    github_raginator: GithubRaginatorSettings = Field(default_factory=GithubRaginatorSettings)
    limits: LimitsSettings = Field(default_factory=LimitsSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    admin: AdminSettings = Field(default_factory=AdminSettings)
    internal_api: InternalApiSettings = Field(default_factory=InternalApiSettings)
    weekly_update: WeeklyUpdateSettings = Field(default_factory=WeeklyUpdateSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    # secrets, from environment / .env only - never from the yaml file
    admin_email: Optional[str] = None
    authorised_email_domains: list[str] = Field(default_factory=list)
    mail_username: Optional[str] = None
    mail_password: Optional[str] = None
    graph_tenant_id: Optional[str] = None
    graph_client_id: Optional[str] = None
    graph_client_secret: Optional[str] = None
    diarisation_service_api_key: Optional[str] = None
    email_api_token: Optional[str] = None

    def ensure_storage_dirs(self) -> None:
        for d in (
            self.storage.incoming,
            self.storage.processing,
            self.storage.completed,
            self.storage.failed,
            self.logging.log_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)


def load_settings(
    config_path: Optional[Path] = None,
    env_path: Optional[Path] = None,
) -> Settings:
    """Load YAML config (non-secret) merged with environment variables (secrets)."""
    load_dotenv(env_path or REPO_ROOT / ".env")

    config_path = config_path or REPO_ROOT / "config" / "config.yaml"
    if not config_path.exists():
        config_path = REPO_ROOT / "config" / "config.example.yaml"

    raw: dict = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

    settings = Settings.model_validate(raw)

    settings.admin_email = os.getenv("ADMIN_EMAIL") or settings.admin_email
    domains = os.getenv("AUTHORISED_EMAIL_DOMAINS")
    if domains:
        settings.authorised_email_domains = [
            d.strip().lower() for d in domains.split(",") if d.strip()
        ]
    settings.mail_username = os.getenv("MAIL_USERNAME") or settings.mail_username
    settings.mail_password = os.getenv("MAIL_PASSWORD") or settings.mail_password
    settings.graph_tenant_id = os.getenv("GRAPH_TENANT_ID") or settings.graph_tenant_id
    settings.graph_client_id = os.getenv("GRAPH_CLIENT_ID") or settings.graph_client_id
    settings.graph_client_secret = os.getenv("GRAPH_CLIENT_SECRET") or settings.graph_client_secret
    settings.diarisation_service_api_key = (
        os.getenv("DIARISATION_SERVICE_API_KEY") or settings.diarisation_service_api_key
    )
    settings.email_api_token = os.getenv("EMAIL_API_TOKEN") or settings.email_api_token

    return settings
