# CC Router — 技术规范

## 项目概述

CC Router is a **Universal Multi-Agent ↔ Multi-CC (Claude Code) Connection Hub** that enables N×M connections between any LLM Agent and any Claude Code instance, with bidirectional MCP communication and intelligent task routing.

## 技术栈

| 层 | 技术 |
|----|------|
| 语言 | Python ≥ 3.11 |
| 异步 | asyncio (原生协程) |
| 通信 | MCP (Model Context Protocol) |
| 子进程 | asyncio.subprocess (CC CLI) |
| 序列化 | stream-json (CC 通信) |
| CLI | argparse (内置) |
| 打包 | setuptools + pyproject.toml |
| 测试 | pytest + pytest-asyncio |
| 代码规范 | black + ruff + mypy |
| CI | GitHub Actions |
| 容器 | Docker (多阶段构建) |

## 架构

```
Agent (Hermes/OpenClaw/Custom)
  → AgentAdapter (协议: submit_task/on_hub_event/event_stream)
  → UniversalRouterHub (路由: tag > @tag > workspace > capability > round-robin)
    → CCAdapter (封装 CCExecutor)
      → CCExecutor (spawn claude --print --input-format=stream-json)
    → EventBus (双向异步 pub/sub, CC 可回调 Agent)
```

## 关键约束

- 最大并行 CC 实例数: 5
- CC 冷启动: 8-12s, 恢复: 2-4s
- 每个 CC 实例内存: ~2GB
- 通信格式: JSON stream
- 支持代理: Hermes, OpenClaw, Custom (AgentAdapter 协议)

## 开发环境

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
python -m pytest tests/ -v

# 代码检查
ruff check .
black --check .
mypy cc_router/
```

## 发布标准

| 检查项 | 标准 |
|--------|------|
| 功能完整性 | 全部核心组件实现并测试 |
| API 稳定性 | 公共 API 冻结 |
| 测试覆盖 | ≥ 80% |
| 文档完备 | README/CHANGELOG/CONTRIBUTING/API |
| CI 通过 | 全平台全版本 |
| 安全审计 | 无漏洞、无密钥泄露 |
| 版本号 | 遵循语义化版本 |
