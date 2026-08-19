# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.1] - 2026-08-19

### Fixed
- **Cross-workspace session resume crash**: `CCAdapter` stored a single
  `session_id` per instance, but claude sessions are per-project-directory.
  A task with `workspace=` override resumed the default-workspace session in
  the wrong directory → claude returned `error_during_execution` (empty
  result, exit 0). Sessions are now bucketed by normalized workspace path
  (`_sessions: dict[str, str]`).
- **Execution errors reported as success**: `_read_events` ignored the
  `is_error` flag on `result` events, and `RouterHub._execute_task` marked
  every task `done` regardless of `result.kind`. `is_error` results now map
  to `kind=ERROR` (message from the `errors` array), and non-SUCCESS results
  mark the task `error` instead of `done` with empty text.
- **Concurrent tasks on one CC crashed** with `readuntil() called while
  another coroutine is already waiting for incoming data`: the registry
  status snapshot was never updated during execution, so concurrent
  submissions all saw instances as `idle` and landed on the same single-
  session CC subprocess. Hub now marks the chosen instance `busy`
  synchronously inside the capacity lock at submit/dequeue time and releases
  it in `_execute_task`'s `finally`; tasks routed to a busy instance are
  queued instead of executing.

### Added
- `tests/live_e2e.py` + `tests/live_e2e_plan.md`: 20-case live end-to-end
  suite (health / lifecycle / routing priority / workspace override /
  agent attribution / error paths / concurrency) with `--mode real|fake`
  to match the configured CLI. All 20 cases pass against real claude CLI.

## [0.4.0] - 2026-08-18

### Added
- **Config-driven CC instance persistence**: top-level `cc_instances` array in
  the JSON config is auto-registered at Hub startup. Add an entry once,
  survive every restart — no more re-registering via HTTP API.
- **Per-task workspace override**: `submit_task(workspace=...)` /
  `POST /api/tasks` accepts an optional `workspace` field that overrides
  the CC instance's default workspace for that single execution. Lets one
  CC pool serve any directory the agent wants.
- `config.py` now reads JSON with `utf-8-sig` to tolerate UTF-8 BOM
  (PowerShell `Set-Content -Encoding UTF8` writes BOM by default).
- `cc_router_config.template.json` ships with an annotated `cc_instances` example.

### Changed
- **Routing strategy simplified**: removed `PATH_MATCH` strategy and the
  workspace-path-based routing rule. Routing now prioritizes
  `tag > @tag > capability > round-robin > first-available`. Workspace is
  no longer used for routing decisions — it's only an execution parameter.
- `CLAUDE.md` and `README.md` updated to reflect the new routing rules
  and persistence behavior.

### Removed
- `RoutingStrategy.PATH_MATCH` enum value (no longer reachable).

### Migration Notes
- Existing v0.3 configs that relied on workspace-based routing: move the
  routing intent into `tags` or `capabilities` on each CC instance.
- Instances previously registered only at runtime via HTTP: add them to
  `cc_instances` in your config so they survive restarts.

## [0.3.0] - 2026-05-07

### Added
- `cc_router/mcp_hub_server.py` — External MCP Hub Server wrapping UniversalRouterHub
- 7 MCP Tools: `submit_task`, `register_cc`, `list_cc_instances`, `list_agents`, `hub_status`, `connect_agent`, `disconnect_agent`
- `MCPAgentBridge` — minimal AgentAdapter for MCP-connected agents
- `--mcp` CLI flag to run as MCP Server (stdio transport) instead of TCP Hub
- MCP configuration: `mcp_enabled`, `mcp_server_name` in config system
- `tests/test_mcp_hub.py` — 32 tests for FastMCP-based Hub Server with mocked Hub
- README "MCP Integration" section with Claude Desktop setup instructions
- `cc_router_config.template.json` updated with MCP config fields

