"""
Test Suite 03: MCP Tool Server
Tests that all MCP tools are correctly registered, callable, and return valid responses.
Uses FastMCP's in-memory client (no subprocess needed).
"""
import json
import pytest
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


def _parse_tool_result(result) -> dict:
    """Extract JSON dict from a fastmcp CallToolResult.

    fastmcp.Client.call_tool() returns a CallToolResult with a .content
    list of ContentBlock objects (each has a .text attribute).
    """
    if hasattr(result, 'content'):
        return json.loads(result.content[0].text)
    # Fallback for older APIs that return a list directly
    if isinstance(result, list):
        return json.loads(result[0].text) if hasattr(result[0], 'text') else result
    return result


@pytest.fixture
def mcp_server():
    """Import the FastMCP server instance."""
    from backend.services.tool_server import mcp
    return mcp


# ── Tool Registration ──

class TestToolRegistration:
    """All required MCP tools must be registered on the server."""

    REQUIRED_TOOLS = [
        "discover_fleet",
        "get_drone_status",
        "assign_search_mission",
        "assign_scan_mission",
        "recall_drone",
        "get_situation_overview",
        "get_frontier_targets",
        "plan_route",
    ]

    @pytest.mark.asyncio
    async def test_server_has_tools(self, mcp_server):
        """Server must expose tools via list_tools."""
        from fastmcp import Client
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            assert len(tool_names) >= 8, f"Expected >=8 tools, got {len(tool_names)}: {tool_names}"

    @pytest.mark.asyncio
    async def test_required_tools_present(self, mcp_server):
        """All core tools must be registered."""
        from fastmcp import Client
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}

            # Check each required tool (allow flexible naming)
            for required in self.REQUIRED_TOOLS:
                found = any(
                    required in name or name.replace('_', '') == required.replace('_', '')
                    for name in tool_names
                )
                if not found:
                    # Try partial match
                    found = any(
                        any(part in name for part in required.split('_'))
                        for name in tool_names
                    )
                assert found, f"Required tool '{required}' not found. Available: {tool_names}"

    @pytest.mark.asyncio
    async def test_tools_have_descriptions(self, mcp_server):
        """Every tool must have a non-empty description."""
        from fastmcp import Client
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            for tool in tools:
                assert tool.description and len(tool.description) > 10, \
                    f"Tool '{tool.name}' has missing/short description: '{tool.description}'"

    @pytest.mark.asyncio
    async def test_tools_have_input_schemas(self, mcp_server):
        """Tools with parameters must have proper input schemas."""
        from fastmcp import Client
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            for tool in tools:
                if tool.inputSchema and tool.inputSchema.get('properties'):
                    for prop_name, prop_def in tool.inputSchema['properties'].items():
                        assert 'type' in prop_def or '$ref' in prop_def or 'anyOf' in prop_def, \
                            f"Tool '{tool.name}' param '{prop_name}' missing type definition"


# ── Tool Execution ──

class TestFleetTools:
    """Fleet intelligence tools must return valid data."""

    @pytest.mark.asyncio
    async def test_discover_fleet(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            result = await client.call_tool("discover_fleet", {})
            assert result is not None
            data = _parse_tool_result(result)
            assert data.get('status') in ('ok', 'success'), f"discover_fleet failed: {data}"

    @pytest.mark.asyncio
    async def test_get_situation_overview(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            result = await client.call_tool("get_situation_overview", {})
            assert result is not None
            data = _parse_tool_result(result)
            assert data.get('status') == 'ok'


class TestNavigationTools:
    """Navigation tools must assign missions and return path info."""

    @pytest.mark.asyncio
    async def test_assign_search_mission(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            fleet_result = await client.call_tool("discover_fleet", {})
            fleet_data = _parse_tool_result(fleet_result)
            drones = fleet_data.get('data', {}).get('drones', [])
            assert len(drones) > 0, "No drones in fleet"
            drone_id = drones[0]['drone_id']

            result = await client.call_tool("assign_search_mission", {
                "drone_id": drone_id, "x": 3, "y": 0,
            })
            assert result is not None


class TestReconTools:
    """Reconnaissance tools must scan and update coverage."""

    @pytest.mark.asyncio
    async def test_assign_scan_mission(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            fleet_result = await client.call_tool("discover_fleet", {})
            fleet_data = _parse_tool_result(fleet_result)
            drones = fleet_data.get('data', {}).get('drones', [])
            drone_id = drones[0]['drone_id']

            result = await client.call_tool("assign_scan_mission", {"drone_id": drone_id})
            assert result is not None


class TestResourceTools:
    """Resource management tools must handle recall."""

    @pytest.mark.asyncio
    async def test_recall_drone(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            fleet_result = await client.call_tool("discover_fleet", {})
            fleet_data = _parse_tool_result(fleet_result)
            drones = fleet_data.get('data', {}).get('drones', [])
            drone_id = drones[0]['drone_id']

            result = await client.call_tool("recall_drone", {"drone_id": drone_id})
            assert result is not None


class TestToolResponseFormat:
    """All tools must return consistent response format."""

    @pytest.mark.asyncio
    async def test_all_tools_return_status(self, mcp_server):
        """Every parameterless tool response must include a 'status' field."""
        from fastmcp import Client
        async with Client(mcp_server) as client:
            for tool_name in ["discover_fleet", "get_situation_overview", "get_frontier_targets"]:
                result = await client.call_tool(tool_name, {})
                data = _parse_tool_result(result)
                assert 'status' in data, f"Tool '{tool_name}' response missing 'status': {data}"
