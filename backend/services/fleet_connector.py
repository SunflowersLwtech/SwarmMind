"""FleetConnector — lifespan context for MCP tool server.

Pattern from droneserver: a dataclass that holds the simulation world
instance, initialized during server lifespan and injected into tools via Context.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from backend.core.grid_world import GridWorld


@dataclass
class FleetConnector:
    """Holds the GridWorld instance for MCP tools to access."""
    world: GridWorld
    ready: bool = False
    mission_active: bool = False
    step_count: int = 0
