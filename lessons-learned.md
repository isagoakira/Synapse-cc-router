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
