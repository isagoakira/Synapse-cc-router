"""
Config writer — 生成 CC Router 配置文件。
"""

import json
import os
from pathlib import Path
from typing import Optional

from .env_detector import EnvInfo


def generate_config(
    info: EnvInfo,
    enable_hermes: bool = False,
    enable_openclaw: bool = False,
    hub_port: int = 8765,
    timeout: float = 300.0,
    log_level: str = "INFO",
) -> dict:
    """Generate a CC Router config dict from detected environment."""
    config = {
        "cc_cli_path": info.cc_cli.path or "claude",
        "timeout": timeout,
        "hub_host": "localhost",
        "hub_port": hub_port,
        "log_level": log_level,
        "max_cc_instances": 5,
    }

    # CC instances
    cc_instances = []
    if info.cc_cli.available:
        cc_instances.append(
            {
                "cc_id": "cc_default",
                "workspace": info.project_dir,
                "tags": ["default", "code"],
                "capabilities": ["code", "debug", "general"],
                "cc_cli_path": info.cc_cli.path,
            }
        )

    if info.workspace_dirs.get("projects"):
        cc_instances.append(
            {
                "cc_id": "cc_research",
                "workspace": info.workspace_dirs["projects"],
                "tags": ["research", "paper"],
                "capabilities": ["research", "paper"],
                "cc_cli_path": info.cc_cli.path or "claude",
            }
        )

    if cc_instances:
        config["cc_instances"] = cc_instances

    # Adapters
    adapters = {}

    if enable_hermes and info.hermes.available:
        adapters["hermes"] = {
            "type": "hermes",
            "agent_id": "hermes_gateway",
            "hermes_path": info.hermes.path,
            "auto_connect": True,
        }

    if enable_openclaw and info.openclaw.available:
        adapters["openclaw"] = {
            "type": "openclaw",
            "agent_id": "openclaw_main",
            "openclaw_path": info.openclaw.path,
            "auto_connect": True,
        }

    if adapters:
        config["adapters"] = adapters

    # MCP tools
    config["mcp_tools"] = [
        "feishu_notify",
        "forward_to_agent",
        "read_training_log",
        "query_experiment_data",
    ]

    return config


def write_config(
    config: dict,
    output_path: Optional[str] = None,
) -> str:
    """Write config to JSON file."""
    if output_path is None:
        output_path = str(Path.cwd() / "cc_router_config.json")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    return output_path


def write_env_script(info: EnvInfo, output_dir: Optional[str] = None) -> str:
    """Write a shell script to activate the CC Router environment."""
    if output_dir is None:
        output_dir = str(Path.cwd())

    script_path = os.path.join(output_dir, "cc_router_env.sh")

    lines = [
        "#!/bin/bash",
        "# CC Router environment setup — auto-generated",
        f'export CC_ROUTER_HOME="{info.project_dir}"',
        f'export CC_CLI_PATH="{info.cc_cli.path or "claude"}"',
        "",
        "# Add to PATH if needed",
        '# export PATH="$CC_ROUTER_HOME:$PATH"',
        "",
        "# Run hub:",
        "#   python -m cc_router.installer.cli_wizard start",
        "",
    ]

    with open(script_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    os.chmod(script_path, 0o755)
    return script_path
