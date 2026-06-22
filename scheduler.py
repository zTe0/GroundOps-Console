from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import math
import uuid
import asyncio

from orbital import SATELLITE_REGISTRY, GROUND_STATION, get_satellite_position


@dataclass
class PassWindow:
    """A predicted contact window over the ground station."""
    satellite_id: str
    aos_time: datetime      # Acquisition of Signal
    los_time: datetime      # Loss of Signal
    max_elevation: float    # degrees above horizon
    duration_seconds: float


# Task durations in seconds
TASK_DURATIONS = {
    "payload_downlink": 120,
    "housekeeping_dump": 60,
    "attitude_upload": 90,
}


@dataclass
class Task:
    """An operational task queued against a pass window."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    satellite_id: str = ""
    task_type: str = ""
    pass_id: str = ""
    status: str = "PENDING"  # PENDING, SCHEDULED, DEFERRED, EXECUTED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# In-memory task queue
task_queue: list[Task] = []


def predict_passes(sat_id: str, hours: int = 24) -> list[PassWindow]:
    """Predict passes over the ground station using 30s elevation stepping."""
    passes = []
    now = datetime.now(timezone.utc)
    step_seconds = 30
    total_steps = int(hours * 3600 / step_seconds)

    # Ground station coordinates in radians
    gs_lat = math.radians(GROUND_STATION["lat"])
    gs_lon = math.radians(GROUND_STATION["lon"])
    gs_alt_km = GROUND_STATION["alt_km"]

    in_pass = False
    aos_time = None
    max_el = 0.0

    for i in range(total_steps):
        dt = now + timedelta(seconds=i * step_seconds)
        pos = get_satellite_position(sat_id, dt)
        if pos is None:
            continue

        # Convert satellite position to radians
        sat_lat = math.radians(pos["lat"])
        sat_lon = math.radians(pos["lon"])
        sat_alt_km = pos["alt_km"]

        # Compute elevation angle using slant range geometry
        earth_radius = 6371.0
        gs_r = earth_radius + gs_alt_km
        sat_r = earth_radius + sat_alt_km

        # Central angle between ground station and satellite sub-point
        cos_gamma = (math.sin(gs_lat) * math.sin(sat_lat) +
                     math.cos(gs_lat) * math.cos(sat_lat) *
                     math.cos(sat_lon - gs_lon))
        gamma = math.acos(max(-1, min(1, cos_gamma)))

        # Elevation angle from ground station to satellite
        elevation = math.degrees(
            math.atan2(sat_r * math.cos(gamma) - gs_r,
                       sat_r * math.sin(gamma))
        )

        if elevation > 0 and not in_pass:
            # AOS detected
            in_pass = True
            aos_time = dt
            max_el = elevation
        elif elevation > 0 and in_pass:
            max_el = max(max_el, elevation)
        elif elevation <= 0 and in_pass:
            # LOS detected
            in_pass = False
            los_time = dt
            duration = (los_time - aos_time).total_seconds()
            passes.append(PassWindow(
                satellite_id=sat_id,
                aos_time=aos_time,
                los_time=los_time,
                max_elevation=round(max_el, 2),
                duration_seconds=duration,
            ))
            aos_time = None
            max_el = 0.0

    return passes

def queue_task(satellite_id: str, task_type: str, pass_id: str = "") -> Task:
    """Queue a task and run greedy first-fit scheduling."""
    task = Task(
        satellite_id=satellite_id,
        task_type=task_type,
        pass_id=pass_id,
        status="PENDING",
    )
    task_queue.append(task)

    # Run greedy first-fit scheduling for this satellite
    passes = predict_passes(satellite_id)
    _schedule_tasks(passes, satellite_id)

    return task

def _schedule_tasks(passes: list[PassWindow], satellite_id: str):
    """Greedy first-fit: assign tasks to the earliest pass with enough time."""
    # Calculate remaining time in each pass window
    pass_remaining = {}
    for i, pw in enumerate(passes):
        pass_id = f"{satellite_id}-pass-{i}"
        already_scheduled = sum(
            TASK_DURATIONS[t.task_type]
            for t in task_queue
            if t.status == "SCHEDULED" and t.pass_id == pass_id
        )
        pass_remaining[pass_id] = pw.duration_seconds - already_scheduled

    # Try to fit each PENDING task into the earliest available pass
    for task in task_queue:
        if task.satellite_id != satellite_id or task.status != "PENDING":
            continue

        duration_needed = TASK_DURATIONS.get(task.task_type, 0)
        scheduled = False

        for i, pw in enumerate(passes):
            pass_id = f"{satellite_id}-pass-{i}"
            if pass_remaining.get(pass_id, 0) >= duration_needed:
                task.status = "SCHEDULED"
                task.pass_id = pass_id
                pass_remaining[pass_id] -= duration_needed
                scheduled = True
                break

        if not scheduled:
            task.status = "DEFERRED"

async def trigger_pass_execution(pass_window: PassWindow):
    """Execute all SCHEDULED tasks for a pass through the autopilot sequencer."""
    # Find the pass_id for this window
    pass_id = None
    passes = predict_passes(pass_window.satellite_id)
    for i, pw in enumerate(passes):
        if pw.aos_time == pass_window.aos_time:
            pass_id = f"{pass_window.satellite_id}-pass-{i}"
            break

    if pass_id is None:
        return

    # Map task types to Project 1 procedure names
    procedure_map = {
        "payload_downlink": "safe_mode_recovery",
        "housekeeping_dump": "telemetry_dump",
        "attitude_upload": "attitude_correction",
    }

    scheduled_tasks = [
        t for t in task_queue
        if t.pass_id == pass_id and t.status == "SCHEDULED"
    ]

    for task in scheduled_tasks:
        procedure_name = procedure_map.get(task.task_type, "telemetry_dump")
        print(f"[SCHEDULER] Executing {task.task_type} via procedure "
              f"'{procedure_name}' for satellite {task.satellite_id}")
        # In production, this calls the autopilot sequencer from Project 1
        # autopilot.execute_procedure(procedure_name)
        task.status = "EXECUTED"

    return scheduled_tasks


async def pass_monitor():
    """Background task that checks for AOS times and triggers execution."""
    while True:
        now = datetime.now(timezone.utc)
        for sat_id in SATELLITE_REGISTRY:
            passes = predict_passes(sat_id, hours=1)
            for pw in passes:
                # Check if we are within the pass window
                if pw.aos_time <= now <= pw.los_time:
                    await trigger_pass_execution(pw)
        await asyncio.sleep(30)