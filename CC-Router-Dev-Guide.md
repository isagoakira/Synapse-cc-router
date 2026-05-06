# CC Router 多CC并行工作系统 — 完整开发指南

> **编写日期**：2026-05-06
> **更新**：2026-05-06 Rev.2 — 双端适配接口、重构为通用多Agent↔多CC连接中枢
> **背景**：bbhermes (Plan A) 因 WSL/Windows DrvFs 文件系统不互通已废弃，Plan B CC Router 设计存在于 skills 但代码从未实现。本文档从零描述完整架构。

---

## 1. 系统定位与目标

### 1.1 问题陈述

现有方案的局限：

| 方案 | 并行度 | Agent 接入方式 | CC 回调能力 |
|------|--------|----------------|-------------|
| 单 LLM Agent | 1 | — | 无 |
| bbhermes (Plan A) | N | Hermes 专有 | 无（轮询） |
| **通用 CC Router Hub（本方案）** | **N×M** | **任意 Agent（Adapter 接口）** | **双向 MCP** |

需要一个**通用中枢**，支持：
- **任意 LLM Agent**（Hermes/OpenClaw/自定义）通过标准 Adapter 接入
- **任意 CC 实例**通过 CCAdapter 接入，成为可被调度的计算资源
- **双向通信**：Caller Agent → CC 执行任务；CC → Caller Agent 回调通知/进度
- **MCP 协议**作为双端适配的统一语言

### 1.2 设计目标

```
┌──────────────────────────────────────────────────────────────────┐
│                     UniversalRouterHub                          │
│  ① AgentRegistry   ② UniversalRouter   ③ EventBus   ④ MCCPServer│
└──────────────────────────────────────────────────────────────────┘
       │                          │                    │
  ┌────┴────┐                ┌───┴────┐          ┌───┴────┐
  │Adapter A│                │Adapter B│          │Adapter N│
  │(Hermes) │                │(OpenClaw)│         │(自定义) │
  └────┬────┘                └────┬────┘          └────┬────┘
       │ CC#1..N                  │ CC#1..N            │ CC#1..N
  ┌────┴────┐                ┌────┴────┐          ┌────┴────┐
  │CCAdapter│               │CCAdapter│          │CCAdapter│
  └────┬────┘                └────┬────┘          └────┬────┘
       │                          │                    │
  ┌────┴──────────────────────────┴────────────────────┴────┐
  │              CCInstance₁  CCInstance₂ ... CCInstanceN   │
  └─────────────────────────────────────────────────────────┘
```

### 1.3 核心需求

| 需求 | 说明 |
|------|------|
| 多 CC 并行 | ≥3 个 CC 实例同时运行，独立 PID |
| 多 Agent 接入 | 任意 LLM Agent 通过 AgentAdapter 协议接入 |
| 双向 MCP | CC 可调用 Agent 提供的 MCP Tools，Agent 可推送事件给 CC |
| 路由决策 | 按 tag/workspace/capability 自动分发 |
| 会话保持 | CC 支持 `--resume` 跨任务连续 |
| 平台无关 | Hub 在 WSL，CC 可在 WSL 或 Windows |
| 透明性 | CC 执行过程可实时回调给 Agent（非黑箱） |

---

## 2. 架构总览

### 2.1 分层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Caller Agent 层                            │
│          HermesGateway / OpenClaw / 自定义Agent / AnyMCPClient       │
│                                    │                                 │
│                          AgentAdapter (RFC)                          │
│         ┌──────────────────────────────────────────────┐             │
│         │  connect(agent_id) → event_channel          │             │
│         │  submit_task(task) → task_id                 │             │
│         │  on_task_result(task_id) → CCResult         │             │
│         │  on_event(event) → None  (push from CC)      │             │
│         └──────────────────────────────────────────────┘             │
└────────────────────────────────────┬────────────────────────────────┘
                                     │ WebSocket / stdio / HTTP
                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     UniversalRouterHub (URH)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │
│  │AgentRegistry│  │UniversalRouter│ │  EventBus    │  │MCP Server │ │
│  │ (多Agent)   │  │ (tag/路径/   │  │ (CC→Agent   │  │(共享服务) │ │
│  │             │  │  capability) │  │  双向回调)   │  │           │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └───────────┘ │
└────────────────────────────────────┬────────────────────────────────┘
                                     │ stream-json / stdio
              ┌──────────────────────┼──────────────────────┐
              ▼                      ▼                      ▼
       ┌──────────┐           ┌──────────┐           ┌──────────┐
       │CCAdapter │           │CCAdapter │           │CCAdapter │
       │  001     │           │  002     │           │  003     │
       │(workspace│           │(workspace│           │(workspace│
       │ /tag:v1) │           │ /tag:v2) │           │ /tag:rt) │
       └────┬─────┘           └────┬─────┘           └────┬─────┘
            │                      │                      │
            └──────────────────────┴──────────────────────┘
                           WSL subprocess
                   (或 Windows WSLInterop → claude.exe)
```

### 2.2 核心数据流

#### 2.2.1 Agent→CC 任务下发

```
Agent: "帮我检查 starfire 的训练日志"
    │
    ▼
AgentAdapter.submit_task(task, tag="starfire")
    │
    ▼
