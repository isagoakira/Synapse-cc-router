# CC Router Examples

This directory contains usage examples for the CC Router.

## Basic Examples

### 1. Minimal Hub Setup

```python
import asyncio
from cc_router import UniversalRouterHub, CCAdapter

async def main():
    hub = UniversalRouterHub()

    # Register a CC instance
    cc = CCAdapter(
        cc_id="my_cc",
        workspace="/path/to/workspace",
        tags=["code"],
        capabilities=["code", "debug"],
    )
    hub.register_cc(cc)

    # Submit a task
    task_id = await hub.submit_task(
        agent_id="my_agent",
        task="Refactor this function",
        tag="code",
    )
    print(f"Submitted task: {task_id}")

    # Wait for result
    await asyncio.sleep(5)
    task = hub.get_task(task_id)
    print(f"Task status: {task.status}")

asyncio.run(main())
```

### 2. Custom Agent Adapter

```python
from cc_router.agent_adapter import AgentAdapter, HubEvent
from typing import AsyncIterator


class MyCustomAgent(AgentAdapter):
    @property
    def agent_id(self) -> str:
        return "my_custom_agent"

    @property
    def supported_events(self) -> list[str]:
        return ["result", "error", "progress"]

    async def connect(self, hub_url: str = None) -> None:
        print(f"Connecting to hub at {hub_url}...")

    async def disconnect(self) -> None:
        print("Disconnecting...")

    async def submit_task(
        self,
        task: str,
        tag: str = None,
        capability: list[str] = None,
        timeout: float = 300.0,
    ) -> str:
        # In a real agent, this would call an API
        return "task_id_from_agent"

    async def on_hub_event(self, event: HubEvent) -> None:
        print(f"Received event: {event.type} -> {event.data}")

    async def event_stream(self) -> AsyncIterator[HubEvent]:
        yield HubEvent(type="heartbeat", task_id="", agent_id=self.agent_id, data={})
```

### 3. Using the CLI

```bash
# Start the hub with default settings
cc-router

# Start with custom port and debug logging
cc-router --port 8765 --log-level DEBUG

# Start with external config file
ccr --config /etc/cc-router/config.json

# Bind to all interfaces
ccr --host 0.0.0.0 --port 8765
```

### 4. MCP Tools from CC Instance

When a CC instance is running inside the hub, it can call MCP tools:

```
# From within Claude Code in a CC instance:
# The tool is available as an MCP tool
```

Tools available:
- `feishu_notify` -- Send notifications to Feishu/Lark
- `forward_to_agent` -- Send real-time updates back to the calling agent
- `read_training_log` -- Read ML training logs from workspace
- `query_experiment_data` -- Query experiment results

### 5. Multi-CC Setup

```python
hub = UniversalRouterHub()

# Register multiple CC instances with different capabilities
hub.register_cc(CCAdapter("cc_code", "/workspace/code", tags=["code"], capabilities=["code", "debug"]))
hub.register_cc(CCAdapter("cc_ml", "/workspace/ml", tags=["ml"], capabilities=["ml", "research"]))
hub.register_cc(CCAdapter("cc_paper", "/workspace/paper", tags=["paper"], capabilities=["paper", "research"]))

# Tags route to specific CCs:
# submit_task("Fix bug", tag="code")     -> cc_code
# submit_task("Train model", tag="ml")    -> cc_ml
# submit_task("Write paper", tag="paper") -> cc_paper
```
