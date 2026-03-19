"""
Test Suite 21: Mission-Oriented MCP Tools
Tests for the 8 new MCP tools that operate through Drone objects.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


def _parse(result) -> dict:
    """Extract JSON dict from a fastmcp CallToolResult."""
    if hasattr(result, "content"):
        return json.loads(result.content[0].text)
    return result


@pytest.fixture
def mcp_server():
    from backend.services.tool_server import mcp, set_shared_world
    from backend.core.grid_world import GridWorld
    # Reset to a fresh world for each test class
    set_shared_world(GridWorld(size=20, num_uavs=5, num_objectives=8, num_obstacles=15))
    return mcp


# ═══════════════════════════════════════════════════════════════
#  Tool count
# ═══════════════════════════════════════════════════════════════

class TestToolCount:
    @pytest.mark.asyncio
    async def test_exactly_8_tools(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            assert len(tools) == 8, (
                f"Expected exactly 8 tools, got {len(tools)}: "
                f"{sorted(t.name for t in tools)}"
            )

    @pytest.mark.asyncio
    async def test_tool_names(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools}
            expected = {
                "discover_fleet", "get_drone_status",
                "assign_search_mission", "assign_scan_mission",
                "recall_drone", "get_situation_overview",
                "get_frontier_targets", "plan_route",
            }
            assert names == expected, (
                f"Tool set mismatch.\n"
                f"  Missing: {expected - names}\n"
                f"  Unexpected: {names - expected}"
            )


# ═══════════════════════════════════════════════════════════════
#  discover_fleet
# ═══════════════════════════════════════════════════════════════

class TestDiscoverFleet:
    @pytest.mark.asyncio
    async def test_returns_drone_ids(self, mcp_server):
        """discover_fleet must return drone IDs without hardcoding."""
        from fastmcp import Client
        async with Client(mcp_server) as client:
            result = await client.call_tool("discover_fleet", {})
            data = _parse(result)
            assert data["status"] == "ok"
            assert "drones" in data["data"]
            assert len(data["data"]["drones"]) > 0
            # Each drone should have an ID
            for d in data["data"]["drones"]:
                assert "drone_id" in d

    @pytest.mark.asyncio
    async def test_includes_mission_status(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            result = await client.call_tool("discover_fleet", {})
            data = _parse(result)
            for d in data["data"]["drones"]:
                assert "mission_status" in d


# ═══════════════════════════════════════════════════════════════
#  get_drone_status
# ═══════════════════════════════════════════════════════════════

class TestGetDroneStatus:
    @pytest.mark.asyncio
    async def test_includes_mission(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            fleet = _parse(await client.call_tool("discover_fleet", {}))
            drone_id = fleet["data"]["drones"][0]["drone_id"]

            result = await client.call_tool("get_drone_status", {"drone_id": drone_id})
            data = _parse(result)
            assert data["status"] == "ok"
            assert "mission_status" in data["data"]
            assert "explorable_cells" in data["data"]
            assert "eta" in data["data"]


# ═══════════════════════════════════════════════════════════════
#  assign_search_mission
# ═══════════════════════════════════════════════════════════════

class TestAssignSearchMission:
    @pytest.mark.asyncio
    async def test_accepted(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            fleet = _parse(await client.call_tool("discover_fleet", {}))
            drone_id = fleet["data"]["drones"][0]["drone_id"]

            # Try multiple targets in case of obstacles
            for target in [(3, 0), (0, 3), (2, 0), (0, 2)]:
                result = await client.call_tool("assign_search_mission", {
                    "drone_id": drone_id, "x": target[0], "y": target[1],
                })
                data = _parse(result)
                if data["status"] == "ok":
                    break

            assert data["status"] == "ok"
            assert "accepted" in data["data"]["status"]

    @pytest.mark.asyncio
    async def test_rejected_invalid_drone(self, mcp_server):
        from fastmcp import Client
        async with Client(mcp_server) as client:
            result = await client.call_tool("assign_search_mission", {
                "drone_id": "GHOST", "x": 5, "y": 5,
            })
            data = _parse(result)
            assert data["status"] == "error"


# ═══════════════════════════════════════════════════════════════
#  get_situation_overview
# ═══════════════════════════════════════════════════════════════

class TestSituationOverview:
    @pytest.mark.asyncio
    async def test_composite(self, mcp_server):
        """Single call should return fleet, progress, hotspots, endurance."""
        from fastmcp import Client
        async with Client(mcp_server) as client:
            result = await client.call_tool("get_situation_overview", {})
            data = _parse(result)
            assert data["status"] == "ok"
            sa = data["data"]
            assert "fleet" in sa
            assert "progress" in sa
            assert "hotspots" in sa
            assert "endurance" in sa
            assert "tick" in sa
