"""
Test Suite 07: MCP Wire Protocol Compliance
Tests that the MCP Server actually runs as a separate process and communicates
via wire protocol (Streamable HTTP), not direct imports.
This is the KEY CS3 compliance test.
"""
import pytest
import subprocess
import sys
import os
import time
import signal
import asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


@pytest.fixture(scope="module")
def mcp_server_proc():
    """Start MCP server on test port 8901."""
    env = {**os.environ, "MCP_PORT": "8901"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.services.tool_server"],
        cwd=os.path.join(os.path.dirname(__file__), '../..'),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    time.sleep(4)  # Wait for server startup
    assert proc.poll() is None, f"MCP server failed to start: {proc.stderr.read().decode()}"
    yield proc
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


class TestMCPServerStarts:
    """MCP server must start as an independent process."""

    def test_server_process_alive(self, mcp_server_proc):
        assert mcp_server_proc.poll() is None, "MCP server process died"


class TestMCPWireProtocol:
    """Tools must be callable over HTTP (wire protocol, not direct import)."""

    @pytest.mark.asyncio
    async def test_list_tools_over_http(self, mcp_server_proc):
        """Connect as an MCP client over Streamable HTTP and list tools."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client("http://localhost:8901/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert len(tools.tools) >= 8, f"Expected >=8 tools over wire, got {len(tools.tools)}"

    @pytest.mark.asyncio
    async def test_call_tool_over_http(self, mcp_server_proc):
        """Call query_fleet tool over wire protocol."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        import json

        async with streamablehttp_client("http://localhost:8901/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("query_fleet", {})
                assert result is not None
                assert len(result.content) > 0
                data = json.loads(result.content[0].text)
                assert data.get('status') in ('ok', 'success')

    @pytest.mark.asyncio
    async def test_navigate_tool_over_http(self, mcp_server_proc):
        """Navigate a UAV over wire protocol."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        import json

        async with streamablehttp_client("http://localhost:8901/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Get a UAV ID first
                fleet = await session.call_tool("query_fleet", {})
                fleet_data = json.loads(fleet.content[0].text)
                uavs = fleet_data.get('data', fleet_data).get('uavs', [])
                assert len(uavs) > 0
                uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0]

                # Find navigate tool
                tools = await session.list_tools()
                nav_tool = next((t.name for t in tools.tools if 'navigate' in t.name or 'move' in t.name), None)
                assert nav_tool, "No navigate tool found over wire"

                # Call it
                result = await session.call_tool(nav_tool, {"uav_id": uav_id, "x": 3, "y": 3})
                assert result is not None


class TestMCPToolDiscovery:
    """CS3 requires dynamic tool discovery — no hardcoded drone IDs."""

    @pytest.mark.asyncio
    async def test_fleet_returns_dynamic_ids(self, mcp_server_proc):
        """query_fleet must return actual UAV IDs that can be used in other tools."""
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        import json

        async with streamablehttp_client("http://localhost:8901/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                fleet = await session.call_tool("query_fleet", {})
                data = json.loads(fleet.content[0].text)
                uavs = data.get('data', data).get('uavs', [])

                # IDs should be strings, unique
                ids = [u['id'] if isinstance(u, dict) else u for u in uavs]
                assert len(ids) > 0
                assert len(set(ids)) == len(ids), "UAV IDs must be unique"
                assert all(isinstance(i, str) for i in ids)
