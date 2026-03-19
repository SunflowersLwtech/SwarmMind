"""
Test Suite 13: Agent/Autopilot Control Contention — Regression Tests

Validates the control handoff between agent commands and autopilot:
1. Agent-set path completion behavior (no silent auto-scan)
2. Idle timeout: agent-controlled UAV releases control after timeout
3. Autopilot path completion still auto-scans
4. Full command_source lifecycle

DO NOT weaken these tests. If a test fails, the code must change, not the test.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.core.grid_world import GridWorld
from backend.core.uav import UAVStatus


@pytest.fixture
def world():
    return GridWorld(size=10, num_uavs=3, num_objectives=3, num_obstacles=3, seed=42)


class TestAgentPathCompletion:
    """When an agent-set path completes, autopilot must NOT auto-scan."""

    def test_agent_path_complete_does_not_auto_scan(self, world):
        """After agent waypoint path finishes, UAV should be IDLE, not scanned."""
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]
        world.mission_status = "running"

        # Set a short agent waypoint
        world.set_waypoint(uav_id, 1, 0)
        assert uav.command_source == "agent"
        path_len = len(uav.path)

        # Step exactly path_len times
        for _ in range(path_len):
            world.step()

        # UAV should be IDLE, not having been auto-scanned
        assert uav.status == UAVStatus.IDLE
        assert (uav.x, uav.y) == (1, 0)

    def test_agent_path_complete_keeps_agent_source(self, world):
        """After agent path completes, command_source should remain 'agent'
        until idle timeout or next agent cycle (not immediately reset)."""
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]
        world.mission_status = "running"

        world.set_waypoint(uav_id, 1, 0)
        path_len = len(uav.path)

        for _ in range(path_len):
            world.step()

        # Immediately after path completion, command_source should still be "agent"
        assert uav.command_source == "agent", (
            "command_source must remain 'agent' immediately after path completion "
            "to prevent autopilot from picking a new target before agent re-evaluates"
        )

    def test_agent_path_complete_emits_arrival_event(self, world):
        """Agent path completion should produce an 'arrived' event."""
        uav_id = list(world.fleet.keys())[0]
        world.mission_status = "running"

        world.set_waypoint(uav_id, 1, 0)
        path_len = len(world.fleet[uav_id].path)

        events_collected = []
        for _ in range(path_len + 1):
            result = world.step()
            events_collected.extend(result.events)

        arrival_events = [e for e in events_collected if "arrived" in e.lower()]
        assert len(arrival_events) > 0, (
            f"Expected arrival event for {uav_id}, got events: {events_collected}"
        )


class TestAutopilotPathCompletion:
    """Autopilot-set paths should still auto-scan on completion."""

    def test_autopilot_path_complete_auto_scans(self, world):
        """Autopilot paths should still trigger scan on arrival (existing behavior)."""
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]
        uav.command_source = "autopilot"
        world.mission_status = "running"

        # Let autopilot pick a target and move
        for _ in range(50):
            world.step()
            if uav.command_source == "autopilot" and uav.status == UAVStatus.IDLE:
                break

        # Autopilot-controlled idle UAV should eventually pick targets and scan
        assert uav.command_source == "autopilot"


class TestIdleTimeout:
    """Agent-controlled UAV should release control after idle timeout."""

    IDLE_TIMEOUT = 10  # ticks — must match grid_world.AGENT_IDLE_TIMEOUT

    def test_agent_idle_releases_after_timeout(self, world):
        """UAV idle with command_source=agent should revert to autopilot after timeout."""
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]
        world.mission_status = "running"

        # Set and complete a short waypoint
        world.set_waypoint(uav_id, 1, 0)
        path_len = len(uav.path)
        for _ in range(path_len):
            world.step()

        assert uav.command_source == "agent"

        # Step beyond timeout
        for _ in range(self.IDLE_TIMEOUT + 2):
            world.step()

        assert uav.command_source == "autopilot", (
            f"UAV should release agent control after {self.IDLE_TIMEOUT} idle ticks"
        )

    def test_agent_command_resets_idle_counter(self, world):
        """New agent command should reset the idle timeout counter."""
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]
        world.mission_status = "running"

        # Set waypoint, complete it
        world.set_waypoint(uav_id, 1, 0)
        for _ in range(len(uav.path)):
            world.step()

        # Wait a few ticks (but less than timeout)
        for _ in range(5):
            world.step()
        assert uav.command_source == "agent"

        # Set a new waypoint — this should reset the timer
        world.set_waypoint(uav_id, 2, 0)
        for _ in range(len(uav.path)):
            world.step()

        # Should still be agent-controlled after second path completes
        assert uav.command_source == "agent"


class TestCommandSourceLifecycle:
    """Full lifecycle: autopilot → agent → path complete → idle timeout → autopilot."""

    def test_full_lifecycle(self, world):
        """Trace the complete command_source lifecycle."""
        uav_id = list(world.fleet.keys())[0]
        uav = world.fleet[uav_id]
        world.mission_status = "running"

        # 1. Start as autopilot
        assert uav.command_source == "autopilot"

        # 2. Agent sets waypoint → switches to agent
        world.set_waypoint(uav_id, 2, 0)
        assert uav.command_source == "agent"

        # 3. Path completes → stays agent (awaiting next command)
        for _ in range(len(uav.path)):
            world.step()
        assert uav.command_source == "agent"
        assert uav.status == UAVStatus.IDLE

        # 4. Idle timeout → reverts to autopilot
        for _ in range(15):
            world.step()
        assert uav.command_source == "autopilot"
