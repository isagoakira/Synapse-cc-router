"""
MCPHubServer -- External MCP Server wrapping UniversalRouterHub.

Exposes Hub functionality as standard MCP Tools (stdio transport)
for Claude Desktop and other MCP clients.

Tools:
  submit_task       Submit a task to the Hub for CC processing
  register_cc       Register a new CC (Claude Code) instance
  list_cc_instances List registered CC instances (optionally filtered)
  list_agents       List agents connected to the Hub
  hub_status        Hub runtime overview
  connect_agent     Connect an external agent to the Hub
  disconnect_agent  Disconnect an agent from the Hub

Usage:
    from cc_router.mcp_hub_server import MCPHubServer
    server = MCPHubServer()
    await server.run()
"""

import json
import logging
from typing import Any, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .cc_adapter import CCAdapter
from .agent_adapter import AgentAdapterImpl
from .exceptions import RouterError, RegistrationError

logger = logging.getLogger(__name__)


# ── Minimal AgentAdapter for MCP-connected agents ────────────────

class MCPAgentBridge(AgentAdapterImpl):
    """
    Minimal AgentAdapter for agents connected via the MCP Hub Server.

    These agents exist as records in the Hub registry but do not maintain
    a persistent bidirectional connection -- they interact through MCP tool calls.
    """

    def __init__(self, agent_id: str, agent_type: str = "mcp") -> None:
        super().__init__(agent_id)
        self._agent_type = agent_type

    @property
    def supported_events(self) -> list[str]:
        return ["result", "error", "partial"]


# ── Serialisation helpers ─────────────────────────────────────────

def _format_cc_instance(inst: Any) -> dict:
    """Serialise a CCInstance to a JSON-safe dict."""
    return {
        "cc_id": inst.cc_id,
        "workspace": inst.workspace,
        "tags": inst.tag if hasattr(inst, "tag") else [],
        "capabilities": inst.capability if hasattr(inst, "capability") else [],
        "status": inst.status,
        "session_id": inst.session_id,
        "pid": inst.pid,
    }


def _format_agent_node(node: Any) -> dict:
    """Serialise an AgentNode to a JSON-safe dict."""
    return {
        "agent_id": node.agent_id,
        "protocol": node.protocol,
        "connected_at": node.connected_at,
        "last_seen": node.last_seen,
        "metadata": node.metadata,
    }


# ── MCP Hub Server ────────────────────────────────────────────────

