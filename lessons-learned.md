# 经验库

## 2026-05-07 — Phase 6: 公开发布完善完成

### 架构/设计经验

- 项目原有 27 个源文件, 2927 行 Python 代码, 14 个核心组件 — 这是一个成熟的 Alpha 项目
- 所有核心组件已实现 (Phases 1-3 完成), 但 Phase 4 (MCP bridge JS) 缺失 — 已补全
- 项目有完善的测试框架 (92 项手动测试) 但缺乏真正的 pytest 风格自动化测试 — 已补全

### 代码规范经验

- `ruff` 和 `mypy` 应在 CI 中作为独立 gate 使用
- `pre-commit hooks` 应包含 ruff check + black + mypy
- 避免在 Python 文件中使用绝对路径作为默认值 (如 `/Users/xxx/.local/bin/hermes`) — 应用 `shutil.which()`
- 在 `pyproject.toml` 中配置好工具参数, 使 `ruff`/`black`/`mypy` 开箱即用

### 测试经验

- 原有测试使用自定义 `main()` runner, 不是标准的 pytest 风格 — 应统一使用 pytest
- 使用 `pytest-asyncio` + `asyncio_mode = "auto"` 可以简化异步测试
- 对于需要外部 CLI 的测试 (claude, hermes), 应通过环境变量 `RUN_REAL_CC` 控制
- `conftest.py` 提供共享 fixtures 显著减少测试代码重复

### 文档经验

- README 需要包含硬件要求表格 (CC 实例内存/CPU/冷启动时间)
- API 参考文档 (`docs/api.md`) 让贡献者快速了解现有接口
- 架构文档 (`docs/architecture.md`) 帮助理解组件间交互流程
- CHANGELOG 应遵循 Keep a Changelog + SemVer 规范
- CLAUDE.md 必须反映项目最新状态, 不能标为 "design only"

### CI/CD 经验

- CI 流水线应分为独立 job: lint / test(matrix) / docker / publish
- 覆盖率报告应作为 CI artifact 保存
- Release workflow 应独立于日常 CI
- Docker 构建应采用多阶段构建以减少镜像体积和提高安全性
- Docker 容器应以非 root 用户运行

### 基础设施经验

- 社区文件 (CONTRIBUTING, issue/pr 模板) 是开源项目的必选项
- 配置模板文件 (.template.json) 应在 .gitignore 中使用 `!` 规则显式保留
- `.gitignore` 应分离项目特定配置和通用规则
- 版本号应同时在 `__init__.py` 和 `pyproject.toml` 中更新

### 本次完成统计

| 维度 | 数值 |
|------|------|
| 任务组 | 6 组 (G0-G5) |
| 总任务数 | 44 项 |
| 新文件 | 15 个 |
| 修改文件 | 18 个 |
| 版本变更 | 0.1.0 → 0.2.0 |

---

## 2026-05-07 — Phase 7: MCP Hub Server 集成 (Synapse)

### 架构/设计经验

- 将现有 Hub 封装为 MCP Server 是一种"适配器模式"的应用 — 不修改核心代码, 仅通过 MCP 协议暴露接口
- `MCPAgentBridge` (继承 `AgentAdapterImpl`) 作为 MCP 客户端的虚拟 Agent 代表, 实现了双向通信的最小实现
- 7 个 MCP Tool 覆盖了 Hub 核心功能: 任务提交、CC 注册与查询、Agent 连接管理、状态概览

### MCP 开发经验

- `mcp` Python SDK 的 `@app.list_tools()` 和 `@app.call_tool()` 装饰器是注册 handler 的标准方式
- `Server.run(read, write)` 使用 `stdio_server()` 作为上下文管理器提供流
- Tool 的 `inputSchema` 使用 JSON Schema 格式定义参数, 每个 tool 需指定 `required`
- `TextContent` 是 MCP 返回内容的包装器, 需要使用 `type="text"`
- 使用 `json.dumps()` 序列化返回数据, 确保 JSON 合规

### 测试经验

- 使用 `MockHub` 模拟 `UniversalRouterHub` 进行单元测试, 避免依赖真实 Hub 和 CC CLI
- 测试 tool handler 直接调用 `_submit_task()`, `_register_cc()` 等方法, 绕过 MCP transport 层
- 测试 schema 验证 (属性类型、required 字段) 确保 MCP 接口定义正确
- `unittest.mock.AsyncMock` 用于模拟异步方法如 `hub.submit_task()`
- MCP Server 使用 lazy-init 模式初始化 Hub, 测试时通过 `server._hub = mock_hub` 注入 mock

