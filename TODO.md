# 待办事项与调试清单

## 待办 (TODO)

| # | 事项 | 优先级 | 状态 | 创建者 | 创建时间 |
|---|------|--------|------|--------|----------|
| 1 | 运行完整测试套件验证 100 测试全部通过 | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 2 | 检查 `cc_router/hermes_executor.py` 未暂存的修改 | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 3 | 创建 `router_mcp_bridge.js` (CC MCP Client stdio bridge) | MEDIUM | ✅ 已解决 | orchestrator | 260507 |
| 4 | 集成测试: CLI `cc-router` 启动验证 | MEDIUM | ✅ 已解决 | orchestrator | 260507 |
| 5 | 验证 `mcp>=1.0.0` 依赖可用性 (v1.27.0, FastMCP 可用) | MEDIUM | ✅ 已解决 | orchestrator | 260507 |
| 6 | Docker 部署验证 | LOW | ⏳ 待处理 | system | 260507 |
| 7 | Phase 5: 并行任务分发 + 健康监控 | MEDIUM | ✅ 已解决 | system | 260507 |
| 32 | B: JS bridge HTTP 委托 | MEDIUM | ✅ 已解决 | developer | 260507 |
| 33 | D: Hub HTTP Server (aiohttp REST API) | HIGH | ✅ 已解决 | developer | 260507 |
| 34 | C: 健康监控后台任务 + 容量管理 | MEDIUM | ✅ 已解决 | developer | 260507 |
| 8 | G0: 基础设施与社区规范 (8 tasks) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 9 | G1: 核心代码质量提升 (8 tasks) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 10 | G2: 测试体系强化 (7 tasks) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 11 | G3: CI/CD 完善 (6 tasks) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 12 | G4: 文档完善 (7 tasks) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 13 | G5: 发布前最终审查 (8 tasks) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 14 | G0: MCP Hub Server 核心实现 (5 tasks) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 15 | G1: MCP CLI 集成 (4 tasks) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 16 | G2: MCP 测试 (test_mcp_hub.py) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 17 | G3: MCP 文档更新 (2 tasks) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 18 | 创建 VCS 快照 | MEDIUM | ✅ 已解决 | orchestrator | 260507 |
| 19 | 运行 pytest tests/test_mcp_hub.py -v (32/32 passed) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 20 | 更新 harness-state.json → completed | MEDIUM | ✅ 已解决 | orchestrator | 260507 |
| 21 | G1: FastMCP 核心实现 (8 tasks) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 22 | G2: FastMCP 测试更新 (5 tasks, 32 tests) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 23 | G3: 引用 & 文档更新 (3 files) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 24 | G4: 最终验证 (5 tasks) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 25 | Phase 9: RouterMCPBridge 重构 — 实例化 task context + Pydantic + 实现 stubs | MEDIUM | ✅ 已解决 | orchestrator | 260507 |
| 26 | Phase 10: 修复硬编码版本号 (mcp_hub_server.py) | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 27 | Phase 10: 修复 bridge._hub bypass 模式 | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 28 | Phase 10: 实现 query_experiment_data 文件搜索 | MEDIUM | ✅ 已解决 | orchestrator | 260507 |
| 29 | Phase 10: 导出 RouterMCPBridge Pydantic 模型 | MEDIUM | ✅ 已解决 | orchestrator | 260507 |
| 30 | Phase 10: 类型注解 Any → TypedDict | LOW | ✅ 已解决 | orchestrator | 260507 |
| 31 | Phase 10: RouterMCPBridge 测试增强 (+15) | LOW | ✅ 已解决 | orchestrator | 260507 |

## 调试 (DEBUG)

| # | 问题描述 | 位置 | 状态 | 创建者 | 创建时间 |
|---|----------|------|------|--------|----------|
| — | (暂无) | — | — | — | — |

## 调试 (DEBUG)

| # | 问题描述 | 位置 | 状态 | 创建者 | 创建时间 |
|---|----------|------|------|--------|----------|
| — | (暂无) | — | — | — | — |

## 状态说明

| 状态 | 含义 | 操作者 |
|------|------|--------|
| ⏳ 待处理 | 待安排处理 | 任意 |
| 🔍 调查中 | 正在分析问题 | dev |
| 🔧 修复中 | 正在修复 | dev |
| ✅ 已解决 | 已修复待复核 | tester |
| 🎉 已归档 | 验证通过已归档 | tester |
