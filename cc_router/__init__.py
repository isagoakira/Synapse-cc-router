"""
CC Router - Universal Multi-Agent ↔ Multi-CC Connection Hub
"""

__version__ = "0.2.0"

from .config import (
    BYPASS_PERMISSION,
    DEFAULT_CC_CLI_PATH,
    DEFAULT_TIMEOUT,
    HUB_HOST,
    HUB_PORT,
    LOG_LEVEL,
    load_config,
    get_bypass_permission,
)

from .exceptions import (
    RouterError,
    AdapterError,
    CCExecutorError,
    RegistrationError,
)

from .agent_adapter import AgentAdapter, HubEvent
from .cc_adapter import CCAdapter, CCInstance, CCResult
from .cc_executor import CCExecutor, CCResult as CCExecResult
from .hermes_executor import HermesExecutor, HermesResult
from .openclaw_executor import OpenClawExecutor, OpenClawResult
from .event_bus import EventBus
from .universal_router import UniversalRouter
from .agent_registry import AgentRegistry
from .cc_registry import CCRegistry
from .router_hub import UniversalRouterHub, get_global_hub
from .universal_router import RoutingStrategy
from .mcp_hub_server import MCPHubServer, MCPAgentBridge, run_server as run_mcp_server

__all__ = [
    # Config
    "BYPASS_PERMISSION",
    "DEFAULT_CC_CLI_PATH",
    "DEFAULT_TIMEOUT",
    "HUB_HOST",
    "HUB_PORT",
    "LOG_LEVEL",
    "load_config",
    "get_bypass_permission",
    # Exceptions
    "RouterError",
    "AdapterError",
    "CCExecutorError",
    "RegistrationError",
    # Protocols
    "AgentAdapter",
    "HubEvent",
    # Core
    "CCAdapter",
    "CCInstance",
    "CCResult",
    "CCExecutor",
    "CCExecResult",
    "HermesExecutor",
    "HermesResult",
    "OpenClawExecutor",
    "OpenClawResult",
    "EventBus",
    "UniversalRouter",
    "AgentRegistry",
    "CCRegistry",
    "UniversalRouterHub",
    "get_global_hub",
    "RoutingStrategy",
    # MCP Hub Server
    "MCPHubServer",
    "MCPAgentBridge",
    "run_mcp_server",
]