class MCPHubServer:
    """
    MCP Hub Server that wraps UniversalRouterHub as standard MCP Tools.

    Uses stdio transport, making it compatible with Claude Desktop's
    ``mcpServers`` configuration.

    Usage::

        server = MCPHubServer()
        await server.run()
    """

    def __init__(self) -> None:
        self._app = Server("synapse-hub")
        self._hub: Optional[Any] = None  # lazy-initialised
        self._setup_handlers()

    # ── Hub access (lazy) ──────────────────────────────────────────

    def _get_hub(self) -> Any:
        """Return the global Hub singleton, creating it if necessary."""
        if self._hub is None:
            from .router_hub import get_global_hub

            self._hub = get_global_hub()
        return self._hub

    # ── MCP handler registration ───────────────────────────────────

    def _setup_handlers(self) -> None:
        """Register list_tools and call_tool handlers with the MCP Server."""
        app = self._app

        @app.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="submit_task",
                    description="Submit a task to the Hub for processing by a CC (Claude Code) instance. "
                    "Returns a task_id for tracking.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "task": {
                                "type": "string",
                                "description": "Task description or message to process",
                            },
                            "tag": {
                                "type": "string",
                                "description": "Optional routing tag (e.g. 'starfire', 'ml')",
                            },
                            "capability": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional capability requirements (e.g. ['code', 'research'])",
                            },
                            "timeout": {
                                "type": "number",
                                "description": "Task timeout in seconds (default: 300)",
                            },
                            "agent_id": {
                                "type": "string",
                                "description": "Caller agent ID (default: 'mcp-client')",
                            },
                        },
                        "required": ["task"],
                    },
                ),
                Tool(
                    name="register_cc",
                    description="Register a new CC (Claude Code) instance with the Hub. "
                    "The instance becomes available for task routing.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "cc_id": {
                                "type": "string",
                                "description": "Unique identifier for this CC instance",
                            },
                            "workspace": {
                                "type": "string",
                                "description": "Absolute path to the workspace directory",
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional routing tags (e.g. ['paper', 'ml'])",
                            },
                            "capabilities": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional capability list (e.g. ['code', 'research'])",
                            },
                        },
                        "required": ["cc_id", "workspace"],
                    },
                ),
                Tool(
                    name="list_cc_instances",
                    description="List all registered CC instances, optionally filtered by status.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": ["idle", "busy", "starting", "dead"],
                                "description": "Filter instances by current status",
                            },
                        },
                    },
                ),
                Tool(
                    name="list_agents",
                    description="List all agents currently connected to the Hub.",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="hub_status",
                    description="Get Hub runtime status overview including agent count, "
                    "CC instance count by status, and task counts.",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="connect_agent",
                    description="Connect an external agent to the Hub. "
                    "The agent is registered and can submit tasks.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_id": {
                                "type": "string",
                                "description": "Unique identifier for the agent",
                            },
                            "type": {
                                "type": "string",
                                "enum": ["mcp", "http", "websocket"],
                                "description": "Agent connection protocol (default: 'mcp')",
                            },
                        },
                        "required": ["agent_id"],
                    },
                ),
                Tool(
                    name="disconnect_agent",
                    description="Disconnect an agent from the Hub. "
                    "The agent is removed from the registry.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "agent_id": {
                                "type": "string",
                                "description": "Agent identifier to disconnect",
                            },
                        },
                        "required": ["agent_id"],
                    },
                ),
            ]

        @app.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            try:
                return await self._handle_call(name, arguments)
            except RouterError as e:
                logger.warning("Tool '%s' returned RouterError: %s", name, e)
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False),
                    )
                ]
            except Exception as e:
                logger.error("Tool '%s' failed: %s", name, e, exc_info=True)
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {"status": "error", "error": f"Internal server error: {e}"},
                            ensure_ascii=False,
                        ),
                    )
                ]

    # ── Tool dispatch ──────────────────────────────────────────────

    async def _handle_call(self, name: str, args: dict) -> list[TextContent]:
        """Dispatch a tool call to the appropriate handler method."""
        handlers = {
            "submit_task": self._submit_task,
            "register_cc": self._register_cc,
            "list_cc_instances": self._list_cc_instances,
            "list_agents": self._list_agents,
            "hub_status": self._hub_status,
            "connect_agent": self._connect_agent,
            "disconnect_agent": self._disconnect_agent,
        }

        handler = handlers.get(name)
        if handler is None:
            raise RouterError(f"Unknown tool: {name}")

        result = await handler(args)
        return [
            TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, indent=2),
            )
        ]

    # ── Tool: submit_task ──────────────────────────────────────────

    async def _submit_task(self, args: dict) -> dict:
        """Submit a task to the Hub for processing."""
        task = (args.get("task") or "").strip()
        if not task:
            return {"status": "error", "error": "task is required and cannot be empty"}

        hub = self._get_hub()
        agent_id = args.get("agent_id", "mcp-client")
        tag = args.get("tag")
        capability = args.get("capability")
        timeout = float(args.get("timeout", 300.0))

        # Ensure the calling agent is registered with the Hub
        if hub.registry.get_sync(agent_id) is None:
            bridge = MCPAgentBridge(agent_id)
            bridge._hub = hub  # bypass AgentAdapterImpl.connect() ref lookup
            hub.connect_agent(agent_id, bridge)

        try:
            task_id = await hub.submit_task(
                agent_id=agent_id,
                task=task,
                tag=tag,
                capability=capability,
                timeout=timeout,
            )
        except RouterError as e:
            return {"status": "error", "error": str(e)}

        return {
            "status": "ok",
            "task_id": task_id,
            "message": f"Task submitted (id: {task_id})",
        }

    # ── Tool: register_cc ──────────────────────────────────────────

    async def _register_cc(self, args: dict) -> dict:
        """Register a new CC instance with the Hub."""
        cc_id = (args.get("cc_id") or "").strip()
        workspace = (args.get("workspace") or "").strip()

        if not cc_id:
            return {"status": "error", "error": "cc_id is required"}
        if not workspace:
            return {"status": "error", "error": "workspace is required"}

        hub = self._get_hub()
        tags = args.get("tags")
        capabilities = args.get("capabilities", ["general"])

        adapter = CCAdapter(
            cc_id=cc_id,
            workspace=workspace,
            tags=tags,
            capabilities=capabilities,
        )

        try:
            registered_id = hub.register_cc(adapter)
        except RegistrationError as e:
            return {"status": "error", "error": str(e)}

        return {
            "status": "ok",
            "cc_id": registered_id,
            "message": f"CC instance '{registered_id}' registered",
        }

    # ── Tool: list_cc_instances ────────────────────────────────────

    async def _list_cc_instances(self, args: dict) -> dict:
        """List registered CC instances, optionally filtered by status."""
        hub = self._get_hub()
        status_filter = args.get("status")

        if status_filter:
            instances = hub.cc_registry.list_by_status(status_filter)
        else:
            instances = hub.cc_registry.list_all()

        return {
            "status": "ok",
            "count": len(instances),
            "instances": [_format_cc_instance(inst) for inst in instances],
        }

    # ── Tool: list_agents ──────────────────────────────────────────

    async def _list_agents(self, args: dict) -> dict:
        """List all agents currently connected to the Hub."""
        hub = self._get_hub()
        agents = hub.registry.list_all_sync()
        return {
            "status": "ok",
            "count": len(agents),
            "agents": [_format_agent_node(a) for a in agents],
        }

    # ── Tool: hub_status ───────────────────────────────────────────

    async def _hub_status(self, args: dict) -> dict:
        """Return Hub runtime status overview."""
        hub = self._get_hub()

        cc_instances = hub.cc_registry.list_all()
        agents = hub.registry.list_all_sync()
        tasks = hub.list_tasks()

        status_counts: dict[str, int] = {}
        for inst in cc_instances:
            status_counts[inst.status] = status_counts.get(inst.status, 0) + 1

        task_counts = {"pending": 0, "running": 0, "done": 0, "error": 0}
        for t in tasks:
            if t.status in task_counts:
                task_counts[t.status] += 1

        return {
            "status": "ok",
            "version": "0.2.0",
            "agents": {
                "count": len(agents),
                "ids": [a.agent_id for a in agents],
            },
            "cc_instances": {
                "count": len(cc_instances),
                "by_status": status_counts,
            },
            "tasks": {
                "count": len(tasks),
                **task_counts,
            },
        }

    # ── Tool: connect_agent ────────────────────────────────────────

    async def _connect_agent(self, args: dict) -> dict:
        """Connect an external agent to the Hub."""
        agent_id = (args.get("agent_id") or "").strip()
        if not agent_id:
            return {"status": "error", "error": "agent_id is required"}

        hub = self._get_hub()

        # Idempotent: skip if already registered
        if hub.registry.get_sync(agent_id) is not None:
            return {"status": "ok", "message": f"Agent '{agent_id}' already connected"}

        agent_type = args.get("type", "mcp")
        bridge = MCPAgentBridge(agent_id, agent_type)
        hub.connect_agent(agent_id, bridge)

        return {
            "status": "ok",
            "agent_id": agent_id,
            "message": f"Agent '{agent_id}' connected via {agent_type}",
        }

    # ── Tool: disconnect_agent ─────────────────────────────────────

    async def _disconnect_agent(self, args: dict) -> dict:
        """Disconnect an agent from the Hub."""
        agent_id = (args.get("agent_id") or "").strip()
        if not agent_id:
            return {"status": "error", "error": "agent_id is required"}

        hub = self._get_hub()

        if hub.registry.get_sync(agent_id) is None:
            return {
                "status": "ok",
                "message": f"Agent '{agent_id}' not found (already disconnected)",
            }

        hub.disconnect_agent(agent_id)
        return {
            "status": "ok",
            "agent_id": agent_id,
            "message": f"Agent '{agent_id}' disconnected",
        }

    # ── Lifecycle ──────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Run the MCP server with stdio transport.

        Blocks until the transport closes (EOF on stdin).
        """
        logger.info("Starting Synapse MCP Hub Server (stdio transport)")
        async with stdio_server() as (read_stream, write_stream):
            await self._app.run(read_stream, write_stream)
        logger.info("Synapse MCP Hub Server stopped")


async def run_server() -> None:
    """Convenience function: create and run an MCPHubServer."""
    server = MCPHubServer()
    await server.run()


__all__ = [
    "MCPHubServer",
    "MCPAgentBridge",
    "run_server",
]
