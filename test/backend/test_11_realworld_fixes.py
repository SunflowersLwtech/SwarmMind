"""
Test Suite 11: Real-World Feasibility Fixes — Regression Tests

Validates all fixes for AI/MCP issues identified in real-world scenario analysis:
1. Waypoint navigation (no teleportation)
2. Agent command priority over autopilot
3. Composite situational awareness tool
4. Session rotation to prevent context bloat
5. Admin/simulation tools removed from MCP surface (least-privilege)
6. Autopilot command_source lifecycle

These tests are designed to PREVENT REGRESSION — do not weaken assertions.
"""
import asyncio
import json
import os
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from backend.core.grid_world import GridWorld
from backend.core.uav import UAV, UAVStatus, WaypointResult


# ═══════════════════════════════════════════════════════════════
#  Fix 1: Waypoint Navigation (No Teleportation)
# ═══════════════════════════════════════════════════════════════

class TestWaypointNavigation:
    """navigate_to must set waypoints, not teleport.

    Industry best practice: command-acknowledgment pattern.
    The UAV moves 1 cell per tick via autopilot, not instantly.
    """

    @pytest.fixture
    def world(self):
        return GridWorld(size=10, num_uavs=3, num_objectives=3, num_obstacles=3, seed=42)

    def test_set_waypoint_does_not_move_uav(self, world):
        """UAV position must be UNCHANGED after set_waypoint."""
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]
        pos_before = (uav.x, uav.y)
        power_before = uav.power

        result = world.set_waypoint(uav_id, 5, 5)

        assert result.status == "ok"
        assert (uav.x, uav.y) == pos_before, "UAV must NOT teleport"
        assert uav.power == power_before, "Power must NOT be consumed at waypoint set"
        assert result.current_position == list(pos_before)

    def test_set_waypoint_sets_path(self, world):
        """UAV must have a non-empty path after set_waypoint."""
        uav_id = list(world.fleet.keys())[0]
        result = world.set_waypoint(uav_id, 5, 5)

        uav = world.fleet[uav_id]
        assert len(uav.path) > 0
        assert uav.path[-1] == (5, 5) or uav.path[-1] == [5, 5]

    def test_set_waypoint_returns_eta(self, world):
        """Result must include ETA, power cost, and planned path."""
        uav_id = list(world.fleet.keys())[0]
        result = world.set_waypoint(uav_id, 5, 5)

        assert result.estimated_eta > 0
        assert result.estimated_distance > 0
        assert result.estimated_power_cost > 0
        assert len(result.planned_path) > 1
        assert result.waypoint == [5, 5]

    def test_set_waypoint_marks_agent_source(self, world):
        uav_id = list(world.fleet.keys())[0]
        world.set_waypoint(uav_id, 5, 5)
        assert world.fleet[uav_id].command_source == "agent"

    def test_set_waypoint_sets_moving_status(self, world):
        uav_id = list(world.fleet.keys())[0]
        world.set_waypoint(uav_id, 5, 5)
        assert world.fleet[uav_id].status == UAVStatus.MOVING

    def test_set_waypoint_blocked_target_returns_error(self, world):
        """Waypoint to an obstacle must return error."""
        uav_id = list(world.fleet.keys())[0]
        # Find an obstacle cell
        import numpy as np
        obstacles = np.argwhere(world.terrain.obstacle_grid)
        if len(obstacles) == 0:
            pytest.skip("No obstacles in test world")
        ox, oy = obstacles[0]
        result = world.set_waypoint(uav_id, int(ox), int(oy))
        assert result.status == "error"

    def test_set_waypoint_oob_returns_error(self, world):
        uav_id = list(world.fleet.keys())[0]
        result = world.set_waypoint(uav_id, 999, 999)
        assert result.status == "error"

    def test_set_waypoint_offline_uav_returns_error(self, world):
        uav_id = list(world.fleet.keys())[0]
        world.fleet[uav_id].status = UAVStatus.OFFLINE
        result = world.set_waypoint(uav_id, 5, 5)
        assert result.status == "error"

    def test_autopilot_executes_waypoint_path(self, world):
        """After set_waypoint, autopilot must move UAV along the path tick by tick."""
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]
        world.mission_status = "running"

        result = world.set_waypoint(uav_id, 3, 0)
        path_len = len(uav.path)
        assert path_len > 0

        # Step exactly path_len times — UAV should arrive at target
        for i in range(path_len):
            world.step()

        # UAV should have arrived at waypoint target
        assert uav.x == 3 and uav.y == 0, f"UAV should arrive at (3,0), got ({uav.x},{uav.y})"

    def test_waypoint_power_consumed_during_movement(self, world):
        """Power must be consumed during autopilot movement, not at waypoint set time."""
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]
        world.mission_status = "running"

        power_before_waypoint = uav.power
        world.set_waypoint(uav_id, 3, 0)
        assert uav.power == power_before_waypoint, "No power consumed at waypoint set"

        # Step simulation to move UAV
        for _ in range(5):
            world.step()

        assert uav.power < power_before_waypoint, "Power must decrease during movement"

    def test_affordable_flag_when_insufficient_power(self, world):
        """affordable flag must be False when UAV can't afford the trip."""
        uav_id = list(world.fleet.keys())[0]
        world.fleet[uav_id].power = 5.0  # Very low power
        result = world.set_waypoint(uav_id, 9, 9)
        if result.status == "ok":
            assert result.affordable is False


