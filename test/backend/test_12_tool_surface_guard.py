"""
Test Suite 12: Tool Surface Regression Guard

Strict contract tests that prevent accidental regression of the MCP tool
refactoring. These tests enforce:

1. FROZEN TOOL SET — exactly 8 mission-oriented tools, no more, no less
2. REMOVED TOOLS BANNED — old tools must never reappear on agent surface
3. RESPONSE CONTRACT — every tool returns {"status": "ok"|"error"|"rejected", ...}
4. TOOL IDEMPOTENCY — read-only tools return stable results across calls
5. ERROR CONTRACT — invalid inputs produce structured errors, not crashes
6. PROMPT CONTRACT — prompts reference only available tools, never removed ones
7. COMPOSITE COMPLETENESS — get_situation_overview covers all needed data
8. STRATEGIST AUTONOMY — agent decides strategy via frontier, not fixed sectors
9. INTERNAL METHODS PRESERVED — GridWorld internals still work for autopilot

DO NOT weaken these tests. If a test fails, the code must change, not the test.
"""
import json
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.core.grid_world import GridWorld


# ─── Constants ────────────────────────────────────────────────────

# The canonical set of 8 mission-oriented tools.
OPERATIONAL_TOOLS = frozenset({
    "discover_fleet",
    "get_drone_status",
    "assign_search_mission",
    "assign_scan_mission",
    "recall_drone",
    "get_situation_overview",
    "get_frontier_targets",
    "plan_route",
})

# Tools removed during refactoring — must NEVER reappear on agent surface.
BANNED_TOOLS = frozenset({
    # Admin/simulation tools (least-privilege violation)
    "init_scenario", "deploy_uav", "inject_event",
    # Prescriptive planning tools (limits agent autonomy)
    "partition_sectors", "assign_sector",
    # Redundant composite (subsumed by get_situation_overview)
    "get_op_summary",
    # Old micro-tools (subsumed by mission-oriented tools)
    "query_fleet", "inspect_uav", "get_threat_map", "get_search_progress",
    "navigate_to", "sweep_scan", "mark_objective",
    "recall_uav", "repower_uav", "assess_endurance",
    "get_situational_awareness",
})


# ─── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def world():
    return GridWorld(size=10, num_uavs=3, num_objectives=4, num_obstacles=5, seed=42)


