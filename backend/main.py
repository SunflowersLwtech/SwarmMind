"""SwarmMind FastAPI Gateway — WebSocket + REST API.

Responsibilities:
1. WebSocket /ws/live — broadcast simulation state at 5 Hz
2. REST /api/ops/start|pause|stop — mission control
3. REST /api/state — current snapshot
4. REST /api/logs — reasoning logs
5. CORS wide-open (dev mode)
6. Static file serving (frontend build)
7. Agent pipeline integration (Gemini ADK)
8. MCP tool server on port 8001 (same process, shared world)

Run:
    conda run -n swarmmind uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import asyncio
import json
import logging
from dotenv import load_dotenv
load_dotenv()
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.core.grid_world import GridWorld
from backend.utils.blackbox import blackbox
from backend.agents.runner import AgentRunner
from backend.services.tool_server import set_shared_world

logger = logging.getLogger("swarmmind")
logging.basicConfig(level=logging.INFO)


# ─── Simulation State ──────────────────────────────────────────

world = GridWorld(size=20, num_uavs=5, num_objectives=8, num_obstacles=15)
simulation_running = False
simulation_speed = 1.0


# ─── WebSocket Connection Manager ──────────────────────────────

class ConnectionManager:
    """Manages WebSocket clients for real-time broadcast."""

    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, client_id: str, ws: WebSocket):
        await ws.accept()
        self.active[client_id] = ws
        logger.info(f"WS client {client_id} connected ({len(self.active)} total)")

    def disconnect(self, client_id: str):
        self.active.pop(client_id, None)
        logger.info(f"WS client {client_id} disconnected ({len(self.active)} total)")

    async def broadcast(self, message: dict):
        if not self.active:
            return
        dead = []
        for cid, ws in self.active.items():
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.active.pop(cid, None)


manager = ConnectionManager()


# ─── Shared state: inject world into MCP + agent ───────────────

set_shared_world(world)
agent_runner = AgentRunner(world=world, broadcast_fn=manager.broadcast)


# ─── MCP server as background uvicorn (port 8001) ──────────────

async def _start_mcp_server():
    """Run MCP tool server on port 8001 in background (same process, shared world)."""
    import uvicorn
    from backend.services.tool_server import mcp as mcp_server

    config = uvicorn.Config(
        mcp_server.streamable_http_app(),
        host="127.0.0.1",
        port=8001,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    await server.serve()


# ─── Lifespan ──────────────────────────────────────────────────

_mcp_task = None


@asynccontextmanager
async def lifespan(app):
    global _mcp_task
    _mcp_task = asyncio.create_task(_start_mcp_server())
    asyncio.create_task(simulation_loop())
    logger.info("SwarmMind Gateway started on port 8000, MCP on port 8001")
    yield
    if _mcp_task:
        _mcp_task.cancel()


# ─── App ────────────────────────────────────────────────────────

app = FastAPI(title="SwarmMind Gateway", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── WebSocket Endpoint ────────────────────────────────────────

@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    client_id = str(uuid.uuid4())[:8]
    await manager.connect(client_id, ws)

    try:
        # Send initial state
        await ws.send_json({
            "type": "initial_state",
            "payload": world.get_state_snapshot(),
        })

        # Listen for client commands
        while True:
            raw = await ws.receive_text()
            try:
                cmd = json.loads(raw)
                await _handle_ws_command(cmd, client_id)
            except json.JSONDecodeError:
                await manager.broadcast({
                    "type": "error",
                    "payload": {"message": "Invalid JSON"},
                })
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WS error {client_id}: {e}")
        manager.disconnect(client_id)


async def _handle_ws_command(cmd: dict, client_id: str):
    global simulation_running, simulation_speed, world, agent_runner

    cmd_type = cmd.get("type")

    if cmd_type == "start":
        simulation_running = True
        world.mission_status = "running"
    elif cmd_type == "pause":
        simulation_running = False
        world.mission_status = "paused"
    elif cmd_type == "resume":
        simulation_running = True
        world.mission_status = "running"
    elif cmd_type == "stop":
        simulation_running = False
        world.mission_status = "idle"
    elif cmd_type == "reset":
        simulation_running = False
        agent_runner.cancel()
        world = GridWorld(size=20, num_uavs=5, num_objectives=8, num_obstacles=15)
        set_shared_world(world)
        agent_runner = AgentRunner(world=world, broadcast_fn=manager.broadcast)
        blackbox.clear()
    elif cmd_type == "set_speed":
        simulation_speed = max(0.1, min(5.0, float(cmd.get("payload", {}).get("speed", 1.0))))
    elif cmd_type == "add_uav":
        from backend.core.uav import CALLSIGNS
        callsign = cmd.get("payload", {}).get("callsign")
        if not callsign:
            used = set(world.fleet.keys())
            callsign = next((c for c in CALLSIGNS if c not in used), f"UAV-{len(world.fleet)}")
        if callsign not in world.fleet:
            world.add_uav(callsign)
    elif cmd_type == "remove_uav":
        uav_id = cmd.get("payload", {}).get("uav_id")
        if uav_id and uav_id in world.fleet and len(world.fleet) > 1:
            del world.fleet[uav_id]
    elif cmd_type == "reload":
        payload = cmd.get("payload", {})
        size = max(8, min(50, int(payload.get("grid_size", 20))))
        uavs = max(1, min(10, int(payload.get("num_uavs", 5))))
        objs = max(1, min(20, int(payload.get("num_objectives", 8))))
        obs = max(0, min(size * size // 4, int(payload.get("num_obstacles", 15))))
        agent_runner.cancel()
        world = GridWorld(size=size, num_uavs=uavs, num_objectives=objs, num_obstacles=obs)
        set_shared_world(world)
        agent_runner = AgentRunner(world=world, broadcast_fn=manager.broadcast)
        blackbox.clear()
        if payload.get("speed") is not None:
            simulation_speed = max(0.1, min(5.0, float(payload["speed"])))
    else:
        return

    # Broadcast updated state after command
    await manager.broadcast({
        "type": "state_update",
        "payload": world.get_state_snapshot(),
    })


# ─── Background Simulation Loop ────────────────────────────────

AGENT_INTERVAL = 50  # ~10 seconds at 5Hz (reduced from 25 to avoid Gemini 429)


async def simulation_loop():
    """Background task: step simulation and broadcast state at ~5 Hz."""
    while True:
        if simulation_running:
            world.step()
            await manager.broadcast({
                "type": "state_update",
                "payload": world.get_state_snapshot(),
            })
            # Agent dispatch with atomic start guard
            if world.tick % AGENT_INTERVAL == 0 and agent_runner.try_start():
                asyncio.create_task(agent_runner.run_cycle())
        await asyncio.sleep(0.2 / max(simulation_speed, 0.1))


# ─── REST API ───────────────────────────────────────────────────

@app.get("/api/state")
async def get_state():
    """Get current simulation state snapshot."""
    return {"status": "ok", "data": world.get_state_snapshot()}


@app.post("/api/ops/start")
async def ops_start():
    global simulation_running
    simulation_running = True
    world.mission_status = "running"
    return {"status": "ok", "message": "Mission started"}


@app.post("/api/ops/pause")
async def ops_pause():
    global simulation_running
    simulation_running = False
    world.mission_status = "paused"
    return {"status": "ok", "message": "Mission paused"}


@app.post("/api/ops/stop")
async def ops_stop():
    global simulation_running
    simulation_running = False
    world.mission_status = "idle"
    return {"status": "ok", "message": "Mission stopped"}


@app.post("/api/ops/reset")
async def ops_reset():
    global simulation_running, world, agent_runner
    simulation_running = False
    agent_runner.cancel()
    world = GridWorld(size=20, num_uavs=5, num_objectives=8, num_obstacles=15)
    set_shared_world(world)
    agent_runner = AgentRunner(world=world, broadcast_fn=manager.broadcast)
    blackbox.clear()
    return {"status": "ok", "message": "Mission reset"}


@app.get("/api/logs")
async def get_logs():
    """Get recent reasoning logs from the blackbox."""
    return {"status": "ok", "data": blackbox.get_recent(50)}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "swarmmind-gateway"}


# ─── Fleet Management API ──────────────────────────────────────

@app.post("/api/fleet/add")
async def fleet_add(body: dict = {}):
    """Add a UAV to the fleet. Optional body: {\"callsign\": \"Foxtrot\"}."""
    global world
    callsign = body.get("callsign")
    if not callsign:
        from backend.core.uav import CALLSIGNS
        used = set(world.fleet.keys())
        callsign = next((c for c in CALLSIGNS if c not in used), f"UAV-{len(world.fleet)}")
    if callsign in world.fleet:
        return {"status": "error", "message": f"'{callsign}' already exists"}
    world.add_uav(callsign)
    return {"status": "ok", "uav_id": callsign, "fleet_size": len(world.fleet)}


@app.post("/api/fleet/remove")
async def fleet_remove(body: dict = {}):
    """Remove a UAV from the fleet. Body: {\"uav_id\": \"Echo\"}."""
    global world
    uav_id = body.get("uav_id")
    if not uav_id or uav_id not in world.fleet:
        return {"status": "error", "message": f"'{uav_id}' not found"}
    if len(world.fleet) <= 1:
        return {"status": "error", "message": "Cannot remove last UAV"}
    del world.fleet[uav_id]
    return {"status": "ok", "removed": uav_id, "fleet_size": len(world.fleet)}


# ─── Simulation Config API ────────────────────────────────────

@app.get("/api/config")
async def get_config():
    """Get current simulation configuration."""
    return {
        "status": "ok",
        "data": {
            "grid_size": world.size,
            "num_uavs": len(world.fleet),
            "num_objectives": len(world.objective_field.objectives),
            "num_obstacles": int(world.terrain.obstacle_grid.sum()),
            "speed": simulation_speed,
            "agent_interval": AGENT_INTERVAL,
        },
    }


@app.post("/api/config/reload")
async def config_reload(body: dict = {}):
    """Rebuild world with new parameters. Body: {grid_size, num_uavs, num_objectives, num_obstacles, speed}."""
    global simulation_running, simulation_speed, world, agent_runner
    simulation_running = False
    agent_runner.cancel()

    size = body.get("grid_size", 20)
    uavs = body.get("num_uavs", 5)
    objs = body.get("num_objectives", 8)
    obs = body.get("num_obstacles", 15)
    # Clamp values to safe ranges
    size = max(8, min(50, int(size)))
    uavs = max(1, min(10, int(uavs)))
    objs = max(1, min(20, int(objs)))
    obs = max(0, min(size * size // 4, int(obs)))

    world = GridWorld(size=size, num_uavs=uavs, num_objectives=objs, num_obstacles=obs)
    set_shared_world(world)
    agent_runner = AgentRunner(world=world, broadcast_fn=manager.broadcast)
    blackbox.clear()

    if body.get("speed") is not None:
        simulation_speed = max(0.1, min(5.0, float(body["speed"])))

    return {
        "status": "ok",
        "message": f"World rebuilt: {size}x{size}, {uavs} UAVs, {objs} objectives, {obs} obstacles",
    }


@app.post("/api/config/speed")
async def set_speed(body: dict = {}):
    """Set simulation speed. Body: {\"speed\": 2.0}."""
    global simulation_speed
    spd = body.get("speed", 1.0)
    simulation_speed = max(0.1, min(5.0, float(spd)))
    return {"status": "ok", "speed": simulation_speed}


# ─── Static Frontend Serving ───────────────────────────────────

_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve frontend SPA — non-API/WS routes go to index.html."""
        from fastapi.responses import JSONResponse
        if full_path.startswith(("api/", "ws/")):
            return JSONResponse({"error": "Not found"}, status_code=404)
        file = _frontend_dist / full_path
        if file.exists() and file.is_file():
            return FileResponse(file)
        return FileResponse(_frontend_dist / "index.html")