### CLI 集成经验

- `--mcp` flag 在 `parse_args` 阶段解析, 在 `async_main` 中优先派发, 避免 TCP Hub 初始化
- `import` 延迟到 `async_main` 内部: `from .mcp_hub_server import run_server` 避免循环导入
- MCP 模式不需要 `get_global_hub()` 提前初始化 — MCPHubServer 内部懒加载 Hub

### 文档经验

- 文档应包含 Claude Desktop 具体的配置示例 (`claude_desktop_config.json`)
- CHANGELOG 中的版本号应反映新增功能的重要性 (0.2.0 → 0.3.0, minor bump)
- README 中 MCP Integration 章节应紧挨 MCP Tools 章节, 形成完整的 MCP 生态介绍

### 本次完成统计

| 维度 | 数值 |
|------|------|
| 任务组 | 4 组 (G0-G3) |
| 总任务数 | 15 项 |
| 新文件 | 2 个 (`mcp_hub_server.py`, `test_mcp_hub.py`) |
| 修改文件 | 6 个 |
| 版本变更 | 0.2.0 → 0.3.0 |

---

## 2026-05-07 — Phase 8: FastMCP 标准化完成

### FastMCP 迁移经验

1. **FastMCP 的 `@mcp.tool()` 装饰器是模块级的** — 工具函数是模块函数，不是类方法。不再需要 `_setup_handlers()` 和 `_handle_call()` 手动 dispatch。

2. **Pydantic 模型参数** — FastMCP 自动检测类型注解。使用 `class Model(BaseModel)` 作为工具参数，FastMCP 自动从模型生成 `inputSchema`（藏在 `$defs` 中），工具自动获得 Pydantic 校验。

3. **Context 注入** — 在工具函数参数中声明 `ctx: Context`，FastMCP 自动注入 Context 对象。该参数不会暴露在工具的 JSON Schema 中。

4. **Lifespan 模式** — 使用 `FastMCP(name, lifespan=func)` 替代懒加载 Hub。lifespan 函数是 async generator，`yield` 的值通过 `ctx.request_context.lifespan_context` 传递给工具。

5. **isError 处理** — 工具函数抛出异常，FastMCP 框架自动设置 `isError=True`。因此业务逻辑错误（如空 task）应 raise 异常，而不是返回 error JSON。

6. **Context.info() 是 async** — FastMCP 的 `ctx.info()` 等日志方法是异步的（返回 coroutine），需要 `await ctx.info(...)`。`%` 格式化不支持，必须用 f-string。

7. **ToolAnnotations** — 从 `mcp.server.fastmcp.server` 导入 `ToolAnnotations`，提供 `readOnlyHint/destructiveHint/idempotentHint/openWorldHint` 属性。

8. **向后兼容** — 保留 `MCPHubServer` 包装类，调用 `mcp.run_stdio_async()`。`__main__.py` 的 `from .mcp_hub_server import run_server` 无需修改。

### FastMCP 限制

- `list_tools()` 返回的 `inputSchema` 中，Pydantic 模型被放在 `$defs` 中，顶层只有一个 `input` 引用。测试 schema 时需要查 `$defs` 而非顶层 `properties`。
- `mcp.run()` 是同步方法（内部 anyio.run），而 `mcp.run_stdio_async()` 是异步方法。`MCPHubServer.run()` 应使用 `run_stdio_async()`。

### FastMCP 安装

FastMCP 是 `mcp>=1.0.0` 包的一部分（从 v1.2+ 开始），无需额外依赖。导入路径: `from mcp.server.fastmcp import FastMCP`。

### 本次完成统计

| 维度 | 数值 |
|------|------|
| 任务组 | 5 组 (G0-G4) |
| 总任务数 | 25 项 |
| 新测试 | 32 个 (重写 test_mcp_hub.py) |
| 修改文件 | 9 个 |
| 版本变更 | 0.2.0 → 0.3.0 |

---

## 2026-05-07 — Phase 9: RouterMCPBridge 重构

### 架构/设计经验

1. **RouterMCPBridge 不是 MCP Server，而是 Tool Bridge** — 它是 CC 实例 ↔ Hub 之间的内部工具执行引擎，不是独立 MCP Server。MCP transport 层由 JS bridge (`router_mcp_bridge.js`) 处理。

