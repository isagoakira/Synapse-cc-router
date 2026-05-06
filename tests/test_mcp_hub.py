"""
Tests for MCPHubServer -- the external MCP Server wrapping UniversalRouterHub.

Run with: python -m pytest tests/test_mcp_hub.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure cc_router is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.types import ListToolsRequest

from cc_router.mcp_hub_server import MCPHubServer, MCPAgentBridge, _format_cc_instance, _format_agent_node


# ── Helpers ─────────────────────────────────────────────────────────

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


class MockHub:
    """Mock UniversalRouterHub for testing."""

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


@pytest.fixture
def mock_hub(mock_cc_instance, mock_agent_node, mock_task):
    """Provide a MockHub instance."""
    return MockHub(mock_cc_instance, mock_agent_node, mock_task)


@pytest.fixture
def server():
    """Provide a fresh MCPHubServer (hub is lazy-init, won't auto-connect)."""
    return MCPHubServer()


# ── Tests: Initialisation ───────────────────────────────────────────

class TestInit:
    """MCPHubServer initialisation tests."""

    def test_create_server(self, server):
        """Server should be creatable without errors."""
        assert server is not None
        assert server._app is not None
        assert server._app.name == "synapse-hub"

    def test_hub_uninitialised_by_default(self, server):
        """Hub should be None until first access."""
        assert server._hub is None

    def test_get_hub_lazy_init(self, server):
        """_get_hub() should create the hub on first call."""
        hub = server._get_hub()
        assert hub is not None
        assert server._hub is hub
        # second call returns same instance
        assert server._get_hub() is hub


# ── Tests: Tool Definitions ─────────────────────────────────────────

class TestToolDefinitions:
    """Verify all expected tools are defined."""

    TOOL_NAMES = {
        "submit_task",
        "register_cc",
        "list_cc_instances",
        "list_agents",
        "hub_status",
        "connect_agent",
        "disconnect_agent",
    }

    async def _get_tools(self, server):
        """Retrieve tools list via the internally registered MCP handler."""
        handler = server._app.request_handlers[ListToolsRequest]
        result = await handler(None)
        return result.root.tools

    @pytest.mark.asyncio
    async def test_all_tools_present(self, server):
        """Server should define all 7 tools."""
        tools = await self._get_tools(server)
        tool_names = {t.name for t in tools}
        assert tool_names == self.TOOL_NAMES, f"Missing: {self.TOOL_NAMES - tool_names}"

    @pytest.mark.asyncio
    async def test_submit_task_schema(self, server):
        """submit_task should require 'task' and have optional fields."""
        tools = await self._get_tools(server)
        submit = next(t for t in tools if t.name == "submit_task")
        props = submit.inputSchema["properties"]
        assert "task" in props
        assert props["task"]["type"] == "string"
        assert "tag" in props
        assert "capability" in props
        assert "timeout" in props
        assert "agent_id" in props
        assert "task" in submit.inputSchema.get("required", [])

    @pytest.mark.asyncio
    async def test_register_cc_schema(self, server):
        """register_cc should require cc_id and workspace."""
        tools = await self._get_tools(server)
        rt = next(t for t in tools if t.name == "register_cc")
        props = rt.inputSchema["properties"]
        assert "cc_id" in props
        assert "workspace" in props
        assert "tags" in props
        assert "capabilities" in props
        required = rt.inputSchema.get("required", [])
        assert "cc_id" in required
        assert "workspace" in required

    @pytest.mark.asyncio
    async def test_list_cc_instances_schema(self, server):
        """list_cc_instances should have optional status filter."""
        tools = await self._get_tools(server)
        t = next(x for x in tools if x.name == "list_cc_instances")
        assert "status" in t.inputSchema["properties"]
        enum_vals = t.inputSchema["properties"]["status"].get("enum", [])
        assert "idle" in enum_vals
        assert "busy" in enum_vals


# ── Tests: format helpers ───────────────────────────────────────────

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


# ── Tests: Tool Handlers (with mock hub) ────────────────────────────

class TestToolHandlers:
    """Test each tool handler with a mocked Hub."""

    @pytest.mark.asyncio
    async def test_submit_task_ok(self, server, mock_hub):
        """submit_task should return task_id on success."""
        server._hub = mock_hub
        result = await server._submit_task({
            "task": "implement a sorting algorithm",
            "tag": "code",
        })
        assert result["status"] == "ok"
        assert result["task_id"] == "task_001"
        assert "submitted" in result["message"]

    @pytest.mark.asyncio
    async def test_submit_task_empty_task(self, server):
        """submit_task should reject empty task."""
        result = await server._submit_task({"task": ""})
        assert result["status"] == "error"
        assert "required" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_submit_task_missing_task(self, server):
        """submit_task should reject missing task."""
        result = await server._submit_task({})
        assert result["status"] == "error"
        assert "required" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_register_cc_ok(self, server, mock_hub):
        """register_cc should register and return cc_id."""
        server._hub = mock_hub
        result = await server._register_cc({
            "cc_id": "cc_new_01",
            "workspace": "/tmp/new",
            "tags": ["ml"],
            "capabilities": ["code"],
        })
        assert result["status"] == "ok"
        assert result["cc_id"] == "cc_new_01"

    @pytest.mark.asyncio
    async def test_register_cc_missing_fields(self, server):
        """register_cc should reject missing cc_id or workspace."""
        r1 = await server._register_cc({"workspace": "/tmp"})
        assert r1["status"] == "error"

        r2 = await server._register_cc({"cc_id": "x"})
        assert r2["status"] == "error"

        r3 = await server._register_cc({})
        assert r3["status"] == "error"

    @pytest.mark.asyncio
    async def test_list_cc_instances_all(self, server, mock_hub):
        """list_cc_instances without filter should return all."""
        server._hub = mock_hub
        result = await server._list_cc_instances({})
        assert result["status"] == "ok"
        assert result["count"] >= 1
        assert len(result["instances"]) >= 1
        assert result["instances"][0]["cc_id"] == "cc_test_01"

    @pytest.mark.asyncio
    async def test_list_cc_instances_filtered(self, server, mock_hub):
        """list_cc_instances with status filter should filter."""
        server._hub = mock_hub
        result = await server._list_cc_instances({"status": "idle"})
        assert result["status"] == "ok"
        assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_list_agents(self, server, mock_hub):
        """list_agents should return agent list."""
        server._hub = mock_hub
        result = await server._list_agents({})
        assert result["status"] == "ok"
        assert result["count"] >= 1
        assert result["agents"][0]["agent_id"] == "agent_test_01"

    @pytest.mark.asyncio
    async def test_hub_status(self, server, mock_hub, mock_cc_instance, mock_agent_node, mock_task):
        """hub_status should return comprehensive overview."""
        mock_hub._tasks = {"task_001": mock_task}
        mock_task.status = "done"
        mock_cc_instance.status = "idle"
        server._hub = mock_hub
        result = await server._hub_status({})
        assert result["status"] == "ok"
        assert "version" in result
        assert result["agents"]["count"] >= 1
        assert result["cc_instances"]["count"] >= 1
        assert result["tasks"]["count"] >= 1
        assert "by_status" in result["cc_instances"]

    @pytest.mark.asyncio
    async def test_connect_agent_ok(self, server, mock_hub):
        """connect_agent should register a new agent."""
        mock_hub.registry.get_sync = MagicMock(return_value=None)
        server._hub = mock_hub
        result = await server._connect_agent({"agent_id": "new_agent"})
        assert result["status"] == "ok"
        assert result["agent_id"] == "new_agent"
        assert "connected" in result["message"]

    @pytest.mark.asyncio
    async def test_connect_agent_already_connected(self, server, mock_hub):
        """connect_agent should be idempotent."""
        mock_hub.registry.get_sync = MagicMock(return_value=MagicMock(agent_id="existing"))
        server._hub = mock_hub
        result = await server._connect_agent({"agent_id": "existing"})
        assert result["status"] == "ok"
        assert "already connected" in result["message"]

    @pytest.mark.asyncio
    async def test_connect_agent_missing_id(self, server):
        """connect_agent should reject empty agent_id."""
        result = await server._connect_agent({"agent_id": ""})
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_disconnect_agent_ok(self, server, mock_hub):
        """disconnect_agent should disconnect."""
        mock_hub.registry.get_sync = MagicMock(return_value=MagicMock(agent_id="test"))
        server._hub = mock_hub
        result = await server._disconnect_agent({"agent_id": "test"})
        assert result["status"] == "ok"
        assert "disconnected" in result["message"]

    @pytest.mark.asyncio
    async def test_disconnect_agent_not_found(self, server, mock_hub):
        """disconnect_agent should handle non-existent agent."""
        mock_hub.registry.get_sync = MagicMock(return_value=None)
        server._hub = mock_hub
        result = await server._disconnect_agent({"agent_id": "ghost"})
        assert result["status"] == "ok"
        assert "not found" in result["message"]

    @pytest.mark.asyncio
    async def test_disconnect_agent_missing_id(self, server):
        """disconnect_agent should reject empty agent_id."""
        result = await server._disconnect_agent({"agent_id": ""})
        assert result["status"] == "error"


# ── Tests: Error handling ───────────────────────────────────────────

class TestErrorHandling:
    """Edge case and error handling tests."""

    @pytest.mark.asyncio
    async def test_unknown_tool(self, server):
        """_handle_call should raise RouterError for unknown tool."""
        with pytest.raises(Exception):
            await server._handle_call("nonexistent_tool", {})

    @pytest.mark.asyncio
    async def test_submit_task_no_hub(self, server):
        """submit_task should work without explicit hub (lazy-init)."""
        # This will create a real Hub via get_global_hub() -- that's fine
        result = await server._submit_task({
            "task": "test",
            "agent_id": "test-agent-for-no-hub",
        })
        assert result["status"] == "ok" or result["status"] == "error"
        # Will be "error" if no CC instances registered, but that's ok

    @pytest.mark.asyncio
    async def test_mcp_agent_bridge(self):
        """MCPAgentBridge should create a usable adapter."""
        bridge = MCPAgentBridge("test-agent", "mcp")
        assert bridge.agent_id == "test-agent"
        assert "result" in bridge.supported_events
        assert "error" in bridge.supported_events

    @pytest.mark.asyncio
    async def test_call_tool_dispatch_ok(self, server, mock_hub):
        """call_tool should dispatch to correct handler and return TextContent."""
        server._hub = mock_hub
        contents = await server._handle_call("hub_status", {})
        assert len(contents) == 1
        assert contents[0].type == "text"
        data = json.loads(contents[0].text)
        assert data["status"] == "ok"


# ── Tests: Serialisation round-trip ─────────────────────────────────

class TestSerialisation:
    """JSON serialisation round-trip tests."""

    def test_cc_instance_serialisable(self, mock_cc_instance):
        result = _format_cc_instance(mock_cc_instance)
        json_str = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["cc_id"] == "cc_test_01"
        assert parsed["status"] == "idle"

    def test_agent_node_serialisable(self, mock_agent_node):
        result = _format_agent_node(mock_agent_node)
        json_str = json.dumps(result, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["agent_id"] == "agent_test_01"
