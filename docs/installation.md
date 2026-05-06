# Installation Guide

## Prerequisites

- **Python 3.11** or later
- **Claude Code CLI** (`claude` command available in PATH)
- **Optional**: Hermes CLI for Hermes agent support
- **Optional**: OpenClaw CLI for OpenClaw agent support

### Hardware Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 4 GB | 16 GB (for 3-4 concurrent CC instances) |
| CPU | 2 cores | 4+ cores |
| Disk | 1 GB | 10 GB (session files, logs) |
| Network | Internet | Broadband (for API calls) |

## Install from PyPI

```bash
pip install cc-router
```

## Install from Source

```bash
# Clone the repository
git clone https://github.com/anthropics/cc-router
cd cc-router

# Install with development tools
pip install -e ".[dev]"
```

## Verify Installation

```bash
# Check CLI is available
cc-router --help
ccr --help

# Run the test suite
python -m pytest tests/ -v

# Run lint checks
ruff check .
black --check .
mypy cc_router/
```

## Quick Start

### 1. Create a configuration file

Copy the template and adjust:

```bash
cp cc_router_config.template.json cc_router_config.json
# Edit cc_router_config.json to match your environment
```

### 2. Start the Hub

```bash
cc-router --port 8765 --log-level INFO
```

### 3. (Optional) Use the interactive installer

```bash
python -m cc_router.installer.cli_wizard
```

This launches a menu-driven wizard that detects your environment and helps configure CC instances, agent adapters, and MCP tools.

## Docker Installation

```bash
# Build the image
docker build -t cc-router .

# Run the container
docker run -d \
  --name cc-router \
  -p 8765:8765 \
  -v /path/to/config.json:/app/cc_router_config.json \
  cc-router
```

## Development Setup

For contributors:

```bash
# Install with all dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Verify setup
python -m pytest tests/ -v --cov=cc_router
```

## Troubleshooting

### "CC CLI not found" error

Ensure the `claude` command is available in your PATH:

```bash
which claude
claude --version
```

### "mcp package not found"

Install the MCP package:

```bash
pip install "mcp>=1.0.0"
```

### Port already in use

Change the port:

```bash
cc-router --port 8766
```

### Permission errors on macOS

If you get permission errors when trying to install packages:

```bash
pip install --user -e ".[dev]"
# or use a virtual environment
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```
