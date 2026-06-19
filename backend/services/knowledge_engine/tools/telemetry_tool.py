import logging


from backend.services.knowledge_engine.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


from typing import Any, Dict, List





class TelemetryTool(BaseTool):
    """
    Tool to interface with the Telemetry Service (InfluxDB) for sensor time-series data.
    """

    name = "get_telemetry"
    description = (
        "Retrieve sensor readings and telemetry data for a machine "
        "over a specific time period."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "machine_id": {
                "type": "string",
                "description": "The ID of the machine",
            },
            "metric_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of metric names "
                    "(e.g., ['temperature', 'vibration'])"
                ),
            },
            "start_time": {
                "type": "string",
                "description": "ISO-8601 start timestamp",
            },
            "end_time": {
                "type": "string",
                "description": "ISO-8601 end timestamp",
            },
            "aggregation": {
                "type": "string",
                "enum": ["mean", "max", "min", "raw"],
                "default": "raw",
                "description": "How to aggregate the data points",
            },
        },
        "required": [
            "machine_id",
            "metric_names",
            "start_time",
            "end_time",
        ],
    }

    def __init__(self, telemetry_client: Any) -> None:
        self.telemetry_client = telemetry_client

    async def _execute_impl(
        self,
        params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        machine_id: str | None = params.get("machine_id")
        metrics: List[str] = params.get("metric_names", [])
        start_time: str | None = params.get("start_time")
        end_time: str | None = params.get("end_time")
        aggregation: str = params.get("aggregation", "raw")

        if self.telemetry_client is None:
            logger.error(
                "Telemetry client is required but not configured."
            )
            raise RuntimeError(
                "Telemetry client is required but not configured."
            )

        if machine_id is None or not metrics:
            raise ValueError(
                "machine_id and metric_names are required"
            )

        logger.info(
            "Executing telemetry fetch for machine_id=%s metrics=%s "
            "start_time=%s end_time=%s aggregation=%s",
            machine_id,
            metrics,
            start_time,
            end_time,
            aggregation,
        )

        results: List[Dict[str, Any]] = []

        try:
            for metric_name in metrics:
                metric_results: List[Dict[str, Any]] = (
                    await self.telemetry_client.query_range(
                        machine_id=machine_id,
                        metric_name=metric_name,
                        start_time=start_time,
                        end_time=end_time,
                        aggregation=aggregation,
                    )
                )

                results.extend(metric_results)

        except Exception:
            logger.error(
                "Telemetry query failed for machine_id=%s metric=%s",
                machine_id,
                metric_name,
                exc_info=True,
            )
            raise

        return results