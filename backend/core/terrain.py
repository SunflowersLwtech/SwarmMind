"""Terrain and obstacle management for SwarmMind simulation."""
from __future__ import annotations
import numpy as np
from pydantic import BaseModel


class CellType:
    """Cell state constants."""
    UNEXPLORED = 0
    EXPLORED = 1
    OBSTACLE = 2
    BASE = 3
    NO_FLY = 4


class Terrain:
    """Manages obstacles, no-fly zones, and terrain features on the grid."""

    def __init__(self, size: int, num_obstacles: int = 15, seed: int | None = None):
        self.size = size
        self.rng = np.random.default_rng(seed)

        # Boolean matrix: True = blocked
        self.obstacle_grid = np.zeros((size, size), dtype=bool)

        # Base station at (0, 0) — always clear
        self.base_position = (0, 0)

        self._place_obstacles(num_obstacles)

    def _place_obstacles(self, count: int) -> None:
        """Randomly place obstacles, avoiding base and its neighbours."""
        protected = {(0, 0), (0, 1), (1, 0), (1, 1)}  # keep base area clear
        placed = 0
        while placed < count:
            x = self.rng.integers(0, self.size)
            y = self.rng.integers(0, self.size)
            if (x, y) not in protected and not self.obstacle_grid[x, y]:
                self.obstacle_grid[x, y] = True
                placed += 1

    def is_blocked(self, x: int, y: int) -> bool:
        """Check if a cell is blocked (obstacle or out of bounds)."""
        if not (0 <= x < self.size and 0 <= y < self.size):
            return True
        return bool(self.obstacle_grid[x, y])

    def is_valid(self, x: int, y: int) -> bool:
        """Check if a cell is within bounds and passable."""
        return not self.is_blocked(x, y)

    def get_passable_matrix(self) -> np.ndarray:
        """Return int matrix: 1=passable, 0=blocked. For pathfinding."""
        return (~self.obstacle_grid).astype(int)

    def get_obstacle_positions(self) -> list[tuple[int, int]]:
        """Return list of obstacle coordinates."""
        coords = np.argwhere(self.obstacle_grid)
        return [(int(r), int(c)) for r, c in coords]

    def to_dict(self) -> dict:
        return {
            "size": self.size,
            "obstacles": self.get_obstacle_positions(),
            "base": list(self.base_position),
        }


class TerrainInfo(BaseModel):
    """Pydantic model for terrain serialization."""
    size: int
    obstacles: list[list[int]]
    base: list[int]