UniversalRouterHub.route(task, tag="starfire")
    │ 路由策略:
    │  1. tag 精确匹配 → CCAdapter_001 (tag=starfire)
    │  2. workspace 路径匹配
    │  3. capability 关键词
    │  4. round-robin / 第一个 idle
    ▼
EventBus.subscribe(agent_id, task_id)  ← 注册回调通道
    │
    ▼
CCAdapter_001.execute(task, caller_agent_id)
    │
    ▼
CCExecutor.run(task, workspace, session_id?, resume=True)
    │ Spawn: claude --print --input-format=stream-json
    │         --output-format=stream-json [--resume SESSION_ID]
    │
    │ ← stdout NDJSON 事件流
    │   可选：实时通过 EventBus 转发 partial 消息给 Agent
    │
    ▼
CCResult { kind, text, session_id, cost, duration }
    │
    ▼
EventBus.publish(agent_id, task_id, CCResult)  ← 回调通知
    │
    ▼
AgentAdapter.on_task_result(task_id, result) → Agent 收到结果
```

#### 2.2.2 CC→Agent 双向回调（CC 主动发消息给 Agent）

```
CCInstance 执行中，检测到需要飞书通知 / 查询共享数据
    │
    ▼
CC 调用 MCP Tool (via 内置 MCP Client)
    │
    ▼
RouterHub MCP Server 收到调用
    │
    ▼
识别 target_agent_id（从 task context 获得）
    │
    ▼
EventBus.forward_to_agent(tool_result, target_agent_id)
    │
    ▼
AgentAdapter.on_event(event) → Agent 实时收到 CC 的回调
```

---

## 3. 核心组件详解

### 3.1 UniversalRouterHub (`router_hub.py`)

**职责**：全局路由中枢，不绑定任何特定 Agent，实现多 Agent↔多 CC 的全连接。

**关键概念**：
- **Agent**：连接到 Hub 的调用方（可以是 Hermes Gateway、OpenClaw、任意自定义 Agent）
- **CCInstance**：可被调度的 CC 计算资源
- **Task**：任务单元，包含 task_id、caller_agent_id、cc_id、状态、结果

```python
class UniversalRouterHub:
    """
    线程安全（asyncio）+ 多 Agent 多 CC 支持
    无状态：所有状态在 AgentRegistry / CCRunner / EventBus 中
    """

    def __init__(
        self,
        registry: "AgentRegistry",
        cc_registry: "CCRegistry",
        router: "UniversalRouter",
        event_bus: "EventBus",
        mcp_server: "RouterMCPServer",
    ):
        self.registry = registry
        self.cc_registry = cc_registry
        self.router = router
        self.event_bus = event_bus
        self.mcp_server = mcp_server
        self._tasks: dict[str, Task] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # ── Agent 侧 API ──────────────────────────────────────────────

    def connect_agent(self, agent_id: str, adapter: "AgentAdapter") -> None:
        """Agent 连接到 Hub（通过 AgentAdapter 实现）"""
        self.registry.register(agent_id, adapter)
        self.event_bus.register_agent(agent_id)

    def disconnect_agent(self, agent_id: str) -> None:
        """Agent 断开连接"""
        self.registry.unregister(agent_id)
        self.event_bus.unregister_agent(agent_id)

    async def submit_task(
        self,
        agent_id: str,
        task: str,
        tag: str = None,
        capability: list[str] = None,
        timeout: float = 300.0,
    ) -> str:
        """
        Agent 下发任务给 Hub
        返回 task_id（后续用于追踪和回调）
        """
        # 1. 路由选择 CC
        route_result = self.router.route(task, tag=tag, capability=capability)

        # 2. 创建任务记录
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

        # 3. 订阅回调
        self.event_bus.subscribe(agent_id, task_id)

        # 4. 执行（异步，不阻塞）
        asyncio.create_task(
            self._execute_task(task_id, route_result, timeout)
        )

        return task_id

    async def _execute_task(
        self, task_id: str, route_result: RouteResult, timeout: float
    ):
        """内部执行任务（异步）"""
        task_obj = self._tasks[task_id]
        cc_adapter = self.cc_registry.get_adapter(route_result.cc_id)
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
            self.event_bus.publish(
                task_obj.caller_agent_id,
                task_id,
                {"type": "result", "result": result}
            )
        except Exception as e:
            task_obj.status = "error"
            task_obj.error = str(e)
            self.event_bus.publish(
                task_obj.caller_agent_id,
                task_id,
                {"type": "error", "error": str(e)}
            )

    # ── CC 侧 API ─────────────────────────────────────────────────

    def register_cc(self, cc_adapter: "CCAdapter") -> str:
        """CC 实例注册到 Hub"""
        return self.cc_registry.register(cc_adapter)

    def cc_ready(self, cc_id: str, session_id: str = None) -> None:
        """CC 实例就绪（可用）"""
        self.cc_registry.update_status(cc_id, "idle", session_id)
```

### 3.2 AgentRegistry (`agent_registry.py`)

**职责**：管理所有连接到 Hub 的 Agent。

**数据结构**：
```python
@dataclass
class AgentNode:
    agent_id: str                    # 唯一标识，"hermes_gateway", "openclaw_main", "custom_001"
    adapter: AgentAdapter            # 适配器实现（接口）
    protocol: str                   # "websocket" | "stdio" | "http" | "mcp"
    metadata: dict                  # 任意元数据（名称、版本、能力描述）
    connected_at: str               # ISO timestamp
    last_seen: str                  # ISO timestamp

