"""
Test Suite 09: Full-Stack Consistency
Ensures every backend feature has a corresponding frontend consumer,
and every frontend component has a corresponding backend provider.
"""
import pytest
import os
import re
import json
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

FRONTEND_SRC = os.path.join(os.path.dirname(__file__), '../../frontend/src')
BACKEND_DIR = os.path.join(os.path.dirname(__file__), '../../backend')


def read_all_frontend_files():
    """Read all .jsx/.js/.tsx/.ts files in frontend/src/."""
    content = ""
    if not os.path.exists(FRONTEND_SRC):
        return content
    for root, dirs, files in os.walk(FRONTEND_SRC):
        for f in files:
            if f.endswith(('.jsx', '.js', '.tsx', '.ts')) and 'node_modules' not in root:
                with open(os.path.join(root, f), 'r', errors='ignore') as fh:
                    content += f"\n// === {f} ===\n" + fh.read()
    return content


def read_all_backend_files():
    """Read all .py files in backend/."""
    content = ""
    for root, dirs, files in os.walk(BACKEND_DIR):
        for f in files:
            if f.endswith('.py') and '__pycache__' not in root:
                with open(os.path.join(root, f), 'r', errors='ignore') as fh:
                    content += f"\n# === {f} ===\n" + fh.read()
    return content


class TestBackendFeaturesHaveFrontendUI:
    """Every significant backend feature must be visible in the frontend."""

    def test_fleet_status_displayed(self):
        """Backend provides fleet data → Frontend must render UAV list/status."""
        fe = read_all_frontend_files()
        assert fe, "Frontend source files not found"
        has_fleet_ui = any(term in fe.lower() for term in ['fleet', 'uav', 'drone', 'aircraft'])
        assert has_fleet_ui, "Frontend must display fleet/UAV status"

    def test_coverage_displayed(self):
        """Backend tracks coverage → Frontend must show coverage metric."""
        fe = read_all_frontend_files()
        has_coverage = any(term in fe.lower() for term in ['coverage', 'progress', 'explored'])
        assert has_coverage, "Frontend must display coverage/progress"

    def test_cot_logs_displayed(self):
        """Backend generates CoT logs → Frontend must show reasoning panel."""
        fe = read_all_frontend_files()
        has_logs = any(term in fe.lower() for term in ['log', 'reasoning', 'blackbox', 'console', 'thought'])
        assert has_logs, "Frontend must display agent reasoning/CoT logs"

    def test_3d_map_exists(self):
        """Backend provides positions → Frontend must render 3D map."""
        fe = read_all_frontend_files()
        has_3d = any(term in fe.lower() for term in ['canvas', 'three', 'r3f', 'fiber', 'mesh', 'scene'])
        assert has_3d, "Frontend must have 3D scene rendering (R3F Canvas)"

    def test_mission_controls_exist(self):
        """Backend has ops endpoints → Frontend must have start/stop buttons."""
        fe = read_all_frontend_files()
        has_controls = any(term in fe.lower() for term in ['start', 'stop', 'pause', 'mission', 'ops'])
        assert has_controls, "Frontend must have mission control buttons (start/stop)"

    def test_websocket_connection(self):
        """Backend has WebSocket → Frontend must connect to it."""
        fe = read_all_frontend_files()
        has_ws = any(term in fe.lower() for term in ['websocket', 'ws://', 'usews', 'socket'])
        assert has_ws, "Frontend must connect to WebSocket for real-time updates"

    def test_dashboard_metrics(self):
        """Backend provides metrics → Frontend must show dashboard."""
        fe = read_all_frontend_files()
        has_dashboard = any(term in fe.lower() for term in ['dashboard', 'metric', 'chart', 'tremor', 'recharts', 'kpi'])
        assert has_dashboard, "Frontend must have dashboard with metrics/charts"


class TestFrontendComponentsHaveBackendSupport:
    """Every frontend component must have corresponding backend data."""

    def test_fleet_panel_has_api(self):
        """FleetPanel component → backend must provide fleet data via API/WS."""
        be = read_all_backend_files()
        has_fleet_api = any(term in be.lower() for term in ['fleet', 'uav', 'query_fleet', 'get_fleet'])
        assert has_fleet_api, "Backend must provide fleet data for FleetPanel"

    def test_3d_scene_has_position_data(self):
        """3D scene needs position data → backend must provide x,y coordinates."""
        be = read_all_backend_files()
        has_pos = any(term in be for term in ['.x', '.y', 'position', 'coordinates'])
        assert has_pos, "Backend must provide position data for 3D rendering"

    def test_command_console_has_ops_api(self):
        """CommandConsole needs ops → backend must have start/stop endpoints."""
        be = read_all_backend_files()
        has_ops = any(term in be.lower() for term in ['ops', 'start_mission', 'stop_mission', '/start', '/stop'])
        assert has_ops, "Backend must have mission operations endpoints"

    def test_event_timeline_has_events(self):
        """EventTimeline component → backend must track events."""
        be = read_all_backend_files()
        has_events = any(term in be.lower() for term in ['event', 'timeline', 'log', 'history', 'blackbox'])
        assert has_events, "Backend must track events/logs for timeline"


class TestFrontendStructure:
    """Frontend must follow the planned component architecture."""

    def test_frontend_dir_exists(self):
        assert os.path.exists(FRONTEND_SRC), "frontend/src/ directory must exist"

    def test_package_json_exists(self):
        pkg = os.path.join(os.path.dirname(__file__), '../../frontend/package.json')
        assert os.path.exists(pkg), "frontend/package.json must exist"

    def test_has_scene_components(self):
        """Must have 3D scene components (not inline in App.jsx)."""
        scene_dir = os.path.join(FRONTEND_SRC, 'scene')
        components_dir = os.path.join(FRONTEND_SRC, 'components')
        has_scene = os.path.isdir(scene_dir) or os.path.isdir(components_dir)
        assert has_scene, "Frontend must have scene/ or components/ directory"

    def test_has_state_management(self):
        """Must have zustand store (not just useState)."""
        fe = read_all_frontend_files()
        has_zustand = 'zustand' in fe or 'create(' in fe
        has_store_dir = os.path.isdir(os.path.join(FRONTEND_SRC, 'stores')) or \
                        os.path.isdir(os.path.join(FRONTEND_SRC, 'store'))
        assert has_zustand or has_store_dir, "Frontend must use zustand (not just useState)"

    def test_uses_r3f_not_raw_threejs(self):
        """Must use React Three Fiber, not raw Three.js."""
        fe = read_all_frontend_files()
        has_r3f = '@react-three/fiber' in fe or 'from \'@react-three' in fe or "from '@react-three" in fe
        assert has_r3f, "Frontend must use @react-three/fiber (R3F), not raw Three.js"

    def test_has_dark_theme(self):
        """Must have dark theme (military command center aesthetic)."""
        css_files = ""
        for root, dirs, files in os.walk(FRONTEND_SRC):
            for f in files:
                if f.endswith(('.css', '.scss', '.jsx', '.tsx')):
                    with open(os.path.join(root, f), 'r', errors='ignore') as fh:
                        css_files += fh.read()
        # Check for dark background colors
        dark_indicators = ['#0B1426', '#0b1426', '#111', '#1B2735', 'bg-gray-9', 'bg-slate-9', 'dark']
        has_dark = any(ind in css_files for ind in dark_indicators)
        assert has_dark, "Frontend must have dark theme (military aesthetic)"
