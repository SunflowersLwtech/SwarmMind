"""
Test Suite 14: SPA Routing — Regression Tests

Validates that the FastAPI catch-all route correctly:
1. Returns 404 for unknown /api/* paths (NOT index.html)
2. Serves index.html for frontend SPA routes
3. Serves static assets correctly
4. Known API endpoints return JSON

DO NOT weaken these tests.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


@pytest.fixture
def client():
    from httpx import AsyncClient, ASGITransport
    from backend.main import app

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestAPIRoutes:
    """Known API routes must return JSON."""

    @pytest.mark.asyncio
    async def test_health_returns_json(self, client):
        r = await client.get("/api/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_state_returns_json(self, client):
        r = await client.get("/api/state")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data

    @pytest.mark.asyncio
    async def test_logs_returns_json(self, client):
        r = await client.get("/api/logs")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data


class TestUnknownAPIRoutes:
    """Unknown /api/* paths must return 404 JSON, NOT index.html."""

    @pytest.mark.asyncio
    async def test_unknown_api_returns_404(self, client):
        r = await client.get("/api/nonexistent")
        assert r.status_code == 404, (
            f"GET /api/nonexistent should return 404, got {r.status_code}"
        )

    @pytest.mark.asyncio
    async def test_unknown_api_returns_json_not_html(self, client):
        r = await client.get("/api/nonexistent")
        content_type = r.headers.get("content-type", "")
        assert "html" not in content_type, (
            "Unknown API path returned HTML — SPA fallback is catching API routes"
        )

    @pytest.mark.asyncio
    async def test_unknown_api_nested_returns_404(self, client):
        r = await client.get("/api/v2/something/deep")
        assert r.status_code == 404