class AgentRegistry:
    def register(agent_id: str, adapter: AgentAdapter, protocol: str = "mcp", metadata: dict = None) -> AgentNode
    def unregister(agent_id: str) -> None
    def get(agent_id: str) -> Optional[AgentNode]
    def list_all() -> list[AgentNode]
    def update_last_seen(agent_id: str) -> None
```

### 3.3 AgentAdapter 协议 (`agent_adapter.py`)

**这是核心抽象层**。任何 Agent 要接入 Hub，只需实现此接口。

```python
from abc import ABC, abstractmethod
from typing import Protocol, AsyncIterator
from dataclasses import dataclass

@dataclass
class CCResult:
    kind: str          # SUCCESS / ERROR / AUTH_CLI / AUTH_API / TIMEOUT / CRASH
    text: str          # 文本结果
    session_id: str
    cost_usd: float
    duration_ms: int
    error: str

@dataclass
class HubEvent:
    type: str          # "result" | "error" | "partial" | "progress" | "log"
    task_id: str
    data: dict         # 事件载荷

class AgentAdapter(ABC):
    """
    Agent 适配器协议 — 任何 LLM Agent 实现此接口即可接入 UniversalRouterHub

    实现类示例：
    - HermesAgentAdapter（接入 Hermes Gateway）
    - OpenClawAgentAdapter（接入 OpenClaw）
    - WebSocketAgentAdapter（通用 WebSocket 接入）
    - StdioAgentAdapter（stdio 子进程接入）
    """

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """Agent 唯一标识"""
        ...

    @property
    @abstractmethod
    def supported_events(self) -> list[str]:
        """该 Adapter 支持接收的事件类型"""
        ...

    @abstractmethod
    async def connect(self, hub_url: str) -> None:
        """连接到 UniversalRouterHub"""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接"""
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
        提交任务给 Hub
        返回 task_id
        """
        ...

    @abstractmethod
    async def on_hub_event(self, event: HubEvent) -> None:
        """
        Hub 推送事件给 Agent（CC 回调触发此方法）
        Agent 在此处理来自 CC 的消息（进度/通知/结果）
        """
        ...

    @abstractmethod
    async def event_stream(self) -> AsyncIterator[HubEvent]:
        """
        返回事件流迭代器（用于 long-poll / WebSocket）
        Agent 持续从此迭代器读取 Hub 发来的事件
        """
        ...
```

#### 3.3.1 HermesAgentAdapter 实现（示例）

```python
class HermesAgentAdapter(AgentAdapter):
    """
    Hermes Gateway 的适配器实现
    Hermes Gateway 通过此 Adapter 接入 URH
    """

    def __init__(self, agent_id: str = "hermes_gateway"):
        self._agent_id = agent_id
        self._hub: UniversalRouterHub = None
        self._event_queue: asyncio.Queue[HubEvent] = asyncio.Queue()
        self._connected = False

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def supported_events(self) -> list[str]:
        return ["result", "error", "partial", "progress", "log"]

    async def connect(self, hub_url: str = None) -> None:
        self._hub = get_global_hub()
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
        return await self._hub.submit_task(
            self._agent_id, task, tag=tag, capability=capability, timeout=timeout
        )

    async def on_hub_event(self, event: HubEvent) -> None:
        """Hub 推送事件 → Hermes Gateway 处理"""
        await self._event_queue.put(event)

    async def event_stream(self) -> AsyncIterator[HubEvent]:
        while self._connected:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=30.0)
                yield event
            except asyncio.TimeoutError:
                # 心跳，保持连接
                yield HubEvent(type="heartbeat", task_id="", data={})
```

#### 3.3.2 OpenClawAgentAdapter 实现（示例）

```python
class OpenClawAgentAdapter(AgentAdapter):
    """
    OpenClaw 的适配器实现
    通过 OpenClaw 的 plugin 机制接入 URH
    """

    def __init__(self, agent_id: str = "openclaw_main"):
        self._agent_id = agent_id
        self._event_queue: asyncio.Queue[HubEvent] = asyncio.Queue()
        self._hub: UniversalRouterHub = None

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def supported_events(self) -> list[str]:
        return ["result", "error", "partial"]

    async def connect(self, hub_url: str = None) -> None:
        self._hub = get_global_hub()
        self._hub.connect_agent(self._agent_id, self)

    async def disconnect(self) -> None:
        self._hub.disconnect_agent(self._agent_id)

    async def submit_task(self, task: str, tag: str = None, ...) -> str:
        return await self._hub.submit_task(self._agent_id, task, ...)

    async def on_hub_event(self, event: HubEvent) -> None:
        # OpenClaw: 通过 plugin 机制处理事件
        await self._dispatch_to_plugin(event)

    async def event_stream(self) -> AsyncIterator[HubEvent]:
        while True:
            event = await self._event_queue.get()
            yield event
