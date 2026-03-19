"""Drone — autonomous agent wrapping a UAV with mission management.

Each Drone is the unit of autonomy in the simulation. It:
1. Checks safety constraints (power, obstacles) every tick
2. Advances along its current path
3. Handles path completion (scan for autopilot, idle for agent)
4. Picks new targets when idle (autopilot mode only)

The AI Agent interacts through assign_mission() and get_report().
The autopilot logic migrated here from GridWorld._autopilot_tick().
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from .uav import (
    UAV, UAVStatus,
    Mission, MissionType, MissionStatus, MissionReport,
)

if TYPE_CHECKING:
    from .grid_world import GridWorld

# Safety override threshold: autopilot ignores agent commands below this
CRITICAL_POWER = 10.0
# Ticks before agent-controlled idle UAV reverts to autopilot
AGENT_IDLE_TIMEOUT = 10


class Drone:
    """Autonomous drone: wraps a UAV with autopilot behaviour + mission management."""

    def __init__(self, uav: UAV):
        self.uav = uav
        self.current_mission: Mission | None = None

    def step(self, env: GridWorld) -> list[str]:
        """Execute one tick of autonomous behavior.

        Args:
            env: The GridWorld providing environment context.

        Returns:
            List of event strings for this tick.
        """
        events: list[str] = []
        uav = self.uav
        base = env.base_position

        if not uav.is_operational:
            return events

        # ── 1. Smart recall: power-aware return-to-base ──
        if (uav.x, uav.y) != base:
            recall_path = env.find_path((uav.x, uav.y), base)
            real_dist = (
                (len(recall_path) - 1)
                if (recall_path and len(recall_path) > 1)
                else (abs(uav.x - base[0]) + abs(uav.y - base[1]))
            )
            power_needed = (real_dist + 1) * uav.POWER_MOVE  # +1 safety margin

            should_recall = False
            if uav.status == UAVStatus.RETURNING:
                pass  # Already heading home — don't interrupt
            elif uav.power <= power_needed:
                # Universal rule: if power can't cover return trip, GO HOME NOW.
                # Applies regardless of command_source — survival trumps all.
                should_recall = True
                if uav.command_source == "agent":
                    events.append(
                        f"{uav.id} SAFETY OVERRIDE: power {uav.power:.0f}% "
                        f"< {power_needed:.0f}% needed to return, ignoring agent"
                    )
            elif uav.command_source != "agent" and uav.is_low_power:
                # Autopilot-only: also recall at general low-power threshold
                should_recall = True

            if should_recall:
                path = env.find_path((uav.x, uav.y), base)
                uav.path = path[1:] if path else []
                uav.status = UAVStatus.RETURNING
                uav.command_source = "autopilot"
                self.current_mission = Mission(
                    type=MissionType.RECALL, target=base,
                    status=MissionStatus.IN_PROGRESS, assigned_by="autopilot",
                )
                if not any(uav.id in e for e in events):
                    events.append(
                        f"{uav.id} power={uav.power:.0f}% → returning to base"
                    )

        # ── 2. At base → charge (block departure below 30%) ──
        if (uav.x, uav.y) == base and uav.power < 95.0:
            if uav.command_source == "agent" and uav.path and uav.power >= 30.0:
                pass  # Agent authority: allow departure above minimum
            else:
                uav.status = UAVStatus.CHARGING
                uav.path = []
                uav.command_source = "autopilot"
                return events

        # ── 3. Following a path → advance one cell ──
        if uav.path:
            next_cell = uav.path[0]
            uav.path = uav.path[1:]

            if not env.is_blocked(next_cell[0], next_cell[1]):
                # Collision avoidance
                next_pos = (
                    next_cell if isinstance(next_cell, tuple)
                    else tuple(next_cell)
                )
                near_base = (
                    abs(next_pos[0] - base[0]) + abs(next_pos[1] - base[1])
                ) <= 2

                if (not near_base
                        and uav.status != UAVStatus.RETURNING
                        and next_pos in env.get_occupied_cells(uav.id)):
                    uav.path.insert(0, next_cell)
                    return events

                # Power consumption
                if next_pos == base and uav.status == UAVStatus.RETURNING:
                    pass  # Free emergency return
                elif not uav.consume_power(uav.POWER_MOVE):
                    if next_pos == base:
                        pass  # Emergency landing
                    else:
                        uav.path = []
                        uav.command_source = "autopilot"
                        return events

                # Move
                dx = next_cell[0] - uav.x
                dy = next_cell[1] - uav.y
                if dx != 0 or dy != 0:
                    uav.heading = float(np.degrees(np.arctan2(dy, dx)) % 360)

                uav.x, uav.y = next_cell[0], next_cell[1]
                env.explored_grid[uav.x, uav.y] = 1

                if uav.status not in (UAVStatus.RETURNING,):
                    uav.status = UAVStatus.MOVING

            # Path finished → handle based on who issued the command
            if not uav.path:
                if uav.status == UAVStatus.RETURNING:
                    if (uav.x, uav.y) == base:
                        uav.status = UAVStatus.CHARGING
                        uav.command_source = "autopilot"
                        if self.current_mission:
                            self.current_mission.status = MissionStatus.COMPLETED
                        events.append(f"{uav.id} arrived at base")
                    else:
                        # Path exhausted before reaching base — recompute
                        new_path = env.find_path((uav.x, uav.y), base)
                        uav.path = (
                            new_path[1:]
                            if new_path and len(new_path) > 1 else []
                        )
                        uav.command_source = "autopilot"
                elif uav.command_source == "agent":
                    # Agent path complete: don't auto-scan, let agent decide
                    uav.status = UAVStatus.IDLE
                    uav._idle_since_tick = env.tick
                    if self.current_mission:
                        self.current_mission.status = MissionStatus.COMPLETED
                    events.append(
                        f"{uav.id} arrived at waypoint ({uav.x},{uav.y})"
                    )
                else:
                    # Autopilot path: auto-scan as before
                    uav.status = UAVStatus.SCANNING
                    scan = env.scan_zone(uav.id)
                    uav.status = UAVStatus.IDLE
                    uav.command_source = "autopilot"
                    if self.current_mission:
                        self.current_mission.status = MissionStatus.COMPLETED
                    if scan.found_objectives:
                        for obj_id in scan.found_objectives:
                            env.objective_field.claim_objective(obj_id, uav.id)
                        events.append(
                            f"{uav.id} found {scan.found_objectives} at ({uav.x},{uav.y})"
                        )
            return events

        # ── 4. Agent idle timeout: release control ──
        if (uav.status == UAVStatus.IDLE and not uav.path
                and uav.command_source == "agent"):
            idle_since = uav._idle_since_tick
            if env.tick - idle_since >= AGENT_IDLE_TIMEOUT:
                uav.command_source = "autopilot"
                self.current_mission = None
                events.append(f"{uav.id} agent idle timeout → autopilot")

        # ── 5. Idle + autopilot → pick new target ──
        if (uav.status == UAVStatus.IDLE and not uav.path
                and uav.command_source != "agent"):
            target = self._pick_target(env)
            if target:
                path = env.find_path((uav.x, uav.y), target)
                if path and len(path) >= 2:
                    uav.path = path[1:]
                    uav.status = UAVStatus.MOVING
                    uav.sector_id = f"→({target[0]},{target[1]})"
                    self.current_mission = Mission(
                        type=MissionType.SEARCH,
                        target=target,
                        status=MissionStatus.IN_PROGRESS,
                        assigned_by="autopilot",
                    )

        return events

    def assign_mission(self, mission: Mission, env: GridWorld) -> MissionReport:
        """Accept a mission from the AI Agent.

        Validates preconditions and returns accepted/rejected status.
        """
        uav = self.uav
        base = env.base_position

        # Reject conditions
        if uav.status == UAVStatus.RETURNING:
            return self._report(env, "rejected: drone is returning to base")
        if uav.status == UAVStatus.CHARGING and uav.power < 30.0:
            return self._report(
                env, f"rejected: charging ({uav.power:.0f}% < 30%)"
            )
        if uav.power < 30.0 and (uav.x, uav.y) != base:
            return self._report(
                env, f"rejected: low power ({uav.power:.0f}% < 30%)"
            )
        if not uav.is_operational:
            return self._report(env, "rejected: drone offline")

        if mission.type == MissionType.SEARCH and mission.target:
            tx, ty = mission.target
            if not (0 <= tx < env.size and 0 <= ty < env.size):
                return self._report(
                    env, f"rejected: target ({tx},{ty}) out of bounds"
                )
            if env.is_blocked(tx, ty):
                return self._report(
                    env, f"rejected: target ({tx},{ty}) is blocked"
                )

            path_to_target = env.find_path((uav.x, uav.y), mission.target)
            if not path_to_target or len(path_to_target) < 2:
                return self._report(
                    env, f"rejected: no path to ({tx},{ty})"
                )

            # Round-trip power check: can we reach target AND return to base?
            path_back = env.find_path(mission.target, base)
            dist_to_target = len(path_to_target) - 1
            dist_back = (
                (len(path_back) - 1)
                if (path_back and len(path_back) > 1)
                else (abs(tx - base[0]) + abs(ty - base[1]))
            )
            round_trip_cost = (dist_to_target + dist_back + 2) * uav.POWER_MOVE
            if uav.power < round_trip_cost:
                return self._report(
                    env,
                    f"rejected: insufficient power for round trip "
                    f"({uav.power:.0f}% < {round_trip_cost:.0f}% needed: "
                    f"{dist_to_target} to target + {dist_back} back)"
                )

            uav.path = path_to_target[1:]
            uav.command_source = "agent"
            uav._idle_since_tick = 0
            uav.status = UAVStatus.MOVING
            mission.status = MissionStatus.IN_PROGRESS
            self.current_mission = mission
            uav.log(f"Mission: search ({tx},{ty})")
            return self._report(env, "accepted")

        elif mission.type == MissionType.RECALL:
            path = env.find_path((uav.x, uav.y), base)
            if not path:
                return self._report(env, "rejected: no path to base")

            uav.path = path[1:]
            uav.command_source = "agent"
            uav.status = UAVStatus.RETURNING
            mission.status = MissionStatus.IN_PROGRESS
            self.current_mission = mission
            uav.log("Mission: recall to base")
            return self._report(env, "accepted")

        return self._report(env, "rejected: unknown mission type")

    def get_report(self, env: GridWorld) -> MissionReport:
        """Return structured status for AI consumption."""
        return self._report(env, self.uav.status.value)

    def _report(self, env: GridWorld, status: str) -> MissionReport:
        """Build a MissionReport."""
        uav = self.uav
        base = env.base_position

        # Calculate explorable cells (power left after return trip)
        route = env.find_path((uav.x, uav.y), base)
        dist_to_base = (
            (len(route) - 1) if (route and len(route) > 1)
            else (abs(uav.x - base[0]) + abs(uav.y - base[1]))
        )
        power_to_return = dist_to_base * uav.POWER_MOVE
        explorable = max(
            0, int((uav.power - power_to_return - 5.0) // uav.POWER_MOVE)
        )

        eta = len(uav.path) if uav.path else 0

        # Mission info
        mission_dict = None
        mission_status = "idle"
        if self.current_mission:
            mission_dict = {
                "type": self.current_mission.type.value,
                "target": (
                    list(self.current_mission.target)
                    if self.current_mission.target else None
                ),
                "status": self.current_mission.status.value,
                "assigned_by": self.current_mission.assigned_by,
            }
            if self.current_mission.status == MissionStatus.IN_PROGRESS:
                mission_status = "executing"
            elif self.current_mission.status == MissionStatus.COMPLETED:
                mission_status = "completed"
            else:
                mission_status = self.current_mission.status.value
        elif uav.path:
            mission_status = "executing"

        return MissionReport(
            drone_id=uav.id,
            status=status,
            power=round(uav.power, 1),
            position=[uav.x, uav.y],
            mission=mission_dict,
            mission_status=mission_status,
            explorable_cells=explorable,
            eta=eta,
        )

    def _pick_target(self, env: GridWorld) -> tuple[int, int] | None:
        """Choose a search target with adaptive spread and power budgeting.

        Scoring: probability-weighted, distance-penalised, repulsion from
        other UAVs using inverse-square decay scaled by fleet density.
        """
        uav = self.uav

        # Build set of cells other UAVs are heading to or occupying
        claimed: set[tuple[int, int]] = set()
        for other in env.fleet.values():
            if other.id != uav.id and other.path:
                last = other.path[-1]
                claimed.add(last if isinstance(last, tuple) else tuple(last))
            if other.id != uav.id and other.is_operational:
                claimed.add((other.x, other.y))

        # Get unexplored passable cells
        mask = env.get_unexplored_mask()
        candidates = np.argwhere(mask)
        if len(candidates) == 0:
            return None

        # Round-trip power budget: drone must be able to return to base
        base = env.base_position
        dist_to_base = abs(uav.x - base[0]) + abs(uav.y - base[1])
        power_for_return = (dist_to_base + 2) * uav.POWER_MOVE  # +2 safety
        available = uav.power - power_for_return
        if available <= 0:
            return None
        max_one_way = int(available / uav.POWER_MOVE)

        # Filter by power budget and distance
        dists = (np.abs(candidates[:, 0] - uav.x)
                 + np.abs(candidates[:, 1] - uav.y))
        reachable = dists <= max_one_way
        candidates = candidates[reachable]
        dists = dists[reachable]

        if len(candidates) == 0:
            return None

        # Scoring
        probs = env.get_prob_matrix()[candidates[:, 0], candidates[:, 1]]
        dists_f = np.maximum(dists.astype(float), 1.0)

        # Repulsion: inverse-square decay, scaled by fleet density
        num_active = sum(1 for u in env.fleet.values() if u.is_operational)
        repulsion_weight = 0.15 * num_active / max(len(env.fleet), 1)

        repulsion = np.zeros(len(candidates))
        for cx, cy in claimed:
            d = np.abs(candidates[:, 0] - cx) + np.abs(candidates[:, 1] - cy)
            repulsion += 1.0 / (d.astype(float) ** 2 + 1.0)

        scores = ((probs + 0.1) / np.sqrt(dists_f)
                  - repulsion * repulsion_weight)

        best_idx = int(np.argmax(scores))
        return (int(candidates[best_idx][0]), int(candidates[best_idx][1]))
