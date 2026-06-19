from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict

from backend.services.knowledge_engine.domain.models.tool_call import ToolCall


class AgentResult(BaseModel):
    """Final output from an Agent execution."""
    model_config = ConfigDict(frozen=True)

    task_id: str
    session_id: str
    output_text: str
    tool_calls: List[ToolCall]
    total_latency_ms: float
    total_tokens: int
    confidence: float = 0.0
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None