```

### 3.4 CCAdapter (`cc_adapter.py`)

**职责**：每个 CC 实例通过 CCAdapter 接入 Hub。封装了 CCExecutor，提供统一的 Hub 接口。

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class CCInstance:
    cc_id: str              # "cc_001"
    workspace: str          # 工作区绝对路径
    tag: list[str]          # 多个路由标签 ["starfire", "ml"]
    capability: list[str]   # ["code", "research", "paper"]
    status: str             # idle | busy | starting | dead
    session_id: str         # CC session ID
    pid: int                # 进程 PID
    adapter: "CCAdapter"    # 引用回 adapter
    metadata: dict          # 额外元数据

class CCAdapter:
    """
    CC 实例适配器

    每个 CC 实例在 Hub 中对应一个 CCAdapter 实例。
    CCAdapter 内部管理 CCExecutor（subprocess），
    对 Hub 暴露统一的 execute() 接口。
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
        self.cc_cli_path = cc_cli_path or DEFAULT_CC_CLI_PATH
        self._executor = CCExecutor(cc_cli_path=self.cc_cli_path)
        self._current_task: Optional[str] = None
        self._status = "idle"
        self._session_id: str = ""

    @property
    def instance(self) -> CCInstance:
        return CCInstance(
            cc_id=self.cc_id,
            workspace=self.workspace,
            tag=self.tags,
            capability=self.capabilities,
            status=self._status,
            session_id=self._session_id,
            pid=0,  # 运行时填充
            adapter=self,
            metadata={},
        )

    async def execute(
        self,
        task: str,
        caller_agent_id: str,
        event_bus: "EventBus" = None,
        resume: bool = True,
        timeout: float = 300.0,
    ) -> CCResult:
        """
        在此 CC 实例上执行任务
        可选通过 event_bus 实时推送 partial 消息
        """
        self._status = "busy"
        self._current_task = task

        try:
            # 通过 event_bus 实时推送 partial 输出（如果订阅了）
            if event_bus:
                # TODO: 实现 partial 消息转发
                pass

            result = await self._executor.run(
                task=task,
                workspace=self.workspace,
                session_id=self._session_id if resume else None,
                resume=resume,
                timeout=timeout,
            )

            if result.kind == CCResultKind.SUCCESS:
                self._session_id = result.session_id
                self._status = "idle"
            else:
                self._status = "dead" if result.kind in (
                    CCResultKind.AUTH_CLI, CCResultKind.AUTH_API
                ) else "idle"

            return result

        finally:
            self._current_task = None

    async def terminate(self) -> None:
        """强制终止 CC 进程"""
        self._status = "dead"
        # 通知 executor kill 进程

    async def get_status(self) -> dict:
        return {
            "cc_id": self.cc_id,
            "status": self._status,
            "session_id": self._session_id,
            "current_task": self._current_task,
        }
```

### 3.5 CCRegistry (`cc_registry.py`)

**职责**：CC 实例注册表，维护所有 CC 实例及其 CCAdapter 映射。

```python
class CCRegistry:
    """
    CC 实例注册中心
    线程安全（asyncio Lock）
    """

    def __init__(self):
        self._instances: dict[str, CCInstance] = {}
        self._adapters: dict[str, CCAdapter] = {}
        self._lock = asyncio.Lock()

    def register(
        self,
        adapter: CCAdapter,
        workspace: str = None,
        tags: list[str] = None,
        capabilities: list[str] = None,
    ) -> str:
        """注册新 CC 实例，返回 cc_id"""

    def unregister(self, cc_id: str) -> None:
        """注销 CC 实例"""

    def get_by_id(self, cc_id: str) -> Optional[CCInstance]:
        """按 ID 查找"""

    def get_by_tag(self, tag: str) -> Optional[CCInstance]:
        """按 tag 查找（返回第一个 idle）"""

    def list_by_status(self, status: str) -> list[CCInstance]:
        """列出指定状态的实例"""

    def list_all(self) -> list[CCInstance]:
        """列出所有实例"""

    def get_adapter(self, cc_id: str) -> Optional[CCAdapter]:
        """获取实例对应的 adapter"""

    def update_status(self, cc_id: str, status: str, session_id: str = None) -> None:
        """原子更新状态"""
```

### 3.6 UniversalRouter (`universal_router.py`)

**职责**：根据任务内容选择最合适的 CC 实例，与具体 Agent 无关。

