# MCP Server Standardization

## 项目信息

| 项目 | 值 |
|------|-----|
| 名称 | CC Router — MCP Server 标准化 |
| 基础 | Python 3.11+, FastMCP, Pydantic v2 |
| 并行度 | 1 (顺序执行) |
| 最大修正轮次 | 3 |
| 创建时间 | 2026-05-07 |

## 目标

将现有的 `mcp_hub_server.py`（基于低阶 `mcp.server.Server`）升级为**标准 MCP Server**（基于 FastMCP），遵循 MCP Builder 最佳实践。

### 核心改进

| 维度 | 当前 | 目标 |
|------|------|------|
| 框架 | 低阶 Server + 手动 dispatch | **FastMCP** + `@mcp.tool()` 装饰器 |
| Tool 命名 | `submit_task` | `synapse_submit_task`（服务前缀） |
| 输入校验 | 手动 `args.get()` | **Pydantic v2** 模型 + `Field()` 约束 |
| Annotations | 无 | `readOnlyHint/destructiveHint/idempotentHint/openWorldHint` |
| 错误处理 | JSON `{"status":"error"}` | MCP `isError` 标记 + 可操作消息 |
| Docstrings | 简短 | 完整 docstring：参数/返回值/示例 |
| Server 名 | `synapse-hub` | `synapse_mcp` |

---

## 任务组

### G0 — 基础设施 & 计划

**依赖**: 无

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 0.1 | 更新 .claude/settings.local.json → bypass mode | `.claude/settings.local.json` | ✅ |
| 0.2 | 编写 dev-plan.md | `dev-plan.md` | ✅ |
| 0.3 | 设置 harness-state.json 持续运行 | `.claude/harness-state.json` | ✅ |
| 0.4 | 创建 continue.flag | `.claude/continue.flag` | ✅ |

**状态**: ✅ 已完成

---

### G1 — FastMCP 核心实现

**依赖**: G0

**关键文件**: `cc_router/mcp_hub_server.py`

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 1.1 | 迁移至 FastMCP 框架：`FastMCP("synapse_mcp")` + `@mcp.tool()` | `cc_router/mcp_hub_server.py` | ✅ |
| 1.2 | 定义 Pydantic 输入模型：SubmitTaskInput, RegisterCCInput, ListCCInput, ConnectAgentInput, DisconnectAgentInput | `cc_router/mcp_hub_server.py` | ✅ |
| 1.3 | 实现所有 7 个 tool，加完整 annotations + docstrings | `cc_router/mcp_hub_server.py` | ✅ |
| 1.4 | 错误处理：统一 `isError` 响应（异常方式） | `cc_router/mcp_hub_server.py` | ✅ |
| 1.5 | 实现 lifespan 管理：Hub 初始化/清理 | `cc_router/mcp_hub_server.py` | ✅ |
| 1.6 | 实现 context 注入：logging/info | `cc_router/mcp_hub_server.py` | ✅ |
| 1.7 | 确保 `--mcp` CLI flag 兼容 | `cc_router/__main__.py` | ✅ |
| 1.8 | 更新 `__init__.py` 导出 | `cc_router/__init__.py` | ✅ |

**验证**: `python -c "from cc_router.mcp_hub_server import MCPHubServer; print('OK')"` + `cc-router --mcp` 可启动

---

### G2 — 测试更新

**依赖**: G1

**关键文件**: `tests/test_mcp_hub.py`

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 2.1 | 重构测试：适配 FastMCP API + Pydantic 输入 | `tests/test_mcp_hub.py` | ✅ |
| 2.2 | 更新 Pydantic模型测试 | `tests/test_mcp_hub.py` | ✅ |
| 2.3 | 更新 ToolDefinitions/Serialization 测试 | `tests/test_mcp_hub.py` | ✅ |
| 2.4 | 更新 ToolFunctions/ErrorHandling 测试 | `tests/test_mcp_hub.py` | ✅ |
| 2.5 | 32 个 MCP 测试全部通过 | `tests/test_mcp_hub.py` | ✅ |

**验证**: `python -m pytest tests/test_mcp_hub.py -v` 全部通过

---

### G3 — 更新引用方

**依赖**: G1+G2

**关键文件**: 引用 mcp_hub_server 的文件

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 3.1 | 验证 `__main__.py` MCP 模式（`run_server` 向后兼容） | `cc_router/__main__.py` | ✅ |
| 3.2 | 更新 `__init__.py` 导出（添加 mcp 实例 + Pydantic 模型） | `cc_router/__init__.py` | ✅ |
| 3.3 | 更新 docs/README/CHANGELOG/CLAUDE.md | `README.md`, `CHANGELOG.md`, `CLAUDE.md` | ✅ |

**验证**: `python -m pytest tests/ -v --ignore=tests/test_local_e2e.py` 通过

---

### G4 — 最终验证

**依赖**: G3

| # | 任务 | 验证方式 | 状态 |
|---|------|----------|------|
| 4.1 | 导入验证 | `python -c "from cc_router import MCPHubServer; print('OK')"` | ✅ |
| 4.2 | MCP 模式启动 | `cc-router --mcp` 无报错启动（import 验证通过） | ✅ |
| 4.3 | 全部 100 个核心+MCP 测试 | `python -m pytest tests/test_core.py tests/test_mcp_hub.py -v` | ✅ |
| 4.4 | Lint + type check | `ruff check . && mypy cc_router/mcp_hub_server.py` | ✅ |
| 4.5 | VCS 快照 | `harness-vcs.sh snapshot` | ⏳ |

---

## 任务依赖关系

```
G0 ──→ G1 ──→ G2 ──→ G3 ──→ G4
```

## 验证清单

- [x] bypass permission 模式已启用
- [x] FastMCP 迁移完成（FastMCP("synapse_mcp") + @mcp.tool()）
- [x] 全部 7 个工具带 Pydantic 校验 + annotations + docstrings
- [x] 全部 32 个 MCP 测试通过（Pydantic/Schema/ToolFunctions/ErrorHandling/BackwardCompat）
- [x] 核心测试全部通过 (68 tests)
- [x] ruff + mypy (mcp_hub_server.py) 无错误