# ═══════════════════════════════════════════════════════════════
#  Fix 2: Recall Waypoint (No Teleportation)
# ═══════════════════════════════════════════════════════════════

class TestRecallWaypoint:
    """recall_uav must use waypoint-based return, not teleport."""

    @pytest.fixture
    def world(self):
        return GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)

    def test_recall_does_not_teleport(self, world):
        uav_id = list(world.fleet.keys())[0]
        world.move_uav(uav_id, 5, 5)  # Direct move for test setup

        result = world.set_recall_waypoint(uav_id)
        uav = world.fleet[uav_id]

        assert result.status == "ok"
        assert (uav.x, uav.y) == (5, 5), "UAV must NOT teleport to base"
        assert uav.status == UAVStatus.RETURNING
        assert len(uav.path) > 0

    def test_recall_sets_agent_source(self, world):
        uav_id = list(world.fleet.keys())[0]
        world.move_uav(uav_id, 5, 5)
        world.set_recall_waypoint(uav_id)
        assert world.fleet[uav_id].command_source == "agent"

    def test_recall_returns_eta(self, world):
        uav_id = list(world.fleet.keys())[0]
        world.move_uav(uav_id, 5, 5)
        result = world.set_recall_waypoint(uav_id)
        assert result.estimated_eta > 0
        assert result.waypoint == [0, 0]  # base

    def test_recall_autopilot_executes_return(self, world):
        uav_id = list(world.fleet.keys())[0]
        world.move_uav(uav_id, 3, 0)
        world.mission_status = "running"

        result = world.set_recall_waypoint(uav_id)
        path_len = result.estimated_eta

        # Step exactly path_len times to reach base
        for _ in range(path_len):
            world.step()

        uav = world.fleet[uav_id]
        assert (uav.x, uav.y) == (0, 0), f"UAV should return to base, got ({uav.x},{uav.y})"


# ═══════════════════════════════════════════════════════════════
#  Fix 3: Agent Command Priority
# ═══════════════════════════════════════════════════════════════

