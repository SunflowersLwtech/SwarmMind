# SwarmMind — Autonomous SAR Drone Swarm Command System

SwarmMind is an **MCP-driven autonomous drone swarm command system** for disaster search-and-rescue (SAR) operations. An AI commander (powered by Google ADK + Gemini) coordinates a fleet of UAVs through the Model Context Protocol to systematically search disaster zones, locate survivors, and manage fleet resources.

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│  Frontend (React + R3F + zustand)        localhost:3000    │
│  ├── 3D Tactical Map (React Three Fiber)                   │
│  ├── Fleet Panel / Command Console / Dashboard             │
│  └── WebSocket auto-reconnect                              │
├────────────────────┬───────────────────────────────────────┤
│                    │ WebSocket + REST                       │
│  FastAPI Gateway   │                         localhost:8000 │
│  /ws/live  /api/*  │                                       │
├────────────────────┴──────────┬────────────────────────────┤
│  Google ADK Agents            │  MCP Tool Server           │
│  ┌─ Assessor                  │  19 MCP tools              │
│  ├─ Strategist    ◄── MCP ───┤  Streamable HTTP           │
│  ├─ Dispatcher                │  localhost:8001/mcp        │
│  └─ Analyst                   │                            │
│  Gemini 2.5 Flash             │                            │
├───────────────────────────────┴────────────────────────────┤
│  Simulation Engine                                         │
│  GridWorld 20x20 │ A* Pathfinding │ Probability Heatmap    │
│  UAV Fleet       │ Terrain/Obstacles │ Gaussian Diffusion  │
└────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Agent Framework | Google ADK 1.27 (SequentialAgent pipeline) |
| LLM | Gemini 2.5 Flash |
| Tool Protocol | MCP (Streamable HTTP transport) |
| MCP Server | FastMCP (from `mcp` SDK) — 19 tools |
| API Gateway | FastAPI + WebSocket |
| Simulation | NumPy + SciPy + python-pathfinding (A*) |
| 3D Frontend | React Three Fiber + drei + postprocessing |
| State Mgmt | zustand 4.5 |
| Styling | Tailwind CSS 3.4 |
| Build | Vite 5 |

## Quick Start

### Prerequisites
- Python 3.12+ (Conda recommended)
- Node.js 20+
- Google API Key (Gemini)

### 1. Setup Environment

```bash
# Create conda environment
conda create -n swarmmind python=3.12 -y
conda activate swarmmind

# Install Python dependencies
pip install google-adk==1.27.1 fastapi==0.135.1 uvicorn==0.42.0 \
  mcp==1.26.0 fastmcp==3.1.1 google-genai==1.67.0 \
  pydantic==2.12.5 numpy==2.4.3 scipy pathfinding==1.0.20 pyyaml

# Install frontend dependencies
cd frontend && npm install --legacy-peer-deps && cd ..
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY
```

### 3. Run (3 terminals)

```bash
# Terminal 1: MCP Tool Server
conda activate swarmmind
python -m backend.services.tool_server

# Terminal 2: API Gateway
conda activate swarmmind
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Terminal 3: Frontend
cd frontend && npm run dev
```

Open **http://localhost:3000** in your browser.

### 4. Test ADK Agent (optional)

```bash
# Terminal 4: ADK Web UI
conda activate swarmmind
adk web backend/agents
```

## MCP Tools (19 total)

| Category | Tools |
|----------|-------|
| Fleet Intelligence | `query_fleet`, `inspect_uav`, `get_threat_map`, `get_search_progress` |
| Navigation | `navigate_to`, `plan_route` |
| Reconnaissance | `sweep_scan`, `detect_frontier`, `mark_objective` |
| Resource Mgmt | `recall_uav`, `repower_uav`, `assess_endurance` |
| Mission Control | `partition_sectors`, `assign_sector`, `get_op_summary` |
| Scenario | `init_scenario`, `deploy_uav`, `inject_event` |

## Key Features

- **Real MCP Integration**: Agent communicates with tools via MCP wire protocol (Streamable HTTP), not direct Python imports
- **4-Stage AI Pipeline**: Assess → Strategize → Dispatch → Report (Google ADK SequentialAgent)
- **Probability Heatmap**: Gaussian diffusion models survivor likelihood, guiding search priority
- **A* Pathfinding**: Obstacle-aware route planning with power cost estimation
- **3D Tactical View**: React Three Fiber with Bloom/Vignette post-processing, instanced UAV rendering
- **Real-time WebSocket**: 5 Hz state broadcast with auto-reconnect (exponential backoff)
- **Dynamic Events**: Inject UAV failures, new survivors, or weather degradation mid-mission

