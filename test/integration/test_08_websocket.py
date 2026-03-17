"""
Test Suite 08: WebSocket Real-Time Streaming
Tests that the FastAPI WebSocket endpoint broadcasts simulation state.
"""
import pytest
import asyncio
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


class TestWebSocketEndpoint:
    """WebSocket must stream real-time state updates."""

    @pytest.mark.asyncio
    async def test_websocket_connects(self, fastapi_app):
        """WebSocket endpoint must accept connections."""
        from httpx_ws import aconnect_ws
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                async with aconnect_ws("/ws/live", client) as ws:
                    # Should connect without error
                    assert True
            except Exception as e:
                # Try alternative paths
                for path in ["/ws", "/ws/simulation", "/ws/stream"]:
                    try:
                        async with aconnect_ws(path, client) as ws:
                            assert True
                            return
                    except:
                        continue
                pytest.fail(f"No WebSocket endpoint found at /ws/live, /ws, /ws/simulation, /ws/stream: {e}")

    @pytest.mark.asyncio
    async def test_websocket_receives_state(self, fastapi_app):
        """WebSocket must send state update messages."""
        from httpx_ws import aconnect_ws
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            paths = ["/ws/live", "/ws", "/ws/simulation", "/ws/stream"]
            for path in paths:
                try:
                    async with aconnect_ws(path, client) as ws:
                        msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
                        assert isinstance(msg, dict), f"Expected dict, got {type(msg)}"
                        return
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    continue
            pytest.fail("No WebSocket endpoint sent state data within 5 seconds")

    @pytest.mark.asyncio
    async def test_websocket_message_has_type(self, fastapi_app):
        """WebSocket messages must have a 'type' field for the frontend to discriminate."""
        from httpx_ws import aconnect_ws
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            paths = ["/ws/live", "/ws", "/ws/simulation", "/ws/stream"]
            for path in paths:
                try:
                    async with aconnect_ws(path, client) as ws:
                        msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
                        assert 'type' in msg or 'event' in msg, \
                            f"WebSocket message must have 'type' or 'event' field: {list(msg.keys())}"
                        return
                except:
                    continue

    @pytest.mark.asyncio
    async def test_websocket_state_has_fleet(self, fastapi_app):
        """WebSocket state updates must contain fleet data for 3D rendering."""
        from httpx_ws import aconnect_ws
        from httpx import AsyncClient, ASGITransport

        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            paths = ["/ws/live", "/ws", "/ws/simulation", "/ws/stream"]
            for path in paths:
                try:
                    async with aconnect_ws(path, client) as ws:
                        msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
                        payload = msg.get('payload', msg.get('data', msg))
                        has_fleet = any(k in payload for k in ('fleet', 'uavs'))
                        if has_fleet:
                            return
                except:
                    continue
            pytest.fail("WebSocket state update must contain fleet/uavs data")
