"""
HTTP Server for CC Router Hub.

Provides a REST API for external tools (including the MCP JS bridge)
to interact with the Hub. Started automatically in TCP mode (``--port``).

Endpoints:
  GET  /api/health         Health check
  POST /api/tasks          Submit a task
  GET  /api/tasks          List tasks (optional ``?agent_id=``)
  GET  /api/tasks/{id}     Get task status/result
  POST /api/cc/register    Register a CC instance
  GET  /api/cc             List CC instances (optional ``?status=``)
  POST /api/tools/{name}   Call a RouterMCPBridge tool
"""

from __future__ import annotations

import asyncio
import json
import logging

from aiohttp import web

from .router_hub import get_global_hub

logger = logging.getLogger(__name__)


# ── Response helpers ────────────────────────────────────────────────


def _json(data: dict, status: int = 200) -> web.Response:
    return web.json_response(
        data,
        status=status,
        dumps=lambda o: json.dumps(o, ensure_ascii=False, default=str),
    )


def _ok(data: dict, status: int = 200) -> web.Response:
    return _json({"status": "ok", **data}, status=status)


def _err(message: str, status: int = 400) -> web.Response:
    return _json({"status": "error", "message": message}, status=status)


# ── Routes ──────────────────────────────────────────────────────────

routes = web.RouteTableDef()


# ── Health ──────────────────────────────────────────────────────────


@routes.get("/api/health")
async def handle_health(request: web.Request) -> web.Response:
    """Health check — reports hub stats, instance status, and capacity."""
    hub = get_global_hub()
    summary = hub.get_health_summary()
    agents = hub.registry.list_all_sync()
    return _ok({
        "agents": {"count": len(agents)},
        **summary,
    })


# ── Tasks ───────────────────────────────────────────────────────────


@routes.post("/api/tasks")
async def handle_submit_task(request: web.Request) -> web.Response:
    """Submit a task to the Hub."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _err("Invalid JSON body")

    task_desc = (body.get("task") or "").strip()
    if not task_desc:
        return _err("task is required")

    hub = get_global_hub()
    try:
        task_id = await hub.submit_task(
            agent_id=body.get("agent_id", "http-client"),
            task=task_desc,
            tag=body.get("tag"),
            capability=body.get("capability"),
            timeout=float(body.get("timeout", 300.0)),
        )
        return _ok({"task_id": task_id}, status=201)
    except Exception as exc:
        logger.exception("Task submission failed")
        return _err(str(exc), status=500)


@routes.get("/api/tasks/{task_id}")
async def handle_get_task(request: web.Request) -> web.Response:
    """Get a single task's status and result."""
    hub = get_global_hub()
    task = hub.get_task(request.match_info["task_id"])
    if not task:
        return _err("Task not found", status=404)

    return _ok({
        "task_id": task.task_id,
        "status": task.status,
        "cc_id": task.cc_id,
        "task": task.task,
        "caller_agent_id": task.caller_agent_id,
        "created_at": task.created_at,
        "result": task.result.text if task.result else None,
        "error": task.error,
    })


@routes.get("/api/tasks")
async def handle_list_tasks(request: web.Request) -> web.Response:
    """List tasks, optionally filtered by agent_id."""
    hub = get_global_hub()
    agent_id = request.query.get("agent_id")
    tasks = hub.list_tasks(agent_id)
    return _ok({
        "count": len(tasks),
        "tasks": [
            {
                "task_id": t.task_id,
                "status": t.status,
                "cc_id": t.cc_id,
                "caller_agent_id": t.caller_agent_id,
                "created_at": t.created_at,
            }
            for t in tasks
        ],
    })


# ── CC instances ────────────────────────────────────────────────────


@routes.post("/api/cc/register")
async def handle_register_cc(request: web.Request) -> web.Response:
    """Register a new CC instance."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return _err("Invalid JSON body")

    cc_id = (body.get("cc_id") or "").strip()
    workspace = (body.get("workspace") or "").strip()
    if not cc_id or not workspace:
        return _err("cc_id and workspace are required")

    from .cc_adapter import CCAdapter

    hub = get_global_hub()
    adapter = CCAdapter(
        cc_id=cc_id,
        workspace=workspace,
        tags=body.get("tags"),
        capabilities=body.get("capabilities", ["general"]),
    )
    try:
        registered_id = hub.register_cc(adapter)
        return _ok({"cc_id": registered_id}, status=201)
    except Exception as exc:
        return _err(str(exc), status=409)


@routes.get("/api/cc")
async def handle_list_cc(request: web.Request) -> web.Response:
    """List registered CC instances."""
    hub = get_global_hub()
    status_filter = request.query.get("status")
    instances = (
        hub.cc_registry.list_by_status(status_filter)
        if status_filter
        else hub.cc_registry.list_all()
    )
    return _ok({
        "count": len(instances),
        "instances": [
            {
                "cc_id": inst.cc_id,
                "workspace": inst.workspace,
                "status": inst.status,
                "tags": inst.tag if hasattr(inst, "tag") else [],
                "capabilities": inst.capability if hasattr(inst, "capability") else [],
                "session_id": inst.session_id,
            }
            for inst in instances
        ],
    })


# ── Bridge tools (for JS bridge delegation) ─────────────────────────


@routes.post("/api/tools/{tool_name}")
async def handle_call_tool(request: web.Request) -> web.Response:
    """Call a RouterMCPBridge tool via HTTP."""
    tool_name = request.match_info["tool_name"]
    body = await request.json() if request.can_read_body else {}

    hub = get_global_hub()
    bridge = getattr(hub, "_mcp_server", None)
    if not bridge:
        return _err("No MCP bridge available", status=503)

    try:
        result = await bridge.call_tool(
            tool_name,
            body.get("arguments", {}),
            context=body.get("context"),
        )
        return _json(result)
    except ValueError as exc:
        return _err(str(exc), status=400)
    except Exception as exc:
        logger.exception("Tool call failed: %s", tool_name)
        return _err(str(exc), status=500)


# ── Server factory ──────────────────────────────────────────────────


def create_app() -> web.Application:
    """Create the aiohttp web application."""
    app = web.Application()
    app.add_routes(routes)
    return app


async def run_http_server(host: str = "0.0.0.0", port: int = 8765) -> None:
    """Run the HTTP server (blocks until cancelled).

    Args:
        host: Bind address (default: ``0.0.0.0``)
        port: TCP port (default: ``8765``)
    """
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("HTTP server started on %s:%s", host, port)

    try:
        while True:
            await asyncio.sleep(3600)  # long sleep, cancelled on shutdown
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()
        logger.info("HTTP server stopped")
