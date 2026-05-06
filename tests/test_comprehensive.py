#!/usr/bin/env python3
"""
Comprehensive tests for CC Router.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cc_router import (
    UniversalRouterHub,
    CCAdapter,
    CCRegistry,
    UniversalRouter,
    EventBus,
    RoutingStrategy,
)
from cc_router.agent_adapter import AgentAdapterImpl


# ─────────────────────────────────────────────────────────────────
# Test 1: Routing Strategy
# ─────────────────────────────────────────────────────────────────


async def test_routing_strategy():
    """Test routing decision logic."""
    print("\n[Test 1] Routing Strategy")

    # Create registry with test CC instances
    registry = CCRegistry()

    # Register test CC instances
    cc1 = CCAdapter(
        cc_id="cc_starfire",
        workspace="/Users/test/starfire",
        tags=["starfire", "ml"],
        capabilities=["ml", "code"],
    )
    cc2 = CCAdapter(
        cc_id="cc_paper",
        workspace="/Users/test/paper",
        tags=["paper"],
        capabilities=["paper", "research"],
    )

    registry.register(cc1)
    registry.register(cc2)

    router = UniversalRouter(registry)

    # Test 1: Tag routing
    result = await router.route("train model", tag="starfire")
    assert result.cc_id == "cc_starfire", f"Expected cc_starfire, got {result.cc_id}"
    assert result.strategy == RoutingStrategy.TAG_MATCH
    print(f"  ✓ Tag routing: {result.cc_id} ({result.strategy.value})")

    # Test 2: Capability routing
    result = await router.route("帮我写论文 introduction")
    assert result.cc_id == "cc_paper", f"Expected cc_paper, got {result.cc_id}"
    print(f"  ✓ Capability routing: {result.cc_id} ({result.strategy.value})")

    # Test 3: Round-robin when no match
    result = await router.route("do something general")
    # Should get round-robin since no specific match
    print(f"  ✓ Default routing: {result.cc_id} ({result.strategy.value})")

    print("  ✓ Routing strategy tests passed")


# ─────────────────────────────────────────────────────────────────
# Test 2: EventBus bidirectional
# ─────────────────────────────────────────────────────────────────


async def test_event_bus():
    """Test EventBus publish/subscribe."""
    print("\n[Test 2] EventBus Bidirectional")

    bus = EventBus()

    # Subscribe
    await bus.subscribe("agent_001", "task_123")

    # Publish from CC to Agent
    await bus.publish("agent_001", "task_123", {"type": "progress", "content": "CC is working..."})

    # Consume event
    events = []
    async for event in bus.event_stream("agent_001"):
        events.append(event)
        if event.task_id == "task_123" and event.type == "progress":
            break

    assert any(e.type == "progress" and "working" in e.data.get("content", "") for e in events)
    print(f"  ✓ Received {len(events)} events")
    print("  ✓ EventBus bidirectional test passed")


# ─────────────────────────────────────────────────────────────────
# Test 3: CCAdapter with mock executor
# ─────────────────────────────────────────────────────────────────


async def test_cc_adapter():
    """Test CCAdapter instantiation and status."""
    print("\n[Test 3] CCAdapter")

    adapter = CCAdapter(
        cc_id="test_cc",
        workspace="/tmp/test",
        tags=["test"],
        capabilities=["general"],
    )

    # Check initial state
    instance = adapter.instance
    assert instance.cc_id == "test_cc"
    assert instance.workspace == "/tmp/test"
    assert instance.status == "idle"
    print(f"  ✓ CCAdapter created: {instance.cc_id}")
    print(f"  ✓ Initial status: {instance.status}")

    # Check status retrieval
    status = await adapter.get_status()
    assert status["cc_id"] == "test_cc"
    assert status["status"] == "idle"
    print("  ✓ get_status() works")

    print("  ✓ CCAdapter tests passed")


# ─────────────────────────────────────────────────────────────────
# Test 4: AgentAdapter protocol
# ─────────────────────────────────────────────────────────────────


async def test_agent_adapter_protocol():
    """Test AgentAdapter protocol implementation."""
    print("\n[Test 4] AgentAdapter Protocol")

    class TestAdapter(AgentAdapterImpl):
        def __init__(self):
            super().__init__("test_agent")

    adapter = TestAdapter()

    # Test properties
    assert adapter.agent_id == "test_agent"
    print(f"  ✓ agent_id: {adapter.agent_id}")

    assert "result" in adapter.supported_events
    assert "error" in adapter.supported_events
    print(f"  ✓ supported_events: {adapter.supported_events}")

    print("  ✓ AgentAdapter protocol tests passed")


# ─────────────────────────────────────────────────────────────────
# Test 5: Hub integration
# ─────────────────────────────────────────────────────────────────


async def test_hub_integration():
    """Test Hub with CC and Agent."""
    print("\n[Test 5] Hub Integration")

    hub = UniversalRouterHub()

    # Register CC
    cc_adapter = CCAdapter(
        cc_id="cc_001",
        workspace="/tmp/test",
        tags=["test"],
        capabilities=["general"],
    )
    hub.register_cc(cc_adapter)
    print("  ✓ CC registered to Hub")

    # Connect mock agent
    class MockAgent(AgentAdapterImpl):
        def __init__(self):
            super().__init__("mock_agent")

    agent = MockAgent()
    hub.connect_agent(agent.agent_id, agent)
    print("  ✓ Agent connected to Hub")

    # Verify CC is registered
    cc = hub.cc_registry.get_by_id("cc_001")
    assert cc is not None
    print("  ✓ CC lookup works")

    # Verify agent is registered
    agent_node = hub.registry.get_sync("mock_agent")
    assert agent_node is not None
    print("  ✓ Agent lookup works")

    print("  ✓ Hub integration tests passed")


# ─────────────────────────────────────────────────────────────────
# Test 6: MCP Bridge tools
# ─────────────────────────────────────────────────────────────────


async def test_mcp_tools():
    """Test MCP tool definitions."""
    print("\n[Test 6] MCP Tools")

    from cc_router.router_mcp_server import RouterMCPBridge

    bridge = RouterMCPBridge()
    tools = bridge.list_tools()

    tool_names = [t["name"] for t in tools]
    assert "feishu_notify" in tool_names
    assert "forward_to_agent" in tool_names
    assert "read_training_log" in tool_names
    assert "query_experiment_data" in tool_names
    print(f"  ✓ Available tools: {tool_names}")

    # Test feishu_notify
    result = await bridge.call_tool("feishu_notify", {"text": "Hello"})
    assert result["status"] == "ok"
    print("  ✓ feishu_notify works")

    # Test forward_to_agent (no agent connected, but should not crash)
    result = await bridge.call_tool(
        "forward_to_agent", {"event_type": "progress", "content": "test", "task_id": "test_task"}
    )
    assert result["status"] == "ok"
    print("  ✓ forward_to_agent works")

    print("  ✓ MCP tools tests passed")


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────


async def main():
    print("=" * 60)
    print("CC Router Comprehensive Test Suite")
    print("=" * 60)

    tests = [
        test_routing_strategy,
        test_event_bus,
        test_cc_adapter,
        test_agent_adapter_protocol,
        test_hub_integration,
        test_mcp_tools,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            await test()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
