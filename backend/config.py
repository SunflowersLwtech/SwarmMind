"""SwarmMind unified configuration."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


class Config:
    """Central configuration loaded from .env."""
    # API Keys
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

    # Model IDs
    AGENT_MODEL: str = "gemini-2.5-flash"  # Stable for agent loops (NOT flash-lite due to 50% empty response bug)
    LITE_MODEL: str = os.getenv("GEMINI_LITE_MODEL", "gemini-3.1-flash-lite-preview")

    # MCP Server
    MCP_HOST: str = "127.0.0.1"
    MCP_PORT: int = 8001
    MCP_TRANSPORT: str = "streamable-http"
    MCP_URL: str = f"http://{MCP_HOST}:{MCP_PORT}/mcp"
    MCP_TIMEOUT: float = 30.0  # Default 5s is too short (ADK issue #1086)

    # FastAPI Gateway
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Simulation defaults
    GRID_SIZE: int = 20
    NUM_UAVS: int = 5
    NUM_OBJECTIVES: int = 8
    NUM_OBSTACLES: int = 15

    # WebSocket
    WS_BROADCAST_INTERVAL: float = 0.2  # 5 updates/sec

    # Power consumption
    POWER_MOVE_PER_CELL: float = 2.0
    POWER_SCAN: float = 1.0
    POWER_CHARGE_PER_STEP: float = 20.0
    POWER_LOW_THRESHOLD: float = 20.0


cfg = Config()
