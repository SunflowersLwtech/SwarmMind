"""A* pathfinding wrapper using python-pathfinding library.

Coordinate convention
---------------------
SwarmMind uses **(row, col)** throughout: ``pos = (row, col)`` where
``row`` is the vertical axis and ``col`` is the horizontal axis.
``obstacle_matrix[row][col]`` follows the same layout.

The ``python-pathfinding`` library uses the **opposite** convention:
``Grid.node(x=col, y=row)``, and path nodes store ``(x=col, y=row)``.

All conversion is encapsulated inside ``find_path`` — callers always
pass and receive ``(row, col)`` tuples.
"""
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
    """A* pathfinding on the simulation grid.

    All public methods accept and return **(row, col)** coordinates.
    The library-specific ``(col, row)`` swap is handled internally.
    """

    def __init__(self, obstacle_matrix: np.ndarray, power_per_cell: float = 2.0):
        self.obstacle_matrix = obstacle_matrix
        self.power_per_cell = power_per_cell
        self.finder = AStarFinder()

    def find_path(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> list[tuple[int, int]]:
        """Find shortest path. Input/output are **(row, col)** tuples.

        Returns an empty list if no path exists.
        """
        # Cache passable matrix (numpy→list is expensive)
        if not hasattr(self, '_passable_list'):
            self._passable_list = (~self.obstacle_matrix).astype(int).tolist()
        grid = Grid(matrix=self._passable_list)

        # Library convention: node(x=col, y=row)  ←→  our (row, col)
        start_node = grid.node(start[1], start[0])
        end_node = grid.node(end[1], end[0])

        path, _ = self.finder.find_path(start_node, end_node, grid)

        # Convert back: node.(x=col, y=row) → our (row, col)
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
