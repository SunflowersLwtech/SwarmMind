"""Integration test fixtures.

Overrides the mcp_server_proc fixture with a longer startup wait
because MCP SDK + pydantic + starlette take ~8s to import in a cold subprocess.
"""
import pytest
import subprocess
import sys
import os
import time
import signal


@pytest.fixture(scope="module")
def mcp_server_proc():
    """Start MCP server on test port 8901 with extended startup wait."""
    env = {**os.environ, "MCP_PORT": "8901"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.services.tool_server"],
        cwd=os.path.join(os.path.dirname(__file__), '../..'),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    # MCP SDK cold import takes ~8s; poll until port is open (max 20s)
    import socket
    for _ in range(20):
        time.sleep(1)
        if proc.poll() is not None:
            pytest.fail(f"MCP server process exited with code {proc.returncode}")
        s = socket.socket()
        s.settimeout(0.3)
        try:
            s.connect(("127.0.0.1", 8901))
            s.close()
            break
        except OSError:
            pass
        finally:
            s.close()
    else:
        proc.kill()
        pytest.fail("MCP server did not bind to port 8901 within 20s")

    yield proc
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
