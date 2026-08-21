"""
CodexExecutor - 底层 Codex CLI 执行器，封装 `codex exec --json` JSONL 协议。

与 CCExecutor 同构，输出同样的 CCResult，供 Hub 无差别调度。

事件映射（实测 codex-cli 0.149.0）：
- {"type":"thread.started","thread_id":...}        → session_id
- {"type":"item.completed","item":{"type":"agent_message","text":...}} → 最终文本
- {"type":"turn.completed","usage":{...}}          → SUCCESS
- {"type":"turn.failed","error":{"message":...}}   → ERROR
- {"type":"error","message":"Reconnecting... x/5"} → 网络重连噪音，忽略
  （Windows 端 WebSocket 常超时回退 HTTPS，属正常路径，不能当失败）

关键注意事项：
- resume 语法：codex exec resume <session_id> --json <task>
- stdout 只收 JSONL；CLI 的 ERROR/WARN 日志走 stderr，不要合并
- ChatGPT 订阅计费，无 per-call 美元成本，cost_usd 恒 0
"""

import asyncio
import json
import shutil
from dataclasses import dataclass
from typing import Optional

from .config import get_timeout
from .exceptions import CCExecutorError


@dataclass
class CCResult:
    """Result from Codex execution (same shape as cc_executor.CCResult)."""

    kind: str  # SUCCESS / ERROR / TIMEOUT / CRASH
    text: str  # 文本结果
    session_id: str
    cost_usd: float
    duration_ms: int
    error: str = ""


class CodexExecutor:
    """
    Codex CLI executor via `codex exec --json` JSONL protocol.

    Usage:
        executor = CodexExecutor()
        result = await executor.run(
            task="say hi",
            workspace="E:\\codex_test",
        )
    """

    def __init__(self, codex_cli_path: str = "codex", bypass_permissions: bool = True):
        self.codex_cli_path = codex_cli_path
        self.bypass_permissions = bypass_permissions
        self._process: Optional[asyncio.subprocess.Process] = None

    async def run(
        self,
        task: str,
        workspace: str,
        session_id: str = None,
        resume: bool = True,
        timeout: float = None,
    ) -> CCResult:
        """
        Execute a task on Codex CLI.

        Args:
            task: Task description
            workspace: Working directory for Codex
            session_id: Optional thread_id to resume
            resume: Whether to enable session resumption
            timeout: Timeout in seconds (uses config default if None)

        Returns:
            CCResult with execution details
        """
        timeout = timeout or get_timeout()

        codex_path = shutil.which(self.codex_cli_path)
        if not codex_path:
            raise CCExecutorError(f"Codex CLI not found: {self.codex_cli_path}")

        sandbox_args = (
            ["--dangerously-bypass-approvals-and-sandbox"]
            if self.bypass_permissions
            else ["-s", "workspace-write"]
        )

        if resume and session_id:
            cmd = [
                codex_path, "exec", "resume", session_id,
                "--json", "--skip-git-repo-check", *sandbox_args, task,
            ]
        else:
            cmd = [
                codex_path, "exec",
                "--json", "--skip-git-repo-check", *sandbox_args, task,
            ]

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace,
        )

        result = await self._read_events(timeout)

        if self._process:
            self._process = None

        return result

    async def _read_events(self, timeout: float) -> CCResult:
        """Read JSONL events from stdout until turn.completed / turn.failed / timeout."""
        assert self._process is not None and self._process.stdout is not None
        assert self._process.stderr is not None
        start_time = asyncio.get_event_loop().time()

        session_id = ""
        texts: list[str] = []
        last_error = ""

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            remaining = timeout - elapsed

            if remaining <= 0:
                self._kill_process()
                return CCResult(
                    kind="TIMEOUT",
                    text="",
                    session_id=session_id,
                    cost_usd=0.0,
                    duration_ms=int(timeout * 1000),
                    error="Task timed out",
                )

            try:
                line = await asyncio.wait_for(
                    self._process.stdout.readline(), timeout=min(remaining, 1.0)
                )
            except asyncio.TimeoutError:
                if self._process.returncode is not None:
                    # Process exited without a terminal event
                    stderr = await self._process.stderr.read()
                    if self._process.returncode == 0 and texts:
                        return CCResult(
                            kind="SUCCESS",
                            text="\n".join(texts),
                            session_id=session_id,
                            cost_usd=0.0,
                            duration_ms=int(elapsed * 1000),
                        )
                    return CCResult(
                        kind="ERROR",
                        text="\n".join(texts),
                        session_id=session_id,
                        cost_usd=0.0,
                        duration_ms=int(elapsed * 1000),
                        error=(
                            stderr.decode(errors="replace")[-2000:]
                            if stderr
                            else f"Process exited with code {self._process.returncode}"
                        ),
                    )
                continue

            if not line:
                break

            try:
                event = json.loads(line.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            event_type = event.get("type", "")

            if event_type == "thread.started":
                session_id = event.get("thread_id", "")

            elif event_type == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message":
                    text = item.get("text", "")
                    if text:
                        texts.append(text)
                elif item.get("type") == "error":
                    # e.g. WebSocket→HTTPS fallback notice; record but not fatal
                    last_error = item.get("message", "")

            elif event_type == "error":
                # "Reconnecting... x/5" noise etc.; only fatal if nothing else follows
                last_error = event.get("message", last_error)

            elif event_type == "turn.completed":
                return CCResult(
                    kind="SUCCESS",
                    text="\n".join(texts),
                    session_id=session_id,
                    cost_usd=0.0,
                    duration_ms=int(elapsed * 1000),
                )

            elif event_type == "turn.failed":
                err = event.get("error") or {}
                return CCResult(
                    kind="ERROR",
                    text="\n".join(texts),
                    session_id=session_id,
                    cost_usd=0.0,
                    duration_ms=int(elapsed * 1000),
                    error=err.get("message", "turn.failed"),
                )

        # stdout closed without terminal event
        if texts:
            return CCResult(
                kind="SUCCESS",
                text="\n".join(texts),
                session_id=session_id,
                cost_usd=0.0,
                duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
            )
        return CCResult(
            kind="ERROR",
            text="",
            session_id=session_id,
            cost_usd=0.0,
            duration_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
            error=last_error or "Stream ended without turn.completed",
        )

    def _kill_process(self) -> None:
        if self._process and self._process.returncode is None:
            try:
                self._process.kill()
            except ProcessLookupError:
                pass
