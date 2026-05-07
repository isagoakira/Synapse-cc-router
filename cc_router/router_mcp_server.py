"""
RouterMCPServer — Built-in MCP Bridge for CC instances.

CC instances connect via stdio to call these tools through the Hub's EventBus.
"""

from __future__ import annotations

import glob as glob_module
import logging
import os
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

from .router_hub import get_global_hub

logger = logging.getLogger(__name__)


# ── Pydantic Models ─────────────────────────────────────────────────


class FeishuNotifyInput(BaseModel):
    """Input model for feishu_notify tool."""

    text: str = Field(..., min_length=1, description="Notification text content")
    chat_id: str | None = Field(None, description="Target chat ID (optional)")


class ForwardToAgentInput(BaseModel):
    """Input model for forward_to_agent tool."""

    event_type: str = Field(
        "partial",
        description="Event type (partial, progress, log, result)",
    )
    content: str = Field(..., min_length=1, description="Event content")
    task_id: str = Field(..., min_length=1, description="Associated task ID")


class ReadTrainingLogInput(BaseModel):
    """Input model for read_training_log tool."""

    workspace: str = Field(".", description="Workspace directory path")
    pattern: str = Field("*.log", description="Glob pattern for log files")


class QueryExperimentDataInput(BaseModel):
    """Input model for query_experiment_data tool."""

    experiment: str = Field(..., min_length=1, description="Experiment name/ID")
    metric: str | None = Field(None, description="Metric name (optional)")


# ── RouterMCPBridge ─────────────────────────────────────────────────


class RouterMCPBridge:
    """
    Bridge between MCP tool calls and Hub's EventBus.

    Provides tools for CC instances to interact with the Hub:
    - feishu_notify: Send Feishu notification
    - forward_to_agent: Forward event to caller Agent
    - read_training_log: Read ML training logs
    - query_experiment_data: Query experiment results
    """

    def __init__(self) -> None:
        self._task_context: dict[str, dict[str, str]] = {}
        self._tools: dict[
            str, Callable[[dict[str, Any], dict[str, str]], Awaitable[dict[str, Any]]]
        ] = {
            "feishu_notify": self._feishu_notify,
            "forward_to_agent": self._forward_to_agent,
            "read_training_log": self._read_training_log,
            "query_experiment_data": self._query_experiment_data,
        }

    # ── Task Context Management ────────────────────────────────────

    def set_task_context(self, task_id: str, cc_id: str, caller_agent_id: str) -> None:
        """Set task context before CC execution."""
        self._task_context[task_id] = {"cc_id": cc_id, "agent_id": caller_agent_id}

    def get_task_context(self, task_id: str) -> dict[str, str]:
        """Get task context during CC execution."""
        return self._task_context.get(task_id, {})

    def clear_task_context(self, task_id: str) -> None:
        """Clear task context after CC execution."""
        self._task_context.pop(task_id, None)

    # ── Main Tool API ──────────────────────────────────────────────

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a tool by name with arguments.

        Args:
            name: Tool name (must be one of the registered tools).
            arguments: Tool-specific arguments.
            context: Execution context dict (may contain ``task_id``).

        Returns:
            Tool result dict with at least a ``"status"`` key.

        Raises:
            ValueError: If the tool name is unknown.
        """
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")

        task_id = context.get("task_id", "") if context else ""
        task_meta = self.get_task_context(task_id)

        return await self._tools[name](arguments, task_meta)

    # ── Individual Tool Handlers ───────────────────────────────────

    async def _feishu_notify(
        self,
        args: dict[str, Any],
        task_meta: dict[str, str],
    ) -> dict[str, Any]:
        """Send a Feishu notification."""
        parsed = FeishuNotifyInput(**args)
        logger.info("Feishu notify: %s", parsed.text[:100])
        return {"status": "ok", "message": "Notification sent"}

    async def _forward_to_agent(
        self,
        args: dict[str, Any],
        task_meta: dict[str, str],
    ) -> dict[str, Any]:
        """Forward an event to the caller Agent via EventBus."""
        parsed = ForwardToAgentInput(**args)

        hub = get_global_hub()
        agent_id = task_meta.get("agent_id", "")

        if agent_id:
            await hub.event_bus.publish(
                agent_id,
                parsed.task_id,
                {"type": parsed.event_type, "content": parsed.content},
            )

        return {"status": "ok", "message": "forwarded"}

    async def _read_training_log(
        self,
        args: dict[str, Any],
        task_meta: dict[str, str],
    ) -> dict[str, Any]:
        """Read ML training log files from workspace via glob."""
        parsed = ReadTrainingLogInput(**args)

        search_path = os.path.join(parsed.workspace, parsed.pattern)
        log_files = glob_module.glob(search_path)

        logs: list[dict[str, Any]] = []
        for filepath in log_files[:20]:  # limit to 20 files per call
            try:
                with open(filepath, "r") as f:
                    content = f.read(50000)  # limit to 50 KB per file
                logs.append(
                    {
                        "path": filepath,
                        "size": os.path.getsize(filepath),
                        "content": content,
                    }
                )
            except (IOError, OSError) as exc:
                logs.append({"path": filepath, "error": str(exc)})

        return {
            "status": "ok",
            "logs": logs,
            "message": f"Read {len(logs)} log file(s) from {parsed.workspace}",
        }

    async def _query_experiment_data(
        self,
        args: dict[str, Any],
        task_meta: dict[str, str],
    ) -> dict[str, Any]:
        """Query experiment results by searching for experiment data files."""
        parsed = QueryExperimentDataInput(**args)

        # Determine search directories from task context or CWD
        search_dirs = [os.getcwd()]
        if task_meta.get("cc_id"):
            search_dirs.append(f"/tmp/{task_meta['cc_id']}")

        found_files: list[dict[str, Any]] = []
        for base_dir in search_dirs:
            if not os.path.isdir(base_dir):
                continue
            # Look for files matching the experiment name
            for ext in ("*.json", "*.csv", "*.yaml", "*.yml", "*.log"):
                pattern = os.path.join(base_dir, f"{parsed.experiment}_{ext}")
                for filepath in glob_module.glob(pattern):
                    try:
                        with open(filepath, "r") as f:
                            content = f.read(20000)
                        found_files.append(
                            {
                                "path": filepath,
                                "size": os.path.getsize(filepath),
                                "content_preview": content[:2000],
                            }
                        )
                    except (IOError, OSError) as exc:
                        found_files.append({"path": filepath, "error": str(exc)})

        if found_files:
            return {
                "status": "ok",
                "data": found_files,
                "count": len(found_files),
                "message": f"Found {len(found_files)} file(s) for experiment '{parsed.experiment}'",
            }

        # If metric filter is specified, return the filter result
        if parsed.metric:
            return {
                "status": "ok",
                "data": None,
                "message": f"Metric '{parsed.metric}' not found for experiment '{parsed.experiment}'",
            }

        return {
            "status": "ok",
            "data": None,
            "count": 0,
            "message": f"No data files found for experiment '{parsed.experiment}'",
        }

    def list_tools(self) -> list[dict[str, Any]]:
        """List available tools with their input schemas."""
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
