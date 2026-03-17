"""GridWorld — 20x20 simulation engine for SwarmMind drone swarm SAR operations."""
from __future__ import annotations

import numpy as np
from pydantic import BaseModel

from .uav import (
    UAV, UAVStatus, CALLSIGNS,
    UAVSummary, UAVDetail, FleetStatus,
    MoveResult, ScanResult, RecallResult, RepowerResult,
)
from .terrain import Terrain
from .objective import ObjectiveField, SearchProgress, ThreatMap, FrontierCell
from .pathplanner import PathPlanner, Route


# ─── Response Models ────────────────────────────────────────────

class StepResult(BaseModel):
    tick: int
    events: list[str]

class Sector(BaseModel):
    id: str
    x_min: int
    x_max: int
    y_min: int
    y_max: int
    priority: float
    area: int = 0

class StateSnapshot(BaseModel):
    """Full serializable state for frontend consumption."""
    tick: int
    grid_size: int
    fleet: list[dict]
    objectives: list[dict]
    coverage_pct: float
    coverage: float = 0.0  # alias for coverage_pct
    explored: list[list[int]]
    obstacles: list[list[int]]
    heatmap: list[list[float]]
    hotspots: list[dict]
    base: list[int]
    mission_status: str
    objectives_found: int
    objectives_total: int
    events: list[str]
    sectors: dict[str, dict] | None = None