```python
from enum import Enum

class RoutingStrategy(Enum):
    TAG_MATCH   = "tag_match"
    PATH_MATCH  = "path_match"
    CAPABILITY  = "capability"
    ROUND_ROBIN = "round_robin"
    DEFAULT     = "default"

@dataclass
class RouteResult:
    cc_id: str
    strategy: RoutingStrategy
    reason: str
    workspace: str

# capability → 关键词映射
CAPABILITY_KEYWORDS = {
    "code":      ["代码", "code", "implement", "bug", "refactor"],
    "research":  ["论文", "research", "survey", "文献", "arxiv"],
    "paper":     ["写论文", "paper", "writing", "introduction", "related work"],
    "ml":        ["训练", "training", "model", "epoch", "loss", "实验"],
    "debug":     ["debug", "错误", "crash", "traceback", " Segmentation"],
    "general":   [],  # 默认
}

class UniversalRouter:
    """
    通用路由 — 不绑定任何 Agent

    策略优先级：
    1. 显式 tag 参数
    2. 消息内 @tag
    3. workspace 路径匹配
    4. capability 关键词匹配
    5. round-robin idle 实例
    6. 第一个 idle 实例（兜底）
    """

    def __init__(self, cc_registry: CCRegistry):
        self.cc_registry = cc_registry
        self._round_robin_index = 0
        self._lock = asyncio.Lock()

        # 正则
        self.TAG_PAT  = re.compile(r"^@(\w+)\s+(.+)$")
        self.PATH_PAT = re.compile(r"([A-Z]:[/\\](?:[^\\/:*?\"<>|\r\n]+[/\\]?)+)")

    async def route(
        self,
        message: str,
        tag: str = None,
        capability: list[str] = None,
    ) -> RouteResult:
        """路由决策（异步，支持将来扩展动态查询）"""

        # 1. 显式 tag
        if tag:
            inst = self.cc_registry.get_by_tag(tag)
            if inst and inst.status in ("idle", "busy"):
                return RouteResult(cc_id=inst.cc_id, strategy=RoutingStrategy.TAG_MATCH,
                                   reason=f"tag={tag}", workspace=inst.workspace)

        # 2. 消息内 @tag
        m = self.TAG_PAT.match(message.strip())
        if m:
            tag_in_msg = m.group(1)
            inst = self.cc_registry.get_by_tag(tag_in_msg)
            if inst:
                return RouteResult(cc_id=inst.cc_id, strategy=RoutingStrategy.TAG_MATCH,
                                   reason=f"@tag={tag_in_msg}", workspace=inst.workspace)

        # 3. workspace 路径匹配
        path_m = self.PATH_PAT.search(message)
        if path_m:
            path = Path(path_m.group(1))
            for inst in self.cc_registry.list_by_status("idle"):
                inst_path = Path(inst.workspace)
                if path in inst_path.parents or inst_path in path.parents:
                    return RouteResult(cc_id=inst.cc_id, strategy=RoutingStrategy.PATH_MATCH,
                                       reason=f"workspace={inst.workspace}", workspace=inst.workspace)

        # 4. capability 关键词
        if capability:
            for cap in capability:
                for inst in self.cc_registry.list_by_status("idle"):
                    if cap in inst.capability:
                        return RouteResult(cc_id=inst.cc_id,
                                           strategy=RoutingStrategy.CAPABILITY,
                                           reason=f"cap={cap}", workspace=inst.workspace)

        # 5. 消息内关键词匹配 capability
        msg_lower = message.lower()
        for cap, keywords in CAPABILITY_KEYWORDS.items():
            if cap == "general":
                continue
            if any(kw in msg_lower for kw in keywords):
                for inst in self.cc_registry.list_by_status("idle"):
                    if cap in inst.capability:
                        return RouteResult(cc_id=inst.cc_id,
                                           strategy=RoutingStrategy.CAPABILITY,
                                           reason=f"keyword→{cap}", workspace=inst.workspace)

        # 6. round-robin idle
        idle = self.cc_registry.list_by_status("idle")
        if idle:
            async with self._lock:
                idx = self._round_robin_index % len(idle)
                self._round_robin_index += 1
                inst = idle[idx]
            return RouteResult(cc_id=inst.cc_id, strategy=RoutingStrategy.ROUND_ROBIN,
                               reason=f"round_robin[{idx}]", workspace=inst.workspace)

        # 7. 兜底：任意 idle
        all_instances = self.cc_registry.list_all()
        idle_or_busy = [i for i in all_instances if i.status in ("idle", "busy")]
        if idle_or_busy:
            return RouteResult(cc_id=idle_or_busy[0].cc_id,
                               strategy=RoutingStrategy.DEFAULT,
                               reason="first_available", workspace=idle_or_busy[0].workspace)

        raise RouterError("No available CC instance")
```

### 3.7 EventBus (`event_bus.py`)

**职责**：双向事件总线。CC 回调给 Agent、Agent 推送控制命令给 CC，均通过 EventBus。

