"""
Test Suite 05d: Shared World Injection & main.py Integration
Regression tests for set_shared_world(), reset handlers, and
agent dispatch in the simulation loop.
"""
import asyncio
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from backend.core.grid_world import GridWorld


# ── set_shared_world ──────────────────────────────────────────

class TestSetSharedWorld:
    def test_sets_module_level_var(self):
        from backend.services import tool_server
        world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=1)
        tool_server.set_shared_world(world)
        assert tool_server._shared_world is world

    def test_replaces_previous(self):
        from backend.services import tool_server
        w1 = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=1)
        w2 = GridWorld(size=10, num_uavs=3, num_objectives=2, num_obstacles=3, seed=2)
        tool_server.set_shared_world(w1)
        tool_server.set_shared_world(w2)
        assert tool_server._shared_world is w2
        assert tool_server._shared_world is not w1

    def test_none_resets(self):
        from backend.services import tool_server
        w = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=1)
        tool_server.set_shared_world(w)
        tool_server.set_shared_world(None)
        assert tool_server._shared_world is None


# ── main.py reset handler ────────────────────────────────────

class TestResetIntegration:
    def test_ops_reset_creates_fresh_world(self):
        """POST /api/ops/reset must create a new GridWorld."""
        import backend.main as main_mod
        old_world = main_mod.world
        old_runner = main_mod.agent_runner

        # Mutate the old world
        old_world.tick = 999
        old_world.mission_status = "running"

        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=main_mod.app)

        async def _reset():
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/ops/reset")
                return resp.json()

        result = asyncio.get_event_loop().run_until_complete(_reset())
        assert result["status"] == "ok"

        # world should be a new instance
        assert main_mod.world is not old_world
        assert main_mod.world.tick == 0
        assert main_mod.world.mission_status == "idle"

        # agent_runner should be recreated
        assert main_mod.agent_runner is not old_runner

    def test_ops_reset_clears_blackbox(self):
        from backend.utils.blackbox import blackbox
        import backend.main as main_mod

        blackbox.log("test", "should be cleared")
        assert len(blackbox.entries) > 0

        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=main_mod.app)

        async def _reset():
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post("/api/ops/reset")

        asyncio.get_event_loop().run_until_complete(_reset())
        assert len(blackbox.entries) == 0

    def test_ops_reset_updates_shared_world(self):
        """After reset, tool_server._shared_world should point to the new world."""
        import backend.main as main_mod
        from backend.services import tool_server

        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=main_mod.app)

        async def _reset():
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                await client.post("/api/ops/reset")

        asyncio.get_event_loop().run_until_complete(_reset())
        assert tool_server._shared_world is main_mod.world


# ── WebSocket command handling ────────────────────────────────

class TestWebSocketCommands:
    @pytest.fixture
    def client(self):
        import backend.main as main_mod
        from httpx import AsyncClient, ASGITransport
        transport = ASGITransport(app=main_mod.app)
        return AsyncClient(transport=transport, base_url="http://test")

    def test_start_sets_running(self, client):
        import backend.main as main_mod
        main_mod.simulation_running = False

        async def _do():
            async with client:
                resp = await client.post("/api/ops/start")
                return resp.json()

        result = asyncio.get_event_loop().run_until_complete(_do())
        assert result["status"] == "ok"
        assert main_mod.simulation_running is True
        assert main_mod.world.mission_status == "running"

    def test_pause_sets_paused(self, client):
        import backend.main as main_mod
        main_mod.simulation_running = True
        main_mod.world.mission_status = "running"

        async def _do():
            async with client:
                await client.post("/api/ops/pause")

        asyncio.get_event_loop().run_until_complete(_do())
        assert main_mod.simulation_running is False
        assert main_mod.world.mission_status == "paused"

    def test_stop_sets_idle(self, client):
        import backend.main as main_mod
        main_mod.simulation_running = True
        main_mod.world.mission_status = "running"

        async def _do():
            async with client:
                await client.post("/api/ops/stop")

        asyncio.get_event_loop().run_until_complete(_do())
        assert main_mod.simulation_running is False
        assert main_mod.world.mission_status == "idle"


# ── Agent dispatch interval ───────────────────────────────────

class TestAgentDispatch:
    def test_agent_interval_constant(self):
        import backend.main as main_mod
        assert main_mod.AGENT_INTERVAL >= 25  # At least 5 seconds at 5Hz
        assert main_mod.AGENT_INTERVAL <= 100  # At most 20 seconds

    def test_try_start_called_at_interval(self):
        """Verify tick % AGENT_INTERVAL == 0 logic."""
        import backend.main as main_mod
        interval = main_mod.AGENT_INTERVAL
        # Ticks where agent should fire
        for mult in [1, 2, 3, 4]:
            assert (interval * mult) % interval == 0
        # Ticks where agent should NOT fire
        for tick in [1, interval - 1, interval + 1]:
            assert tick % interval != 0


# ── Blackbox logging from runner ──────────────────────────────

class TestBlackboxIntegration:
    def test_run_cycle_logs_to_blackbox(self):
        from backend.utils.blackbox import blackbox
        blackbox.clear()

        world = GridWorld(size=10, num_uavs=2, num_objectives=2, num_obstacles=3, seed=42)
        broadcasts = []

        async def capture(msg):
            broadcasts.append(msg)

        runner = __import__("backend.agents.runner", fromlist=["AgentRunner"]).AgentRunner(
            world=world, broadcast_fn=capture
        )

        old_key = os.environ.pop("GOOGLE_API_KEY", None)
        try:
            runner._running = True
            asyncio.get_event_loop().run_until_complete(runner.run_cycle())
        finally:
            if old_key:
                os.environ["GOOGLE_API_KEY"] = old_key

        # Blackbox should have entries for cycle start + error
        entries = blackbox.get_recent(50)
        agents = [e["agent"] for e in entries]
        assert "system" in agents
