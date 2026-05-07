"""
Tests for FastMCP-based MCP Hub Server.

Run with: python -m pytest tests/test_mcp_hub.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure cc_router is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cc_router.mcp_hub_server import (
    mcp,
    MCPHubServer,
    MCPAgentBridge,
    SubmitTaskInput,
    RegisterCCInput,
    ListCCInput,
    ConnectAgentInput,
    DisconnectAgentInput,
    _format_cc_instance,
    _format_agent_node,
)


# ── Mock Context ──────────────────────────────────────────────────────


class MockHub:
    """Mock UniversalRouterHub for testing tool functions."""

    def __init__(self, cc_instance, agent_node, task):
        self.registry = MagicMock()
        self.cc_registry = MagicMock()
        self.router = MagicMock()
        self.event_bus = MagicMock()

        # mock task tracking
        self._tasks = {"task_001": task}

        # registry mock
        self.registry.get_sync = MagicMock(return_value=None)
        self.registry.list_all_sync = MagicMock(return_value=[agent_node])

        # cc_registry mock
        self.cc_registry.list_all = MagicMock(return_value=[cc_instance])
        self.cc_registry.list_by_status = MagicMock(return_value=[cc_instance])

        # submit_task mock
        self.submit_task = AsyncMock(return_value="task_001")

        # router mock
        route_result = MagicMock()
        route_result.cc_id = "cc_test_01"
        self.router.route = AsyncMock(return_value=route_result)

    def connect_agent(self, agent_id, adapter):
        self.registry.get_sync = MagicMock(return_value=MagicMock(agent_id=agent_id))
        self.registry.register_sync(agent_id, adapter)

    def disconnect_agent(self, agent_id):
        self.registry.get_sync = MagicMock(return_value=None)

    def register_cc(self, adapter):
        return adapter.cc_id

    def list_tasks(self):
        return list(self._tasks.values())


def make_context(mock_hub):
    """Build a minimal Context-like object for tool testing."""
    return MagicMock(
        request_context=MagicMock(
            lifespan_context={"hub": mock_hub},
        ),
        info=AsyncMock(),
        debug=AsyncMock(),
        warning=AsyncMock(),
        error=AsyncMock(),
    )


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_cc_instance():
    """Create a mock CCInstance-like object."""
    inst = MagicMock()
    inst.cc_id = "cc_test_01"
    inst.workspace = "/tmp/test"
    inst.tag = ["ml", "test"]
    inst.capability = ["code", "research"]
    inst.status = "idle"
    inst.session_id = "sess_001"
    inst.pid = 12345
    return inst


@pytest.fixture
def mock_agent_node():
    """Create a mock AgentNode-like object."""
    node = MagicMock()
    node.agent_id = "agent_test_01"
    node.protocol = "mcp"
    node.connected_at = "2026-05-07T12:00:00"
    node.last_seen = "2026-05-07T12:00:00"
    node.metadata = {"version": "1.0"}
    return node


@pytest.fixture
def mock_task():
    """Create a mock Task-like object."""
    task = MagicMock()
    task.task_id = "task_001"
    task.caller_agent_id = "mcp-client"
    task.cc_id = "cc_test_01"
    task.status = "done"
    task.task = "test task"
    return task


@pytest.fixture
def mock_hub(mock_cc_instance, mock_agent_node, mock_task):
    """Provide a MockHub instance."""
    return MockHub(mock_cc_instance, mock_agent_node, mock_task)


@pytest.fixture
def ctx(mock_hub):
    """Provide a mock Context with the mock_hub injected."""
    return make_context(mock_hub)


# ── Tests: Pydantic Models ────────────────────────────────────────────


class TestPydanticModels:
    """Pydantic input model validation."""

    def test_submit_task_input_required(self):
        m = SubmitTaskInput(task="hello")
        assert m.task == "hello"
        assert m.tag is None
        assert m.timeout == 300.0
        assert m.agent_id == "mcp-client"

    def test_submit_task_input_all_fields(self):
        m = SubmitTaskInput(
            task="test",
            tag="code",
            capability=["code"],
            timeout=60.0,
            agent_id="my-agent",
        )
        assert m.tag == "code"
        assert m.capability == ["code"]
        assert m.timeout == 60.0
        assert m.agent_id == "my-agent"

    def test_register_cc_input_required(self):
        m = RegisterCCInput(cc_id="my-cc", workspace="/tmp")
        assert m.cc_id == "my-cc"
        assert m.capabilities == ["general"]

    def test_list_cc_input_default(self):
        m = ListCCInput()
        assert m.status is None

    def test_list_cc_input_with_status(self):
        m = ListCCInput(status="idle")
        assert m.status == "idle"

    def test_connect_agent_input(self):
        m = ConnectAgentInput(agent_id="agent-1")
        assert m.agent_id == "agent-1"
        assert m.type == "mcp"

    def test_disconnect_agent_input(self):
        m = DisconnectAgentInput(agent_id="agent-1")
        assert m.agent_id == "agent-1"


# ── Tests: Tool Definitions ───────────────────────────────────────────


class TestToolDefinitions:
    """Verify all expected tools are defined on the FastMCP instance."""

    TOOL_NAMES = {
        "synapse_submit_task",
        "synapse_register_cc",
        "synapse_list_cc_instances",
        "synapse_list_agents",
        "synapse_hub_status",
        "synapse_connect_agent",
        "synapse_disconnect_agent",
    }

    @pytest.mark.asyncio
    async def test_all_tools_present(self):
        """FastMCP should have all 7 tools registered."""
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        assert tool_names == self.TOOL_NAMES, f"Missing: {self.TOOL_NAMES - tool_names}"

    @pytest.mark.asyncio
    async def test_submit_task_schema(self):
        """submit_task should have 'task' as required via Pydantic model."""
        tools = await mcp.list_tools()
        t = next(x for x in tools if x.name == "synapse_submit_task")
        schema = t.inputSchema
        # FastMCP wraps the Pydantic model under $defs
        defs = schema.get("$defs", {})
        model_key = next(k for k in defs if "SubmitTaskInput" in k)
        model_schema = defs[model_key]
        props = model_schema.get("properties", {})
        assert "task" in props
        assert "tag" in props
        assert "capability" in props
        assert "timeout" in props
        assert "agent_id" in props
        assert "task" in model_schema.get("required", [])

    @pytest.mark.asyncio
    async def test_register_cc_schema(self):
        """register_cc should require cc_id and workspace."""
        tools = await mcp.list_tools()
        t = next(x for x in tools if x.name == "synapse_register_cc")
        schema = t.inputSchema
        defs = schema.get("$defs", {})
        model_key = next(k for k in defs if "RegisterCCInput" in k)
        model_schema = defs[model_key]
        props = model_schema.get("properties", {})
        assert "cc_id" in props
        assert "workspace" in props
        assert "tags" in props
        assert "capabilities" in props
        required = model_schema.get("required", [])
        assert "cc_id" in required
        assert "workspace" in required

    @pytest.mark.asyncio
    async def test_list_cc_instances_schema(self):
        """list_cc_instances should have optional status filter."""
        tools = await mcp.list_tools()
        t = next(x for x in tools if x.name == "synapse_list_cc_instances")
        schema = t.inputSchema
        defs = schema.get("$defs", {})
        model_key = next(k for k in defs if "ListCCInput" in k)
        assert "status" in defs[model_key].get("properties", {})

    @pytest.mark.asyncio
    async def test_tools_have_descriptions(self):
        """All tools should have non-empty descriptions."""
        tools = await mcp.list_tools()
        for t in tools:
            assert t.description, f"Tool {t.name} has no description"


# ── Tests: Serialization helpers ──────────────────────────────────────


class TestFormatHelpers:
    """Format helper function tests."""

    def test_format_cc_instance(self, mock_cc_instance):
        result = _format_cc_instance(mock_cc_instance)
        assert result["cc_id"] == "cc_test_01"
        assert result["workspace"] == "/tmp/test"
        assert result["status"] == "idle"
        assert result["pid"] == 12345

    def test_format_agent_node(self, mock_agent_node):
        result = _format_agent_node(mock_agent_node)
        assert result["agent_id"] == "agent_test_01"
        assert result["protocol"] == "mcp"
        assert "connected_at" in result
        assert "last_seen" in result

    def test_cc_instance_serialisable(self, mock_cc_instance):
        result = _format_cc_instance(mock_cc_instance)
        json_str = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["cc_id"] == "cc_test_01"

    def test_agent_node_serialisable(self, mock_agent_node):
        result = _format_agent_node(mock_agent_node)
        json_str = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["agent_id"] == "agent_test_01"


# ── Tests: Tool Functions (with mock hub) ─────────────────────────────


class TestToolFunctions:
    """Test each tool function with mock Context."""

    @pytest.mark.asyncio
    async def test_submit_task_ok(self, ctx, mock_hub):
        """synapse_submit_task returns task_id on success."""
        from cc_router.mcp_hub_server import synapse_submit_task

        result = await synapse_submit_task(ctx, SubmitTaskInput(task="implement sorting"))
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["task_id"] == "task_001"

    @pytest.mark.asyncio
    async def test_submit_task_empty_task(self, ctx):
        """synapse_submit_task should reject empty task."""
        from cc_router.mcp_hub_server import synapse_submit_task

        with pytest.raises(ValueError, match="required"):
            await synapse_submit_task(ctx, SubmitTaskInput(task=""))

    @pytest.mark.asyncio
    async def test_register_cc_ok(self, ctx, mock_hub):
        """synapse_register_cc registers and returns cc_id."""
        from cc_router.mcp_hub_server import synapse_register_cc

        result = await synapse_register_cc(
            ctx, RegisterCCInput(cc_id="cc_new_01", workspace="/tmp/new")
        )
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["cc_id"] == "cc_new_01"

    @pytest.mark.asyncio
    async def test_list_cc_instances(self, ctx, mock_hub):
        """synapse_list_cc_instances returns instance list."""
        from cc_router.mcp_hub_server import synapse_list_cc_instances

        result = await synapse_list_cc_instances(ctx, ListCCInput())
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["count"] >= 1
        assert data["instances"][0]["cc_id"] == "cc_test_01"

    @pytest.mark.asyncio
    async def test_list_cc_instances_filtered(self, ctx, mock_hub):
        """synapse_list_cc_instances with status filter."""
        from cc_router.mcp_hub_server import synapse_list_cc_instances

        result = await synapse_list_cc_instances(ctx, ListCCInput(status="idle"))
        data = json.loads(result)
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_list_agents(self, ctx, mock_hub):
        """synapse_list_agents returns agent list."""
        from cc_router.mcp_hub_server import synapse_list_agents

        result = await synapse_list_agents(ctx)
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["count"] >= 1
        assert data["agents"][0]["agent_id"] == "agent_test_01"

    @pytest.mark.asyncio
    async def test_hub_status(self, ctx, mock_hub, mock_task):
        """synapse_hub_status returns comprehensive overview."""
        from cc_router.mcp_hub_server import synapse_hub_status

        mock_hub._tasks = {"task_001": mock_task}
        mock_task.status = "done"

        result = await synapse_hub_status(ctx)
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "version" in data
        assert data["agents"]["count"] >= 1
        assert data["cc_instances"]["count"] >= 1
        assert data["tasks"]["count"] >= 1

    @pytest.mark.asyncio
    async def test_connect_agent_ok(self, ctx, mock_hub):
        """synapse_connect_agent registers a new agent."""
        from cc_router.mcp_hub_server import synapse_connect_agent

        mock_hub.registry.get_sync = MagicMock(return_value=None)
        result = await synapse_connect_agent(ctx, ConnectAgentInput(agent_id="new_agent"))
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["agent_id"] == "new_agent"

    @pytest.mark.asyncio
    async def test_connect_agent_already_connected(self, ctx, mock_hub):
        """synapse_connect_agent should be idempotent."""
        from cc_router.mcp_hub_server import synapse_connect_agent

        mock_hub.registry.get_sync = MagicMock(return_value=MagicMock(agent_id="existing"))
        result = await synapse_connect_agent(ctx, ConnectAgentInput(agent_id="existing"))
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "already" in data.get("message", "")

    @pytest.mark.asyncio
    async def test_disconnect_agent_ok(self, ctx, mock_hub):
        """synapse_disconnect_agent disconnects."""
        from cc_router.mcp_hub_server import synapse_disconnect_agent

        mock_hub.registry.get_sync = MagicMock(return_value=MagicMock(agent_id="test"))
        result = await synapse_disconnect_agent(ctx, DisconnectAgentInput(agent_id="test"))
        data = json.loads(result)
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_disconnect_agent_not_found(self, ctx, mock_hub):
        """synapse_disconnect_agent handles non-existent agent (idempotent)."""
        from cc_router.mcp_hub_server import synapse_disconnect_agent

        mock_hub.registry.get_sync = MagicMock(return_value=None)
        result = await synapse_disconnect_agent(ctx, DisconnectAgentInput(agent_id="ghost"))
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "not found" in data.get("message", "")


# ── Tests: Error Handling ─────────────────────────────────────────────


class TestErrorHandling:
    """Error handling tests — exceptions raised for error cases."""

    def test_mcp_agent_bridge(self):
        """MCPAgentBridge creates a usable adapter."""
        bridge = MCPAgentBridge("test-agent", "mcp")
        assert bridge.agent_id == "test-agent"
        assert "result" in bridge.supported_events
        assert "error" in bridge.supported_events

    @pytest.mark.asyncio
    async def test_submit_task_no_hub_raises(self):
        """submit_task without lifespan context raises an error."""
        from cc_router.mcp_hub_server import synapse_submit_task

        bad_ctx = MagicMock(
            request_context=MagicMock(
                lifespan_context={},  # no "hub" key
            ),
        )
        with pytest.raises(KeyError):
            await synapse_submit_task(bad_ctx, SubmitTaskInput(task="test"))


# ── Tests: Backward Compatibility ─────────────────────────────────────


class TestBackwardCompatibility:
    """MCPHubServer wrapper class backward compatibility."""

    def test_mcp_hub_server_creation(self):
        """MCPHubServer can be instantiated."""
        server = MCPHubServer()
        assert server is not None
        assert server.app is mcp

    def test_run_method_async(self):
        """MCPHubServer.run is awaitable."""
        server = MCPHubServer()
        assert hasattr(server, "run")

    def test_run_server_function(self):
        """run_server convenience function is importable."""
        from cc_router.mcp_hub_server import run_server

        assert run_server is not None
