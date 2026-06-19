import logging
from typing import Any, List

from backend.services.knowledge_engine.agents.base_agent import BaseIndustrialAgent
from backend.services.knowledge_engine.domain.models.agent_task import AgentTask
from backend.services.knowledge_engine.domain.models.agent_result import AgentResult

logger = logging.getLogger(__name__)


class MaintenanceAgent(BaseIndustrialAgent):
    """
    Specializes in creating and scheduling work orders.
    """

    @property
    def system_prompt(self) -> str:
        return (
            "You are an expert Maintenance Planner. Your task is to generate actionable, safe Maintenance Work Orders.\n"
            "You must identify the required steps, necessary spare parts, estimated duration, required technician skills, "
            "and all safety requirements (e.g. LOTO, confined space permits).\n"
            "Do not perform root cause analysis. Focus strictly on executing the requested maintenance effectively."
        )

    @property
    def allowed_tools(self) -> List[str]:
        # Only rag_search is currently registered in the tool_registry.
        # TODO: wire calendar_tool, erp_tool, notification_tool,
        #       parts_availability_tool when ERP/CMMS integration is implemented.
        return ["rag_search"]

    async def pre_process(self, input_task: AgentTask) -> AgentTask:
        return input_task

    async def post_process(self, output_result: AgentResult) -> AgentResult:
        # Standardize formatting to MaintenanceWorkOrder schema conceptually
        return output_result
