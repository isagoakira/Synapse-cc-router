# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **CC Router** — a Universal Multi-Agent ↔ Multi-CC (Claude Code) Connection Hub that enables NxM connections between any LLM Agent and any Claude Code instance, with bidirectional MCP communication and intelligent task routing.

**Current Status**: v0.2.0 (alpha). The core architecture is implemented and tested. 27+ source files, 5+ test files with 44+ pytest tests. Ready for public release preparations.

## Architecture

```
Agent (Hermes/OpenClaw/Custom)
    → AgentAdapter (protocol: submit_task/on_hub_event/event_stream)
    → UniversalRouterHub (routing: tag > @tag > workspace > capability > round-robin)
        → CCAdapter (wraps CCExecutor)
        → CCExecutor (spawns claude --print --input-format=stream-json)
    → EventBus (bidirectional async pub/sub, CC can callback to Agent)
```

## Core Components

| Component | File | Purpose |
|-----------|------|---------|
| `UniversalRouterHub` | `cc_router/router_hub.py` | Main routing hub |
| `AgentRegistry` | `cc_router/agent_registry.py` | Manages connected agents |
| `CCRegistry` | `cc_router/cc_registry.py` | Manages CC instances |
| `CCAdapter` | `cc_router/cc_adapter.py` | Adapter for CC instances |
| `CCExecutor` | `cc_router/cc_executor.py` | Executes CC CLI via stream-json |
| `UniversalRouter` | `cc_router/universal_router.py` | Routes tasks by tag/path/capability |
| `EventBus` | `cc_router/event_bus.py` | Bidirectional async event bus |
| `AgentAdapter` | `cc_router/agent_adapter.py` | Protocol for agents to connect |
| `RouterMCPServer` | `cc_router/router_mcp_server.py` | Built-in MCP server |
| `HermesExecutor` | `cc_router/hermes_executor.py` | Hermes subprocess executor |
| `OpenClawExecutor` | `cc_router/openclaw_executor.py` | OpenClaw subprocess executor |
| `MCP Bridge` | `cc_router/mcp/router_mcp_bridge.js` | MCP stdio bridge (Node.js) |

## Routing Strategy

Priority order:
1. Explicit `tag` parameter
2. `@tag` in message (regex: `^@(\w+)\s+(.+)$`)
3. Workspace path matching
4. Capability keyword matching
5. Round-robin idle instances
6. First available instance

Capability keywords:
- `code`: code, implement, bug, refactor
- `research`: research, survey, paper
- `paper`: writing, introduction, related work
- `ml`: training, model, epoch, loss, experiment
- `debug`: debug, crash, traceback, exception

## CC CLI Usage

```bash
claude --print \
  --input-format=stream-json \
  --output-format=stream-json \
  --include-partial-messages \
  [--resume SESSION_ID]
```

**Critical notes**:
- Do NOT use `--no-session-persistence` (breaks resume)
- Parse `result.result` from result events, not assistant content
- CC CLI does not accept `--cwd` — use subprocess `cwd=` parameter
- stream-json auth failures exit with code 1 and no stdout

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v --cov=cc_router

# Lint and format
ruff check .
black --check .
mypy cc_router/

# Pre-commit hooks
pre-commit install
```

## Key Design Decisions

- Hub is **stateless** — all state in AgentRegistry/CCRegistry/EventBus
- **AgentAdapter protocol** — any agent implements 5 methods to connect
- CC instances are **workspace-tagged** for routing
- **EventBus** uses asyncio.Queue for async pub/sub
- CC cold start ~8-12s, resume ~2-4s
- Memory per CC instance ~2GB (limit N≤5)

## Documentation

- `docs/api.md` — API reference
- `docs/architecture.md` — Architecture overview
- `docs/installation.md` — Installation guide
- `docs/examples/` — Usage examples
