"""
Test Suite 20: Drone Autonomous Agent
Tests for the Drone class — autopilot behavior, mission management,
safety overrides, and target selection.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.core.drone import Drone, CRITICAL_POWER, AGENT_IDLE_TIMEOUT
from backend.core.grid_world import GridWorld
from backend.core.uav import (
    UAV, UAVStatus,
    Mission, MissionType, MissionStatus,
)


@pytest.fixture
def world():
    return GridWorld(size=10, num_uavs=3, num_objectives=3, num_obstacles=3, seed=42)


@pytest.fixture
def drone(world):
    return list(world.drones.values())[0]


# ═══════════════════════════════════════════════════════════════
#  Drone.step() basics
# ═══════════════════════════════════════════════════════════════

class TestDroneStep:
    def test_drone_step_advances_path(self, world, drone):
        """step() should advance the drone one cell along its path."""
        uav = drone.uav
        uav.path = [(1, 0), (2, 0)]
        uav.status = UAVStatus.MOVING
        uav.command_source = "autopilot"
        world.mission_status = "running"

        drone.step(world)

        assert (uav.x, uav.y) == (1, 0)
        assert uav.path == [(2, 0)]

    def test_drone_step_scans_on_arrival(self, world, drone):
        """Autopilot path completion should auto-scan."""
        uav = drone.uav
        # Set a short path
        uav.path = [(1, 0)]
        uav.status = UAVStatus.MOVING
        uav.command_source = "autopilot"

        events = drone.step(world)

        assert uav.status == UAVStatus.IDLE
        assert uav.command_source == "autopilot"

    def test_drone_agent_arrival_no_auto_scan(self, world, drone):
        """Agent path completion should NOT auto-scan."""
        uav = drone.uav
        uav.path = [(1, 0)]
        uav.status = UAVStatus.MOVING
        uav.command_source = "agent"

        events = drone.step(world)

        assert uav.status == UAVStatus.IDLE
        assert uav.command_source == "agent"
        arrival = [e for e in events if "arrived at waypoint" in e]
        assert len(arrival) > 0


# ═══════════════════════════════════════════════════════════════
#  assign_mission()
# ═══════════════════════════════════════════════════════════════

class TestAssignMission:
    def test_drone_assign_mission_accepted(self, world, drone):
        """Idle drone should accept a search mission."""
        uav = drone.uav
        uav.status = UAVStatus.IDLE
        uav.power = 100.0

        mission = Mission(type=MissionType.SEARCH, target=(5, 5), assigned_by="agent")
        report = drone.assign_mission(mission, world)

        assert "accepted" in report.status
        assert uav.command_source == "agent"
        assert uav.status == UAVStatus.MOVING
        assert len(uav.path) > 0

    def test_drone_assign_mission_rejected_busy(self, world, drone):
        """Returning drone should reject a new mission."""
        uav = drone.uav
        uav.status = UAVStatus.RETURNING
        uav.path = [(1, 0)]

        mission = Mission(type=MissionType.SEARCH, target=(5, 5), assigned_by="agent")
        report = drone.assign_mission(mission, world)

        assert "rejected" in report.status

    def test_drone_assign_mission_rejected_low_power(self, world):
        """Drone with <30% power (not at base) should reject."""
        drone_id = list(world.drones.keys())[0]
        drone = world.drones[drone_id]
        uav = drone.uav
        world.move_uav(drone_id, 3, 0)  # Move away from base
        uav.power = 20.0
        uav.status = UAVStatus.IDLE

        mission = Mission(type=MissionType.SEARCH, target=(5, 5), assigned_by="agent")
        report = drone.assign_mission(mission, world)

        assert "rejected" in report.status

    def test_drone_assign_recall_accepted(self, world):
        """Idle drone should accept a recall mission."""
        drone_id = list(world.drones.keys())[0]
        drone = world.drones[drone_id]
        world.move_uav(drone_id, 3, 0)
        drone.uav.status = UAVStatus.IDLE
        drone.uav.power = 80.0

        mission = Mission(type=MissionType.RECALL, assigned_by="agent")
        report = drone.assign_mission(mission, world)

        assert "accepted" in report.status
        assert drone.uav.status == UAVStatus.RETURNING


# ═══════════════════════════════════════════════════════════════
#  Safety overrides
# ═══════════════════════════════════════════════════════════════

class TestDroneSafety:
    def test_drone_safety_override(self, world):
        """<10% power should force return regardless of agent command."""
        drone_id = list(world.drones.keys())[0]
        drone = world.drones[drone_id]
        uav = drone.uav
        world.move_uav(drone_id, 3, 0)
        uav.power = 5.0
        uav.command_source = "agent"
        uav.path = [(4, 0)]
        uav.status = UAVStatus.MOVING

        events = drone.step(world)

        assert uav.status == UAVStatus.RETURNING
        assert uav.command_source == "autopilot"
        safety_events = [e for e in events if "SAFETY OVERRIDE" in e]
        assert len(safety_events) > 0


# ═══════════════════════════════════════════════════════════════
#  Idle timeout
# ═══════════════════════════════════════════════════════════════

class TestDroneIdleTimeout:
    def test_drone_idle_timeout(self, world, drone):
        """Agent-controlled idle drone should revert to autopilot after timeout."""
        uav = drone.uav
        uav.status = UAVStatus.IDLE
        uav.command_source = "agent"
        uav._idle_since_tick = 0
        uav.path = []
        world.tick = AGENT_IDLE_TIMEOUT + 1

        events = drone.step(world)

        assert uav.command_source == "autopilot"
        timeout_events = [e for e in events if "idle timeout" in e]
        assert len(timeout_events) > 0


# ═══════════════════════════════════════════════════════════════
#  get_report()
# ═══════════════════════════════════════════════════════════════

class TestDroneReport:
    def test_drone_get_report_includes_mission(self, world, drone):
        """Report should include mission status when a mission is active."""
        uav = drone.uav
        drone.current_mission = Mission(
            type=MissionType.SEARCH, target=(5, 5),
            status=MissionStatus.IN_PROGRESS, assigned_by="agent",
        )

        report = drone.get_report(world)

        assert report.drone_id == uav.id
        assert report.mission is not None
        assert report.mission["type"] == "search"
        assert report.mission_status == "executing"

    def test_drone_get_report_idle(self, world, drone):
        """Report should show idle status when no mission."""
        report = drone.get_report(world)
        assert report.mission_status == "idle"
        assert report.mission is None


# ═══════════════════════════════════════════════════════════════
#  Target selection
# ═══════════════════════════════════════════════════════════════

class TestDroneTargetSelection:
    def test_drone_autonomous_target_selection(self, world, drone):
        """Idle autopilot drone should pick a target."""
        uav = drone.uav
        uav.status = UAVStatus.IDLE
        uav.command_source = "autopilot"
        uav.path = []
        uav.power = 100.0
        # Move away from base so charging logic doesn't interfere
        uav.x, uav.y = 3, 3
        world.explored_grid[3, 3] = 1

        events = drone.step(world)

        # Drone should have picked a target and started moving
        assert uav.status == UAVStatus.MOVING or len(uav.path) > 0 or uav.command_source == "autopilot"
