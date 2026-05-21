import logging
from typing import Any, Dict

from backend.services.agent_service.src.infrastructure.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


class GraphTool(BaseTool):
    """
    Tool to interface with the Knowledge Graph Service to traverse
    causality and topology.
    """

    name = "graph_query"

    description = (
        "Query the industrial knowledge graph for machine components, "
        "failure modes, and causal chains."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "query_type": {
                "type": "string",
                "enum": [
                    "failure_chain",
                    "health_subgraph",
                    "causal_analysis",
                ],
                "description": "The type of graph query to execute",
            },
            "machine_id": {
                "type": "string",
                "description": (
                    "Target machine ID "
                    "(required for failure_chain and health_subgraph)"
                ),
            },
            "component_id": {
                "type": "string",
                "description": "Target component ID",
            },
            "sensor_id": {
                "type": "string",
                "description": (
                    "Target sensor ID "
                    "(required for causal_analysis)"
                ),
            },
        },
        "required": ["query_type"],
    }

    def __init__(self, graph_client: Any) -> None:
        self.graph_client = graph_client

    async def _execute_impl(
        self,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        query_type: str | None = params.get("query_type")
        machine_id: str | None = params.get("machine_id")
        component_id: str | None = params.get("component_id")
        sensor_id: str | None = params.get("sensor_id")

        if self.graph_client is None:
            logger.error(
                "Graph client is required but not configured."
            )
            raise RuntimeError(
                "Graph client is required but not configured."
            )

        logger.info(
            "Executing graph query query_type=%s machine_id=%s",
            query_type,
            machine_id,
        )

        try:
            if query_type == "causal_analysis":
                return await self.graph_client.causal_analysis(
                    sensor_id=sensor_id,
                )

            if query_type == "health_subgraph":
                return await self.graph_client.get_health_subgraph(
                    machine_id=machine_id,
                )

            if query_type == "failure_chain":
                return await self.graph_client.get_failure_chain(
                    machine_id=machine_id,
                    component_id=component_id,
                )

            raise ValueError(
                f"Unsupported graph query type: {query_type}"
            )

        except Exception:
            logger.error(
                "Graph query execution failed for query_type=%s "
                "machine_id=%s",
                query_type,
                machine_id,
                exc_info=True,
            )
            raise
