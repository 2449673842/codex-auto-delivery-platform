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

from app.routers import health, projects, tasks, artifacts, events, reviews, agents, agent_runs, agent_reviews, approval_policies, approval, orchestration
from app.routers import code_context as code_context_router
from app.routers import patch_sandbox as patch_sandbox_router
from app.routers import sandbox_gate as sandbox_gate_router
from app.routers import review_packet as review_packet_router
from app.routers import context_selector as context_selector_router
from app.routers import ai_context_packet as ai_context_packet_router
from app.routers import prompt_template as prompt_template_router
from app.routers import ai_dispatch as ai_dispatch_router
from app.routers import ai_runtime as ai_runtime_router
from app.routers import dispatch_batches as dispatch_batches_router
from app.routers import answer_synthesis as answer_synthesis_router
from app.routers import ai_handoff as ai_handoff_router
from app.routers import browser_ai as browser_ai_router
from app.routers import mcp_bridge as mcp_bridge_router

app.include_router(health.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(artifacts.router)
app.include_router(events.router)
app.include_router(reviews.router)
app.include_router(agents.router)
app.include_router(agent_runs.router)
app.include_router(agent_reviews.router)
app.include_router(approval_policies.router)
app.include_router(approval.router)
app.include_router(orchestration.router)
app.include_router(code_context_router.router)
app.include_router(patch_sandbox_router.router)
app.include_router(sandbox_gate_router.router)
app.include_router(review_packet_router.router)
app.include_router(context_selector_router.router)
app.include_router(ai_context_packet_router.router)
app.include_router(prompt_template_router.router)
app.include_router(ai_dispatch_router.router)
app.include_router(ai_runtime_router.router)
app.include_router(dispatch_batches_router.router)
app.include_router(answer_synthesis_router.router)
app.include_router(ai_handoff_router.router)
app.include_router(browser_ai_router.router)
app.include_router(mcp_bridge_router.router)