```python
from dataclasses import dataclass
import asyncio

@dataclass
class HubEvent:
    type: str        # "result" | "error" | "partial" | "progress" | "log" | "interrupt"
    task_id: str
    agent_id: str    # 目标 agent
    data: dict       # 事件载荷

class EventBus:
    """
    异步事件总线

    发布订阅模型：
    - Agent 订阅任务结果：subscribe(agent_id, task_id)
    - CC 推送事件：publish(agent_id, task_id, event_data)
    - Agent 通过 event_stream() 接收

    同时支持：
    - Hub → CC 控制命令（interrupt / cancel）
    - CC → Agent 回调（progress / log / result）
    """

    def __init__(self):
        # agent_id → {task_id → asyncio.Queue[HubEvent]}
        self._subscriptions: dict[str, dict[str, asyncio.Queue]] = {}
        # 全局 agent 事件通道（不受 task_id 限制）
        self._global: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    # ── Agent 侧订阅 ────────────────────────────────────────────

    async def subscribe(self, agent_id: str, task_id: str) -> None:
        """Agent 订阅特定任务的结果"""
        async with self._lock:
            if agent_id not in self._subscriptions:
                self._subscriptions[agent_id] = {}
            if task_id not in self._subscriptions[agent_id]:
                self._subscriptions[agent_id][task_id] = asyncio.Queue()
            if agent_id not in self._global:
                self._global[agent_id] = asyncio.Queue()

    async def unsubscribe(self, agent_id: str, task_id: str) -> None:
        async with self._lock:
            if agent_id in self._subscriptions:
                self._subscriptions[agent_id].pop(task_id, None)

    async def event_stream(self, agent_id: str) -> AsyncIterator[HubEvent]:
        """Agent 的事件流（合并 task 事件 + 全局事件）"""
        while True:
            event = None

            # 先检查全局事件（高优先级）
            try:
                event = self._global[agent_id].get_nowait()
            except asyncio.QueueEmpty:
                pass

            # 再检查 task 事件
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
                await asyncio.sleep(0.1)  # 无事件时短暂让出

    # ── CC / Hub 侧发布 ────────────────────────────────────────

    async def publish(self, agent_id: str, task_id: str, event_data: dict) -> None:
        """CC 或 Hub 发布事件给 Agent"""
        event = HubEvent(type=event_data["type"], task_id=task_id,
                         agent_id=agent_id, data=event_data)

        async with self._lock:
            # 发到 task 专属通道
            if agent_id in self._subscriptions:
                q = self._subscriptions[agent_id].get(task_id)
                if q:
                    await q.put(event)

            # 同时发到全局通道
            if agent_id in self._global:
                await self._global[agent_id].put(event)

    # ── 控制命令（Hub → CC）────────────────────────────────────

    async def send_interrupt(self, cc_id: str, task_id: str, reason: str = None) -> None:
        """
        Agent 通过 Hub 发送中断命令给 CC
        CCAdapter 监听此通道并终止进程
        """
        # 通过特殊 task 广播
        for agent_id in self._subscriptions:
            await self._global[agent_id].put(HubEvent(
                type="interrupt", task_id=task_id, agent_id=cc_id,
                data={"reason": reason, "cc_id": cc_id}
            ))
```

### 3.8 RouterMCPServer (`router_mcp_server.py`)

**职责**：Hub 内置的 MCP Server，所有连接的 CC 实例都可以通过 MCP Protocol 调用它的 Tools。

```python
"""
RouterHub 内置 MCP Server

CC 实例通过 stdio 连接到此 MCP Server，调用：
- feishu_notify        → 飞书通知
- read_training_log   → 读取训练日志
- query_shared_data   → 查询共享数据
- forward_to_agent    → 主动向 Agent 发消息

每个 Tool 调用时自动附带你 CallToolContext（包含 task_id, caller_cc_id）
"""

from mcp.server import Server
from mcp.types import Tool, CallToolResult
from mcp.shared.context import CallToolContext
import asyncio

# 全局 task context lookup（CCAdapter.execute 时设置）
_TASK_CONTEXT: dict[str, dict] = {}

def set_task_context(task_id: str, cc_id: str, caller_agent_id: str):
    _TASK_CONTEXT[task_id] = {"cc_id": cc_id, "agent_id": caller_agent_id}

def get_task_context(task_id: str) -> dict:
    return _TASK_CONTEXT.get(task_id, {})

# ── MCP Server ─────────────────────────────────────────────────────────────

router_server = Server("router-hub-services")

@router_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="feishu_notify",
            description="Send notification to Feishu (via Hermes gateway)",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "chat_id": {"type": "string", "description": "optional target chat_id"}
                },
                "required": ["text"]
            }
        ),
        Tool(
            name="forward_to_agent",
            description="Forward a message/event to the caller Agent (via EventBus)",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_type": {"type": "string", "description": "partial|progress|log|error"},
                    "content": {"type": "string"},
                    "task_id": {"type": "string"}
                },
                "required": ["event_type", "content", "task_id"]
            }
        ),
        Tool(
            name="read_training_log",
            description="Read ML training log files",
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": {"type": "string"},
                    "pattern": {"type": "string"}
                }
            }
        ),
        Tool(
            name="query_experiment_data",
            description="Query experiment results from shared data directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "experiment": {"type": "string"},
                    "metric": {"type": "string"}
                }
            }
        ),
    ]

@router_server.call_tool()
async def call_tool(name: str, arguments: dict, context: CallToolContext) -> CallToolResult:
    # context.task_id 标识来自哪个 task，可用于 lookup caller_agent_id
    task_meta = get_task_context(context.task_id or "")

    if name == "feishu_notify":
        text = arguments["text"]
        chat_id = arguments.get("chat_id")
        await feishu_notify_async(text, chat_id=chat_id)
        return CallToolResult(content=[{"type": "text", "text": "OK"}])

    elif name == "forward_to_agent":
        # 通过 EventBus 转发给 Agent
        event_bus = get_global_event_bus()
        await event_bus.publish(
            agent_id=task_meta.get("agent_id", ""),
            task_id=arguments["task_id"],
            event_data={
                "type": arguments["event_type"],
                "content": arguments["content"],
            }
        )
        return CallToolResult(content=[{"type": "text", "text": "forwarded"}])

    elif name == "read_training_log":
        ...

    elif name == "query_experiment_data":
        ...

    raise ValueError(f"Unknown tool: {name}")

def get_global_event_bus() -> EventBus:
    """由 Hub 实例提供"""
    ...

def get_global_hub() -> UniversalRouterHub:
    """由调用方提供"""
    ...
```

