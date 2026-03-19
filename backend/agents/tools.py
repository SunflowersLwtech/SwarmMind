"""FunctionTool closures for ADK agent — mirrors MCP tool_server.py logic.

Each function closes over a shared GridWorld instance. ADK auto-wraps
them as FunctionTool and auto-executes them when the LLM emits function_call.

13 operational tools across 5 categories:
  1. Fleet Intelligence: query_fleet, inspect_uav, get_threat_map, get_search_progress
  2. Navigation: navigate_to, plan_route
  3. Reconnaissance: sweep_scan, detect_frontier, mark_objective
  4. Resource Management: recall_uav, repower_uav, assess_endurance
  5. Situational Awareness: get_situational_awareness (composite)
"""
from __future__ import annotations

from backend.core.grid_world import GridWorld


def make_tools(world: GridWorld) -> list:
    """Return 13 sync functions closing over *world* for ADK FunctionTool wrapping."""

    # ── Category 1: Fleet Intelligence ────────────────────────────

    def query_fleet() -> dict:
        """Get complete fleet status — all UAVs with position, power, status, and summary statistics."""
        status = world.get_fleet_status()
        return {"status": "ok", "data": status.model_dump()}

    def inspect_uav(uav_id: str) -> dict:
        """Get detailed telemetry for a single UAV including mission history."""
        detail = world.get_uav_detail(uav_id)
        if not detail:
            return {"status": "error", "message": f"UAV '{uav_id}' not found"}
        return {"status": "ok", "data": detail.model_dump()}

    def get_threat_map() -> dict:
        """Get probability heatmap — shows likelihood of survivors at each cell, plus top-5 hotspots."""
        threat = world.get_threat_map()
        return {"status": "ok", "data": threat.model_dump()}

    def get_search_progress() -> dict:
        """Get search coverage statistics — percentage explored, objectives found, cells remaining."""
        progress = world.get_search_progress()
        return {"status": "ok", "data": progress.model_dump()}

    # ── Category 2: Navigation ────────────────────────────────────

    def navigate_to(uav_id: str, x: int, y: int) -> dict:
        """Set a navigation waypoint for a UAV. Movement is gradual (1 cell/tick via autopilot), NOT instant teleport."""
        uav = world.get_uav(uav_id)
        if not uav:
            return {"status": "error", "message": f"UAV '{uav_id}' not found"}
        result = world.set_waypoint(uav_id, x, y)
        return {"status": result.status, "data": result.model_dump()}

    def plan_route(start_x: int, start_y: int, end_x: int, end_y: int) -> dict:
        """Plan an A* route WITHOUT executing it. Returns optimal path, distance, and estimated power cost."""
        route = world.plan_route(start_x, start_y, end_x, end_y)
        return {"status": "ok", "data": route.model_dump()}

    # ── Category 3: Reconnaissance ────────────────────────────────

    def sweep_scan(uav_id: str) -> dict:
        """Perform thermal scan around a UAV's current position."""
        uav = world.get_uav(uav_id)
        if not uav:
            return {"status": "error", "message": f"UAV '{uav_id}' not found"}
        result = world.scan_zone(uav_id)
        return {"status": "ok", "data": result.model_dump()}

    def detect_frontier() -> dict:
        """Find unexplored cells adjacent to explored areas, sorted by probability."""
        frontier = world.detect_frontier()
        data = [f.model_dump() for f in frontier[:20]]
        return {"status": "ok", "data": data, "total_frontier": len(frontier)}

    def mark_objective(objective_id: str, uav_id: str) -> dict:
        """Claim a detected objective for a UAV to prevent duplicate rescue attempts."""
        success = world.objective_field.claim_objective(objective_id, uav_id)
        if success:
            return {"status": "ok", "message": f"{uav_id} claimed {objective_id}"}
        return {"status": "error", "message": f"{objective_id} already claimed or not found"}

    # ── Category 4: Resource Management ───────────────────────────

    def recall_uav(uav_id: str) -> dict:
        """Set a return-to-base waypoint. Movement is gradual (1 cell/tick), NOT instant teleport."""
        uav = world.get_uav(uav_id)
        if not uav:
            return {"status": "error", "message": f"UAV '{uav_id}' not found"}
        result = world.set_recall_waypoint(uav_id)
        return {"status": result.status, "data": result.model_dump()}

    def repower_uav(uav_id: str) -> dict:
        """Charge a UAV at base station. Each call restores 20% power."""
        uav = world.get_uav(uav_id)
        if not uav:
            return {"status": "error", "message": f"UAV '{uav_id}' not found"}
        result = world.repower_uav(uav_id)
        return {"status": "ok", "data": result.model_dump()}

    def assess_endurance() -> dict:
        """Assess remaining flight endurance for each UAV."""
        endurance = []
        base = world.terrain.base_position
        for uav in world.fleet.values():
            route = world.plan_route(uav.x, uav.y, base[0], base[1])
            cells_remaining = int(uav.power // uav.POWER_MOVE)
            power_to_return = route.power_cost
            power_after_return = uav.power - power_to_return
            # safe: can return with >10% power remaining
            safe_to_recall = route.reachable and power_after_return > 10.0
            # urgent: must return NOW or will die (less than 5% margin)
            urgent_recall = route.reachable and power_after_return < 5.0
            # explorable: power left for searching after reserving return cost
            explorable_cells = max(0, int((uav.power - power_to_return - 5.0) // uav.POWER_MOVE))
            endurance.append({
                "uav_id": uav.id,
                "status": uav.status.value,
                "power": round(uav.power, 1),
                "cells_remaining": cells_remaining,
                "explorable_cells": explorable_cells,
                "distance_to_base": route.distance,
                "power_to_return": round(power_to_return, 1),
                "safe_to_recall": safe_to_recall,
                "urgent_recall": urgent_recall,
            })
        return {"status": "ok", "data": endurance}

    # ── Category 5: Situational Awareness (composite) ─────────────

    def get_situational_awareness() -> dict:
        """Get complete situational picture — fleet, coverage, threats, endurance — in one call."""
        data = world.get_situational_awareness()
        return {"status": "ok", "data": data}

    return [
        query_fleet, inspect_uav, get_threat_map, get_search_progress,
        navigate_to, plan_route, sweep_scan, detect_frontier, mark_objective,
        recall_uav, repower_uav, assess_endurance,
        get_situational_awareness,
    ]
