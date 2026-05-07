"""
MCPHubServer -- FastMCP-based MCP Server wrapping UniversalRouterHub.

Exposes Hub functionality as standard MCP Tools (stdio transport)
for Claude Desktop and other MCP clients.

Tools:
  synapse_submit_task       Submit a task to the Hub for CC processing
  synapse_register_cc       Register a new CC (Claude Code) instance
  synapse_list_cc_instances List registered CC instances (optionally filtered)
  synapse_list_agents       List agents connected to the Hub
  synapse_hub_status        Hub runtime overview
  synapse_connect_agent     Connect an external agent to the Hub
  synapse_disconnect_agent  Disconnect an agent from the Hub

Usage:
    from cc_router.mcp_hub_server import mcp
    mcp.run(transport="stdio")
"""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Optional, TypedDict

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.fastmcp.server import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .cc_adapter import CCAdapter
from .agent_adapter import AgentAdapterImpl
from .exceptions import RouterError, RegistrationError

logger = logging.getLogger(__name__)


# ── Pydantic Input Models ─────────────────────────────────────────────


class SubmitTaskInput(BaseModel):
    """Input model for :func:`synapse_submit_task`."""

    task: str = Field(
        ..., description="Task description or message to process"
    )
    tag: Optional[str] = Field(
        None, description="Optional routing tag (e.g. 'starfire', 'ml')"
    )
    capability: Optional[list[str]] = Field(
        None,
        description="Optional capability requirements (e.g. ['code', 'research'])",
    )
    timeout: float = Field(
        300.0, description="Task timeout in seconds (default: 300)"
    )
    agent_id: str = Field(
        "mcp-client", description="Caller agent ID (default: 'mcp-client')"
    )


class RegisterCCInput(BaseModel):
    """Input model for :func:`synapse_register_cc`."""

    cc_id: str = Field(..., description="Unique identifier for this CC instance")
    workspace: str = Field(
        ..., description="Absolute path to the workspace directory"
    )
    tags: Optional[list[str]] = Field(
        None, description="Optional routing tags (e.g. ['paper', 'ml'])"
    )
    capabilities: list[str] = Field(
        ["general"],
        description="Optional capability list (e.g. ['code', 'research'])",
    )


class ListCCInput(BaseModel):
    """Input model for :func:`synapse_list_cc_instances`."""

    status: Optional[str] = Field(
        None,
        description="Filter instances by current status (idle / busy / starting / dead)",
    )


class ConnectAgentInput(BaseModel):
    """Input model for :func:`synapse_connect_agent`."""

    agent_id: str = Field(..., description="Unique identifier for the agent")
    type: str = Field(
        "mcp",
        description="Agent connection protocol (mcp / http / websocket)",
    )


class DisconnectAgentInput(BaseModel):
    """Input model for :func:`synapse_disconnect_agent`."""

    agent_id: str = Field(..., description="Agent identifier to disconnect")


# ── Minimal AgentAdapter for MCP-connected agents ─────────────────────