**CC 端启动 MCP Client**（在 CCAdapter 中配置）：

```yaml
# CC 的 MCP 配置（~/.claude/mcp.json）
{
  "mcpServers": {
    "router-hub": {
      "command": "node",
      "args": ["/path/to/router_mcp_bridge.js"],
      "env": {
        "ROUTER_HUB_URL": "stdio",
        "CC_ID": "cc_001"
      }
    }
  }
}
```

```javascript
// router_mcp_bridge.js
// CC MCP Client → URH MCP Server 的 stdio 桥接
// 将 MCP JSON-RPC 转为 Hub EventBus 调用
```

---

## 4. CCExecutor（底层 CC CLI 封装）

### 4.1 CC CLI 调用方式（已验证）

```bash
claude --print \
  --input-format=stream-json \
  --output-format=stream-json \
  --include-partial-messages \
  [--resume SESSION_ID]
```

**stdin（NDJSON）**：
```json
{"type": "user", "message": {"role": "user", "content": "任务描述"}}
```

**stdout 事件流（NDJSON）**：
```
{"type": "system", "subtype": "init", "session_id": "s_abc123"}
{"type": "assistant", "message": {"content": ["部分输出"]}}
{"type": "result", "subtype": "success", "result": "最终文本", "total_cost_usd": 0.025, "duration_ms": 5613}
```

### 4.2 关键注意事项

| 发现 | 影响 | 正确做法 |
|------|------|----------|
| `result.result` 是最终文本 | assistant content 数组拼接是错的 | 必须解析 result 事件 |
| `--no-session-persistence` 导致 resume 失败 | bug，session 丢失 | 去掉此参数 |
| stream-json 认证失败时 exit=1 无 stdout | 调试困难 | 先 text mode 验证 token |
| CC CLI 不接受 `--cwd` | 参数错误 | subprocess_exec 的 cwd= 参数代替 |

---

## 5. 多 Agent 多 CC 并行执行

### 5.1 多 Agent 场景

```
Agent A (Hermes) → URH → CCInstance_001 (tag=starfire)
Agent B (OpenClaw) → URH → CCInstance_002 (tag=paper)
Agent C (Custom) → URH → CCInstance_001 (tag=starfire, 复用)
```

Hub 通过 `caller_agent_id` 隔离不同 Agent 的任务上下文，互不干扰。

### 5.2 并行任务分发

```python
async def dispatch_parallel_tasks(
    hub: UniversalRouterHub,
    agent_id: str,
    sub_tasks: list[tuple[str, str]],  # [(tag, task), ...]
) -> dict[str, str]:  # task_id → status
    """
    并行分发多个任务
    agent_id: 发起的 Agent
    sub_tasks: [(tag, task_text), ...]
    """
    task_ids = {}
    for tag, task_text in sub_tasks:
        task_id = await hub.submit_task(
            agent_id=agent_id,
            task=task_text,
            tag=tag,
        )
        task_ids[task_id] = "submitted"

    return task_ids
```

### 5.3 CC 实例池（预热）

```python
class CCPool:
    """
    预启动 N 个 idle CC 实例，冷启动时间在后台隐藏
    """

    def __init__(self, hub: UniversalRouterHub, size: int = 3):
        self.hub = hub
        self.size = size
        self._bootstrap()

    def _bootstrap(self):
        for i in range(self.size):
            adapter = CCAdapter(
                cc_id=f"pool_{i}",
                workspace=f"/tmp/cc_workspace_{i}",
                tags=[f"pool_{i}"],
                capabilities=["general"],
            )
            self.hub.register_cc(adapter)

    async def warm_up(self):
        """后台空跑预热"""
        for inst in self.hub.cc_registry.list_all():
            await inst.adapter.execute(
                task="say ready",
                caller_agent_id="system",
                resume=False,
                timeout=10.0,
            )
```

---

## 6. 文件结构

```
~/.hermes/
├── router_hub.py              # UniversalRouterHub 主入口
├── agent_registry.py          # Agent 注册表
├── cc_registry.py             # CC 实例注册表
├── cc_adapter.py              # CC 适配器
├── cc_executor.py             # CC CLI 底层执行器
├── universal_router.py        # 路由引擎
├── event_bus.py               # 双向事件总线
├── agent_adapter.py           # AgentAdapter 协议定义
│
├── adapters/
│   ├── __init__.py
│   ├── hermes_adapter.py      # HermesGateway 适配器
│   ├── openclaw_adapter.py    # OpenClaw 适配器
│   └── websocket_adapter.py    # 通用 WebSocket 适配器
│
└── mcp/
    ├── router_mcp_server.py   # Hub 内置 MCP Server
    ├── router_mcp_bridge.js   # CC MCP Client stdio 桥接
    └── tools/
        ├── feishu_notify.py
        ├── training_log.py
        └── shared_data.py

~/.hermes/cc_registry.json     # CC 注册表持久化
~/.hermes/agent_registry.json   # Agent 注册表持久化
```

---

## 7. 当前状态与实现路线图

### 7.1 当前状态

