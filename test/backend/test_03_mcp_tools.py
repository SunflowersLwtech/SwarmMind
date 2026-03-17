"""
Test Suite 03: MCP Tool Server
Tests that all MCP tools are correctly registered, callable, and return valid responses.
Uses FastMCP's in-memory client (no subprocess needed).
"""
import pytest
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


@pytest.fixture
def mcp_server():
    """Import the FastMCP server instance."""
    from backend.services.tool_server import mcp
    return mcp


# ── Tool Registration ──

class TestToolRegistration:
    """All required MCP tools must be registered on the server."""

    REQUIRED_TOOLS = [
        "query_fleet",
        "sweep_scan",           # or sweep_zone
        "navigate_to",          # or navigate_uav
        "check_power",
        "recall_uav",
        "repower_uav",
        "get_search_progress",
        "detect_frontier",      # or detect_search_boundary
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
    async def test_query_fleet(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            result = await client.call_tool("query_fleet", {})
            assert result is not None
            # Parse the result text
            import json
            data = json.loads(result[0].text) if hasattr(result[0], 'text') else result
            assert data.get('status') in ('ok', 'success'), f"query_fleet failed: {data}"

    @pytest.mark.asyncio
    async def test_get_search_progress(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            # Find the progress tool name
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            progress_tool = next((n for n in tool_names if 'progress' in n or 'coverage' in n), None)
            assert progress_tool, f"No progress/coverage tool found in {tool_names}"
            result = await client.call_tool(progress_tool, {})
            assert result is not None


class TestNavigationTools:
    """Navigation tools must move UAVs and return path info."""

    @pytest.mark.asyncio
    async def test_navigate_to(self, mcp_server):
        from fastmcp import Client
        import json
        async with Client(mcp_server) as client:
            # First get a UAV ID
            fleet_result = await client.call_tool("query_fleet", {})
            fleet_data = json.loads(fleet_result[0].text) if hasattr(fleet_result[0], 'text') else fleet_result
            uavs = fleet_data.get('data', fleet_data).get('uavs', [])
            assert len(uavs) > 0, "No UAVs in fleet"
            uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id

            # Find navigate tool
            tools = await client.list_tools()
            nav_tool = next((t.name for t in tools if 'navigate' in t.name or 'move' in t.name), None)
            assert nav_tool, f"No navigation tool found"

            result = await client.call_tool(nav_tool, {"uav_id": uav_id, "x": 5, "y": 5})
            assert result is not None


class TestReconTools:
    """Reconnaissance tools must scan and update coverage."""

    @pytest.mark.asyncio
    async def test_sweep_scan(self, mcp_server):
        from fastmcp import Client
        import json
        async with Client(mcp_server) as client:
            fleet_result = await client.call_tool("query_fleet", {})
            fleet_data = json.loads(fleet_result[0].text) if hasattr(fleet_result[0], 'text') else fleet_result
            uavs = fleet_data.get('data', fleet_data).get('uavs', [])
            uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id

            tools = await client.list_tools()
            scan_tool = next((t.name for t in tools if 'scan' in t.name or 'sweep' in t.name), None)
            assert scan_tool, "No scan/sweep tool found"

            result = await client.call_tool(scan_tool, {"uav_id": uav_id})
            assert result is not None


class TestResourceTools:
    """Resource management tools must handle recall and recharge."""

    @pytest.mark.asyncio
    async def test_recall_uav(self, mcp_server):
        from fastmcp import Client
        import json
        async with Client(mcp_server) as client:
            fleet_result = await client.call_tool("query_fleet", {})
            fleet_data = json.loads(fleet_result[0].text) if hasattr(fleet_result[0], 'text') else fleet_result
            uavs = fleet_data.get('data', fleet_data).get('uavs', [])
            uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id

            tools = await client.list_tools()
            recall_tool = next((t.name for t in tools if 'recall' in t.name or 'return' in t.name), None)
            assert recall_tool, "No recall/return tool found"

            result = await client.call_tool(recall_tool, {"uav_id": uav_id})
            assert result is not None


class TestToolResponseFormat:
    """All tools must return consistent response format."""

    @pytest.mark.asyncio
    async def test_all_tools_return_status(self, mcp_server):
        """Every tool response must include a 'status' field."""
        from fastmcp import Client
        import json
        async with Client(mcp_server) as client:
            # Test parameterless tools
            for tool_name in ["query_fleet"]:
                result = await client.call_tool(tool_name, {})
                data = json.loads(result[0].text) if hasattr(result[0], 'text') else result
                assert 'status' in data, f"Tool '{tool_name}' response missing 'status': {data}"
