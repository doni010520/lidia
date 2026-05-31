from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Identidade
    agent_name: str = "LidIA"
    env: str = "production"
    debug: bool = False

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_temperature: float = 0.5
    openai_max_tokens: int = 2000
    openai_embedding_model: str = "text-embedding-3-small"

    # uazapi v2
    uaz_base_url: str = ""
    uaz_token: str = ""
    uaz_webhook_secret: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://lidia:lidia_secret@db:5432/lidia"
    redis_url: str = "redis://redis:6379/0"
    redis_buffer_seconds: int = 10

    # Conversa
    history_limit: int = 40
    rag_enabled: bool = True
    rag_top_k: int = 7

    # Google Drive / Sheets
    google_service_account_json: str = "/app/secrets/google-sa.json"
    drive_folder_documents: str = ""
    drive_folder_media: str = ""
    sheets_eventos_id: str = ""
    sheets_informacoes_id: str = ""
    sheets_plano_leitura_id: str = ""
    sheets_log_notificacoes_id: str = ""
    sheets_log_oracao_id: str = ""

    # Gmail
    gmail_from: str = "lidia@paes.org.br"
    gmail_service_account_json: str = "/app/secrets/gmail-sa.json"

    # Admin
    admin_phones: str = ""

    # Handoff
    handoff_pause_minutes: int = 30
    handoff_keyword_off: str = "Roberta aqui!"
    handoff_keyword_on: str = "té mais!"

    # Workers
    training_schedule_cron: str = "0 3 * * *"
    sheets_sync_interval_minutes: int = 15

    # Misc
    dry_run: bool = False
    log_level: str = "INFO"

    @property
    def admin_phones_list(self) -> list[str]:
        if not self.admin_phones:
            return []
        return [p.strip() for p in self.admin_phones.split(",") if p.strip()]


settings = Settings()
