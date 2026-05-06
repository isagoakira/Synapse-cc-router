# Synapse — MCP Hub Server

## 项目信息

| 项目 | 值 |
|------|-----|
| 名称 | Synapse — MCP Hub Server |
| 基础 | Python 3.11+, mcp>=1.0.0, asyncio |
| 并行度 | 2 |
| 最大修正轮次 | 3 |
| 创建时间 | 2026-05-07 |

## 目标

将 Synapse Hub 封装为**标准的 MCP Server**，使得 Claude Desktop 等 MCP 客户端可以通过 `mcpServers` 配置直接调用 Hub 的核心功能。

### 设计

```
Claude Desktop
  │  mcpServers.synapse = { command: "cc-router", args: ["--mcp"] }
  │
  ▼
MCP Hub Server (cc_router/mcp_hub_server.py)
  │  stdio transport
  │  Tools: submit_task / register_cc / list_cc_instances / list_agents / hub_status
  │
  ▼
UniversalRouterHub (existing)
  │  CCAdapter / CCExecutor / EventBus ...
  ▼
Claude Code instances
```

### 暴露的 MCP Tools

| Tool | 描述 | 参数 |
|------|------|------|
| `submit_task` | 提交任务到 Hub | task, tag?, capability?, timeout? |
| `register_cc` | 注册 CC 实例 | cc_id, workspace, tags?, capabilities? |
| `list_cc_instances` | 列出已注册的 CC | status? |
| `list_agents` | 列出已连接的 Agent | — |
| `hub_status` | Hub 运行状态概览 | — |
| `connect_agent` | 连接一个 Agent | agent_id, type? |
| `disconnect_agent` | 断开一个 Agent | agent_id |

---

## 任务组

### G0 — MCP Hub Server 核心实现

**描述**: 创建 MCP Hub Server，将 Hub 功能封装为标准 MCP Tools

**依赖**: 无

**任务清单**:

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 0.1 | 创建 `mcp_hub_server.py` — MCP Server 骨架 (stdio transport) | `cc_router/mcp_hub_server.py` | ✅ |
| 0.2 | 实现 `submit_task` tool | `cc_router/mcp_hub_server.py` | ✅ |
| 0.3 | 实现 `register_cc` / `list_cc_instances` tools | `cc_router/mcp_hub_server.py` | ✅ |
| 0.4 | 实现 `list_agents` / `hub_status` / `connect_agent` / `disconnect_agent` tools | `cc_router/mcp_hub_server.py` | ✅ |
| 0.5 | 添加错误处理、日志、优雅关闭 | `cc_router/mcp_hub_server.py` | ✅ |

**交付物**: 完整的 MCP Hub Server，支持 7 个工具

**状态**: ✅ 已完成 (1 轮)

---

### G1 — CLI 集成

**描述**: 将 MCP Server 集成到 CLI 和配置系统

**依赖**: G0

**任务清单**:

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 1.1 | 添加 `--mcp` CLI flag | `cc_router/__main__.py` | ✅ |
| 1.2 | 添加 MCP server 配置项 | `cc_router/config.py` | ✅ |
| 1.3 | 更新 `cc_router_config.template.json` | `cc_router_config.template.json` | ✅ |
| 1.4 | 导出 MCPHubServer 到 `__init__.py` | `cc_router/__init__.py` | ✅ |

**交付物**: `cc-router --mcp` 一键启动 MCP Server

**状态**: ✅ 已完成 (1 轮)

---

### G2 — 测试

**描述**: 为 MCP Hub Server 添加测试

**依赖**: G0

**任务清单**:

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 2.1 | 测试 MCP Server 初始化 + tool 列表 | `tests/test_mcp_hub.py` | ✅ |
| 2.2 | 测试 `submit_task` tool (mock hub) | `tests/test_mcp_hub.py` | ✅ |
| 2.3 | 测试 `register_cc` / `list_cc` tools | `tests/test_mcp_hub.py` | ✅ |
| 2.4 | 测试 `list_agents` / `hub_status` tools | `tests/test_mcp_hub.py` | ✅ |

**交付物**: 全部测试通过（25+ 项测试），覆盖率符合要求

**状态**: ✅ 已完成 (1 轮)

---

### G3 — 文档

**描述**: 更新 README 和配置文档

**依赖**: G1+G2

**任务清单**:

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| 3.1 | 更新 README — 添加 MCP 集成章节 + CLI 参考 + 项目结构 | `README.md` | ✅ |
| 3.2 | 更新 CHANGELOG — v0.3.0 条目 | `CHANGELOG.md` | ✅ |

**状态**: ✅ 已完成 (1 轮)


## 任务依赖关系

```
G0 ──→ G1 ──→ G3
 │              │
 └──→ G2 ──────┘
```

| Wave | 组 | 说明 | 状态 |
|------|-----|------|------|
| 1 | G0 | MCP Server 核心实现 | ✅ |
| 2 | G1 + G2 | CLI 集成 + 测试 (并行) | ✅ |
| 3 | G3 | 文档更新 | ✅ |

## 执行摘要

| 指标 | 值 |
|------|-----|
| 完成时间 | 2026-05-07 |
| 完成组数 | 4/4 (G0, G1, G2, G3) |
| 总任务数 | 15/15 |
| 新文件 | 2 (`cc_router/mcp_hub_server.py`, `tests/test_mcp_hub.py`) |
| 修改文件 | 6 (`__init__.py`, `config.py`, `__main__.py`, `cc_router_config.template.json`, `README.md`, `CHANGELOG.md`) |
| VCS 快照 | `group-g0-complete`, `group-g1-complete`, `group-g2-complete`, `group-g3-complete` |
