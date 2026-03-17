"""SwarmMind FastAPI Gateway — WebSocket + REST API.

Responsibilities:
1. WebSocket /ws/live — broadcast simulation state at 5 Hz
2. REST /api/ops/start|pause|stop — mission control
3. REST /api/state — current snapshot
4. REST /api/logs — reasoning logs
5. CORS wide-open (dev mode)
6. Static file serving (frontend build)

Run:
    conda run -n swarmmind uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.core.grid_world import GridWorld
from backend.utils.blackbox import blackbox

logger = logging.getLogger("swarmmind")
logging.basicConfig(level=logging.INFO)


# ─── App ────────────────────────────────────────────────────────

app = FastAPI(title="SwarmMind Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    global simulation_running, simulation_speed, world

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
        world = GridWorld(size=20, num_uavs=5, num_objectives=8, num_obstacles=15)
        blackbox.clear()
    elif cmd_type == "set_speed":
        simulation_speed = cmd.get("payload", {}).get("speed", 1.0)
    else:
        return

    # Broadcast updated state after command
    await manager.broadcast({
        "type": "state_update",
        "payload": world.get_state_snapshot(),
    })


# ─── Background Simulation Loop ────────────────────────────────

async def simulation_loop():
    """Background task: step simulation and broadcast state at ~5 Hz."""
    while True:
        if simulation_running:
            world.step()
            await manager.broadcast({
                "type": "state_update",
                "payload": world.get_state_snapshot(),
            })
        await asyncio.sleep(0.2 / max(simulation_speed, 0.1))


@app.on_event("startup")
async def startup():
    asyncio.create_task(simulation_loop())
    logger.info("SwarmMind Gateway started on port 8000")


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
    global simulation_running, world
    simulation_running = False
    world = GridWorld(size=20, num_uavs=5, num_objectives=8, num_obstacles=15)
    blackbox.clear()
    return {"status": "ok", "message": "Mission reset"}


@app.get("/api/logs")
async def get_logs():
    """Get recent reasoning logs from the blackbox."""
    return {"status": "ok", "data": blackbox.get_recent(50)}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "swarmmind-gateway"}


# ─── Static Frontend Serving ───────────────────────────────────

_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve frontend SPA — all non-API routes go to index.html."""
        file = _frontend_dist / full_path
        if file.exists() and file.is_file():
            return FileResponse(file)
        return FileResponse(_frontend_dist / "index.html")
