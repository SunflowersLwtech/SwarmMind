"""SwarmMind MCP Tool Server — 13 operational tools for drone fleet C2.

Refactored to follow least-privilege principles:
- Removed admin/simulation tools (init_scenario, deploy_uav, inject_event)
  → Use test fixtures or backend.core.grid_world directly for testing.
- Removed prescriptive planning tools (partition_sectors, assign_sector)
  → Agent decides strategy autonomously via detect_frontier + plan_route.
- Removed redundant composite (get_op_summary)
  → get_situational_awareness covers the same data.

Run as independent process:
    conda run -n swarmmind python -m backend.services.tool_server

Transport: Streamable HTTP at /mcp (SSE is deprecated).
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from mcp.server.fastmcp import FastMCP, Context


# ─── Shared world injection (set by main.py before MCP starts) ────

_shared_world: GridWorld | None = None


def set_shared_world(w: GridWorld) -> None:
    """Inject the simulation's GridWorld so MCP tools share the same instance."""
    global _shared_world
    _shared_world = w


# ─── Lifespan: initialise GridWorld (lazy imports for fast startup) ──

@asynccontextmanager
async def fleet_lifespan(server: FastMCP):
    """Create and yield the simulation world for the server's lifetime."""
    # Lazy imports — deferred to after uvicorn binds the port
    from backend.core.grid_world import GridWorld
    from backend.services.fleet_connector import FleetConnector

    world = _shared_world or GridWorld(size=20, num_uavs=5, num_objectives=8, num_obstacles=15)
    connector = FleetConnector(world=world, ready=True)
    yield connector


mcp = FastMCP(
    "SwarmMind-Fleet",
    lifespan=fleet_lifespan,
)


def _connector(ctx: Context) -> FleetConnector:
    """Extract FleetConnector from context with guard check."""
    connector: FleetConnector = ctx.request_context.lifespan_context
    if not connector.ready:
        raise RuntimeError("Fleet not initialised")
    return connector


# ═══════════════════════════════════════════════════════════════
#  Category 1: Fleet Intelligence (態勢感知)
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def query_fleet(ctx: Context) -> dict:
    """Get complete fleet status — all UAVs with position, power, status, and summary statistics."""
    c = _connector(ctx)
    status = c.world.get_fleet_status()
    return {"status": "ok", "data": status.model_dump()}


@mcp.tool()
async def inspect_uav(uav_id: str, ctx: Context) -> dict:
    """Get detailed telemetry for a single UAV including mission history."""
    c = _connector(ctx)
    detail = c.world.get_uav_detail(uav_id)
    if not detail:
        return {"status": "error", "message": f"UAV '{uav_id}' not found"}
    return {"status": "ok", "data": detail.model_dump()}


@mcp.tool()
async def get_threat_map(ctx: Context) -> dict:
    """Get probability heatmap — shows likelihood of survivors at each cell, plus top-5 hotspots."""
    c = _connector(ctx)
    threat = c.world.get_threat_map()
    return {"status": "ok", "data": threat.model_dump()}


@mcp.tool()
async def get_search_progress(ctx: Context) -> dict:
    """Get search coverage statistics — percentage explored, objectives found, cells remaining."""
    c = _connector(ctx)
    progress = c.world.get_search_progress()
    return {"status": "ok", "data": progress.model_dump()}


# ═══════════════════════════════════════════════════════════════
#  Category 2: Navigation & Pathfinding (導航)
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def navigate_to(uav_id: str, x: int, y: int, ctx: Context) -> dict:
    """Set a navigation waypoint for a UAV. The UAV moves to the target via A* pathfinding, executing one cell per simulation tick (NOT instant teleport). Returns the planned path, ETA, and estimated power cost. Call sweep_scan only AFTER the UAV has arrived."""
    c = _connector(ctx)
    uav = c.world.get_uav(uav_id)
    if not uav:
        return {"status": "error", "message": f"UAV '{uav_id}' not found"}
    result = c.world.set_waypoint(uav_id, x, y)
    return {"status": result.status, "data": result.model_dump()}


