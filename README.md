<div align="center">

<img src="assets/hero-banner.svg" alt="SwarmMind — Autonomous Drone Swarm Intelligence" width="100%"/>

<br/>

**When disaster strikes, every second costs lives. SwarmMind exists because we believe autonomous AI coordination can find survivors faster than any human dispatcher — and we built the system to prove it.**

<br/>

[![Google ADK](https://img.shields.io/badge/Google_ADK-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://google.github.io/adk-docs/)
[![Gemini](https://img.shields.io/badge/Gemini_2.5-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![MCP](https://img.shields.io/badge/MCP_Protocol-00D4FF?style=for-the-badge)](https://modelcontextprotocol.io/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)

[![React](https://img.shields.io/badge/React_18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Three.js](https://img.shields.io/badge/React_Three_Fiber-000000?logo=threedotjs&logoColor=white)](https://r3f.docs.pmnd.rs/)
[![Tailwind](https://img.shields.io/badge/Tailwind_CSS-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![zustand](https://img.shields.io/badge/zustand-443E38?logo=npm&logoColor=white)](https://zustand.docs.pmnd.rs/)
[![Python](https://img.shields.io/badge/Python_3.12-3776AB?logo=python&logoColor=white)](https://python.org)
[![NumPy](https://img.shields.io/badge/NumPy-013243?logo=numpy&logoColor=white)](https://numpy.org)
[![SciPy](https://img.shields.io/badge/SciPy-8CAAE6?logo=scipy&logoColor=white)](https://scipy.org)
[![Pydantic](https://img.shields.io/badge/Pydantic_v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev)
[![License MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

[Vision](#the-vision) · [How It Works](#how-it-works) · [Architecture](#system-architecture) · [MCP Integration](#mcp-tool-protocol) · [Agent Pipeline](#ai-command-pipeline) · [Autopilot Algorithm](#autonomous-search-algorithm) · [Probability Heatmap](#gaussian-probability-heatmap) · [3D Command Center](#3d-tactical-command-center) · [Real-Time Streaming](#real-time-websocket-streaming) · [Quick Start](#quick-start)

</div>

---

## The Vision

Every year, natural disasters claim over 60,000 lives. In the critical first 72 hours, search-and-rescue teams face an impossible coordination challenge: too much ground, too few eyes, too little time. Drone swarms can cover vast areas — but coordinating them intelligently requires more than remote control. It requires **autonomous reasoning**.

SwarmMind is an **MCP-driven autonomous drone swarm command system** that uses AI to coordinate fleet-scale search-and-rescue operations. An AI commander — powered by Google ADK and Gemini — observes the battlefield, plans search strategies, dispatches UAVs, and adapts in real time as survivors are found, batteries deplete, and conditions change.

The system communicates through the **Model Context Protocol (MCP)**, meaning the AI agent discovers and invokes drone control tools over a standard wire protocol — the same way a human operator would use a ground control station. This is not a chatbot. This is an **autonomous operations center**.

### What Makes It Different

| Traditional Approach | SwarmMind |
|---------------------|-----------|
| Human manually assigns each drone | AI commander reasons about optimal fleet deployment |
| Fixed search patterns | Probability-guided search with Gaussian diffusion heatmap |
| No obstacle awareness | A* pathfinding with real-time obstacle avoidance |
| Status checked via polling | WebSocket push at 5 Hz with auto-reconnect |
| Text dashboards | 3D tactical map with React Three Fiber |
| Direct function calls | MCP wire protocol (Streamable HTTP) — agent discovers tools at runtime |

---

## How It Works

<div align="center">
<img src="assets/architecture.svg" alt="SwarmMind System Architecture" width="100%"/>
</div>

SwarmMind is a **4-layer system** where each layer communicates through well-defined protocols:

1. **Frontend** (React + R3F + zustand) — 3D tactical map, fleet panel, command console, operations dashboard. Connected via WebSocket for real-time state updates.

2. **API Gateway** (FastAPI) — WebSocket broadcast at 5 Hz, REST endpoints for mission control, CORS-enabled for development.

3. **AI + MCP Layer** — Google ADK agents connect to a separate MCP tool server via Streamable HTTP. The agent discovers 18 tools at runtime and invokes them through the MCP JSON-RPC wire protocol. This is **real MCP integration** — not decorative imports.

4. **Simulation Engine** — A 20x20 grid world with UAV fleet, A* pathfinding, Gaussian probability heatmap, terrain obstacles, and autonomous search behavior.

---

## MCP Tool Protocol

<div align="center">
<img src="assets/mcp-pipeline.svg" alt="MCP-Driven Command Pipeline" width="100%"/>
</div>

SwarmMind implements **18 MCP tools** across 6 categories, served over **Streamable HTTP** transport. The AI agent connects as an MCP client and discovers tools dynamically — no hardcoded drone IDs, no direct imports.

### Why MCP Matters

The MCP wire protocol ensures:
- **Tool discovery at runtime** — the agent calls `list_tools()` and learns what's available
- **Process isolation** — tool server and agent run in separate processes; a crash in one doesn't kill the other
- **Standard protocol** — any MCP-compatible client can connect and control the fleet
- **Dynamic fleet** — UAV IDs are discovered via `query_fleet`, not hardcoded

### 18 Tools in 6 Categories

| Category | Tools | Purpose |
|----------|-------|---------|
| **Fleet Intelligence** | `query_fleet`, `inspect_uav`, `get_threat_map`, `get_search_progress` | Situational awareness — one call gets complete fleet status |
| **Navigation** | `navigate_to`, `plan_route` | A* pathfinding with power cost estimation; plan before committing |
| **Reconnaissance** | `sweep_scan`, `detect_frontier`, `mark_objective` | Thermal scan, probability-guided frontier detection, objective claiming |
| **Resource Management** | `recall_uav`, `repower_uav`, `assess_endurance` | Smart recall when power barely covers return trip |
| **Mission Control** | `partition_sectors`, `assign_sector`, `get_op_summary` | Grid partitioning, UAV assignment, comprehensive mission reporting |
| **Scenario Control** | `init_scenario`, `deploy_uav`, `inject_event` | Dynamic events: UAV failures, new survivors, weather degradation |

Every tool returns `{"status": "ok/error", "data": {...}}` — Pydantic-validated, JSON-serializable.

---

## AI Command Pipeline

The AI commander is a **4-stage sequential pipeline** built with Google ADK's `SequentialAgent`:

```
Assessor ──────> Strategist ──────> Dispatcher ──────> Analyst
  | output:        | output:         | output:          | output:
  | "assessment"   | "strategy"      | "execution_log"  | "report"
  |                |                 |                  |
  | query_fleet    | partition_      | navigate_to      | get_op_
  | get_progress   |   sectors       | sweep_scan       |   summary
  | assess_        | detect_         | recall_uav       |
  |   endurance    |   frontier      | mark_objective   |
  | get_threat_map | plan_route      | assign_sector    |
```

| Stage | Role | Key Decision |
|-------|------|-------------|
| **Assessor** | Gathers intelligence | "Alpha 95%, Bravo 80%, Echo 20% — Echo needs recall" |
| **Strategist** | Plans deployment | "Partition into 4 sectors, assign by proximity and power" |
| **Dispatcher** | Executes actions | "Navigate Alpha to E1, Bravo to E2, recall Echo to base" |
| **Analyst** | Reports results | "Coverage 67%, 3/8 survivors found, recommend expanding search east" |

Each stage passes its output to the next via `output_key`. The Dispatcher is the only stage that *modifies* the simulation — the others reason and plan.

**Model**: Gemini 2.5 Flash (stable for tool-calling loops; flash-lite has a 50% empty response bug).

---

## Autonomous Search Algorithm

<div align="center">
<img src="assets/autopilot-algorithm.svg" alt="Autonomous Search Algorithm" width="100%"/>
</div>

When the mission is running, each UAV operates autonomously with a **one-cell-per-tick** movement model:

### Target Selection Scoring

```
score(cell) = (probability + 0.1) / sqrt(manhattan_distance) - repulsion
```

Where:
- **probability** = Gaussian heatmap value at the cell (higher = more likely survivor)
- **manhattan_distance** = |dx| + |dy| from UAV to cell
- **repulsion** = sum of 1/(distance_to_other_UAV + 1) for all other UAVs — prevents clustering

### Smart Recall

UAVs are recalled when their power barely covers the return trip:

```python
power_needed = (manhattan_distance_to_base + 2) * POWER_PER_CELL
if uav.power <= power_needed:
    recall_to_base()
```

The `+2` margin ensures UAVs don't die en route. Offline UAVs at base are revived by charging.

### Full Lifecycle

```
Deploy > Pick Target > A* Path > Move 1 cell/tick > Scan on Arrival
  ^                                                        |
  |         +-- Objective Found > Claim + Log              |
  |         |                                              |
  +- Charge < Return to Base < Power Low? < Update Heatmap +
```

Performance: **500 ticks on 20x20 grid in 2.2 seconds**, finding 4-6 of 8 objectives with 70%+ coverage.

---

## Gaussian Probability Heatmap

<div align="center">
<img src="assets/probability-heatmap.svg" alt="Gaussian Probability Heatmap" width="100%"/>
</div>

The simulation uses a **Gaussian diffusion probability matrix** to model survivor likelihood:

| Mechanism | Effect |
|-----------|--------|
| **Initial placement** | Objectives placed randomly; probability boosted in a radius-3 circle around each |
| **Gaussian diffusion** | Every tick, `scipy.ndimage.gaussian_filter(sigma=0.5)` blurs the matrix — uncertainty spreads |
| **Scan update** | Scanned cells set to 0 (nothing found) or 1.0 (objective detected) |
| **Obstacle mask** | Obstacle cells always have probability 0 |

This creates a **self-healing search priority map** — if an area hasn't been scanned recently, its probability gradually rises, driving UAVs to re-explore. The top-5 hotspots are always available via `get_threat_map`.

---

## 3D Tactical Command Center

The frontend renders a **military operations center** aesthetic with React Three Fiber:

| Component | Implementation | Performance |
|-----------|---------------|-------------|
| **Terrain** | Ground plane + obstacle boxes with `useMemo`-cached geometry | 1 draw call for ground |
| **Fleet** | Octahedron UAV markers with `lerp` interpolation in `useFrame` | No React re-renders |
| **Coverage** | 400-cell `instancedMesh` updated per frame via color buffer | Single draw call |
| **Objectives** | Pulsing red octahedrons with rescue rings | Conditional render |
| **Post-FX** | Bloom (0.8) + Vignette (0.7) + Noise (0.02) | 3-pass composer |
| **Camera** | `CameraControls` with polar angle limits | Interactive orbit |

### R3F Performance Rules

- **Never** call `setState` in `useFrame` — use `ref.position.lerp()` directly
- **Never** create objects in render loop — use `useMemo` for geometry/material
- **Always** read store via `useMissionStore.getState()` in `useFrame`, not selectors
- UAV labels use drei `Billboard` + `Text` for camera-facing HUD

### Color System

```
Background:  #0B1426 (deep navy)     Status OK:    #06D6A0 (teal)
Panel:       #111B2E (slate)         Warning:      #F4A261 (amber)
Border:      #1E3A5F (steel blue)    Danger:       #E63946 (red)
Accent:      #00D4FF (electric cyan) Charging:     #FFD166 (gold)
Text:        rgba(255,255,255,0.87)  Offline:      #6C757D (gray)
```

---

## Real-Time WebSocket Streaming

<div align="center">
<img src="assets/realtime-streaming.svg" alt="Real-Time WebSocket Streaming" width="100%"/>
</div>

The simulation broadcasts state at **5 Hz** via WebSocket with automatic reconnection:

### Data Flow

```
GridWorld.step()                    useMissionStore
    |                                   |
    v                                   v
ConnectionManager.broadcast()    getState().updateState(payload)
    |                                   |
    +-- {"type": "state_update",       v
    |    "payload": {              useFrame(() => {
    |      "fleet": [...],           ref.position.lerp(...)
    |      "coverage_pct": 67.2,   })
    |      "tick": 142,            // 0 re-renders
    |      "objectives": [...]     // 60fps smooth
    |    }}
    |
    +-- Dead client cleanup
        (per-client try/catch)
```

### Auto-Reconnect

Exponential backoff: `1s, 2s, 4s, 8s, 16s, 30s (max)`, 10 attempts. Connection state shown in the global status bar as LIVE/OFFLINE indicator.

---

## Quick Start

### Prerequisites

- Python 3.12+ (Conda recommended)
- Node.js 20+
- Google API Key ([Get one here](https://aistudio.google.com/apikey))

### 1. Clone and Setup

```bash
git clone https://github.com/your-org/SwarmMind.git
cd SwarmMind

# Python environment
conda create -n swarmmind python=3.12 -y
conda activate swarmmind
pip install google-adk==1.27.1 fastapi==0.135.1 uvicorn==0.42.0 \
  mcp==1.26.0 fastmcp==3.1.1 google-genai==1.67.0 \
  pydantic==2.12.5 numpy==2.4.3 scipy pathfinding==1.0.20 pyyaml

# Frontend
cd frontend && npm install --legacy-peer-deps && cd ..
```

### 2. Configure

```bash
echo "GOOGLE_API_KEY=your_key_here" > .env
```

### 3. Run (3 terminals)

```bash
# Terminal 1: MCP Tool Server
python -m backend.services.tool_server

# Terminal 2: API Gateway
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Terminal 3: Frontend
cd frontend && npm run dev
```

Open **http://localhost:5173** — click START to begin the autonomous search mission.

### 4. Test ADK Agent (optional)

```bash
adk web backend/agents  # Opens ADK Web UI at localhost:8007
```

---

## Project Structure

```
SwarmMind/
  backend/
    config.py                  # Unified configuration from .env
    main.py                    # FastAPI gateway (WebSocket + REST)
    core/                      # Simulation engine
      grid_world.py            # 20x20 GridWorld + autopilot
      uav.py                   # UAV dataclass + Pydantic models
      terrain.py               # Obstacles + passable matrix
      objective.py             # Probability heatmap (scipy Gaussian)
      pathplanner.py           # A* wrapper (python-pathfinding)
    services/                  # MCP tool layer
      tool_server.py           # 18 MCP tools (Streamable HTTP)
      fleet_connector.py       # Lifespan context dataclass
    agents/                    # Google ADK agents
      commander.py             # 4-stage SequentialAgent pipeline
      prompts.yaml             # Externalized agent prompts
    utils/
      blackbox.py              # Structured JSON reasoning logs
  frontend/
    src/
      App.jsx                  # 3-column layout
      stores/missionStore.js   # zustand global state
      hooks/useWebSocket.js    # Auto-reconnect hook
      scene/                   # R3F 3D components (7 files)
      panels/                  # 2D UI panels (5 files)
    package.json               # React 18 + R3F 8 + zustand 4
  test/                        # 118 tests (10 suites)
```

---

## Tech Stack

| Layer | Technology | Role |
|-------|-----------|------|
| **Agent Framework** | Google ADK 1.27 | SequentialAgent pipeline with McpToolset |
| **LLM** | Gemini 2.5 Flash | All agent reasoning and tool selection |
| **Tool Protocol** | MCP (Streamable HTTP) | Wire protocol for agent-to-tool communication |
| **MCP Server** | mcp SDK FastMCP | 18 tools with lifespan context injection |
| **API Gateway** | FastAPI + WebSocket | 5 Hz state broadcast + REST mission control |
| **Simulation** | NumPy + SciPy + pathfinding | Probability heatmap, A* routing, grid world |
| **3D Frontend** | React Three Fiber + drei | Instanced rendering, post-processing, camera controls |
| **State Management** | zustand 4.5 | Transient updates via getState() in useFrame |
| **Styling** | Tailwind CSS 3.4 | Dark military theme with JetBrains Mono |
| **Build** | Vite 5 | Sub-second HMR, optimized production bundle |

---

## Test Coverage

SwarmMind ships with **118 tests** across 10 suites:

| Suite | Tests | Scope |
|-------|:-----:|-------|
| UAV Model | 9 | Dataclass creation, power management, status transitions |
| GridWorld | 29 | Movement, scanning, pathfinding, coverage, sectors, snapshots |
| MCP Tools | 10 | Tool registration, execution, response format validation |
| API Gateway | 10 | REST endpoints, CORS, JSON serialization |
| ADK Agent | 12 | Pipeline structure, model config, McpToolset timeout |
| BlackBox | 8 | Structured logging, timestamps, serialization |
| MCP Wire | 5 | **Streamable HTTP wire protocol** — tools called over HTTP, not imports |
| WebSocket | 4 | Connection, state broadcast, message format, fleet data |
| Fullstack | 17 | Every backend feature has frontend UI and vice versa |
| E2E Playwright | 13 | Browser: canvas, dark theme, controls, real-time data |

```bash
pytest test/ -v --timeout=60
# 118 passed, 0 failed, 0 skipped
```

---

## License

This project is licensed under the [MIT License](LICENSE).

---

<div align="center">

**The future of search-and-rescue is autonomous, intelligent, and protocol-driven.**

<a href="https://google.github.io/adk-docs/"><img src="https://img.shields.io/badge/Google_ADK-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Google ADK"/></a>
<a href="https://ai.google.dev/"><img src="https://img.shields.io/badge/Gemini-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white" alt="Gemini"/></a>
<a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-00D4FF?style=for-the-badge" alt="MCP"/></a>
<a href="https://fastapi.tiangolo.com"><img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/></a>
<a href="https://r3f.docs.pmnd.rs/"><img src="https://img.shields.io/badge/React_Three_Fiber-000000?style=for-the-badge&logo=threedotjs&logoColor=white" alt="R3F"/></a>

</div>
