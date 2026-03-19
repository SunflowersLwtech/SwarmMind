"""
Test Suite 05c: AgentRunner (backend/agents/runner.py)
Regression tests for try_start guard, run_cycle error paths,
_process_event CoT extraction, and broadcast messages.
"""
import asyncio
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from backend.core.grid_world import GridWorld
from backend.agents.runner import AgentRunner


@pytest.fixture
def world():
    return GridWorld(size=10, num_uavs=3, num_objectives=4, num_obstacles=5, seed=42)


@pytest.fixture
def broadcasts():
    """Collect all broadcast messages."""
    return []


@pytest.fixture
def runner(world, broadcasts):
    async def capture(msg):
        broadcasts.append(msg)
    # Use a dummy MCP URL — runner won't actually connect (no API key in tests)
    return AgentRunner(world=world, broadcast_fn=capture, mcp_url="http://127.0.0.1:8001/mcp")


# ── try_start() atomic guard ──────────────────────────────────

class TestTryStart:
    def test_first_call_returns_true(self, runner):
        assert runner.try_start() is True

    def test_second_call_returns_false(self, runner):
        runner.try_start()
        assert runner.try_start() is False

    def test_resets_after_cycle_fails(self, runner, broadcasts):
        """After run_cycle fails (no API key), _running resets to False."""
        runner.try_start()
        # Remove GOOGLE_API_KEY to force failure
        old_key = os.environ.pop("GOOGLE_API_KEY", None)
        try:
            asyncio.get_event_loop().run_until_complete(runner.run_cycle())
        except Exception:
            pass
        finally:
            if old_key:
                os.environ["GOOGLE_API_KEY"] = old_key
        # _running should be reset
        assert runner.try_start() is True

    def test_concurrent_guard_single_threaded(self, runner):
        """Simulates the pattern used in simulation_loop."""
        results = []
        for _ in range(5):
            results.append(runner.try_start())
        # Only the first should succeed
        assert results == [True, False, False, False, False]


# ── run_cycle() error handling ────────────────────────────────

class TestRunCycleErrors:
    @pytest.fixture(autouse=True)
    def clear_api_key(self):
        old = os.environ.pop("GOOGLE_API_KEY", None)
        yield
        if old:
            os.environ["GOOGLE_API_KEY"] = old

    def test_missing_api_key_broadcasts_error(self, runner, broadcasts):
        runner._running = True
        asyncio.get_event_loop().run_until_complete(runner.run_cycle())

        # API key check fires before "thinking" broadcast, so only "error" is sent
        statuses = [b["payload"]["status"] for b in broadcasts if b["type"] == "agent_status"]
        assert "error" in statuses

    def test_missing_api_key_error_message(self, runner, broadcasts):
        runner._running = True
        asyncio.get_event_loop().run_until_complete(runner.run_cycle())

        error_msgs = [b for b in broadcasts
                      if b["type"] == "agent_status" and b["payload"]["status"] == "error"]
        assert len(error_msgs) > 0
        assert "GOOGLE_API_KEY" in error_msgs[0]["payload"]["message"]

    def test_running_resets_after_error(self, runner, broadcasts):
        runner._running = True
        asyncio.get_event_loop().run_until_complete(runner.run_cycle())
        assert runner._running is False

    def test_cycle_counter_increments(self, runner, broadcasts):
        runner._running = True
        asyncio.get_event_loop().run_until_complete(runner.run_cycle())
        assert runner._cycle == 1

        runner._running = True
        asyncio.get_event_loop().run_until_complete(runner.run_cycle())
        assert runner._cycle == 2


# ── _process_event() CoT extraction ──────────────────────────

class _FakePart:
    """Minimal mock for google.genai Part objects."""
    def __init__(self, text=None, function_call=None, function_response=None):
        self.text = text
        self.function_call = function_call
        self.function_response = function_response


class _FakeFC:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class _FakeFR:
    def __init__(self, name, response):
        self.name = name
        self.response = response


class _FakeContent:
    def __init__(self, parts):
        self.parts = parts


class _FakeEvent:
    def __init__(self, author, parts):
        self.author = author
        self.content = _FakeContent(parts)


