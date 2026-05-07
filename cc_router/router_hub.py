"""
UniversalRouterHub - Main entry point for the CC Router system.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from .agent_registry import AgentRegistry
from .cc_adapter import CCAdapter, CCResult
from .cc_registry import CCRegistry
from .event_bus import EventBus
from .universal_router import UniversalRouter, RouteResult
from .config import (
    get_health_check_interval,
    get_max_concurrent,
    get_max_consecutive_failures,
)

logger = logging.getLogger(__name__)


@dataclass
class Task:
    """Task unit tracked by Hub."""

    task_id: str
    caller_agent_id: str
    cc_id: str
    task: str
    status: str  # pending | running | done | error | queued
    created_at: str
    result: Optional[CCResult] = None
    error: Optional[str] = None
    tag: Optional[str] = None
    capability: Optional[list[str]] = None
    timeout: float = 300.0


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

        # ── Parallel capacity & queuing ──────────────────────────
        self._max_concurrent: int = get_max_concurrent()
        self._task_queue: asyncio.Queue[tuple[str, RouteResult, float]] = asyncio.Queue()
        self._queue_processor_task: Optional[asyncio.Task] = None
        self._active_task_count: int = 0
        self._capacity_lock = asyncio.Lock()

        # ── Health monitoring ────────────────────────────────────
        self._health_interval: float = get_health_check_interval()
        self._max_failures: int = get_max_consecutive_failures()
        self._health_task: Optional[asyncio.Task] = None
        self._consecutive_failures: dict[str, int] = {}
        self._health_running = False

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

        If at max concurrent capacity, the task is queued and executed
        when a CC instance becomes available.

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
            tag=tag,
            capability=capability,
            timeout=timeout,
        )
        self._tasks[task_id] = task_obj

        # 3. Subscribe to callback
        await self.event_bus.subscribe(agent_id, task_id)

        # 4. Check capacity — queue if at limit
        async with self._capacity_lock:
            if self._active_task_count >= self._max_concurrent:
                task_obj.status = "queued"
                await self._task_queue.put((task_id, route_result, timeout))
                logger.info(
                    "Task %s queued (active=%d, max=%d)",
                    task_id,
                    self._active_task_count,
                    self._max_concurrent,
                )
                return task_id

            self._active_task_count += 1

        # 5. Execute async (non-blocking)
        asyncio.create_task(self._execute_task(task_id, route_result, timeout))

        return task_id

    async def _process_queue(self) -> None:
        """
        Background task that processes the task queue when capacity frees up.
        """
        while True:
            task_id, route_result, timeout = await self._task_queue.get()

            # Check if the task was cancelled
            task_obj = self._tasks.get(task_id)
            if not task_obj or task_obj.status == "error":
                self._task_queue.task_done()
                continue

            # Check capacity before dequeuing
            async with self._capacity_lock:
                if self._active_task_count >= self._max_concurrent:
                    # Still full — put back and wait
                    await self._task_queue.put((task_id, route_result, timeout))
                    self._task_queue.task_done()
                    await asyncio.sleep(0.5)
                    continue
                self._active_task_count += 1

            task_obj.status = "pending"
            asyncio.create_task(self._execute_task(task_id, route_result, timeout))
            self._task_queue.task_done()

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
            await self._decrement_active()
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
        finally:
            await self._decrement_active()

    async def _decrement_active(self) -> None:
        """Decrement active task count and wake queue processor."""
        async with self._capacity_lock:
            self._active_task_count = max(0, self._active_task_count - 1)

    # ── CC-side API ───────────────────────────────────────────────

    def register_cc(self, cc_adapter: CCAdapter) -> str:
        """CC instance registers to Hub."""
        cc_id = self.cc_registry.register(cc_adapter)
        # Track failures for new instance
        self._consecutive_failures[cc_id] = 0
        return cc_id

    def cc_ready(self, cc_id: str, session_id: str = None) -> None:
        """CC instance is ready (available)."""
        self.cc_registry.update_status(cc_id, "idle", session_id)
        self._consecutive_failures[cc_id] = 0

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

    # ── Capacity management ───────────────────────────────────────

    @property
    def max_concurrent(self) -> int:
        """Get max concurrent task limit."""
        return self._max_concurrent

    @max_concurrent.setter
    def max_concurrent(self, value: int) -> None:
        """Set max concurrent task limit."""
        self._max_concurrent = max(1, value)
        logger.info("Max concurrent tasks set to %d", self._max_concurrent)

    @property
    def active_task_count(self) -> int:
        """Get current active task count."""
        return self._active_task_count

    @property
    def queued_task_count(self) -> int:
        """Get current queued task count."""
        return self._task_queue.qsize()

    # ── Health Monitoring ─────────────────────────────────────────

    async def _health_check_cycle(self) -> None:
        """
        Run one health check cycle across all CC instances.

        For each instance:
        - If busy: check if the subprocess is still alive
        - If dead: increment consecutive failures counter
        - If consecutive failures exceed threshold: mark as dead
        """
        for cc_adapter in list(self.cc_registry._adapters.values()):
            cc_id = cc_adapter.cc_id
            try:
                status = await cc_adapter.health_check()
                inst = self.cc_registry.get_by_id(cc_id)

                if not inst:
                    continue

                if status["status"] == "busy" and not status["process_alive"]:
                    # Process died unexpectedly
                    logger.warning("CC %s process died unexpectedly", cc_id)
                    fails = self._consecutive_failures.get(cc_id, 0) + 1
                    self._consecutive_failures[cc_id] = fails

                    if fails >= self._max_failures:
                        logger.error(
                            "CC %s marked dead after %d consecutive failures",
                            cc_id,
                            fails,
                        )
                        self.cc_registry.update_status(cc_id, "dead")
                    else:
                        self.cc_registry.update_status(cc_id, "starting")
                elif status["status"] in ("idle", "starting"):
                    # Healthy — reset failure counter
                    self._consecutive_failures[cc_id] = 0
                elif status["status"] == "dead":
                    # Already dead, increment if not yet at threshold
                    if self._consecutive_failures.get(cc_id, 0) < self._max_failures:
                        self._consecutive_failures[cc_id] = (
                            self._consecutive_failures.get(cc_id, 0) + 1
                        )

            except Exception as e:
                logger.error("Health check failed for CC %s: %s", cc_id, e)
                fails = self._consecutive_failures.get(cc_id, 0) + 1
                self._consecutive_failures[cc_id] = fails
                if fails >= self._max_failures:
                    self.cc_registry.update_status(cc_id, "dead")

    async def _health_monitor_loop(self) -> None:
        """Background loop that periodically runs health checks."""
        self._health_running = True
        logger.info(
            "Health monitor started (interval=%ds, max_failures=%d)",
            self._health_interval,
            self._max_failures,
        )

        try:
            while self._health_running:
                await asyncio.sleep(self._health_interval)
                await self._health_check_cycle()
        except asyncio.CancelledError:
            pass
        finally:
            self._health_running = False
            logger.info("Health monitor stopped")

    def start_health_monitor(self) -> None:
        """Start the background health monitoring task."""
        if self._health_task is not None and not self._health_task.done():
            logger.warning("Health monitor already running")
            return
        self._health_task = asyncio.create_task(self._health_monitor_loop())

    def stop_health_monitor(self) -> None:
        """Stop the background health monitoring task."""
        self._health_running = False
        if self._health_task and not self._health_task.done():
            self._health_task.cancel()

    def start_queue_processor(self) -> None:
        """Start the background queue processor task."""
        if self._queue_processor_task is not None and not self._queue_processor_task.done():
            logger.warning("Queue processor already running")
            return
        self._queue_processor_task = asyncio.create_task(self._process_queue())

    def stop_queue_processor(self) -> None:
        """Stop the background queue processor task."""
        if self._queue_processor_task and not self._queue_processor_task.done():
            self._queue_processor_task.cancel()

    def start_background_tasks(self) -> None:
        """Start all background tasks (health monitor + queue processor)."""
        self.start_health_monitor()
        self.start_queue_processor()

    def stop_background_tasks(self) -> None:
        """Stop all background tasks."""
        self.stop_health_monitor()
        self.stop_queue_processor()

    def get_health_summary(self) -> dict[str, Any]:
        """
        Get a comprehensive health summary of the Hub.

        Returns:
            dict with instance status breakdown, active/queued task counts,
            and instance-level health details.
        """
        cc_instances = self.cc_registry.list_all()

        status_counts: dict[str, int] = {}
        instance_health: list[dict[str, Any]] = []
        for inst in cc_instances:
            status_counts[inst.status] = status_counts.get(inst.status, 0) + 1
            instance_health.append(
                {
                    "cc_id": inst.cc_id,
                    "status": inst.status,
                    "workspace": inst.workspace,
                    "tags": inst.tag if hasattr(inst, "tag") else [],
                    "capabilities": inst.capability if hasattr(inst, "capability") else [],
                    "has_session": bool(inst.session_id),
                    "consecutive_failures": self._consecutive_failures.get(inst.cc_id, 0),
                }
            )

        tasks = self.list_tasks()
        task_counts = {"pending": 0, "running": 0, "done": 0, "error": 0, "queued": 0}
        for t in tasks:
            if t.status in task_counts:
                task_counts[t.status] += 1

        return {
            "cc_instances": {
                "count": len(cc_instances),
                "by_status": status_counts,
                "details": instance_health,
            },
            "tasks": {
                "count": len(tasks),
                **task_counts,
            },
            "capacity": {
                "max_concurrent": self._max_concurrent,
                "active": self._active_task_count,
                "queued": self._task_queue.qsize(),
                "available_slots": max(0, self._max_concurrent - self._active_task_count),
            },
            "monitoring": {
                "health_running": self._health_running,
                "health_interval": self._health_interval,
                "max_failures": self._max_failures,
            },
        }

    # ── MCP Server integration ────────────────────────────────────

    def set_mcp_server(self, mcp_server) -> None:
        """Set the MCP server for this hub."""
        self._mcp_server = mcp_server

    def get_mcp_server(self):
        """Get the MCP server."""
        return self._mcp_server
