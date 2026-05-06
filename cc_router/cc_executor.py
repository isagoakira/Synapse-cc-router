"""
CCExecutor -底层 CC CLI 执行器，封装 stream-json 协议。

关键注意事项：
- result.result 是最终文本，不是 assistant content 数组
- 不要使用 --no-session-persistence（会破坏 resume）
- CC CLI 不接受 --cwd，用 subprocess 的 cwd= 参数
"""

import asyncio
import json
import shutil
from dataclasses import dataclass
from typing import Optional

from .config import get_cc_cli_path, get_timeout
from .exceptions import CCExecutorError


@dataclass
class CCResult:
    """Result from CC execution."""

    kind: str  # SUCCESS / ERROR / AUTH_CLI / AUTH_API / TIMEOUT / CRASH
    text: str  # 文本结果
    session_id: str
    cost_usd: float
    duration_ms: int
    error: str = ""


class CCExecutor:
    """
    CC CLI executor via stream-json protocol.

    Usage:
        executor = CCExecutor()
        result = await executor.run(
            task="say hi",
            workspace="/path/to/workspace",
            resume=True,
        )
    """

    def __init__(self, cc_cli_path: str = None):
        self.cc_cli_path = cc_cli_path or get_cc_cli_path()
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
        Execute a task on CC CLI.

        Args:
            task: Task description
            workspace: Working directory for CC
            session_id: Optional session ID to resume
            resume: Whether to enable session resumption
            timeout: Timeout in seconds (uses config default if None)

        Returns:
            CCResult with execution details
        """
        timeout = timeout or get_timeout()

        # Verify CC CLI exists
        cc_path = shutil.which(self.cc_cli_path)
        if not cc_path:
            raise CCExecutorError(f"CC CLI not found: {self.cc_cli_path}")

        # Build command
        # Note: --output-format=stream-json requires --verbose
        cmd = [
            cc_path,
            "--print",
            "--input-format=stream-json",
            "--output-format=stream-json",
            "--include-partial-messages",
            "--verbose",
        ]

        if resume and session_id:
            cmd.extend(["--resume", session_id])

        # Start process
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace,
        )

        # Send task
        assert self._process.stdin is not None  # created with stdin=PIPE
        input_data = {"type": "user", "message": {"role": "user", "content": task}}
        self._process.stdin.write(json.dumps(input_data).encode() + b"\n")
        await self._process.stdin.drain()

        # Read events
        result = await self._read_events(timeout)

        # Clean up
        if self._process:
            self._process = None

        return result

    async def _read_events(self, timeout: float) -> CCResult:
        """Read events from stdout until result or timeout."""
        assert self._process is not None and self._process.stdout is not None
        assert self._process.stderr is not None
        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            remaining = timeout - elapsed

            if remaining <= 0:
                return CCResult(
                    kind="TIMEOUT",
                    text="",
                    session_id="",
                    cost_usd=0.0,
                    duration_ms=int(timeout * 1000),
                    error="Task timed out",
                )

            try:
                line = await asyncio.wait_for(
                    self._process.stdout.readline(), timeout=min(remaining, 1.0)
                )
            except asyncio.TimeoutError:
                # Check if process is still running
                if self._process.returncode is not None and self._process.returncode != 0:
                    stderr = await self._process.stderr.read()
                    return CCResult(
                        kind="ERROR",
                        text="",
                        session_id="",
                        cost_usd=0.0,
                        duration_ms=int(elapsed * 1000),
                        error=(
                            stderr.decode()
                            if stderr
                            else f"Process exited with code {self._process.returncode}"
                        ),
                    )
                continue

            if not line:
                break

            try:
                event = json.loads(line.decode())
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")
            subtype = event.get("subtype", "")

            if event_type == "result":
                return CCResult(
                    kind=subtype.upper() if subtype else "SUCCESS",
                    text=event.get("result", ""),
                    session_id=event.get("session_id", ""),
                    cost_usd=event.get("total_cost_usd", 0.0),
                    duration_ms=event.get("duration_ms", 0),
                )

            elif event_type == "error":
                return CCResult(
                    kind="ERROR",
                    text="",
                    session_id=event.get("session_id", ""),
                    cost_usd=0.0,
                    duration_ms=int(elapsed * 1000),
                    error=event.get("error", "Unknown error"),
                )

            # Check for auth errors
            if event_type == "system" and subtype == "auth_error":
                return CCResult(
                    kind="AUTH_CLI",
                    text="",
                    session_id="",
                    cost_usd=0.0,
                    duration_ms=int(elapsed * 1000),
                    error="CC CLI authentication failed",
                )

        # If we get here with no result, check process status
        if self._process and self._process.returncode != 0:
            stderr = await self._process.stderr.read()
            return CCResult(
                kind="ERROR",
                text="",
                session_id="",
                cost_usd=0.0,
                duration_ms=int(elapsed * 1000),
                error=(
                    stderr.decode()
                    if stderr
                    else f"Process exited with code {self._process.returncode}"
                ),
            )

        return CCResult(
            kind="SUCCESS",
            text="",
            session_id="",
            cost_usd=0.0,
            duration_ms=int(elapsed * 1000),
        )

    async def kill(self) -> None:
        """Kill the running CC process."""
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None
