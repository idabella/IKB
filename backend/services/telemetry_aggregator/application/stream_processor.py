from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

import asyncpg
import httpx
import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from prometheus_client import Counter, Histogram

# ── Local imports ─────────────────────────────────────────────────────────────
from backend.services.telemetry_aggregator.application.cache.redis_cache import TelemetryRedisCache
from backend.services.telemetry_aggregator.application.detectors.rule_detector import RuleDetector
from backend.services.telemetry_aggregator.application.detectors.statistical_detector import StatisticalDetector
# MLDetector removed — no model exists; stat_detector is the effective final tier.

logger = structlog.get_logger(__name__)

# ── Prometheus Metrics ────────────────────────────────────────────────────────
MESSAGES_PROCESSED = Counter(
    "ta_messages_processed_total",
    "Total telemetry messages processed by the Telemetry Aggregator",
)
PROCESSING_LATENCY = Histogram(
    "ta_processing_latency_ms",
    "Batch processing latency in milliseconds",
    buckets=[10, 25, 50, 100, 200, 500],
)
ANOMALIES_DETECTED = Counter(
    "ta_anomalies_detected_total",
    "Total anomalies detected",
    ["severity", "detector_type"],
)
DETECTOR_ERRORS = Counter(
    "ta_detector_errors_total",
    "Errors during anomaly detection",
)
TIMESCALE_WRITES = Counter(
    "ta_timescaledb_writes_total",
    "Total sensor readings written to TimescaleDB",
)


@dataclass
class SensorReading:
    """Canonical sensor reading schema (replaces the InfluxDB-specific model)."""
    sensor_id:  str
    machine_id: str
    tenant_id:  str
    value:      float
    unit:       str = ""
    quality:    int = 100
    timestamp:  float = 0.0  # Unix epoch seconds; 0 = use NOW()

    @property
    def recorded_at(self):
        """Return an ISO-8601 string for asyncpg, or None to use DB NOW()."""
        import datetime
        if self.timestamp:
            return datetime.datetime.fromtimestamp(self.timestamp, tz=datetime.timezone.utc)
        return None


