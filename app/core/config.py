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
    sheets_hook_key: str = ""  # segredo pro webhook onEdit da planilha

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

    # Disparos
    disparos_delay_seconds: int = 3  # gap curto: "digitando" + texto→contato
    # Intervalo aleatório ENTRE pessoas (anti-ban). Default 3–5 min.
    disparos_intervalo_min_seconds: int = 180
    disparos_intervalo_max_seconds: int = 300
    # Janela de envio (Brasília): pausa fora dela (protege a madrugada).
    # Todos os dias, das 8h às 21h. Retoma sozinho na próxima abertura.
    disparos_janela_inicio_hora: int = 8
    disparos_janela_fim_hora: int = 21
    disparos_business_hours_enabled: bool = False  # regra antiga desativada
    disparos_max_file_mb: int = 16
    disparos_drive_folder: str = ""

    # Auth do painel
    painel_jwt_secret: str = "change-me-in-prod"
    painel_jwt_expire_hours: int = 12
    painel_default_admin_user: str = "admin"
    painel_default_admin_pass: str = ""

    # Misc
    dry_run: bool = False
    log_level: str = "INFO"


    # ── Workers PAES ──
    drive_video_boas_vindas: str = ""
    cultos_dominicais_meses_a_frente: int = 3

    # ── Migração Supabase (one-shot) ──
    supabase_url: str = ""
    supabase_key: str = ""

    # ── n8n Google Proxy ──
    # Quando setado, sheets/drive/gmail clients usam o webhook n8n
    # em vez de chamar Google APIs diretamente (não precisa de SA local).
    n8n_google_webhook_url: str = ""
    n8n_google_token: str = ""
    n8n_google_timeout_seconds: int = 30

    # ── Diacon API ──
    diacon_base_url: str = ""
    diacon_token: str = ""
    diacon_timeout_seconds: int = 30

    @property
    def admin_phones_list(self) -> list[str]:
        if not self.admin_phones:
            return []
        return [p.strip() for p in self.admin_phones.split(",") if p.strip()]


settings = Settings()