class TestProcessEvent:
    def test_reasoning_text(self, runner, broadcasts):
        event = _FakeEvent("assessor", [_FakePart(text="Analyzing fleet status...")])
        asyncio.get_event_loop().run_until_complete(runner._process_event(event, 1))

        logs = [b for b in broadcasts if b["type"] == "agent_log"]
        assert len(logs) == 1
        assert logs[0]["payload"]["action"] == "reasoning"
        assert logs[0]["payload"]["agent"] == "assessor"
        assert "Analyzing fleet" in logs[0]["payload"]["detail"]

    def test_function_call(self, runner, broadcasts):
        fc = _FakeFC("query_fleet", {"verbose": True})
        event = _FakeEvent("dispatcher", [_FakePart(function_call=fc)])
        asyncio.get_event_loop().run_until_complete(runner._process_event(event, 2))

        logs = [b for b in broadcasts if b["type"] == "agent_log"]
        assert len(logs) == 1
        assert logs[0]["payload"]["action"] == "tool_call"
        assert "query_fleet" in logs[0]["payload"]["detail"]

    def test_function_response(self, runner, broadcasts):
        fr = _FakeFR("query_fleet", {"status": "ok", "data": {"total": 3}})
        event = _FakeEvent("dispatcher", [_FakePart(function_response=fr)])
        asyncio.get_event_loop().run_until_complete(runner._process_event(event, 2))

        logs = [b for b in broadcasts if b["type"] == "agent_log"]
        assert len(logs) == 1
        assert logs[0]["payload"]["action"] == "tool_result"
        assert "query_fleet" in logs[0]["payload"]["detail"]

    def test_mixed_parts(self, runner, broadcasts):
        """An event with text + function_call should produce 2 log entries."""
        fc = _FakeFC("sweep_scan", {"uav_id": "Alpha"})
        event = _FakeEvent("dispatcher", [
            _FakePart(text="I will scan with Alpha"),
            _FakePart(function_call=fc),
        ])
        asyncio.get_event_loop().run_until_complete(runner._process_event(event, 3))

        logs = [b for b in broadcasts if b["type"] == "agent_log"]
        assert len(logs) == 2
        actions = [l["payload"]["action"] for l in logs]
        assert "reasoning" in actions
        assert "tool_call" in actions

    def test_empty_event_ignored(self, runner, broadcasts):
        """Event with no content should not broadcast anything."""
        event = _FakeEvent("assessor", [])
        asyncio.get_event_loop().run_until_complete(runner._process_event(event, 1))
        assert len(broadcasts) == 0

    def test_event_without_content(self, runner, broadcasts):
        """Event with content=None should not crash."""
        class NoContent:
            author = "test"
            content = None
        asyncio.get_event_loop().run_until_complete(runner._process_event(NoContent(), 1))
        assert len(broadcasts) == 0

    def test_text_truncated_at_500(self, runner, broadcasts):
        long_text = "A" * 1000
        event = _FakeEvent("analyst", [_FakePart(text=long_text)])
        asyncio.get_event_loop().run_until_complete(runner._process_event(event, 1))

        logs = [b for b in broadcasts if b["type"] == "agent_log"]
        assert len(logs[0]["payload"]["detail"]) == 500

    def test_cycle_number_in_payload(self, runner, broadcasts):
        event = _FakeEvent("assessor", [_FakePart(text="test")])
        asyncio.get_event_loop().run_until_complete(runner._process_event(event, 42))

        logs = [b for b in broadcasts if b["type"] == "agent_log"]
        assert logs[0]["payload"]["cycle"] == 42

    def test_timestamp_in_payload(self, runner, broadcasts):
        import time
        before = time.time()
        event = _FakeEvent("assessor", [_FakePart(text="test")])
        asyncio.get_event_loop().run_until_complete(runner._process_event(event, 1))
        after = time.time()

        logs = [b for b in broadcasts if b["type"] == "agent_log"]
        assert before <= logs[0]["payload"]["timestamp"] <= after


# ── AgentRunner initialization ────────────────────────────────

class TestRunnerInit:
    def test_has_correct_agent_name(self, runner):
        assert runner._agent.name == "swarm_commander"

    def test_has_4_sub_agents(self, runner):
        assert len(runner._agent.sub_agents) == 4

    def test_initial_cycle_is_zero(self, runner):
        assert runner._cycle == 0

    def test_initial_not_running(self, runner):
        assert runner._running is False

    def test_session_id_initially_none(self, runner):
        assert runner._session_id is None
