"""SwarmMind MCP Tool Server — 8 mission-oriented tools for drone fleet C2.

Refactored from 13 micro-tools to 8 mission-oriented tools:
- Tools operate through Drone objects, not directly on UAV state
- AI assigns missions; Drones execute autonomously
- Read-only tools merged into get_situation_overview()

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
#  Tool 1: Fleet Discovery
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def discover_fleet(ctx: Context) -> dict:
    """Discover all drones in the fleet — returns drone IDs, status, power, position, and current mission. Use this first to learn which drones are available."""
    c = _connector(ctx)
    drones_info = []
    for drone_id, drone in c.world.drones.items():
        report = drone.get_report(c.world)
        drones_info.append(report.model_dump())
    return {
        "status": "ok",
        "data": {
            "drones": drones_info,
            "total": len(drones_info),
            "active": sum(1 for d in c.world.drones.values() if d.uav.is_operational),
        },
    }


# ═══════════════════════════════════════════════════════════════
#  Tool 2: Drone Status
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def get_drone_status(drone_id: str, ctx: Context) -> dict:
    """Get detailed status for a single drone — includes mission progress, ETA, explorable cells, and power analysis."""
    c = _connector(ctx)
    drone = c.world.drones.get(drone_id)
    if not drone:
        return {"status": "error", "message": f"Drone '{drone_id}' not found"}
    report = drone.get_report(c.world)
    return {"status": "ok", "data": report.model_dump()}


# ═══════════════════════════════════════════════════════════════
#  Tool 3: Assign Search Mission
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def assign_search_mission(drone_id: str, x: int, y: int, ctx: Context) -> dict:
    """Assign a search mission to a drone — it will fly to (x, y) via A* pathfinding. Returns accepted/rejected with reason. REJECTS if the drone lacks power for the ROUND TRIP (to target + back to base). Each cell costs 2% power. If rejected, try a CLOSER target."""
    c = _connector(ctx)
    drone = c.world.drones.get(drone_id)
    if not drone:
        return {"status": "error", "message": f"Drone '{drone_id}' not found"}
    from backend.core.uav import Mission, MissionType
    mission = Mission(type=MissionType.SEARCH, target=(x, y), assigned_by="agent")
    report = drone.assign_mission(mission, c.world)
    accepted = "accepted" in report.status
    return {
        "status": "ok" if accepted else "rejected",
        "data": report.model_dump(),
    }


# ═══════════════════════════════════════════════════════════════
#  Tool 4: Assign Scan Mission
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def assign_scan_mission(drone_id: str, ctx: Context) -> dict:
    """Perform thermal scan at the drone's current position. Only effective when the drone is idle at or near a target. Detects objectives within sensor range and updates the probability heatmap."""
    c = _connector(ctx)
    drone = c.world.drones.get(drone_id)
    if not drone:
        return {"status": "error", "message": f"Drone '{drone_id}' not found"}
    uav = drone.uav
    if not uav.is_operational:
        return {"status": "error", "message": f"Drone '{drone_id}' is offline"}
    result = c.world.scan_zone(drone_id)
    # Auto-claim any found objectives
    if result.found_objectives:
        for obj_id in result.found_objectives:
            c.world.objective_field.claim_objective(obj_id, drone_id)
    return {"status": "ok", "data": result.model_dump()}


# ═══════════════════════════════════════════════════════════════
#  Tool 5: Recall Drone
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def recall_drone(drone_id: str, ctx: Context) -> dict:
    """Recall a drone to base for recharging. The drone navigates back via A* pathfinding (1 cell/tick). Do NOT recall drones that are already returning or charging."""
    c = _connector(ctx)
    drone = c.world.drones.get(drone_id)
    if not drone:
        return {"status": "error", "message": f"Drone '{drone_id}' not found"}
    from backend.core.uav import Mission, MissionType
    mission = Mission(type=MissionType.RECALL, assigned_by="agent")
    report = drone.assign_mission(mission, c.world)
    accepted = "accepted" in report.status
    return {
        "status": "ok" if accepted else "rejected",
        "data": report.model_dump(),
    }


# ═══════════════════════════════════════════════════════════════
#  Tool 6: Situation Overview (composite)
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def get_situation_overview(ctx: Context) -> dict:
    """Get complete situational picture in ONE call — fleet status with missions, search coverage, threat hotspots, and endurance assessment. Use this instead of multiple separate queries."""
    c = _connector(ctx)
    data = c.world.get_situational_awareness()
    return {"status": "ok", "data": data}


# ═══════════════════════════════════════════════════════════════
#  Tool 7: Frontier Targets
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def get_frontier_targets(ctx: Context) -> dict:
    """Find unexplored cells adjacent to explored areas, sorted by probability (highest priority first). Use this to decide where to assign search missions next."""
    c = _connector(ctx)
    frontier = c.world.detect_frontier()
    data = [f.model_dump() for f in frontier[:20]]  # top 20
    return {"status": "ok", "data": data, "total_frontier": len(frontier)}


# ═══════════════════════════════════════════════════════════════
#  Tool 8: Route Planning
# ═══════════════════════════════════════════════════════════════

@mcp.tool()
async def plan_route(start_x: int, start_y: int, end_x: int, end_y: int, ctx: Context) -> dict:
    """Plan an A* route WITHOUT executing it. Returns optimal path, distance, and estimated power cost. Use this to evaluate movement options before committing."""
    c = _connector(ctx)
    route = c.world.plan_route(start_x, start_y, end_x, end_y)
    return {"status": "ok", "data": route.model_dump()}


# ─── Entry Point ────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MCP_PORT", "8001"))
    # Use uvicorn directly to avoid anyio subprocess deadlock (GitHub issue #532)
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
