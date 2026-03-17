"""
Test Suite 06: Mission BlackBox (Logging System)
Tests that reasoning logs are captured, structured, and retrievable.
"""
import pytest
import json
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


class TestBlackBoxExists:
    """BlackBox logging module must exist and be importable."""

    def test_blackbox_importable(self):
        from backend.utils.blackbox import MissionBlackBox
        assert MissionBlackBox is not None

    def test_blackbox_can_instantiate(self):
        from backend.utils.blackbox import MissionBlackBox
        bb = MissionBlackBox()
        assert bb is not None


class TestBlackBoxLogging:
    """BlackBox must capture structured log entries."""

    def test_log_entry(self):
        from backend.utils.blackbox import MissionBlackBox
        bb = MissionBlackBox()
        bb.log("assessor", "Evaluating fleet status — 5 UAVs active, coverage 23%")
        entries = bb.get_entries()
        assert len(entries) >= 1

    def test_log_has_timestamp(self):
        from backend.utils.blackbox import MissionBlackBox
        bb = MissionBlackBox()
        bb.log("strategist", "Planning sector assignments")
        entry = bb.get_entries()[-1]
        has_time = 'timestamp' in entry or 'time' in entry or 'ts' in entry
        assert has_time, f"Log entry missing timestamp: {entry}"

    def test_log_has_agent_name(self):
        from backend.utils.blackbox import MissionBlackBox
        bb = MissionBlackBox()
        bb.log("dispatcher", "Moving Alpha to (5,3)")
        entry = bb.get_entries()[-1]
        has_agent = 'agent' in entry or 'source' in entry or 'phase' in entry
        assert has_agent, f"Log entry missing agent/source: {entry}"

    def test_log_serializable(self):
        from backend.utils.blackbox import MissionBlackBox
        bb = MissionBlackBox()
        bb.log("analyst", "Mission complete — 3 survivors found")
        entries = bb.get_entries()
        try:
            json.dumps(entries)
        except (TypeError, ValueError) as e:
            pytest.fail(f"Log entries not JSON-serializable: {e}")

    def test_multiple_entries_ordered(self):
        from backend.utils.blackbox import MissionBlackBox
        bb = MissionBlackBox()
        bb.log("assessor", "Step 1")
        bb.log("strategist", "Step 2")
        bb.log("dispatcher", "Step 3")
        entries = bb.get_entries()
        assert len(entries) >= 3
        # Verify ordering (latest last)
        agents = [e.get('agent', e.get('source', e.get('phase', ''))) for e in entries[-3:]]
        assert agents == ["assessor", "strategist", "dispatcher"]

    def test_get_summary(self):
        """BlackBox should provide a summary method."""
        from backend.utils.blackbox import MissionBlackBox
        bb = MissionBlackBox()
        bb.log("assessor", "Fleet OK")
        bb.log("analyst", "Mission complete")
        summary = bb.get_summary() if hasattr(bb, 'get_summary') else bb.get_entries()
        assert summary is not None
        assert len(summary) > 0
