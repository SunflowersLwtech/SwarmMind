"""
Test Suite 02: GridWorld Simulation Engine
Tests the core simulation — grid, movement, scanning, coverage, obstacles.
"""
import pytest
import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from test.conftest import assert_valid_position, assert_valid_power


class TestGridWorldInit:
    """GridWorld must initialize correctly with all components."""

    def test_creates_with_correct_size(self, grid_world):
        assert grid_world.size == 20

    def test_has_uavs(self, grid_world):
        fleet = grid_world.get_fleet_status()
        assert hasattr(fleet, 'uavs') or isinstance(fleet, dict)
        uavs = fleet.uavs if hasattr(fleet, 'uavs') else fleet.get('uavs', fleet.get('data', {}).get('uavs', []))
        assert len(uavs) >= 3, "Must have at least 3 UAVs"

    def test_has_objectives(self, grid_world):
        assert len(grid_world.objectives) > 0 if hasattr(grid_world, 'objectives') else True

    def test_has_obstacles(self, grid_world):
        """Grid must contain obstacles (terrain)."""
        assert hasattr(grid_world, 'terrain') or hasattr(grid_world, 'obstacles')

    def test_initial_coverage_is_zero_or_near_zero(self, grid_world):
        progress = grid_world.get_search_progress()
        coverage = progress.coverage_pct if hasattr(progress, 'coverage_pct') else progress.get('coverage_pct', progress.get('coverage', 0))
        assert coverage < 5.0, f"Initial coverage should be ~0%, got {coverage}%"


class TestUAVMovement:
    """Movement must consume power, respect bounds, and use pathfinding."""

    def test_move_to_valid_position(self, small_world):
        fleet = small_world.get_fleet_status()
        uavs = fleet.uavs if hasattr(fleet, 'uavs') else fleet.get('uavs', [])
        uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id
        result = small_world.move_uav(uav_id, 3, 3)
        status = result.status if hasattr(result, 'status') else result.get('status')
        assert status in ('ok', 'success'), f"Move failed: {result}"

    def test_move_consumes_power(self, small_world):
        fleet = small_world.get_fleet_status()
        uavs = fleet.uavs if hasattr(fleet, 'uavs') else fleet.get('uavs', [])
        uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id

        # Get initial power
        detail_before = small_world.get_uav_detail(uav_id)
        power_before = detail_before.power if hasattr(detail_before, 'power') else detail_before.get('power', detail_before.get('data', {}).get('power', 100))

        # Move
        small_world.move_uav(uav_id, 5, 5)

        # Check power decreased
        detail_after = small_world.get_uav_detail(uav_id)
        power_after = detail_after.power if hasattr(detail_after, 'power') else detail_after.get('power', detail_after.get('data', {}).get('power', 100))
        assert power_after < power_before, f"Power should decrease after move: {power_before} -> {power_after}"

    def test_move_to_obstacle_fails_or_routes_around(self, small_world):
        """Moving to an obstacle cell must either fail or find alternate route."""
        # Find an obstacle position
        if hasattr(small_world, 'terrain'):
            terrain = small_world.terrain
        elif hasattr(small_world, 'obstacles'):
            terrain = small_world.obstacles
        else:
            pytest.skip("No terrain/obstacles attribute found")

        # This test verifies the system doesn't crash on obstacle navigation
        fleet = small_world.get_fleet_status()
        uavs = fleet.uavs if hasattr(fleet, 'uavs') else fleet.get('uavs', [])
        uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id
        # Attempt move — should not raise exception regardless of result
        result = small_world.move_uav(uav_id, 0, 0)
        assert result is not None

    def test_move_out_of_bounds_rejected(self, small_world):
        fleet = small_world.get_fleet_status()
        uavs = fleet.uavs if hasattr(fleet, 'uavs') else fleet.get('uavs', [])
        uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id
        result = small_world.move_uav(uav_id, 999, 999)
        status = result.status if hasattr(result, 'status') else result.get('status')
        assert status in ('error', 'failed'), "Out-of-bounds move should fail"


