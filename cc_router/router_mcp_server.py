"""
RouterMCPServer - Built-in MCP Server for CC instances.
"""

import logging

from .router_hub import get_global_hub

logger = logging.getLogger(__name__)


# Global task context lookup (set by CCAdapter.execute)
_TASK_CONTEXT: dict = {}


def set_task_context(task_id: str, cc_id: str, caller_agent_id: str):
    """Set task context before CC execution."""
    _TASK_CONTEXT[task_id] = {"cc_id": cc_id, "agent_id": caller_agent_id}


def get_task_context(task_id: str) -> dict:
    """Get task context during CC execution."""
    return _TASK_CONTEXT.get(task_id, {})


def clear_task_context(task_id: str):
    """Clear task context after CC execution."""
    _TASK_CONTEXT.pop(task_id, None)


class RouterMCPBridge:
    """
    Bridge between MCP tool calls and Hub's EventBus.

    CC instances connect via stdio to call these tools:
    - feishu_notify: Send Feishu notification
    - forward_to_agent: Forward event to caller Agent
    - read_training_log: Read ML training logs
    - query_experiment_data: Query experiment results
    """

    def __init__(self):
        self._tools = {
            "feishu_notify": self._feishu_notify,
            "forward_to_agent": self._forward_to_agent,
            "read_training_log": self._read_training_log,
            "query_experiment_data": self._query_experiment_data,
        }

    async def call_tool(self, name: str, arguments: dict, context: dict = None) -> dict:
        """Call a tool by name with arguments."""
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")

        task_id = context.get("task_id", "") if context else ""
        task_meta = get_task_context(task_id)

        return await self._tools[name](arguments, task_meta)

    async def _feishu_notify(self, args: dict, task_meta: dict) -> dict:
        """Send Feishu notification."""
        text = args.get("text", "")
        logger.info("Feishu notify: %s", text[:100])
        return {"status": "ok", "message": "Notification sent"}

    async def _forward_to_agent(self, args: dict, task_meta: dict) -> dict:
        """Forward event to caller Agent via EventBus."""
        event_type = args.get("event_type", "partial")
        content = args.get("content", "")
        task_id = args.get("task_id", "")

        hub = get_global_hub()
        agent_id = task_meta.get("agent_id", "")

        if agent_id:
            await hub.event_bus.publish(agent_id, task_id, {"type": event_type, "content": content})

        return {"status": "ok", "message": "forwarded"}

    async def _read_training_log(self, args: dict, task_meta: dict) -> dict:
        """Read ML training log files."""
        return {"status": "ok", "logs": [], "message": "Training log reading not yet implemented"}

    async def _query_experiment_data(self, args: dict, task_meta: dict) -> dict:
        """Query experiment results."""
        return {
            "status": "ok",
            "data": None,
            "message": "Experiment data query not yet implemented",
        }

    def list_tools(self) -> list[dict]:
        """List available tools."""
        return [
            {
                "name": "feishu_notify",
                "description": "Send notification to Feishu",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "chat_id": {"type": "string"},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "forward_to_agent",
                "description": "Forward message to caller Agent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "event_type": {"type": "string"},
                        "content": {"type": "string"},
                        "task_id": {"type": "string"},
                    },
                    "required": ["event_type", "content", "task_id"],
                },
            },
            {
                "name": "read_training_log",
                "description": "Read ML training log files",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "workspace": {"type": "string"},
                        "pattern": {"type": "string"},
                    },
                },
            },
            {
                "name": "query_experiment_data",
                "description": "Query experiment results",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "experiment": {"type": "string"},
                        "metric": {"type": "string"},
                    },
                },
            },
        ]
