"""
Test Suite 12: Tool Surface Regression Guard

Strict contract tests that prevent accidental regression of the MCP tool
refactoring. These tests enforce:

1. FROZEN TOOL SET — exactly 13 operational tools, no more, no less
2. REMOVED TOOLS BANNED — 6 removed tools must never reappear on agent surface
3. MCP ↔ ADK PARITY — both surfaces expose identical tool names
4. RESPONSE CONTRACT — every tool returns {"status": "ok"|"error", ...}
5. TOOL IDEMPOTENCY — read-only tools return stable results across calls
6. ERROR CONTRACT — invalid inputs produce structured errors, not crashes
7. PROMPT CONTRACT — prompts reference only available tools, never removed ones
8. COMPOSITE COMPLETENESS — get_situational_awareness subsumes get_op_summary
9. STRATEGIST AUTONOMY — agent decides strategy via frontier, not fixed sectors
10. INTERNAL METHODS PRESERVED — GridWorld internals still work for autopilot

DO NOT weaken these tests. If a test fails, the code must change, not the test.
"""
import json
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.agents.tools import make_tools
from backend.core.grid_world import GridWorld


# ─── Constants ────────────────────────────────────────────────────

# The canonical set of 13 operational tools. Any change requires updating
# BOTH the code AND this constant — that friction is intentional.
OPERATIONAL_TOOLS = frozenset({
    # Category 1: Fleet Intelligence
    "query_fleet",
    "inspect_uav",
    "get_threat_map",
    "get_search_progress",
    # Category 2: Navigation
    "navigate_to",
    "plan_route",
    # Category 3: Reconnaissance
    "sweep_scan",
    "detect_frontier",
    "mark_objective",
    # Category 4: Resource Management
    "recall_uav",
    "repower_uav",
    "assess_endurance",
    # Category 5: Situational Awareness
    "get_situational_awareness",
})

# Tools removed during refactoring — must NEVER reappear on agent surface.
BANNED_TOOLS = frozenset({
    # Admin/simulation tools (least-privilege violation)
    "init_scenario",
    "deploy_uav",
    "inject_event",
    # Prescriptive planning tools (limits agent autonomy)
    "partition_sectors",
    "assign_sector",
    # Redundant composite (subsumed by get_situational_awareness)
    "get_op_summary",
})


# ─── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def world():
    return GridWorld(size=10, num_uavs=3, num_objectives=4, num_obstacles=5, seed=42)


@pytest.fixture
def tool_map(world):
    tools = make_tools(world)
    return {fn.__name__: fn for fn in tools}


@pytest.fixture
def adk_tool_names(world):
    return {fn.__name__ for fn in make_tools(world)}


