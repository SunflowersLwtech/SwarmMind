"""
Test Suite 05b: FunctionTool Closures (backend/agents/tools.py)
Regression tests for all 13 ADK tool closures — verifies closure binding,
return format, error handling, and world mutation visibility.

Refactored: removed partition_sectors, assign_sector, get_op_summary
(prescriptive planning / redundant composite tools removed from agent surface).
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from backend.core.grid_world import GridWorld
from backend.agents.tools import make_tools


@pytest.fixture
def world():
    return GridWorld(size=10, num_uavs=3, num_objectives=4, num_obstacles=5, seed=42)


@pytest.fixture
def tools(world):
    return make_tools(world)


@pytest.fixture
def tool_map(tools):
    """Name→function mapping for readable tests."""
    return {fn.__name__: fn for fn in tools}


# ── Smoke: all 13 returned ────────────────────────────────────

class TestToolFactory:
    def test_returns_13_tools(self, tools):
        assert len(tools) == 13

    def test_all_callable(self, tools):
        for fn in tools:
            assert callable(fn), f"{fn} is not callable"

    def test_all_have_docstrings(self, tools):
        for fn in tools:
            assert fn.__doc__, f"{fn.__name__} missing docstring"

    def test_names_unique(self, tools):
        names = [fn.__name__ for fn in tools]
        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"


# ── Category 1: Fleet Intelligence ────────────────────────────

class TestQueryFleet:
    def test_returns_ok(self, tool_map):
        result = tool_map["query_fleet"]()
        assert result["status"] == "ok"

    def test_data_has_total(self, tool_map):
        result = tool_map["query_fleet"]()
        assert result["data"]["total"] == 3

    def test_data_has_uavs(self, tool_map):
        result = tool_map["query_fleet"]()
        assert len(result["data"]["uavs"]) == 3


class TestInspectUav:
    def test_valid_uav(self, tool_map, world):
        uav_id = list(world.fleet.keys())[0]
        result = tool_map["inspect_uav"](uav_id)
        assert result["status"] == "ok"
        assert result["data"]["id"] == uav_id

    def test_invalid_uav(self, tool_map):
        result = tool_map["inspect_uav"]("GHOST")
        assert result["status"] == "error"
        assert "not found" in result["message"]


class TestGetThreatMap:
    def test_returns_ok(self, tool_map):
        result = tool_map["get_threat_map"]()
        assert result["status"] == "ok"
        assert "heatmap" in result["data"]
        assert "hotspots" in result["data"]


class TestGetSearchProgress:
    def test_returns_ok(self, tool_map):
        result = tool_map["get_search_progress"]()
        assert result["status"] == "ok"
        assert "coverage_pct" in result["data"]
        assert "objectives_found" in result["data"]


# ── Category 2: Navigation (waypoint-based) ───────────────────

class TestNavigateTo:
    def test_waypoint_valid(self, tool_map, world):
        uav_id = list(world.fleet.keys())[0]
        result = tool_map["navigate_to"](uav_id, 3, 3)
        assert result["status"] == "ok"

    def test_waypoint_invalid_uav(self, tool_map):
        result = tool_map["navigate_to"]("GHOST", 1, 1)
        assert result["status"] == "error"

    def test_waypoint_does_not_teleport(self, tool_map, world):
        """navigate_to must NOT move the UAV instantly (industry best practice)."""
        uav_id = list(world.fleet.keys())[0]
        pos_before = (world.fleet[uav_id].x, world.fleet[uav_id].y)
        tool_map["navigate_to"](uav_id, 3, 3)
        pos_after = (world.fleet[uav_id].x, world.fleet[uav_id].y)
        assert pos_before == pos_after, "navigate_to must NOT teleport the UAV"

    def test_waypoint_sets_path(self, tool_map, world):
        """navigate_to must set the UAV's path for autopilot execution."""
        uav_id = list(world.fleet.keys())[0]
        tool_map["navigate_to"](uav_id, 3, 3)
        assert len(world.fleet[uav_id].path) > 0, "Path must be set after navigate_to"

    def test_waypoint_sets_command_source(self, tool_map, world):
        """navigate_to must mark the UAV as agent-controlled."""
        uav_id = list(world.fleet.keys())[0]
        tool_map["navigate_to"](uav_id, 3, 3)
        assert world.fleet[uav_id].command_source == "agent"

    def test_waypoint_returns_eta(self, tool_map, world):
        """Result must include ETA and power cost estimate."""
        uav_id = list(world.fleet.keys())[0]
        result = tool_map["navigate_to"](uav_id, 3, 3)
        data = result["data"]
        assert data["estimated_eta"] > 0
        assert data["estimated_power_cost"] > 0
        assert data["current_position"] == [0, 0]

    def test_waypoint_does_not_consume_power(self, tool_map, world):
        """Power is consumed during autopilot execution, NOT at waypoint set time."""
        uav_id = list(world.fleet.keys())[0]
        power_before = world.fleet[uav_id].power
        tool_map["navigate_to"](uav_id, 3, 3)
        assert world.fleet[uav_id].power == power_before


