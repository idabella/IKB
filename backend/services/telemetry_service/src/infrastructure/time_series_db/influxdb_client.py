from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from influxdb_client import BucketRetentionRules, Point
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.write_api_async import WriteApiAsync

logger = logging.getLogger(__name__)

# Retention policy definitions: bucket name → retention in seconds.
# telemetry_raw  :  7 days   (604_800 s)
# telemetry_1min : 30 days   (2_592_000 s)
# telemetry_1hr  : 365 days  (31_536_000 s)
_BUCKET_RETENTION: Dict[str, int] = {
    "telemetry_raw": 604_800,
    "telemetry_1min": 2_592_000,
    "telemetry_1hr": 31_536_000,
}


@dataclass
class SensorReading:
    sensor_id: str
    machine_id: str
    value: float
    timestamp: float  # Unix epoch


@dataclass
class DataPoint:
    timestamp: float
    value: float


class AsyncInfluxDBClient:
    """
    High-throughput async wrapper for InfluxDB v2.
    Uses Batched Line Protocol for writes.
    """

    def __init__(self, url: str, token: str, org: str, bucket: str) -> None:
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.client: InfluxDBClientAsync | None = None
        self.write_api: WriteApiAsync | None = None

    async def connect(self) -> None:
        self.client = InfluxDBClientAsync(url=self.url, token=self.token, org=self.org)
        self.write_api = self.client.write_api()
        logger.info(
            "Connected to InfluxDB at %s (org=%s bucket=%s)",
            self.url,
            self.org,
            self.bucket,
        )
        await self._ensure_retention_policies()

    async def close(self) -> None:
        if self.client:
            await self.client.close()
            logger.info("Closed InfluxDB connection.")

    # -------------------------------------------------------------------------
    # Retention policy enforcement
    # -------------------------------------------------------------------------

    async def _ensure_retention_policies(self) -> None:
        """Create or update the three canonical telemetry buckets with correct
        retention rules.

        Buckets managed:
            telemetry_raw   →  7 days   (604 800 s)
            telemetry_1min  →  30 days  (2 592 000 s)
            telemetry_1hr   →  365 days (31 536 000 s)

        Per-bucket failures are caught and logged as WARNING so a single
        permission error does not abort the entire initialisation sequence.
        """
        if self.client is None:
            raise ConnectionError(
                "InfluxDB client not initialised — call connect() first."
            )

        buckets_api = self.client.buckets_api()

        for bucket_name, retention_seconds in _BUCKET_RETENTION.items():
            try:
                retention_rule = BucketRetentionRules(
                    type="expire",
                    every_seconds=retention_seconds,
                )

                existing = buckets_api.find_bucket_by_name(bucket_name)

                if existing is None:
                    # Bucket does not exist — create it from scratch.
                    buckets_api.create_bucket(
                        bucket_name=bucket_name,
                        retention_rules=retention_rule,
                        org=self.org,
                    )
                    logger.info(
                        "Created bucket '%s' with retention=%d s (%d days)",
                        bucket_name,
                        retention_seconds,
                        retention_seconds // 86_400,
                    )
                else:
                    # Bucket exists — overwrite retention rules in place.
                    existing.retention_rules = [retention_rule]
                    buckets_api.update_bucket(bucket=existing)
                    logger.info(
                        "Updated bucket '%s' retention to %d s (%d days)",
                        bucket_name,
                        retention_seconds,
                        retention_seconds // 86_400,
                    )

            except Exception:
                # Log and continue so one bad bucket does not abort the rest.
                logger.warning(
                    "Failed to create/update retention policy for bucket '%s' — "
                    "manual intervention may be required.",
                    bucket_name,
                    exc_info=True,
                )

    # -------------------------------------------------------------------------
    # Write
    # -------------------------------------------------------------------------

    async def write_batch(self, readings: List[SensorReading]) -> None:
        """Write a batch of sensor readings using high-performance line protocol."""
        if not self.write_api or not readings:
            return

        points: List[Point] = []
        for r in readings:
            point = (
                Point("sensor_data")
                .tag("machine_id", r.machine_id)
                .tag("sensor_id", r.sensor_id)
                .field("value", float(r.value))
                .time(int(r.timestamp * 1e9))  # InfluxDB expects nanoseconds
            )
            points.append(point)

        try:
            await self.write_api.write(
                bucket=self.bucket, org=self.org, record=points
            )
        except Exception as exc:
            logger.error("Failed to write batch to InfluxDB: %s", exc, exc_info=True)
            raise

    # -------------------------------------------------------------------------
    # Query
    # -------------------------------------------------------------------------

    async def query_range(
        self,
        machine_id: str,
        metric_name: str,
        start_time: str,
        end_time: str,
        bucket: str | None = None,
    ) -> List[Dict[str, Any]]:
        """Query historical time-series data with 1-minute mean aggregation.

        Args:
            machine_id:  Tag value used to filter ``machine_id`` in InfluxDB.
            metric_name: Field name to filter on (maps to ``r._field``).
            start_time:  Flux-compatible start time (e.g. ``"-1h"`` or RFC3339).
            end_time:    Flux-compatible stop time (e.g. ``"now()"`` or RFC3339).
            bucket:      Override the instance-level bucket if provided.

        Returns:
            List of dicts: ``{"timestamp": str, "metric_name": str, "value": float}``.

        Raises:
            ConnectionError: If the InfluxDB client has not been initialised.
            RuntimeError:    On any query execution failure.
        """
        if self.client is None:
            raise ConnectionError(
                "InfluxDB client not initialised — call connect() first."
            )

        target_bucket: str = bucket or self.bucket

        flux_query: str = f"""
from(bucket: "{target_bucket}")
  |> range(start: {start_time}, stop: {end_time})
  |> filter(fn: (r) =>
      r._measurement == "sensor_data" and
      r.machine_id == "{machine_id}" and
      r._field == "{metric_name}"
  )
  |> aggregateWindow(every: 1m, fn: mean, createEmpty: false)
"""

        try:
            query_api = self.client.query_api()
            result = await query_api.query(query=flux_query, org=self.org)

            data_points: List[Dict[str, Any]] = []
            for table in result:
                for record in table.records:
                    data_points.append(
                        {
                            "timestamp": record.get_time().isoformat(),
                            "metric_name": metric_name,
                            "value": float(record.get_value()),
                        }
                    )

            logger.debug(
                "query_range: machine_id=%s metric=%s bucket=%s rows=%d",
                machine_id,
                metric_name,
                target_bucket,
                len(data_points),
            )

            return data_points

        except Exception as exc:
            logger.error(
                "InfluxDB query failed — machine_id=%s metric=%s bucket=%s",
                machine_id,
                metric_name,
                target_bucket,
                exc_info=True,
            )
            raise RuntimeError(f"InfluxDB query failed: {str(exc)}") from exc