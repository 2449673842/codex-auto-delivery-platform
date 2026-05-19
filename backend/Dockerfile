# ---- Stage 1: 依赖安装 ----
FROM python:3.12-slim AS builder

WORKDIR /install
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/deps -r requirements.txt

# ---- Stage 2: 运行时 ----
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /deps /usr/local/lib/python3.12/site-packages
COPY app/ /app/app/

EXPOSE 8701

# CODEX_HOST / CODEX_PORT 由 docker-compose 传入，默认 127.0.0.1:8701（本地开发）
CMD uvicorn app.main:app --host ${CODEX_HOST:-127.0.0.1} --port ${CODEX_PORT:-8701}
