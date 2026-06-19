"""
backend/services/telemetry_aggregator/application/cache/redis_cache.py

Local TelemetryRedisCache — replaces the deleted telemetry_service import.
Provides Redis-backed sensor stats (Welford online algorithm) and anomaly dedup.
"""
from __future__ import annotations

import json
import logging
import math
import time
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

# ── TTL constants ─────────────────────────────────────────────────────────────
_STATS_TTL_SECONDS    = 86_400   # 24 h — sensor baseline stats
_RECENT_ANOMALY_TTL   = 3_600    # 1 h  — recent anomaly log
_DEDUP_WINDOW_SECONDS = 300      # 5 min — suppression window


class TelemetryRedisCache:
    """
    Redis-backed cache for:
      - Per-sensor Welford rolling stats (mean, std_dev, count)
      - Anomaly deduplication window (suppresses repeat alerts)
      - Recent anomaly log per machine (for ML detector rolling window)
      - Latest-value store (for /machines/{id}/latest REST endpoint)
    """

    def __init__(self, client) -> None:
        """
        Args:
            client: An async Redis client (redis.asyncio.Redis).
        """
        self.client = client

    # ── Sensor Statistics (Welford online algorithm) ──────────────────────────

    async def get_sensor_stats(self, sensor_id: str) -> Optional[Dict[str, Any]]:
        """Return rolling {mean, std_dev, count} for sensor_id, or None."""
        raw = await self.client.get(f"ta:stats:{sensor_id}")
        if raw is None:
            return None
        return json.loads(raw)

    async def update_sensor_stats(self, sensor_id: str, value: float) -> None:
        """
        Welford's online mean/variance update — O(1) per reading, numerically stable.
        Persists updated stats to Redis with a 24-hour TTL.
        """
        key = f"ta:stats:{sensor_id}"
        raw = await self.client.get(key)

        if raw:
            stats = json.loads(raw)
            count   = stats["count"]
            mean    = stats["mean"]
            m2      = stats.get("m2", 0.0)
        else:
            count, mean, m2 = 0, 0.0, 0.0

        count  += 1
        delta   = value - mean
        mean   += delta / count
        delta2  = value - mean
        m2     += delta * delta2

        std_dev = math.sqrt(m2 / count) if count > 1 else 0.0

        await self.client.setex(
            key,
            _STATS_TTL_SECONDS,
            json.dumps({"count": count, "mean": mean, "std_dev": std_dev, "m2": m2}),
        )

    # ── Anomaly Deduplication ─────────────────────────────────────────────────

    async def is_duplicate_anomaly(
        self,
        sensor_id: str,
        severity: str,
        window_seconds: int = _DEDUP_WINDOW_SECONDS,
    ) -> bool:
        """Return True if the same (sensor_id, severity) anomaly was seen within window_seconds."""
        key = f"ta:dedup:{sensor_id}:{severity}"
        exists = await self.client.exists(key)
        if not exists:
            await self.client.setex(key, window_seconds, "1")
        return bool(exists)

    async def add_recent_anomaly(
        self,
        machine_id: str,
        anomaly_dict: Dict[str, Any],
        timestamp: float,
    ) -> None:
        """Append anomaly to the per-machine recent anomaly list (capped at 100 entries)."""
        key = f"ta:anomalies:recent:{machine_id}"
        entry = json.dumps({**anomaly_dict, "logged_at": timestamp})
        pipe = self.client.pipeline()
        pipe.rpush(key, entry)
        pipe.ltrim(key, -100, -1)
        pipe.expire(key, _RECENT_ANOMALY_TTL)
        await pipe.execute()

    # ── Machine Rules (for RuleDetector) ─────────────────────────────────────

    async def get_machine_rules(self, machine_id: str) -> List[Dict[str, Any]]:
        """Return cached alert rules for a machine, or [] if none cached."""
        raw = await self.client.get(f"ta:rules:{machine_id}")
        if raw is None:
            return []
        return json.loads(raw)

    async def set_machine_rules(
        self,
        machine_id: str,
        rules: List[Dict[str, Any]],
        ttl: int = 300,
    ) -> None:
        """Cache rules for machine_id with a 5-minute TTL."""
        await self.client.setex(f"ta:rules:{machine_id}", ttl, json.dumps(rules))

    # ── Latest-value store (for /latest endpoint) ─────────────────────────────

    async def set_latest(self, machine_id: str, sensor_id: str, reading: Dict[str, Any]) -> None:
        """Update the latest reading for a machine/sensor pair. TTL = 30 s."""
        key = f"ta:latest:{machine_id}"
        await self.client.hset(key, sensor_id, json.dumps(reading))
        await self.client.expire(key, 30)

    async def get_latest(self, machine_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Return up to `limit` latest readings for all sensors on a machine."""
        raw = await self.client.hgetall(f"ta:latest:{machine_id}")
        results = []
        for sensor_id, val in list(raw.items())[:limit]:
            try:
                parsed = json.loads(val)
                parsed["sensor_id"] = sensor_id.decode() if isinstance(sensor_id, bytes) else sensor_id
                results.append(parsed)
            except (json.JSONDecodeError, AttributeError):
                continue
        return results
