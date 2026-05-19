import logging
from typing import Any, Dict

from backend.services.agent_service.src.infrastructure.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


class RagTool(BaseTool):
    """
    Tool to interface with the RAG Service to fetch semantic chunks from manuals and reports.
    """
    name = "rag_search"
    description = "Search maintenance manuals, incident reports, and technical documents for semantic information."
    
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query (e.g., 'how to replace spindle bearing')"
            },
            "machine_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of machine IDs to filter by"
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return",
                "default": 5
            },
            "doc_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional document types to filter (e.g., 'manual', 'incident_report')"
            }
        },
        "required": ["query"]
    }

    def __init__(self, rag_client: Any = None) -> None:
        self.rag_client = rag_client  # Inject gRPC/REST client

    async def _execute_impl(self, params: Dict[str, Any]) -> Any:
        if self.rag_client is None:
            raise RuntimeError("RagTool: rag_client is not configured")

        query = params.get("query")
        if not query:
            raise ValueError("Query is required for RagTool")

        logger.info("Executing RAG Search with query: '%s'", query)
        
        body = {
            "query": query,
            "top_k": params.get("top_k", 5),
            "filters": {
                "machine_ids": params.get("machine_ids"),
                "doc_types": params.get("doc_types")
            }
        }
        
        try:
            response = await self.rag_client.post("/api/v1/retrieve", json=body)
            response.raise_for_status()
            data = response.json()
            return data.get("chunks", [])
        except Exception as e:
            logger.error("RagTool execution failed: %s", str(e))
            raise ValueError(f"Failed to fetch RAG context: {str(e)}")
