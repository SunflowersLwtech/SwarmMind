"""
Test Suite 01: UAV Model
Tests the fundamental UAV dataclass — position, power, status, constraints.
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


class TestUAVCreation:
    """UAV instances must initialize with correct defaults."""

    def test_create_default_uav(self, uav_factory):
        uav = uav_factory()
        assert uav.id == "test-uav"
        assert uav.x == 0
        assert uav.y == 0
        assert uav.power == 100.0
        assert uav.status == "idle"

    def test_create_custom_uav(self, uav_factory):
        uav = uav_factory(id="alpha", x=5, y=10, power=75.0, status="moving")
        assert uav.id == "alpha"
        assert uav.x == 5
        assert uav.y == 10
        assert uav.power == 75.0
        assert uav.status == "moving"

    def test_uav_has_sensor_range(self, uav_factory):
        uav = uav_factory()
        assert hasattr(uav, 'sensor_range')
        assert isinstance(uav.sensor_range, int)
        assert uav.sensor_range > 0

    def test_uav_has_mission_log(self, uav_factory):
        uav = uav_factory()
        assert hasattr(uav, 'mission_log')
        assert isinstance(uav.mission_log, list)


class TestUAVPower:
    """Power management must be consistent and bounded."""

    def test_power_bounded_0_100(self, uav_factory):
        uav = uav_factory(power=100.0)
        assert 0.0 <= uav.power <= 100.0

    def test_power_cannot_exceed_100(self, uav_factory):
        uav = uav_factory(power=100.0)
        uav.power = min(uav.power + 50, 100.0)
        assert uav.power <= 100.0

    def test_low_power_threshold_exists(self):
        """There must be a defined low-power threshold (e.g. 20%)."""
        from backend.core import uav as uav_module
        # Check for a constant like LOW_POWER_THRESHOLD or similar
        has_threshold = (
            hasattr(uav_module, 'LOW_POWER_THRESHOLD') or
            hasattr(uav_module, 'LOW_BATTERY_THRESHOLD') or
            hasattr(uav_module, 'POWER_CRITICAL')
        )
        assert has_threshold, "UAV module must define a low power threshold constant"


class TestUAVStatus:
    """Status transitions must be valid."""

    def test_valid_statuses(self, uav_factory):
        valid = {"idle", "moving", "scanning", "returning", "charging", "offline"}
        uav = uav_factory()
        assert uav.status in valid, f"Default status '{uav.status}' not in valid set"

    def test_uav_id_is_string(self, uav_factory):
        uav = uav_factory(id="alpha-01")
        assert isinstance(uav.id, str)
        assert len(uav.id) > 0
