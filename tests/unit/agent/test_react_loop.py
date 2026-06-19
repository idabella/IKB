import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.services.knowledge_engine.domain.models.agent_task import AgentTask
from backend.services.knowledge_engine.agents.base_agent import BaseIndustrialAgent
from backend.services.knowledge_engine.llm.gemini_client import GeminiClient, NormalizedBlock, NormalizedResponse, UsageInfo
from backend.services.knowledge_engine.tools.base_tool import BaseTool, ToolResult


class MockTool(BaseTool):
    name = "mock_tool"
    description = "A mock tool"
    input_schema = {"type": "object", "properties": {}}

    async def _execute_impl(self, params):
        return "mock_tool_success"


class MockAgent(BaseIndustrialAgent):
    @property
    def system_prompt(self):
        return "Mock system prompt"

    @property
    def allowed_tools(self):
        return ["mock_tool"]

    async def pre_process(self, input_task):
        return input_task

    async def post_process(self, output_result):
        return output_result


def _make_text_response(text: str) -> NormalizedResponse:
    """Helper: build a NormalizedResponse with a single text block."""
    return NormalizedResponse(
        content=[NormalizedBlock(type="text", text=text)],
        usage=UsageInfo(input_tokens=10, output_tokens=10),
    )


def _make_tool_use_response(text: str, tool_name: str) -> NormalizedResponse:
    """Helper: build a NormalizedResponse with a text block + a tool_use block."""
    return NormalizedResponse(
        content=[
            NormalizedBlock(type="text", text=text),
            NormalizedBlock(
                type="tool_use",
                name=tool_name,
                id="call_123",
                input={},
            ),
        ],
        usage=UsageInfo(input_tokens=10, output_tokens=10),
    )


@pytest.mark.asyncio
async def test_react_loop_execution():
    # 1. Setup Memory Mock
    mock_memory = AsyncMock()
    mock_memory.get_history.return_value = []

    # 2. Setup Tool Registry
    mock_tool = MockTool()
    tool_registry = {"mock_tool": mock_tool}

    # 3. Setup LLM Mock — spec against GeminiClient (was AnthropicClient)
    mock_llm = AsyncMock(spec=GeminiClient)

    # Simulate ReAct Loop Responses:
    # Step 1: LLM decides to use the tool
    step_1_response = _make_tool_use_response("Let me use the tool.", "mock_tool")

    # Step 2: LLM provides final answer based on tool output
    step_2_response = _make_text_response("The tool was successful.")

    # Configure LLM to return Step 1 then Step 2
    mock_llm.complete.side_effect = [step_1_response, step_2_response]

    # 4. Initialize Agent
    agent = MockAgent(llm_client=mock_llm, tool_registry=tool_registry, memory_store=mock_memory)

    # 5. Execute
    task = AgentTask(session_id="sesh_1", tenant_id="tenant_1", task_id="task_1", query="Do something.")
    result = await agent.run(task)

    # 6. Verify
    # LLM should have been called twice
    assert mock_llm.complete.call_count == 2

    # Output should be the final text
    assert result.output_text == "Let me use the tool.The tool was successful."

    # Tool call should have been recorded
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "mock_tool"
    assert result.tool_calls[0].success is True
    assert result.tool_calls[0].output == "mock_tool_success"
