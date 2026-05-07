"""
CC Router CLI — command-line entry point for the UniversalRouterHub.

Usage:
    cc-router [--host HOST] [--port PORT] [--config CONFIG] [--log-level LEVEL]
    ccr [--host HOST] [--port PORT] [--config CONFIG] [--log-level LEVEL]

Examples:
    cc-router --port 8765 --log-level DEBUG
    ccr --host 0.0.0.0 --config /path/to/config.json
"""

import argparse
import asyncio
import logging
import signal
import sys

from .config import load_config, update_config
from .router_hub import get_global_hub

logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
_shutdown_requested = False


def _handle_signal(sig, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    global _shutdown_requested
    if _shutdown_requested:
        # Second signal → force exit
        logger.warning("Forced shutdown")
        sys.exit(1)
    _shutdown_requested = True
    logger.info("Shutdown requested (press Ctrl+C again to force)")


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        prog="cc-router",
        description="Universal Multi-Agent ↔ Multi-CC Connection Hub",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Hub host address (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Hub port (default: 8765)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config JSON file",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--bypass-permission",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Bypass all permission checks (default: True, use --no-bypass-permission to disable)",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="Run as MCP Server (stdio transport) instead of TCP Hub",
    )
    return parser


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with consistent format."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
    )


async def async_main(args: argparse.Namespace) -> None:
    """Async main entry point."""
    # Load config
    config = load_config(args.config)
    if args.host:
        update_config(hub_host=args.host)
    if args.port:
        update_config(hub_port=args.port)
    if args.log_level:
        update_config(log_level=args.log_level)
        setup_logging(args.log_level)
    if args.bypass_permission is not None:
        update_config(bypass_permission=args.bypass_permission)

    # MCP Server mode (stdio transport for Claude Desktop)
    if args.mcp:
        logger.info("Starting in MCP Server mode (stdio transport)")
        from .mcp_hub_server import run_server

        await run_server()
        return

    # Get global hub instance (TCP mode)
    hub = get_global_hub()
    host = config.get("hub_host", "localhost")
    port = config.get("hub_port", 8765)
    logger.info("CC Router Hub starting on %s:%d", host, port)

    # Start background tasks (health monitor + queue processor)
    hub.start_background_tasks()
    logger.info("Background tasks started (health monitor, queue processor)")

    # Start HTTP server as background task
    logger.info("Starting HTTP server on %s:%d", host, port)
    from .http_server import run_http_server

    http_task = asyncio.create_task(run_http_server(host, port))

    # Register signal handlers
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Main loop — keep hub alive
    try:
        while not _shutdown_requested:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Hub shutting down...")
        hub.stop_background_tasks()
        http_task.cancel()
        try:
            await http_task
        except asyncio.CancelledError:
            pass
        logger.info("Hub stopped")


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    # Initial logging setup
    log_level = args.log_level or "INFO"
    setup_logging(log_level)

    # Run async main
    try:
        asyncio.run(async_main(args))
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
