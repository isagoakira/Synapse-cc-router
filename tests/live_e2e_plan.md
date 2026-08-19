# CC Router 对线测试计划（Live E2E）

> 目标：对运行在 Windows `127.0.0.1:8765` 的 CC Router Hub 做端到端验证。
> 执行端：WSL，通过 `E:\cc_router_venv\cc_http.ps1`（PowerShell Invoke-RestMethod）发 HTTP。
> 执行脚本：`tests/live_e2e.py`
>
> 环境前提：3 个 CC 实例（cc_code / cc_ml / cc_paper）已由 config 持久化加载，
> 全部 idle。
>
> **⚠️ 两种模式**（2026-08-19 实测发现）：
> - **real 模式**（当前配置）：`cc_cli_path=claude`（真实 CLI）。结果文本由 LLM 生成，
>   路由断言只看 `cc_id`；workspace 断言用「让 claude 自报 cwd」探测。
> - **fake 模式**：`cc_cli_path=E:\cc_router_venv\fake_claude.bat`。结果文本确定性
>   （`[FAKE-CC-X] handled task=..., workspace=<cwd>`），可做严格文本断言。
>
> 脚本用 `--mode real|fake` 切换，默认 real。

## 路由优先级（v0.4 被测对象）

`显式 tag > 消息内 @tag > 显式 capability > 消息关键词 capability > round-robin idle > first-available`

---

## A. 连通性与健康

| ID | 用例 | 步骤 | 预期 |
|----|------|------|------|
| A1 | health 基础检查 | GET /api/health | status=ok；cc_instances.count=3；by_status.idle=3；tasks.count≥0 |

## B. 任务生命周期

| ID | 用例 | 步骤 | 预期 |
|----|------|------|------|
| B1 | 异步提交→轮询→完成 | POST /api/tasks（中性文本）→ 轮询 GET /api/tasks/{id} | 201 返回 task_id；最终 status=done；cc_id 非空；fake 模式下 result 含 `[FAKE-CC-` 前缀，real 模式下 result 非空 |
| B2 | 同步等待 | 提交后轮询直到 done（等价 cc_submit run） | 60s 内完成，无 error |

## C. 路由策略（核心）

| ID | 用例 | 输入 | 预期 cc_id |
|----|------|------|-----------|
| C1 | 显式 tag | tag="ml"，中性文本 | cc_ml（fake 模式另验 `[FAKE-CC-ML]`）|
| C2 | 消息内 @tag | 文本含 `@code` | cc_code |
| C3 | 显式 capability | capability=["training"]，中性文本 | cc_ml |
| C4 | 关键词 capability | 文本含「训练 model loss」 | cc_ml（keyword→ml）|
| C5 | 未知 tag 降级 | tag="nonexistent"，中性文本 | 不报错；落到 round-robin，任一 idle CC |
| C6 | round-robin 轮换 | 连续 2 个中性任务（无 tag/关键词） | 两个任务的 cc_id **不同**（3 实例下连续 RR 必换）|
| C7 | 优先级：tag 压过关键词 | tag="paper" + 文本含「训练 model」 | cc_paper（tag 优先于关键词）|

## D. Workspace 覆盖

| ID | 用例 | 输入 | 预期 |
|----|------|------|------|
| D1 | 任务级覆盖 | tag="code" + workspace=`E:\fake_cc_workspaces\paper` | fake：result 中 workspace=`...\paper`；real：claude 自报 cwd 含 paper |
| D2 | 默认 workspace | tag="code"，不传 workspace | fake：result 中 workspace=`...\code`；real：claude 自报 cwd 含 code 且不含 paper/ml |

## E. Agent 归属与过滤

| ID | 用例 | 步骤 | 预期 |
|----|------|------|------|
| E1 | 归属记录 | agent_id="e2e-rokid" 提交 | get-task 的 caller_agent_id="e2e-rokid" |
| E2 | 列表过滤 | GET /api/tasks?agent_id=e2e-rokid | 返回任务全部属于该 agent，且包含 E1 任务 |

## F. 错误路径

