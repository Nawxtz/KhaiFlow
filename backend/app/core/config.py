from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/app_dev"

    # Shop & Tenancy
    DEFAULT_SHOP_ID: str | None = "default"

    # Google Sheets Integration (Phase 1)
    GOOGLE_SERVICE_ACCOUNT_JSON_PATH: str | None = None
    GOOGLE_SHEET_ID: str | None = None
    GOOGLE_SHEET_INVENTORY_RANGE: str = "Inventory!A1:G"

    # Ingest & Sync (reference_settings.md)
    SHEET_SYNC_INTERVAL_SECONDS: int = 60
    SHEET_INGEST_SELLER_OVERRIDE: bool = True
    CACHE_TTL_SECONDS: int = 60

    # Placeholders for future phases per reference_settings.md
    LINE_CHANNEL_ACCESS_TOKEN: str | None = None
    LINE_CHANNEL_SECRET: str | None = None
    OPENROUTER_API_KEY: str | None = None

    # LLM Settings (reference_settings.md)
    LLM_ENABLED: bool = True
    LLM_MODEL_MAIN: str = "gemini/gemini-flash"
    LLM_MODEL_BACKUP: str = "openai/gpt-4o-mini"
    LLM_ESCALATE_CONFIDENCE: float = 0.8

    # UX Settings (reference_settings.md)
    CAROUSEL_PAGE_SIZE: int = 8
    ADDRESS_BOOK_ENABLED: bool = True
    UI_DEFAULT_BUYER_LANGUAGE: str = "th"
    UI_BUYER_LANGUAGE_SELECTABLE: bool = True
    UI_DEFAULT_PORTAL_LANGUAGE: str = "en"
    UI_DEFAULT_THEME: str = "system"
    UI_THEME_SELECTABLE: bool = True

    # Payment & Reservation Settings (reference_settings.md & Phase 6 spec)
    PAYMENT_QR_SECRET: str = ""
    GATEWAY_WEBHOOK_SECRET: str = ""
    RESERVATION_TTL_SECONDS: int = 600
    TTL_AWAITING_PAYMENT_MINUTES: int = 30

    # PDPA Settings (reference_settings.md & Phase 10)
    RETENTION_MONTHS: int = 12
    CONSENT_REQUIRED: bool = True


settings = Settings()
