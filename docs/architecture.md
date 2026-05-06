# CC Router Architecture

## Overview

CC Router provides **NxM** connections between any number of LLM Agents and any number of Claude Code (CC) instances. It uses a hub-and-spoke architecture with intelligent task routing and bidirectional event communication.

```
Agent (Hermes/OpenClaw/Custom)
    |  AgentAdapter Protocol
    v
UniversalRouterHub
    |-- AgentRegistry (who is connected)
    |-- CCRegistry (available CC instances)
    |-- UniversalRouter (where to route)
    |-- EventBus (how they communicate)
    |-- MCP Server (tool bridge)
    |
    v
CCAdapter --> CCExecutor --> claude --print (subprocess)
```

## Core Design Principles

### 1. Hub is Stateless

The UniversalRouterHub itself holds no persistent state. All state lives in its sub-components:

- **AgentRegistry** tracks which agents are connected and their metadata
- **CCRegistry** tracks CC instance states (idle/busy/dead)
- **EventBus** maintains subscription queues for active tasks
- **Tasks** are ephemeral: created on submit, tracked until completion

This design allows the hub to be restarted without losing connection state (agents reconnect) and makes horizontal scaling possible.

### 2. Protocol-Driven Adapters

Every agent connects through the `AgentAdapter` protocol — an abstract class with 5 required methods:

```
agent_id          →  Unique identifier
supported_events  →  What event types this agent consumes
connect()         →  Establish connection to hub
disconnect()      →  Tear down connection
submit_task()     →  Submit a task for routing
on_hub_event()    →  Handle incoming events from CC
event_stream()    →  Async iterator for receiving events
```

This means any agent — Hermes, OpenClaw, WebSocket, gRPC, custom — can connect by implementing these 5 methods.

### 3. Priority-Based Routing

Routing follows a strict priority chain:

| Priority | Strategy | Example |
|----------|----------|---------|
| 1 | Explicit `tag=` parameter | `submit_task(tag="ml")` |
| 2 | `@tag` in message text | `@paper write introduction` |
| 3 | Workspace path match | Task references a known directory |
| 4 | Capability keywords | Task contains "debug", "train", etc. |
| 5 | Round-robin idle | Distribute across idle instances |
| 6 | First available | Any instance that can take work |

### 4. Bidirectional Event Bus

The EventBus enables full-duplex communication:

- **Hub -> Agent**: CC execution results, progress updates, errors
- **Agent -> Hub**: Task submissions, interrupt commands
- **CC -> Agent**: Real-time partial messages via MCP tools

Events flow through `asyncio.Queue` channels keyed by `(agent_id, task_id)`.

## Component Details

### UniversalRouterHub (`router_hub.py`)

The main entry point. Coordinates all sub-components and exposes the high-level API:

- `connect_agent()` / `disconnect_agent()` — Manage agent lifecycle
- `register_cc()` — Add a CC instance to the pool
- `submit_task()` — Route and execute a task asynchronously
- Task tracking via `get_task()` / `list_tasks()`

### CCAdapter (`cc_adapter.py`)

Wraps a single CC instance:

- Manages state machine: `idle -> busy -> idle | dead`
- Holds workspace path, tags, and capabilities
- Delegates actual execution to `CCExecutor`
- Preserves session IDs across calls for resumption

### CCExecutor (`cc_executor.py`)

Low-level subprocess manager for `claude --print`:

- Spawns CC CLI as subprocess with stream-json protocol
- Reads events from stdout (init, result, error, auth_error)
- Handles timeouts and process crashes
- Returns structured `CCResult` objects

### EventBus (`event_bus.py`)

Async pub/sub event system:

- Per-agent task queues for targeted delivery
- Global agent channels for broadcast events
- Priority ordering (global events first)
- Interrupt channel for cancellation

### UniversalRouter (`universal_router.py`)

Routing engine:

- Implements 6-level priority routing
- Capability keyword matching with multi-language support
- Thread-safe round-robin counter
- Returns `RouteResult` with routing metadata

### RouterMCPBridge (`router_mcp_server.py`)

MCP tool bridge enabling CC instances to call back to the hub:

- Tools: `feishu_notify`, `forward_to_agent`, `read_training_log`, `query_experiment_data`
- Task context stored in global dict (set before CC execution)
- Forwards events to caller agent via EventBus

## Data Flow

### Task Submission Flow

```
Agent            Hub                Router         CCAdapter         CC CLI
  |                |                   |              |                 |
  |-- submit_task -|                   |              |                 |
  |                |--- route() ------>|              |                 |
  |                |<-- RouteResult ---|              |                 |
  |                |                   |              |                 |
  |                |-- create_task() --|              |                 |
  |                |-- asyncio.create_task(_execute)  |                 |
  |                |                   |              |                 |
  |                |--- execute() ------------------->|                 |
  |                |                   |              |-- run()-------->|
  |                |                   |              |                 |-- claude --
  |                |                   |              |<-- CCResult ----|     print
  |<-- event -----|                   |              |                 |
  |   (result)    |                   |              |                 |
```

### CC-to-Agent Callback Flow (via MCP)

```
CC CLI            MCP Bridge          EventBus          Agent
  |                   |                  |                |
  |-- call_tool() --->|                  |                |
  |  forward_to_agent |                  |                |
  |                   |-- publish() ---->|                |
  |                   |                  |-- event_stream |
  |                   |                  |     (yield) -->|
  |<-- result --------|                  |                |-- on_hub_event()
```

## Session Management

CC sessions are automatically preserved:

1. First execution creates a session ID
2. Session ID is stored in CCAdapter
3. Subsequent calls use `--resume` for faster cold start (2-4s vs 8-12s)
4. The `--no-session-persistence` flag is NEVER used (would break resume)

## Thread Safety

All registries use `asyncio.Lock()` for thread-safe operations:

- `CCRegistry` — Lock on async status updates
- `AgentRegistry` — Lock on register/unregister
- `EventBus` — Lock on subscription modifications
- `UniversalRouter` — Lock on round-robin counter
