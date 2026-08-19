#!/usr/bin/env python3
"""
live_e2e.py — CC Router 对线端到端测试（WSL 端执行）

对运行中的 Hub (Windows 127.0.0.1:8765) 执行 live_e2e_plan.md 中的 A–G 组用例。
H 组（重启/持久化）默认跳过，需 --with-restart 且手动配合。

用法：
    python3 tests/live_e2e.py              # 全量 A–G（real 模式）
    python3 tests/live_e2e.py --mode fake  # Router 用 fake_claude.bat 时的确定性模式
    python3 tests/live_e2e.py -k C         # 只跑 C 组（路由）
    python3 tests/live_e2e.py -v           # 打印失败 traceback

模式说明：
    real — config cc_cli_path 指向真实 claude CLI。结果文本由 LLM 生成，
           路由断言只看 cc_id；workspace 断言用「让 claude 自报 cwd」探测。
    fake — config cc_cli_path 指向 fake_claude.bat。结果文本确定性
           （[FAKE-CC-X] ... workspace=<cwd>），可做严格文本断言。

退出码：0 = 全过，1 = 有失败。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Callable, Optional

HOST = os.environ.get("CC_ROUTER_HOST", "127.0.0.1")
PORT = os.environ.get("CC_ROUTER_PORT", "8765")
BASE = f"http://{HOST}:{PORT}"
PS_WRAP = os.environ.get("CC_PS_WRAP", r"E:\cc_router_venv\cc_http.ps1")
BODY_FILE_WSL = "/mnt/c/Users/11436/AppData/Local/Temp/cc_e2e_body.json"
BODY_FILE_WIN = r"C:\Users\11436\AppData\Local\Temp\cc_e2e_body.json"

POLL_INTERVAL = 1.0
TASK_DEADLINE = 180.0  # real 模式 LLM 延迟偶尔 >60s，放宽避免误报

VERBOSE = False
MODE = "real"  # real | fake


# ── HTTP 桥 ──────────────────────────────────────────────────────────


class HttpError(RuntimeError):
    """PowerShell 包装层返回非 0（通常是 HTTP 4xx/5xx）。"""


def http(method: str, path: str, payload: Optional[dict] = None,
         raw_body: Optional[bytes] = None) -> dict:
    url = f"{BASE}{path}"
    cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass",
           "-File", PS_WRAP, "-Method", method, "-Url", url]
    if raw_body is not None:
        with open(BODY_FILE_WSL, "wb") as f:
            f.write(raw_body)
        cmd += ["-BodyFile", BODY_FILE_WIN]
    elif payload is not None:
        with open(BODY_FILE_WSL, "wb") as f:
            f.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        cmd += ["-BodyFile", BODY_FILE_WIN]

    proc = subprocess.run(cmd, capture_output=True, timeout=90)
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip()
        raise HttpError(f"rc={proc.returncode}: {err[:300]}")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise HttpError(f"non-JSON response: {out[:200]}")


def submit(task: str, agent_id: str = "e2e", tag: Optional[str] = None,
           capability: Optional[list] = None,
           workspace: Optional[str] = None,
           timeout: float = 120.0) -> str:
    payload: dict[str, Any] = {"agent_id": agent_id, "task": task,
                               "timeout": timeout}
    if tag:
        payload["tag"] = tag
    if capability:
        payload["capability"] = capability
    if workspace:
        payload["workspace"] = workspace
    resp = http("POST", "/api/tasks", payload=payload)
    assert resp.get("status") == "ok", f"submit rejected: {resp}"
    return resp["task_id"]


def wait_done(task_id: str, deadline: float = TASK_DEADLINE) -> dict:
    t0 = time.time()
    while time.time() - t0 < deadline:
        resp = http("GET", f"/api/tasks/{task_id}")
        if resp.get("status") in ("done", "error"):
            return resp
        time.sleep(POLL_INTERVAL)
    raise AssertionError(f"task {task_id} not done within {deadline}s "
                         f"(last={resp})")


def run_task(task: str, **kw) -> dict:
    return wait_done(submit(task, **kw))


# ── 断言辅助 ─────────────────────────────────────────────────────────


def ws_of(task: dict) -> str:
    m = re.search(r"workspace=([^\s]+)$", task.get("result") or "")
    return m.group(1) if m else ""


# ── 用例 ─────────────────────────────────────────────────────────────


def a1_health():
    h = http("GET", "/api/health")
    assert h["status"] == "ok"
    assert h["cc_instances"]["count"] == 3, h["cc_instances"]
    assert h["cc_instances"]["by_status"].get("idle") == 3, h["cc_instances"]
    return f"instances=3 idle=3 tasks={h['tasks']['count']}"


def b1_async_lifecycle():
    tid = submit("e2e neutral ping alpha beta gamma")
    assert tid
    t = wait_done(tid)
    assert t["status"] == "done", t
    assert t["cc_id"], t
    if MODE == "fake":
        assert "[FAKE-CC-" in (t["result"] or ""), t["result"]
    else:
        # real claude：只要求有响应文本（偶发空 result 另见已知问题）
        assert t["result"], "empty result from real claude"
    return f"task_id={tid} cc={t['cc_id']}"


def b2_sync_run():
    t = run_task("e2e neutral ping delta epsilon zeta")
    assert t["status"] == "done" and not t["error"], t
    return f"cc={t['cc_id']}"


def c1_explicit_tag():
    t = run_task("e2e neutral ping", tag="ml")
    assert t["cc_id"] == "cc_ml", t["cc_id"]
    if MODE == "fake":
        assert "[FAKE-CC-ML]" in t["result"], t["result"]
    return t["cc_id"]


def c2_at_tag_in_message():
    t = run_task("e2e please handle this @code thanks")
    assert t["cc_id"] == "cc_code", t["cc_id"]
    return t["cc_id"]


def c3_explicit_capability():
    t = run_task("e2e neutral ping", capability=["training"])
    assert t["cc_id"] == "cc_ml", t["cc_id"]
    return t["cc_id"]


def c4_keyword_capability():
    t = run_task("e2e 请训练这个 model 并观察 loss 曲线")
    assert t["cc_id"] == "cc_ml", t["cc_id"]
    return t["cc_id"]


def c5_unknown_tag_fallback():
    t = run_task("e2e neutral ping", tag="nonexistent")
    assert t["status"] == "done"
    assert t["cc_id"] in ("cc_code", "cc_ml", "cc_paper"), t["cc_id"]
    return f"fell through to {t['cc_id']}"


def c6_round_robin_rotation():
    # 两个连续中性任务，round-robin 索引递增 → cc 应不同
    t1 = run_task("e2e neutral ping one")
    t2 = run_task("e2e neutral ping two")
    assert t1["cc_id"] != t2["cc_id"], \
        f"expected rotation, got {t1['cc_id']} twice"
    return f"{t1['cc_id']} -> {t2['cc_id']}"


def c7_tag_beats_keyword():
    t = run_task("e2e 请训练 model 观察 loss", tag="paper")
    assert t["cc_id"] == "cc_paper", t["cc_id"]
    return t["cc_id"]


CWD_PROBE = ("Reply with ONLY the absolute path of your current working "
             "directory. No other text, no punctuation.")


def d1_workspace_override():
    if MODE == "fake":
        t = run_task("e2e neutral ping", tag="code",
                     workspace=r"E:\fake_cc_workspaces\paper")
        assert t["status"] == "done", t
        assert ws_of(t).endswith("\\paper"), ws_of(t)
        return f"workspace={ws_of(t)}"
    t = run_task(CWD_PROBE, tag="code",
                 workspace=r"E:\fake_cc_workspaces\paper")
    assert t["status"] == "done" and t["result"], t
    assert "paper" in t["result"].lower(), t["result"][:200]
    return f"cwd={t['result'][:60]}"


def d2_default_workspace():
    if MODE == "fake":
        t = run_task("e2e neutral ping", tag="code")
        assert ws_of(t).endswith("\\code"), ws_of(t)
        return f"workspace={ws_of(t)}"
    t = run_task(CWD_PROBE, tag="code")
    assert t["status"] == "done" and t["result"], t
    r = t["result"].lower().replace("\\", "/")
    assert "code" in r and "paper" not in r and "/ml" not in r, \
        t["result"][:200]
    return f"cwd={t['result'][:60]}"


def e1_agent_attribution():
    tid = submit("e2e neutral ping", agent_id="e2e-rokid")
    t = wait_done(tid)
    assert t["caller_agent_id"] == "e2e-rokid", t["caller_agent_id"]
    return f"caller={t['caller_agent_id']}"


def e2e2_list_filter():
    tid = submit("e2e neutral ping", agent_id="e2e-rokid")
    wait_done(tid)
    resp = http("GET", "/api/tasks?agent_id=e2e-rokid")
    assert resp["count"] >= 1, resp
    ids = [t["task_id"] for t in resp["tasks"]]
    assert tid in ids, ids
    assert all(t["caller_agent_id"] == "e2e-rokid" for t in resp["tasks"])
    return f"count={resp['count']}"


def f1_unknown_task_id():
    try:
        http("GET", "/api/tasks/e2e-does-not-exist")
    except HttpError as e:
        assert "404" in str(e) or "Not Found" in str(e), e
        return "404 raised"
    raise AssertionError("expected HttpError for unknown task_id")


def f2_missing_task_field():
    try:
        http("POST", "/api/tasks", payload={"agent_id": "e2e"})
    except HttpError as e:
        assert "400" in str(e) or "Bad Request" in str(e), e
        return "400 raised"
    raise AssertionError("expected 400 for missing task")


def f3_malformed_json():
    try:
        http("POST", "/api/tasks", raw_body=b"{not json")
    except HttpError as e:
        assert "400" in str(e) or "Bad Request" in str(e), e
        return "400 raised"
    raise AssertionError("expected 400 for malformed JSON")


def f4_blank_task():
    try:
        http("POST", "/api/tasks", payload={"task": "   ", "agent_id": "e2e"})
    except HttpError as e:
        assert "400" in str(e) or "Bad Request" in str(e), e
        return "400 raised"
    raise AssertionError("expected 400 for blank task")


def g1_concurrent_five():
    tids = [submit(f"e2e neutral burst {i}") for i in range(5)]
    results = [wait_done(t, deadline=90) for t in tids]
    assert all(t["status"] == "done" for t in results), results
    return "5/5 done"


def g2_idle_after_burst():
    h = http("GET", "/api/health")
    assert h["cc_instances"]["by_status"].get("idle") == 3, h["cc_instances"]
    assert h["capacity"]["active"] == 0, h["capacity"]
    return "idle=3 active=0"


# ── 运行器 ───────────────────────────────────────────────────────────

CASES: list[tuple[str, str, Callable[[], str]]] = [
    ("A1", "health 基础检查", a1_health),
    ("B1", "异步任务生命周期", b1_async_lifecycle),
    ("B2", "同步等待完成", b2_sync_run),
    ("C1", "路由: 显式 tag", c1_explicit_tag),
    ("C2", "路由: 消息内 @tag", c2_at_tag_in_message),
    ("C3", "路由: 显式 capability", c3_explicit_capability),
    ("C4", "路由: 关键词 capability", c4_keyword_capability),
    ("C5", "路由: 未知 tag 降级", c5_unknown_tag_fallback),
    ("C6", "路由: round-robin 轮换", c6_round_robin_rotation),
    ("C7", "路由: tag 优先于关键词", c7_tag_beats_keyword),
    ("D1", "workspace 任务级覆盖", d1_workspace_override),
    ("D2", "workspace 实例默认", d2_default_workspace),
    ("E1", "agent 归属记录", e1_agent_attribution),
    ("E2", "任务列表按 agent 过滤", e2e2_list_filter),
    ("F1", "错误: 不存在 task_id → 404", f1_unknown_task_id),
    ("F2", "错误: 缺 task 字段 → 400", f2_missing_task_field),
    ("F3", "错误: 畸形 JSON → 400", f3_malformed_json),
    ("F4", "错误: 空白 task → 400", f4_blank_task),
    ("G1", "并发 5 任务全部完成", g1_concurrent_five),
    ("G2", "并发后恢复空闲", g2_idle_after_burst),
]


def main() -> int:
    global VERBOSE, MODE
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", "--filter", default="", help="只跑 ID 含此串的用例")
    ap.add_argument("--mode", choices=["real", "fake"], default="real",
                    help="Router 当前使用的 CLI 类型（默认 real）")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    VERBOSE = args.verbose
    MODE = args.mode
    print(f"mode={MODE} target={BASE}")

    selected = [c for c in CASES if args.filter.upper() in c[0]]
    if not selected:
        print("no cases matched")
        return 1

    passed = failed = 0
    failures = []
    for cid, name, fn in selected:
        t0 = time.time()
        try:
            detail = fn()
            dt = time.time() - t0
            print(f"PASS {cid:3s} {name:28s} ({dt:4.1f}s) {detail}")
            passed += 1
        except Exception as e:
            dt = time.time() - t0
            msg = str(e).replace("\n", " ")[:200]
            print(f"FAIL {cid:3s} {name:28s} ({dt:4.1f}s) {msg}")
            if VERBOSE:
                import traceback; traceback.print_exc()
            failures.append((cid, msg))
            failed += 1

    print(f"\n{'='*60}\n{passed} passed, {failed} failed, "
          f"{len(selected)} total")
    if failures:
        for cid, msg in failures:
            print(f"  ✗ {cid}: {msg}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
