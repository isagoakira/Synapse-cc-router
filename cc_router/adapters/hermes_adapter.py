"""
HermesAgentAdapter - 连接本地 Hermes Gateway 和 CC Router Hub 的适配器。

支持两种模式:
1. Gateway 模式: Hermes Gateway 通过此适配器连接 Hub，提交任务到 CC 实例
2. 子进程模式: Hub 通过 hermes chat -q 子进程调用本地 Hermes Agent
"""

import asyncio
from typing import Optional

from ..agent_adapter import AgentAdapterImpl, HubEvent
from ..hermes_executor import HermesExecutor, HermesResult


class HermesAgentAdapter(AgentAdapterImpl):
    """
    Hermes Agent 适配器。

    将本地 Hermes Agent 连接到 UniversalRouterHub:
    - 作为 Agent 连接到 Hub（Gateway 方向）
    - 通过子进程调用 Hermes（Executor 方向）
    """

    def __init__(
        self,
        agent_id: str = "hermes_gateway",
        hermes_path: Optional[str] = None,
        executor: Optional[HermesExecutor] = None,
    ):
        super().__init__(agent_id)
        self._event_queue: asyncio.Queue[HubEvent] = asyncio.Queue()
        self._connected = False
        self._hermes_executor = executor or HermesExecutor(hermes_path=hermes_path)

    @property
    def supported_events(self) -> list[str]:
        return ["result", "error", "partial", "progress", "log", "heartbeat"]

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
    ) -> HermesResult:
        """
        通过子进程调用本地 Hermes Agent 执行任务。

        这是 "Hub → Hermes" 方向:
        Hub 可以直接调用本地 Hermes 来处理任务（如研究、写作等）。

        Args:
            task: 任务描述
            timeout: 超时秒数

        Returns:
            HermesResult
        """
        return await self._hermes_executor.run(task=task, timeout=timeout)

    async def kill_executor(self) -> None:
        """终止正在运行的 Hermes 子进程。"""
        await self._hermes_executor.kill()
