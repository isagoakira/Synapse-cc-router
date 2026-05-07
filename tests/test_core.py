"""
Core unit tests for CC Router — pytest style.

Run with: python -m pytest tests/test_core.py -v
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure cc_router is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cc_router.config import (
    load_config,
    get_config,
    update_config,
    get_cc_cli_path,
    get_timeout,
    get_hub_endpoint,
    get_bypass_permission,
    get_health_check_interval,
    get_max_concurrent,
    get_max_consecutive_failures,
)
from cc_router.exceptions import (
    RouterError,
    AdapterError,
    CCExecutorError,
    RegistrationError,
    RoutingError,
)
from cc_router.event_bus import EventBus
from cc_router.cc_registry import CCRegistry
from cc_router.agent_registry import AgentRegistry
from cc_router.cc_adapter import CCAdapter, CCInstance, CCResult
from cc_router.agent_adapter import HubEvent, AgentAdapterImpl
from cc_router.universal_router import UniversalRouter, RouteResult, RoutingStrategy
from cc_router.router_hub import UniversalRouterHub, get_global_hub
from cc_router.cc_executor import CCExecutor
from cc_router.hermes_executor import HermesExecutor, HermesResult
from cc_router.openclaw_executor import OpenClawExecutor, OpenClawResult
from cc_router.router_mcp_server import (
    RouterMCPBridge,
    FeishuNotifyInput,
    ForwardToAgentInput,
    ReadTrainingLogInput,
    QueryExperimentDataInput,
)


# ═══════════════════════════════════════════════════════════════════════
# Config Tests
# ═══════════════════════════════════════════════════════════════════════


class TestConfig:
    """Configuration module tests."""

    def test_defaults(self):
        """Default config values are set correctly."""
        assert get_cc_cli_path() == "claude"
        assert get_timeout() == 300.0
        assert "localhost" in get_hub_endpoint()
        assert get_bypass_permission() is True

    def test_update_config(self):
        """update_config() updates values."""
        old = get_cc_cli_path()
        update_config(cc_cli_path="/test/claude")
        assert get_cc_cli_path() == "/test/claude"
        # Restore
        update_config(cc_cli_path=old)

    def test_load_config_from_path(self):
        """load_config() reads a JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"cc_cli_path": "/from/file/claude", "timeout": 600.0}, f)
            f.flush()
            cfg = load_config(f.name)
            assert cfg["cc_cli_path"] == "/from/file/claude"
            assert cfg["timeout"] == 600.0

    def test_load_config_missing_file(self):
        """load_config() with missing file returns defaults."""
        cfg = load_config("/nonexistent/config.json")
        assert isinstance(cfg, dict)

    def test_load_config_bad_json(self):
        """load_config() raises RouterError on invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not json")
            f.flush()
            with pytest.raises(RouterError):
                load_config(f.name)

    def test_get_config_copy(self):
        """get_config() returns a copy, not the internal dict."""
        c1 = get_config()
        c2 = get_config()
        assert c1 == c2
        assert c1 is not c2  # Different objects

    def test_health_check_config_defaults(self):
        """Health check config defaults are set."""
        assert get_health_check_interval() == 30.0
        assert get_max_consecutive_failures() == 3

    def test_max_concurrent_default(self):
        """Max concurrent default is 5."""
        assert get_max_concurrent() == 5


# ═══════════════════════════════════════════════════════════════════════
# Exception Tests
# ═══════════════════════════════════════════════════════════════════════


class TestExceptions:
    """Exception hierarchy tests."""

    def test_router_error(self):
        assert issubclass(RouterError, Exception)

    def test_adapter_error(self):
        assert issubclass(AdapterError, Exception)

    def test_cc_executor_error(self):
        e = CCExecutorError("test error")
        assert str(e) == "test error"

    def test_registration_error(self):
        e = RegistrationError("already registered")
        assert "registered" in str(e)

    def test_routing_error(self):
        assert issubclass(RoutingError, RouterError)


# ═══════════════════════════════════════════════════════════════════════
# EventBus Tests
# ═══════════════════════════════════════════════════════════════════════


class TestEventBus:
    """EventBus publish/subscribe tests."""

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self):
        bus = EventBus()
        await bus.subscribe("agent_1", "task_1")
        await bus.publish("agent_1", "task_1", {"type": "result", "content": "done"})

        events = []
        async for event in bus.event_stream("agent_1"):
            events.append(event)
            if event.type == "result":
                break
            if len(events) > 5:
                break

        assert any(e.type == "result" for e in events)
        await bus.unsubscribe("agent_1", "task_1")

    @pytest.mark.asyncio
    async def test_publish_to_missing_agent(self):
        """Publishing to non-existent agent should not crash."""
        bus = EventBus()
        await bus.publish("no_such_agent", "task_1", {"type": "result", "content": "x"})

    @pytest.mark.asyncio
    async def test_subscribe_creates_global_queue(self):
        bus = EventBus()
        await bus.subscribe("agent_new", "task_new")
        await bus.publish("agent_new", "task_new", {"type": "log", "content": "test"})

    @pytest.mark.asyncio
    async def test_send_interrupt(self):
        bus = EventBus()
        await bus.subscribe("agent_interrupt", "task_int")
        await bus.send_interrupt("cc_01", "task_int", reason="User cancelled")


# ═══════════════════════════════════════════════════════════════════════
# CCRegistry Tests
# ═══════════════════════════════════════════════════════════════════════


class TestCCRegistry:
    """CCRegistry tests."""

    def setup_method(self):
        self.registry = CCRegistry()
        self.adapter = CCAdapter(
            cc_id="cc_001", workspace="/tmp/test", tags=["ml"], capabilities=["code"]
        )
        self.registry.register(self.adapter)

    def test_register(self):
        assert self.registry.get_by_id("cc_001") is not None
        assert self.registry.get_by_id("cc_001").cc_id == "cc_001"

    def test_register_duplicate(self):
        with pytest.raises(RegistrationError):
            self.registry.register(self.adapter)

    def test_unregister(self):
        self.registry.unregister("cc_001")
        assert self.registry.get_by_id("cc_001") is None

    def test_get_by_tag(self):
        inst = self.registry.get_by_tag("ml")
        assert inst is not None
        assert inst.cc_id == "cc_001"

    def test_get_by_tag_nonexistent(self):
        assert self.registry.get_by_tag("nonexistent") is None

    def test_list_by_status(self):
        idle = self.registry.list_by_status("idle")
        assert len(idle) == 1
        assert idle[0].cc_id == "cc_001"

    def test_list_all(self):
        all_inst = self.registry.list_all()
        assert len(all_inst) == 1

    def test_get_adapter(self):
        adapter = self.registry.get_adapter("cc_001")
        assert adapter is not None
        assert adapter.cc_id == "cc_001"

    def test_update_status(self):
        self.registry.update_status("cc_001", "busy")
        assert self.registry.get_by_id("cc_001").status == "busy"

    def test_update_status_with_session(self):
        self.registry.update_status("cc_001", "idle", session_id="s_test")
        assert self.registry.get_by_id("cc_001").session_id == "s_test"

    @pytest.mark.asyncio
    async def test_update_status_async(self):
        await self.registry.update_status_async("cc_001", "busy")
        assert self.registry.get_by_id("cc_001").status == "busy"


# ═══════════════════════════════════════════════════════════════════════
# AgentRegistry Tests
# ═══════════════════════════════════════════════════════════════════════


class TestAgentRegistry:
    """AgentRegistry tests."""

    @pytest.mark.asyncio
    async def test_register_and_get(self):
        registry = AgentRegistry()
        adapter = AgentAdapterImpl("test_agent")
        node = await registry.register("test_agent", adapter)
        assert node.agent_id == "test_agent"

        got = await registry.get("test_agent")
        assert got is not None
        assert got.agent_id == "test_agent"

    @pytest.mark.asyncio
    async def test_register_with_metadata(self):
        registry = AgentRegistry()
        adapter = AgentAdapterImpl("meta_agent")
        node = await registry.register(
            "meta_agent", adapter, protocol="http", metadata={"version": "1.0"}
        )
        assert node.protocol == "http"
        assert node.metadata["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_unregister(self):
        registry = AgentRegistry()
        adapter = AgentAdapterImpl("remove_agent")
        await registry.register("remove_agent", adapter)
        await registry.unregister("remove_agent")
        assert await registry.get("remove_agent") is None

    @pytest.mark.asyncio
    async def test_list_all(self):
        registry = AgentRegistry()
        for i in range(3):
            adapter = AgentAdapterImpl(f"agent_{i}")
            await registry.register(f"agent_{i}", adapter)
        agents = await registry.list_all()
        assert len(agents) == 3

    def test_sync_methods(self):
        registry = AgentRegistry()
        adapter = AgentAdapterImpl("sync_agent")
        registry.register_sync("sync_agent", adapter)
        assert registry.get_sync("sync_agent") is not None
        assert len(registry.list_all_sync()) == 1
        registry.unregister_sync("sync_agent")
        assert registry.get_sync("sync_agent") is None


# ═══════════════════════════════════════════════════════════════════════
# CCAdapter Tests
# ═══════════════════════════════════════════════════════════════════════


class TestCCAdapter:
    """CCAdapter instantiation and property tests."""

    def test_create_adapter(self):
        adapter = CCAdapter(cc_id="test", workspace="/tmp", tags=["a"], capabilities=["b"])
        assert adapter.cc_id == "test"
        assert adapter.workspace == "/tmp"
        assert adapter.tags == ["a"]
        assert adapter.capabilities == ["b"]

    def test_instance_property(self):
        adapter = CCAdapter(cc_id="test", workspace="/tmp")
        instance = adapter.instance
        assert isinstance(instance, CCInstance)
        assert instance.cc_id == "test"
        assert instance.status == "idle"

    @pytest.mark.asyncio
    async def test_get_status(self):
        adapter = CCAdapter(cc_id="test", workspace="/tmp")
        status = await adapter.get_status()
        assert status["cc_id"] == "test"
        assert status["status"] == "idle"

    @pytest.mark.asyncio
    async def test_terminate(self):
        adapter = CCAdapter(cc_id="test", workspace="/tmp")
        await adapter.terminate()
        status = await adapter.get_status()
        assert status["status"] == "dead"

    def test_default_capabilities(self):
        adapter = CCAdapter(cc_id="test", workspace="/tmp")
        assert adapter.capabilities == ["general"]

    @pytest.mark.asyncio
    async def test_health_check_idle(self):
        """health_check returns healthy for idle instance."""
        adapter = CCAdapter(cc_id="health_test", workspace="/tmp")
        result = await adapter.health_check()
        assert result["cc_id"] == "health_test"
        assert result["status"] == "idle"
        assert result["process_alive"] is True

    @pytest.mark.asyncio
    async def test_health_check_after_terminate(self):
        """health_check reflects dead status after terminate."""
        adapter = CCAdapter(cc_id="health_term", workspace="/tmp")
        await adapter.terminate()
        result = await adapter.health_check()
        assert result["status"] == "dead"
        assert result["has_session"] is False

    def test_ccresult_dataclass(self):
        r = CCResult(kind="SUCCESS", text="hello", session_id="s1", cost_usd=0.01, duration_ms=1000)
        assert r.kind == "SUCCESS"
        assert r.text == "hello"


# ═══════════════════════════════════════════════════════════════════════
# UniversalRouter Tests
# ═══════════════════════════════════════════════════════════════════════


class TestUniversalRouter:
    """Routing logic tests."""

    @pytest.mark.asyncio
    async def test_tag_routing(self):
        registry = CCRegistry()
        cc = CCAdapter(cc_id="cc_ml", workspace="/tmp/ml", tags=["ml"], capabilities=["code"])
        registry.register(cc)
        router = UniversalRouter(registry)

        result = await router.route("train model", tag="ml")
        assert result.cc_id == "cc_ml"
        assert result.strategy == RoutingStrategy.TAG_MATCH

    @pytest.mark.asyncio
    async def test_at_tag_routing(self):
        registry = CCRegistry()
        cc = CCAdapter(cc_id="cc_paper", workspace="/tmp/paper", tags=["paper"])
        registry.register(cc)
        router = UniversalRouter(registry)

        result = await router.route("@paper write introduction")
        assert result.cc_id == "cc_paper"
        assert result.strategy == RoutingStrategy.TAG_MATCH

    @pytest.mark.asyncio
    async def test_no_cc_raises_error(self):
        registry = CCRegistry()
        router = UniversalRouter(registry)

        with pytest.raises(RoutingError):
            await router.route("any task")

    @pytest.mark.asyncio
    async def test_route_result_dataclass(self):
        r = RouteResult(
            cc_id="test", strategy=RoutingStrategy.DEFAULT, reason="fallback", workspace="/tmp"
        )
        assert r.cc_id == "test"
        assert r.workspace == "/tmp"
        assert r.reason == "fallback"


# ═══════════════════════════════════════════════════════════════════════
# UniversalRouterHub Tests
# ═══════════════════════════════════════════════════════════════════════


class TestHub:
    """UniversalRouterHub tests."""

    def test_create_hub(self):
        hub = UniversalRouterHub()
        assert hub.registry is not None
        assert hub.cc_registry is not None
        assert hub.router is not None
        assert hub.event_bus is not None

    def test_register_cc(self):
        hub = UniversalRouterHub()
        cc = CCAdapter(cc_id="cc_hub", workspace="/tmp")
        cc_id = hub.register_cc(cc)
        assert cc_id == "cc_hub"
        assert hub.cc_registry.get_by_id("cc_hub") is not None

    def test_connect_agent(self):
        hub = UniversalRouterHub()
        agent = AgentAdapterImpl("test_hub_agent")
        hub.connect_agent(agent.agent_id, agent)
        assert hub.registry.get_sync("test_hub_agent") is not None

    def test_disconnect_agent(self):
        hub = UniversalRouterHub()
        agent = AgentAdapterImpl("bye_agent")
        hub.connect_agent(agent.agent_id, agent)
        hub.disconnect_agent("bye_agent")
        assert hub.registry.get_sync("bye_agent") is None

    @pytest.mark.asyncio
    async def test_submit_task(self):
        hub = UniversalRouterHub()
        cc = CCAdapter(cc_id="cc_hub_test", workspace="/tmp", tags=["test"])
        hub.register_cc(cc)
        agent = AgentAdapterImpl("task_agent")
        hub.connect_agent(agent.agent_id, agent)

        task_id = await hub.submit_task("task_agent", "do something", tag="test", timeout=5.0)
        assert len(task_id) > 0

        # Should be pending or running initially
        await asyncio.sleep(0.5)
        task = hub.get_task(task_id)
        assert task is not None
        assert task.task_id == task_id
        assert task.caller_agent_id == "task_agent"

    def test_list_tasks(self):
        hub = UniversalRouterHub()
        assert hub.list_tasks() == []
        assert hub.list_tasks("nonexistent") == []

    def test_cc_ready(self):
        hub = UniversalRouterHub()
        cc = CCAdapter(cc_id="cc_rdy", workspace="/tmp")
        hub.register_cc(cc)
        hub.cc_ready("cc_rdy", session_id="s_rdy")
        inst = hub.cc_registry.get_by_id("cc_rdy")
        assert inst.status == "idle"
        assert inst.session_id == "s_rdy"

    def test_mcp_server(self):
        hub = UniversalRouterHub()
        bridge = RouterMCPBridge()
        hub.set_mcp_server(bridge)
        assert hub.get_mcp_server() is bridge

    def test_get_global_hub(self):
        h1 = get_global_hub()
        h2 = get_global_hub()
        assert h1 is h2

    # ── Hub: Health Monitoring ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_health_monitor_start_stop(self):
        """Health monitor can be started and stopped."""
        hub = UniversalRouterHub()
        assert hub._health_task is None
        hub.start_health_monitor()
        assert hub._health_task is not None
        assert not hub._health_task.done()
        hub.stop_health_monitor()
        await asyncio.sleep(0.1)

    @pytest.mark.asyncio
    async def test_queue_processor_start_stop(self):
        """Queue processor can be started and stopped."""
        hub = UniversalRouterHub()
        assert hub._queue_processor_task is None
        hub.start_queue_processor()
        assert hub._queue_processor_task is not None
        hub.stop_queue_processor()

    @pytest.mark.asyncio
    async def test_background_tasks_start_stop(self):
        """All background tasks start and stop together."""
        hub = UniversalRouterHub()
        hub.start_background_tasks()
        assert hub._health_task is not None
        assert hub._queue_processor_task is not None
        hub.stop_background_tasks()

    # ── Hub: Capacity Management ─────────────────────────────────

    def test_max_concurrent_property(self):
        """max_concurrent property get/set works."""
        hub = UniversalRouterHub()
        assert hub.max_concurrent == 5
        hub.max_concurrent = 3
        assert hub.max_concurrent == 3

    def test_max_concurrent_min_one(self):
        """max_concurrent cannot be set below 1."""
        hub = UniversalRouterHub()
        hub.max_concurrent = 0
        assert hub.max_concurrent == 1

    def test_active_and_queued_counts_initial(self):
        """Active and queued task counts start at 0."""
        hub = UniversalRouterHub()
        assert hub.active_task_count == 0
        assert hub.queued_task_count == 0

    # ── Hub: Health Summary ──────────────────────────────────────

    def test_get_health_summary(self):
        """get_health_summary returns the expected structure."""
        hub = UniversalRouterHub()
        cc = CCAdapter(cc_id="sum_cc", workspace="/tmp", tags=["test"])
        hub.register_cc(cc)

        summary = hub.get_health_summary()

        assert summary["cc_instances"]["count"] == 1
        assert "by_status" in summary["cc_instances"]
        assert summary["cc_instances"]["details"][0]["cc_id"] == "sum_cc"
        assert "capacity" in summary
        assert summary["capacity"]["max_concurrent"] == 5
        assert summary["capacity"]["active"] == 0
        assert summary["capacity"]["queued"] == 0
        assert summary["capacity"]["available_slots"] == 5
        assert "monitoring" in summary
        assert summary["monitoring"]["health_interval"] == 30.0
        assert summary["monitoring"]["max_failures"] == 3

    def test_get_health_summary_empty(self):
        """get_health_summary handles empty Hub gracefully."""
        hub = UniversalRouterHub()
        summary = hub.get_health_summary()
        assert summary["cc_instances"]["count"] == 0
        assert summary["tasks"]["count"] == 0

    @pytest.mark.asyncio
    async def test_health_check_cycle(self):
        """_health_check_cycle runs without error on empty registry."""
        hub = UniversalRouterHub()
        await hub._health_check_cycle()  # Should not raise

    @pytest.mark.asyncio
    async def test_submit_task_queues_when_at_capacity(self):
        """submit_task queues when active count equals max_concurrent."""
        hub = UniversalRouterHub()
        hub.max_concurrent = 1
        cc = CCAdapter(cc_id="cap_cc", workspace="/tmp", tags=["cap"])
        hub.register_cc(cc)
        agent = AgentAdapterImpl("cap_agent")
        hub.connect_agent(agent.agent_id, agent)

        # First task starts immediately
        await hub.submit_task("cap_agent", "task one", tag="cap", timeout=3.0)
        await asyncio.sleep(0.2)

        # Manually set active count to max
        async with hub._capacity_lock:
            hub._active_task_count = 1

        # Second task should be queued
        task_id_2 = await hub.submit_task("cap_agent", "task two", tag="cap", timeout=3.0)
        task_2 = hub.get_task(task_id_2)
        assert task_2.status == "queued"

        # Reset
        async with hub._capacity_lock:
            hub._active_task_count = 0


# ═══════════════════════════════════════════════════════════════════════
# AgentAdapter Tests
# ═══════════════════════════════════════════════════════════════════════


class TestAgentAdapter:
    """AgentAdapter protocol tests."""

    def test_agent_adapter_impl_create(self):
        adapter = AgentAdapterImpl("my_agent")
        assert adapter.agent_id == "my_agent"
        assert "result" in adapter.supported_events
        assert not adapter._connected

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        adapter = AgentAdapterImpl("conn_agent")
        # Will use global hub internally
        await adapter.connect()
        assert adapter._connected
        await adapter.disconnect()
        assert not adapter._connected

    def test_hub_event_dataclass(self):
        event = HubEvent(type="result", task_id="t1", agent_id="a1", data={"key": "val"})
        assert event.type == "result"
        assert event.data["key"] == "val"


# ═══════════════════════════════════════════════════════════════════════
# CCExecutor Tests (mock-based, no real CC CLI needed)
# ═══════════════════════════════════════════════════════════════════════


class TestCCExecutor:
    """CCExecutor tests with mocked subprocess."""

    def test_create_executor(self):
        executor = CCExecutor(cc_cli_path="/mock/claude")
        assert executor is not None

    def test_is_process_alive_no_process(self):
        """is_process_alive returns False when no process has started."""
        executor = CCExecutor(cc_cli_path="/mock/claude")
        assert executor.is_process_alive() is False

    @pytest.mark.asyncio
    async def test_executor_missing_cli(self):
        executor = CCExecutor(cc_cli_path="/definitely/not/found/cli")
        with pytest.raises(CCExecutorError):
            await executor.run(task="test", workspace="/tmp")

    def test_ccresult_dataclass(self):
        r = CCResult(
            kind="TIMEOUT",
            text="",
            session_id="",
            cost_usd=0.0,
            duration_ms=5000,
            error="timed out",
        )
        assert r.kind == "TIMEOUT"
        assert r.error == "timed out"


# ═══════════════════════════════════════════════════════════════════════
# HermesExecutor Tests (mock-based)
# ═══════════════════════════════════════════════════════════════════════


class TestHermesExecutor:
    """HermesExecutor tests."""

    def test_hermes_result_dataclass(self):
        r = HermesResult(kind="SUCCESS", text="output", session_id="s1", duration_ms=500, error="")
        assert r.kind == "SUCCESS"
        assert r.text == "output"

    def test_create_executor(self):
        ex = HermesExecutor(hermes_path="/mock/hermes")
        assert ex is not None


# ═══════════════════════════════════════════════════════════════════════
# OpenClawExecutor Tests (mock-based)
# ═══════════════════════════════════════════════════════════════════════


class TestOpenClawExecutor:
    """OpenClawExecutor tests."""

    def test_openclaw_result_dataclass(self):
        r = OpenClawResult(kind="SUCCESS", text="out", session_id="s1", duration_ms=100)
        assert r.kind == "SUCCESS"

    def test_create_executor(self):
        ex = OpenClawExecutor(openclaw_path="/mock/openclaw")
        assert ex is not None


# ═══════════════════════════════════════════════════════════════════════
# RouterMCPBridge Tests
# ═══════════════════════════════════════════════════════════════════════


class TestMCPBridge:
    """RouterMCPBridge tests."""

    @pytest.mark.asyncio
    async def test_list_tools(self):
        bridge = RouterMCPBridge()
        tools = bridge.list_tools()
        assert len(tools) == 4
        names = [t["name"] for t in tools]
        assert "feishu_notify" in names
        assert "forward_to_agent" in names
        assert "read_training_log" in names
        assert "query_experiment_data" in names

    @pytest.mark.asyncio
    async def test_feishu_notify(self):
        bridge = RouterMCPBridge()
        result = await bridge.call_tool("feishu_notify", {"text": "test notification"})
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_unknown_tool_raises(self):
        bridge = RouterMCPBridge()
        with pytest.raises(ValueError):
            await bridge.call_tool("nonexistent", {})

    @pytest.mark.asyncio
    async def test_read_training_log(self):
        bridge = RouterMCPBridge()
        result = await bridge.call_tool(
            "read_training_log", {"workspace": "/tmp", "pattern": "*.log"}
        )
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_query_experiment_data(self):
        bridge = RouterMCPBridge()
        result = await bridge.call_tool("query_experiment_data", {"experiment": "exp1"})
        assert result["status"] == "ok"

    def test_task_context(self):
        bridge = RouterMCPBridge()
        bridge.set_task_context("task_ctx_1", "cc_ctx", "agent_ctx")
        ctx = bridge.get_task_context("task_ctx_1")
        assert ctx["cc_id"] == "cc_ctx"
        assert ctx["agent_id"] == "agent_ctx"
        bridge.clear_task_context("task_ctx_1")
        assert bridge.get_task_context("task_ctx_1") == {}

    # ── Pydantic Model Tests ───────────────────────────────────────

    def test_feishu_notify_input(self):
        m = FeishuNotifyInput(text="hello")
        assert m.text == "hello"
        assert m.chat_id is None

    def test_feishu_notify_input_with_chat_id(self):
        m = FeishuNotifyInput(text="hello", chat_id="chat_123")
        assert m.chat_id == "chat_123"

    def test_feishu_notify_input_rejects_empty_text(self):
        with pytest.raises(ValueError):  # Pydantic ValidationError is a subclass
            FeishuNotifyInput(text="")

    def test_forward_to_agent_input(self):
        m = ForwardToAgentInput(content="test", task_id="t1")
        assert m.content == "test"
        assert m.task_id == "t1"
        assert m.event_type == "partial"

    def test_forward_to_agent_input_requires_content_and_task_id(self):
        with pytest.raises(ValueError):
            ForwardToAgentInput(content="")
        with pytest.raises(ValueError):
            ForwardToAgentInput(task_id="")

    def test_read_training_log_input(self):
        m = ReadTrainingLogInput(workspace="/tmp")
        assert m.workspace == "/tmp"
        assert m.pattern == "*.log"

    def test_query_experiment_data_input(self):
        m = QueryExperimentDataInput(experiment="exp1")
        assert m.experiment == "exp1"
        assert m.metric is None

    def test_query_experiment_data_input_with_metric(self):
        m = QueryExperimentDataInput(experiment="exp1", metric="accuracy")
        assert m.metric == "accuracy"

    def test_query_experiment_data_input_rejects_empty(self):
        with pytest.raises(ValueError):
            QueryExperimentDataInput(experiment="")

    # ── Edge Case Tests ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_feishu_notify_empty_text_raises(self):
        bridge = RouterMCPBridge()
        with pytest.raises(ValueError):
            await bridge.call_tool("feishu_notify", {"text": ""})

    @pytest.mark.asyncio
    async def test_read_training_log_nonexistent_workspace(self):
        bridge = RouterMCPBridge()
        result = await bridge.call_tool(
            "read_training_log", {"workspace": "/nonexistent_path_xyz", "pattern": "*.log"}
        )
        assert result["status"] == "ok"
        assert len(result.get("logs", [])) == 0

    @pytest.mark.asyncio
    async def test_forward_to_agent_missing_context(self):
        """forward_to_agent should not crash when context has no agent_id."""
        bridge = RouterMCPBridge()
        result = await bridge.call_tool(
            "forward_to_agent",
            {"event_type": "log", "content": "test", "task_id": "no_ctx_task"},
        )
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_query_experiment_data_nonexistent(self):
        """query_experiment_data returns empty results for unknown experiment."""
        bridge = RouterMCPBridge()
        result = await bridge.call_tool(
            "query_experiment_data", {"experiment": "nonexistent_experiment_xyz"}
        )
        assert result["status"] == "ok"
        assert result.get("count") == 0

    @pytest.mark.asyncio
    async def test_forward_to_agent_with_task_context(self):
        """forward_to_agent uses task context to find agent_id."""
        bridge = RouterMCPBridge()
        bridge.set_task_context("ctx_task_1", "cc_test", "agent_test")
        result = await bridge.call_tool(
            "forward_to_agent",
            {"event_type": "result", "content": "done", "task_id": "ctx_task_1"},
            context={"task_id": "ctx_task_1"},
        )
        assert result["status"] == "ok"
        bridge.clear_task_context("ctx_task_1")

    def test_context_isolated_between_bridges(self):
        """Each bridge instance should have its own task context."""
        b1 = RouterMCPBridge()
        b2 = RouterMCPBridge()
        b1.set_task_context("t1", "cc1", "agent1")
        assert b2.get_task_context("t1") == {}
        assert b1.get_task_context("t1")["cc_id"] == "cc1"


# ═══════════════════════════════════════════════════════════════════════
# Integration-style Tests (no external dependencies)
# ═══════════════════════════════════════════════════════════════════════


class TestIntegration:
    """Integration tests requiring multiple components."""

    @pytest.mark.asyncio
    async def test_hub_agent_cc_flow(self):
        """End-to-end flow: Hub + Agent + CC registration."""
        hub = UniversalRouterHub()

        # Register CC
        cc = CCAdapter(cc_id="integ_cc", workspace="/tmp", tags=["integ"])
        hub.register_cc(cc)

        # Connect agent
        agent = AgentAdapterImpl("integ_agent")
        hub.connect_agent(agent.agent_id, agent)

        # Verify both registered
        assert hub.cc_registry.get_by_id("integ_cc") is not None
        assert hub.registry.get_sync("integ_agent") is not None

        # Submit task
        task_id = await hub.submit_task("integ_agent", "test task", tag="integ", timeout=3.0)
        assert task_id is not None

        # Task should be tracked
        task = hub.get_task(task_id)
        assert task is not None
        assert task.status in ("pending", "running", "done", "error")

    @pytest.mark.asyncio
    async def test_eventbus_routing_integration(self):
        """EventBus and routing work together."""
        registry = CCRegistry()
        cc = CCAdapter(cc_id="integ_bus", workspace="/tmp/bus", tags=["bus"])
        registry.register(cc)
        router = UniversalRouter(registry)

        result = await router.route("test bus", tag="bus")
        assert result.cc_id == "integ_bus"

        bus = EventBus()
        await bus.subscribe("integ_agent_bus", "integ_task_bus")
        await bus.publish(
            "integ_agent_bus", "integ_task_bus", {"type": "result", "content": "bus done"}
        )
        # Agent should receive
        events = []
        async for event in bus.event_stream("integ_agent_bus"):
            events.append(event)
            if event.type == "result":
                break
            if len(events) >= 5:
                break
        assert any(e.type == "result" for e in events)