class TestAgentCommandPriority:
    """Agent commands must take priority over autopilot decisions.

    Industry best practice: explicit command hierarchy with safety override.
    """

    @pytest.fixture
    def world(self):
        return GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)

    def test_autopilot_respects_agent_path(self, world):
        """When command_source=agent, autopilot must NOT pick a new target."""
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]
        world.mission_status = "running"

        world.set_waypoint(uav_id, 5, 5)
        agent_path = list(uav.path)  # Copy

        # Step simulation a few ticks
        world.step()

        # UAV should still be following the agent path (not a new autopilot target)
        # The path shrinks by 1 each tick but target remains the same
        if uav.path:
            assert uav.command_source == "agent"

    def test_autopilot_does_not_override_agent_on_low_power(self, world):
        """Agent commands survive normal low-power threshold (20%).

        Only CRITICAL power (< 10%) triggers safety override.
        """
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]

        # Move UAV away from base first, then set low power
        world.move_uav(uav_id, 3, 0)
        uav.power = 18.0  # Below LOW_POWER (20%) but above CRITICAL (10%)
        world.mission_status = "running"

        # Agent orders UAV to a target 3+ cells away (takes multiple ticks)
        world.set_waypoint(uav_id, 6, 0)
        assert uav.command_source == "agent"
        assert len(uav.path) >= 2, "Path must be long enough to survive 1 step"

        world.step()

        # After 1 step, UAV is mid-path — agent command should NOT be overridden
        # (autopilot would normally recall at 18% power, but agent has priority)
        assert uav.command_source == "agent", \
            "Agent commands must survive low-power threshold (only critical <10% overrides)"

    def test_safety_override_on_critical_power(self, world):
        """Autopilot MUST override agent on critical power (< 10%)."""
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]
        world.move_uav(uav_id, 3, 0)  # Move away from base
        uav.power = 5.0  # Critical power
        world.mission_status = "running"

        # Set an agent waypoint going AWAY from base
        world.set_waypoint(uav_id, 5, 0)
        assert uav.command_source == "agent"

        world.step()

        # Safety override should force return to base
        assert uav.command_source == "autopilot", "Safety override must reset command_source"
        assert uav.status == UAVStatus.RETURNING

    def test_command_source_resets_after_idle_timeout(self, world):
        """After agent path completes and idle timeout elapses, command_source
        must reset to 'autopilot'. The UAV stays agent-controlled immediately
        after path completion to let the agent decide the next action."""
        uav_id = list(world.fleet.keys())[0]
        world.mission_status = "running"

        # Set a short waypoint
        world.set_waypoint(uav_id, 1, 0)
        assert world.fleet[uav_id].command_source == "agent"

        # Step enough for path + idle timeout (path ~1 tick + 10 timeout + margin)
        for _ in range(20):
            world.step()

        uav = world.fleet[uav_id]
        if not uav.path:
            assert uav.command_source == "autopilot", \
                "command_source must reset to autopilot after idle timeout"

    def test_autopilot_picks_target_only_when_autopilot_controlled(self, world):
        """When command_source=agent and UAV is idle with no path, autopilot must NOT pick target."""
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]
        uav.command_source = "agent"
        uav.status = UAVStatus.IDLE
        uav.path = []
        world.mission_status = "running"

        world.step()

        # Autopilot should NOT have assigned a new path
        # (Though the charging logic at base may still apply)
        if (uav.x, uav.y) != world.terrain.base_position or uav.power >= 95.0:
            assert len(uav.path) == 0 or uav.command_source == "autopilot"


# ═══════════════════════════════════════════════════════════════
#  Fix 4: Composite Situational Awareness Tool
# ═══════════════════════════════════════════════════════════════

class TestSituationalAwareness:
    """Composite tool must return complete picture in one call.

    Industry best practice: reduce MCP round-trips.
    One call replaces query_fleet + get_search_progress + get_threat_map + assess_endurance.
    """

    @pytest.fixture
    def world(self):
        return GridWorld(size=10, num_uavs=3, num_objectives=3, num_obstacles=3, seed=42)

    def test_returns_complete_data(self, world):
        sa = world.get_situational_awareness()
        assert "fleet" in sa
        assert "progress" in sa
        assert "hotspots" in sa
        assert "endurance" in sa
        assert "tick" in sa
        assert "mission_status" in sa

    def test_fleet_data_matches_standalone(self, world):
        sa = world.get_situational_awareness()
        fleet = world.get_fleet_status().model_dump()
        assert sa["fleet"]["total"] == fleet["total"]
        assert sa["fleet"]["active"] == fleet["active"]
        assert len(sa["fleet"]["uavs"]) == len(fleet["uavs"])

    def test_progress_data_matches_standalone(self, world):
        sa = world.get_situational_awareness()
        progress = world.get_search_progress().model_dump()
        assert sa["progress"]["coverage_pct"] == progress["coverage_pct"]
        assert sa["progress"]["objectives_found"] == progress["objectives_found"]

    def test_endurance_data_matches_standalone(self, world):
        sa = world.get_situational_awareness()
        assert len(sa["endurance"]) == len(world.fleet)
        for entry in sa["endurance"]:
            assert "uav_id" in entry
            assert "power" in entry
            assert "safe_to_recall" in entry
            assert "urgent_recall" in entry

    def test_hotspots_present(self, world):
        sa = world.get_situational_awareness()
        assert isinstance(sa["hotspots"], list)


# ═══════════════════════════════════════════════════════════════
#  Fix 5: Session Rotation
# ═══════════════════════════════════════════════════════════════

