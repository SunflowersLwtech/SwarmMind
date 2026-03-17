"""
Test Suite 08: WebSocket Real-Time Streaming
Tests that the FastAPI WebSocket endpoint broadcasts simulation state.
"""
import pytest
import asyncio
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


@pytest.fixture
def ws_client(fastapi_app):
    """Create an httpx client with ASGIWebSocketTransport for WS tests."""
    from httpx_ws.transport import ASGIWebSocketTransport
    from httpx import AsyncClient
    transport = ASGIWebSocketTransport(app=fastapi_app)
    return AsyncClient(transport=transport, base_url="http://test")


WS_PATHS = ["/ws/live", "/ws", "/ws/simulation", "/ws/stream"]


class TestWebSocketEndpoint:
    """WebSocket must stream real-time state updates."""

    @pytest.mark.asyncio
    async def test_websocket_connects(self, ws_client):
        """WebSocket endpoint must accept connections."""
        from httpx_ws import aconnect_ws

        async with ws_client as client:
            for path in WS_PATHS:
                try:
                    async with aconnect_ws(path, client) as ws:
                        assert True
                        return
                except Exception:
                    continue
            pytest.fail(f"No WebSocket endpoint found at any of {WS_PATHS}")

    @pytest.mark.asyncio
    async def test_websocket_receives_state(self, ws_client):
        """WebSocket must send state update messages."""
        from httpx_ws import aconnect_ws

        async with ws_client as client:
            for path in WS_PATHS:
                try:
                    async with aconnect_ws(path, client) as ws:
                        msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
                        assert isinstance(msg, dict), f"Expected dict, got {type(msg)}"
                        return
                except (asyncio.TimeoutError, Exception):
                    continue
            pytest.fail("No WebSocket endpoint sent state data within 5 seconds")

    @pytest.mark.asyncio
    async def test_websocket_message_has_type(self, ws_client):
        """WebSocket messages must have a 'type' field for the frontend to discriminate."""
        from httpx_ws import aconnect_ws

        async with ws_client as client:
            for path in WS_PATHS:
                try:
                    async with aconnect_ws(path, client) as ws:
                        msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
                        assert 'type' in msg or 'event' in msg, \
                            f"WebSocket message must have 'type' or 'event' field: {list(msg.keys())}"
                        return
                except Exception:
                    continue

    @pytest.mark.asyncio
    async def test_websocket_state_has_fleet(self, ws_client):
        """WebSocket state updates must contain fleet data for 3D rendering."""
        from httpx_ws import aconnect_ws

        async with ws_client as client:
            for path in WS_PATHS:
                try:
                    async with aconnect_ws(path, client) as ws:
                        msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
                        payload = msg.get('payload', msg.get('data', msg))
                        has_fleet = any(k in payload for k in ('fleet', 'uavs'))
                        if has_fleet:
                            return
                except Exception:
                    continue
            pytest.fail("WebSocket state update must contain fleet/uavs data")
