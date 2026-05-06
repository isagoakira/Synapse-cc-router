"""
AgentRegistry - manages all connected agents.
"""

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional

from .agent_adapter import AgentAdapter


@dataclass
class AgentNode:
    """Represents a connected agent."""

    agent_id: str  # Unique identifier
    adapter: AgentAdapter  # Adapter implementation
    protocol: str  # "websocket" | "stdio" | "http" | "mcp"
    metadata: dict  # Arbitrary metadata
    connected_at: str  # ISO timestamp
    last_seen: str  # ISO timestamp


class AgentRegistry:
    """
    Agent registry - manages all agents connected to the Hub.

    Thread-safe (asyncio Lock).
    """

    def __init__(self):
        self._agents: Dict[str, AgentNode] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        agent_id: str,
        adapter: AgentAdapter,
        protocol: str = "mcp",
        metadata: dict = None,
    ) -> AgentNode:
        """
        Register a new agent.

        Args:
            agent_id: Unique identifier
            adapter: AgentAdapter implementation
            protocol: Connection protocol
            metadata: Optional metadata

        Returns:
            Created AgentNode
        """
        async with self._lock:
            from datetime import datetime

            node = AgentNode(
                agent_id=agent_id,
                adapter=adapter,
                protocol=protocol,
                metadata=metadata or {},
                connected_at=datetime.now().isoformat(),
                last_seen=datetime.now().isoformat(),
            )
            self._agents[agent_id] = node
            return node

    async def unregister(self, agent_id: str) -> None:
        """Unregister an agent."""
        async with self._lock:
            self._agents.pop(agent_id, None)

    async def get(self, agent_id: str) -> Optional[AgentNode]:
        """Get agent by ID."""
        return self._agents.get(agent_id)

    async def list_all(self) -> List[AgentNode]:
        """List all agents."""
        return list(self._agents.values())

    async def update_last_seen(self, agent_id: str) -> None:
        """Update agent's last_seen timestamp."""
        from datetime import datetime

        if agent_id in self._agents:
            self._agents[agent_id].last_seen = datetime.now().isoformat()

    # Sync versions for non-async contexts
    def register_sync(
        self,
        agent_id: str,
        adapter: AgentAdapter,
        protocol: str = "mcp",
        metadata: dict = None,
    ) -> AgentNode:
        """Synchronous register (for use in connect calls)."""
        from datetime import datetime

        node = AgentNode(
            agent_id=agent_id,
            adapter=adapter,
            protocol=protocol,
            metadata=metadata or {},
            connected_at=datetime.now().isoformat(),
            last_seen=datetime.now().isoformat(),
        )
        self._agents[agent_id] = node
        return node

    def unregister_sync(self, agent_id: str) -> None:
        """Synchronous unregister."""
        self._agents.pop(agent_id, None)

    def get_sync(self, agent_id: str) -> Optional[AgentNode]:
        """Synchronous get."""
        return self._agents.get(agent_id)

    def list_all_sync(self) -> List[AgentNode]:
        """Synchronous list_all."""
        return list(self._agents.values())