class TestPlanRoute:
    def test_returns_ok(self, tool_map):
        result = tool_map["plan_route"](0, 0, 5, 5)
        assert result["status"] == "ok"
        assert len(result["data"]["path"]) > 0

    def test_does_not_move_uav(self, tool_map, world):
        uav_id = list(world.fleet.keys())[0]
        pos_before = (world.fleet[uav_id].x, world.fleet[uav_id].y)
        tool_map["plan_route"](0, 0, 5, 5)
        pos_after = (world.fleet[uav_id].x, world.fleet[uav_id].y)
        assert pos_before == pos_after


# ── Category 3: Reconnaissance ────────────────────────────────

class TestSweepScan:
    def test_returns_ok(self, tool_map, world):
        uav_id = list(world.fleet.keys())[0]
        result = tool_map["sweep_scan"](uav_id)
        assert result["status"] == "ok"
        assert "scanned_cells" in result["data"]

    def test_invalid_uav(self, tool_map):
        result = tool_map["sweep_scan"]("GHOST")
        assert result["status"] == "error"

    def test_increases_coverage(self, tool_map, world):
        """Use move_uav (direct) to position UAV, then scan."""
        uav_id = list(world.fleet.keys())[0]
        world.move_uav(uav_id, 5, 5)  # Direct move for test setup
        progress_before = world.get_search_progress().coverage_pct
        tool_map["sweep_scan"](uav_id)
        progress_after = world.get_search_progress().coverage_pct
        assert progress_after > progress_before


class TestDetectFrontier:
    def test_returns_ok(self, tool_map):
        result = tool_map["detect_frontier"]()
        assert result["status"] == "ok"
        assert isinstance(result["data"], list)
        assert "total_frontier" in result

    def test_frontier_not_empty_initially(self, tool_map):
        result = tool_map["detect_frontier"]()
        assert result["total_frontier"] > 0


class TestMarkObjective:
    def test_claim_nonexistent_objective(self, tool_map, world):
        uav_id = list(world.fleet.keys())[0]
        result = tool_map["mark_objective"]("FAKE-OBJ", uav_id)
        assert result["status"] == "error"


# ── Category 4: Resource Management ───────────────────────────

class TestRecallUav:
    def test_recall_sets_waypoint(self, tool_map, world):
        """recall_uav must set return path, NOT teleport to base."""
        uav_id = list(world.fleet.keys())[0]
        world.move_uav(uav_id, 4, 4)  # Direct move to field position
        result = tool_map["recall_uav"](uav_id)
        assert result["status"] == "ok"
        uav = world.fleet[uav_id]
        # UAV should NOT be at base yet — it has a waypoint path
        assert uav.status.value == "returning"
        assert uav.command_source == "agent"
        assert len(uav.path) > 0

    def test_invalid_uav(self, tool_map):
        result = tool_map["recall_uav"]("GHOST")
        assert result["status"] == "error"


class TestRepowerUav:
    def test_repower_at_base(self, tool_map, world):
        uav_id = list(world.fleet.keys())[0]
        # Use direct methods for test setup (not waypoint tools)
        world.move_uav(uav_id, 5, 5)
        world.recall_uav(uav_id)  # Direct recall (teleports for test setup)
        power_before = world.fleet[uav_id].power
        result = tool_map["repower_uav"](uav_id)
        assert result["status"] == "ok"
        assert result["data"]["new_power"] > power_before

    def test_invalid_uav(self, tool_map):
        result = tool_map["repower_uav"]("GHOST")
        assert result["status"] == "error"


