"""
CCRegistry - manages all CC instances.
"""

import asyncio
from typing import Dict, List, Optional

from .cc_adapter import CCAdapter, CCInstance
from .exceptions import RegistrationError


class CCRegistry:
    """
    CC instance registry.

    Thread-safe (asyncio Lock).
    """

    def __init__(self):
        self._instances: Dict[str, CCInstance] = {}
        self._adapters: Dict[str, CCAdapter] = {}
        self._lock = asyncio.Lock()

    def register(
        self,
        adapter: CCAdapter,
        workspace: str = None,
        tags: List[str] = None,
        capabilities: List[str] = None,
    ) -> str:
        """
        Register a new CC instance.

        Args:
            adapter: CCAdapter instance
            workspace: Optional workspace override
            tags: Optional tags override
            capabilities: Optional capabilities override

        Returns:
            cc_id of registered instance
        """
        cc_id = adapter.cc_id

        if cc_id in self._adapters:
            raise RegistrationError(f"CC already registered: {cc_id}")

        # Override if provided
        if workspace:
            adapter.workspace = workspace
        if tags:
            adapter.tags = tags
        if capabilities:
            adapter.capabilities = capabilities

        self._instances[cc_id] = adapter.instance
        self._adapters[cc_id] = adapter

        return cc_id

    def unregister(self, cc_id: str) -> None:
        """Unregister a CC instance by ID."""
        self._instances.pop(cc_id, None)
        self._adapters.pop(cc_id, None)

    def get_by_id(self, cc_id: str) -> Optional[CCInstance]:
        """Find a CC instance by its unique ID."""
        return self._instances.get(cc_id)

    def get_by_tag(self, tag: str) -> Optional[CCInstance]:
        """Find first matching (idle or busy) instance with the given tag."""
        for inst in self._instances.values():
            if tag in inst.tag and inst.status in ("idle", "busy"):
                return inst
        return None

    def list_by_status(self, status: str) -> List[CCInstance]:
        """List all instances with given status."""
        return [i for i in self._instances.values() if i.status == status]

    def list_all(self) -> List[CCInstance]:
        """List all instances."""
        return list(self._instances.values())

    def get_adapter(self, cc_id: str) -> Optional[CCAdapter]:
        """Get adapter for instance."""
        return self._adapters.get(cc_id)

    def update_status(self, cc_id: str, status: str, session_id: str = None) -> None:
        """Atomically update instance status."""
        if cc_id in self._instances:
            self._instances[cc_id].status = status
            if session_id:
                self._instances[cc_id].session_id = session_id

    async def update_status_async(self, cc_id: str, status: str, session_id: str = None) -> None:
        """Async version of update_status."""
        async with self._lock:
            self.update_status(cc_id, status, session_id)
