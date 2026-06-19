from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

from backend.services.knowledge_engine.agents.base_agent import BaseIndustrialAgent
from backend.services.knowledge_engine.domain.models.agent_task import AgentTask
from backend.services.knowledge_engine.domain.models.agent_result import AgentResult
from backend.shared.infrastructure.messaging.kafka_producer import KafkaMessageProducer

logger = logging.getLogger(__name__)

_ESCALATION_TOPIC: str = "ikb.anomalies.escalation"


class MonitoringAgent(BaseIndustrialAgent):
    """
    Level-1 Anomaly Triage Agent.

    Evaluates incoming anomalies to determine the required response level,
    then publishes an escalation event to Kafka for downstream pipelines.

    A singleton KafkaMessageProducer is injected at construction time (started
    and stopped by the FastAPI lifespan in main.py). This avoids opening a new
    TCP connection to the broker on every escalation event, which previously
    cost 100–200 ms per call and risked connection leaks on exception.
    """

    def __init__(
        self,
        llm_client: Any,
        tool_registry: Dict[str, Any],
        memory_store: Any,
        kafka_producer: KafkaMessageProducer,
        max_steps: int = 10,
        max_tokens_per_step: int = 2000,
    ) -> None:
        super().__init__(
            llm_client=llm_client,
            tool_registry=tool_registry,
            memory_store=memory_store,
            max_steps=max_steps,
            max_tokens_per_step=max_tokens_per_step,
        )
        self._producer = kafka_producer  # singleton — never started/stopped here

    @property
    def system_prompt(self) -> str:
        return (
            "You are a Level 1 Anomaly Triage Agent.\n"
            "Analyze the incoming anomaly event and decide the exact required escalation path.\n"
            "You must output ONE of the following decisions exactly:\n"
            "1. monitor_only (for minor fluctuations within tolerance)\n"
            "2. escalate_to_rca (for complex, unexplainable issues requiring deep analysis)\n"
            "3. create_work_order (for known, easily actionable wear-and-tear)\n"
            "4. page_on_call (for critical, plant-halting emergencies)\n"
            "Base your decision on the anomaly severity, frequency, and historical context."
        )

    @property
    def allowed_tools(self) -> List[str]:
        # Only rag_search is registered in the tool_registry.
        # get_telemetry and graph_query are roadmap items.
        return ["rag_search"]

    async def pre_process(self, input_task: AgentTask) -> AgentTask:
        return input_task

    async def post_process(self, output_result: AgentResult) -> AgentResult:
        """Publish the triage decision to Kafka as a downstream escalation event.

        Uses the injected singleton producer — no connect/disconnect overhead.
        The publish is best-effort: a failure is logged at ERROR level but never
        swallows ``output_result``, which is always returned to the caller.

        Args:
            output_result: Completed AgentResult from the ReAct loop.

        Returns:
            The unchanged ``output_result``, with or without a successful publish.
        """
        escalation_payload: Dict[str, Any] = {
            "task_id": output_result.task_id,
            "output_text": output_result.output_text,
            "confidence": output_result.confidence,
            "tenant_id": output_result.metadata.get("tenant_id") if output_result.metadata else None,
            "timestamp": datetime.utcnow().isoformat(),
            "agent_type": "monitoring",
        }

        try:
            await self._producer.send(
                topic=_ESCALATION_TOPIC,
                value=escalation_payload,
                key=output_result.task_id,
            )
            logger.info(
                "Escalation event published — task_id=%s topic=%s tenant_id=%s",
                output_result.task_id,
                _ESCALATION_TOPIC,
                escalation_payload["tenant_id"],
            )

        except Exception:
            # Kafka failure must never drop the result — downstream consumers
            # can replay; the agent result is the source of truth here.
            logger.error(
                "Failed to publish escalation event for task_id=%s topic=%s",
                output_result.task_id,
                _ESCALATION_TOPIC,
                exc_info=True,
            )

        return output_result