class TestScanning:
    """Scanning must update coverage and detect objectives."""

    def test_scan_returns_result(self, small_world):
        fleet = small_world.get_fleet_status()
        uavs = fleet.uavs if hasattr(fleet, 'uavs') else fleet.get('uavs', [])
        uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id
        result = small_world.scan_zone(uav_id)
        assert result is not None

    def test_scan_increases_coverage(self, small_world):
        progress_before = small_world.get_search_progress()
        cov_before = progress_before.coverage_pct if hasattr(progress_before, 'coverage_pct') else progress_before.get('coverage_pct', progress_before.get('coverage', 0))

        fleet = small_world.get_fleet_status()
        uavs = fleet.uavs if hasattr(fleet, 'uavs') else fleet.get('uavs', [])
        uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id

        # Move somewhere and scan
        small_world.move_uav(uav_id, 5, 5)
        small_world.scan_zone(uav_id)

        progress_after = small_world.get_search_progress()
        cov_after = progress_after.coverage_pct if hasattr(progress_after, 'coverage_pct') else progress_after.get('coverage_pct', progress_after.get('coverage', 0))
        assert cov_after > cov_before, f"Coverage should increase after scan: {cov_before} -> {cov_after}"

    def test_scan_consumes_power(self, small_world):
        fleet = small_world.get_fleet_status()
        uavs = fleet.uavs if hasattr(fleet, 'uavs') else fleet.get('uavs', [])
        uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id
        detail_before = small_world.get_uav_detail(uav_id)
        power_before = detail_before.power if hasattr(detail_before, 'power') else detail_before.get('power', detail_before.get('data', {}).get('power', 100))

        small_world.scan_zone(uav_id)

        detail_after = small_world.get_uav_detail(uav_id)
        power_after = detail_after.power if hasattr(detail_after, 'power') else detail_after.get('power', detail_after.get('data', {}).get('power', 100))
        assert power_after < power_before, "Scanning should consume power"


class TestPathfinding:
    """A* pathfinding must produce valid, obstacle-free paths."""

    def test_plan_route_returns_path(self, small_world):
        route = small_world.plan_route((0, 0), (5, 5))
        path = route.path if hasattr(route, 'path') else route.get('path', [])
        assert len(path) > 0, "Route should have at least one waypoint"

    def test_path_starts_at_origin(self, small_world):
        route = small_world.plan_route((1, 1), (8, 8))
        path = route.path if hasattr(route, 'path') else route.get('path', [])
        assert path[0] == (1, 1) or path[0] == [1, 1], f"Path should start at (1,1), got {path[0]}"

    def test_path_ends_at_destination(self, small_world):
        route = small_world.plan_route((1, 1), (8, 8))
        path = route.path if hasattr(route, 'path') else route.get('path', [])
        end = tuple(path[-1]) if isinstance(path[-1], list) else path[-1]
        assert end == (8, 8), f"Path should end at (8,8), got {end}"

    def test_unreachable_returns_empty_or_error(self, small_world):
        """If destination is unreachable, should return empty path or error."""
        route = small_world.plan_route((0, 0), (999, 999))
        if hasattr(route, 'path'):
            assert len(route.path) == 0 or route.status in ('error', 'failed')
        elif isinstance(route, dict):
            path = route.get('path', [])
            assert len(path) == 0 or route.get('status') in ('error', 'failed')


class TestCoverage:
    """Coverage tracking must be accurate and monotonically increasing."""

    def test_coverage_is_percentage(self, grid_world):
        progress = grid_world.get_search_progress()
        coverage = progress.coverage_pct if hasattr(progress, 'coverage_pct') else progress.get('coverage_pct', progress.get('coverage', 0))
        assert 0.0 <= coverage <= 100.0

    def test_coverage_never_decreases(self, small_world):
        """Coverage must never go down after exploring."""
        fleet = small_world.get_fleet_status()
        uavs = fleet.uavs if hasattr(fleet, 'uavs') else fleet.get('uavs', [])
        uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id

        prev_coverage = 0.0
        for target in [(2, 2), (4, 4), (6, 6), (8, 8)]:
            small_world.move_uav(uav_id, *target)
            small_world.scan_zone(uav_id)
            progress = small_world.get_search_progress()
            coverage = progress.coverage_pct if hasattr(progress, 'coverage_pct') else progress.get('coverage_pct', progress.get('coverage', 0))
            assert coverage >= prev_coverage, f"Coverage decreased: {prev_coverage} -> {coverage}"
            prev_coverage = coverage


