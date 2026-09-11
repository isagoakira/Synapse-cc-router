# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **CC Router** — a Universal Multi-Agent ↔ Multi-CC (Claude Code) Connection Hub that enables NxM connections between any LLM Agent and any Claude Code instance, with bidirectional MCP communication and intelligent task routing.

**Current Status**: v0.4.0 (alpha). Core architecture implemented and tested with health monitoring, parallel task distribution, HTTP REST API, MCP bridge, **config-driven CC instance persistence**, and **per-task workspace overrides**. 30+ source files, 165+ pytest tests.

## Architecture

```
Agent (Hermes/OpenClaw/Custom)
    → AgentAdapter (protocol: submit_task/on_hub_event/event_stream)
    → UniversalRouterHub (routing: tag > @tag > capability > round-robin)
        → CCAdapter (wraps CCExecutor; workspace overridable per task)
        → CCExecutor (spawns claude --print --input-format=stream-json)
    → EventBus (bidirectional async pub/sub, CC can callback to Agent)
```

## Core Components

| Component | File | Purpose |
|-----------|------|---------|
| `UniversalRouterHub` | `router_hub.py` | Main routing hub + health monitor + task queue |
| `AgentRegistry` | `agent_registry.py` | Manages connected agents |
| `CCRegistry` | `cc_registry.py` | Manages CC instances |
| `CCAdapter` | `cc_adapter.py` | Adapter for CC instances + per-task workspace override + health check |
| `CCExecutor` | `cc_executor.py` | Executes CC CLI via stream-json + process alive check |
| `UniversalRouter` | `universal_router.py` | Routes tasks by tag/capability (no workspace path match) |
| `EventBus` | `event_bus.py` | Bidirectional async event bus |
| `AgentAdapter` | `agent_adapter.py` | Protocol for agents to connect |
| `RouterMCPServer` | `router_mcp_server.py` | Built-in MCP server |
| `MCPHubServer` | `mcp_hub_server.py` | FastMCP-based external MCP server |
| `HermesExecutor` | `hermes_executor.py` | Hermes subprocess executor |
| `OpenClawExecutor` | `openclaw_executor.py` | OpenClaw subprocess executor |
| `HTTP Server` | `http_server.py` | aiohttp REST API (7 endpoints) |
| `MCP Bridge` | `cc_router/mcp/router_mcp_bridge.js` | MCP stdio bridge (Node.js) |

## Routing Strategy (v0.4+)

Priority order:
1. Explicit `tag` parameter
2. `@tag` in message (regex: `^@(\w+)\s+(.+)$`)
3. Explicit `capability` parameter list
4. Capability keyword matching
5. Round-robin idle instances
6. First available instance (fallback)

**Workspace is no longer used for routing** — it is a per-task execution parameter supplied at submission time (see `Per-Task Workspace Override` below).

Capability keywords:
- `code`: code, implement, bug, refactor
- `research`: research, survey, paper
- `paper`: writing, introduction, related work
- `ml`: training, model, epoch, loss, experiment
- `debug`: debug, crash, traceback, exception

## Per-Task Workspace Override

CC instances register with a *default* workspace (`cc_instances[].workspace` in config, or the `workspace` field on `/api/cc/register`), but each task submission can override the working directory used for that single execution.

```bash
# Default workspace (the CC instance's registered workspace)
curl -X POST http://localhost:8765/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"task": "@code refactor this"}'

# Override workspace for this single task
curl -X POST http://localhost:8765/api/tasks \
  -H 'Content-Type: application/json' \
  -d '{"task": "@code refactor this", "workspace": "D:\\projects\\foo"}'
```

In Python:

```python
await hub.submit_task(
    agent_id="bbbot",
    task="@code refactor this",
    workspace="D:\\projects\\foo",   # optional; falls back to CC default
)
```

## CC Instance Persistence (config-driven)

v0.4.0: pre-configured CC instances in the JSON config are **auto-registered at Hub startup** (no more re-registering via HTTP after each restart). Add a top-level `cc_instances` array to your config:

```json
{
  "hub_host": "127.0.0.1",
  "hub_port": 8765,
  "cc_cli_path": "claude",
  "cc_instances": [
    {
      "cc_id": "cc_code",
      "workspace": "D:\\projects\\code",
      "tags": ["code"],
      "capabilities": ["code", "debug"]
    },
    {
      "cc_id": "cc_ml",
      "workspace": "D:\\projects\\ml",
      "tags": ["ml"],
      "capabilities": ["ml", "training"]
    }
  ]
}
```

Launch:

```bash
cc-router --config /path/to/router_config.json
```

The Hub will log each instance it auto-registers at INFO level:

```
INFO  Auto-registered CC: cc_code (workspace=D:\projects\code, caps=['code', 'debug'])
INFO  Auto-registered CC: cc_ml (workspace=D:\projects\ml, caps=['ml', 'training'])
```

Note: `config.py` reads JSON with `utf-8-sig` to tolerate UTF-8 BOM (PowerShell `Set-Content -Encoding UTF8` writes BOM by default).
