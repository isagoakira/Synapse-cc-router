# CC Router API Reference

## Core Classes

### UniversalRouterHub

The main routing hub. Coordinates agents, CC instances, and event routing.

```python
from cc_router import UniversalRouterHub

hub = UniversalRouterHub()
```

**Methods:**

| Method | Description |
|--------|-------------|
| `connect_agent(agent_id, adapter)` | Register an agent adapter |
| `disconnect_agent(agent_id)` | Unregister an agent |
| `submit_task(agent_id, task, tag, capability, timeout)` | Submit a task for routing |
| `register_cc(cc_adapter)` | Register a CC instance |
| `cc_ready(cc_id, session_id)` | Mark CC as ready/idle |
| `get_task(task_id)` | Get task by ID |
| `list_tasks(agent_id)` | List tasks (optionally filtered) |
| `set_mcp_server(mcp_server)` | Attach MCP server |
| `get_mcp_server()` | Get attached MCP server |

### CCAdapter

Wraps a single Claude Code instance.

```python
from cc_router import CCAdapter

cc = CCAdapter(
    cc_id="cc_001",
    workspace="/path/to/project",
    tags=["ml", "research"],
    capabilities=["code", "research"],
)
```

**Properties:** `cc_id`, `workspace`, `tags`, `capabilities`, `instance`

**Methods:** `execute(task, ...)`, `terminate()`, `get_status()`

### CCExecutor

Low-level executor for the CC CLI stream-json protocol.

```python
from cc_router.cc_executor import CCExecutor

executor = CCExecutor(cc_cli_path="claude")
result = await executor.run(task="say hi", workspace="/tmp")
```

**Returns:** `CCResult` with fields: `kind`, `text`, `session_id`, `cost_usd`, `duration_ms`, `error`

### AgentAdapter (Protocol)

Abstract base class for agent connections. All agents must implement:

```python
from cc_router import AgentAdapter

class MyAgent(AgentAdapter):
    @property
    def agent_id(self) -> str: ...
    @property
    def supported_events(self) -> list[str]: ...
    async def connect(self, hub_url: str = None) -> None: ...
    async def disconnect(self) -> None: ...
    async def submit_task(self, task, tag, capability, timeout) -> str: ...
    async def on_hub_event(self, event: HubEvent) -> None: ...
    async def event_stream(self) -> AsyncIterator[HubEvent]: ...
```

### EventBus

Async pub/sub event bus for bidirectional communication.

```python
from cc_router import EventBus

bus = EventBus()
await bus.subscribe("agent_id", "task_id")
await bus.publish("agent_id", "task_id", {"type": "result", "content": "done"})
```

**Methods:** `subscribe()`, `unsubscribe()`, `publish()`, `event_stream()`, `send_interrupt()`

### UniversalRouter

Routes tasks to CC instances based on priority strategy.

```python
from cc_router import UniversalRouter, RoutingStrategy

router = UniversalRouter(cc_registry)
result = await router.route("task message", tag="ml")
# result.cc_id, result.strategy, result.workspace
```

**Routing priority:** tag > @tag > workspace > capability > round-robin > first-available

### RouterMCPBridge

Built-in MCP tool bridge for CC-to-Agent communication.

```python
from cc_router.router_mcp_server import RouterMCPBridge

bridge = RouterMCPBridge()
result = await bridge.call_tool("feishu_notify", {"text": "Hello"})
```

**Available tools:** `feishu_notify`, `forward_to_agent`, `read_training_log`, `query_experiment_data`

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CC_ROUTER_HUB_URL` | `http://localhost:8765` | Hub endpoint for MCP bridge |

### Config File (cc_router_config.json)

```json
{
  "cc_cli_path": "claude",
  "timeout": 300.0,
  "hub_host": "localhost",
  "hub_port": 8765,
  "log_level": "INFO",
  "bypass_permission": true,
  "max_cc_instances": 5
}
```

## Exceptions

| Exception | Parent | Description |
|-----------|--------|-------------|
| `RouterError` | `Exception` | Base router error |
| `RoutingError` | `RouterError` | No CC instance available |
| `TimeoutError` | `RouterError` | Task execution timeout |
| `AdapterError` | `Exception` | Adapter connection error |
| `CCExecutorError` | `Exception` | CC CLI execution error |
| `RegistrationError` | `Exception` | Duplicate registration |
