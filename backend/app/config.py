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


settings = Settings()