2. **Pydantic 模型用于内部桥接** — 在 `RouterMCPBridge` 中使用 `BaseModel` 做输入校验，即使不暴露 JSON Schema。Pydantic 的 `**args` 解包提供了一个验证边界，确保数据完整性。

3. **实例级状态优于模块级全局变量** — 将 `_TASK_CONTEXT` 从模块级 dict 迁移到 `RouterMCPBridge._task_context` 实例 dict，消除了全局可变状态的隐患。测试时每个 test 创建独立 bridge，避免测试间污染。

4. **`src/` vs `subpackage/` 模块组织** — `router_mcp_server.py` 位于 `cc_router/` 根目录，`mcp/__init__.py` 用绝对导入 `from cc_router.router_mcp_server` 引用。相对导入 `from .router_mcp_server` 会查找 `cc_router/mcp/router_mcp_server.py`，导致 `ModuleNotFoundError`。

### 代码规范经验

- 使用 `from __future__ import annotations` 启用 PEP 604 联合类型语法（`str | None` 而非 `Optional[str]`）
- Pydantic v2 的 `Field(..., description=...)` 提供字段级文档，优于注释
- 文件读取应设置大小限制（50 KB/文件）和数量限制（20 文件/调用），防止 OOM
- 异常处理：`_read_training_log` 中对单个文件读取失败使用 `try/except (IOError, OSError)`，不会因单个文件导致整体失败

### 测试迁移经验

- 模块级函数 → 实例方法的迁移需要同步更新 3 个层面的引用：定义文件、`__init__.py` 导出、测试文件
- `test_local_e2e.py` 使用自定义 `check()` runner（非 pytest）— 只需更新 import 和调用方式，不影响测试逻辑

### 本次完成统计

| 维度 | 数值 |
|------|------|
| 任务组 | 1 组 |
| 核心变更文件 | 2 个 (`router_mcp_server.py`, `mcp/__init__.py`) |
| 修改测试文件 | 2 个 (`test_core.py`, `test_local_e2e.py`) |
| 测试验证 | 100/100 passed (68 core + 32 MCP) |
| Pydantic 模型新增 | 4 个 (FeishuNotifyInput, ForwardToAgentInput, ReadTrainingLogInput, QueryExperimentDataInput) |

---

## 2026-05-07 — Phase 10: MCP 评估问题修复

### 架构/设计经验

1. **Pydantic `Field(min_length=1)` 是必须显式声明的** — 不像数据库 `NOT NULL`，Pydantic v2 的 `Field(...)` 只要求字段存在，不会拒绝空字符串。用 `min_length=1` 对字符串施加非空约束。

2. **TypedDict 优于 `dict` 做返回类型** — 对序列化函数使用 `TypedDict` 替代裸 `dict`，让调用方能精确知道返回结构。同时保留 duck-typing 的灵活性（输入仍可用 `Any`）。

3. **构造参数优于外部属性写入** — `bridge._hub = hub` 破坏封装。改为 `MCPAgentBridge(agent_id, hub=hub)` 构造注入，对调用方透明、对静态类型可追踪。

4. **`from . import __version__` 是 Python 包内共享版本号的正确模式** — 避免在多个文件中硬编码版本字符串。所有模块统一从 `__init__.py` 导入 `__version__`。

### 代码质量经验

- `_tools` dict 类型 `dict[str, Any]` → `dict[str, Callable[[dict[str, Any], dict[str, str]], Awaitable[dict[str, Any]]]]` — 精确的类型注解能让工具函数接口自文档化
- Pydantic `ValidationError` 在 v2 中继承自 `ValueError`，所以 `pytest.raises(ValueError)` 可以捕获 Pydantic 校验错误

### 本次完成统计

| 维度 | 数值 |
|------|------|
| 修复项目 | 6 项 (P1×2, P2×2, P3×2) |
| 修改文件 | 4 个 (mcp_hub_server, router_mcp_server, __init__, test_core) |
| 新增测试 | 15 个 (Pydantic 模型 9 + 边缘 case 5 + 隔离测试 1) |
| 测试验证 | 115/115 (83 core + 32 MCP) |

---

## 2026-05-07 — Phase 11: BCD — HTTP Server + JS Bridge + 健康监控与并行分发

### HTTP Server 设计经验

