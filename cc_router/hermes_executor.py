"""
HermesExecutor — 子进程模式调用本地 Hermes Agent。

通过 hermes chat -q "task" -Q 以子进程方式执行任务，
解析输出提取响应文本和 session_id。

用法:
    executor = HermesExecutor()
    result = await executor.run(task="写一段Python代码")
"""

import asyncio
import re
import shutil
from dataclasses import dataclass
from typing import Optional


@dataclass
class HermesResult:
    """Result from Hermes execution."""

    kind: str  # SUCCESS / ERROR / TIMEOUT / CRASH
    text: str  # 响应文本
    session_id: str
    duration_ms: int
    error: str = ""


# 响应框: 提取 ╭─ ⚕ Hermes ───...╮ 之后到 session_id: 之间的内容
RESPONSE_BOX_RE = re.compile(r"╭─[^╮]*╮\s*\n(.*?)(?=\n\s*session_id:\s|\Z)", re.DOTALL)

# session_id 行
SESSION_ID_RE = re.compile(r"session_id:\s*(\S+)")


class HermesExecutor:
    """
    Hermes Agent 子进程执行器。

    通过 hermes chat -q 以单次查询模式调用本地 Hermes Agent，
    解析安静模式 (-Q) 的输出提取响应文本。
    """

    def __init__(self, hermes_path: str = None):
        self.hermes_path = hermes_path or shutil.which("hermes") or "hermes"
        self._process: Optional[asyncio.subprocess.Process] = None

    async def run(
        self,
        task: str,
        timeout: float = 300.0,
    ) -> HermesResult:
        """
        执行一个任务 on Hermes Agent。

        Args:
            task: 任务描述
            timeout: 超时秒数

        Returns:
            HermesResult
        """
        # Verify hermes exists
        hermes_path = shutil.which(self.hermes_path)
        if not hermes_path:
            hermes_path = self.hermes_path
            if not shutil.which(hermes_path):
                from .exceptions import AdapterError

                raise AdapterError(f"Hermes CLI not found: {self.hermes_path}")

        # Build command
        cmd = [hermes_path, "chat", "-q", task, "-Q"]

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
            return HermesResult(
                kind="TIMEOUT",
                text="",
                session_id="",
                duration_ms=int(elapsed * 1000),
                error=f"Hermes task timed out after {timeout}s",
            )

        elapsed = asyncio.get_event_loop().time() - start_time

        rc = self._process.returncode or 0
        if rc != 0:
            err_text = stderr.decode() if stderr else f"exit code {rc}"
            return HermesResult(
                kind="CRASH" if rc < 0 else "ERROR",
                text="",
                session_id="",
                duration_ms=int(elapsed * 1000),
                error=err_text[:500],
            )

        output = stdout.decode() if stdout else ""
        return self._parse_output(output, elapsed)

    def _parse_output(self, output: str, elapsed: float) -> HermesResult:
        """
        解析 Hermes 安静模式输出。

        输出格式:
            ╭─ ⚕ Hermes ───────────────────────────────────────────────╮
            response text here
            ╰──────────────────────────────────────────────────────────╯

            session_id: 20260506_231720_6d25b7
        """
        # Extract response from box
        text = ""
        m = RESPONSE_BOX_RE.search(output)
        if m:
            text = m.group(1).strip()

        # Extract session_id
        session_id = ""
        m = SESSION_ID_RE.search(output)
        if m:
            session_id = m.group(1)

        if not text and not session_id:
            # Maybe it's an error or unexpected format
            return HermesResult(
                kind="ERROR",
                text="",
                session_id="",
                duration_ms=int(elapsed * 1000),
                error=f"Could not parse Hermes output: {output[:300]}",
            )

        return HermesResult(
            kind="SUCCESS",
            text=text,
            session_id=session_id,
            duration_ms=int(elapsed * 1000),
        )

    async def kill(self) -> None:
        """Kill the running Hermes process."""
        if self._process:
            try:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self._process.kill()
            except (ProcessLookupError, OSError):
                # Process already exited
                pass
            self._process = None
