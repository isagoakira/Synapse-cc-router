#!/usr/bin/env python3
"""
Basic smoke test for CC Router.
"""

import asyncio
import sys
from pathlib import Path

# Add cc_router to path
sys.path.insert(0, str(Path(__file__).parent))

from cc_router import (
    UniversalRouterHub,
    CCAdapter,
    CCRegistry,
    UniversalRouter,
    EventBus,
    AgentAdapter,
    HubEvent,
)


async def test_imports():
    """Test that all modules import correctly."""
    print("✓ All imports successful")


async def test_registry():
    """Test CCRegistry."""
    CCRegistry()
    print("✓ CCRegistry created")


async def test_router():
    """Test UniversalRouter."""
    registry = CCRegistry()
    UniversalRouter(registry)
    print("✓ UniversalRouter created")


async def test_event_bus():
    """Test EventBus."""
    bus = EventBus()
    await bus.subscribe("test_agent", "test_task")
    print("✓ EventBus subscribe works")


async def test_cc_adapter():
    """Test CCAdapter instantiation."""
    adapter = CCAdapter(
        cc_id="test_cc",
        workspace="/tmp/test",
        tags=["test"],
        capabilities=["general"],
    )
    assert adapter.cc_id == "test_cc"
    print("✓ CCAdapter created")


async def test_agent_adapter():
    """Test AgentAdapter protocol."""

    class DummyAdapter(AgentAdapter):
        @property
        def agent_id(self) -> str:
            return "dummy"

        @property
        def supported_events(self) -> list[str]:
            return ["result"]

        async def connect(self, hub_url: str = None) -> None:
            pass

        async def disconnect(self) -> None:
            pass

        async def submit_task(
            self, task: str, tag: str = None, capability: list[str] = None, timeout: float = 300.0
        ) -> str:
            return "dummy_task_id"

        async def on_hub_event(self, event: HubEvent) -> None:
            pass

        async def event_stream(self):
            yield  # Empty generator

    adapter = DummyAdapter()
    assert adapter.agent_id == "dummy"
    print("✓ AgentAdapter protocol implemented")


async def test_hub():
    """Test UniversalRouterHub."""
    hub = UniversalRouterHub()
    assert hub.registry is not None
    assert hub.cc_registry is not None
    assert hub.router is not None
    assert hub.event_bus is not None
    print("✓ UniversalRouterHub created")


async def main():
    print("=" * 50)
    print("CC Router Basic Smoke Test")
    print("=" * 50)

    tests = [
        test_imports,
        test_registry,
        test_router,
        test_event_bus,
        test_cc_adapter,
        test_agent_adapter,
        test_hub,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            await test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1

    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