1. **aiohttp RouteTableDef 装饰器是声明式 API 的利器** — `@routes.get("/api/health")` 模式使端点路由一目了然，优于 Flask 的集中式路由注册。

2. **`create_app()` 工厂函数分离了定义与启动** — `create_app()` 返回 `web.Application`，便于测试（`aiohttp_client`）和生产启动（`run_http_server`）复用。

3. **`_ok()`/`_err()` 帮助函数统一响应格式** — 所有端点返回 `{"status": "ok"}` 或 `{"status": "error", "message": "..."}`。这个模式在 SDK 中应该标准化导出。

4. **aiohttp 最小开发依赖** — 需要 `pytest-aiohttp` 提供 `aiohttp_client` fixture。`aiohttp>=3.9` 是唯一运行时依赖（已集成在项目依赖中）。

### JS Bridge 设计经验

1. **Node.js http.request 回调风格** — Node.js 的 `http.request()` 使用回调模式（`res.on("data")`, `res.on("end")`），但 MCP bridge 在 async 上下文中需要用 `new Promise()` 包装。超时通过 `req.setTimeout()` 实现。

2. **无依赖 stdio bridge** — JS bridge 纯使用 Node.js 内置模块 `readline` + `http`，零 npm 依赖。适合直接 `node` 运行。

3. **JSON-RPC 2.0 over stdio** — MCP 协议基于 JSON-RPC 2.0，使用 stdin/stdout 传输。`readline` 模块天然适配行分隔的 JSON 流。

4. **HTTP 回退模式** — JS bridge 的 `handleToolCall()` 先尝试 Hub HTTP 委托，失败时回退本地 handler。这种"连接 Hub → 本地兜底"的策略提高了可用性。

### 健康监控经验

1. **后台循环 vs 定时任务** — `asyncio.create_task()` + `while running: await sleep(interval)` 模式比 crontab 或外部调度更可控、可测试。通过 `_health_running` 标志控制生命周期。

2. **连续失败计数器模式** — 使用 `_consecutive_failures[cc_id]` 跟踪每个实例的健康状况，达到阈值后才标记 dead。避免瞬态错误（如网络抖动）导致误杀。

3. **健康检查与容量管理分离** — 健康检查负责检测/标记实例状态，容量管理负责任务分发。两者通过 `CCRegistry` 的实例状态字段耦合，没有直接依赖。

4. **get_health_summary() 是监控仪表盘** — 将分散的 Hub 状态（实例、任务、容量、监控）聚合为一个 dict，为 HTTP `/api/health` 和 MCP `hub_status` 提供统一数据源。

### 并行任务队列经验

1. **asyncio.Queue 是 Go channel 在 Python 中的对应** — 任务排队使用 `asyncio.Queue`，队列处理器作为独立 background task 运行。容量控制通过 `_capacity_lock` + `_active_task_count` 实现。

2. **submit_task 的三路径策略**:
   - 路径 1（正常）：有容量 → 立即 `create_task(_execute_task(...))`
   - 路径 2（已满）：超容量 → 入队 `_task_queue.put(...)`，状态设为 `queued`
   - 路径 3（出队）：队列处理器在容量释放时取出任务，转入路径 1

3. **`_decrement_active()` 确保无论成功/失败都释放槽位** — 在 `_execute_task` 的 `finally` 块中调用，保证异常不会导致容量泄漏。

4. **队列处理器不能死等** — `_process_queue` 从队列取出任务后仍需检查容量（`if self._active_task_count >= self._max_concurrent`），容量不足时重新入队。这是避免 race condition 的关键。

### 测试经验

1. **async 测试需要 @pytest.mark.asyncio** — 使用 `asyncio.create_task()` 的测试必须是 async 函数。同步函数中调用 `create_task()` 会引发 `RuntimeError: no running event loop`。

2. **Mock 数据需要完整的结构** — 当 `http_server` 的 health endpoint 调用 `hub.get_health_summary()` 时，mock 必须返回包含 `cc_instances`/`capacity`/`monitoring` 的完整 dict。

### 本次完成统计

| 维度 | 数值 |
|------|------|
| 任务 | B (JS bridge), C (健康监控+并行), D (HTTP Server) |
| 修改/新建文件 | 9 个 |
| 新增测试 | 17 个 (core 15 + http 2) |
| 累计测试 | 111/111 passed (98 core + 13 http) |
| 新增配置项 | 3 个 (health_check_interval, max_consecutive_failures, max_concurrent) |