class MCPAgentBridge(AgentAdapterImpl):
    """
    Minimal AgentAdapter for agents connected via the MCP Hub Server.

    These agents exist as records in the Hub registry but do not maintain
    a persistent bidirectional connection — they interact through MCP tool calls.
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: str = "mcp",
        hub: Any = None,
    ) -> None:
        super().__init__(agent_id)
        self._agent_type = agent_type
        if hub is not None:
            self._hub = hub

    @property
    def supported_events(self) -> list[str]:
        return ["result", "error", "partial"]


# ── Serialisation helpers ─────────────────────────────────────────────


class CCInstanceDict(TypedDict):
    """JSON-safe representation of a CCInstance."""

    cc_id: str
    workspace: str
    tags: list[str]
    capabilities: list[str]
    status: str
    session_id: str
    pid: int


class AgentNodeDict(TypedDict):
    """JSON-safe representation of an AgentNode."""

    agent_id: str
    protocol: str
    connected_at: str
    last_seen: str
    metadata: dict[str, Any]


def _format_cc_instance(inst: Any) -> CCInstanceDict:
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


def _format_agent_node(node: Any) -> AgentNodeDict:
    """Serialise an AgentNode to a JSON-safe dict."""
    return {
        "agent_id": node.agent_id,
        "protocol": node.protocol,
        "connected_at": node.connected_at,
        "last_seen": node.last_seen,
        "metadata": node.metadata,
    }


# ── Lifespan manager ──────────────────────────────────────────────────


@asynccontextmanager
async def _hub_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """
    Lifespan context manager for the FastMCP server.

    Initialises the global Hub on startup and tears it down on shutdown.
    The yielded dict is exposed to tools via ``ctx.request_context.lifespan_context``.
    """
    from .router_hub import get_global_hub

    hub = get_global_hub()
    logger.info("Hub initialised for FastMCP server '%s'", server.name)
    try:
        yield {"hub": hub}
    finally:
        logger.info("Hub shutting down for FastMCP server '%s'", server.name)


# ── FastMCP Server Instance ───────────────────────────────────────────

mcp = FastMCP("synapse_mcp", lifespan=_hub_lifespan)
"""
The FastMCP server instance. Register additional tools with :func:`mcp.tool`.
Start the server with ``mcp.run(transport="stdio")``.
"""


# ── Response helper ───────────────────────────────────────────────────


def _ok(data: dict) -> str:
    """Return a JSON success response with ``status: ok``."""
    return json.dumps({"status": "ok", **data}, ensure_ascii=False)


# ── Tool: synapse_submit_task ─────────────────────────────────────────


@mcp.tool(
    name="synapse_submit_task",
    description="Submit a task to the Hub for processing by a CC (Claude Code) instance.",
    annotations=ToolAnnotations(
        title="Submit Task",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
)
async def synapse_submit_task(ctx: Context, input: SubmitTaskInput) -> str:
    """
    Submit a task to the Hub for processing by a CC (Claude Code) instance.

    Returns a **task_id** for tracking. The task is routed to an appropriate
    CC instance based on tags, capabilities, or round-robin selection.

    Parameters
    ----------
    input : SubmitTaskInput
        - **task** (``str``, **required**): Task description or message.
        - **tag** (``str`` | ``None``): Optional routing tag.
        - **capability** (``list[str]`` | ``None``): Required capabilities.
        - **timeout** (``float``): Timeout in seconds (default 300).
        - **agent_id** (``str``): Caller agent ID (default ``"mcp-client"``).

    Returns
    -------
    str
        JSON with ``status: "ok"`` and ``task_id`` on success;
        JSON with ``status: "error"`` on failure.

    Example
    -------
    Input::

        {"task": "implement sorting in Python", "tag": "code"}

    Output::

        {"status": "ok", "task_id": "task_001", "message": "Task submitted (id: task_001)"}
    """
    hub = ctx.request_context.lifespan_context["hub"]

    if not input.task.strip():
        raise ValueError("task is required and cannot be empty")

    # Ensure the calling agent is registered with the Hub
    if hub.registry.get_sync(input.agent_id) is None:
        bridge = MCPAgentBridge(input.agent_id, hub=hub)
        hub.connect_agent(input.agent_id, bridge)

    try:
        task_id = await hub.submit_task(
            agent_id=input.agent_id,
            task=input.task,
            tag=input.tag,
            capability=input.capability,
            timeout=input.timeout,
        )
    except RouterError as e:
        raise ValueError(str(e)) from e

    await ctx.info(f"Task submitted: {task_id}")
    return _ok({
        "task_id": task_id,
        "message": f"Task submitted (id: {task_id})",
    })


# ── Tool: synapse_register_cc ─────────────────────────────────────────


@mcp.tool(
    name="synapse_register_cc",
    description="Register a new CC (Claude Code) instance with the Hub.",
    annotations=ToolAnnotations(
        title="Register CC Instance",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def synapse_register_cc(ctx: Context, input: RegisterCCInput) -> str:
    """
    Register a new CC (Claude Code) instance with the Hub.

    The instance becomes available for task routing. Use this to add CC
    workers to the pool.

    Parameters
    ----------
    input : RegisterCCInput
        - **cc_id** (``str``, **required**): Unique identifier.
        - **workspace** (``str``, **required**): Absolute workspace path.
        - **tags** (``list[str]`` | ``None``): Routing tags.
        - **capabilities** (``list[str]``): Capability list.

    Returns
    -------
    str
        JSON confirming registration.

    Example
    -------
    Input::

        {"cc_id": "worker-1", "workspace": "/projects/myapp"}

    Output::

        {"status": "ok", "cc_id": "worker-1", "message": "CC instance 'worker-1' registered"}
    """
    hub = ctx.request_context.lifespan_context["hub"]

    adapter = CCAdapter(
        cc_id=input.cc_id,
        workspace=input.workspace,
        tags=input.tags,
        capabilities=input.capabilities,
    )

    try:
        registered_id = hub.register_cc(adapter)
    except RegistrationError as e:
        raise ValueError(str(e)) from e

    await ctx.info(f"CC instance registered: {registered_id}")
    return _ok({
        "cc_id": registered_id,
        "message": f"CC instance '{registered_id}' registered",
    })


# ── Tool: synapse_list_cc_instances ───────────────────────────────────


@mcp.tool(
    name="synapse_list_cc_instances",
    description="List registered CC instances, optionally filtered by status.",
    annotations=ToolAnnotations(
        title="List CC Instances",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def synapse_list_cc_instances(ctx: Context, input: ListCCInput) -> str:
    """
    List all registered CC instances, optionally filtered by status.

    Parameters
    ----------
    input : ListCCInput
        - **status** (``str`` | ``None``): Optional filter (idle / busy / starting / dead).

    Returns
    -------
    str
        JSON with instance list and count.

    Example
    -------
    Output::

        {"status": "ok", "count": 2, "instances": [...]}
    """
    hub = ctx.request_context.lifespan_context["hub"]

    if input.status:
        instances = hub.cc_registry.list_by_status(input.status)
    else:
        instances = hub.cc_registry.list_all()

    return _ok({
        "count": len(instances),
        "instances": [_format_cc_instance(inst) for inst in instances],
    })


# ── Tool: synapse_list_agents ─────────────────────────────────────────


@mcp.tool(
    name="synapse_list_agents",
    description="List all agents currently connected to the Hub.",
    annotations=ToolAnnotations(
        title="List Agents",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def synapse_list_agents(ctx: Context, input: None = None) -> str:
    """
    List all agents currently connected to the Hub.

    Parameters
    ----------
    input : None
        This tool does not accept any parameters.

    Returns
    -------
    str
        JSON with agent list and count.

    Example
    -------
    Output::

        {"status": "ok", "count": 1, "agents": [...]}
    """
    hub = ctx.request_context.lifespan_context["hub"]
    agents = hub.registry.list_all_sync()
    return _ok({
        "count": len(agents),
        "agents": [_format_agent_node(a) for a in agents],
    })


# ── Tool: synapse_hub_status ──────────────────────────────────────────


@mcp.tool(
    name="synapse_hub_status",
    description="Get Hub runtime status overview including agent count, CC instance count, and task counts.",
    annotations=ToolAnnotations(
        title="Hub Status",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def synapse_hub_status(ctx: Context, input: None = None) -> str:
    """
    Get a comprehensive overview of the Hub runtime status.

    Returns counts and summaries for agents, CC instances, and tasks.

    Parameters
    ----------
    input : None
        This tool does not accept any parameters.

    Returns
    -------
    str
        JSON with Hub status overview.

    Example
    -------
    Output::

        {
          "status": "ok",
          "version": __version__,
          "agents": {"count": 1, "ids": ["mcp-client"]},
          "cc_instances": {"count": 2, "by_status": {"idle": 2}},
          "tasks": {"count": 5, "pending": 0, "running": 0, "done": 5, "error": 0}
        }
    """
    hub = ctx.request_context.lifespan_context["hub"]

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

    return _ok({
        "version": __version__,
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
    })


# ── Tool: synapse_connect_agent ───────────────────────────────────────


@mcp.tool(
    name="synapse_connect_agent",
    description="Connect an external agent to the Hub.",
    annotations=ToolAnnotations(
        title="Connect Agent",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    ),
)
async def synapse_connect_agent(ctx: Context, input: ConnectAgentInput) -> str:
    """
    Connect an external agent to the Hub so it can submit tasks.

    The agent is registered in the Hub registry. Connecting an already
    registered agent is idempotent.

    Parameters
    ----------
    input : ConnectAgentInput
        - **agent_id** (``str``, **required**): Unique agent identifier.
        - **type** (``str``): Connection protocol (mcp / http / websocket).

    Returns
    -------
    str
        JSON confirming connection.

    Example
    -------
    Input::

        {"agent_id": "my-agent", "type": "http"}

    Output::

        {"status": "ok", "agent_id": "my-agent", "message": "Agent 'my-agent' connected via http"}
    """
    hub = ctx.request_context.lifespan_context["hub"]

    # Idempotent: skip if already registered
    if hub.registry.get_sync(input.agent_id) is not None:
        return _ok({"message": f"Agent '{input.agent_id}' already connected"})

    bridge = MCPAgentBridge(input.agent_id, input.type)
    hub.connect_agent(input.agent_id, bridge)

    await ctx.info(f"Agent connected: {input.agent_id} ({input.type})")
    return _ok({
        "agent_id": input.agent_id,
        "message": f"Agent '{input.agent_id}' connected via {input.type}",
    })


# ── Tool: synapse_disconnect_agent ────────────────────────────────────


@mcp.tool(
    name="synapse_disconnect_agent",
    description="Disconnect an agent from the Hub.",
    annotations=ToolAnnotations(
        title="Disconnect Agent",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    ),
)
async def synapse_disconnect_agent(ctx: Context, input: DisconnectAgentInput) -> str:
    """
    Disconnect an agent from the Hub, removing it from the registry.

    Disconnecting a non-existent agent is treated as a no-op (idempotent).

    Parameters
    ----------
    input : DisconnectAgentInput
        - **agent_id** (``str``, **required**): Agent to disconnect.

    Returns
    -------
    str
        JSON confirming disconnection.

    Example
    -------
    Input::

        {"agent_id": "my-agent"}

    Output::

        {"status": "ok", "agent_id": "my-agent", "message": "Agent 'my-agent' disconnected"}
    """
    hub = ctx.request_context.lifespan_context["hub"]

    if hub.registry.get_sync(input.agent_id) is None:
        return _ok({
            "message": f"Agent '{input.agent_id}' not found (already disconnected)",
        })

    hub.disconnect_agent(input.agent_id)
    await ctx.info(f"Agent disconnected: {input.agent_id}")
    return _ok({
        "agent_id": input.agent_id,
        "message": f"Agent '{input.agent_id}' disconnected",
    })


# ── Backward-compatible wrapper ───────────────────────────────────────


class MCPHubServer:
    """
    Backward-compatible wrapper around the FastMCP server instance.

    Provided so that code importing ``MCPHubServer`` continues to work
    without changes. Prefer using the module-level ``mcp`` object directly
    in new code.
    """

    async def run(self) -> None:
        """
        Run the FastMCP server with stdio transport.

        Blocks until the transport closes (EOF on stdin).
        """
        await mcp.run_stdio_async()

    @property
    def app(self) -> FastMCP:
        """Return the underlying FastMCP instance."""
        return mcp


async def run_server() -> None:
    """Convenience function: create and run an MCP server with stdio transport."""
    server = MCPHubServer()
    await server.run()


__all__ = [
    # Pydantic models
    "SubmitTaskInput",
    "RegisterCCInput",
    "ListCCInput",
    "ConnectAgentInput",
    "DisconnectAgentInput",
    # Server
    "MCPHubServer",
    "MCPAgentBridge",
    "mcp",
    "run_server",
]
