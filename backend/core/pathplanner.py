"""A* pathfinding wrapper using python-pathfinding library."""
from __future__ import annotations
import numpy as np
from pathfinding.core.grid import Grid
from pathfinding.finder.a_star import AStarFinder
from pydantic import BaseModel


class Route(BaseModel):
    """Planned route result."""
    path: list[list[int]]
    distance: int
    power_cost: float  # estimated power usage (distance * cost_per_cell)
    reachable: bool
    status: str = "ok"


class PathPlanner:
    """A* pathfinding on the simulation grid."""

    def __init__(self, obstacle_matrix: np.ndarray, power_per_cell: float = 2.0):
        self.obstacle_matrix = obstacle_matrix
        self.power_per_cell = power_per_cell
        self.finder = AStarFinder()

    def find_path(self, start: tuple[int, int], end: tuple[int, int]) -> list[tuple[int, int]]:
        """Find shortest path from start to end. Returns list of (x, y) tuples.

        Note: pathfinding library uses (col, row) = (x, y) convention.
        Our grid: obstacle_matrix[row][col] where row=x, col=y.
        The library Grid expects matrix[row][col] with 1=walkable, 0=blocked.
        Grid.node(x, y) where x=col, y=row.
        """
        # Cache the passable list to avoid repeated numpy→list conversion
        if not hasattr(self, '_passable_list'):
            self._passable_list = (~self.obstacle_matrix).astype(int).tolist()
        grid = Grid(matrix=self._passable_list)

        # pathfinding lib: node(x=col, y=row)
        start_node = grid.node(start[1], start[0])
        end_node = grid.node(end[1], end[0])

        path, _ = self.finder.find_path(start_node, end_node, grid)

        # Convert back: path nodes have (x=col, y=row) -> we want (row, col) = (x, y)
        return [(p.y, p.x) for p in path]

    def plan_route(self, start: tuple[int, int], end: tuple[int, int]) -> Route:
        """Plan a route and return full route info without executing."""
        path = self.find_path(start, end)
        if not path:
            return Route(path=[], distance=0, power_cost=0.0, reachable=False, status="error")

        distance = len(path) - 1  # path includes start
        return Route(
            path=[[p[0], p[1]] for p in path],
            distance=distance,
            power_cost=distance * self.power_per_cell,
            reachable=True,
        )
