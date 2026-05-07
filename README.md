# CC Router

**Universal Multi-Agent ↔ Multi-CC (Claude Code) Connection Hub.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

CC Router enables **N×M** connections between any number of LLM Agents (Hermes, OpenClaw, custom) and any number of Claude Code (CC) instances, with bidirectional MCP communication and intelligent task routing.

```text
  ┌──────┐  ┌──────────┐  ┌──────┐
  │Hermes│  │ OpenClaw │  │Custom│
  └──┬───┘  └────┬─────┘  └──┬───┘
     │           │           │
     └───────────┬───────────┘
                 │
        ┌────────▼────────┐
        │UniversalRouterHub│
        │  ┌────────────┐ │
        │  │   Router   │ │
        │  │  Registry  │ │
        │  │  EventBus  │ │
        │  │  HTTP API  │ │
        │  │  MCP Svr   │ │
        │  └────────────┘ │
        └────────┬────────┘
                 │
     ┌───────────┼───────────┐
     │           │           │
  ┌──▼───┐  ┌───▼───┐  ┌───▼───┐
  │CC #1 │  │ CC #2 │  │ CC #N │
  │(code)│  │ (ml)  │  │(paper)│
  └──────┘  └───────┘  └───────┘
```

---

## Features

- **Universal** — Any LLM Agent implementing the lightweight `AgentAdapter` protocol can connect
- **Bidirectional** — CC instances can callback to Agents in real-time via EventBus pub/sub
- **Intelligent Routing** — Tag-based, path-based, capability-keyword, and round-robin task distribution
- **On-Demand CC** — Claude Code instances spawn on demand (8-12s cold start); no pre-warming required
- **MCP Protocol** — Built-in MCP server enables CC instances to call tools during execution
- **Multi-Agent** — Hermes, OpenClaw, and custom agents coexist and share the same CC pool
- **Session Management** — Automatic session persistence and resumption (2-4s resume)
- **Parallel Dispatch** — Concurrent task execution with health monitoring and automatic dead instance detection
- **HTTP REST API** — Programmatic access to Hub operations via aiohttp (7 endpoints)
- **Health Monitoring** — Background health checks with configurable intervals and failure thresholds

---

## Quick Start

### Installation

```bash
# From source (latest)
git clone https://github.com/isagoakira/Synapse-cc-router
cd cc-router
pip install -e ".[dev]"
```

### Start the Hub

```bash
# Default port 8765
cc-router

# With options
ccr --host 0.0.0.0 --port 8765 --log-level DEBUG

# With custom config
ccr --config /path/to/config.json
```

### Use from Python

```python
import asyncio
from cc_router import UniversalRouterHub, CCAdapter

async def main():
    hub = UniversalRouterHub()

    # Register a code-focused CC instance
    hub.register_cc(CCAdapter(
        cc_id="cc_code",
        workspace="/projects/myapp",
        tags=["code"],
        capabilities=["code", "debug"],
    ))

    # Register an ML-focused CC instance
    hub.register_cc(CCAdapter(
        cc_id="cc_ml",
        workspace="/projects/ml-experiment",
        tags=["ml"],
        capabilities=["ml", "research"],
    ))

    # Submit a task — Hub routes to the right CC instance
    task_id = await hub.submit_task(
        agent_id="my_agent",
        task="@ml 帮我分析训练日志中的loss曲线",
        timeout=120.0,
    )
    print(f"Task submitted: {task_id}")

asyncio.run(main())
```

---

## Architecture

### Core Components

| Component | File | Responsibility |
|-----------|------|---------------|
| `UniversalRouterHub` | `router_hub.py` | Central orchestrator; coordinates all components |
| `AgentRegistry` | `agent_registry.py` | Manages connected Agent identities and metadata |
| `CCRegistry` | `cc_registry.py` | Manages CC instance lifecycle, status, and lookup |
| `CCAdapter` | `cc_adapter.py` | Wraps a single CC instance; handles execute/terminate/resume |
| `CCExecutor` | `cc_executor.py` | Low-level CC CLI execution via stream-json protocol |
| `UniversalRouter` | `universal_router.py` | Routes tasks by tag, path, capability, or round-robin |
| `EventBus` | `event_bus.py` | Async pub/sub for real-time Agent ↔ CC communication |
| `AgentAdapter` | `agent_adapter.py` | Protocol definition for connecting any LLM Agent |
| `RouterMCPServer` | `router_mcp_server.py` | Built-in MCP tool server for CC callbacks |
| `MCPHubServer` | `mcp_hub_server.py` | FastMCP-based external MCP server (stdio transport) |
| `HTTPServer` | `http_server.py` | aiohttp REST API for external tools and MCP JS bridge |
| `MCPBridge` | `mcp/router_mcp_bridge.js` | Node.js stdio bridge for MCP tool invocation |

