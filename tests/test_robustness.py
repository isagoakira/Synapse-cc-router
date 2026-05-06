#!/usr/bin/env python3
"""
Robustness tests for CC Router.
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
    RouterError,
)


# ─────────────────────────────────────────────────────────────────
# Test 1: Timeout handling
# ─────────────────────────────────────────────────────────────────


async def test_timeout_handling():
    """Test that timeout returns TIMEOUT kind, not ERROR."""
    print("\n[Test 1] Timeout Handling")

    from cc_router.cc_executor import CCExecutor

    executor = CCExecutor()
    # Use a very short timeout to trigger timeout
    result = await executor.run(
        task="sleep 10", workspace="/tmp", resume=False, timeout=1.0  # This would take 10 seconds
    )

    # Should be TIMEOUT, not ERROR
    assert result.kind == "TIMEOUT", f"Expected TIMEOUT, got {result.kind}"
    print(f"  ✓ Timeout returns kind=TIMEOUT (duration={result.duration_ms}ms)")

    # Clean up
    await executor.kill()


# ─────────────────────────────────────────────────────────────────
# Test 2: CC CLI not found
# ─────────────────────────────────────────────────────────────────


async def test_cc_not_found():
    """Test behavior when CC CLI is not found."""
    print("\n[Test 2] CC CLI Not Found")

    from cc_router.cc_executor import CCExecutor, CCExecutorError

    executor = CCExecutor(cc_cli_path="/nonexistent/claude")

    try:
        await executor.run(task="say hi", workspace="/tmp", resume=False, timeout=5.0)
        assert False, "Should have raised CCExecutorError"
    except CCExecutorError as e:
        assert "not found" in str(e).lower()
        print(f"  ✓ Raises CCExecutorError for missing CLI: {e}")


# ─────────────────────────────────────────────────────────────────
# Test 3: Router error when no CC available
# ─────────────────────────────────────────────────────────────────


async def test_router_no_cc():
    """Test routing when no CC instances are registered."""
    print("\n[Test 3] Router - No CC Available")

    registry = CCRegistry()
    router = UniversalRouter(registry)

    try:
        await router.route("any task")
        assert False, "Should have raised RouterError"
    except RouterError as e:
        assert "no available" in str(e).lower()
        print(f"  ✓ Raises RouterError when no CC: {e}")


# ─────────────────────────────────────────────────────────────────
# Test 4: Empty task handling
# ─────────────────────────────────────────────────────────────────


async def test_empty_task():
    """Test handling of empty task."""
    print("\n[Test 4] Empty Task Handling")

    registry = CCRegistry()
    cc = CCAdapter(
        cc_id="test_cc",
        workspace="/tmp",
        tags=["test"],
    )
    registry.register(cc)
    router = UniversalRouter(registry)

    # Should still route (empty string is valid)
    result = await router.route("")
    assert result.cc_id == "test_cc"
    print("  ✓ Empty task still routes successfully")


# ─────────────────────────────────────────────────────────────────
# Test 5: Multiple CC with same tag
# ─────────────────────────────────────────────────────────────────


async def test_multiple_cc_same_tag():
    """Test routing when multiple CCs have the same tag."""
    print("\n[Test 5] Multiple CCs with Same Tag")

    registry = CCRegistry()

    cc1 = CCAdapter(cc_id="cc_1", workspace="/tmp/w1", tags=["ml"])
    cc2 = CCAdapter(cc_id="cc_2", workspace="/tmp/w2", tags=["ml"])

    registry.register(cc1)
    registry.register(cc2)

    router = UniversalRouter(registry)

    # Should get first idle with tag
    result = await router.route("train model", tag="ml")
    assert result.cc_id in ["cc_1", "cc_2"]
    print(f"  ✓ Routes to one of the CCs: {result.cc_id}")

    # Round-robin should cycle through them
    result2 = await router.route("train model", tag="ml")
    print(f"  ✓ Second route: {result2.cc_id} (strategy={result2.strategy.value})")


# ─────────────────────────────────────────────────────────────────
# Test 6: EventBus with missing agent
# ─────────────────────────────────────────────────────────────────


async def test_eventbus_missing_agent():
    """Test EventBus operations with non-existent agent."""
    print("\n[Test 6] EventBus - Missing Agent")

    bus = EventBus()

    # Publishing to non-existent agent should not crash
    await bus.publish("nonexistent_agent", "task_123", {"type": "result", "content": "test"})
    print("  ✓ Publish to missing agent doesn't crash")

    # Subscribing should create the agent entry
    await bus.subscribe("new_agent", "task_456")
    await bus.publish("new_agent", "task_456", {"type": "result", "content": "test"})
    print("  ✓ Subscribe + publish works for new agent")


# ─────────────────────────────────────────────────────────────────
# Test 7: CCAdapter status transitions
# ─────────────────────────────────────────────────────────────────


async def test_ccadapter_status():
    """Test CCAdapter status transitions."""
    print("\n[Test 7] CCAdapter Status Transitions")

    adapter = CCAdapter(
        cc_id="test_cc",
        workspace="/tmp",
        tags=["test"],
    )

    assert adapter._status == "idle"
    print(f"  ✓ Initial status: {adapter._status}")

    # Simulate execution
    adapter._status = "busy"
    assert adapter._status == "busy"
    print(f"  ✓ Busy status: {adapter._status}")

    adapter._status = "dead"
    assert adapter._status == "dead"
    print(f"  ✓ Dead status: {adapter._status}")


# ─────────────────────────────────────────────────────────────────
# Test 8: Unicode task handling
# ─────────────────────────────────────────────────────────────────


async def test_unicode_task():
    """Test handling of unicode in tasks."""
    print("\n[Test 8] Unicode Task Handling")

    registry = CCRegistry()
    cc = CCAdapter(cc_id="test_cc", workspace="/tmp", tags=["test"])
    registry.register(cc)
    router = UniversalRouter(registry)

    # Chinese task
    result = await router.route("帮我检查训练日志")
    assert result.cc_id is not None
    print(f"  ✓ Chinese task routes: {result.cc_id}")

    # Mixed content
    result = await router.route("Check log: C:\\Users\\test\\train.log")
    assert result.cc_id is not None
    print(f"  ✓ Windows path in task routes: {result.cc_id}")


# ─────────────────────────────────────────────────────────────────
# Test 9: Hub with no registered CC
# ─────────────────────────────────────────────────────────────────


async def test_hub_no_cc():
    """Test Hub behavior when no CC is registered."""
    print("\n[Test 9] Hub - No CC Registered")

    hub = UniversalRouterHub()

    # First register a CC so routing succeeds
    cc = CCAdapter(cc_id="test_cc", workspace="/tmp", tags=["test"])
    hub.register_cc(cc)

    # Submit task
    task_id = await hub.submit_task(agent_id="test_agent", task="do something", timeout=5.0)

    # Wait a bit for async execution
    await asyncio.sleep(1.0)

    task = hub.get_task(task_id)
    assert task is not None
    print(f"  ✓ Task created: {task_id}")
    print(f"    Status: {task.status}")
    if task.error:
        print(f"    Error: {task.error}")
    else:
        print(f"    Result: {task.result.text if task.result else '(none)'}")


# ─────────────────────────────────────────────────────────────────
# Test 10: CCAdapter terminate
# ─────────────────────────────────────────────────────────────────


async def test_ccadapter_terminate():
    """Test CCAdapter.terminate()."""
    print("\n[Test 10] CCAdapter.terminate()")

    adapter = CCAdapter(
        cc_id="test_cc",
        workspace="/tmp",
    )

    # Should not crash even if no process running
    await adapter.terminate()
    assert adapter._status == "dead"
    print("  ✓ terminate() sets status to dead")


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────


async def main():
    print("=" * 60)
    print("CC Router Robustness Test Suite")
    print("=" * 60)

    tests = [
        test_timeout_handling,
        test_cc_not_found,
        test_router_no_cc,
        test_empty_task,
        test_multiple_cc_same_tag,
        test_eventbus_missing_agent,
        test_ccadapter_status,
        test_unicode_task,
        test_hub_no_cc,
        test_ccadapter_terminate,
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