class GridWorld:
    """Core simulation engine: 20x20 grid with UAVs, objectives, terrain, and pathfinding."""

    def __init__(
        self,
        size: int = 20,
        num_uavs: int = 5,
        num_objectives: int = 8,
        num_obstacles: int = 15,
        seed: int | None = None,
    ):
        self.size = size
        self.tick = 0
        self.mission_status = "idle"  # idle | running | paused | completed
        self.events: list[str] = []
        self.rng = np.random.default_rng(seed)

        # Exploration tracking: 0=unexplored, 1=explored
        self.explored_grid = np.zeros((size, size), dtype=int)
        self.explored_grid[0, 0] = 1  # base is explored

        # Terrain (obstacles)
        self.terrain = Terrain(size, num_obstacles, seed=seed)

        # Objectives + probability heatmap
        self.objective_field = ObjectiveField(
            size, num_objectives, self.terrain.obstacle_grid, seed=seed
        )

        # Pathfinding
        self.path_planner = PathPlanner(self.terrain.obstacle_grid)

        # Fleet
        self.fleet: dict[str, UAV] = {}
        for i in range(num_uavs):
            callsign = CALLSIGNS[i] if i < len(CALLSIGNS) else f"UAV-{i}"
            self.add_uav(callsign)

        # Sectors (set after partition_sectors is called)
        self.sectors: dict[str, Sector] | None = None

    # ─── Fleet Management ───────────────────────────────────────

    def add_uav(self, uav_id: str) -> UAV:
        """Add a UAV at the base station."""
        uav = UAV(id=uav_id, x=0, y=0)
        uav.log(f"Deployed at base (0,0)")
        self.fleet[uav_id] = uav
        return uav

    def get_uav(self, uav_id: str) -> UAV | None:
        return self.fleet.get(uav_id)

    # ─── Movement ───────────────────────────────────────────────

    def move_uav(self, uav_id: str, target_x: int, target_y: int) -> MoveResult:
        """Move UAV to target using A* pathfinding. Moves one cell per call."""
        uav = self.fleet[uav_id]

        if not uav.is_operational:
            return MoveResult(
                uav_id=uav_id, path=[], distance=0,
                power_cost=0, new_position=[uav.x, uav.y], new_power=uav.power,
            )

        if self.terrain.is_blocked(target_x, target_y):
            uav.log(f"Target ({target_x},{target_y}) is blocked")
            return MoveResult(
                uav_id=uav_id, path=[], distance=0,
                power_cost=0, new_position=[uav.x, uav.y], new_power=uav.power,
                status="error",
            )

        path = self.path_planner.find_path((uav.x, uav.y), (target_x, target_y))
        if not path or len(path) < 2:
            uav.log(f"No path to ({target_x},{target_y})")
            return MoveResult(
                uav_id=uav_id, path=[], distance=0,
                power_cost=0, new_position=[uav.x, uav.y], new_power=uav.power,
            )

        # Calculate total cost
        distance = len(path) - 1
        total_cost = distance * uav.POWER_MOVE

        if uav.power < total_cost:
            # Move as far as possible
            max_steps = int(uav.power // uav.POWER_MOVE)
            if max_steps == 0:
                uav.log("Insufficient power to move")
                return MoveResult(
                    uav_id=uav_id, path=[], distance=0,
                    power_cost=0, new_position=[uav.x, uav.y], new_power=uav.power,
                )
            path = path[: max_steps + 1]
            distance = len(path) - 1
            total_cost = distance * uav.POWER_MOVE

        # Execute movement along the entire path
        uav.status = UAVStatus.MOVING
        for cell in path[1:]:
            uav.x, uav.y = cell
            uav.consume_power(uav.POWER_MOVE)
            self.explored_grid[cell[0], cell[1]] = 1

        # Update heading based on last segment
        if len(path) >= 2:
            dx = path[-1][0] - path[-2][0]
            dy = path[-1][1] - path[-2][1]
            if dx != 0 or dy != 0:
                uav.heading = float(np.degrees(np.arctan2(dy, dx)) % 360)

        uav.status = UAVStatus.IDLE
        uav.log(f"Moved to ({uav.x},{uav.y}), power={uav.power:.1f}%")

        self._emit(f"{uav_id} moved to ({uav.x},{uav.y})")

        return MoveResult(
            uav_id=uav_id,
            path=[[p[0], p[1]] for p in path],
            distance=distance,
            power_cost=total_cost,
            new_position=[uav.x, uav.y],
            new_power=uav.power,
        )

    # ─── Scanning ───────────────────────────────────────────────

    def scan_zone(self, uav_id: str) -> ScanResult:
        """Perform thermal scan around UAV position."""
        uav = self.fleet[uav_id]

        if not uav.is_operational:
            return ScanResult(
                uav_id=uav_id, scanned_cells=[], found_objectives=[],
                coverage_delta=0, power_after=uav.power,
            )

        uav.status = UAVStatus.SCANNING
        uav.consume_power(uav.POWER_SCAN)

        radius = uav.sensor_range
        scanned: list[list[int]] = []
        old_explored = int(self.explored_grid.sum())

        # Mark cells as explored
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                nx, ny = uav.x + dx, uav.y + dy
                if 0 <= nx < self.size and 0 <= ny < self.size:
                    dist = (dx**2 + dy**2) ** 0.5
                    if dist <= radius and not self.terrain.obstacle_grid[nx, ny]:
                        self.explored_grid[nx, ny] = 1
                        scanned.append([nx, ny])

        # Update probability matrix and detect objectives
        found = self.objective_field.update_after_scan(uav.x, uav.y, radius)

        new_explored = int(self.explored_grid.sum())
        total_passable = int((~self.terrain.obstacle_grid).sum())
        coverage_delta = (new_explored - old_explored) / total_passable * 100

        uav.status = UAVStatus.IDLE

        for obj_id in found:
            uav.log(f"DETECTED objective {obj_id}!")
            self._emit(f"{uav_id} detected {obj_id} at ({uav.x},{uav.y})")

        uav.log(f"Scanned {len(scanned)} cells, found {len(found)} objectives")

        return ScanResult(
            uav_id=uav_id,
            scanned_cells=scanned,
            found_objectives=found,
            coverage_delta=round(coverage_delta, 2),
            power_after=uav.power,
        )

    # ─── Fleet Status ───────────────────────────────────────────

    def get_fleet_status(self) -> FleetStatus:
        """Return complete fleet status."""
        uavs = []
        for u in self.fleet.values():
            uavs.append(UAVSummary(
                id=u.id, x=u.x, y=u.y,
                power=round(u.power, 1),
                status=u.status.value,
                heading=u.heading,
                sector_id=u.sector_id,
                is_low_power=u.is_low_power,
            ))

        active = sum(1 for u in self.fleet.values() if u.is_operational)
        idle = sum(1 for u in self.fleet.values() if u.status == UAVStatus.IDLE)
        low = sum(1 for u in self.fleet.values() if u.is_low_power)
        powers = [u.power for u in self.fleet.values()]

        return FleetStatus(
            uavs=uavs,
            total=len(self.fleet),
            active=active,
            idle=idle,
            low_power=low,
            avg_power=round(sum(powers) / len(powers), 1) if powers else 0,
        )

    def get_uav_detail(self, uav_id: str) -> UAVDetail | None:
        """Return detailed info for a single UAV."""
        uav = self.fleet.get(uav_id)
        if not uav:
            return None
        return UAVDetail(
            id=uav.id, x=uav.x, y=uav.y,
            power=round(uav.power, 1),
            status=uav.status.value,
            heading=uav.heading,
            sensor_range=uav.sensor_range,
            comms_range=uav.comms_range,
            sector_id=uav.sector_id,
            is_low_power=uav.is_low_power,
            mission_log=uav.mission_log[-20:],  # last 20 entries
        )

    # ─── Recall & Repower ──────────────────────────────────────

    def recall_uav(self, uav_id: str) -> RecallResult:
        """Recall UAV to base for charging."""
        uav = self.fleet[uav_id]
        base = self.terrain.base_position

        path = self.path_planner.find_path((uav.x, uav.y), base)
        if not path:
            return RecallResult(
                uav_id=uav_id, return_path=[], eta=0,
                power_on_arrival=uav.power,
            )

        distance = len(path) - 1
        power_cost = distance * uav.POWER_MOVE

        # Actually move the UAV back to base
        uav.status = UAVStatus.RETURNING
        for cell in path[1:]:
            uav.x, uav.y = cell
            uav.consume_power(uav.POWER_MOVE)
            self.explored_grid[cell[0], cell[1]] = 1

        uav.status = UAVStatus.CHARGING
        uav.log(f"Recalled to base, power={uav.power:.1f}%")
        self._emit(f"{uav_id} recalled to base")

        return RecallResult(
            uav_id=uav_id,
            return_path=[[p[0], p[1]] for p in path],
            eta=distance,
            power_on_arrival=round(uav.power, 1),
        )

    def repower_uav(self, uav_id: str) -> RepowerResult:
        """Charge a UAV at base (one step)."""
        uav = self.fleet[uav_id]
        old_power = uav.power

        if uav.x != 0 or uav.y != 0:
            uav.log("Cannot charge: not at base")
            return RepowerResult(
                uav_id=uav_id, old_power=old_power,
                new_power=uav.power, fully_charged=False,
            )

        uav.status = UAVStatus.CHARGING
        new_power = uav.charge()
        fully_charged = new_power >= 100.0

        if fully_charged:
            uav.log("Fully charged!")
            self._emit(f"{uav_id} fully charged")

        return RepowerResult(
            uav_id=uav_id,
            old_power=round(old_power, 1),
            new_power=round(new_power, 1),
            fully_charged=fully_charged,
        )

    # ─── Search Progress ────────────────────────────────────────

    def get_search_progress(self) -> SearchProgress:
        """Return current search coverage statistics."""
        total_passable = int((~self.terrain.obstacle_grid).sum())
        explored = int(self.explored_grid.sum())
        pct = (explored / total_passable * 100) if total_passable > 0 else 0

        return SearchProgress(
            coverage_pct=round(pct, 1),
            explored_cells=explored,
            total_cells=total_passable,
            objectives_found=self.objective_field.total_detected,
            objectives_total=self.objective_field.total_objectives,
        )

    # ─── Threat Map ─────────────────────────────────────────────

    def get_threat_map(self) -> ThreatMap:
        """Return probability heatmap data."""
        return ThreatMap(
            heatmap=self.objective_field.get_heatmap_data(),
            hotspots=self.objective_field.get_hotspots(),
        )

    # ─── Frontier Detection ─────────────────────────────────────

    def detect_frontier(self) -> list[FrontierCell]:
        """Find unexplored cells adjacent to explored ones, sorted by probability."""
        frontier: list[FrontierCell] = []

        for x in range(self.size):
            for y in range(self.size):
                if self.explored_grid[x, y] == 0 and not self.terrain.obstacle_grid[x, y]:
                    # Check if adjacent to an explored cell
                    is_frontier = False
                    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < self.size and 0 <= ny < self.size:
                            if self.explored_grid[nx, ny] == 1:
                                is_frontier = True
                                break

                    if is_frontier:
                        priority = float(self.objective_field.prob_matrix[x, y])
                        frontier.append(FrontierCell(x=x, y=y, priority=round(priority, 3)))

        # Sort by priority descending
        frontier.sort(key=lambda f: f.priority, reverse=True)
        return frontier

    # ─── Sector Partitioning ────────────────────────────────────

    def partition_sectors(self, n: int = 4) -> dict[str, Sector]:
        """Partition the grid into n roughly equal sectors."""
        # Simple grid-based partition (2x2 or other)
        cols = int(np.ceil(np.sqrt(n)))
        rows = int(np.ceil(n / cols))
        cell_w = self.size // cols
        cell_h = self.size // rows

        sectors: dict[str, Sector] = {}
        sector_names = ["North-West", "North-East", "South-West", "South-East",
                        "Center", "East", "West", "North"]
        idx = 0
        for r in range(rows):
            for c in range(cols):
                if idx >= n:
                    break
                x_min = r * cell_h
                x_max = min((r + 1) * cell_h - 1, self.size - 1)
                y_min = c * cell_w
                y_max = min((c + 1) * cell_w - 1, self.size - 1)

                name = sector_names[idx] if idx < len(sector_names) else f"Sector-{idx}"
                sid = f"S-{idx + 1}"

                # Priority based on avg probability in sector
                sector_prob = self.objective_field.prob_matrix[x_min:x_max+1, y_min:y_max+1]
                priority = float(np.mean(sector_prob))

                area = (x_max - x_min + 1) * (y_max - y_min + 1)
                sectors[sid] = Sector(
                    id=sid, x_min=x_min, x_max=x_max,
                    y_min=y_min, y_max=y_max, priority=round(priority, 3),
                    area=area,
                )
                idx += 1

        self.sectors = sectors
        return sectors

    # ─── Route Planning ─────────────────────────────────────────

    def plan_route(self, start_x_or_tuple, start_y_or_end=None, end_x=None, end_y=None) -> Route:
        """Plan a route without executing it. Accepts either 4 ints or 2 tuples."""
        if isinstance(start_x_or_tuple, (tuple, list)):
            start = tuple(start_x_or_tuple)
            end = tuple(start_y_or_end)
        else:
            start = (start_x_or_tuple, start_y_or_end)
            end = (end_x, end_y)
        # Gracefully handle out-of-bounds coordinates
        if (not (0 <= start[0] < self.size and 0 <= start[1] < self.size) or
                not (0 <= end[0] < self.size and 0 <= end[1] < self.size)):
            return Route(path=[], distance=0, power_cost=0.0, reachable=False, status="error")
        return self.path_planner.plan_route(start, end)

    # ─── Simulation Step ────────────────────────────────────────

    def step(self) -> StepResult:
        """Advance simulation by one tick with autonomous UAV behaviour."""
        self.tick += 1
        events: list[str] = []

        # Diffuse probability matrix
        self.objective_field.step()

        # ── Autopilot: drive each UAV one cell per tick ──
        if self.mission_status == "running":
            events.extend(self._autopilot_tick())

        # Charge UAVs at base
        for uav in self.fleet.values():
            if uav.status == UAVStatus.CHARGING and uav.x == 0 and uav.y == 0:
                old = uav.power
                uav.charge()
                if uav.power >= 100.0 and old < 100.0:
                    uav.status = UAVStatus.IDLE
                    events.append(f"{uav.id} fully charged")

        # Check completion
        progress = self.get_search_progress()
        if progress.objectives_found >= progress.objectives_total:
            self.mission_status = "completed"
            events.append("ALL OBJECTIVES FOUND — Mission Complete!")

        self.events.extend(events)
        return StepResult(tick=self.tick, events=events)

    # ─── Autopilot Logic ────────────────────────────────────────

    def _autopilot_tick(self) -> list[str]:
        """One tick of autonomous search behaviour for all UAVs."""
        events: list[str] = []
        base = self.terrain.base_position

        for uav in self.fleet.values():
            if not uav.is_operational:
                continue

            # ── Low power → recall to base ──
            if uav.is_low_power and (uav.x, uav.y) != base:
                if uav.status != UAVStatus.RETURNING:
                    path = self.path_planner.find_path((uav.x, uav.y), base)
                    uav.path = path[1:] if path else []
                    uav.status = UAVStatus.RETURNING
                    events.append(f"{uav.id} low power → returning to base")

            # ── At base + low power → charge ──
            if (uav.x, uav.y) == base and uav.power < 95.0:
                uav.status = UAVStatus.CHARGING
                uav.path = []
                continue

            # ── Following a path → advance one cell ──
            if uav.path:
                next_cell = uav.path[0]
                uav.path = uav.path[1:]

                if not self.terrain.is_blocked(next_cell[0], next_cell[1]):
                    # Consume power
                    if not uav.consume_power(uav.POWER_MOVE):
                        uav.path = []
                        continue

                    # Update heading
                    dx = next_cell[0] - uav.x
                    dy = next_cell[1] - uav.y
                    if dx != 0 or dy != 0:
                        uav.heading = float(np.degrees(np.arctan2(dy, dx)) % 360)

                    uav.x, uav.y = next_cell
                    self.explored_grid[next_cell[0], next_cell[1]] = 1

                    if uav.status not in (UAVStatus.RETURNING,):
                        uav.status = UAVStatus.MOVING

                # Path finished → scan
                if not uav.path:
                    if uav.status == UAVStatus.RETURNING:
                        if (uav.x, uav.y) == base:
                            uav.status = UAVStatus.CHARGING
                            events.append(f"{uav.id} arrived at base")
                    else:
                        uav.status = UAVStatus.SCANNING
                        scan = self.scan_zone(uav.id)
                        uav.status = UAVStatus.IDLE
                        if scan.found_objectives:
                            for obj_id in scan.found_objectives:
                                self.objective_field.claim_objective(obj_id, uav.id)
                            events.append(
                                f"{uav.id} found {scan.found_objectives} at ({uav.x},{uav.y})"
                            )
                continue

            # ── Idle + no path → pick a new target ──
            if uav.status == UAVStatus.IDLE and not uav.path:
                target = self._pick_target(uav)
                if target:
                    path = self.path_planner.find_path((uav.x, uav.y), target)
                    if path and len(path) >= 2:
                        uav.path = path[1:]
                        uav.status = UAVStatus.MOVING
                        uav.sector_id = f"→({target[0]},{target[1]})"

        return events

    def _pick_target(self, uav: UAV) -> tuple[int, int] | None:
        """Choose a search target based on probability heatmap. Fast heuristic."""
        # Avoid targets other UAVs are heading to
        claimed: set[tuple[int, int]] = set()
        for other in self.fleet.values():
            if other.id != uav.id and other.path:
                claimed.add(other.path[-1] if isinstance(other.path[-1], tuple)
                            else tuple(other.path[-1]))

        # Score all unexplored passable cells by probability
        mask = (self.explored_grid == 0) & (~self.terrain.obstacle_grid)
        candidates = np.argwhere(mask)
        if len(candidates) == 0:
            return None

        # Rank by probability (higher is better) minus distance penalty
        best_score = -1.0
        best_pos = None
        for cx, cy in candidates[:40]:  # limit to 40 candidates for speed
            pos = (int(cx), int(cy))
            if pos in claimed:
                continue
            prob = float(self.objective_field.prob_matrix[cx, cy])
            dist = abs(cx - uav.x) + abs(cy - uav.y)  # Manhattan distance
            if dist == 0:
                continue
            # Power budget check: rough estimate, need 2x distance for round trip
            if dist * uav.POWER_MOVE * 2 > uav.power * 0.7:
                continue
            score = prob + 0.1 / (dist + 1)  # prefer high-prob, nearby cells
            if score > best_score:
                best_score = score
                best_pos = pos

        return best_pos

    # ─── State Snapshot ─────────────────────────────────────────

    def get_state_snapshot(self) -> dict:
        """Serialize full state for frontend consumption via WebSocket."""
        progress = self.get_search_progress()

        return StateSnapshot(
            tick=self.tick,
            grid_size=self.size,
            fleet=[u.to_dict() for u in self.fleet.values()],
            objectives=[o.to_dict() for o in self.objective_field.objectives.values()],
            coverage_pct=progress.coverage_pct,
            coverage=progress.coverage_pct,
            explored=np.argwhere(self.explored_grid == 1).tolist(),
            obstacles=self.terrain.get_obstacle_positions(),
            heatmap=self.objective_field.get_heatmap_data(),
            hotspots=self.objective_field.get_hotspots(),
            base=list(self.terrain.base_position),
            mission_status=self.mission_status,
            objectives_found=progress.objectives_found,
            objectives_total=progress.objectives_total,
            events=self.events[-20:],
            sectors={k: v.model_dump() for k, v in self.sectors.items()} if self.sectors else None,
        ).model_dump()

    # ─── Internal Helpers ───────────────────────────────────────

    def _emit(self, event: str) -> None:
        """Record a mission event."""
        self.events.append(f"[T{self.tick}] {event}")
