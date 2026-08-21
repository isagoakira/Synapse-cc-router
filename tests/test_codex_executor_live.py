"""Live smoke test: CodexExecutor hello world. Run on Windows venv python."""
import asyncio
import sys

from cc_router.codex_executor import CodexExecutor


async def main():
    ex = CodexExecutor()
    r = await ex.run(
        task="Reply with exactly: hello from executor",
        workspace=r"E:\codex_test",
        timeout=180,
    )
    print(f"kind={r.kind}")
    print(f"text={r.text!r}")
    print(f"session_id={r.session_id}")
    print(f"duration_ms={r.duration_ms}")
    print(f"error={r.error!r}")
    assert r.kind == "SUCCESS", r.error
    assert "hello from executor" in r.text
    assert r.session_id

    # resume test
    r2 = await ex.run(
        task="Reply with exactly: resumed ok",
        workspace=r"E:\codex_test",
        session_id=r.session_id,
        resume=True,
        timeout=180,
    )
    print(f"[resume] kind={r2.kind} text={r2.text!r} sid={r2.session_id} err={r2.error!r}")
    assert r2.kind == "SUCCESS", r2.error
    print("SMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())
