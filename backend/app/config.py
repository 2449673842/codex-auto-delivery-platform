import os
from dataclasses import dataclass
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    # --- 服务监听 ---
    host: str = os.getenv("CODEX_HOST", "127.0.0.1")  # NOSONAR
    port: int = int(os.getenv("CODEX_PORT", "8700"))  # NOSONAR

    # --- 数据库 ---
    db_dir: Path = Path(os.getenv("CODEX_DB_DIR", str(_PROJECT_ROOT / "data")))  # NOSONAR
    db_filename: str = os.getenv("CODEX_DB_FILENAME", "codex_platform.db")  # NOSONAR

    @property
    def db_path(self) -> Path:
        return self.db_dir / self.db_filename

    @property
    def db_url(self) -> str:
        """SQLAlchemy 连接 URL，优先使用 CODEX_DB_URL 环境变量覆盖"""
        if "CODEX_DB_URL" in os.environ:  # NOSONAR
            return os.environ["CODEX_DB_URL"]  # NOSONAR
        return f"sqlite+aiosqlite:///{self.db_path}"

    # --- CORS ---
    frontend_origin: str = os.getenv("CODEX_FRONTEND_ORIGIN", "http://127.0.0.1:9700")  # NOSONAR

    # --- 环境标识 ---
    debug: bool = os.getenv("CODEX_DEBUG", "0") == "1"  # NOSONAR

    # --- AI 执行开关 ---
    ai_execution_enabled: bool = os.getenv("AI_EXECUTION_ENABLED", "").lower() in ("1", "true")  # NOSONAR

    # --- OpenAI ---
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")  # NOSONAR

    # --- OpenAI-compatible provider settings ---
    openai_model_provider: str = os.getenv("OPENAI_MODEL_PROVIDER", "openai")  # NOSONAR
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")  # NOSONAR
    openai_wire_api: str = os.getenv("OPENAI_WIRE_API", "chat_completions")  # NOSONAR
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # NOSONAR
    openai_reasoning_effort: str = os.getenv("OPENAI_REASONING_EFFORT", "")  # NOSONAR
    openai_disable_response_storage: bool = os.getenv("OPENAI_DISABLE_RESPONSE_STORAGE", "").lower() in ("1", "true", "yes")  # NOSONAR
    openai_service_tier: str = os.getenv("OPENAI_SERVICE_TIER", "")  # NOSONAR

    # --- AI Provider 白名单（逗号分隔） ---
    _provider_allowlist_raw: str = os.getenv("AI_PROVIDER_ALLOWLIST", "sandbox")  # NOSONAR

    @property
    def provider_allowlist(self) -> list[str]:
        return [x.strip() for x in self._provider_allowlist_raw.split(",") if x.strip()]

    # --- Browser AI Provider ---
    browser_ai_enabled: bool = os.getenv("BROWSER_AI_ENABLED", "").lower() in ("1", "true", "yes")  # NOSONAR
    browser_ai_headless: bool = os.getenv("BROWSER_AI_HEADLESS", "").lower() in ("1", "true", "yes")  # NOSONAR
    _browser_ai_provider_allowlist_raw: str = os.getenv("BROWSER_AI_PROVIDER_ALLOWLIST", "custom")  # NOSONAR
    browser_ai_default_timeout_seconds: int = int(os.getenv("BROWSER_AI_DEFAULT_TIMEOUT_SECONDS", "180"))  # NOSONAR
    browser_ai_user_data_dir: str = os.getenv("BROWSER_AI_USER_DATA_DIR", "")  # NOSONAR

    @property
    def browser_ai_provider_allowlist(self) -> list[str]:
        return [x.strip() for x in self._browser_ai_provider_allowlist_raw.split(",") if x.strip()]


settings = Settings()
