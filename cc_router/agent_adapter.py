"""
AgentAdapter protocol - any Agent can connect by implementing this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncGenerator, Optional

import asyncio

if TYPE_CHECKING:
    from .router_hub import UniversalRouterHub


@dataclass
class HubEvent:
    """
    Event passed from Hub to Agent (CC callbacks, results, etc.)
    """

    type: str  # "result" | "error" | "partial" | "progress" | "log" | "interrupt"
    task_id: str
    agent_id: str  # target agent
    data: dict  # event payload


class AgentAdapter(ABC):
    """
    Agent adapter protocol.

    Any LLM Agent can connect to UniversalRouterHub by implementing this interface.

    Implementation examples:
    - HermesAgentAdapter (connects to Hermes Gateway)
    - OpenClawAgentAdapter (connects to OpenClaw)
    - WebSocketAgentAdapter (generic WebSocket connection)
    - StdioAgentAdapter (stdio subprocess connection)
    """

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Unique identifier for this agent."""
        ...

    @property
    @abstractmethod
    def supported_events(self) -> list[str]:
        """List of event types this adapter supports receiving."""
        ...

    @abstractmethod
    async def connect(self, hub_url: str = None) -> None:
        """
        Connect to UniversalRouterHub.

        Args:
            hub_url: Hub URL (if applicable, None for internal connection)
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from UniversalRouterHub."""
        ...

    @abstractmethod
    async def submit_task(
        self,
        task: str,
        tag: str = None,
        capability: list[str] = None,
        timeout: float = 300.0,
    ) -> str:
        """
        Submit a task to the Hub.

        Args:
            task: Task description text
            tag: Optional routing tag (e.g., "starfire", "paper")
            capability: Optional capability list (e.g., ["code", "research"])
            timeout: Task timeout in seconds

        Returns:
            task_id for tracking
        """
        ...

    @abstractmethod
    async def on_hub_event(self, event: HubEvent) -> None:
        """
        Handle event pushed from Hub (CC callback triggers this).

        Agent processes messages from CC (progress/notification/result).
        """
        ...

    @abstractmethod
    async def event_stream(self) -> AsyncGenerator[HubEvent, None]:
        """
        Return an async generator for receiving events.

        Agent continuously reads events from Hub via this generator.
        """
        ...
        # This makes it an async generator (not just a coroutine)
        if False:
            yield


class AgentAdapterImpl(AgentAdapter):
    """
    Base implementation with common functionality.
    Subclass this to create custom adapters.
    """

    def __init__(self, agent_id: str):
        self._agent_id = agent_id
        self._hub: Optional["UniversalRouterHub"] = None
        self._event_queue: asyncio.Queue[HubEvent] = asyncio.Queue()
        self._connected = False

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def supported_events(self) -> list[str]:
        return ["result", "error", "partial", "progress", "log"]

    async def connect(self, hub_url: str = None) -> None:
        from .router_hub import get_global_hub

        self._hub = get_global_hub()
        assert self._hub is not None
        self._hub.connect_agent(self._agent_id, self)
        self._connected = True

    async def disconnect(self) -> None:
        if self._hub and self._connected:
            self._hub.disconnect_agent(self._agent_id)
            self._connected = False

    async def submit_task(
        self,
        task: str,
        tag: str = None,
        capability: list[str] = None,
        timeout: float = 300.0,
    ) -> str:
        assert self._hub is not None  # must call connect() first
        return await self._hub.submit_task(
            self._agent_id, task, tag=tag, capability=capability, timeout=timeout
        )

    async def on_hub_event(self, event: HubEvent) -> None:
        await self._event_queue.put(event)

    async def event_stream(self) -> AsyncGenerator[HubEvent, None]:
        while self._connected:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=30.0)
                yield event
            except asyncio.TimeoutError:
                # Heartbeat to keep connection alive
                yield HubEvent(type="heartbeat", task_id="", agent_id=self._agent_id, data={})
