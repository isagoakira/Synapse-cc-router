"""
Environment detector — 自动检测本地环境中的 CLI、路径、配置。
"""

import importlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CLIInfo:
    """Detected CLI tool info."""

    name: str
    path: Optional[str]
    version: Optional[str]
    available: bool


@dataclass
class EnvInfo:
    """Full environment detection result."""

    python_version: str
    cc_cli: CLIInfo
    hermes: CLIInfo
    openclaw: CLIInfo
    mcp_installed: bool
    project_dir: str
    workspace_dirs: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)


def detect() -> EnvInfo:
    """Run full environment detection."""
    info = EnvInfo(
        python_version=sys.version.split()[0],
        cc_cli=_detect_cli("claude", ["--version"]),
        hermes=_detect_cli("hermes", ["--version"]),
        openclaw=_detect_cli("openclaw", ["--version"]),
        mcp_installed=_check_mcp(),
        project_dir=str(Path(__file__).parent.parent.parent.resolve()),
    )

    # Detect workspace dirs
    home = Path.home()
    candidates = {
        "home": str(home),
        "desktop": str(home / "Desktop"),
        "projects": str(home / "Desktop" / "file" / "Agent&Development"),
    }
    for name, path in candidates.items():
        p = Path(path)
        if p.exists():
            info.workspace_dirs[name] = str(p)

    # Detect existing config
    config_paths = [
        Path.cwd() / "cc_router_config.json",
        Path.cwd() / "cc_router_config.local.json",
        Path.home() / ".cc_router" / "config.json",
    ]
    for cp in config_paths:
        if cp.exists():
            try:
                with open(cp) as f:
                    info.config = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

    return info


def _detect_cli(name: str, version_args: list[str]) -> CLIInfo:
    """Detect a CLI tool."""
    path = shutil.which(name)
    version = None
    available = path is not None

    if path:
        try:
            r = subprocess.run(
                [path] + version_args,
                capture_output=True,
                text=True,
                timeout=10,
            )
            version = (r.stdout or r.stderr).strip()[:60]
        except (subprocess.TimeoutExpired, OSError):
            pass

    return CLIInfo(name=name, path=path, version=version, available=available)


def _check_mcp() -> bool:
    """Check if mcp Python package is installed."""
    try:
        importlib.import_module("mcp")
        return True
    except ImportError:
        return False


def print_report(info: EnvInfo) -> None:
    """Print a formatted environment report."""
    print()
    print("  ╭──────────────────────────────────────────╮")
    print("  │        CC Router 环境检测报告             │")
    print("  ├──────────────────────────────────────────┤")
    print(f"  │ Python:      {info.python_version:<30s}│")
    print(f"  │ 项目目录:    {_shorten(info.project_dir, 28):<28s}│")

    for cli in [info.cc_cli, info.hermes, info.openclaw]:
        icon = "✓" if cli.available else "✗"
        path = cli.path or "(not found)"
        print(f"  │ {icon} {cli.name:<11s} {_shorten(path, 28):<28s}│")

    mcp_icon = "✓" if info.mcp_installed else "✗"
    mcp_status = "installed" if info.mcp_installed else "not installed"
    print(f"  │ {mcp_icon} mcp          {mcp_status:<28s}│")
    print("  │                                                          │")

    if info.workspace_dirs:
        print("  │ 发现工作区:                                       │")
        for name, path in info.workspace_dirs.items():
            print(f"  │   {name:<12s} {_shorten(path, 26):<26s}│")

    print("  ╰──────────────────────────────────────────╯")
    print()


def _shorten(s: str, maxlen: int) -> str:
    return s if len(s) <= maxlen else "..." + s[-(maxlen - 3) :]
