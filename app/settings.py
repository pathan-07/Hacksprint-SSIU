from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="dev", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # WhatsApp Cloud API
    enable_whatsapp: bool = Field(default=False, alias="ENABLE_WHATSAPP")
    whatsapp_verify_token: str | None = Field(default=None, alias="WHATSAPP_VERIFY_TOKEN")
    whatsapp_token: str | None = Field(default=None, alias="WHATSAPP_TOKEN")
    whatsapp_phone_number_id: str | None = Field(default=None, alias="WHATSAPP_PHONE_NUMBER_ID")
    meta_graph_version: str = Field(default="v19.0", alias="META_GRAPH_VERSION")

    # Optional (recommended) signature validation
    whatsapp_app_secret: str | None = Field(default=None, alias="WHATSAPP_APP_SECRET")

    # Supabase
    supabase_url: str | None = Field(default=None, alias="SUPABASE_URL")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")

    # Gemini
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_transcribe_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_TRANSCRIBE_MODEL")
    gemini_intent_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_INTENT_MODEL")

    # Product behavior
    pending_action_ttl_seconds: int = Field(default=600, alias="PENDING_ACTION_TTL_SECONDS")
    confidence_threshold: float = Field(default=0.7, alias="CONFIDENCE_THRESHOLD")
    auto_confirm_threshold: float = Field(default=0.9, alias="AUTO_CONFIRM_THRESHOLD")

    # Dev/test mode
    test_mode: bool = Field(default=False, alias="TEST_MODE")


settings = Settings()


def require_secrets() -> None:
    missing: list[str] = []
    if settings.enable_whatsapp:
        if not settings.whatsapp_verify_token:
            missing.append("WHATSAPP_VERIFY_TOKEN")
        if not settings.whatsapp_token:
            missing.append("WHATSAPP_TOKEN")
        if not settings.whatsapp_phone_number_id:
            missing.append("WHATSAPP_PHONE_NUMBER_ID")
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_service_role_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if not settings.gemini_api_key:
        missing.append("GEMINI_API_KEY")

    if missing:
        raise RuntimeError("Missing required env vars: " + ", ".join(missing))
