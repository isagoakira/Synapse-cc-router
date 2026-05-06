"""
UniversalRouterHub - Main entry point for the CC Router system.
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .agent_registry import AgentRegistry
from .cc_adapter import CCAdapter, CCResult
from .cc_registry import CCRegistry
from .event_bus import EventBus
from .universal_router import UniversalRouter, RouteResult


@dataclass
class Task:
    """Task unit tracked by Hub."""

    task_id: str
    caller_agent_id: str
    cc_id: str
    task: str
    status: str  # pending | running | done | error
    created_at: str
    result: Optional[CCResult] = None
    error: Optional[str] = None


# Global hub instance
_global_hub: Optional["UniversalRouterHub"] = None


def get_global_hub() -> "UniversalRouterHub":
    """Get the global hub instance."""
    global _global_hub
    if _global_hub is None:
        _global_hub = UniversalRouterHub()
    return _global_hub


class UniversalRouterHub:
    """
    Thread-safe + multi-Agent multi-CC support.

    Stateless: all state in AgentRegistry / CCRegistry / EventBus.
    """

    def __init__(
        self,
        registry: AgentRegistry = None,
        cc_registry: CCRegistry = None,
        router: UniversalRouter = None,
        event_bus: EventBus = None,
    ):
        self.registry = registry or AgentRegistry()
        self.cc_registry = cc_registry or CCRegistry()
        self.router = router or UniversalRouter(self.cc_registry)
        self.event_bus = event_bus or EventBus()
        self._tasks: dict[str, Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._mcp_server = None

    # ── Agent-side API ────────────────────────────────────────────

    def connect_agent(self, agent_id: str, adapter) -> None:
        """Agent connects to Hub via AgentAdapter."""
        self.registry.register_sync(agent_id, adapter)
        # Create global event queue for this agent
        if not hasattr(self.event_bus, "_global"):
            self.event_bus._global[agent_id] = asyncio.Queue()

    def disconnect_agent(self, agent_id: str) -> None:
        """Agent disconnects."""
        self.registry.unregister_sync(agent_id)

    async def submit_task(
        self,
        agent_id: str,
        task: str,
        tag: str = None,
        capability: list[str] = None,
        timeout: float = 300.0,
    ) -> str:
        """
        Agent submits task to Hub.

        Returns task_id (used for tracking and callbacks).
        """
        # 1. Route to CC
        route_result = await self.router.route(task, tag=tag, capability=capability)

        # 2. Create task record
        task_id = str(uuid.uuid4())
        task_obj = Task(
            task_id=task_id,
            caller_agent_id=agent_id,
            cc_id=route_result.cc_id,
            task=task,
            status="pending",
            created_at=datetime.now().isoformat(),
        )
        self._tasks[task_id] = task_obj

        # 3. Subscribe to callback
        await self.event_bus.subscribe(agent_id, task_id)

        # 4. Execute async (non-blocking)
        asyncio.create_task(self._execute_task(task_id, route_result, timeout))

        return task_id

    async def _execute_task(self, task_id: str, route_result: RouteResult, timeout: float) -> None:
        """Internal task execution (async)."""
        task_obj = self._tasks[task_id]
        cc_adapter = self.cc_registry.get_adapter(route_result.cc_id)

        if not cc_adapter:
            task_obj.status = "error"
            task_obj.error = f"CC not found: {route_result.cc_id}"
            await self.event_bus.publish(
                task_obj.caller_agent_id,
                task_id,
                {"type": "error", "error": f"CC not found: {route_result.cc_id}"},
            )
            return

        try:
            task_obj.status = "running"
            result = await cc_adapter.execute(
                task_obj.task,
                caller_agent_id=task_obj.caller_agent_id,
                event_bus=self.event_bus,
                timeout=timeout,
            )
            task_obj.status = "done"
            task_obj.result = result
            await self.event_bus.publish(
                task_obj.caller_agent_id,
                task_id,
                {"type": "result", "result": result.text, "session_id": result.session_id},
            )
        except Exception as e:
            task_obj.status = "error"
            task_obj.error = str(e)
            await self.event_bus.publish(
                task_obj.caller_agent_id, task_id, {"type": "error", "error": str(e)}
            )

    # ── CC-side API ───────────────────────────────────────────────

    def register_cc(self, cc_adapter: CCAdapter) -> str:
        """CC instance registers to Hub."""
        return self.cc_registry.register(cc_adapter)

    def cc_ready(self, cc_id: str, session_id: str = None) -> None:
        """CC instance is ready (available)."""
        self.cc_registry.update_status(cc_id, "idle", session_id)

    # ── Task management ───────────────────────────────────────────

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self, agent_id: str = None) -> list[Task]:
        """List tasks, optionally filtered by agent."""
        tasks = list(self._tasks.values())
        if agent_id:
            tasks = [t for t in tasks if t.caller_agent_id == agent_id]
        return tasks

    # ── MCP Server integration ────────────────────────────────────

    def set_mcp_server(self, mcp_server) -> None:
        """Set the MCP server for this hub."""
        self._mcp_server = mcp_server

    def get_mcp_server(self):
        """Get the MCP server."""
        return self._mcp_server
