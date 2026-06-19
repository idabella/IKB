FROM python:3.11-slim

LABEL maintainer="ikb-team@company.com"
LABEL description="IKB Telemetry Aggregator — Sensor ingestion, anomaly detection, time-series persistence"

# ── System dependencies ──────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libpq-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Python environment ────────────────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Dependency layer (cached separately from source)
COPY backend/services/telemetry_aggregator/requirements.txt ./ta_requirements.txt
COPY backend/requirements.txt ./base_requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r base_requirements.txt \
 && pip install --no-cache-dir -r ta_requirements.txt

# Application source
COPY backend/ ./backend/
COPY scripts/ ./scripts/

# ── Health check ─────────────────────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

EXPOSE 8002

CMD ["uvicorn", \
     "backend.services.telemetry_aggregator.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8002", \
     "--workers", "1", \
     "--log-config", "/app/backend/config/log_config.yaml"]