### Data Flow

```
Agent submits task
       │
       ▼
UniversalRouterHub.submit_task()
       │
       ▼
UniversalRouter.route()
  │
  ├─ 1. Explicit tag match?
  ├─ 2. @tag in message?
  ├─ 3. Workspace path match?
  ├─ 4. Capability keyword match?
  ├─ 5. Round-robin idle instances?
  └─ 6. First available instance?
       │
       ▼
CCAdapter.execute(task)
       │
       ▼
CCExecutor.run(task)
  └─ spawn: claude --print --input-format=stream-json
       │
       ▼
Result returned → EventBus notifies Agent
```

### Health Monitoring

The Hub runs a background health monitor that periodically checks CC instances:

| Setting | Default | Description |
|---------|---------|-------------|
| `health_check_interval` | 30s | Interval between health checks |
| `max_consecutive_failures` | 3 | Failures before marking instance as `dead` |
| Check method | Process alive | Verifies subprocess is alive for `busy` instances |

Instance status lifecycle: `idle` > `busy` > `dead` > `starting`

### Parallel Capacity Management

Tasks are queued when all CC instances are busy:

| Setting | Default | Description |
|---------|---------|-------------|
| `max_concurrent` | 5 | Maximum parallel tasks |
| Queue type | `asyncio.Queue` | Background `_process_queue` task |
| Flow | Normal | Immediate execution when capacity available |
| Flow | Full | Queued until instance released |

---

## HTTP API

When running in TCP mode (`--port`), the Hub exposes a REST API:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Hub health status (instances/capacity/tasks/monitoring) |
| `/api/tasks` | POST | Submit a task |
| `/api/tasks/{id}` | GET | Get task status/result |
| `/api/tasks` | GET | List tasks (optional `?agent_id=`) |
| `/api/cc/register` | POST | Register a CC instance |
| `/api/cc` | GET | List CC instances (optional `?status=`) |
| `/api/tools/{name}` | POST | Call a RouterMCPBridge tool |

---

## Agent Integration

Any LLM Agent can connect to the Hub by implementing 5 methods:

```python
from cc_router import AgentAdapter, HubEvent
from typing import AsyncIterator

class MyAgent(AgentAdapter):
    @property
    def agent_id(self) -> str:
        return "my_agent"

    @property
    def supported_events(self) -> list[str]:
        return ["result", "error", "partial", "progress"]

    async def connect(self, hub_url: str = None) -> None: ...
    async def disconnect(self) -> None: ...
    async def submit_task(
        self, task: str, tag: str = None,
        capability: list[str] = None, timeout: float = 300.0,
    ) -> str: ...

    async def on_hub_event(self, event: HubEvent) -> None:
        # Receive real-time callbacks from CC
        print(f"Event: {event.type} → {event.data}")

    async def event_stream(self) -> AsyncIterator[HubEvent]:
        # Yield events for the Agent's main loop
        ...
```

### Built-in Adapters

CC Router ships with ready-made adapters for common agents:

```python
from cc_router.adapters.hermes_adapter import HermesAgentAdapter
from cc_router.adapters.openclaw_adapter import OpenClawAgentAdapter

hermes = HermesAgentAdapter(agent_id="hermes_gateway")
openclaw = OpenClawAgentAdapter(agent_id="openclaw_main")
```

---

## Routing Strategy

When a task is submitted, the Hub selects a target CC instance in this priority order:

| Priority | Strategy | Trigger |
|----------|----------|---------|
| 1 | **Explicit Tag** | `tag="ml"` parameter in `submit_task()` |
| 2 | **@-Mention** | Message starts with `@ml analyze the model` |
| 3 | **Workspace Path** | Task workspace matches a CC instance's workspace |
| 4 | **Capability** | Keywords in task match instance capabilities |
| 5 | **Round Robin** | Distribute across idle instances |
| 6 | **First Available** | Fallback to any ready instance |

