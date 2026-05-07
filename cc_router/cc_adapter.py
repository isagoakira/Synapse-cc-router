"""
CCAdapter - each CC instance connects to Hub via this adapter.
"""

from dataclasses import dataclass, field
from typing import Optional

from .cc_executor import CCExecutor
from .config import get_cc_cli_path


@dataclass
class CCResult:
    """
    Result from CC execution.
    """

    kind: str  # SUCCESS / ERROR / AUTH_CLI / AUTH_API / TIMEOUT / CRASH
    text: str  # Text result
    session_id: str
    cost_usd: float
    duration_ms: int
    error: str = ""


@dataclass
class CCInstance:
    """
    Represents a CC (Claude Code) instance.
    """

    cc_id: str  # "cc_001"
    workspace: str  # Workspace absolute path
    tag: list[str] = field(default_factory=list)  # Multiple routing tags ["starfire", "ml"]
    capability: list[str] = field(default_factory=list)  # ["code", "research", "paper"]
    status: str = "idle"  # idle | busy | starting | dead
    session_id: str = ""
    pid: int = 0
    adapter: Optional["CCAdapter"] = None  # Reference back to adapter
    metadata: dict = field(default_factory=dict)


class CCAdapter:
    """
    CC instance adapter.

    Each CC instance corresponds to one CCAdapter in the Hub.
    CCAdapter internally manages CCExecutor (subprocess),
    exposing a unified execute() interface to the Hub.
    """

    def __init__(
        self,
        cc_id: str,
        workspace: str,
        tags: list[str] = None,
        capabilities: list[str] = None,
        cc_cli_path: str = None,
    ):
        self.cc_id = cc_id
        self.workspace = workspace
        self.tags = tags or []
        self.capabilities = capabilities or ["general"]
        self.cc_cli_path = cc_cli_path or get_cc_cli_path()
        self._executor = CCExecutor(cc_cli_path=self.cc_cli_path)
        self._current_task: Optional[str] = None
        self._status = "idle"
        self._session_id: str = ""

    @property
    def instance(self) -> CCInstance:
        """Return CCInstance representation."""
        return CCInstance(
            cc_id=self.cc_id,
            workspace=self.workspace,
            tag=self.tags,
            capability=self.capabilities,
            status=self._status,
            session_id=self._session_id,
            pid=0,  # Filled at runtime
            adapter=self,
            metadata={},
        )

    async def execute(
        self,
        task: str,
        caller_agent_id: str,
        event_bus=None,
        resume: bool = True,
        timeout: float = 300.0,
    ) -> CCResult:
        """
        Execute a task on this CC instance.
        Optionally push partial messages via event_bus if subscribed.
        """
        self._status = "busy"
        self._current_task = task

        try:
            # TODO: Implement partial message forwarding via event_bus
            # if event_bus:
            #     await event_bus.publish(caller_agent_id, task_id, {"type": "partial", ...})

            result = await self._executor.run(
                task=task,
                workspace=self.workspace,
                session_id=self._session_id if resume else None,
                resume=resume,
                timeout=timeout,
            )

            if result.kind == "SUCCESS":
                self._session_id = result.session_id
                self._status = "idle"
            else:
                # Auth errors mean CC is dead, needs re-auth
                self._status = "dead" if result.kind in ("AUTH_CLI", "AUTH_API") else "idle"

            return CCResult(
                kind=result.kind,
                text=result.text,
                session_id=result.session_id,
                cost_usd=result.cost_usd,
                duration_ms=result.duration_ms,
                error=result.error,
            )

        finally:
            self._current_task = None

    async def health_check(self) -> dict:
        """
        Run a health check on this CC instance.

        Returns:
            dict with keys:
              - cc_id: str
              - status: str (idle / busy / dead / starting)
              - process_alive: bool (whether subprocess is running)
              - has_session: bool (whether a session_id is stored)
        """
        process_alive = self._executor.is_process_alive() if self._status == "busy" else True
        return {
            "cc_id": self.cc_id,
            "status": self._status,
            "process_alive": process_alive,
            "has_session": bool(self._session_id),
        }

    async def terminate(self) -> None:
        """Force terminate CC process."""
        self._status = "dead"
        await self._executor.kill()

    async def get_status(self) -> dict:
        """Get CC instance status."""
        return {
            "cc_id": self.cc_id,
            "status": self._status,
            "session_id": self._session_id,
            "current_task": self._current_task,
        }