class TelemetryStreamProcessor:
    """
    High-throughput async stream processor for industrial sensor telemetry.

    Flow (v2.3):
      Kafka: ikb.sensors.raw
        → parse batch
        → asyncio.gather(
              TimescaleDB COPY  (bulk write via asyncpg),
              Rule + Statistical detection  (inline),
          )
        → anomaly_events PostgreSQL INSERT
        → ikb.anomalies Kafka publish (dashboards / alerting)
        → if HIGH/CRITICAL: HTTP POST to KE /internal/agent-tasks  (persistent client)

    v2.3 changes vs. original:
      - InfluxDB client REMOVED — writes go directly to TimescaleDB via asyncpg COPY.
      - ikb.agent.tasks Kafka topic REMOVED — escalation via persistent httpx.AsyncClient.
      - ML detector (Tier 3) REMOVED — no trained model in MLflow; re-add when ready.
      - structlog replaces stdlib logging throughout.
    """

    def __init__(
        self,
        db_pool: asyncpg.Pool,
        redis_cache: TelemetryRedisCache,
        kafka_bootstrap_servers: str = "kafka:29092",
        batch_size: int = 500,
        flush_interval_ms: int = 100,
        knowledge_engine_url: str = "",
    ) -> None:
        self.db_pool            = db_pool
        self.redis_cache        = redis_cache
        self.bootstrap_servers  = kafka_bootstrap_servers
        self.batch_size         = batch_size
        self.flush_interval_seconds = flush_interval_ms / 1000.0
        # Direct HTTP escalation to Knowledge Engine (replaces ikb.agent.tasks topic)
        self._ke_url = knowledge_engine_url or os.getenv("KNOWLEDGE_ENGINE_URL", "http://knowledge-engine:8001")

        # Two-tier detector chain: Rule (O1) → Statistical (Welford Z-score)
        # MLDetector removed — no trained model; re-add when MLflow registry has a model.
        self.stat_detector  = StatisticalDetector(redis_cache=redis_cache)
        self.rule_detector  = RuleDetector(redis_cache=redis_cache)

        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self._running = False

        # Persistent HTTP client — reused across all escalation calls to KE.
        # Avoids TCP handshake (~5–50 ms) on every HIGH/CRITICAL anomaly.
        self._http_client = httpx.AsyncClient(timeout=5.0)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        self.consumer = AIOKafkaConsumer(
            "ikb.sensors.raw",
            bootstrap_servers=self.bootstrap_servers,
            group_id="telemetry_aggregator_group",
            auto_offset_reset="latest",
            enable_auto_commit=False,
        )
        self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        await self.consumer.start()
        await self.producer.start()
        self._running = True
        logger.info("stream_processor_started", bootstrap_servers=self.bootstrap_servers)
        asyncio.create_task(self._consume_loop())

    async def stop(self) -> None:
        self._running = False
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        await self._http_client.aclose()   # close persistent escalation client
        logger.info("stream_processor_stopped")

    # ── Consume Loop ──────────────────────────────────────────────────────────

    async def _consume_loop(self) -> None:
        batch: list = []
        last_flush = time.time()
        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(self.consumer.getone(), timeout=0.01)
                    batch.append(msg)
                except asyncio.TimeoutError:
                    pass

                now = time.time()
                if (len(batch) >= self.batch_size or
                        (now - last_flush) >= self.flush_interval_seconds) and batch:
                    await self._process_batch(batch)
                    await self.consumer.commit()
                    batch = []
                    last_flush = now

        except Exception as exc:
            logger.error("consume_loop_fatal_error", error=str(exc), exc_info=True)

    # ── Batch Processing ──────────────────────────────────────────────────────

    async def _process_batch(self, messages: list) -> None:
        start_time = time.time()
        readings: List[SensorReading] = []

        for msg in messages:
            try:
                data = json.loads(msg.value.decode("utf-8"))
                readings.append(SensorReading(
                    sensor_id=data["sensor_id"],
                    machine_id=data["machine_id"],
                    tenant_id=data.get("tenant_id", "default"),
                    value=float(data["value"]),
                    unit=data.get("unit", ""),
                    quality=int(data.get("quality", 100)),
                    timestamp=float(data.get("timestamp", 0.0)),
                ))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.debug("malformed_message_skipped", error=str(exc))

        if not readings:
            return

        # TimescaleDB COPY + Rule/Statistical detection run concurrently
        results = await asyncio.gather(
            self._write_to_timescaledb(readings),
            self._run_tiered_detection(readings),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                logger.error("batch_subtask_failed", error=str(r))

        MESSAGES_PROCESSED.inc(len(readings))
        PROCESSING_LATENCY.observe((time.time() - start_time) * 1000)

    # ── TimescaleDB Write (replaces InfluxDB) ─────────────────────────────────

    async def _write_to_timescaledb(self, readings: List[SensorReading]) -> None:
        """
        Bulk insert via asyncpg COPY — ~10x faster than individual INSERTs.
        TimescaleDB partitions the rows into 1-day chunks automatically.
        """
        import datetime
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        records = [
            (
                r.sensor_id,
                r.machine_id,
                r.tenant_id,
                r.value,
                r.unit,
                r.quality,
                r.recorded_at or now,
            )
            for r in readings
        ]

        async with self.db_pool.acquire() as conn:
            await conn.copy_records_to_table(
                "sensor_readings",
                records=records,
                columns=["sensor_id", "machine_id", "tenant_id", "value", "unit", "quality", "recorded_at"],
            )

        TIMESCALE_WRITES.inc(len(records))
        logger.debug("timescaledb_write_ok", count=len(records))

    # ── Anomaly Detection (tiered) ────────────────────────────────────────────

    async def _run_tiered_detection(self, readings: List[SensorReading]) -> None:
        """
        Two-tier anomaly detection per reading:
          Tier 1 — RuleDetector: O(1) Redis-cached hard bounds
          Tier 2 — StatisticalDetector: Welford online Z-score (warm-up: 30 samples)

        ML tier (Tier 3) removed — no trained model in MLflow registry.
        Re-introduce MLDetector when a model is registered and tested.
        """
        for r in readings:
            try:
                # Tier 1
                anomaly = await self.rule_detector.detect(r.sensor_id, r.machine_id, r.value, r.timestamp)
                detector_type = "rule"

                # Tier 2
                if not anomaly:
                    anomaly = await self.stat_detector.detect(r.sensor_id, r.machine_id, r.value, r.timestamp)
                    detector_type = "statistical"

                if anomaly:
                    ANOMALIES_DETECTED.labels(severity=anomaly.severity, detector_type=detector_type).inc()
                    await self._handle_anomaly(anomaly, detector_type)

            except Exception as exc:
                DETECTOR_ERRORS.inc()
                logger.error("detector_error", sensor_id=r.sensor_id, error=str(exc))

    # ── Anomaly Handling ──────────────────────────────────────────────────────

    async def _handle_anomaly(self, anomaly, detector_type: str) -> None:
        """Persist to PostgreSQL, publish to Kafka, escalate if CRITICAL/HIGH."""
        anomaly_id = str(uuid.uuid4())
        anomaly_dict = {**anomaly.__dict__, "anomaly_id": anomaly_id, "detector_type": detector_type}
        payload = json.dumps(anomaly_dict).encode("utf-8")

        # 1. Persist to anomaly_events hypertable
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO anomaly_events
                        (anomaly_id, machine_id, sensor_id, tenant_id, severity, value,
                         detector_type, detected_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                    ON CONFLICT (anomaly_id) DO NOTHING
                    """,
                    anomaly_id,
                    anomaly.machine_id,
                    anomaly.sensor_id,
                    getattr(anomaly, "tenant_id", "default"),
                    anomaly.severity,
                    anomaly.value,
                    detector_type,
                )
        except Exception as exc:
            logger.error("anomaly_persist_failed", anomaly_id=anomaly_id, error=str(exc))

        # 2. Standard anomaly feed (dashboards / Prometheus alerts consumer)
        await self.producer.send_and_wait(
            "ikb.anomalies",
            value=payload,
            key=anomaly.machine_id.encode("utf-8"),
        )

        # 3. Escalate HIGH/CRITICAL → Knowledge Engine via direct HTTP POST
        #    Replaces ikb.agent.tasks Kafka topic — same logic, 0 Kafka overhead.
        #    < 10 escalations/min at peak — HTTP is sufficient and simpler.
        if anomaly.severity in ("HIGH", "CRITICAL"):
            agent_task = {
                "task_type":     "anomaly_analysis",
                "machine_id":    anomaly.machine_id,
                "sensor_id":     anomaly.sensor_id,
                "severity":      anomaly.severity,
                "trigger_value": anomaly.value,
                "anomaly_id":    anomaly_id,
            }
            try:
                resp = await self._http_client.post(
                    f"{self._ke_url}/api/v1/internal/agent-tasks",
                    json=agent_task,
                )
                resp.raise_for_status()
                logger.info(
                    "anomaly_escalated_to_ke",
                    machine_id=anomaly.machine_id,
                    severity=anomaly.severity,
                    anomaly_id=anomaly_id,
                    status=resp.status_code,
                )
            except Exception as exc:
                # Best-effort — persist + anomalies feed already succeeded
                logger.error(
                    "ke_escalation_failed",
                    anomaly_id=anomaly_id,
                    error=str(exc),
                )
