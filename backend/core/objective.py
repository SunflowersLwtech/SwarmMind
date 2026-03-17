"""Objective (survivor) management and probability heatmap for SwarmMind."""
from __future__ import annotations
import numpy as np
from pydantic import BaseModel
_gaussian_filter = None

def gaussian_filter(matrix, sigma=0.5):
    """Lazy-loaded scipy gaussian_filter to speed up module import."""
    global _gaussian_filter
    if _gaussian_filter is None:
        from scipy.ndimage import gaussian_filter as _gf
        _gaussian_filter = _gf
    return _gaussian_filter(matrix, sigma=sigma)


class Objective:
    """A search-and-rescue objective (survivor/target)."""

    def __init__(self, obj_id: str, x: int, y: int):
        self.id = obj_id
        self.x = x
        self.y = y
        self.detected = False
        self.claimed_by: str | None = None  # UAV id that claimed this objective

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "detected": self.detected,
            "claimed_by": self.claimed_by,
        }


class ObjectiveField:
    """Manages objectives and the probability heatmap.

    The probability matrix represents the likelihood of finding a survivor
    at each cell. It uses Gaussian diffusion to simulate uncertainty spread
    over time. When a cell is scanned, its probability resets (if nothing found)
    or is confirmed (if objective found).
    """

    def __init__(self, grid_size: int, num_objectives: int, obstacle_mask: np.ndarray, seed: int | None = None):
        self.grid_size = grid_size
        self.rng = np.random.default_rng(seed)

        # Probability matrix: float 0.0-1.0 representing likelihood
        self.prob_matrix = np.full((grid_size, grid_size), 0.5)

        # Zero out obstacle cells
        self.prob_matrix[obstacle_mask] = 0.0

        self.objectives: dict[str, Objective] = {}
        self.obstacle_mask = obstacle_mask

        self._place_objectives(num_objectives)

    def _place_objectives(self, count: int) -> None:
        """Place objectives randomly on non-obstacle, non-base cells."""
        placed = 0
        while placed < count:
            x = self.rng.integers(2, self.grid_size)  # avoid base area (0-1)
            y = self.rng.integers(2, self.grid_size)
            if not self.obstacle_mask[x, y]:
                obj_id = f"OBJ-{placed + 1:03d}"
                self.objectives[obj_id] = Objective(obj_id, int(x), int(y))
                # Increase probability around objective location
                self._boost_probability(int(x), int(y), radius=3, amount=0.3)
                placed += 1

    def _boost_probability(self, cx: int, cy: int, radius: int, amount: float) -> None:
        """Increase probability in a circle around (cx, cy)."""
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.grid_size and 0 <= ny < self.grid_size:
                    dist = (dx**2 + dy**2) ** 0.5
                    if dist <= radius and not self.obstacle_mask[nx, ny]:
                        boost = amount * (1.0 - dist / (radius + 1))
                        self.prob_matrix[nx, ny] = min(1.0, self.prob_matrix[nx, ny] + boost)

    def step(self) -> None:
        """Advance one time step: apply Gaussian diffusion to probability matrix.

        This simulates uncertainty spreading — if we haven't searched an area recently,
        its probability slowly rises back up.
        """
        # Apply gentle Gaussian blur (sigma=0.5) to simulate diffusion
        self.prob_matrix = gaussian_filter(self.prob_matrix, sigma=0.5)

        # Clamp to [0, 1]
        np.clip(self.prob_matrix, 0.0, 1.0, out=self.prob_matrix)

        # Keep obstacles at 0
        self.prob_matrix[self.obstacle_mask] = 0.0

    def update_after_scan(self, cx: int, cy: int, radius: int) -> list[str]:
        """Update probability matrix after a scan at (cx, cy) with given radius.

        - Scanned cells with no objective: probability -> 0
        - If objective found: mark as detected

        Returns list of newly detected objective IDs.
        """
        found: list[str] = []

        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < self.grid_size and 0 <= ny < self.grid_size:
                    dist = (dx**2 + dy**2) ** 0.5
                    if dist <= radius:
                        # Clear probability for scanned area
                        self.prob_matrix[nx, ny] = 0.0

                        # Check for objectives at this cell
                        for obj in self.objectives.values():
                            if obj.x == nx and obj.y == ny and not obj.detected:
                                obj.detected = True
                                found.append(obj.id)
                                # Set high probability at found location
                                self.prob_matrix[nx, ny] = 1.0

        return found

    def claim_objective(self, obj_id: str, uav_id: str) -> bool:
        """Claim an objective for a UAV. Returns False if already claimed."""
        obj = self.objectives.get(obj_id)
        if obj and obj.claimed_by is None:
            obj.claimed_by = uav_id
            return True
        return False

    def get_hotspots(self, top_n: int = 5) -> list[dict]:
        """Return top-N highest probability cells."""
        # Flatten, get top indices
        flat = self.prob_matrix.flatten()
        indices = np.argsort(flat)[::-1][:top_n]

        hotspots = []
        for idx in indices:
            x, y = divmod(int(idx), self.grid_size)
            prob = float(flat[idx])
            if prob > 0.01:
                hotspots.append({"x": x, "y": y, "probability": round(prob, 3)})
        return hotspots

    @property
    def total_detected(self) -> int:
        return sum(1 for o in self.objectives.values() if o.detected)

    @property
    def total_objectives(self) -> int:
        return len(self.objectives)

    def to_dict(self) -> dict:
        return {
            "objectives": [o.to_dict() for o in self.objectives.values()],
            "detected": self.total_detected,
            "total": self.total_objectives,
            "hotspots": self.get_hotspots(),
        }

    def get_heatmap_data(self) -> list[list[float]]:
        """Return probability matrix as nested list for JSON serialization."""
        return self.prob_matrix.round(3).tolist()


# ─── Pydantic Response Models ──────────────────────────────────

class ObjectiveInfo(BaseModel):
    id: str
    x: int
    y: int
    detected: bool
    claimed_by: str | None = None

class ThreatMap(BaseModel):
    heatmap: list[list[float]]
    hotspots: list[dict]

class SearchProgress(BaseModel):
    coverage_pct: float
    explored_cells: int
    total_cells: int
    objectives_found: int
    objectives_total: int
    estimated_remaining: float | None = None

class FrontierCell(BaseModel):
    x: int
    y: int
    priority: float  # higher = more urgent
