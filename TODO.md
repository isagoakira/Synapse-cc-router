# 待办事项与调试清单

## 待办 (TODO)

| # | 事项 | 优先级 | 状态 | 创建者 | 创建时间 |
|---|------|--------|------|--------|----------|
| 1 | 运行完整测试套件验证 92 测试全部通过 | HIGH | ⏳ 待处理 | system | 260507 |
| 2 | 检查 `cc_router/hermes_executor.py` 未暂存的修改 | HIGH | ✅ 已解决 | orchestrator | 260507 |
| 3 | 创建 `router_mcp_bridge.js` (CC MCP Client stdio bridge) | MEDIUM | ✅ 已解决 | orchestrator | 260507 |
| 4 | 集成测试: CLI `cc-router` 启动验证 | MEDIUM | ⏳ 待处理 | system | 260507 |
| 5 | 验证 `mcp>=1.0.0` 依赖可用性 | MEDIUM | ⏳ 待处理 | system | 260507 |
| 6 | Docker 部署验证 | LOW | ⏳ 待处理 | system | 260507 |
| 7 | Phase 5: 并行任务分发 + 健康监控 | LOW | ⏳ 待处理 | system | 260507 |
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
| 18 | 创建 VCS 快照 (group-g0..g3) | MEDIUM | ⏳ 待处理 | orchestrator | 260507 |
| 19 | 运行 pytest tests/test_mcp_hub.py -v | HIGH | ⏳ 待处理 | orchestrator | 260507 |
| 20 | 更新 harness-state.json | MEDIUM | ⏳ 待处理 | orchestrator | 260507 |

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
