"""
EventBus - bidirectional async event bus for CC↔Agent communication.
"""

import asyncio
from typing import AsyncIterator, Dict

from .agent_adapter import HubEvent


class EventBus:
    """
    Async event bus for bidirectional communication.

    Publish-subscribe model:
    - Agent subscribes to task results: subscribe(agent_id, task_id)
    - CC publishes events: publish(agent_id, task_id, event_data)
    - Agent receives via event_stream()

    Also supports:
    - Hub → CC control commands (interrupt / cancel)
    - CC → Agent callbacks (progress / log / result)
    """

    def __init__(self):
        # agent_id → {task_id → asyncio.Queue[HubEvent]}
        self._subscriptions: Dict[str, Dict[str, asyncio.Queue]] = {}
        # Global agent event channels (not limited by task_id)
        self._global: Dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    # ── Agent subscription ─────────────────────────────────────────

    async def subscribe(self, agent_id: str, task_id: str) -> None:
        """Agent subscribes to specific task result."""
        async with self._lock:
            if agent_id not in self._subscriptions:
                self._subscriptions[agent_id] = {}
            if task_id not in self._subscriptions[agent_id]:
                self._subscriptions[agent_id][task_id] = asyncio.Queue()
            if agent_id not in self._global:
                self._global[agent_id] = asyncio.Queue()

    async def unsubscribe(self, agent_id: str, task_id: str) -> None:
        """Unsubscribe from task events."""
        async with self._lock:
            if agent_id in self._subscriptions:
                self._subscriptions[agent_id].pop(task_id, None)

    async def event_stream(self, agent_id: str) -> AsyncIterator[HubEvent]:
        """
        Agent's event stream (merges task events + global events).

        Yields events as they arrive. Global events have higher priority.
        """
        while True:
            event = None

            # Check global events first (high priority)
            try:
                event = self._global[agent_id].get_nowait()
            except (asyncio.QueueEmpty, KeyError):
                pass

            # Then check task events
            if not event:
                async with self._lock:
                    for task_queues in self._subscriptions.get(agent_id, {}).values():
                        try:
                            event = task_queues.get_nowait()
                            break
                        except asyncio.QueueEmpty:
                            continue

            if event:
                yield event
            else:
                await asyncio.sleep(0.1)  # Yield when no events

    # ── CC / Hub publish ───────────────────────────────────────────

    async def publish(self, agent_id: str, task_id: str, event_data: dict) -> None:
        """CC or Hub publishes event to Agent."""
        event = HubEvent(
            type=event_data["type"], task_id=task_id, agent_id=agent_id, data=event_data
        )

        async with self._lock:
            # Send to task-specific channel
            if agent_id in self._subscriptions:
                q = self._subscriptions[agent_id].get(task_id)
                if q:
                    await q.put(event)

            # Also send to global channel
            if agent_id in self._global:
                await self._global[agent_id].put(event)

    # ── Control commands (Hub → CC) ───────────────────────────────

    async def send_interrupt(self, cc_id: str, task_id: str, reason: str = None) -> None:
        """
        Agent sends interrupt command to CC via Hub.

        CCAdapter listens on this channel and terminates process.
        """
        # Broadcast via global to all agents (they forward to their CC)
        for agent_id in self._global:
            await self._global[agent_id].put(
                HubEvent(
                    type="interrupt",
                    task_id=task_id,
                    agent_id=cc_id,  # cc_id as target
                    data={"reason": reason, "cc_id": cc_id},
                )
            )
