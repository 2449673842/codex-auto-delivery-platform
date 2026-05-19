from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db


# ─── Lifespan ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：初始化数据库
    await init_db()
    print(f"[startup] listening on {settings.host}:{settings.port}")
    yield
    # 关闭：无需额外清理
    print("[shutdown] bye")


# ─── App ───────────────────────────────────────────────

app = FastAPI(
    title="Codex 自动化代码交付平台",
    version="0.1.0",
    description="多项目自动化代码交付平台 MVP",
    lifespan=lifespan,
)

# ─── CORS ───────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Routers（后续在此注册）─────────────────────────────
# from app.routers import projects, tasks, artifacts, events, reviews


# ─── Health ─────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "codex-auto-delivery",
        "version": "0.1.0",
        "db": settings.db_url,
    }