Capability keywords are language-aware. For example, a task containing `训练`, `model`, `loss`, or `experiment` triggers the `ml` capability.

---

## CLI Reference

```text
Usage: cc-router [OPTIONS]

Options:
  --host TEXT               Host to bind (default: localhost)
  --port INTEGER            Port to bind (default: 8765)
  --log-level TEXT          Log level: DEBUG, INFO, WARNING, ERROR (default: INFO)
  --config PATH             Path to JSON config file
  --bypass-permission BOOL  Bypass permission checks (default: true)
  --mcp                     Run as MCP Server (stdio transport)
  --help                    Show this message and exit

Alias: ccr
```

### Interactive Configuration Wizard

```bash
python -m cc_router.installer.cli_wizard
```

This detects your environment (available CLIs, Python version, OS) and interactively generates a `cc_router_config.json` tailored to your setup.

---

## Configuration

Config file (`cc_router_config.json`) example:

```json
{
  "hub_host": "localhost",
  "hub_port": 8765,
  "timeout": 300,
  "log_level": "INFO",
  "cc_cli_path": "claude",
  "bypass_permission": true,
  "cc_instances": [
    {
      "cc_id": "cc_code",
      "workspace": "/projects/myapp",
      "tags": ["code"],
      "capabilities": ["code", "debug"]
    }
  ],
  "adapters": {
    "hermes": { "enabled": true },
    "openclaw": { "enabled": false }
  },
  "mcp_tools": {
    "feishu_notify": true,
    "forward_to_agent": true,
    "read_training_log": true,
    "query_experiment_data": true
  }
}
```

A template is available at `cc_router_config.template.json`.

---

## MCP Tools

CC instances can call built-in MCP tools during task execution via the `RouterMCPServer`:

| Tool | Function |
|------|----------|
| `feishu_notify` | Send notification to Feishu |
| `forward_to_agent` | Forward real-time message back to the caller Agent |
| `read_training_log` | Read ML training log files from workspace |
| `query_experiment_data` | Query experiment results |

Tools are invoked by CC via the stdio MCP bridge (`router_mcp_bridge.js`).

---

## MCP Integration

CC Router can run as an **MCP Hub Server** using stdio transport, allowing Claude Desktop and other MCP clients to directly invoke Hub operations.

### Claude Desktop Configuration

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cc_router_mcp": {
      "command": "cc-router",
      "args": ["--mcp"]
    }
  }
}
```

### Available MCP Tools

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `synapse_submit_task` | Submit a task to the Hub for CC processing | `task` |
| `synapse_register_cc` | Register a CC instance with the Hub | `cc_id`, `workspace` |
| `synapse_list_cc_instances` | List registered CC instances | _(optional `status` filter)_ |
| `synapse_list_agents` | List connected agents | _(none)_ |
| `synapse_hub_status` | Hub runtime overview | _(none)_ |
| `synapse_connect_agent` | Connect an external agent | `agent_id` |
| `synapse_disconnect_agent` | Disconnect an agent | `agent_id` |

### Programmatic Usage

```python
from cc_router.mcp_hub_server import mcp

# Start with stdio transport (for Claude Desktop)
mcp.run(transport="stdio")
```

**Using individual tools programmatically:**

```python
from cc_router.mcp_hub_server import (
    mcp,
    SubmitTaskInput,
    synapse_submit_task,
)
import anyio

async def example():
    result = await synapse_submit_task(
        input=SubmitTaskInput(
            task="implement sorting algorithm",
            tag="code",
        ),
    )
    print(result)
```

### CLI Mode

```bash
# Start as MCP Server (stdio transport)
cc-router --mcp

