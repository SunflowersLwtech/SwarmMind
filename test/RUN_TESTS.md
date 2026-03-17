# SwarmMind Test Suite

> ⚠️ DO NOT READ DURING DEVELOPMENT. Run only after implementation is complete.

## Test Execution Order

### Step 1: Backend Unit Tests (no servers needed)
```bash
cd /Users/sunfl/Documents/study/VHACK/project/SwarmMind
conda activate swarmmind
pytest test/backend/ -v --timeout=30
```
Expected: All 40+ tests pass.

### Step 2: MCP Wire Protocol Tests (needs MCP server)
```bash
# Terminal 1: Start MCP Server on test port
MCP_PORT=8901 conda run -n swarmmind python -m backend.services.tool_server

# Terminal 2: Run integration tests
conda activate swarmmind
pytest test/integration/test_07_mcp_wire.py -v --timeout=30
```
Expected: All MCP wire protocol tests pass.

### Step 3: WebSocket Tests (needs FastAPI server)
```bash
# Install extra test dep
conda run -n swarmmind pip install httpx-ws

# Run (uses in-process ASGI transport, no server needed)
conda activate swarmmind
pytest test/integration/test_08_websocket.py -v --timeout=30
```

### Step 4: Full-Stack Consistency Tests
```bash
pytest test/integration/test_09_fullstack_consistency.py -v
```
Expected: Every backend feature has frontend UI and vice versa.

### Step 5: E2E Playwright Tests (needs all servers + frontend)
```bash
# Install playwright
conda run -n swarmmind pip install playwright
conda run -n swarmmind playwright install chromium

# Terminal 1: MCP Server
conda run -n swarmmind python -m backend.services.tool_server

# Terminal 2: FastAPI
conda run -n swarmmind python -m backend.main

# Terminal 3: Frontend
cd frontend && npm run dev

# Terminal 4: Run E2E
conda activate swarmmind
pytest test/e2e/ -v --timeout=60
```
Expected: All browser tests pass.

### Full Suite (after all servers running)
```bash
pytest test/ -v --timeout=60
```

## Test Coverage Summary

| Suite | File | Tests | What It Verifies |
|-------|------|:-----:|-----------------|
| 01 | test_01_uav.py | ~10 | UAV model, power, status |
| 02 | test_02_grid_world.py | ~25 | Grid, movement, scan, coverage, pathfinding, sectors |
| 03 | test_03_mcp_tools.py | ~15 | MCP tool registration, execution, response format |
| 04 | test_04_api_gateway.py | ~10 | REST endpoints, CORS, JSON format |
| 05 | test_05_agent.py | ~12 | ADK agent structure, model config, pipeline stages |
| 06 | test_06_blackbox.py | ~8 | Logging, timestamps, serialization |
| 07 | test_07_mcp_wire.py | ~5 | MCP over Streamable HTTP (CS3 compliance!) |
| 08 | test_08_websocket.py | ~5 | WebSocket streaming, message format |
| 09 | test_09_fullstack_consistency.py | ~15 | Backend↔Frontend feature parity |
| 10 | test_10_playwright.py | ~12 | Browser UI, 3D canvas, dark theme, controls |
| **Total** | | **~117** | |

## Acceptance Criteria
ALL tests must pass. No skips (except Playwright if servers not running).
Debug and iterate until 100% green.