| ID | 用例 | 输入 | 预期 |
|----|------|------|------|
| F1 | 不存在 task_id | GET /api/tasks/does-not-exist | HTTP 404（PowerShell 包装层 rc≠0，stderr 含 404）|
| F2 | 缺 task 字段 | POST /api/tasks  `{}` | 400，body 含 "task is required" |
| F3 | 畸形 JSON | POST body=`{not json` | 400（Invalid JSON body）|
| F4 | 空 task 字符串 | POST {"task":"   "} | 400 |

## G. 并发与容量

| ID | 用例 | 步骤 | 预期 |
|----|------|------|------|
| G1 | 并发 5 任务 | 快速连发 5 个异步任务（max_concurrent=5） | 全部 done；health 中无 error 任务 |
| G2 | 并发后恢复空闲 | G1 完成后查 health | by_status.idle=3，active=0 |

## H. 持久化（手动/重启，默认跳过）

| ID | 用例 | 步骤 | 预期 |
|----|------|------|------|
| H1 | config 持久化 | 重启 Router（start_router.bat）→ GET /api/cc | 3 个 config 实例自动恢复，无需重新 register |
| H2 | 运行时注册不持久 | 运行时 register cc_temp → 重启 | cc_temp 消失（仅 config 实例存活）|

## I. 超时（设计，暂不可自动化）

| ID | 用例 | 说明 |
|----|------|------|
| I1 | 任务超时 | fake CC 固定 sleep 0.2s，无法触发真实超时；需加 `--slow N` 模式的 fake_claude 后再测 timeout=1 → status=error/timeout |

---

## 已知边界 / 注意事项

- F 组错误测试依赖 PowerShell 包装层把非 2xx 变成 rc≠0（Invoke-RestMethod 默认行为），断言 stderr 文案而非精确 body。
- 运行时 register 的测试实例会留在内存直到重启——本计划避免 register 用例（持久化由 H 组覆盖）。
- 测试统一用 agent_id 前缀 `e2e-`，避免污染 main/rokid-front 的任务历史。
- fake CC 身份靠 cwd 判断，workspace 覆盖会改变身份前缀（D1 中前缀变 `[FAKE-CC]` generic）——fake 模式断言用 result 里的 `workspace=` 字段，不要用前缀。

## 首轮实测发现（2026-08-19，real 模式）

1. **当前 Router 接的是真实 claude CLI**（config `cc_cli_path=claude`），不是 fake_claude.bat。
   fake 断言全部不适用——测试脚本因此做了模式拆分。
2. ~~**真实 claude 偶发空 result**~~ → 已定位为 Bug 1（见下）并修复。
3. real 模式下全量耗时 ~5-6 min（LLM 真实延迟），fake 模式应 < 2 min。
4. GBK 乱码：PowerShell 包装层读回的 result 含替换字符，是 Windows 控制台
   编码问题，不影响状态/路由断言。
5. 轮询 deadline 放宽到 180s：真实 LLM 偶尔 >60s（C7 实测 61.8s），60s 会误报。

## 测试驱动的 Bug 修复（2026-08-19，已提交）

| Bug | 根因 | 修复 | 验证 |
|-----|------|------|------|
| **#1 跨目录 resume 崩溃**：workspace override 后任务 done 但 result 为空 | claude session 按项目目录存储；adapter 把 A 目录的 session_id 用 `--resume` 传给 B 目录 → `error_during_execution` 空 result exit 0 | `cc_adapter.py`：session 改为按 workspace normpath 分桶存储（`_sessions: dict`） | D1/D2 通过 |
| **#2 执行错误被当成功**：`is_error:true` 的 result 事件 → task done + 空文本 | `_read_events` 不看 `is_error`；hub 不看 `result.kind` 一律标 done | `cc_executor.py` 识别 is_error→kind=ERROR；`router_hub.py` 非 SUCCESS→task error | G1 中正确暴露 Bug #3 |
| **#3 单 CC 并发崩溃**：`readuntil() called while another coroutine is already waiting` | registry 快照状态不更新，路由永远看到 idle；提交间竞争让多任务落到同一 CC 共享同一 stdout | `router_hub.py`：submit 时在容量锁内同步标 busy；execute finally 释放为 idle；busy 实例上的任务改为排队 | G1 5 并发全过 |

预存 flake（与本次修复无关）：`test_robustness.py::test_timeout_handling` 在多文件
合并跑时偶发失败（stash 后复现同样失败，单跑稳定通过）。
