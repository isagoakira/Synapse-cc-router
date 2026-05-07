"""Configuration management for CC Router.
Supports both direct assignment and JSON file loading."""

import json
from pathlib import Path
from typing import Any, Optional

# Default values
DEFAULT_CC_CLI_PATH = "claude"
DEFAULT_TIMEOUT = 300.0
HUB_HOST = "localhost"
HUB_PORT = 8765
LOG_LEVEL = "INFO"
BYPASS_PERMISSION = True  # Default bypass all permission checks
MCP_ENABLED = False  # Default: TCP Hub mode
MCP_SERVER_NAME = "synapse-hub"  # MCP server name

# Health monitoring
HEALTH_CHECK_INTERVAL = 30.0  # Seconds between health check cycles
MAX_CONSECUTIVE_FAILURES = 3  # Mark dead after N failed checks

# Parallel capacity
MAX_CONCURRENT_TASKS = 5  # Maximum concurrent CC tasks

# Global config state
_config: dict[str, Any] = {
    "cc_cli_path": DEFAULT_CC_CLI_PATH,
    "timeout": DEFAULT_TIMEOUT,
    "hub_host": HUB_HOST,
    "hub_port": HUB_PORT,
    "log_level": LOG_LEVEL,
    "bypass_permission": BYPASS_PERMISSION,
    "mcp_enabled": MCP_ENABLED,
    "mcp_server_name": MCP_SERVER_NAME,
    "health_check_interval": HEALTH_CHECK_INTERVAL,
    "max_consecutive_failures": MAX_CONSECUTIVE_FAILURES,
    "max_concurrent": MAX_CONCURRENT_TASKS,
}


def load_config(config_path: Optional[str] = None) -> dict:
    """
    Load configuration from JSON file.

    Args:
        config_path: Path to config JSON file. If None, uses default paths.

    Returns:
        Loaded configuration dictionary.
    """
    global _config

    if config_path is None:
        # Try default locations
        possible_paths = [
            Path("cc_router_config.json"),
            Path.home() / ".cc_router" / "config.json",
            Path(__file__).parent.parent / "cc_router_config.json",
        ]
        for path in possible_paths:
            if path.exists():
                config_path = str(path)
                break

    if config_path and Path(config_path).exists():
        try:
            with open(config_path, "r") as f:
                loaded = json.load(f)
                _config.update(loaded)
        except (json.JSONDecodeError, OSError) as e:
            from .exceptions import RouterError

            raise RouterError(f"Failed to load config from {config_path}: {e}")

    return _config.copy()


def get_config() -> dict:
    """Get current configuration dictionary copy."""
    return _config.copy()


def update_config(**kwargs) -> None:
    """Update configuration values with provided keyword arguments."""
    _config.update(kwargs)


def get_cc_cli_path() -> str:
    """Get CC CLI path from config."""
    return _config["cc_cli_path"]


def get_timeout() -> float:
    """Get default timeout from config."""
    return _config["timeout"]


def get_hub_endpoint() -> str:
    """Get Hub endpoint URL."""
    return f"http://{_config['hub_host']}:{_config['hub_port']}"


def get_bypass_permission() -> bool:
    """Get whether permission checks are bypassed by default."""
    return _config.get("bypass_permission", BYPASS_PERMISSION)


def get_health_check_interval() -> float:
    """Get health check interval in seconds."""
    return _config.get("health_check_interval", HEALTH_CHECK_INTERVAL)


def get_max_consecutive_failures() -> int:
    """Get max consecutive failures before marking instance dead."""
    return _config.get("max_consecutive_failures", MAX_CONSECUTIVE_FAILURES)


def get_max_concurrent() -> int:
    """Get max concurrent CC task limit."""
    return _config.get("max_concurrent", MAX_CONCURRENT_TASKS)
