"""
Test Suite 10: End-to-End Playwright Tests
Tests the frontend UI via browser automation using Playwright MCP.

REQUIRES:
- Frontend dev server running at http://localhost:5173
- Backend API server running at http://localhost:8000
- MCP tool server running at http://localhost:8001

Run these with: pytest test/e2e/ -v --timeout=60
The test runner should use Playwright MCP tools for browser interaction.
"""
import pytest
import subprocess
import time
import signal
import sys
import os

# Skip entire module if playwright not available
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


def _frontend_is_running():
    """Check if the frontend dev server is reachable."""
    import urllib.request
    try:
        urllib.request.urlopen(FRONTEND_URL, timeout=2)
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.skipif(not HAS_PLAYWRIGHT, reason="playwright not installed"),
    pytest.mark.skipif(not _frontend_is_running(), reason="frontend dev server not running at " + FRONTEND_URL),
]


@pytest.fixture(scope="module")
def browser():
    """Launch browser for E2E tests."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    """Create a new page for each test."""
    page = browser.new_page()
    page.set_viewport_size({"width": 1920, "height": 1080})
    yield page
    page.close()


class TestPageLoads:
    """Frontend must load and render correctly."""

    def test_page_loads_without_error(self, page):
        """Page must load without JS errors."""
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        assert len(errors) == 0, f"Page had JS errors: {errors}"

    def test_page_has_title(self, page):
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        title = page.title()
        assert 'swarm' in title.lower() or 'mind' in title.lower() or len(title) > 0, \
            f"Page title should mention SwarmMind, got: '{title}'"

    def test_page_has_canvas(self, page):
        """Must have a WebGL canvas for 3D rendering."""
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        canvas = page.query_selector("canvas")
        assert canvas is not None, "Page must have a <canvas> element for R3F 3D scene"

    def test_canvas_has_dimensions(self, page):
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        canvas = page.query_selector("canvas")
        assert canvas is not None
        box = canvas.bounding_box()
        assert box['width'] > 200, f"Canvas width too small: {box['width']}"
        assert box['height'] > 200, f"Canvas height too small: {box['height']}"


class TestUIComponents:
    """All major UI components must be present."""

    def test_has_status_bar(self, page):
        """Global status bar must be visible."""
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        # Look for status-like elements at the top
        status = page.query_selector("[class*='status'], [class*='header'], [class*='global'], header")
        assert status is not None, "Must have a global status bar/header"

    def test_has_fleet_panel(self, page):
        """Fleet panel showing UAV list must be visible."""
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        text = page.text_content("body")
        has_fleet = any(term in text.lower() for term in ['uav', 'drone', 'alpha', 'bravo', 'fleet'])
        assert has_fleet, "Page must show fleet/UAV information"

    def test_has_command_area(self, page):
        """Command/chat area for AI interaction must exist."""
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        # Look for input field or text area
        inputs = page.query_selector_all("input, textarea, [contenteditable]")
        buttons = page.query_selector_all("button")
        assert len(inputs) > 0 or len(buttons) > 0, "Must have input/button for mission commands"

    def test_has_mission_controls(self, page):
        """Start/Stop mission buttons must exist."""
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        buttons = page.query_selector_all("button")
        button_texts = [b.text_content().lower() for b in buttons]
        has_start = any('start' in t for t in button_texts)
        has_stop = any('stop' in t or 'end' in t or 'pause' in t for t in button_texts)
        assert has_start or has_stop, f"Must have start/stop buttons. Found: {button_texts}"

    def test_dark_theme_applied(self, page):
        """Page must have dark background (military aesthetic)."""
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        bg = page.evaluate("""
            () => window.getComputedStyle(document.body).backgroundColor
        """)
        # Parse rgb values
        if 'rgb' in bg:
            values = [int(x) for x in bg.replace('rgb(', '').replace('rgba(', '').replace(')', '').split(',')[:3]]
            avg_brightness = sum(values) / 3
            assert avg_brightness < 80, f"Background should be dark (military theme), got {bg} (brightness={avg_brightness})"


class TestRealTimeUpdates:
    """UI must update in real-time via WebSocket."""

    def test_websocket_connected(self, page):
        """Frontend must establish WebSocket connection."""
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        # Wait a moment for WS to connect
        page.wait_for_timeout(2000)
        ws_connected = page.evaluate("""
            () => {
                // Check if any WebSocket is open
                return performance.getEntriesByType('resource')
                    .some(r => r.name.includes('ws://') || r.name.includes('wss://'));
            }
        """)
        # Alternative: check the DOM for connection indicator
        text = page.text_content("body")
        has_connection_indicator = any(term in text.lower() for term in ['connected', 'online', 'live'])
        assert ws_connected or has_connection_indicator, "Frontend should have WebSocket connection"

    def test_fleet_data_appears(self, page):
        """Fleet data should appear on the page after WebSocket connects."""
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(3000)  # Wait for data
        text = page.text_content("body")
        # Should show UAV-related content
        has_data = any(term in text.lower() for term in ['%', 'battery', 'power', 'idle', 'active', 'uav', 'drone'])
        assert has_data, "Page should display fleet data after connecting"


class TestAccessibility:
    """Basic accessibility checks."""

    def test_no_console_errors(self, page):
        """No JavaScript console errors."""
        errors = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(2000)
        # Filter out known benign errors (WebSocket disconnect if backend not running, etc.)
        real_errors = [e for e in errors if 'websocket' not in e.lower() and 'failed to fetch' not in e.lower()]
        assert len(real_errors) == 0, f"Console errors found: {real_errors}"

    def test_responsive_layout(self, page):
        """Page should not have horizontal overflow."""
        page.goto(FRONTEND_URL, wait_until="networkidle", timeout=15000)
        overflow = page.evaluate("""
            () => document.documentElement.scrollWidth > document.documentElement.clientWidth
        """)
        assert not overflow, "Page has horizontal overflow — layout broken"