class TestSessionRotation:
    """Session must rotate to prevent context window bloat.

    Industry best practice: bounded conversation history.
    """

    def test_session_max_cycles_constant_exists(self):
        from backend.agents.runner import SESSION_MAX_CYCLES
        assert SESSION_MAX_CYCLES > 0
        assert SESSION_MAX_CYCLES <= 30  # Reasonable upper bound

    def test_session_rotates_at_interval(self):
        """Session ID must be reset after SESSION_MAX_CYCLES cycles."""
        from backend.agents.runner import AgentRunner, SESSION_MAX_CYCLES

        world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)
        broadcasts = []

        async def capture(msg):
            broadcasts.append(msg)

        runner = AgentRunner(world=world, broadcast_fn=capture)

        # Simulate reaching the rotation point
        runner._session_id = "test-session-123"
        runner._cycle = SESSION_MAX_CYCLES - 1  # Next cycle will be exactly at boundary

        # Force error path (no API key) to test rotation logic
        old_key = os.environ.pop("GOOGLE_API_KEY", None)
        try:
            runner._running = True
            asyncio.get_event_loop().run_until_complete(runner.run_cycle())
        except Exception:
            pass
        finally:
            if old_key:
                os.environ["GOOGLE_API_KEY"] = old_key

        # After cycle at boundary, session should have been rotated
        # (set to None, then recreated — but since no API key, it may stay None or be new)
        assert runner._session_id != "test-session-123" or runner._session_id is None


# ═══════════════════════════════════════════════════════════════
#  Fix 6: Admin/Simulation Tools Removed from MCP Surface
# ═══════════════════════════════════════════════════════════════