| 组件 | 状态 | 说明 |
|------|------|------|
| `CCExecutor` | ⚠️ 部分实现 | bbhermes 废弃后未重新实现 stream-json 封装 |
| `CCRegistry` | ❌ 未实现 | 仅存在于 skills 设计文档 |
| `CCAdapter` | ❌ 未实现 | 新设计 |
| `AgentRegistry` | ❌ 未实现 | 新设计 |
| `AgentAdapter` 协议 | ❌ 未实现 | 新设计 |
| `UniversalRouter` | ❌ 未实现 | 新设计 |
| `EventBus` | ❌ 未实现 | 新设计 |
| `RouterMCPServer` | ❌ 未实现 | 新设计 |
| `HermesAdapter` | ❌ 未实现 | 新设计 |
| `OpenClawAdapter` | ❌ 未实现 | 新设计 |

### 7.2 分阶段实现计划

```
Phase 1: 核心骨架 + 单 CC 直接执行（2-3天）
├── 定义 AgentAdapter 协议（agent_adapter.py）
├── 实现 CCExecutor（最小可用，stream-json）
├── 实现 CCRegistry + CCAdapter（内存版）
├── 实现 UniversalRouter（tag/路径路由）
├── 实现 EventBus（异步队列，订阅/发布）
├── 实现 UniversalRouterHub 主入口
└── 验证: HermesAdapter → Hub → CC 执行 → 返回结果

Phase 2: 多 CC 路由 + 会话管理（2天）
├── 实现 CCSessionManager（session 持久化，resume）
├── 多实例注册与状态管理
├── round-robin 策略实现
├── capability 关键词路由
└── 验证: @tag 路由到正确 CC 实例

Phase 3: OpenClaw 适配器（2天）
├── 实现 OpenClawAgentAdapter
├── OpenClaw plugin 配置
├── 双 Agent（Hermes + OpenClaw）同时接入
└── 验证: OpenClaw 通过 Hub 调用 CC

Phase 4: MCP 双向扩展（3-5天）
├── 实现 RouterMCPServer（feishu_notify 等工具）
├── 实现 router_mcp_bridge.js（CC MCP Client 桥接）
├── CC 可调用 feishu_notify / forward_to_agent
├── EventBus 支持 progress/partial 实时推送
└── 验证: CC 执行中实时回调 Agent

Phase 5: 并行 + 稳定性（持续）
├── CCSessionManager.run_task_parallel
├── /ccparallel 命令
├── 任务队列与优先级
├── CC 进程健康监控 + 自动重启
├── 断点续传（checkpoint）
└── Web UI / 日志 dashboard
```

---

## 8. 性能特性

| 操作 | 耗时 | 说明 |
|------|------|------|
| CC cold start | ~8-12s | CC CLI 启动 + 模型初始化 |
| CC resume | ~2-4s | 跳过初始化，直接推理 |
| Hub 路由决策 | <5ms | 纯内存操作，无 I/O |
| EventBus 投递 | <10ms | asyncio.Queue，本地进程内 |
| MCP Tool 调用 | 取决于工具 | feishu_notify ~500ms |

**扩展瓶颈**：
- CC 每个实例 ~2GB 内存 → 限制最大实例数（N≤5）
- CC cold start → 实例池预热，后台隐藏延迟

---

## 9. 优缺点总结

### 9.1 优点

| 优点 | 说明 |
|------|------|
| **真正的多 Agent↔多 CC 全连接** | 任何 Agent 通过 Adapter 接入，M 个 Agent × N 个 CC 实例 |
| **双向 MCP** | CC 可主动回调 Agent，非纯黑箱 |
| **AgentAdapter 协议** | 接入新 Agent 只需实现 Adapter，无需改动 Hub |
| **EventBus 解耦** | CC 和 Agent 通过异步队列解耦，支持实时推送 |
| **路由策略可插拔** | UniversalRouter 策略模式，可扩展自定义路由算法 |
| **Hub 无状态** | 状态全在 Registry，Hub 本身可重启 |

### 9.2 缺点与缓解

| 缺点 | 缓解方案 |
|------|----------|
| CC cold start 8-12s | 实例池预热 + 后台空跑 |
| CC 每个实例 ~2GB 内存 | 限制 N≤5 实例 |
| Adapter 协议需为每个 Agent 单独实现 | 协议简单（5个方法），实现成本低 |
| MCP 双工通信需 CC 侧配置 mcp.json | 提供自动化配置脚本 |
| 多 CC 并行时飞书通知秩序 | serial 排队通知 |

---

## 10. 附录：验证命令

```bash
# 1. 验证 CC CLI 可执行
claude --version

# 2. 验证 stream-json 协议（先 text mode 验证 token）
printf 'say hi' | claude --print

# 3. 验证 stream-json 协议
printf '{"type":"user","message":{"role":"user","content":"say hi"}}' \
  | claude --print --input-format=stream-json --output-format=stream-json

# 4. 验证 WSLInterop
ls /proc/sys/fs/binfmt_misc/WSLInterop
cmd.exe /c echo hello

# 5. 验证 CC session resumption（无 --no-session-persistence）
# 用有效 session_id 测试 resume
```

## 11. 参考资料

- CC CLI stream-json 协议：`cc-windows-executor-guide` skill
- Plan A 废弃教训：`cc-architecture-migration` skill
- bbhermes 协议文件：`bbhermes-protocol` skill
- Hermes Gateway 架构：`hermes-agent/AGENTS.md`
- MCP 官方文档：https://modelcontextprotocol.io/
