"""SwarmMind MCP Tool Server — 19 tools for drone fleet command and control.

Run as independent process:
    conda run -n swarmmind python -m backend.services.tool_server

Uses `from fastmcp import FastMCP` (standalone package) so that
`fastmcp.Client` can wrap the server instance in tests.

Transport: Streamable HTTP at /mcp (SSE is deprecated).
"""
from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastmcp import FastMCP, Context

from backend.core.grid_world import GridWorld
from backend.services.fleet_connector import FleetConnector


# ─── Lifespan: initialise GridWorld ─────────────────────────────

@asynccontextmanager
async def fleet_lifespan(server: FastMCP):
    """Create and yield the simulation world for the server's lifetime."""
    world = GridWorld(size=20, num_uavs=5, num_objectives=8, num_obstacles=15)
    connector = FleetConnector(world=world, ready=True)
    print(f"[MCP] Fleet initialised: {len(world.fleet)} UAVs, "
          f"{world.objective_field.total_objectives} objectives, "
          f"grid {world.size}x{world.size}")
    yield {"connector": connector}


mcp = FastMCP(
    "SwarmMind-Fleet",
    lifespan=fleet_lifespan,
)


def _connector(ctx: Context) -> FleetConnector:
    """Extract FleetConnector from context with guard check."""
    connector: FleetConnector = ctx.lifespan_context["connector"]
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
    """Move a UAV to target coordinates using A* pathfinding. Returns the actual path taken, distance, and power cost."""
    c = _connector(ctx)
    uav = c.world.get_uav(uav_id)
    if not uav:
        return {"status": "error", "message": f"UAV '{uav_id}' not found"}
    result = c.world.move_uav(uav_id, x, y)
    return {"status": "ok", "data": result.model_dump()}


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
    """Recall a UAV to base station for charging. Uses A* to find return path."""
    c = _connector(ctx)
    uav = c.world.get_uav(uav_id)
    if not uav:
        return {"status": "error", "message": f"UAV '{uav_id}' not found"}
    result = c.world.recall_uav(uav_id)
    return {"status": "ok", "data": result.model_dump()}


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
        safe_to_recall = route.reachable and route.power_cost < uav.power * 0.8
        endurance.append({
            "uav_id": uav.id,
            "power": round(uav.power, 1),
            "cells_remaining": cells_remaining,
            "distance_to_base": route.distance,
            "power_to_return": route.power_cost,
            "safe_to_recall": safe_to_recall,
            "urgent_recall": route.reachable and route.power_cost > uav.power * 0.6,
        })
    return {"status": "ok", "data": endurance}


# ═══════════════════════════════════════════════════════════════
#  Category 5: Mission Control (任務控制)
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def partition_sectors(num_sectors: int, ctx: Context) -> dict:
    """Divide the grid into N sectors for systematic search coverage. Returns sector boundaries and priorities based on probability."""
    c = _connector(ctx)
    sectors = c.world.partition_sectors(num_sectors)
    return {"status": "ok", "data": {k: v.model_dump() for k, v in sectors.items()}}


@mcp.tool()
async def assign_sector(uav_id: str, sector_id: str, ctx: Context) -> dict:
    """Assign a UAV to a specific search sector."""
    c = _connector(ctx)
    uav = c.world.get_uav(uav_id)
    if not uav:
        return {"status": "error", "message": f"UAV '{uav_id}' not found"}
    if c.world.sectors and sector_id not in c.world.sectors:
        return {"status": "error", "message": f"Sector '{sector_id}' not found"}
    uav.sector_id = sector_id
    uav.log(f"Assigned to sector {sector_id}")
    return {"status": "ok", "message": f"{uav_id} assigned to {sector_id}"}


