# Industrial Knowledge Brain (IKB)

**v2.4** — Google Gemini 2.5 Flash · 3-Service Monorepo · TimescaleDB · KRaft Kafka

An enterprise-grade AI platform for industrial factory monitoring, diagnostics, and knowledge management. IKB orchestrates high-frequency sensor streams, parses operational manuals, reasons over a Knowledge Graph, and delivers real-time diagnostics through Retrieval-Augmented Generation (RAG) and agentic ReAct loops.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Services](#services)
   - [API Gateway](#api-gateway----8000)
   - [Knowledge Engine](#knowledge-engine----8001)
   - [Telemetry Aggregator](#telemetry-aggregator----8002)
3. [Monorepo Structure](#monorepo-structure)
4. [Getting Started](#getting-started)
5. [Testing](#testing)
6. [Observability](#observability)
7. [RBAC](#rbac)
8. [Kubernetes](#kubernetes)
9. [Data Flows](#data-flows)
10. [RAG Pipeline Reference](#rag-pipeline-reference)
11. [Agent System Reference](#agent-system-reference)
12. [Environment Variables](#environment-variables)
13. [Redis Key Namespace](#redis-key-namespace)
14. [Performance Targets](#performance-targets)
15. [Development Guide](#development-guide)
16. [Key Dependencies](#key-dependencies)
17. [Infrastructure Details](#infrastructure-details)
18. [Roadmap](#roadmap)

---

## Architecture Overview

Three backend services. One unified time-series store. No Zookeeper. No InfluxDB.

```mermaid
graph TD
    Client["Web App (Next.js)\n:3000"] -- "HTTPS / WebSocket" --> GW

    subgraph "Backend - 3 Services"
        GW["API Gateway :8000\nAuth · RBAC · Rate Limit · WebSocket"]
        GW -- "HTTP proxy\nKNOWLEDGE_ENGINE_URL" --> KE
        GW -- "HTTP proxy\nTELEMETRY_AGGREGATOR_URL" --> TA

        subgraph KE["Knowledge Engine :8001"]
            direction TB
            AGT["Agent Orchestrator\n(ReAct loop)"]
            RAG["RAG Pipeline\n(Qdrant in-process)"]
            GRP["Graph Queries\n(Neo4j in-process)"]
            ING["Ingestion\n(background task)"]
            INT["Internal Endpoint\n/internal/agent-tasks"]
            AGT -- "in-process" --> RAG
            AGT -- "in-process" --> GRP
        end

        subgraph TA["Telemetry Aggregator :8002"]
            direction TB
            KFK["Kafka Consumer\nikb.sensors.raw\nbatch + back-pressure"]
            DET["Rule (Tier 1) - Statistical (Tier 2)"]
            KFK --> DET
        end
    end

    TA -- "HTTP POST /internal/agent-tasks\n(HIGH/CRITICAL only)" --> INT
    INT --> AGT

    KE & TA --> DB[("TimescaleDB / PostgreSQL 16\nHypertables · Continuous Aggregates\n90-day retention · hourly rollups")]
    KE --> Q[("Qdrant\nRAG vectors\nHNSW m=32 · on_disk_payload")]
    KE --> N[("Neo4j\nKnowledge Graph")]
    GW & KE & TA --> R[("Redis\nRAG cache · Rate Limit\nLatest sensor values\nEpisodic memory · Parent chunks")]
    GW & KE & TA --> Obs["Prometheus - Grafana\nJaeger (distributed tracing)"]
    TA -.-> MLf["MLflow (optional)\nModel registry\nGraceful fallback if absent"]

    style GW  fill:#0f172a,stroke:#3b82f6,color:#fff
    style KE  fill:#1e1b4b,stroke:#6366f1,color:#fff
    style TA  fill:#052e16,stroke:#10b981,color:#fff
    style Client fill:#1e293b,stroke:#38bdf8,color:#fff
```

### Design Properties

| Property | Detail |
|---|---|
| **Zero cross-service imports** | All agent, RAG, and graph code lives inside `knowledge_engine/` |
| **In-process tool calls** | Agent to RAG/Graph with no HTTP hop — saves 20-80 ms per ReAct step |
| **HTTP escalation** | HIGH/CRITICAL anomalies posted to `POST /internal/agent-tasks` — no dedicated Kafka topic needed |
| **Unified time-series** | TimescaleDB handles all time-series data via `asyncpg COPY` bulk writes (10x faster than INSERTs) |
| **KRaft Kafka** | Zookeeper eliminated — Kafka 7.6 manages its own consensus |
| **Two-tier anomaly detection** | Rule-based O(1) Redis check, then Welford Z-score statistics. Optional ML tier via MLflow |
| **MLflow optional** | Lazy import — all services start and run fully without MLflow present |
| **spaCy optional** | `ENABLE_SPACY_NER=true` activates NER; off by default (saves ~200 MB RAM) |
| **Qdrant HNSW m=32** | P95 query latency -30% vs default m=16. `on_disk_payload=True` saves 300-500 MB RAM |
| **RBAC enforced** | `require_roles()` FastAPI dependency applied to every protected route |
| **Structured logging** | `structlog` — JSON in production, colour-keyed console in development |
| **SSE streaming** | `/api/v1/agents/tasks/{id}/stream` delivers real-time ReAct reasoning steps |
| **Singleton pattern** | DB pool, orchestrator, RAG pipeline, and Redis client built once at startup in `app.state` |
| **DevAuthMiddleware** | Injects a default identity in development when `AUTH_ENABLED=false` |

---

## Services

### API Gateway — `:8000`

Entry point for all client traffic. Handles authentication, rate limiting, CORS, and request proxying.

- JWT validation and Redis-backed rate limiting
- Reverse-proxies to Knowledge Engine (`KNOWLEDGE_ENGINE_URL=http://knowledge-engine:8001`)
- Reverse-proxies to Telemetry Aggregator (`TELEMETRY_AGGREGATOR_URL=http://telemetry-aggregator:8002`)
- WebSocket upgrade and streaming relay via `src/websocket/realtime_handler.py`
- Docs: http://localhost:8000/docs

**Source layout:**

```
api_gateway/
├── main.py
└── src/
    ├── app.py                   # FastAPI application factory
    ├── config.py                # Environment-driven settings
    ├── middleware/
    │   ├── auth.py              # JWT validation
    │   └── rate_limiter.py      # Redis-backed rate limiting
    ├── routers/
    │   ├── agents.py            # Proxies to Knowledge Engine agent endpoints
    │   ├── query.py             # Proxies to Knowledge Engine RAG/query endpoints
    │   └── telemetry.py         # Proxies to Telemetry Aggregator endpoints
    ├── schemas/                 # Request/response Pydantic models
    └── websocket/
        └── realtime_handler.py  # WebSocket upgrade and streaming relay
```

---

### Knowledge Engine — `:8001`

Unified cognitive service. No cross-service imports. No outbound HTTP from within the agent loop.

**Startup singletons** — built once in `lifespan()`, stored in `app.state`:

| Singleton | `app.state` key | Order | Purpose |
|---|---|---|---|
| asyncpg Pool | `db_pool` | 1 | PostgreSQL / TimescaleDB connection pool |
| Redis client | `redis_client` | 2 | RAG L1 cache, parent chunks, episodic memory |
| KafkaMessageProducer | `kafka_producer` | 3 | MonitoringAgent anomaly escalation (singleton — no per-call reconnect) |
| RetrieveContextHandler | `retrieve_handler` | 4 | Full RAG pipeline: embed, retrieve, rerank |
| IngestDocumentHandler | `ingest_handler` | 4 | Chunk, embed, and upsert to Qdrant |
| AgentOrchestrator | `orchestrator` | 5 | Routes tasks to RCA / Maintenance / Monitoring agents |

**Source layout:**

```
knowledge_engine/
├── main.py                    # FastAPI lifespan — builds all singletons once
├── api/
│   ├── router.py              # Root router — mounts sub-routers under /api/v1
│   ├── dependencies.py        # Centralised Depends() helpers
│   ├── agents_router.py       # Agent task submission, SSE stream, trace
│   ├── rag_router.py          # In-process RAG retrieval with Redis L1 cache (10 min TTL)
│   └── ingest_router.py       # Document ingestion as FastAPI BackgroundTask
├── agents/
│   ├── base_agent.py          # Abstract ReAct loop with SSE stream() support
│   ├── root_cause_agent.py    # IEC 62682 / ISA-18.2 root cause analysis
│   ├── maintenance_agent.py   # Work order generation
│   └── monitoring_agent.py    # Anomaly triage with Kafka escalation
├── llm/
│   ├── base_llm_client.py     # Abstract LLM interface
│   ├── gemini_client.py       # Google Gemini 2.5 Flash async client (primary)
│   └── anthropic_client.py    # Anthropic client (legacy, not active)
├── memory/
│   └── episodic_memory.py     # Redis-backed sliding window (50 turns, 8 h TTL, LLM summarisation)
├── tools/
│   ├── base_tool.py           # Abstract ToolResult interface
│   ├── rag_tool.py            # In-process RAG search — no HTTP
│   ├── graph_tool.py          # In-process Neo4j graph queries
│   └── telemetry_tool.py      # In-process TimescaleDB / Redis sensor data retrieval
├── rag/
│   ├── chunkers/              # ParentChildChunker: parent 1000 tokens, child 200 tokens
│   ├── embedders/
│   │   └── gemini_embedder.py          # Gemini embedding async client (gemini-embedding-001)
│   ├── rerankers/
│   │   └── cross_encoder_reranker.py   # ms-marco-MiniLM-L-6-v2, lazy-loaded, run_in_executor
│   ├── retrievers/
│   │   ├── hybrid_retriever.py         # Dense vector search via QdrantStore
│   │   ├── multi_query_retriever.py    # LLM query expansion (opt-in, 2-3 extra LLM calls)
│   │   └── parent_retriever.py         # Child-to-parent expansion via Redis
│   └── vector_stores/
│       └── qdrant_store.py    # HNSW m=32, on_disk_payload, upsert_batch()
├── graph/
│   ├── extractors/
│   │   ├── base_extractor.py
│   │   ├── industrial_ner.py  # Optional: activated by ENABLE_SPACY_NER=true
│   │   ├── llm_extractor.py   # Default NER via Gemini
│   │   └── relation_extractor.py
│   └── graph_db/
│       ├── neo4j_client.py
│       ├── cypher_queries.py
│       └── graph_schema.py
├── domain/                    # AgentTask, AgentResult, ToolCall domain models
├── application/
│   ├── orchestrator.py        # AgentOrchestrator — routes by task_type
│   └── workflows/
├── rag_application/
│   ├── commands/              # IngestDocumentCommand
│   └── queries/               # RetrieveContextQuery
└── graph_application/
    ├── commands/              # ExtractEntities
    └── queries/               # CausalAnalysis
```

**Endpoints:**

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/v1/agents/analyze` | operator+ | Submit an async agent analysis task |
| `GET` | `/api/v1/agents/tasks/{id}` | operator+ | Poll task status and result |
| `GET` | `/api/v1/agents/tasks/{id}/stream` | operator+ | SSE live reasoning steps |
| `GET` | `/api/v1/agents/tasks/{id}/trace` | operator+ | Per-step tool execution trace |
| `POST` | `/api/v1/rag/retrieve` | operator+ | Semantic retrieval with Redis L1 cache |
| `POST` | `/api/v1/ingest/document` | engineer+ | Upload and ingest PDF / DOCX / TXT |
| `GET` | `/api/v1/ingest/jobs/{id}` | operator+ | Poll ingestion job status |
| `POST` | `/api/v1/internal/agent-tasks` | internal | Receives HIGH/CRITICAL escalations from Telemetry Aggregator |
| `GET` | `/health` | public | Service health and singleton readiness map |

> **Escalation path:** Telemetry Aggregator posts to `/api/v1/internal/agent-tasks`. The request is accepted immediately (HTTP 202) and processed asynchronously via `asyncio.create_task()` through the AgentOrchestrator.

Docs: http://localhost:8001/docs

---

### Telemetry Aggregator — `:8002`

High-throughput sensor processing. TimescaleDB writes via `asyncpg COPY` — 10x faster than row-by-row INSERTs.

**Startup singletons:**

| Singleton | `app.state` key | Purpose |
|---|---|---|
| asyncpg Pool | `db_pool` | TimescaleDB bulk writes (min=3, max=10) |
| Redis client | `redis_client` | Welford stats, dedup window, latest values |
| TelemetryRedisCache | `redis_cache` | Higher-level cache abstraction |
| TelemetryStreamProcessor | `stream_processor` | Kafka consumer loop and tiered detection pipeline |

**Anomaly detection pipeline:**

```
Kafka: ikb.sensors.raw
    |
    v  batch (up to 500 msgs, flush every 100 ms)
    |
    +-- asyncpg COPY --> TimescaleDB sensor_readings (hypertable)
    |
    +-- Per reading:
            Tier 1: RuleDetector       — O(1) Redis-cached hard bounds, 5-min dedup
            Tier 2: StatisticalDetector — Welford online Z-score (warm-up: 30 samples)
            Tier 3: MLDetector         — optional, requires MLflow model registration
            |
            v  on anomaly
            +-- INSERT --> anomaly_events (PostgreSQL)
            +-- PUBLISH --> ikb.anomalies (Kafka) -- dashboards / Prometheus
            +-- if HIGH or CRITICAL:
                    HTTP POST /api/v1/internal/agent-tasks --> Knowledge Engine
```

**Source layout:**

```
telemetry_aggregator/
├── main.py
├── api/
│   ├── router.py               # Root router
│   ├── sensors_router.py       # REST push and Redis/TimescaleDB read paths
│   └── anomalies_router.py     # Anomaly history queries
└── application/
    ├── stream_processor.py     # Kafka consumer, COPY writes, anomaly pipeline, HTTP escalation
    ├── cache/
    │   └── redis_cache.py      # Welford stats, dedup window, latest-value hash, recent anomaly list
    └── detectors/
        ├── rule_detector.py         # Tier 1: absolute threshold check with 5-min dedup
        └── statistical_detector.py  # Tier 2: Z-score / IQR via Welford online algorithm
```

**Endpoints:**

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/sensors/readings` | REST sensor push to TimescaleDB |
| `GET` | `/api/v1/sensors/machines/{id}/latest` | Redis cache (TTL 30 s), falls back to TimescaleDB view |
| `GET` | `/api/v1/sensors/machines/{id}/sensors/{sid}/history` | Raw rows for <=24 h; hourly continuous aggregate for >24 h |
| `GET` | `/api/v1/anomalies/machines/{id}` | Anomaly history with severity filter and pagination |
| `GET` | `/api/v1/anomalies/{anomaly_id}` | Single anomaly event detail |
| `GET` | `/health` | Service health |

Docs: http://localhost:8002/docs

---

## Monorepo Structure

```
.
├── ai/                                 # Experimental AI modules (agents, RAG, models, knowledge_graph)
├── backend/
│   ├── services/
│   │   ├── api_gateway/               # API Gateway :8000
│   │   │   ├── main.py
│   │   │   └── src/
│   │   │       ├── app.py
│   │   │       ├── config.py
│   │   │       ├── middleware/        # auth.py, rate_limiter.py
│   │   │       ├── routers/           # agents.py, query.py, telemetry.py
│   │   │       ├── schemas/
│   │   │       └── websocket/         # realtime_handler.py
│   │   ├── knowledge_engine/          # Knowledge Engine :8001
│   │   └── telemetry_aggregator/      # Telemetry Aggregator :8002
│   └── shared/
│       ├── base/
│       ├── infrastructure/
│       │   ├── database/
│       │   │   └── postgres.py        # init_db_pool, close_db_pool, get_db_pool
│       │   ├── messaging/             # KafkaMessageProducer (singleton, injected)
│       │   ├── metrics.py             # Prometheus metrics mounting
│       │   └── tracing/               # OpenTelemetry setup, instrument_fastapi
│       ├── security/
│       │   ├── rbac.py                # require_roles() FastAPI dependency
│       │   ├── dev_auth.py            # DevAuthMiddleware (development only)
│       │   └── tenant.py              # get_tenant_id() dependency
│       └── utils/
│           └── logging.py             # structlog: JSON in production, colour console in dev
├── data_pipelines/                    # ETL and batch pipeline scripts
├── frontend/                          # Next.js 14 Web UI (:3000)
├── infrastructure/
│   ├── docker/
│   │   └── migrations/
│   │       ├── 001_initial_schema.sql
│   │       ├── 002_consolidated_architecture.sql
│   │       ├── 003_timescaledb.sql             # Hypertables and continuous aggregates
│   │       └── 004_performance_hardening.sql   # Index tuning and active-anomaly partial index
│   └── kubernetes/
│       ├── config.yaml
│       ├── api-gateway.yaml
│       ├── knowledge-engine.yaml
│       └── telemetry-aggregator.yaml
├── monitoring/                        # Grafana, Prometheus, Jaeger configuration
├── scripts/                           # Dev/ops helper scripts
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── load/
├── Makefile
├── docker-compose.dev.yml
└── pyproject.toml
```

---

## Getting Started

### Prerequisites

- Docker and Docker Compose v2+
- Python 3.11+ with Poetry
- Node.js 18+ with npm

### Step 1 — Configure environment

```bash
make .env        # copies .env.example to .env
```

Set `GEMINI_API_KEY` and all service passwords before proceeding.

### Step 2 — Start all services

```bash
make up
# Services:  api-gateway, knowledge-engine, telemetry-aggregator
# Infra:     timescaledb (pg16), redis, kafka (KRaft), qdrant, neo4j
#            prometheus, grafana, jaeger, mlflow (optional), frontend
```

### Step 3 — Apply database migrations

Run in order:

```bash
make migrate          # migrations 001 and 002
make migrate-003      # TimescaleDB hypertables and continuous aggregates
make migrate-004      # Partial indexes and active-anomaly index
```

### Step 4 — Verify health

```bash
make health
# api-gateway          (port 8000): HEALTHY
# knowledge-engine     (port 8001): HEALTHY  {"singletons_ready": {"db_pool": true, ...}}
# telemetry-aggregator (port 8002): HEALTHY
```

### Optional features

```bash
# Enable spaCy NER (requires ~500 MB model download)
ENABLE_SPACY_NER=true make up

# Enable ML anomaly detector via MLflow (requires a registered model)
MLFLOW_TRACKING_URI=http://mlflow:5000 \
MLFLOW_MODEL_NAME=telemetry-lstm-autoencoder \
MLFLOW_MODEL_STAGE=Production \
make up

# Enable distributed tracing via Jaeger
docker compose --profile tracing up
```

### Common developer commands

```bash
make logs-gw         # tail API Gateway logs
make logs-ke         # tail Knowledge Engine logs
make logs-ta         # tail Telemetry Aggregator logs
make shell-ke        # open shell inside Knowledge Engine container
make ps              # list all containers
make down            # stop all services
make clean           # stop and delete all volumes
```

---

## Testing

```bash
make test-unit          # unit tests — no infrastructure required (~seconds)
make test-integration   # integration tests — mocked infrastructure
make test-e2e           # end-to-end tests — full stack required
make test-load          # Locust load test — full stack required
make test-cov           # all suites + coverage report (threshold: 70%)
```

| Suite | Location | Infrastructure |
|---|---|---|
| Unit | `tests/unit/` | None |
| Integration | `tests/integration/` | None (AsyncMock) |
| E2E | `tests/e2e/` | Full stack |
| Load | `tests/load/` | Full stack + Locust |

---

## Observability

| Service | URL | Purpose |
|---|---|---|
| API Gateway | http://localhost:8000/docs | OpenAPI docs |
| Knowledge Engine | http://localhost:8001/docs | OpenAPI docs |
| Telemetry Aggregator | http://localhost:8002/docs | OpenAPI docs |
| Frontend | http://localhost:3000 | Next.js UI |
| Grafana | http://localhost:3001 | Metrics dashboards |
| Jaeger | http://localhost:16686 | Distributed traces (profile: tracing) |
| MLflow | http://localhost:5000 | Model registry (optional) |
| Qdrant | http://localhost:6333/dashboard | Vector database dashboard |
| Neo4j | http://localhost:7474 | Graph query console |

### Key Prometheus Metrics

| Metric | Service | Description |
|---|---|---|
| `ta_messages_processed_total` | Telemetry Aggregator | Total Kafka messages processed |
| `ta_processing_latency_ms` | Telemetry Aggregator | Batch processing latency |
| `ta_anomalies_detected_total{severity,detector_type}` | Telemetry Aggregator | Anomaly counts by tier and severity |
| `ta_timescaledb_writes_total` | Telemetry Aggregator | Bulk COPY write operations |
| `retrieval_latency_ms` | Knowledge Engine | Full RAG pipeline latency (target: <500 ms p95) |
| `rerank_latency_ms` | Knowledge Engine | Cross-encoder reranking step latency |
| `empty_result_count` | Knowledge Engine | Queries that returned zero results |

### TimescaleDB Query Examples

```sql
-- Latest sensor readings per machine (uses latest_sensor_readings view)
SELECT machine_id, sensor_id, value, unit, recorded_at
FROM   latest_sensor_readings
WHERE  machine_id = 'CNC-07';

-- Hourly trend via pre-computed continuous aggregate
SELECT bucket, avg_val, max_val, stddev_val
FROM   sensor_readings_hourly
WHERE  machine_id = 'CNC-07'
  AND  sensor_id  = 'temperature'
  AND  bucket >= NOW() - INTERVAL '24 hours'
ORDER  BY bucket DESC;

-- Active unresolved critical anomalies (served by partial B-tree index)
SELECT *
FROM   anomaly_events
WHERE  machine_id  = 'CNC-07'
  AND  is_resolved = FALSE
  AND  severity    IN ('CRITICAL', 'HIGH')
ORDER  BY detected_at DESC;
```

---

## RBAC

| Role | Permissions |
|---|---|
| `readonly` | Read-only dashboard queries |
| `operator` | Reads, sensor queries, agent polling |
| `engineer` | Operator permissions plus document ingestion and agent submission |
| `admin` | Full access |
| `api_client` | Machine-to-machine sensor push |

```python
from backend.shared.security.rbac import require_roles, Roles

@router.post("/sensitive")
async def endpoint(_=Depends(require_roles([Roles.ENGINEER, Roles.ADMIN]))):
    ...
```

> **Development mode:** When `AUTH_ENABLED=false` (the default when `ENVIRONMENT=development`), `DevAuthMiddleware` injects a default identity so every request passes authentication without a real token.

---

## Kubernetes

```bash
kubectl apply -f infrastructure/kubernetes/config.yaml
kubectl edit secret ikb-secrets -n ikb
kubectl apply -f infrastructure/kubernetes/api-gateway.yaml
kubectl apply -f infrastructure/kubernetes/knowledge-engine.yaml
kubectl apply -f infrastructure/kubernetes/telemetry-aggregator.yaml
kubectl get hpa -n ikb
```

| Service | Replicas | Scale Trigger |
|---|---|---|
| `api-gateway` | 2-8 | CPU >= 70% |
| `knowledge-engine` | 2-10 | CPU >= 70% or Memory >= 80% |
| `telemetry-aggregator` | 2-8 | CPU >= 70% (bounded by Kafka partition count) |

---

## Data Flows

### High-frequency sensor ingestion (Kafka path)

```
IoT Device / SCADA
    |
    v  JSON messages --> ikb.sensors.raw (32 partitions)
Kafka Broker
    |
    v  batched: up to 500 messages or 100 ms flush
TelemetryStreamProcessor._consume_loop()
    |
    +-- asyncio.gather():
    |       |
    |       +-- _write_to_timescaledb()
    |       |       asyncpg COPY --> sensor_readings (hypertable)
    |       |       TimescaleDB auto-partitions into 1-day chunks
    |       |
    |       +-- _run_tiered_detection()
    |               Tier 1: RuleDetector       -- Redis O(1) threshold check
    |               Tier 2: StatisticalDetector -- Welford Z-score
    |
    +-- on anomaly:
            INSERT --> anomaly_events
            PUBLISH --> ikb.anomalies (Kafka)
            if severity is HIGH or CRITICAL:
                httpx POST --> KE /api/v1/internal/agent-tasks (async, best-effort)
```

### Low-frequency sensor ingestion (REST path)

```
Client  -->  POST /api/v1/sensors/readings
                 |
                 +-- INSERT --> sensor_readings (TimescaleDB)
                 +-- SET    --> Redis ta:latest:{machine_id} (TTL 30 s)
```

### Agent analysis — full ReAct loop

```
Client  -->  POST /api/v1/agents/analyze
                 |
                 v  returns task_id immediately (HTTP 202)
                 INSERT --> agent_tasks (status=processing)
                 |
                 v  background coroutine
AgentOrchestrator.route_and_execute(task)
                 |
                 v  routed by task_type
    +-------------------------------------------+
    |  RootCauseAgent    (anomaly_analysis)      |
    |  MaintenanceAgent  (work_order_creation)   |
    |  MonitoringAgent   (monitoring_event)      |
    +-------------------------------------------+
                 |
                 v  ReAct loop (max 10 steps)
    LLM (Gemini 2.5 Flash):
        Reason --> select tool --> execute tool --> observe --> repeat
                 |
                 |  in-process tools (no HTTP):
                 |    rag_search   --> RetrieveContextHandler --> Qdrant
                 |    graph_query  --> Neo4j
                 |    telemetry    --> TimescaleDB / Redis
                 |
                 v  on completion
    UPDATE agent_tasks SET status=completed, result=...
                 |
                 v  SSE consumers
    GET /tasks/{id}/stream  -->  live token stream
```

### Document ingestion

```
Client  -->  POST /api/v1/ingest/document  (multipart upload)
                 |
                 v  returns job_id immediately (HTTP 202)
                 INSERT --> ingestion_jobs (status=processing)
                 |
                 v  FastAPI BackgroundTask
IngestDocumentHandler.handle(cmd)
    |
    +-- ParentChildChunker   --> parent (1000 tokens) + child (200 tokens) chunks
    +-- GeminiEmbedder       --> dense vectors (gemini-embedding-001)
    +-- QdrantStore.upsert_batch() --> Qdrant collection ikb_{tenant_id}
                 |
    UPDATE ingestion_jobs SET status=done
```

---

## RAG Pipeline Reference

### Retrieval Modes

| Mode | Trigger | LLM Calls | Use Case |
|---|---|---|---|
| Direct hybrid (default) | `use_multi_query=false` | 1 embed call | Most queries — fast, good recall |
| Multi-query expansion | `use_multi_query=true` | 1 embed + 2-3 LLM calls | Ambiguous or short queries — higher recall at ~+500 ms |

### Default Pipeline Steps

```
query string
    |
    v  1. Embed  (Gemini gemini-embedding-001, async)
query_vector  [float x 768]
    |
    v  2. HybridRetriever.search()
           collection:      ikb_{tenant_id}
           filters:         tenant_id + machine_ids (MatchAny) + doc_type
           index:           HNSW m=32
           score_threshold: 0.6
           limit:           top_k x 2
    |
    v  3. ParentRetriever.expand_to_parents()
           Redis GET rag:parent:{parent_id} for each child chunk
           Falls back to child text on cache miss
    |
    v  4. CrossEncoderReranker.rerank()   (when rerank=True)
           model:     cross-encoder/ms-marco-MiniLM-L-6-v2
           execution: thread pool via run_in_executor (non-blocking)
           min_score: 0.1, returns top_k results
    |
    v  5. Return List[RetrievalResult]
           Prometheus counters: retrieval_latency_ms, rerank_latency_ms
           Latency target: <500 ms p95
```

### Chunking Strategy

| Level | Size | Overlap | Storage |
|---|---|---|---|
| Parent | 1000 tokens | 100 tokens | Redis `rag:parent:{id}` (TTL set at ingestion time) |
| Child | 200 tokens | 20 tokens | Qdrant payload: `.text` and `.parent_id` |

### Qdrant Collection Schema

```
collection:  ikb_{tenant_id}
vectors:
  dense:   dim=768, distance=COSINE
  sparse:  SparseVectorParams  (reserved for future BM25 hybrid search)
hnsw:
  m=32, ef_construct=200, full_scan_threshold=10_000
indexed payload fields:
  tenant_id, machine_id, doc_type, doc_id, parent_id, chunk_id, text, timestamp
on_disk_payload: true    -- saves 300-500 MB RAM per collection
```

---

## Agent System Reference

### Agent Routing

| `task_type` | Agent | Timeout |
|---|---|---|
| `anomaly_analysis` | `RootCauseAgent` | 30 s |
| `work_order_creation` | `MaintenanceAgent` | 30 s |
| `monitoring_event` | `MonitoringAgent` | 30 s |
| `conversational_query` (default) | `RootCauseAgent` | 30 s |

### Agent Capabilities

| Agent | System Role | Active Tools |
|---|---|---|
| RootCauseAgent | IEC 62682 / ISA-18.2 RCA engineer | `rag_search`, `graph_query`, `telemetry` |
| MaintenanceAgent | Maintenance work-order planner | `rag_search` |
| MonitoringAgent | Level-1 anomaly triage | `rag_search`, `telemetry` |

### ReAct Loop (BaseIndustrialAgent)

```python
for step in range(max_steps=10):
    response = await llm_client.complete(messages, system_prompt, tools)
    # tool_use blocks  --> execute in-process, append tool_result, continue
    # no tool_use      --> loop terminates, call post_process()
# post_process(): safety override, confidence calibration, optional Kafka publish
# EpisodicMemory.append(): Redis pipeline rpush + ltrim + expire
```

### Episodic Memory

| Property | Value |
|---|---|
| Backend | Redis list at `agent:memory:episodic:{session_id}` |
| Sliding window | 50 turns maximum (`ltrim -50 -1`) |
| TTL | 8 hours (28800 s), refreshed on every append |
| Auto-summarisation | Triggered when token count exceeds 4096; old turns compressed via LLM, last 10 kept verbatim |

---

## Environment Variables

### Required

| Variable | Service | Description |
|---|---|---|
| `GEMINI_API_KEY` | KE | Google Gemini API key for LLM and embeddings |
| `GEMINI_MODEL` | KE | Chat model override (default: `gemini-2.5-flash`) |
| `GEMINI_EMBEDDING_MODEL` | KE | Embedding model (default: `gemini-embedding-001`) |
| `GEMINI_EMBEDDING_DIM` | KE | Embedding vector dimension (default: `768`) |
| `POSTGRES_PASSWORD` | All | PostgreSQL password |
| `REDIS_PASSWORD` | All | Redis password |
| `NEO4J_PASSWORD` | KE | Neo4j password |

### Networking

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://ikb_admin:...@postgres:5432/ikb_main` | PostgreSQL connection DSN |
| `REDIS_URL` | `redis://:...@redis:6379/0` | Redis URL (KE: db=0, TA: db=1) |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant REST endpoint |
| `NEO4J_URI` | `bolt://neo4j:7687` | Neo4j Bolt URI |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:29092` | Kafka bootstrap servers |
| `KNOWLEDGE_ENGINE_URL` | `http://knowledge-engine:8001` | Used by API Gateway and Telemetry Aggregator |
| `TELEMETRY_AGGREGATOR_URL` | `http://telemetry-aggregator:8002` | Used by API Gateway |

### Ports

| Variable | Default | Service |
|---|---|---|
| `API_GATEWAY_PORT` | `8000` | API Gateway |
| `KNOWLEDGE_ENGINE_PORT` | `8001` | Knowledge Engine |
| `TELEMETRY_PORT` | `8002` | Telemetry Aggregator |
| `FRONTEND_PORT` | `3000` | Next.js UI |
| `POSTGRES_PORT` | `5432` | TimescaleDB / PostgreSQL |
| `REDIS_PORT` | `6379` | Redis |
| `KAFKA_PORT` | `9092` | Kafka (external listener) |
| `QDRANT_PORT` | `6333` | Qdrant REST |
| `NEO4J_HTTP_PORT` | `7474` | Neo4j Browser |
| `NEO4J_BOLT_PORT` | `7687` | Neo4j Bolt |
| `GRAFANA_PORT` | `3001` | Grafana |
| `PROMETHEUS_PORT` | `9090` | Prometheus |
| `JAEGER_UI_PORT` | `16686` | Jaeger UI |
| `MLFLOW_PORT` | `5000` | MLflow (optional) |

### Feature Flags

| Variable | Default | Description |
|---|---|---|
| `AUTH_ENABLED` | `false` in dev / `true` in prod | Enable JWT authentication |
| `ENABLE_SPACY_NER` | `false` | Load spaCy `en_core_web_lg` for industrial NER (~200 MB) |
| `MLFLOW_TRACKING_URI` | unset | Enables the ML detector tier when set and a model is registered |
| `MLFLOW_MODEL_NAME` | `telemetry-lstm-autoencoder` | Registered MLflow model name |
| `MLFLOW_MODEL_STAGE` | `Production` | MLflow model stage to load |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://jaeger:4317` | OpenTelemetry OTLP exporter endpoint |
| `DEFAULT_TENANT_ID` | `default` | Default tenant used in internal escalations |
| `QDRANT_SCORE_THRESHOLD` | `0.6` | Minimum cosine similarity score for RAG retrieval |

---

## Redis Key Namespace

| Key pattern | TTL | Owner | Description |
|---|---|---|---|
| `ta:stats:{sensor_id}` | 24 h | Telemetry Aggregator | Welford rolling stats: mean, std_dev, m2, count |
| `ta:dedup:{sensor_id}:{severity}` | 5 min | Telemetry Aggregator | Anomaly deduplication suppression window |
| `ta:anomalies:recent:{machine_id}` | 1 h | Telemetry Aggregator | Last 100 anomaly events per machine |
| `ta:rules:{machine_id}` | 5 min | Telemetry Aggregator | Alert rules cached from PostgreSQL |
| `ta:latest:{machine_id}` | 30 s | Telemetry Aggregator | Hash of `{sensor_id}` to latest reading JSON |
| `rag:{sha256[:24]}` | 10 min | Knowledge Engine | RAG retrieval result cache (scoped by tenant and query) |
| `rag:parent:{parent_id}` | set at ingestion | Knowledge Engine | Parent chunk text for ParentRetriever expansion |
| `agent:memory:episodic:{session_id}` | 8 h | Knowledge Engine | EpisodicMemory conversation history |
| rate-limit keys | per window | API Gateway | Redis-backed request rate limiter |

---

## Performance Targets

| Metric | Target | Instrument |
|---|---|---|
| RAG retrieval latency (p95) | < 500 ms | `retrieval_latency_ms` histogram |
| Sensor batch processing | < 100 ms per 500 messages | `ta_processing_latency_ms` histogram |
| TimescaleDB COPY write | < 10 ms per batch | Internal timing |
| Agent task hard timeout | 30 s | `asyncio.wait_for` in orchestrator |
| Redis latest-value read | < 1 ms | In-memory hash (TTL 30 s) |
| SSE first-token latency | < 2 s | Gemini streaming API |
| Qdrant HNSW search | < 50 ms | Qdrant query log |
| Kafka consumer lag | < 1 s | Prometheus / Kafka metrics |

---

## Development Guide

### Running services locally without Docker

```bash
# Create and activate a virtual environment
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install all packages from the monorepo root
pip install -e ".[dev]"

# Start only infrastructure dependencies
docker compose up postgres redis kafka qdrant neo4j -d

# Run Knowledge Engine
cd backend/services/knowledge_engine
uvicorn main:app --reload --port 8001

# Run Telemetry Aggregator
cd backend/services/telemetry_aggregator
uvicorn main:app --reload --port 8002
```

### Adding a new agent

1. Create `backend/services/knowledge_engine/agents/my_agent.py` inheriting `BaseIndustrialAgent`
2. Implement `system_prompt`, `allowed_tools`, `pre_process`, and `post_process`
3. Wire the agent in `_build_orchestrator()` inside `main.py`
4. Add its routing key to `AgentOrchestrator.agents` in `orchestrator.py`

### Adding a new tool

1. Create `backend/services/knowledge_engine/tools/my_tool.py` inheriting `BaseTool`
2. Implement `async def execute(self, input: dict) -> ToolResult`
3. Register the tool in `tool_registry` inside `_build_orchestrator()` in `main.py`
4. Add the tool name to the relevant agent's `allowed_tools` list

### Adding a new sensor endpoint

1. Add the route to `backend/services/telemetry_aggregator/api/sensors_router.py`
2. For write paths use `db_pool = _get_db_pool(request)`
3. For cache paths use `request.app.state.stream_processor.redis_cache`
4. Apply RBAC with `_rbac=Depends(require_roles([Roles.OPERATOR, ...]))`

### Code quality

```bash
black backend/ --line-length 100   # format
ruff check backend/                # lint
mypy backend/ --ignore-missing-imports  # type check
make lint                          # runs all three
```

### Commit convention

```
feat(ke): add graph_query tool to RootCauseAgent
fix(ta): pool httpx client across escalations
perf(rag): lazy-load CrossEncoder model in executor
docs: update README architecture section
chore(deps): pin qdrant-client to v1.9.2
```

Scope prefixes: `ke` = Knowledge Engine, `ta` = Telemetry Aggregator, `gw` = API Gateway, `rag`, `infra`.

---

## Key Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.111.0 | Web framework for all three services |
| `uvicorn[standard]` | 0.30.1 | ASGI server |
| `asyncpg` | 0.29.0 | PostgreSQL async driver; used for TimescaleDB COPY writes |
| `google-genai` | >=1.0.0 | Google Gemini LLM and embeddings |
| `qdrant-client` | 1.9.1 | Vector database async client |
| `sentence-transformers` | 3.0.1 | Cross-encoder reranker (local inference) |
| `neo4j` | 5.20.0 | Knowledge Graph async Bolt driver |
| `aiokafka` | latest | Async Kafka consumer and producer |
| `redis` | 5.0.4 | Async Redis client for cache and episodic memory |
| `httpx` | latest | HTTP client for TA-to-KE anomaly escalation |
| `structlog` | 24.2.0 | Structured JSON logging |
| `prometheus-client` | 0.20.0 | Metrics exposition |
| `opentelemetry-*` | 1.24.0 | Distributed tracing via OTLP to Jaeger |
| `pypdf` | 4.2.0 | PDF document parsing |
| `python-docx` | 1.1.2 | DOCX document parsing |
| `tiktoken` | 0.7.0 | Token counting for chunkers |
| `tenacity` | 8.3.0 | Retry logic for LLM calls |
| `orjson` | latest | Fast JSON serialisation for Kafka messages |
| `pydantic` | 2.7.1 | Data validation across all services |

---

## Infrastructure Details

### Kafka Topics

| Topic | Partitions | Retention | Producer | Consumer |
|---|---|---|---|---|
| `ikb.sensors.raw` | 32 | 7 days | IoT devices / REST bridge | TelemetryStreamProcessor |
| `ikb.sensors.processed` | 16 | 7 days | (future) | (future) |
| `ikb.anomalies` | 8 | 30 days | TelemetryStreamProcessor | Dashboards / Alerting |
| `ikb.alerts` | 4 | indefinite | (future alert engine) | (future) |
| `ikb.documents.ingestion` | 4 | default | (future) | (future) |

### TimescaleDB Schema

**Key tables:**

| Table | Type | Partition | Retention |
|---|---|---|---|
| `sensor_readings` | Hypertable | 1-day chunks | 90 days |
| `anomaly_events` | Hypertable | 1-day chunks | 90 days |
| `agent_tasks` | Regular table | — | indefinite |
| `agent_tool_calls` | Regular table | — | indefinite |
| `ingestion_jobs` | Regular table | — | indefinite |

**Continuous aggregates:**

| View | Bucket | Materialises |
|---|---|---|
| `sensor_readings_hourly` | 1 hour | avg, min, max, stddev per sensor |

**Key indexes:**

| Index | Table | Type | Purpose |
|---|---|---|---|
| `(machine_id, recorded_at DESC)` | `sensor_readings` | B-tree | Time-range queries per machine |
| `(machine_id, is_resolved, severity) WHERE NOT is_resolved` | `anomaly_events` | Partial B-tree | Active anomaly dashboard |
| `(machine_id, detected_at DESC)` | `anomaly_events` | B-tree | Anomaly history per machine |

### PostgreSQL Connection Pools

| Service | `min_size` | `max_size` | Workload |
|---|---|---|---|
| Knowledge Engine | 5 | 20 | Agent tasks and RAG queries |
| Telemetry Aggregator | 3 | 10 | Bulk COPY writes dominate |

---

## Roadmap

| Item | Status |
|---|---|
| 6 services consolidated to 3 | Done |
| InfluxDB replaced by TimescaleDB hypertables | Done |
| Zero cross-service imports | Done |
| Kafka KRaft mode (Zookeeper eliminated) | Done |
| Anthropic Claude replaced by Google Gemini 2.5 Flash | Done |
| Qdrant HNSW tuned (m=32, on_disk_payload) | Done |
| spaCy gated behind ENABLE_SPACY_NER flag | Done |
| MLflow lazy import (non-blocking startup) | Done |
| SSE streaming for agent reasoning steps | Done |
| Redis L1 cache on RAG retrieval (10 min TTL) | Done |
| Baseline database migrations (001-004) | Done |
| HTTP POST anomaly escalation (no dedicated Kafka topic) | Done |
| In-process graph_tool and telemetry_tool for agents | Done |
| DevAuthMiddleware for development environments | Done |
| WebSocket relay in API Gateway | Done |
| TimescaleDB cold-data compression | Optional — see migration 004 comments |
| PostgreSQL LISTEN/NOTIFY for SSE (replaces polling) | Planned |
| ML anomaly detector — Tier 3 (requires MLflow model) | Blocked on model training |
| KEDA Kafka-lag autoscaler | Future |
| PostgreSQL row-level security per tenant | Future |
| Graph-RAG hybrid retrieval | Future |
| Merge `rag_application/` and `graph_application/` into `application/` | Planned (low risk) |
| Tool registry expansion: calendar, ERP, notification, parts availability | Future — MaintenanceAgent |

---

## License

MIT License — see [LICENSE](LICENSE) for details.
