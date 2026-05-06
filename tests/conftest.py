"""
Shared fixtures for CC Router tests.
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from cc_router.cc_adapter import CCAdapter
from cc_router.cc_registry import CCRegistry
from cc_router.agent_adapter import AgentAdapterImpl
from cc_router.agent_registry import AgentRegistry
from cc_router.universal_router import UniversalRouter


@pytest.fixture
def cc_adapter():
    """Provide a basic CCAdapter instance."""
    return CCAdapter(
        cc_id="test_cc",
        workspace="/tmp/test",
        tags=["test"],
        capabilities=["general"],
    )


@pytest.fixture
def cc_registry(cc_adapter):
    """Provide a CCRegistry with one registered instance."""
    registry = CCRegistry()
    registry.register(cc_adapter)
    return registry


@pytest.fixture
def router(cc_registry):
    """Provide a UniversalRouter with registered CC instances."""
    return UniversalRouter(cc_registry)


@pytest.fixture
def agent_adapter():
    """Provide a basic AgentAdapterImpl instance."""
    return AgentAdapterImpl("test_agent")


@pytest.fixture
def agent_registry(agent_adapter):
    """Provide an AgentRegistry with one registered agent."""
    registry = AgentRegistry()
    registry.register_sync("test_agent", agent_adapter)
    return registry


@pytest.fixture
def event_bus():
    """Provide a fresh EventBus instance."""
    from cc_router.event_bus import EventBus

    return EventBus()