@mcp.tool()
async def get_op_summary(ctx: Context) -> dict:
    """Get comprehensive mission summary — coverage, objectives, fleet status, elapsed time."""
    c = _connector(ctx)
    progress = c.world.get_search_progress()
    fleet = c.world.get_fleet_status()
    return {
        "status": "ok",
        "data": {
            "tick": c.world.tick,
            "mission_status": c.world.mission_status,
            "coverage": progress.model_dump(),
            "fleet_summary": {
                "total": fleet.total,
                "active": fleet.active,
                "avg_power": fleet.avg_power,
                "low_power_count": fleet.low_power,
            },
            "objectives_found": progress.objectives_found,
            "objectives_total": progress.objectives_total,
            "recent_events": c.world.events[-10:],
        },
    }


# ═══════════════════════════════════════════════════════════════
#  Category 6: Scenario Control (場景控制)
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def init_scenario(grid_size: int, num_uavs: int, num_objectives: int, num_obstacles: int, ctx: Context) -> dict:
    """Reinitialise the simulation with new parameters. Resets all state."""
    c = _connector(ctx)
    c.world = GridWorld(
        size=grid_size,
        num_uavs=num_uavs,
        num_objectives=num_objectives,
        num_obstacles=num_obstacles,
    )
    c.ready = True
    return {
        "status": "ok",
        "message": f"Scenario initialised: {grid_size}x{grid_size} grid, "
                   f"{num_uavs} UAVs, {num_objectives} objectives, {num_obstacles} obstacles",
    }


@mcp.tool()
async def deploy_uav(uav_id: str, ctx: Context) -> dict:
    """Deploy a new UAV to the fleet at the base station."""
    c = _connector(ctx)
    if uav_id in c.world.fleet:
        return {"status": "error", "message": f"UAV '{uav_id}' already exists"}
    uav = c.world.add_uav(uav_id)
    return {"status": "ok", "data": uav.to_dict()}


@mcp.tool()
async def inject_event(event_type: str, params: str, ctx: Context) -> dict:
    """Inject a dynamic event into the simulation. Types: 'failure' (knock out a UAV), 'new_objective' (add a survivor), 'weather' (reduce sensor range).
    params should be a JSON string, e.g. '{"uav_id": "Alpha"}' for failure."""
    import json as json_mod
    c = _connector(ctx)

    try:
        p = json_mod.loads(params) if params else {}
    except json_mod.JSONDecodeError:
        return {"status": "error", "message": "params must be valid JSON string"}

    if event_type == "failure":
        uav_id = p.get("uav_id")
        uav = c.world.get_uav(uav_id)
        if not uav:
            return {"status": "error", "message": f"UAV '{uav_id}' not found"}
        from backend.core.uav import UAVStatus
        uav.status = UAVStatus.OFFLINE
        uav.power = 0
        uav.log("SYSTEM FAILURE — offline")
        c.world._emit(f"{uav_id} went OFFLINE (injected failure)")
        return {"status": "ok", "message": f"{uav_id} is now offline"}

    elif event_type == "new_objective":
        x, y = p.get("x", 10), p.get("y", 10)
        obj_id = f"OBJ-{len(c.world.objective_field.objectives) + 1:03d}"
        from backend.core.objective import Objective
        c.world.objective_field.objectives[obj_id] = Objective(obj_id, x, y)
        c.world.objective_field._boost_probability(x, y, radius=3, amount=0.3)
        c.world._emit(f"New objective {obj_id} at ({x},{y})")
        return {"status": "ok", "message": f"Objective {obj_id} placed at ({x},{y})"}

    elif event_type == "weather":
        reduction = p.get("reduction", 1)
        for uav in c.world.fleet.values():
            uav.sensor_range = max(1, uav.sensor_range - reduction)
        c.world._emit(f"Weather event: sensor range reduced by {reduction}")
        return {"status": "ok", "message": f"All UAV sensor ranges reduced by {reduction}"}

    return {"status": "error", "message": f"Unknown event type: {event_type}"}


# ─── Entry Point ────────────────────────────────────────────────

if __name__ == "__main__":
    print("[MCP] Starting SwarmMind Fleet Tool Server on port 8001...")
    mcp.run(transport="streamable-http")