@pytest.fixture
def prompts():
    path = os.path.join(os.path.dirname(__file__), "../../backend/agents/prompts.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


# ═══════════════════════════════════════════════════════════════════
#  1. FROZEN TOOL SET — exactly 8 tools
# ═══════════════════════════════════════════════════════════════════

class TestFrozenToolSet:
    """The agent must see exactly 8 tools — no more, no less."""

    @pytest.mark.asyncio
    async def test_mcp_exposes_exactly_8_tools(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert len(tools) == 8, (
                f"Expected exactly 8 MCP tools, got {len(tools)}: "
                f"{sorted(t.name for t in tools)}"
            )

    @pytest.mark.asyncio
    async def test_mcp_tool_names_match_contract(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            tools = await client.list_tools()
            actual = frozenset(t.name for t in tools)
            assert actual == OPERATIONAL_TOOLS, (
                f"MCP tool set mismatch.\n"
                f"  Missing: {OPERATIONAL_TOOLS - actual}\n"
                f"  Unexpected: {actual - OPERATIONAL_TOOLS}"
            )


# ═══════════════════════════════════════════════════════════════════
#  2. REMOVED TOOLS BANNED
# ═══════════════════════════════════════════════════════════════════

class TestBannedTools:
    """Removed tools must never reappear on the agent-facing surface."""

    @pytest.mark.asyncio
    async def test_mcp_has_no_banned_tools(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            tools = await client.list_tools()
            actual = {t.name for t in tools}
            leaked = actual & BANNED_TOOLS
            assert not leaked, (
                f"BANNED tools leaked onto MCP surface: {leaked}\n"
                f"These tools were removed for security/design reasons."
            )

    @pytest.mark.asyncio
    async def test_calling_banned_tool_via_mcp_fails(self):
        """Attempting to invoke a removed tool must raise or error."""
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            for tool_name in ["query_fleet", "navigate_to", "recall_uav"]:
                with pytest.raises(Exception):
                    await client.call_tool(tool_name, {})


# ═══════════════════════════════════════════════════════════════════
#  3. RESPONSE CONTRACT — every tool returns {"status": ...}
# ═══════════════════════════════════════════════════════════════════

class TestResponseContract:
    """Every tool must return a dict with 'status' key."""

    ZERO_ARG_TOOLS = [
        "discover_fleet", "get_situation_overview", "get_frontier_targets",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_name", ZERO_ARG_TOOLS)
    async def test_zero_arg_tool_returns_status_ok(self, tool_name):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool(tool_name, {})
            data = json.loads(result.content[0].text)
            assert "status" in data, f"MCP {tool_name} missing 'status'"
            assert data["status"] == "ok", f"MCP {tool_name}: {data}"


# ═══════════════════════════════════════════════════════════════════
#  4. TOOL IDEMPOTENCY — read-only tools return stable results
# ═══════════════════════════════════════════════════════════════════

class TestToolIdempotency:
    """Read-only tools must return identical results when called twice."""

    @pytest.mark.asyncio
    async def test_discover_fleet_idempotent(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            r1 = json.loads((await client.call_tool("discover_fleet", {})).content[0].text)
            r2 = json.loads((await client.call_tool("discover_fleet", {})).content[0].text)
            assert r1 == r2

    @pytest.mark.asyncio
    async def test_situation_overview_idempotent(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            r1 = json.loads((await client.call_tool("get_situation_overview", {})).content[0].text)
            r2 = json.loads((await client.call_tool("get_situation_overview", {})).content[0].text)
            assert r1 == r2


# ═══════════════════════════════════════════════════════════════════
#  5. ERROR CONTRACT — invalid inputs → structured errors
# ═══════════════════════════════════════════════════════════════════

class TestErrorContract:
    """Invalid inputs must return structured errors, not crashes."""

    GHOST_DRONE = "GHOST-999"

    @pytest.mark.asyncio
    async def test_get_drone_status_invalid_id(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool("get_drone_status", {"drone_id": self.GHOST_DRONE})
            data = json.loads(result.content[0].text)
            assert data["status"] == "error"
            assert "not found" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_assign_search_invalid_id(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool("assign_search_mission", {
                "drone_id": self.GHOST_DRONE, "x": 1, "y": 1,
            })
            data = json.loads(result.content[0].text)
            assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_recall_drone_invalid_id(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool("recall_drone", {"drone_id": self.GHOST_DRONE})
            data = json.loads(result.content[0].text)
            assert data["status"] == "error"


# ═══════════════════════════════════════════════════════════════════
#  6. PROMPT CONTRACT — reference only available tools
# ═══════════════════════════════════════════════════════════════════

class TestPromptContract:
    """Prompts must reference only tools that exist on the agent surface."""

    STAGES = ["assessor", "strategist", "dispatcher", "analyst"]

    def test_all_stages_present(self, prompts):
        for stage in self.STAGES:
            assert stage in prompts, f"Missing prompt for stage '{stage}'"
            assert "instruction" in prompts[stage], f"Missing instruction for '{stage}'"

    @pytest.mark.parametrize("stage", STAGES)
    def test_no_banned_tool_references(self, prompts, stage):
        """Prompts must NEVER mention removed tool names."""
        instruction = prompts[stage]["instruction"]
        for banned in BANNED_TOOLS:
            assert banned not in instruction, (
                f"Prompt '{stage}' references banned tool '{banned}'"
            )

    def test_prompts_only_reference_available_tools(self, prompts):
        """Every backtick-quoted tool name in prompts must be in OPERATIONAL_TOOLS."""
        import re
        for stage in self.STAGES:
            instruction = prompts[stage]["instruction"]
            referenced = set(re.findall(r"`(\w+)`", instruction))
            for ref in referenced:
                if ref in ("ok", "error", "status", "assessment", "strategy",
                           "execution_log", "report", "rejected"):
                    continue
                assert ref in OPERATIONAL_TOOLS, (
                    f"Prompt '{stage}' references `{ref}` which is not in "
                    f"OPERATIONAL_TOOLS."
                )

    def test_strategist_uses_frontier_targets(self, prompts):
        instruction = prompts["strategist"]["instruction"]
        assert "get_frontier_targets" in instruction

    def test_analyst_uses_situation_overview(self, prompts):
        instruction = prompts["analyst"]["instruction"]
        assert "get_situation_overview" in instruction


# ═══════════════════════════════════════════════════════════════════
#  7. COMPOSITE COMPLETENESS — get_situation_overview
# ═══════════════════════════════════════════════════════════════════

class TestCompositeCompleteness:
    """get_situation_overview must return comprehensive data."""

    @pytest.mark.asyncio
    async def test_contains_all_sections(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool("get_situation_overview", {})
            data = json.loads(result.content[0].text)["data"]

            assert "fleet" in data
            assert "progress" in data
            assert "hotspots" in data
            assert "endurance" in data
            assert "tick" in data
            assert "mission_status" in data

    @pytest.mark.asyncio
    async def test_endurance_includes_mission(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool("get_situation_overview", {})
            data = json.loads(result.content[0].text)["data"]
            for entry in data["endurance"]:
                assert "mission" in entry


# ═══════════════════════════════════════════════════════════════════
#  8. STRATEGIST AUTONOMY
# ═══════════════════════════════════════════════════════════════════

class TestStrategistAutonomy:
    """Agent must decide strategy autonomously."""

    @pytest.mark.asyncio
    async def test_frontier_targets_provides_ranked_cells(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool("get_frontier_targets", {})
            data = json.loads(result.content[0].text)
            assert data["status"] == "ok"
            assert len(data["data"]) > 0
            priorities = [c["priority"] for c in data["data"]]
            assert priorities == sorted(priorities, reverse=True)

    @pytest.mark.asyncio
    async def test_plan_route_enables_cost_comparison(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool("plan_route", {
                "start_x": 0, "start_y": 0, "end_x": 5, "end_y": 5,
            })
            data = json.loads(result.content[0].text)
            assert data["status"] == "ok"
            assert "power_cost" in data["data"]
            assert "distance" in data["data"]


# ═══════════════════════════════════════════════════════════════════
#  9. INTERNAL METHODS PRESERVED
# ═══════════════════════════════════════════════════════════════════

class TestInternalMethodsPreserved:
    """GridWorld internal methods must still work."""

    def test_partition_sectors_works_internally(self, world):
        sectors = world.partition_sectors(4)
        assert len(sectors) == 4

    def test_add_uav_works_internally(self, world):
        uav = world.add_uav("Zulu")
        assert uav.id == "Zulu"
        assert uav.id in world.fleet

    def test_autopilot_still_runs_via_drones(self, world):
        world.mission_status = "running"
        for _ in range(5):
            result = world.step()
            assert result.tick > 0

    def test_state_snapshot_still_serializable(self, world):
        snapshot = world.get_state_snapshot()
        assert "fleet" in snapshot
        assert "coverage_pct" in snapshot
        assert "objectives" in snapshot

    def test_move_uav_direct_still_works(self, world):
        uav_id = list(world.fleet.keys())[0]
        result = world.move_uav(uav_id, 3, 0)
        assert result.new_position == [3, 0]

    def test_recall_uav_direct_still_works(self, world):
        uav_id = list(world.fleet.keys())[0]
        world.move_uav(uav_id, 3, 0)
        result = world.recall_uav(uav_id)
        uav = world.fleet[uav_id]
        assert (uav.x, uav.y) == (0, 0)

    def test_fleet_property_returns_uavs(self, world):
        """fleet property must return {id: UAV} dict."""
        fleet = world.fleet
        assert len(fleet) == 3
        for uid, uav in fleet.items():
            assert isinstance(uav, __import__("backend.core.uav", fromlist=["UAV"]).UAV)

    def test_drones_dict_accessible(self, world):
        """drones dict must be the primary storage."""
        assert len(world.drones) == 3
        for did, drone in world.drones.items():
            assert drone.uav.id == did


# ═══════════════════════════════════════════════════════════════════
#  10. MCP TOOL DESCRIPTIONS
# ═══════════════════════════════════════════════════════════════════

class TestToolDescriptions:
    """All tools must have informative descriptions."""

    @pytest.mark.asyncio
    async def test_all_tools_have_descriptions(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            tools = await client.list_tools()
            for tool in tools:
                assert tool.description and len(tool.description.strip()) > 10, (
                    f"MCP tool '{tool.name}' has missing or trivial description"
                )