# With custom config and log level
cc-router --mcp --log-level DEBUG --config /path/to/config.json
```

The `--mcp` flag switches the runtime from TCP Hub mode to stdio MCP Server mode.

---

## Requirements

### Software

| Dependency | Required | Notes |
|------------|----------|-------|
| Python | >= 3.11 | Core runtime |
| Claude Code CLI | Yes | `claude` command in PATH for CC execution |
| Hermes CLI | Optional | For Hermes agent integration |
| OpenClaw CLI | Optional | For OpenClaw agent integration |
| `mcp` package | Yes | MCP protocol support (`>=1.0.0`) |

### Hardware

CC Router itself is lightweight, but each Claude Code instance spawned at runtime has significant resource requirements:

| Resource | Per CC Instance | Recommended (3-4 concurrent) |
|----------|----------------|------------------------------|
| RAM | ~2 GB | 8+ GB |
| CPU | 1-2 cores | 4+ cores |
| Disk | ~500 MB | SSD recommended |
| Cold start | 8-12 s | 15+ GB RAM for 5 instances |
| Session resume | 2-4 s | — |

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest -v

# With coverage
pytest --cov=cc_router --cov-report=term

# Lint
ruff check .

# Format
black .

# Type check
mypy cc_router/
```

### Project Structure

```
cc_router/
├── __init__.py              # Public API exports
├── __main__.py              # CLI entry point
├── agent_adapter.py         # Agent protocol definition
├── agent_registry.py        # Agent registration
├── cc_adapter.py            # CC instance adapter
├── cc_executor.py           # CC CLI executor (stream-json)
├── cc_registry.py           # CC instance registry
├── config.py                # Configuration management
├── event_bus.py             # Async pub/sub event bus
├── exceptions.py            # Error types
├── hermes_executor.py       # Hermes subprocess executor
├── openclaw_executor.py     # OpenClaw subprocess executor
├── router_hub.py            # Main orchestrator + health monitor
├── router_mcp_server.py     # MCP tool server
├── mcp_hub_server.py        # FastMCP-based external MCP server (stdio)
├── http_server.py           # aiohttp REST API (7 endpoints)
├── universal_router.py      # Task routing engine
├── adapters/                # Built-in agent adapters
│   ├── hermes_adapter.py
│   └── openclaw_adapter.py
├── installer/               # Interactive setup wizard
│   ├── cli_wizard.py
│   ├── config_writer.py
│   └── env_detector.py
└── mcp/                     # MCP tool implementations
    ├── router_mcp_bridge.js # Node.js stdio bridge
    └── tools/
        ├── feishu_notify.py
        ├── training_log.py
        └── shared_data.py

tests/
├── test_basic.py            # Core functionality tests
├── test_core.py             # Core component tests
├── test_comprehensive.py    # Comprehensive integration tests
├── test_http_server.py      # HTTP API endpoint tests
├── test_mcp_hub.py          # MCP hub server tests
├── test_robustness.py       # Error handling and edge case tests
└── test_local_e2e.py        # End-to-end tests (requires CC CLI)
```

### Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test modules
pytest tests/test_core.py tests/test_basic.py tests/test_comprehensive.py -v

# Run HTTP API tests
pytest tests/test_http_server.py -v

# Run MCP hub tests
pytest tests/test_mcp_hub.py -v

# Run robustness/edge case tests
pytest tests/test_robustness.py -v

# Run end-to-end integration tests (requires CC CLI)
RUN_REAL_CC=1 pytest tests/test_local_e2e.py -v
```

---

## Project Status

**Version 0.3.0** — Alpha stage, approaching public release.

| Component | Status |
|-----------|--------|
| Core routing engine | ✅ Implemented & tested |
| Multi-CC management | ✅ Implemented & tested |
| Agent adapter protocol | ✅ Implemented & tested |
| MCP server & tools | ✅ Implemented & tested |
| Hermes/OpenClaw adapters | ✅ Implemented & tested |
| Session resume | ✅ Implemented & tested |
| Parallel task dispatch | ✅ Implemented & tested |
| Health monitoring | ✅ Implemented & tested |
| HTTP REST API | ✅ Implemented & tested |
| MCP JS bridge | ✅ Implemented & tested |
| **Public release** | 🔜 **Targeting v0.4.0** |

### Roadmap

- **v0.4.0** — Web dashboard + metrics + performance benchmarking
- **v1.0.0** — Stable API, production hardening

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

- [Bug reports](.github/ISSUE_TEMPLATE/bug_report.md)
- [Feature requests](.github/ISSUE_TEMPLATE/feature_request.md)
- [Pull requests](.github/PULL_REQUEST_TEMPLATE.md)

---

## License

[MIT](LICENSE) © CC Router Team
