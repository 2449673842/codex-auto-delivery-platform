"""
异步 SQLAlchemy 引擎与会话工厂。

-SQLite 使用 aiosqlite 驱动
-WAL mode 通过 engine 事件启用（SQLite 专属）
-所有 ORM 模型通过 import models 注册后，init_db 自动建表
"""

from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event

from app.config import settings


# ─── ORM 基类 ──────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ─── 引擎 ──────────────────────────────────────────────

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.db_url,
            echo=settings.debug,
            future=True,
        )
        _enable_wal_mode(_engine)
    return _engine


def _enable_wal_mode(engine: AsyncEngine) -> None:
    """SQLite 专属：通过 sync 连接设置 WAL 模式 + 同步策略"""
    if not settings.db_url.startswith("sqlite"):
        return

    @event.listens_for(engine.sync_engine, "connect")
    def _set_wal(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """FastAPI Depends 用的会话获取器"""
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─── 建表 ──────────────────────────────────────────────

async def init_db() -> None:
    """启动时调用，自动建表（后续引入 Alembic 后分离）"""
    engine = get_engine()
    async with engine.begin() as conn:
        # 导入所有模型以确保它们注册到 Base.metadata
        import app.models  # noqa: F401  # pylint: disable=unused-import
        await conn.run_sync(Base.metadata.create_all)
    if settings.debug:
        print(f"[init_db] database ready at {settings.db_url}")
