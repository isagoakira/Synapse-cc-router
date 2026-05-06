"""
UniversalRouter - 根据 tag/path/capability 路由任务到合适的 CC 实例。
"""

import asyncio
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .cc_registry import CCRegistry
from .exceptions import RoutingError


class RoutingStrategy(Enum):
    TAG_MATCH = "tag_match"
    PATH_MATCH = "path_match"
    CAPABILITY = "capability"
    ROUND_ROBIN = "round_robin"
    DEFAULT = "default"


@dataclass
class RouteResult:
    """Result of a routing decision."""

    cc_id: str
    strategy: RoutingStrategy
    reason: str
    workspace: str


# capability → 关键词映射
CAPABILITY_KEYWORDS = {
    "code": ["代码", "code", "implement", "bug", "refactor", "函数", "class", "import"],
    "research": ["论文", "research", "survey", "文献", "arxiv", "paper"],
    "paper": ["写论文", "paper", "writing", "introduction", "related work", "摘要"],
    "ml": ["训练", "training", "model", "epoch", "loss", "实验", "neural", "network"],
    "debug": ["debug", "错误", "crash", "traceback", "segfault", "exception", "bug"],
    "general": [],  # 默认
}


class UniversalRouter:
    """
    Universal routing - not bound to any specific Agent.

    Strategy priority:
    1. Explicit tag parameter
    2. @tag in message
    3. Workspace path matching
    4. Capability keyword matching
    5. Round-robin idle instances
    6. First available instance (fallback)
    """

    def __init__(self, cc_registry: CCRegistry):
        self.cc_registry = cc_registry
        self._round_robin_index = 0
        self._lock = asyncio.Lock()

        # Regex patterns
        self.TAG_PAT = re.compile(r"^@(\w+)\s+(.+)$")
        self.PATH_PAT = re.compile(r"([A-Z]:[/\\](?:[^\\/:*?\"<>|\r\n]+[/\\]?)+)")

    async def route(
        self,
        message: str,
        tag: str = None,
        capability: list[str] = None,
    ) -> RouteResult:
        """
        Make routing decision (async for future extensibility).

        Args:
            message: Task message text
            tag: Optional explicit tag
            capability: Optional explicit capability list

        Returns:
            RouteResult with cc_id and strategy info
        """
        # 1. Explicit tag parameter
        if tag:
            inst = self.cc_registry.get_by_tag(tag)
            if inst and inst.status in ("idle", "busy"):
                return RouteResult(
                    cc_id=inst.cc_id,
                    strategy=RoutingStrategy.TAG_MATCH,
                    reason=f"tag={tag}",
                    workspace=inst.workspace,
                )

        # 2. @tag in message
        m = self.TAG_PAT.match(message.strip())
        if m:
            tag_in_msg = m.group(1)
            inst = self.cc_registry.get_by_tag(tag_in_msg)
            if inst and inst.status in ("idle", "busy"):
                return RouteResult(
                    cc_id=inst.cc_id,
                    strategy=RoutingStrategy.TAG_MATCH,
                    reason=f"@tag={tag_in_msg}",
                    workspace=inst.workspace,
                )

        # 3. Workspace path matching
        path_m = self.PATH_PAT.search(message)
        if path_m:
            path = Path(path_m.group(1))
            for inst in self.cc_registry.list_by_status("idle"):
                inst_path = Path(inst.workspace)
                if path in inst_path.parents or inst_path in path.parents:
                    return RouteResult(
                        cc_id=inst.cc_id,
                        strategy=RoutingStrategy.PATH_MATCH,
                        reason=f"workspace={inst.workspace}",
                        workspace=inst.workspace,
                    )

        # 4. Explicit capability
        if capability:
            for cap in capability:
                for inst in self.cc_registry.list_by_status("idle"):
                    if cap in inst.capability:
                        return RouteResult(
                            cc_id=inst.cc_id,
                            strategy=RoutingStrategy.CAPABILITY,
                            reason=f"cap={cap}",
                            workspace=inst.workspace,
                        )

        # 5. Keyword matching in message
        msg_lower = message.lower()
        for cap, keywords in CAPABILITY_KEYWORDS.items():
            if cap == "general":
                continue
            if any(kw in msg_lower for kw in keywords):
                for inst in self.cc_registry.list_by_status("idle"):
                    if cap in inst.capability:
                        return RouteResult(
                            cc_id=inst.cc_id,
                            strategy=RoutingStrategy.CAPABILITY,
                            reason=f"keyword→{cap}",
                            workspace=inst.workspace,
                        )

        # 6. Round-robin idle
        idle = self.cc_registry.list_by_status("idle")
        if idle:
            async with self._lock:
                idx = self._round_robin_index % len(idle)
                self._round_robin_index += 1
                inst = idle[idx]
            return RouteResult(
                cc_id=inst.cc_id,
                strategy=RoutingStrategy.ROUND_ROBIN,
                reason=f"round_robin[{idx}]",
                workspace=inst.workspace,
            )

        # 7. Fallback: any available instance
        all_instances = self.cc_registry.list_all()
        available = [i for i in all_instances if i.status in ("idle", "busy")]
        if available:
            return RouteResult(
                cc_id=available[0].cc_id,
                strategy=RoutingStrategy.DEFAULT,
                reason="first_available",
                workspace=available[0].workspace,
            )

        raise RoutingError("No available CC instance")
