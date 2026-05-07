"""
Tests for the CC Router HTTP Server.

Run with: python -m pytest tests/test_http_server.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cc_router.http_server import create_app, _ok, _err


# ── Unit: Response helpers ──────────────────────────────────────────


class TestResponseHelpers:
    """Response helper function tests."""

    def test_ok_response(self):
        resp = _ok({"key": "val"})
        assert resp.status == 200
        assert resp.content_type == "application/json"

    def test_err_response(self):
        resp = _err("something wrong", status=404)
        assert resp.status == 404
        assert resp.content_type == "application/json"


# ── Integration: App creation ───────────────────────────────────────


class TestAppCreation:
    """HTTP app integration tests (with mocked Hub)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Mock get_global_hub before each test."""
        self.mock_hub = MagicMock()
        self.mock_hub.cc_registry.list_all = MagicMock(return_value=[])
        self.mock_hub.cc_registry.list_by_status = MagicMock(return_value=[])
        self.mock_hub.registry.list_all_sync = MagicMock(return_value=[])
        self.mock_hub.list_tasks = MagicMock(return_value=[])
        self.mock_hub.get_task = MagicMock(return_value=None)
        self.mock_hub.register_cc = MagicMock(
            side_effect=lambda adapter: adapter.cc_id
        )
        self.mock_hub.submit_task = AsyncMock(return_value="task_test")
        self.mock_hub.get_health_summary = MagicMock(return_value={
            "cc_instances": {"count": 0, "by_status": {}, "details": []},
            "tasks": {"count": 0, "pending": 0, "running": 0, "done": 0, "error": 0, "queued": 0},
            "capacity": {"max_concurrent": 5, "active": 0, "queued": 0, "available_slots": 5},
            "monitoring": {"health_running": False, "health_interval": 30.0, "max_failures": 3},
        })

        # Patch at the http_server module level (where get_global_hub is imported)
        patcher = patch("cc_router.http_server.get_global_hub", return_value=self.mock_hub)
        patcher.start()
        yield
        patcher.stop()

    @pytest.fixture
    def app(self):
        """Create the aiohttp test app."""
        return create_app()

    @pytest.fixture
    async def client(self, app, aiohttp_client):
        """Create an aiohttp test client."""
        return await aiohttp_client(app)

    # ── Health ──────────────────────────────────────────────────────

    async def test_health_endpoint(self, client):
        resp = await client.get("/api/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        # Enhanced health response with capacity and monitoring sections
        assert "agents" in data
        assert "cc_instances" in data
        assert "by_status" in data["cc_instances"]
        assert "capacity" in data
        assert "monitoring" in data

    # ── Tasks ───────────────────────────────────────────────────────

    async def test_submit_task_ok(self, client):
        resp = await client.post("/api/tasks", json={"task": "write tests"})
        assert resp.status == 201
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["task_id"] == "task_test"

    async def test_submit_task_empty(self, client):
        resp = await client.post("/api/tasks", json={"task": ""})
        assert resp.status == 400
        data = await resp.json()
        assert data["status"] == "error"

    async def test_submit_task_missing_body(self, client):
        resp = await client.post("/api/tasks", json={})
        assert resp.status == 400

    async def test_list_tasks(self, client):
        resp = await client.get("/api/tasks")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"

    async def test_get_task_not_found(self, client):
        resp = await client.get("/api/tasks/nonexistent")
        assert resp.status == 404

    # ── CC instances ────────────────────────────────────────────────

    async def test_register_cc_ok(self, client):
        resp = await client.post(
            "/api/cc/register",
            json={"cc_id": "test-cc", "workspace": "/tmp"},
        )
        assert resp.status == 201
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["cc_id"] == "test-cc"

    async def test_register_cc_missing_fields(self, client):
        resp = await client.post("/api/cc/register", json={"cc_id": "test"})
        assert resp.status == 400

    async def test_list_cc(self, client):
        resp = await client.get("/api/cc")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"

    # ── Bridge tools ────────────────────────────────────────────────

    async def test_call_tool_no_bridge(self, client):
        self.mock_hub._mcp_server = None
        resp = await client.post("/api/tools/feishu_notify", json={"arguments": {"text": "hi"}})
        assert resp.status == 503

    async def test_call_tool_with_bridge(self, client):
        bridge = MagicMock()
        bridge.call_tool = AsyncMock(return_value={"status": "ok", "message": "done"})
        self.mock_hub._mcp_server = bridge
        resp = await client.post("/api/tools/feishu_notify", json={"arguments": {"text": "hi"}})
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