@mcp.tool()
async def plan_route(start_x: int, start_y: int, end_x: int, end_y: int, ctx: Context) -> dict:
    """Plan an A* route WITHOUT executing it. Returns optimal path, distance, and estimated power cost. Use this to evaluate movement options before committing."""
    c = _connector(ctx)
    route = c.world.plan_route(start_x, start_y, end_x, end_y)
    return {"status": "ok", "data": route.model_dump()}


# ═══════════════════════════════════════════════════════════════
#  Category 3: Reconnaissance (偵察)
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def sweep_scan(uav_id: str, ctx: Context) -> dict:
    """Perform thermal scan around a UAV's current position. Detects objectives within sensor range and updates the probability heatmap."""
    c = _connector(ctx)
    uav = c.world.get_uav(uav_id)
    if not uav:
        return {"status": "error", "message": f"UAV '{uav_id}' not found"}
    result = c.world.scan_zone(uav_id)
    return {"status": "ok", "data": result.model_dump()}


@mcp.tool()
async def detect_frontier(ctx: Context) -> dict:
    """Find unexplored cells adjacent to explored areas, sorted by probability (highest priority first). Use this to decide where to search next."""
    c = _connector(ctx)
    frontier = c.world.detect_frontier()
    data = [f.model_dump() for f in frontier[:20]]  # top 20
    return {"status": "ok", "data": data, "total_frontier": len(frontier)}


@mcp.tool()
async def mark_objective(objective_id: str, uav_id: str, ctx: Context) -> dict:
    """Claim a detected objective for a UAV to prevent duplicate rescue attempts."""
    c = _connector(ctx)
    success = c.world.objective_field.claim_objective(objective_id, uav_id)
    if success:
        return {"status": "ok", "message": f"{uav_id} claimed {objective_id}"}
    return {"status": "error", "message": f"{objective_id} already claimed or not found"}


# ═══════════════════════════════════════════════════════════════
#  Category 4: Resource Management (資源管理)
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def recall_uav(uav_id: str, ctx: Context) -> dict:
    """Set a return-to-base waypoint for a UAV. The UAV navigates back via A* pathfinding, one cell per tick (NOT instant teleport). Returns planned path and ETA."""
    c = _connector(ctx)
    uav = c.world.get_uav(uav_id)
    if not uav:
        return {"status": "error", "message": f"UAV '{uav_id}' not found"}
    result = c.world.set_recall_waypoint(uav_id)
    return {"status": result.status, "data": result.model_dump()}


@mcp.tool()
async def repower_uav(uav_id: str, ctx: Context) -> dict:
    """Charge a UAV that is at the base station. Each call restores 20% power."""
    c = _connector(ctx)
    uav = c.world.get_uav(uav_id)
    if not uav:
        return {"status": "error", "message": f"UAV '{uav_id}' not found"}
    result = c.world.repower_uav(uav_id)
    return {"status": "ok", "data": result.model_dump()}


@mcp.tool()
async def assess_endurance(ctx: Context) -> dict:
    """Assess remaining flight endurance for each UAV — power left, estimated cells remaining, safe recall window."""
    c = _connector(ctx)
    endurance = []
    base = c.world.terrain.base_position
    for uav in c.world.fleet.values():
        route = c.world.plan_route(uav.x, uav.y, base[0], base[1])
        cells_remaining = int(uav.power // uav.POWER_MOVE)
        power_to_return = route.power_cost
        power_after_return = uav.power - power_to_return
        safe_to_recall = route.reachable and power_after_return > 10.0
        urgent_recall = route.reachable and power_after_return < 5.0
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


# ═══════════════════════════════════════════════════════════════
#  Category 5: Situational Awareness (態勢感知 — 複合查詢)
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def get_situational_awareness(ctx: Context) -> dict:
    """Get complete situational picture in ONE call — fleet status, search coverage, threat hotspots, and endurance assessment. Use this instead of calling query_fleet + get_search_progress + get_threat_map + assess_endurance separately."""
    c = _connector(ctx)
    data = c.world.get_situational_awareness()
    return {"status": "ok", "data": data}


# ─── Entry Point ────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MCP_PORT", "8001"))
    # Use uvicorn directly to avoid anyio subprocess deadlock (GitHub issue #532)
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
