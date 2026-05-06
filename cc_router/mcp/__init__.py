"""
MCP module for CC Router.
"""

from .router_mcp_server import (
    RouterMCPBridge,
    set_task_context,
    get_task_context,
    clear_task_context,
)

__all__ = ["RouterMCPBridge", "set_task_context", "get_task_context", "clear_task_context"]
