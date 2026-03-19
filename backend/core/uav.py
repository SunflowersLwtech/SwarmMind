"""UAV (Unmanned Aerial Vehicle) model for SwarmMind simulation."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pydantic import BaseModel


class UAVStatus(str, Enum):
    IDLE = "idle"
    MOVING = "moving"
    SCANNING = "scanning"
    RETURNING = "returning"
    CHARGING = "charging"
    OFFLINE = "offline"


# ─── Mission Models ─────────────────────────────────────────────

class MissionType(str, Enum):
    SEARCH = "search"    # fly to target + scan on arrival
    RECALL = "recall"    # return to base
    IDLE = "idle"


class MissionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Mission:
    type: MissionType
    target: tuple[int, int] | None = None
    status: MissionStatus = MissionStatus.PENDING
    assigned_by: str = "autopilot"


# Module-level power threshold constant
LOW_POWER_THRESHOLD = 20.0

# Greek-letter callsigns
CALLSIGNS = ["Alpha", "Bravo", "Charlie", "Delta", "Echo",
             "Foxtrot", "Golf", "Hotel", "India", "Juliet"]


@dataclass
class UAV:
    """Mutable UAV state used by the simulation engine."""
    id: str
    x: int = 0
    y: int = 0
    power: float = 100.0          # 0-100%
    status: UAVStatus = UAVStatus.IDLE
    heading: float = 0.0          # 0-360 degrees
    sensor_range: int = 2         # scan radius in cells
    comms_range: int = 10         # communication range in cells
    sector_id: str | None = None
    mission_log: list[str] = field(default_factory=list)
    path: list[tuple[int, int]] = field(default_factory=list)  # current movement path
    command_source: str = "autopilot"  # "agent" or "autopilot" — who issued current command
    _idle_since_tick: int = 0          # tick when UAV became idle (for agent timeout)

    # Power consumption constants
    POWER_MOVE: float = 2.0       # per cell
    POWER_SCAN: float = 1.0       # per scan
    POWER_CHARGE: float = 20.0    # per step while charging
    LOW_POWER: float = 20.0       # threshold for low power warning

    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = UAVStatus(self.status)

    @property
    def is_low_power(self) -> bool:
        return self.power <= self.LOW_POWER

    @property
    def is_operational(self) -> bool:
        return self.status != UAVStatus.OFFLINE and self.power > 0

    def consume_power(self, amount: float) -> bool:
        """Consume power. Returns False if insufficient."""
        if self.power < amount:
            return False
        self.power = max(0.0, self.power - amount)
        if self.power == 0:
            self.status = UAVStatus.OFFLINE
        return True

    def charge(self) -> float:
        """Charge one step. Returns new power level."""
        self.power = min(100.0, self.power + self.POWER_CHARGE)
        if self.power >= 100.0:
            self.status = UAVStatus.IDLE
        return self.power

    def log(self, message: str) -> None:
        self.mission_log.append(message)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "power": round(self.power, 1),
            "status": self.status.value,
            "heading": self.heading,
            "sensor_range": self.sensor_range,
            "comms_range": self.comms_range,
            "sector_id": self.sector_id,
            "is_low_power": self.is_low_power,
            "command_source": self.command_source,
        }


# ─── Pydantic Response Models ──────────────────────────────────

class UAVSummary(BaseModel):
    id: str
    x: int
    y: int
    power: float
    status: str
    heading: float
    sector_id: str | None = None
    is_low_power: bool = False
    command_source: str = "autopilot"

class UAVDetail(BaseModel):
    id: str
    x: int
    y: int
    power: float
    status: str
    heading: float
    sensor_range: int
    comms_range: int
    sector_id: str | None = None
    is_low_power: bool = False
    mission_log: list[str] = []

class FleetStatus(BaseModel):
    uavs: list[UAVSummary]
    total: int
    active: int
    idle: int
    low_power: int
    avg_power: float

class MoveResult(BaseModel):
    uav_id: str
    path: list[list[int]]
    distance: int
    power_cost: float
    new_position: list[int]
    new_power: float
    status: str = "ok"

class ScanResult(BaseModel):
    uav_id: str
    scanned_cells: list[list[int]]
    found_objectives: list[str]
    coverage_delta: float
    power_after: float

class RecallResult(BaseModel):
    uav_id: str
    return_path: list[list[int]]
    eta: int
    power_on_arrival: float
    status: str = "ok"

class RepowerResult(BaseModel):
    uav_id: str
    old_power: float
    new_power: float
    fully_charged: bool


class MissionReport(BaseModel):
    """Structured drone status returned by Drone.get_report() / assign_mission()."""
    drone_id: str
    status: str
    power: float
    position: list[int]
    mission: dict | None = None     # current mission description
    mission_status: str = "idle"    # idle / executing / completed / returning
    explorable_cells: int = 0       # cells explorable after reserving return power
    eta: int = 0                    # ticks until arrival


class WaypointResult(BaseModel):
    """Result of setting a navigation waypoint (non-teleporting).

    Industry best practice: command-acknowledgment pattern.
    The UAV does NOT teleport — it moves 1 cell/tick via autopilot.
    """
    uav_id: str
    waypoint: list[int]           # Target [x, y]
    current_position: list[int]   # Where UAV is now (unchanged)
    planned_path: list[list[int]]
    estimated_distance: int
    estimated_power_cost: float
    estimated_eta: int            # Ticks until arrival
    affordable: bool = True       # Can UAV afford the full trip?
    status: str = "ok"
