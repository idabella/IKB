FROM python:3.11-slim

LABEL maintainer="ikb-team@company.com"
LABEL description="IKB Knowledge Engine — Unified Agent, RAG & Graph Service"

# ── System dependencies ──────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libpq-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Python environment ───────────────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install Python dependencies before copying source (layer cache optimisation)
COPY backend/services/knowledge_engine/requirements.txt ./ke_requirements.txt
COPY backend/requirements.txt ./base_requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r base_requirements.txt \
 && pip install --no-cache-dir -r ke_requirements.txt

# ── Application source ────────────────────────────────────────────────────────
COPY backend/ ./backend/
COPY scripts/ ./scripts/

# ── Health check ─────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# ── Runtime ──────────────────────────────────────────────────────────────────
EXPOSE 8001

CMD ["uvicorn", \
     "backend.services.knowledge_engine.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8001", \
     "--workers", "1", \
     "--log-config", "/app/backend/config/log_config.yaml"]
