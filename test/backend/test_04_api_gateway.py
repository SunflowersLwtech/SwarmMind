"""
Test Suite 04: FastAPI Gateway
Tests REST endpoints, WebSocket streaming, and CORS.
"""
import pytest
import json
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


class TestRESTEndpoints:
    """All required REST endpoints must exist and respond correctly."""

    @pytest.mark.asyncio
    async def test_health_check(self, api_client):
        """Root or /health endpoint must respond."""
        for path in ["/", "/health", "/api/health"]:
            resp = await api_client.get(path)
            if resp.status_code == 200:
                return
        pytest.fail("No health check endpoint found at /, /health, or /api/health")

    @pytest.mark.asyncio
    async def test_get_state(self, api_client):
        """GET /api/state must return current simulation state."""
        resp = await api_client.get("/api/state")
        assert resp.status_code == 200, f"GET /api/state returned {resp.status_code}"
        data = resp.json()
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_ops_start(self, api_client):
        """POST /api/ops/start must start a mission."""
        resp = await api_client.post("/api/ops/start", json={"mission": "search eastern zone"})
        assert resp.status_code in (200, 201, 202), f"POST /api/ops/start returned {resp.status_code}"

    @pytest.mark.asyncio
    async def test_ops_stop(self, api_client):
        """POST /api/ops/stop must stop the mission."""
        resp = await api_client.post("/api/ops/stop")
        assert resp.status_code == 200, f"POST /api/ops/stop returned {resp.status_code}"

    @pytest.mark.asyncio
    async def test_get_logs(self, api_client):
        """GET /api/logs must return agent reasoning logs."""
        resp = await api_client.get("/api/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_state_contains_fleet(self, api_client):
        """State response must include fleet data for frontend rendering."""
        resp = await api_client.get("/api/state")
        data = resp.json()
        has_fleet = any(key in data for key in ('fleet', 'uavs', 'data'))
        assert has_fleet, f"State must contain fleet data. Keys: {list(data.keys())}"

    @pytest.mark.asyncio
    async def test_state_contains_coverage(self, api_client):
        """State response must include coverage for frontend dashboard."""
        resp = await api_client.get("/api/state")
        data = resp.json()
        # Flatten nested structures
        all_keys = set(data.keys())
        if 'data' in data and isinstance(data['data'], dict):
            all_keys.update(data['data'].keys())
        has_coverage = any('coverage' in k or 'progress' in k for k in all_keys)
        assert has_coverage, f"State must contain coverage. Keys: {all_keys}"


class TestCORS:
    """CORS must be configured for frontend development."""

    @pytest.mark.asyncio
    async def test_cors_headers(self, api_client):
        resp = await api_client.options(
            "/api/state",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"}
        )
        # Should not be 405 Method Not Allowed — CORS preflight must be handled
        assert resp.status_code != 405, "CORS preflight not handled"


class TestResponseFormat:
    """API responses must be consistent and well-structured."""

    @pytest.mark.asyncio
    async def test_json_content_type(self, api_client):
        resp = await api_client.get("/api/state")
        assert "application/json" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_state_is_json_serializable(self, api_client):
        resp = await api_client.get("/api/state")
        try:
            data = resp.json()
            json.dumps(data)  # Double-check serialization
        except (json.JSONDecodeError, TypeError) as e:
            pytest.fail(f"State response not valid JSON: {e}")
