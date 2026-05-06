# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-05-07

### Added
- `cc_router/mcp_hub_server.py` — External MCP Hub Server wrapping UniversalRouterHub
- 7 MCP Tools: `submit_task`, `register_cc`, `list_cc_instances`, `list_agents`, `hub_status`, `connect_agent`, `disconnect_agent`
- `MCPAgentBridge` — minimal AgentAdapter for MCP-connected agents
- `--mcp` CLI flag to run as MCP Server (stdio transport) instead of TCP Hub
- MCP configuration: `mcp_enabled`, `mcp_server_name` in config system
- `tests/test_mcp_hub.py` — 25+ tests for MCP Hub Server with mocked Hub
- README "MCP Integration" section with Claude Desktop setup instructions
- `cc_router_config.template.json` updated with MCP config fields

### Changed
- `__init__.py`: exports `MCPHubServer`, `MCPAgentBridge`, `run_mcp_server`
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