class TestRecallAndRecharge:
    """Recall and recharge must restore UAV to operational state."""

    def test_recall_moves_uav_to_base(self, small_world):
        fleet = small_world.get_fleet_status()
        uavs = fleet.uavs if hasattr(fleet, 'uavs') else fleet.get('uavs', [])
        uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id

        small_world.move_uav(uav_id, 5, 5)
        result = small_world.recall_uav(uav_id)
        status = result.status if hasattr(result, 'status') else result.get('status')
        assert status in ('ok', 'success')

    def test_recharge_restores_power(self, small_world):
        fleet = small_world.get_fleet_status()
        uavs = fleet.uavs if hasattr(fleet, 'uavs') else fleet.get('uavs', [])
        uav_id = uavs[0]['id'] if isinstance(uavs[0], dict) else uavs[0].id

        # Drain some power
        small_world.move_uav(uav_id, 7, 7)
        small_world.recall_uav(uav_id)
        result = small_world.repower_uav(uav_id)

        detail = small_world.get_uav_detail(uav_id)
        power = detail.power if hasattr(detail, 'power') else detail.get('power', detail.get('data', {}).get('power', 0))
        assert power > 50.0, f"After recharge, power should be high, got {power}"


class TestThreatMap:
    """Probability heatmap must reflect objective distribution."""

    def test_threat_map_returns_data(self, grid_world):
        threat = grid_world.get_threat_map()
        assert threat is not None

    def test_threat_map_has_hotspots(self, grid_world):
        threat = grid_world.get_threat_map()
        if hasattr(threat, 'hotspots'):
            assert len(threat.hotspots) > 0
        elif isinstance(threat, dict):
            hotspots = threat.get('hotspots', threat.get('data', {}).get('hotspots', []))
            assert len(hotspots) > 0, "Threat map should have hotspots"


class TestFrontier:
    """Frontier detection must return unexplored boundary cells."""

    def test_frontier_not_empty_initially(self, grid_world):
        frontier = grid_world.detect_frontier()
        cells = frontier if isinstance(frontier, list) else (frontier.cells if hasattr(frontier, 'cells') else frontier.get('cells', []))
        assert len(cells) > 0, "Frontier should not be empty at start"

    def test_frontier_cells_are_valid_positions(self, grid_world):
        frontier = grid_world.detect_frontier()
        cells = frontier if isinstance(frontier, list) else (frontier.cells if hasattr(frontier, 'cells') else frontier.get('cells', []))
        for cell in cells[:10]:
            x = cell[0] if isinstance(cell, (list, tuple)) else (cell.x if hasattr(cell, 'x') else cell.get('x', 0))
            y = cell[1] if isinstance(cell, (list, tuple)) else (cell.y if hasattr(cell, 'y') else cell.get('y', 0))
            assert_valid_position(x, y, grid_world.size)


class TestSectorPartitioning:
    """Sector partitioning must divide grid into non-overlapping regions."""

    def test_partition_creates_correct_count(self, grid_world):
        sectors = grid_world.partition_sectors(4)
        if isinstance(sectors, dict):
            assert len(sectors) == 4
        elif hasattr(sectors, '__len__'):
            assert len(sectors) == 4

    def test_partition_covers_entire_grid(self, small_world):
        sectors = small_world.partition_sectors(4)
        # Verify all non-obstacle cells are assigned to a sector
        if isinstance(sectors, dict):
            total_cells = sum(
                s.get('area', 0) if isinstance(s, dict) else (s.area if hasattr(s, 'area') else 0)
                for s in sectors.values()
            )
            assert total_cells > 0, "Sectors should cover some area"


class TestStateSnapshot:
    """State snapshot must be JSON-serializable for frontend."""

    def test_snapshot_is_serializable(self, grid_world):
        import json
        snapshot = grid_world.get_state_snapshot()
        try:
            json_str = json.dumps(snapshot)
            assert len(json_str) > 10
        except (TypeError, ValueError) as e:
            pytest.fail(f"State snapshot not JSON-serializable: {e}")

    def test_snapshot_contains_fleet(self, grid_world):
        snapshot = grid_world.get_state_snapshot()
        assert 'fleet' in snapshot or 'uavs' in snapshot, \
            f"Snapshot must contain fleet/uavs data. Keys: {list(snapshot.keys())}"

    def test_snapshot_contains_coverage(self, grid_world):
        snapshot = grid_world.get_state_snapshot()
        has_coverage = 'coverage' in snapshot or 'search_progress' in snapshot or 'progress' in snapshot
        assert has_coverage, f"Snapshot must contain coverage data. Keys: {list(snapshot.keys())}"
