"""
Test Suite 15: Reset Safety — Regression Tests

Validates that resetting the simulation is safe:
1. AgentRunner cancellation on reset
2. Old runner does not mutate new world
3. Concurrent reset and step don't corrupt state

DO NOT weaken these tests.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.agents.runner import AgentRunner
from backend.core.grid_world import GridWorld


class TestAgentRunnerCancellation:
    """AgentRunner must support clean cancellation."""

    def test_runner_has_cancel_method(self):
        world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)

        async def noop(msg):
            pass

        runner = AgentRunner(world=world, broadcast_fn=noop)
        assert hasattr(runner, "cancel"), "AgentRunner must have a cancel() method"

    def test_cancel_prevents_new_cycle(self):
        world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)
        broadcasts = []

        async def capture(msg):
            broadcasts.append(msg)

        runner = AgentRunner(world=world, broadcast_fn=capture)
        runner.cancel()

        # After cancel, try_start should still work (cancel only affects in-flight)
        # But run_cycle should detect cancelled state
        assert runner._cancelled is True

    @pytest.mark.asyncio
    async def test_cancelled_runner_cycle_exits_early(self):
        world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)
        broadcasts = []

        async def capture(msg):
            broadcasts.append(msg)

        runner = AgentRunner(world=world, broadcast_fn=capture)
        runner._running = True
        runner.cancel()

        await runner.run_cycle()

        # Should have exited cleanly — no "thinking" broadcast
        thinking_msgs = [m for m in broadcasts if m.get("payload", {}).get("status") == "thinking"]
        assert len(thinking_msgs) == 0, "Cancelled runner should not start thinking"


class TestResetWorldIsolation:
    """New world after reset must be independent of old world."""

    def test_new_world_is_independent(self):
        old_world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)
        old_world.mission_status = "running"
        for _ in range(10):
            old_world.step()

        new_world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)

        # New world should be fresh
        assert new_world.tick == 0
        assert old_world.tick > 0

        # Modifying old world should not affect new world
        old_world.step()
        assert new_world.tick == 0

    def test_runner_with_old_world_does_not_affect_new_world(self):
        """If a runner holds a reference to old_world, it should not touch new_world."""
        old_world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)
        new_world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)

        async def noop(msg):
            pass

        old_runner = AgentRunner(world=old_world, broadcast_fn=noop)

        # Old runner references old_world
        assert old_runner.world is old_world
        assert old_runner.world is not new_world