### Changed
- **MCP Server migrated to FastMCP**: low-level `mcp.server.Server` replaced with `FastMCP("synapse_mcp")` + `@mcp.tool()` decorators
- **Tool naming**: all 7 tools prefixed with `synapse_` (e.g. `submit_task` → `synapse_submit_task`)
- **Input validation**: manual `args.get()` replaced with Pydantic v2 models (`SubmitTaskInput`, `RegisterCCInput`, etc.)
- **Error handling**: JSON `{"status":"error"}` replaced with MCP `isError` flag via exception raising
- **Lifespan management**: Hub initialization moved to FastMCP lifespan context manager
- **Context injection**: `ctx: Context` parameter provides logging + lifespan access to all tools
- **Tool annotations**: all tools annotated with `readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint`
- **Server name**: `synapse-hub` → `synapse_mcp`
- `__init__.py`: exports `MCPHubServer`, `MCPAgentBridge`, `run_mcp_server`, `mcp` FastMCP instance, and 5 Pydantic input models
- `config.py`: added `MCP_ENABLED` and `MCP_SERVER_NAME` defaults
- `__main__.py`: MCP mode dispatched before TCP Hub startup
- Project structure in README updated to include `mcp_hub_server.py`

## [0.2.0] - 2026-05-07

### Added
- GitHub Issue templates (bug report + feature request)
- GitHub PR template
- `CONTRIBUTING.md` contribution guide
- `cc_router_config.template.json` configuration template
- `cc_router/mcp/router_mcp_bridge.js` — MCP stdio bridge (JSON-RPC 2.0)
- `docs/` documentation suite: API reference, architecture, installation, examples
- `tests/test_core.py` — 44 pytest-style unit and integration tests
- `tests/conftest.py` — shared test fixtures
- `.github/workflows/release.yml` — GitHub Release + PyPI publish workflow
- Hardware requirements table to README

### Changed
- CI workflow: split into 4 parallel jobs (lint/test/docker/publish)
- CI: added coverage reporting with `pytest-cov` and artifact upload
- CI: separated lint into its own job (ruff + black + mypy)
- `pyproject.toml`: added `mypy>=1.0`, `pytest-cov>=4.0` to dev deps
- `.gitignore`: added template file exception (`!cc_router_config.template.json`)
- `openclaw_executor.py`: hardcoded `/opt/homebrew/bin/openclaw` → `"openclaw"` (portability)
- `hermes_executor.py`: hardcoded `/Users/<user>/.local/bin/hermes` → `"hermes"` (portability)
- `README.md`: expanded with hardware requirements table

### Fixed
- Unused imports: `os` in `config.py` and `__main__.py`, `HubEvent`/`CCExecutor` in `router_hub.py`, `Optional` in `router_mcp_server.py`
- Long lines (>100 chars) in `router_mcp_server.py`, `mcp/__init__.py`, `training_log.py`, `shared_data.py`, `env_detector.py`, `cli_wizard.py`, `cc_executor.py`
- Exception handling: `config.py` now wraps file I/O errors with `RouterError`
- Missing docstrings in `config.py` and `cc_registry.py`

## [0.1.0] - 2025-05-06

### Added
- Initial release of CC Router — Universal Multi-Agent ↔ Multi-CC Connection Hub
- Core routing hub with UniversalRouterHub, AgentRegistry, CCRegistry
- EventBus for bidirectional async event pub/sub
- UniversalRouter with tag/path/capability-based routing
- CCAdapter and CCExecutor for Claude Code CLI integration
- HermesExecutor and OpenClawExecutor for agent execution
- RouterMCPBridge for MCP tool calls
- Interactive installation wizard (CLI)
- Environment detection and configuration management
- Feishu notification, training log, and shared data MCP tools
- Comprehensive test suite (92 tests)
- Dockerfile and Docker health check
- GitHub Actions CI with lint, test, and publish stages
- pre-commit hooks (black, ruff, mypy, etc.)
- MIT License