@pytest.fixture
def prompts():
    path = os.path.join(os.path.dirname(__file__), "../../backend/agents/prompts.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


# ═══════════════════════════════════════════════════════════════════
#  1. FROZEN TOOL SET — exactly 13 tools
# ═══════════════════════════════════════════════════════════════════

class TestFrozenToolSet:
    """The agent must see exactly 13 tools — no more, no less."""

    @pytest.mark.asyncio
    async def test_mcp_exposes_exactly_13_tools(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            tools = await client.list_tools()
            assert len(tools) == 13, (
                f"Expected exactly 13 MCP tools, got {len(tools)}: "
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

    def test_adk_exposes_exactly_13_tools(self, world):
        tools = make_tools(world)
        assert len(tools) == 13, (
            f"Expected exactly 13 ADK tools, got {len(tools)}: "
            f"{sorted(fn.__name__ for fn in tools)}"
        )

    def test_adk_tool_names_match_contract(self, adk_tool_names):
        assert adk_tool_names == OPERATIONAL_TOOLS, (
            f"ADK tool set mismatch.\n"
            f"  Missing: {OPERATIONAL_TOOLS - adk_tool_names}\n"
            f"  Unexpected: {adk_tool_names - OPERATIONAL_TOOLS}"
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

    def test_adk_has_no_banned_tools(self, adk_tool_names):
        leaked = adk_tool_names & BANNED_TOOLS
        assert not leaked, (
            f"BANNED tools leaked onto ADK surface: {leaked}\n"
            f"These tools were removed for security/design reasons."
        )

    @pytest.mark.asyncio
    async def test_calling_banned_tool_via_mcp_fails(self):
        """Attempting to invoke a removed tool must raise or error, not silently succeed."""
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            for tool_name in BANNED_TOOLS:
                with pytest.raises(Exception):
                    await client.call_tool(tool_name, {})

    def test_no_admin_guard_infrastructure_in_tool_server(self):
        """The RBAC guard code must be fully removed, not just disabled."""
        import inspect
        from backend.services import tool_server

        source = inspect.getsource(tool_server)
        assert "_admin_mode" not in source, (
            "Residual _admin_mode variable found — admin guard infrastructure "
            "should be fully removed, not just disabled."
        )
        assert "SWARMMIND_ADMIN_TOOLS" not in source, (
            "Residual SWARMMIND_ADMIN_TOOLS reference — env var guard "
            "should be fully removed."
        )
        assert "_require_admin" not in source, (
            "Residual _require_admin function — admin guard helper "
            "should be fully removed."
        )


# ═══════════════════════════════════════════════════════════════════
#  3. MCP ↔ ADK PARITY
# ═══════════════════════════════════════════════════════════════════

class TestMCPADKParity:
    """MCP server and ADK tool closures must expose the identical tool set."""

    @pytest.mark.asyncio
    async def test_same_tool_names(self, adk_tool_names):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            tools = await client.list_tools()
            mcp_names = {t.name for t in tools}
            assert mcp_names == adk_tool_names, (
                f"MCP and ADK tool sets diverged.\n"
                f"  MCP only: {mcp_names - adk_tool_names}\n"
                f"  ADK only: {adk_tool_names - mcp_names}"
            )

    def test_adk_tools_all_have_docstrings(self, world):
        for fn in make_tools(world):
            assert fn.__doc__ and len(fn.__doc__.strip()) > 10, (
                f"Tool '{fn.__name__}' has missing or trivial docstring"
            )

    @pytest.mark.asyncio
    async def test_mcp_tools_all_have_descriptions(self):
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            tools = await client.list_tools()
            for tool in tools:
                assert tool.description and len(tool.description.strip()) > 10, (
                    f"MCP tool '{tool.name}' has missing or trivial description"
                )


# ═══════════════════════════════════════════════════════════════════
#  4. RESPONSE CONTRACT — every tool returns {"status": ...}
# ═══════════════════════════════════════════════════════════════════

class TestResponseContract:
    """Every tool must return a dict with 'status' key of 'ok' or 'error'."""

    # Parameterless tools — can call with no arguments
    ZERO_ARG_TOOLS = [
        "query_fleet", "get_threat_map", "get_search_progress",
        "detect_frontier", "assess_endurance", "get_situational_awareness",
    ]

    @pytest.mark.parametrize("tool_name", ZERO_ARG_TOOLS)
    def test_zero_arg_tool_returns_status_ok(self, tool_map, tool_name):
        result = tool_map[tool_name]()
        assert isinstance(result, dict), f"{tool_name} must return dict"
        assert result["status"] == "ok", f"{tool_name} returned: {result}"

    @pytest.mark.parametrize("tool_name", ZERO_ARG_TOOLS)
    def test_zero_arg_tool_has_data_or_message(self, tool_map, tool_name):
        result = tool_map[tool_name]()
        has_payload = "data" in result or "message" in result or "total_frontier" in result
        assert has_payload, f"{tool_name} response has no data payload: {result.keys()}"

    def test_navigate_to_returns_status(self, tool_map, world):
        uav_id = list(world.fleet.keys())[0]
        result = tool_map["navigate_to"](uav_id, 3, 3)
        assert "status" in result
        assert result["status"] in ("ok", "error")

    def test_sweep_scan_returns_status(self, tool_map, world):
        uav_id = list(world.fleet.keys())[0]
        result = tool_map["sweep_scan"](uav_id)
        assert result["status"] == "ok"
        assert "scanned_cells" in result["data"]

    def test_plan_route_returns_status(self, tool_map):
        result = tool_map["plan_route"](0, 0, 5, 5)
        assert result["status"] == "ok"
        assert "path" in result["data"]

    @pytest.mark.asyncio
    async def test_all_mcp_parameterless_tools_return_valid_json(self):
        """MCP wire format: every tool returns parseable JSON with 'status'."""
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            for tool_name in self.ZERO_ARG_TOOLS:
                result = await client.call_tool(tool_name, {})
                data = json.loads(result.content[0].text)
                assert "status" in data, f"MCP {tool_name} missing 'status'"
                assert data["status"] == "ok", f"MCP {tool_name}: {data}"


# ═══════════════════════════════════════════════════════════════════
#  5. TOOL IDEMPOTENCY — read-only tools return stable results
# ═══════════════════════════════════════════════════════════════════

class TestToolIdempotency:
    """Read-only tools must return identical results when called twice."""

    READ_ONLY_TOOLS = [
        "query_fleet", "get_threat_map", "get_search_progress",
        "detect_frontier", "assess_endurance", "get_situational_awareness",
    ]

    @pytest.mark.parametrize("tool_name", READ_ONLY_TOOLS)
    def test_read_only_tool_is_idempotent(self, tool_map, tool_name):
        r1 = tool_map[tool_name]()
        r2 = tool_map[tool_name]()
        assert r1 == r2, (
            f"{tool_name} is not idempotent — returned different results on consecutive calls"
        )

    def test_inspect_uav_idempotent(self, tool_map, world):
        uav_id = list(world.fleet.keys())[0]
        r1 = tool_map["inspect_uav"](uav_id)
        r2 = tool_map["inspect_uav"](uav_id)
        assert r1 == r2

    def test_plan_route_idempotent(self, tool_map):
        r1 = tool_map["plan_route"](0, 0, 5, 5)
        r2 = tool_map["plan_route"](0, 0, 5, 5)
        assert r1 == r2


# ═══════════════════════════════════════════════════════════════════
#  6. ERROR CONTRACT — invalid inputs → structured errors
# ═══════════════════════════════════════════════════════════════════

class TestErrorContract:
    """Invalid inputs must return {"status": "error", "message": "..."}, never crash."""

    GHOST_UAV = "GHOST-999"

    def test_inspect_uav_invalid_id(self, tool_map):
        result = tool_map["inspect_uav"](self.GHOST_UAV)
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_navigate_to_invalid_id(self, tool_map):
        result = tool_map["navigate_to"](self.GHOST_UAV, 1, 1)
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_sweep_scan_invalid_id(self, tool_map):
        result = tool_map["sweep_scan"](self.GHOST_UAV)
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_recall_uav_invalid_id(self, tool_map):
        result = tool_map["recall_uav"](self.GHOST_UAV)
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_repower_uav_invalid_id(self, tool_map):
        result = tool_map["repower_uav"](self.GHOST_UAV)
        assert result["status"] == "error"
        assert "not found" in result["message"].lower()

    def test_mark_objective_invalid_id(self, tool_map, world):
        uav_id = list(world.fleet.keys())[0]
        result = tool_map["mark_objective"]("FAKE-OBJ-999", uav_id)
        assert result["status"] == "error"

    def test_navigate_to_blocked_cell(self, tool_map, world):
        """Navigating to an obstacle must return error, not crash."""
        import numpy as np
        uav_id = list(world.fleet.keys())[0]
        obstacles = np.argwhere(world.terrain.obstacle_grid)
        if len(obstacles) > 0:
            ox, oy = obstacles[0]
            result = tool_map["navigate_to"](uav_id, int(ox), int(oy))
            assert result["status"] == "error"

    def test_plan_route_out_of_bounds(self, tool_map):
        result = tool_map["plan_route"](0, 0, 999, 999)
        # Should return error or empty path, not crash
        assert isinstance(result, dict)
        assert "status" in result

    @pytest.mark.asyncio
    async def test_mcp_invalid_uav_returns_error_json(self):
        """Invalid inputs over MCP wire must return error JSON, not 500."""
        from backend.services.tool_server import mcp
        from fastmcp import Client

        async with Client(mcp) as client:
            result = await client.call_tool("inspect_uav", {"uav_id": self.GHOST_UAV})
            data = json.loads(result.content[0].text)
            assert data["status"] == "error"
            assert "not found" in data["message"].lower()


# ═══════════════════════════════════════════════════════════════════
#  7. PROMPT CONTRACT — reference only available tools
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
                f"Prompt '{stage}' references banned tool '{banned}' — "
                f"this tool was removed and must not be suggested to the agent."
            )

    def test_prompts_only_reference_available_tools(self, prompts):
        """Every backtick-quoted tool name in prompts must be in OPERATIONAL_TOOLS."""
        import re
        for stage in self.STAGES:
            instruction = prompts[stage]["instruction"]
            # Extract `tool_name` patterns
            referenced = set(re.findall(r"`(\w+)`", instruction))
            for ref in referenced:
                # Filter out non-tool references (status values, etc.)
                if ref in ("ok", "error", "status", "assessment", "strategy",
                           "execution_log", "report"):
                    continue
                assert ref in OPERATIONAL_TOOLS, (
                    f"Prompt '{stage}' references `{ref}` which is not in "
                    f"OPERATIONAL_TOOLS. Either add it to the tool set or "
                    f"remove it from the prompt."
                )

    def test_strategist_uses_frontier_not_sectors(self, prompts):
        """Strategist must use detect_frontier for autonomous planning."""
        instruction = prompts["strategist"]["instruction"]
        assert "detect_frontier" in instruction, (
            "Strategist must reference detect_frontier for autonomous exploration"
        )
        assert "partition_sectors" not in instruction, (
            "Strategist must NOT reference partition_sectors (removed)"
        )
        assert "assign_sector" not in instruction, (
            "Strategist must NOT reference assign_sector (removed)"
        )

    def test_dispatcher_does_not_reference_assign_sector(self, prompts):
        instruction = prompts["dispatcher"]["instruction"]
        assert "assign_sector" not in instruction

    def test_analyst_uses_situational_awareness(self, prompts):
        instruction = prompts["analyst"]["instruction"]
        assert "get_situational_awareness" in instruction
        assert "get_op_summary" not in instruction


# ═══════════════════════════════════════════════════════════════════
#  8. COMPOSITE COMPLETENESS — get_situational_awareness subsumes
# ═══════════════════════════════════════════════════════════════════

class TestCompositeCompleteness:
    """get_situational_awareness must cover all data get_op_summary provided."""

    def test_contains_tick(self, tool_map):
        result = tool_map["get_situational_awareness"]()
        assert "tick" in result["data"]

    def test_contains_mission_status(self, tool_map):
        result = tool_map["get_situational_awareness"]()
        assert "mission_status" in result["data"]

    def test_contains_fleet_with_totals(self, tool_map):
        """Must include fleet total/active/avg_power (what get_op_summary had)."""
        data = tool_map["get_situational_awareness"]()["data"]
        fleet = data["fleet"]
        assert "total" in fleet
        assert "active" in fleet
        assert "avg_power" in fleet

    def test_contains_coverage(self, tool_map):
        """Must include coverage_pct (what get_op_summary had)."""
        data = tool_map["get_situational_awareness"]()["data"]
        assert "coverage_pct" in data["progress"]

    def test_contains_objectives_count(self, tool_map):
        """Must include objectives_found/total (what get_op_summary had)."""
        data = tool_map["get_situational_awareness"]()["data"]
        progress = data["progress"]
        assert "objectives_found" in progress
        assert "objectives_total" in progress

    def test_contains_endurance(self, tool_map):
        data = tool_map["get_situational_awareness"]()["data"]
        assert "endurance" in data
        assert len(data["endurance"]) > 0

    def test_contains_hotspots(self, tool_map):
        """Extra data that get_op_summary didn't have — bonus."""
        data = tool_map["get_situational_awareness"]()["data"]
        assert "hotspots" in data

    def test_equivalence_with_individual_tools(self, tool_map):
        """Composite must return consistent data with individual tools."""
        sa = tool_map["get_situational_awareness"]()["data"]
        fleet = tool_map["query_fleet"]()["data"]
        progress = tool_map["get_search_progress"]()["data"]
        endurance = tool_map["assess_endurance"]()["data"]

        assert sa["fleet"]["total"] == fleet["total"]
        assert sa["fleet"]["active"] == fleet["active"]
        assert sa["progress"]["coverage_pct"] == progress["coverage_pct"]
        assert sa["progress"]["objectives_found"] == progress["objectives_found"]
        assert len(sa["endurance"]) == len(endurance)


# ═══════════════════════════════════════════════════════════════════
#  9. STRATEGIST AUTONOMY — no prescriptive planning
# ═══════════════════════════════════════════════════════════════════

class TestStrategistAutonomy:
    """Agent must decide strategy autonomously — no fixed grid partitioning."""

    def test_detect_frontier_provides_ranked_targets(self, tool_map):
        """detect_frontier must return priority-sorted cells for autonomous planning."""
        result = tool_map["detect_frontier"]()
        assert result["status"] == "ok"
        data = result["data"]
        assert len(data) > 0, "Frontier must not be empty on fresh world"
        # Verify sorted by priority descending
        priorities = [cell["priority"] for cell in data]
        assert priorities == sorted(priorities, reverse=True), (
            "Frontier cells must be sorted by priority descending"
        )

    def test_detect_frontier_cells_have_coordinates(self, tool_map):
        result = tool_map["detect_frontier"]()
        for cell in result["data"]:
            assert "x" in cell and "y" in cell, f"Frontier cell missing coordinates: {cell}"
            assert "priority" in cell, f"Frontier cell missing priority: {cell}"

    def test_plan_route_enables_cost_comparison(self, tool_map):
        """plan_route must return power_cost so agent can compare options."""
        result = tool_map["plan_route"](0, 0, 5, 5)
        data = result["data"]
        assert "power_cost" in data
        assert "distance" in data
        assert "path" in data

    def test_endurance_enables_recall_decisions(self, tool_map):
        """assess_endurance must return safe_to_recall so agent can decide."""
        result = tool_map["assess_endurance"]()
        for entry in result["data"]:
            assert "safe_to_recall" in entry
            assert "urgent_recall" in entry
            assert "power_to_return" in entry


# ═══════════════════════════════════════════════════════════════════
#  10. INTERNAL METHODS PRESERVED — autopilot still works
# ═══════════════════════════════════════════════════════════════════

class TestInternalMethodsPreserved:
    """GridWorld internal methods must still work — they're used by autopilot.

    These are NOT exposed as MCP tools but are called by GridWorld.step().
    """

    def test_partition_sectors_works_internally(self, world):
        """partition_sectors removed from MCP but still needed by GridWorld."""
        sectors = world.partition_sectors(4)
        assert len(sectors) == 4
        for sid, sector in sectors.items():
            assert hasattr(sector, "x_min")
            assert hasattr(sector, "priority")

    def test_add_uav_works_internally(self, world):
        """add_uav removed from MCP but still needed by GridWorld.__init__."""
        uav = world.add_uav("Zulu")
        assert uav.id == "Zulu"
        assert uav.id in world.fleet

    def test_autopilot_tick_still_runs(self, world):
        """Autopilot loop must still function without sector tools on MCP."""
        world.mission_status = "running"
        for _ in range(5):
            result = world.step()
            assert result.tick > 0

    def test_state_snapshot_still_serializable(self, world):
        """Frontend snapshot must still include all required fields."""
        snapshot = world.get_state_snapshot()
        assert "fleet" in snapshot
        assert "coverage_pct" in snapshot
        assert "objectives" in snapshot
        assert "heatmap" in snapshot

    def test_move_uav_direct_still_works(self, world):
        """Direct move_uav (used by tests) must still function."""
        uav_id = list(world.fleet.keys())[0]
        result = world.move_uav(uav_id, 3, 0)
        assert result.new_position == [3, 0]

    def test_recall_uav_direct_still_works(self, world):
        """Direct recall_uav (teleport, used by tests) must still function."""
        uav_id = list(world.fleet.keys())[0]
        world.move_uav(uav_id, 3, 0)
        result = world.recall_uav(uav_id)
        uav = world.fleet[uav_id]
        assert (uav.x, uav.y) == (0, 0)


# ═══════════════════════════════════════════════════════════════════
#  11. WRITE-TOOL MUTATION SAFETY
# ═══════════════════════════════════════════════════════════════════

class TestWriteToolMutationSafety:
    """Write tools must only mutate the intended UAV/objective."""

    def test_navigate_to_only_affects_target_uav(self, tool_map, world):
        uav_ids = list(world.fleet.keys())
        # Snapshot all UAVs before
        before = {uid: (world.fleet[uid].x, world.fleet[uid].y) for uid in uav_ids}
        # Navigate only the first UAV
        tool_map["navigate_to"](uav_ids[0], 4, 4)
        # Others must be unchanged
        for uid in uav_ids[1:]:
            uav = world.fleet[uid]
            assert (uav.x, uav.y) == before[uid], (
                f"navigate_to({uav_ids[0]}) mutated {uid}"
            )

    def test_sweep_scan_only_affects_target_uav_power(self, tool_map, world):
        uav_ids = list(world.fleet.keys())
        powers_before = {uid: world.fleet[uid].power for uid in uav_ids}
        tool_map["sweep_scan"](uav_ids[0])
        for uid in uav_ids[1:]:
            assert world.fleet[uid].power == powers_before[uid], (
                f"sweep_scan({uav_ids[0]}) drained power from {uid}"
            )

    def test_recall_uav_only_affects_target_uav(self, tool_map, world):
        uav_ids = list(world.fleet.keys())
        # Move first UAV out, then recall
        world.move_uav(uav_ids[0], 4, 4)
        statuses_before = {uid: world.fleet[uid].status.value for uid in uav_ids[1:]}
        tool_map["recall_uav"](uav_ids[0])
        for uid in uav_ids[1:]:
            assert world.fleet[uid].status.value == statuses_before[uid], (
                f"recall_uav({uav_ids[0]}) changed status of {uid}"
            )


# ═══════════════════════════════════════════════════════════════════
#  12. TOOL DOCSTRING QUALITY
# ═══════════════════════════════════════════════════════════════════

class TestToolDocstringQuality:
    """Operational tool docstrings must be informative and free of admin language."""

    def test_no_admin_language_in_docstrings(self, world):
        """Operational tools must not contain '[ADMIN]' or 'simulation' in descriptions."""
        for fn in make_tools(world):
            doc = fn.__doc__ or ""
            assert "[ADMIN]" not in doc, (
                f"Tool '{fn.__name__}' has admin marker in docstring"
            )
            assert "simulation" not in doc.lower() or "NOT instant" in doc, (
                f"Tool '{fn.__name__}' mentions 'simulation' — operational tools "
                f"should describe real behavior, not simulation mechanics"
            )

    @pytest.mark.asyncio
    async def test_mcp_descriptions_match_adk_docstrings(self):
        """MCP descriptions should be semantically consistent with ADK docstrings."""
        from backend.services.tool_server import mcp
        from fastmcp import Client

        world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)
        adk_docs = {fn.__name__: fn.__doc__.strip() for fn in make_tools(world)}

        async with Client(mcp) as client:
            tools = await client.list_tools()
            for tool in tools:
                if tool.name in adk_docs:
                    # First sentence should be similar (both describe the same action)
                    mcp_first = tool.description.split(".")[0].lower()
                    adk_first = adk_docs[tool.name].split(".")[0].lower()
                    # At minimum, both should reference the same verb/noun
                    # Descriptions should share significant words
                    mcp_words = set(mcp_first.split())
                    adk_words = set(adk_first.split())
                    # Ignore short words (articles, prepositions)
                    significant = {w for w in (mcp_words & adk_words) if len(w) > 3}
                    assert len(significant) >= 2, (
                        f"Tool '{tool.name}': MCP and ADK descriptions diverged.\n"
                        f"  MCP: {mcp_first}\n  ADK: {adk_first}\n"
                        f"  Shared words: {significant}"
                    )
