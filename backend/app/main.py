from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    print(f"[startup] listening on {settings.host}:{settings.port}")
    yield
    print("[shutdown] bye")


app = FastAPI(
    title="Codex 自动化代码交付平台",
    version="0.1.0",
    description="多项目自动化代码交付平台 MVP",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import health, projects, tasks, artifacts, events, reviews

app.include_router(health.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(artifacts.router)
app.include_router(events.router)
app.include_router(reviews.router)
