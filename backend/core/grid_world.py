"""GridWorld — 20x20 simulation engine for SwarmMind drone swarm SAR operations."""
from __future__ import annotations

import numpy as np
from pydantic import BaseModel

from .uav import (
    UAV, UAVStatus, CALLSIGNS,
    UAVSummary, UAVDetail, FleetStatus,
    MoveResult, ScanResult, RecallResult, RepowerResult,
    WaypointResult,
    Mission, MissionType, MissionStatus,
)
from .terrain import Terrain
from .objective import ObjectiveField, SearchProgress, ThreatMap, FrontierCell
from .pathplanner import PathPlanner, Route
from .drone import Drone


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

        # Fleet: Drone wrappers around UAVs
        self.drones: dict[str, Drone] = {}
        for i in range(num_uavs):
            callsign = CALLSIGNS[i] if i < len(CALLSIGNS) else f"UAV-{i}"
            self.add_uav(callsign)

        # Sectors (set after partition_sectors is called)
        self.sectors: dict[str, Sector] | None = None

    # ─── Environment Protocol (used by Drone) ────────────────────

    @property
    def base_position(self) -> tuple[int, int]:
        return self.terrain.base_position

    def is_blocked(self, x: int, y: int) -> bool:
        return self.terrain.is_blocked(x, y)

    def find_path(
        self, start: tuple[int, int], end: tuple[int, int],
    ) -> list[tuple[int, int]]:
        return self.path_planner.find_path(start, end)

    def get_occupied_cells(
        self, exclude_id: str | None = None,
    ) -> set[tuple[int, int]]:
        """Set of cells occupied by operational UAVs (excluding base and *exclude_id*)."""
        base = self.terrain.base_position
        occupied: set[tuple[int, int]] = set()
        for drone in self.drones.values():
            uav = drone.uav
            if uav.id == exclude_id or not uav.is_operational:
                continue
            pos = (uav.x, uav.y)
            if pos != base:
                occupied.add(pos)
        return occupied

    def get_unexplored_mask(self) -> np.ndarray:
        """Boolean mask: True for unexplored passable cells."""
        return (self.explored_grid == 0) & (~self.terrain.obstacle_grid)

    def get_prob_matrix(self) -> np.ndarray:
        return self.objective_field.prob_matrix

    # ─── Fleet Management ───────────────────────────────────────

    @property
    def fleet(self) -> dict[str, UAV]:
        """Backward-compatible view: {drone_id: UAV object}."""
        return {did: drone.uav for did, drone in self.drones.items()}

    def add_uav(self, uav_id: str) -> UAV:
        """Add a UAV at the base station."""
        uav = UAV(id=uav_id, x=0, y=0)
        uav.log(f"Deployed at base (0,0)")
        self.drones[uav_id] = Drone(uav)
        return uav

    def remove_uav(self, uav_id: str) -> bool:
        """Remove a UAV from the fleet. Returns True if removed."""
        if uav_id in self.drones:
            del self.drones[uav_id]
            return True
        return False

    def get_uav(self, uav_id: str) -> UAV | None:
        drone = self.drones.get(uav_id)
        return drone.uav if drone else None

    # ─── Movement ───────────────────────────────────────────────

    def move_uav(self, uav_id: str, target_x: int, target_y: int) -> MoveResult:
        """Instant teleport along A* path — **test infrastructure only**.

        NOT exposed via MCP/Agent. Use ``set_waypoint()`` for production
        movement (gradual, 1 cell/tick via autopilot).
        Kept for test fixtures that need to position UAVs quickly.
        """
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

    # ─── Waypoint Navigation (non-teleporting) ──────────────────

    def set_waypoint(self, uav_id: str, target_x: int, target_y: int) -> WaypointResult:
        """Set a navigation waypoint — autopilot executes movement tick by tick.

        Industry best practice: command-acknowledgment pattern.
        The UAV does NOT teleport — it moves 1 cell/tick via autopilot.
        Agent commands take priority over autopilot's autonomous decisions.
        """
        drone = self.drones[uav_id]
        uav = drone.uav

        _err = lambda msg="error": WaypointResult(
            uav_id=uav_id, waypoint=[target_x, target_y],
            current_position=[uav.x, uav.y],
            planned_path=[], estimated_distance=0,
            estimated_power_cost=0, estimated_eta=0,
            affordable=False, status="error",
        )

        if not uav.is_operational:
            return _err()

        if not (0 <= target_x < self.size and 0 <= target_y < self.size):
            return _err()

        if self.terrain.is_blocked(target_x, target_y):
            uav.log(f"Target ({target_x},{target_y}) is blocked")
            return _err()

        path = self.path_planner.find_path((uav.x, uav.y), (target_x, target_y))
        if not path or len(path) < 2:
            uav.log(f"No path to ({target_x},{target_y})")
            return _err()

        distance = len(path) - 1
        power_cost = distance * uav.POWER_MOVE
        affordable = uav.power >= power_cost

        # Set path for autopilot execution (NOT instant teleport)
        uav.path = path[1:]
        uav.command_source = "agent"
        uav._idle_since_tick = 0  # Reset idle timer on new command
        uav.status = UAVStatus.MOVING
        uav.log(f"Waypoint set: ({target_x},{target_y}), ETA {distance} ticks")

        # Track mission on drone
        drone.current_mission = Mission(
            type=MissionType.SEARCH, target=(target_x, target_y),
            status=MissionStatus.IN_PROGRESS, assigned_by="agent",
        )

        self._emit(f"{uav_id} waypoint → ({target_x},{target_y})")

        return WaypointResult(
            uav_id=uav_id,
            waypoint=[target_x, target_y],
            current_position=[uav.x, uav.y],
            planned_path=[[p[0], p[1]] for p in path],
            estimated_distance=distance,
            estimated_power_cost=power_cost,
            estimated_eta=distance,
            affordable=affordable,
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
                command_source=u.command_source,
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
        """Instant teleport recall to base — **test infrastructure only**.

        NOT exposed via MCP/Agent. Use ``set_recall_waypoint()`` for
        production recall (gradual, 1 cell/tick via autopilot).
        """
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

    def set_recall_waypoint(self, uav_id: str) -> WaypointResult:
        """Set a return-to-base waypoint — autopilot executes the return path.

        Unlike recall_uav() which teleports, this sets a path for gradual return.
        """
        drone = self.drones[uav_id]
        uav = drone.uav
        base = self.terrain.base_position

        _err = lambda: WaypointResult(
            uav_id=uav_id, waypoint=list(base),
            current_position=[uav.x, uav.y],
            planned_path=[], estimated_distance=0,
            estimated_power_cost=0, estimated_eta=0,
            affordable=False, status="error",
        )

        if not uav.is_operational:
            return _err()

        path = self.path_planner.find_path((uav.x, uav.y), base)
        if not path:
            return _err()

        distance = len(path) - 1
        power_cost = distance * uav.POWER_MOVE
        affordable = uav.power >= power_cost

        uav.path = path[1:]
        uav.command_source = "agent"
        uav.status = UAVStatus.RETURNING
        uav.log(f"Recall waypoint: base, ETA {distance} ticks")

        # Track mission on drone
        drone.current_mission = Mission(
            type=MissionType.RECALL, target=base,
            status=MissionStatus.IN_PROGRESS, assigned_by="agent",
        )

        self._emit(f"{uav_id} recall waypoint → base")

        return WaypointResult(
            uav_id=uav_id,
            waypoint=list(base),
            current_position=[uav.x, uav.y],
            planned_path=[[p[0], p[1]] for p in path],
            estimated_distance=distance,
            estimated_power_cost=power_cost,
            estimated_eta=distance,
            affordable=affordable,
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

    # ─── Situational Awareness (composite) ──────────────────────

    def get_situational_awareness(self) -> dict:
        """Composite query: fleet + coverage + threats + endurance in one call.

        Industry best practice: reduce MCP round-trips for situational awareness.
        One call replaces query_fleet + get_search_progress + get_threat_map + assess_endurance.
        """
        fleet = self.get_fleet_status()
        progress = self.get_search_progress()
        hotspots = self.objective_field.get_hotspots()

        base = self.terrain.base_position
        endurance = []
        for drone in self.drones.values():
            uav = drone.uav
            route = self.plan_route(uav.x, uav.y, base[0], base[1])
            cells_remaining = int(uav.power // uav.POWER_MOVE)
            power_to_return = route.power_cost
            power_after_return = uav.power - power_to_return
            safe_to_recall = route.reachable and power_after_return > 10.0
            urgent_recall = route.reachable and power_after_return < 5.0
            explorable_cells = max(0, int((uav.power - power_to_return - 5.0) // uav.POWER_MOVE))
            # Mission info from drone
            mission_info = None
            if drone.current_mission:
                mission_info = {
                    "type": drone.current_mission.type.value,
                    "status": drone.current_mission.status.value,
                    "assigned_by": drone.current_mission.assigned_by,
                }
            endurance.append({
                "uav_id": uav.id,
                "status": uav.status.value,
                "power": round(uav.power, 1),
                "cells_remaining": cells_remaining,
                "explorable_cells": explorable_cells,
                "distance_to_base": route.distance,
                "power_to_return": round(power_to_return, 1),
                "safe_to_recall": safe_to_recall,
                "urgent_recall": urgent_recall,
                "mission": mission_info,
            })

        # Spatial intel: which quadrants still need exploration
        half = self.size // 2
        quadrants = {}
        for name, (r0, r1, c0, c1) in [
            ("NW", (0, half, 0, half)),
            ("NE", (0, half, half, self.size)),
            ("SW", (half, self.size, 0, half)),
            ("SE", (half, self.size, half, self.size)),
        ]:
            region = self.explored_grid[r0:r1, c0:c1]
            obs = self.terrain.obstacle_grid[r0:r1, c0:c1]
            passable = int((~obs).sum())
            explored = int(region.sum())
            pct = round(explored / passable * 100, 1) if passable > 0 else 100.0
            quadrants[name] = {
                "coverage_pct": pct,
                "center": [(r0 + r1) // 2, (c0 + c1) // 2],
            }

        return {
            "fleet": fleet.model_dump(),
            "progress": progress.model_dump(),
            "hotspots": hotspots,
            "endurance": endurance,
            "quadrants": quadrants,
            "grid_size": self.size,
            "base": list(base),
            "tick": self.tick,
            "mission_status": self.mission_status,
        }

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

        # ── Drone autonomous behaviour: each drone steps independently ──
        if self.mission_status == "running":
            for drone in self.drones.values():
                events.extend(drone.step(self))

        # Rescue stranded UAVs adjacent to base (power=0, can't move normally)
        base = self.terrain.base_position
        for drone in self.drones.values():
            uav = drone.uav
            if uav.power <= 0 and (uav.x, uav.y) != base:
                dist = abs(uav.x - base[0]) + abs(uav.y - base[1])
                if dist <= 1:
                    uav.x, uav.y = base
                    uav.status = UAVStatus.CHARGING
                    uav.command_source = "autopilot"
                    uav.path = []
                    events.append(f"{uav.id} emergency landing at base")

        # Charge UAVs at base (including reviving offline ones)
        for drone in self.drones.values():
            uav = drone.uav
            at_base = (uav.x, uav.y) == base
            if at_base and uav.power < 100.0:
                if uav.status == UAVStatus.OFFLINE:
                    uav.status = UAVStatus.CHARGING  # revive
                if uav.status in (UAVStatus.CHARGING, UAVStatus.IDLE):
                    uav.status = UAVStatus.CHARGING
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
