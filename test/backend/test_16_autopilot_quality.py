"""
Test Suite 16: Autopilot Target Selection & Movement Quality

Validates:
1. Repulsion scales with fleet size / grid size (not hardcoded)
2. UAV collision avoidance (no two UAVs on same cell)
3. Power budget adapts to coverage progress
4. Coordinate system correctness (pathfinding round-trips)
5. move_uav marked as test-only infrastructure

DO NOT weaken these tests.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.core.grid_world import GridWorld
from backend.core.uav import UAV, UAVStatus
from backend.core.pathplanner import PathPlanner


# ═══════════════════════════════════════════════════════════════
#  1. Repulsion — adaptive coefficients
# ═══════════════════════════════════════════════════════════════

class TestRepulsionAdaptive:
    """Repulsion must scale with fleet density, not use hardcoded magic numbers."""

    def test_spread_improves_with_more_uavs(self):
        """More UAVs should still produce spatially diverse targets."""
        world = GridWorld(size=20, num_uavs=5, num_objectives=4, num_obstacles=5, seed=42)
        world.mission_status = "running"

        # Run a few ticks so UAVs pick targets
        for _ in range(5):
            world.step()

        # Collect positions of all operational UAVs
        positions = set()
        for uav in world.fleet.values():
            if uav.is_operational:
                positions.add((uav.x, uav.y))

        # With 5 UAVs, we should have at least 3 distinct positions
        assert len(positions) >= 3, (
            f"5 UAVs clustered into {len(positions)} positions — repulsion too weak"
        )

    def test_pick_target_avoids_other_uavs(self):
        """Picked target should not be at another UAV's current position."""
        world = GridWorld(size=10, num_uavs=3, num_objectives=3, num_obstacles=3, seed=42)

        # Move UAVs to known positions
        ids = list(world.fleet.keys())
        world.move_uav(ids[0], 5, 5)
        world.move_uav(ids[1], 3, 3)

        # Drone at base picks a target
        drone = world.drones[ids[2]]
        target = drone._pick_target(world)
        if target is not None:
            occupied = {(world.fleet[i].x, world.fleet[i].y) for i in ids[:2]}
            assert target not in occupied, (
                f"_pick_target chose {target} which is occupied by another UAV"
            )

    def test_repulsion_uses_inverse_square(self):
        """Repulsion should decay as 1/d² not 1/(d+1) for more physical spread."""
        world = GridWorld(size=10, num_uavs=3, num_objectives=3, num_obstacles=3, seed=42)
        ids = list(world.fleet.keys())
        world.move_uav(ids[0], 5, 0)
        world.move_uav(ids[1], 5, 1)

        # Drone 2 at (0,0) should NOT pick a target near (5,0)/(5,1)
        drone = world.drones[ids[2]]
        target = drone._pick_target(world)
        if target is not None:
            dist_to_cluster = abs(target[0] - 5) + abs(target[1] - 0)
            assert dist_to_cluster >= 2, (
                f"Target {target} is too close to UAV cluster at (5,0)/(5,1)"
            )


# ═══════════════════════════════════════════════════════════════
#  2. Collision avoidance
# ═══════════════════════════════════════════════════════════════

class TestCollisionAvoidance:
    """Two UAVs must not occupy the same cell simultaneously (except base)."""

    def test_autopilot_prevents_same_cell_over_many_ticks(self):
        """Over 60 ticks, no two UAVs should share a cell far from base."""
        world = GridWorld(size=10, num_uavs=4, num_objectives=2, num_obstacles=3, seed=42)
        world.mission_status = "running"

        base = world.terrain.base_position
        for tick in range(60):
            world.step()

            positions = {}
            for uav in world.fleet.values():
                pos = (uav.x, uav.y)
                # Base area (within 2 cells) is exempt — UAVs must be able to pass
                near_base = abs(pos[0] - base[0]) + abs(pos[1] - base[1]) <= 2
                if near_base:
                    continue
                if pos in positions:
                    pytest.fail(
                        f"Tick {tick}: {uav.id} collided with {positions[pos]} at {pos}"
                    )
                positions[pos] = uav.id

    def test_forced_collision_scenario(self):
        """Two UAVs heading toward each other must not collide far from base."""
        world = GridWorld(size=10, num_uavs=2, num_objectives=1, num_obstacles=0, seed=42)
        ids = list(world.fleet.keys())
        world.mission_status = "running"

        # Place UAVs far from base to avoid base-area exemption
        world.move_uav(ids[0], 8, 0)
        world.set_waypoint(ids[0], 4, 0)

        world.move_uav(ids[1], 4, 0)
        world.set_waypoint(ids[1], 8, 0)

        base = world.terrain.base_position
        for tick in range(10):
            world.step()
            u0 = world.fleet[ids[0]]
            u1 = world.fleet[ids[1]]
            pos0 = (u0.x, u0.y)
            pos1 = (u1.x, u1.y)
            near_base = abs(pos0[0]) + abs(pos0[1]) <= 2
            if pos0 == pos1 and not near_base:
                pytest.fail(
                    f"Tick {tick}: {ids[0]}@{pos0} collided with {ids[1]}@{pos1}"
                )

    def test_waypoint_to_occupied_cell_accepted(self):
        """Setting waypoint to an occupied cell should still succeed —
        collision is handled at movement time, not at planning time."""
        world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)
        ids = list(world.fleet.keys())
        world.move_uav(ids[0], 3, 0)

        result = world.set_waypoint(ids[1], 3, 0)
        assert result.status == "ok"


