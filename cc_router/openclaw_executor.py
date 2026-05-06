"""
OpenClawExecutor — 子进程模式调用本地 OpenClaw Agent。

通过 openclaw agent --local --message "task" --json 以子进程方式执行，
解析 JSON 输出提取响应文本。

用法:
    executor = OpenClawExecutor()
    result = await executor.run(task="写一段Python代码")
"""

import asyncio
import json
import shutil
from dataclasses import dataclass
from typing import Optional


@dataclass
class OpenClawResult:
    """Result from OpenClaw execution."""

    kind: str  # SUCCESS / ERROR / TIMEOUT / CRASH
    text: str  # 响应文本
    session_id: str
    duration_ms: int
    error: str = ""


class OpenClawExecutor:
    """
    OpenClaw Agent 子进程执行器。

    通过 openclaw agent --local --message "task" --json --session-id <id>
    以单次查询模式调用本地 OpenClaw Agent，解析 JSON 输出。
    """

    def __init__(self, openclaw_path: str = None):
        self.openclaw_path = openclaw_path or shutil.which("openclaw") or "openclaw"
        self._process: Optional[asyncio.subprocess.Process] = None

    async def run(
        self,
        task: str,
        timeout: float = 300.0,
        session_id: str = None,
    ) -> OpenClawResult:
        """
        执行一个任务 on OpenClaw Agent。

        Args:
            task: 任务描述
            timeout: 超时秒数
            session_id: 可选 session ID（默认自动生成）

        Returns:
            OpenClawResult
        """
        import uuid

        sid = session_id or f"cc_router_{uuid.uuid4().hex[:8]}"

        # Verify openclaw exists
        oc_path = shutil.which(self.openclaw_path)
        if not oc_path:
            oc_path = self.openclaw_path
            if not shutil.which(oc_path):
                from .exceptions import AdapterError

                raise AdapterError(f"OpenClaw CLI not found: {self.openclaw_path}")

        # Build command
        cmd = [oc_path, "agent", "--local", "--message", task, "--json", "--session-id", sid]

        start_time = asyncio.get_event_loop().time()

        # Start process
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                self._process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            self._process.kill()
            await self._process.wait()
            elapsed = asyncio.get_event_loop().time() - start_time
            return OpenClawResult(
                kind="TIMEOUT",
                text="",
                session_id=sid,
                duration_ms=int(elapsed * 1000),
                error=f"OpenClaw task timed out after {timeout}s",
            )

        elapsed = asyncio.get_event_loop().time() - start_time

        rc = self._process.returncode or 0
        if rc != 0:
            err_text = stderr.decode() if stderr else f"exit code {rc}"
            return OpenClawResult(
                kind="CRASH" if rc < 0 else "ERROR",
                text="",
                session_id=sid,
                duration_ms=int(elapsed * 1000),
                error=err_text[:500],
            )

        output = stdout.decode() if stdout else ""
        return self._parse_output(output, sid, elapsed)

    def _parse_output(self, output: str, session_id: str, elapsed: float) -> OpenClawResult:
        """Parse JSON output from OpenClaw agent command."""
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            return OpenClawResult(
                kind="ERROR",
                text="",
                session_id=session_id,
                duration_ms=int(elapsed * 1000),
                error=f"Could not parse OpenClaw JSON output: {output[:300]}",
            )

        # Extract text from payloads
        payloads = data.get("payloads", [])
        text = ""
        if payloads:
            text = payloads[0].get("text", "")

        # Extract duration
        meta = data.get("meta", {})
        duration_ms = meta.get("durationMs", int(elapsed * 1000))

        # Extract session ID from agent meta
        agent_meta = meta.get("agentMeta", {})
        sid = agent_meta.get("sessionId", session_id)

        # Check for abort/error
        aborted = meta.get("aborted", False)
        stop_reason = meta.get("stopReason", "")

        if aborted:
            return OpenClawResult(
                kind="ERROR",
                text=text,
                session_id=sid,
                duration_ms=duration_ms,
                error="Agent aborted",
            )

        if not text and stop_reason != "stop":
            return OpenClawResult(
                kind="ERROR",
                text="",
                session_id=sid,
                duration_ms=duration_ms,
                error=f"Agent stopped with reason: {stop_reason}",
            )

        return OpenClawResult(
            kind="SUCCESS",
            text=text,
            session_id=sid,
            duration_ms=duration_ms,
        )

    async def kill(self) -> None:
        """Kill the running OpenClaw process."""
        if self._process:
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
            except (ProcessLookupError, OSError):
                pass
            self._process = None
