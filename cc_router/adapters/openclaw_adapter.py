"""
OpenClawAgentAdapter - 连接本地 OpenClaw Agent 和 CC Router Hub 的适配器。

支持两种模式:
1. Gateway 模式: OpenClaw Gateway 通过此适配器连接 Hub
2. 子进程模式: Hub 通过 openclaw agent --local --message 子进程调用 OpenClaw
"""

import asyncio
from typing import Optional

from ..agent_adapter import AgentAdapterImpl, HubEvent
from ..openclaw_executor import OpenClawExecutor, OpenClawResult


class OpenClawAgentAdapter(AgentAdapterImpl):
    """
    OpenClaw Agent 适配器。

    将本地 OpenClaw Agent 连接到 UniversalRouterHub:
    - 作为 Agent 连接到 Hub（Gateway 方向）
    - 通过子进程调用 OpenClaw（Executor 方向）
    """

    def __init__(
        self,
        agent_id: str = "openclaw_main",
        openclaw_path: Optional[str] = None,
        executor: Optional[OpenClawExecutor] = None,
    ):
        super().__init__(agent_id)
        self._event_queue: asyncio.Queue[HubEvent] = asyncio.Queue()
        self._connected = False
        self._openclaw_executor = executor or OpenClawExecutor(openclaw_path=openclaw_path)

    @property
    def supported_events(self) -> list[str]:
        return ["result", "error", "partial"]

    async def connect(self, hub_url: str = None) -> None:
        await super().connect(hub_url)
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False
        await super().disconnect()

    async def on_hub_event(self, event: HubEvent) -> None:
        await self._event_queue.put(event)

    async def event_stream(self):
        while self._connected:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=30.0)
                yield event
            except asyncio.TimeoutError:
                yield HubEvent(type="heartbeat", task_id="", agent_id=self._agent_id, data={})

    # ── 子进程执行 ──────────────────────────────────────────────

    async def execute_via_subprocess(
        self,
        task: str,
        timeout: float = 300.0,
        session_id: str = None,
    ) -> OpenClawResult:
        """
        通过子进程调用本地 OpenClaw Agent 执行任务。

        Args:
            task: 任务描述
            timeout: 超时秒数
            session_id: 可选 session ID

        Returns:
            OpenClawResult
        """
        return await self._openclaw_executor.run(task=task, timeout=timeout, session_id=session_id)

    async def kill_executor(self) -> None:
        """终止正在运行的 OpenClaw 子进程。"""
        await self._openclaw_executor.kill()