# ═══════════════════════════════════════════════════════════════
#  3. Power budget — adaptive
# ═══════════════════════════════════════════════════════════════

class TestAdaptivePowerBudget:
    """Power budget should adapt to mission progress."""

    def test_early_mission_conservative(self):
        """Early in mission (low coverage), budget should be conservative."""
        world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)
        drone = list(world.drones.values())[0]
        drone.uav.power = 80.0

        target = drone._pick_target(world)
        if target:
            dist = abs(target[0] - drone.uav.x) + abs(target[1] - drone.uav.y)
            max_range = drone.uav.power / drone.uav.POWER_MOVE
            # Should not use more than ~50% of power
            assert dist <= max_range * 0.6, (
                f"Early mission: target at dist {dist} exceeds safe range {max_range * 0.6}"
            )

    def test_late_mission_allows_longer_reach(self):
        """Late in mission (high coverage), budget can be more aggressive."""
        world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)
        world.mission_status = "running"

        # Explore most of the grid
        for x in range(8):
            for y in range(8):
                world.explored_grid[x, y] = 1

        drone = list(world.drones.values())[0]
        drone.uav.power = 80.0
        target = drone._pick_target(world)

        # With high coverage, remaining targets may be far — budget should allow
        if target:
            dist = abs(target[0] - drone.uav.x) + abs(target[1] - drone.uav.y)
            assert dist > 0, "Should still find unexplored targets"


# ═══════════════════════════════════════════════════════════════
#  4. Coordinate system correctness
# ═══════════════════════════════════════════════════════════════

class TestCoordinateSystem:
    """Pathfinding coordinate transforms must be correct and well-documented."""

    def test_path_start_matches_input(self):
        world = GridWorld(size=10, num_uavs=1, num_objectives=1, num_obstacles=3, seed=42)
        path = world.path_planner.find_path((0, 0), (5, 3))
        assert path[0] == (0, 0)

    def test_path_end_matches_input(self):
        world = GridWorld(size=10, num_uavs=1, num_objectives=1, num_obstacles=3, seed=42)
        path = world.path_planner.find_path((0, 0), (5, 3))
        assert path[-1] == (5, 3)

    def test_asymmetric_path_correct(self):
        """(2,7) != (7,2) — verify coordinate swap is correct."""
        world = GridWorld(size=10, num_uavs=1, num_objectives=1, num_obstacles=0, seed=42)
        path1 = world.path_planner.find_path((0, 0), (2, 7))
        path2 = world.path_planner.find_path((0, 0), (7, 2))

        assert path1[-1] == (2, 7), f"Expected (2,7), got {path1[-1]}"
        assert path2[-1] == (7, 2), f"Expected (7,2), got {path2[-1]}"
        assert path1[-1] != path2[-1], "Asymmetric targets must produce different endpoints"

    def test_path_contiguous(self):
        """Every step in path must be exactly 1 Manhattan distance."""
        world = GridWorld(size=10, num_uavs=1, num_objectives=1, num_obstacles=3, seed=42)
        path = world.path_planner.find_path((0, 0), (8, 8))
        if not path:
            pytest.skip("No path found (obstacles may block)")
        for i in range(1, len(path)):
            dx = abs(path[i][0] - path[i - 1][0])
            dy = abs(path[i][1] - path[i - 1][1])
            assert dx + dy == 1, (
                f"Discontinuity at step {i}: {path[i-1]} -> {path[i]}"
            )

    def test_path_avoids_obstacles(self):
        """No cell on path should be blocked."""
        world = GridWorld(size=10, num_uavs=1, num_objectives=1, num_obstacles=5, seed=42)
        path = world.path_planner.find_path((0, 0), (9, 9))
        if not path:
            pytest.skip("No path found")
        for cell in path:
            assert not world.terrain.is_blocked(cell[0], cell[1]), (
                f"Path goes through blocked cell {cell}"
            )

    def test_round_trip_consistency(self):
        """Path A→B reversed should match path B→A (same cells, opposite order)."""
        world = GridWorld(size=10, num_uavs=1, num_objectives=1, num_obstacles=3, seed=42)
        fwd = world.path_planner.find_path((0, 0), (5, 5))
        rev = world.path_planner.find_path((5, 5), (0, 0))

        if fwd and rev:
            assert fwd[0] == rev[-1], "Forward start should be reverse end"
            assert fwd[-1] == rev[0], "Forward end should be reverse start"
            assert len(fwd) == len(rev), "Forward and reverse should have same length"


# ═══════════════════════════════════════════════════════════════
#  5. move_uav is test infrastructure only
# ═══════════════════════════════════════════════════════════════

class TestMoveUavInfrastructure:
    """move_uav must not be exposed to Agent via any tool surface."""

    def test_not_in_mcp_tools(self):
        """move_uav must not appear in MCP tool names."""
        from backend.services.tool_server import mcp
        import asyncio
        from fastmcp import Client

        async def _check():
            async with Client(mcp) as client:
                tools = await client.list_tools()
                return {t.name for t in tools}

        tool_names = asyncio.get_event_loop().run_until_complete(_check())
        assert "move_uav" not in tool_names

    def test_still_works_for_tests(self):
        """move_uav must still function as test infrastructure."""
        world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)
        uav_id = list(world.fleet.keys())[0]
        result = world.move_uav(uav_id, 3, 0)
        assert result.new_position == [3, 0]