class TestAssessEndurance:
    def test_returns_ok(self, tool_map):
        result = tool_map["assess_endurance"]()
        assert result["status"] == "ok"
        assert len(result["data"]) == 3  # 3 UAVs

    def test_has_endurance_fields(self, tool_map):
        result = tool_map["assess_endurance"]()
        entry = result["data"][0]
        for field in ["uav_id", "power", "cells_remaining", "distance_to_base",
                       "power_to_return", "safe_to_recall", "urgent_recall"]:
            assert field in entry, f"Missing field: {field}"


# ── Category 5: Situational Awareness (composite) ─────────────

class TestGetSituationalAwareness:
    def test_returns_ok(self, tool_map):
        result = tool_map["get_situational_awareness"]()
        assert result["status"] == "ok"

    def test_contains_fleet(self, tool_map):
        result = tool_map["get_situational_awareness"]()
        assert "fleet" in result["data"]
        assert "uavs" in result["data"]["fleet"]

    def test_contains_progress(self, tool_map):
        result = tool_map["get_situational_awareness"]()
        assert "progress" in result["data"]
        assert "coverage_pct" in result["data"]["progress"]

    def test_contains_hotspots(self, tool_map):
        result = tool_map["get_situational_awareness"]()
        assert "hotspots" in result["data"]

    def test_contains_endurance(self, tool_map):
        result = tool_map["get_situational_awareness"]()
        assert "endurance" in result["data"]
        assert len(result["data"]["endurance"]) == 3  # 3 UAVs

    def test_replaces_four_separate_calls(self, tool_map):
        """Composite tool must return equivalent data to 4 separate calls."""
        sa = tool_map["get_situational_awareness"]()["data"]
        fleet = tool_map["query_fleet"]()["data"]
        progress = tool_map["get_search_progress"]()["data"]
        endurance = tool_map["assess_endurance"]()["data"]

        assert sa["fleet"]["total"] == fleet["total"]
        assert sa["progress"]["coverage_pct"] == progress["coverage_pct"]
        assert len(sa["endurance"]) == len(endurance)


# ── Closure binding: tools see world mutations ────────────────

class TestClosureBinding:
    def test_waypoint_visible_across_tools(self, tool_map, world):
        """navigate_to sets waypoint; fleet query should still work on same world."""
        uav_id = list(world.fleet.keys())[0]
        tool_map["navigate_to"](uav_id, 4, 4)
        result = tool_map["query_fleet"]()
        uav_data = [u for u in result["data"]["uavs"] if u["id"] == uav_id][0]
        # UAV hasn't moved yet (waypoint), still at origin
        assert uav_data["x"] == 0
        assert uav_data["y"] == 0
        # But path should be set on the world object
        assert len(world.fleet[uav_id].path) > 0

    def test_two_tool_sets_share_world(self, world):
        """Two make_tools() calls on same world should see each other's mutations."""
        tools_a = make_tools(world)
        tools_b = make_tools(world)
        map_a = {fn.__name__: fn for fn in tools_a}
        map_b = {fn.__name__: fn for fn in tools_b}

        uav_id = list(world.fleet.keys())[0]
        map_a["navigate_to"](uav_id, 3, 3)

        # Both tool sets should see the path set on the shared world
        assert len(world.fleet[uav_id].path) > 0
        result = map_b["query_fleet"]()
        uav_data = [u for u in result["data"]["uavs"] if u["id"] == uav_id][0]
        assert uav_data["command_source"] == "agent"

    def test_different_worlds_isolated(self):
        """Tools from different worlds should NOT see each other's mutations."""
        world_a = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=1)
        world_b = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=1)
        map_a = {fn.__name__: fn for fn in make_tools(world_a)}
        map_b = {fn.__name__: fn for fn in make_tools(world_b)}

        uav_id = list(world_a.fleet.keys())[0]
        map_a["navigate_to"](uav_id, 3, 3)

        # world_b should be unaffected
        assert len(world_b.fleet[uav_id].path) == 0
        assert world_b.fleet[uav_id].command_source == "autopilot"
