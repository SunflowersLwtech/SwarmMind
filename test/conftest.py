"""
SwarmMind Test Suite — Shared Fixtures
DO NOT READ DURING DEVELOPMENT. Run only after implementation is complete.
"""
import pytest
import asyncio
import sys
import os
import json
import subprocess
import time
import signal

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ── Async event loop ──

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Simulation Engine Fixtures ──

@pytest.fixture
def grid_world():
    """Create a fresh GridWorld for each test."""
    from backend.core.grid_world import GridWorld
    world = GridWorld(size=20, num_uavs=5, num_objectives=8, num_obstacles=15)
    return world


@pytest.fixture
def small_world():
    """A minimal 10x10 world for fast tests."""
    from backend.core.grid_world import GridWorld
    world = GridWorld(size=10, num_uavs=3, num_objectives=3, num_obstacles=5)
    return world


@pytest.fixture
def uav_factory():
    """Factory to create UAVs with custom params."""
    from backend.core.uav import UAV

    def _make(id="test-uav", x=0, y=0, power=100.0, status="idle"):
        return UAV(id=id, x=x, y=y, power=power, status=status)

    return _make


# ── MCP Server Fixtures ──

@pytest.fixture(scope="session")
def mcp_server_process():
    """Start the MCP tool server as a subprocess for integration tests."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.services.tool_server"],
        cwd=os.path.join(os.path.dirname(__file__), '..'),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "MCP_PORT": "8901"},  # Test port
    )
    time.sleep(3)  # Wait for server to start
    yield proc
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=5)


# ── FastAPI Fixtures ──

@pytest.fixture
def fastapi_app():
    """Create the FastAPI app for testing."""
    from backend.main import app
    return app


@pytest.fixture
def api_client(fastapi_app):
    """Async HTTP test client."""
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=fastapi_app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── Helpers ──

def assert_status_ok(response_data: dict):
    """Assert MCP tool returned success."""
    assert "status" in response_data, f"Response missing 'status' key: {response_data}"
    assert response_data["status"] in ("ok", "success"), \
        f"Expected ok/success, got: {response_data['status']} — {response_data.get('message', '')}"


def assert_status_error(response_data: dict):
    """Assert MCP tool returned error."""
    assert "status" in response_data
    assert response_data["status"] in ("error", "failed")


def assert_valid_position(x, y, grid_size=20):
    """Assert coordinates are within grid bounds."""
    assert 0 <= x < grid_size, f"x={x} out of bounds [0, {grid_size})"
    assert 0 <= y < grid_size, f"y={y} out of bounds [0, {grid_size})"


def assert_valid_power(power):
    """Assert power is in valid range."""
    assert 0.0 <= power <= 100.0, f"Power {power} out of range [0, 100]"