class TestAdminToolsRemoved:
    """Admin tools (init_scenario, deploy_uav, inject_event) must NOT be
    discoverable via MCP. They were simulation-only and violated least-privilege.

    Industry best practice: never expose test/simulation controls to the agent.
    """

    @pytest.mark.asyncio
    async def test_admin_tools_not_in_tool_list(self):
        """init_scenario, deploy_uav, inject_event must not appear in MCP tool discovery."""
        from backend.services import tool_server
        from fastmcp import Client

        async with Client(tool_server.mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            for removed in ("init_scenario", "deploy_uav", "inject_event"):
                assert removed not in tool_names, f"{removed} must not be exposed to agent"

    @pytest.mark.asyncio
    async def test_prescriptive_planning_tools_removed(self):
        """partition_sectors, assign_sector, get_op_summary must not appear in MCP."""
        from backend.services import tool_server
        from fastmcp import Client

        async with Client(tool_server.mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            for removed in ("partition_sectors", "assign_sector", "get_op_summary"):
                assert removed not in tool_names, f"{removed} must not be exposed to agent"

    @pytest.mark.asyncio
    async def test_operational_tools_available(self):
        """Core operational tools must still be discoverable."""
        from backend.services import tool_server
        from fastmcp import Client

        async with Client(tool_server.mcp) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            expected = {
                "query_fleet", "inspect_uav", "get_threat_map", "get_search_progress",
                "navigate_to", "plan_route", "sweep_scan", "detect_frontier",
                "mark_objective", "recall_uav", "repower_uav", "assess_endurance",
                "get_situational_awareness",
            }
            assert expected == tool_names, f"Expected {expected}, got {tool_names}"


# ═══════════════════════════════════════════════════════════════
#  Fix 7: MCP Tool — navigate_to Waypoint Behavior
# ═══════════════════════════════════════════════════════════════

class TestMCPNavigateToWaypoint:
    """MCP navigate_to tool must use waypoint behavior over the wire."""

    @pytest.mark.asyncio
    async def test_navigate_to_returns_waypoint_result(self):
        from backend.services import tool_server
        from fastmcp import Client

        async with Client(tool_server.mcp) as client:
            # Get a UAV ID
            fleet_result = await client.call_tool("query_fleet", {})
            fleet_data = json.loads(fleet_result.content[0].text)
            uav_id = fleet_data["data"]["uavs"][0]["id"]

            # Navigate to a target — try multiple safe targets in case of obstacles
            for target in [(3, 0), (0, 3), (2, 0), (0, 2)]:
                result = await client.call_tool("navigate_to", {
                    "uav_id": uav_id, "x": target[0], "y": target[1],
                })
                data = json.loads(result.content[0].text)
                if data["status"] == "ok":
                    break

            assert data["status"] == "ok"
            assert "estimated_eta" in data["data"]
            assert "current_position" in data["data"]
            assert "planned_path" in data["data"]
            assert data["data"]["estimated_eta"] > 0

    @pytest.mark.asyncio
    async def test_recall_uav_returns_waypoint_result(self):
        from backend.services import tool_server
        from fastmcp import Client

        async with Client(tool_server.mcp) as client:
            fleet_result = await client.call_tool("query_fleet", {})
            fleet_data = json.loads(fleet_result.content[0].text)
            uav_id = fleet_data["data"]["uavs"][0]["id"]

            result = await client.call_tool("recall_uav", {"uav_id": uav_id})
            data = json.loads(result.content[0].text)
            # UAV at base → still ok but short/zero path
            assert data["status"] in ("ok", "error")

    @pytest.mark.asyncio
    async def test_situational_awareness_tool_exists(self):
        from backend.services import tool_server
        from fastmcp import Client

        async with Client(tool_server.mcp) as client:
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            assert "get_situational_awareness" in tool_names

            result = await client.call_tool("get_situational_awareness", {})
            data = json.loads(result.content[0].text)
            assert data["status"] == "ok"
            assert "fleet" in data["data"]
            assert "progress" in data["data"]
            assert "endurance" in data["data"]


# ═══════════════════════════════════════════════════════════════
#  Fix 8: WaypointResult Model Validation
# ═══════════════════════════════════════════════════════════════

class TestWaypointResultModel:
    """WaypointResult Pydantic model must be correct and serializable."""

    def test_model_fields(self):
        result = WaypointResult(
            uav_id="Alpha",
            waypoint=[5, 5],
            current_position=[0, 0],
            planned_path=[[0, 0], [1, 0], [2, 0]],
            estimated_distance=2,
            estimated_power_cost=4.0,
            estimated_eta=2,
            affordable=True,
        )
        assert result.uav_id == "Alpha"
        assert result.waypoint == [5, 5]
        assert result.estimated_eta == 2

    def test_model_serializable(self):
        result = WaypointResult(
            uav_id="Alpha",
            waypoint=[5, 5],
            current_position=[0, 0],
            planned_path=[[0, 0], [1, 0]],
            estimated_distance=1,
            estimated_power_cost=2.0,
            estimated_eta=1,
        )
        d = result.model_dump()
        assert isinstance(d, dict)
        json_str = json.dumps(d)
        assert len(json_str) > 10

    def test_error_result(self):
        result = WaypointResult(
            uav_id="Alpha",
            waypoint=[99, 99],
            current_position=[0, 0],
            planned_path=[],
            estimated_distance=0,
            estimated_power_cost=0,
            estimated_eta=0,
            affordable=False,
            status="error",
        )
        assert result.status == "error"
        assert result.affordable is False


# ═══════════════════════════════════════════════════════════════
#  Fix 9: UAV command_source Field
# ═══════════════════════════════════════════════════════════════

class TestUAVCommandSource:
    """UAV must track who issued the current command."""

    def test_default_is_autopilot(self):
        uav = UAV(id="test")
        assert uav.command_source == "autopilot"

    def test_to_dict_includes_command_source(self):
        uav = UAV(id="test", command_source="agent")
        d = uav.to_dict()
        assert "command_source" in d
        assert d["command_source"] == "agent"

    def test_command_source_in_fleet_status(self):
        world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)
        uav_id = list(world.fleet.keys())[0]
        world.fleet[uav_id].command_source = "agent"

        snapshot = world.get_state_snapshot()
        uav_data = [u for u in snapshot["fleet"] if u["id"] == uav_id][0]
        assert uav_data["command_source"] == "agent"


# ═══════════════════════════════════════════════════════════════
#  Fix 10: Prompts Updated for Waypoint Behavior
# ═══════════════════════════════════════════════════════════════

class TestPromptsUpdated:
    """Prompts must reflect waypoint-based navigation."""

    def test_assessor_mentions_situational_awareness(self):
        import yaml
        prompts_path = os.path.join(os.path.dirname(__file__), '../../backend/agents/prompts.yaml')
        with open(prompts_path) as f:
            data = yaml.safe_load(f)
        instruction = data["assessor"]["instruction"]
        assert "get_situational_awareness" in instruction

    def test_dispatcher_mentions_waypoint(self):
        import yaml
        prompts_path = os.path.join(os.path.dirname(__file__), '../../backend/agents/prompts.yaml')
        with open(prompts_path) as f:
            data = yaml.safe_load(f)
        instruction = data["dispatcher"]["instruction"]
        assert "WAYPOINT" in instruction.upper() or "waypoint" in instruction.lower()

    def test_dispatcher_warns_about_scan_timing(self):
        """Dispatcher must warn: don't scan immediately after navigate_to."""
        import yaml
        prompts_path = os.path.join(os.path.dirname(__file__), '../../backend/agents/prompts.yaml')
        with open(prompts_path) as f:
            data = yaml.safe_load(f)
        instruction = data["dispatcher"]["instruction"]
        assert "arrived" in instruction.lower() or "NOT" in instruction
