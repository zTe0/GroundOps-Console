import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from autopilot import AutopilotSequencer
from monitor import TelemetryMonitor
from procedures import ProcedureEngine
from resolvers import ResolverSystem
from simulator import SatelliteSimulator

from fastapi import HTTPException

from datetime import datetime, timezone
from orbital import (
    SATELLITE_REGISTRY, GROUND_STATION,
    get_satellite_position, get_ground_track, get_passes,
    register_custom_satellite
)
from scheduler import (
    predict_passes, queue_task, task_queue,
    TASK_DURATIONS, pass_monitor
)

import persistence
from typing import Optional

import traceback
import os, sys

import uvicorn

if getattr(sys, 'frozen', False):
    # Running as compiled .exe
    base_path = sys._MEIPASS
else:
    # Running as normal script
    base_path = os.path.dirname(os.path.abspath(__file__))

static_path = os.path.join(base_path, 'static')



# Read PORT from environment (Render)
port = int(os.environ.get("PORT", 8000))

# Module-level instances shared across the application
simulator = SatelliteSimulator()
monitor = TelemetryMonitor()
engine = ProcedureEngine()
resolvers = ResolverSystem()
autopilot = AutopilotSequencer(engine)
connected_clients: list[WebSocket] = []


async def safe_task_runner(coroutine, task_name: str):
    """Wrapper that prevents background coroutines from crashing silently."""
    try:
        print(f"[SYSTEM] Starting background task: {task_name}")
        await coroutine
    except Exception as e:
        print(f"\n[CRITICAL ERROR] Background task '{task_name}' has crashed!")
        print("------------------------------------------------------------")
        traceback.print_exc()  # Prints the exact file line and error causing the crash
        print("------------------------------------------------------------\n")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Structure the database tables
    await persistence.init_db()
    
    # 2. Schedule background tasks using the Safe Runner
    asyncio.create_task(safe_task_runner(telemetry_loop(), "Telemetry Monitor"))
    asyncio.create_task(safe_task_runner(pass_monitor(), "Pass Monitor"))
    
    yield

async def telemetry_loop():
    while True:
        frame = simulator.generate_frame()
        alerts = monitor.evaluate(frame)

        # Build a lookup so we can tag each channel with its alarm state
        alert_by_param = {a.parameter: a.severity.value for a in alerts}

        # Persist every numeric telemetry channel to the database
        for channel in ("battery_voltage", "obc_temperature", "comms_signal_strength"):
            value = getattr(frame, channel)
            alarm_state = alert_by_param.get(channel, "NOMINAL")
            await persistence.log_telemetry(frame.satellite_id, channel, value, alarm_state)

        # Auto-resolve alerts by firing the matched procedure, then log the action
        for alert in alerts:
            procedure_name = resolvers.match(alert)
            if procedure_name:
                outcome = await engine.execute(procedure_name, simulator.command)
                resolvers.log_action(alert, outcome)
                await persistence.log_resolver(
                    f"{alert.parameter}:{alert.severity.value}",
                    procedure_name,
                    "SUCCESS" if outcome.success else "FAILURE",
                )

        # Broadcast telemetry to all connected WebSocket clients
        frame_data = frame.model_dump_json()
        for client in connected_clients.copy():
            try:
                await client.send_text(frame_data)
            except Exception:
                connected_clients.remove(client)

        await asyncio.sleep(1.0)

# @app.get("/")
# async def root():
#     return FileResponse("static/index.html")
app = FastAPI(title="GroundOps Console", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.websocket("/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)


@app.get("/api/alerts")
async def get_alerts():
    return {"alerts": [a.model_dump() for a in monitor.alerts[-50:]]}


@app.get("/api/procedures")
async def get_procedures():
    return {"procedures": list(engine.procedures.keys())}


@app.post("/api/procedures/{name}/execute")
async def execute_procedure(name: str):
    if name not in engine.procedures:
        return {"error": f"Procedure '{name}' not found"}
    outcome = await engine.execute(name, simulator.command)
    await persistence.log_command(
        simulator.satellite_id, "manual", name,
        "SUCCESS" if outcome.success else "FAILURE"
    )
    return outcome.model_dump()


class AutopilotRequest(BaseModel):
    sequence_name: str
    procedure_names: list[str]


@app.post("/api/autopilot/execute")
async def execute_autopilot(request: AutopilotRequest):
    result = await autopilot.execute_sequence(
        request.sequence_name, request.procedure_names, simulator.command
    )
    for outcome in result.procedure_outcomes:
        await persistence.log_command(
            simulator.satellite_id, "autopilot", outcome.procedure_name,
            "SUCCESS" if outcome.success else "FAILURE"
        )
    return result.model_dump()


@app.get("/api/autopilot/history")
async def get_autopilot_history():
    return {"history": [r.model_dump() for r in autopilot.history]}


@app.get("/api/resolver/history")
async def get_resolver_history():
    return {"history": resolvers.history}

class SatelliteRegisterRequest(BaseModel):
    norad_id: int = Field(..., description="Official NORAD Catalog ID")

@app.post("/satellites/register")
async def api_register_satellite(req: SatelliteRegisterRequest):
    """Register satellite dynamically by fetching its name and TLE from PocketWorld."""
    success = await register_custom_satellite(req.norad_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch or parse TLE for NORAD {req.norad_id}."
        )
    return {"message": "Success! Spacecraft added to active catalog."}



# @app.get("/satellites/{sat_id}/passes")
# async def satellite_passes(
#     sat_id: str, 
#     lat: float | None = None, 
#     lon: float | None = None, 
#     alt_km: float | None = None
# ):
#     """Get passes with optional custom Ground Station coordinates."""
#     if sat_id not in SATELLITE_REGISTRY:
#         return {"error": f"Satellite {sat_id} not found"}
        
#     passes_list = get_passes(sat_id, hours=24, gs_lat=lat, gs_lon=lon, gs_alt_km=alt_km)
    
#     # Return the observer location used for confirmation
#     observer = {
#         "name": "Custom Ground Station" if lat is not None else GROUND_STATION["name"],
#         "lat": lat if lat is not None else GROUND_STATION["lat"],
#         "lon": lon if lon is not None else GROUND_STATION["lon"],
#         "alt_km": alt_km if alt_km is not None else GROUND_STATION["alt_km"],
#     }
    
#     return {
#         "satellite_id": sat_id,
#         "ground_station": observer,
#         "passes": passes_list,
#     }

@app.get("/satellites")
async def list_satellites():
    """List all satellites in the constellation registry."""
    return {
        "satellites": [
            {"id": sat_id, "name": data["name"], "norad_id": data["norad_id"]}
            for sat_id, data in SATELLITE_REGISTRY.items()
        ],
        "ground_station": GROUND_STATION,
    }


@app.get("/satellites/{sat_id}/position")
async def satellite_position(sat_id: str):
    import math
    from orbital import _satellites
    from sgp4.api import jday
    """Get current lat/lon/alt of a satellite."""
    now = datetime.now(timezone.utc)
    pos = get_satellite_position(sat_id, now)
    if pos is None:
        return {"error": f"Satellite {sat_id} not found or propagation error"}
    orbital_el = {}
    sat_obj = _satellites.get(sat_id)
    if sat_obj:
        inclination_deg = math.degrees(sat_obj.inclo)
        eccentricity    = sat_obj.ecco
        period_min      = (2 * math.pi) / sat_obj.no
        jd, fr = jday(now.year, now.month, now.day,
                    now.hour, now.minute, now.second + now.microsecond / 1e6)
        e, _, vel_teme = sat_obj.sgp4(jd, fr)
        speed_kms = round(math.sqrt(sum(v**2 for v in vel_teme)), 3) if e == 0 else None
        orbital_el = {
            "inclination_deg": round(inclination_deg, 4),
            "eccentricity":    round(eccentricity, 7),
            "period_min":      round(period_min, 2),
            "speed_kms":       speed_kms,
        }

    return {"satellite_id": sat_id, "timestamp": now.isoformat(), **pos, **orbital_el}

@app.get("/satellites/{sat_id}/ground-track")
async def satellite_ground_track(sat_id: str):
    """Get ground track for the next period at 60s intervals."""
    if sat_id not in SATELLITE_REGISTRY:
        return {"error": f"Satellite {sat_id} not found"}
    track = get_ground_track(sat_id, interval_s=60)
    return {"satellite_id": sat_id, "track": track}


@app.get("/satellites/{sat_id}/passes")
async def satellite_passes(
    sat_id: str,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    alt_km: Optional[float] = None,
):
    """Get predicted passes over ground station in the next 24 hours.
    Accepts optional lat/lon/alt_km query params to override the default ground station."""
    if sat_id not in SATELLITE_REGISTRY:
        return {"error": f"Satellite {sat_id} not found"}
    passes_list = get_passes(sat_id, hours=24, gs_lat=lat, gs_lon=lon, gs_alt_km=alt_km)
    observer = {
        "name": f"Custom Observer ({lat}, {lon})" if lat is not None else GROUND_STATION["name"],
        "lat":    lat    if lat    is not None else GROUND_STATION["lat"],
        "lon":    lon    if lon    is not None else GROUND_STATION["lon"],
        "alt_km": alt_km if alt_km is not None else GROUND_STATION["alt_km"],
    }
    return {
        "satellite_id": sat_id,
        "ground_station": observer,
        "passes": passes_list,
    }

@app.post("/scheduler/queue-task")
async def api_queue_task(satellite_id: str, task_type: str, pass_id: str = ""):
    """Queue an operational task against a satellite pass."""
    sat_id_clean = satellite_id.strip().lower()
    if task_type not in TASK_DURATIONS:
        return {"error": f"Invalid task type. Choose from: {list(TASK_DURATIONS.keys())}"}
    task = queue_task(sat_id_clean, task_type, pass_id)
    return {"task_id": task.id, "status": task.status, "pass_id": task.pass_id}


@app.get("/scheduler/passes")
async def api_scheduler_passes(satellite_id: str = ""):
    """Get upcoming passes with their queued tasks."""
    from orbital import SATELLITE_REGISTRY
    results = []
    sat_ids = [satellite_id] if satellite_id else list(SATELLITE_REGISTRY.keys())
    for sid in sat_ids:
        passes = predict_passes(sid)
        for i, pw in enumerate(passes):
            pass_id = f"{sid}-pass-{i}"
            tasks = [t for t in task_queue if t.pass_id == pass_id]
            results.append({
                "pass_id": pass_id,
                "satellite_id": sid,
                "aos_time": pw.aos_time.isoformat(),
                "los_time": pw.los_time.isoformat(),
                "max_elevation": pw.max_elevation,
                "duration_seconds": pw.duration_seconds,
                "tasks": [{"id": t.id, "type": t.task_type, "status": t.status} for t in tasks],
            })
    return results


@app.get("/scheduler/tasks")
async def api_scheduler_tasks():
    """Get all tasks with their current status."""
    return [
        {
            "id": t.id,
            "satellite_id": t.satellite_id,
            "task_type": t.task_type,
            "pass_id": t.pass_id,
            "status": t.status,
            "created_at": t.created_at.isoformat(),
        }
        for t in task_queue
    ]


@app.get("/logs/telemetry")
async def get_telemetry_logs(start_time: Optional[str] = None, end_time: Optional[str] = None):
    """Retrieve telemetry log with optional time-range filter."""
    return await persistence.get_telemetry_logs(start_time, end_time)

@app.get("/logs/commands")
async def get_command_logs(start_time: Optional[str] = None, end_time: Optional[str] = None):
    """Retrieve command log with optional time-range filter."""
    return await persistence.get_command_logs(start_time, end_time)

@app.get("/logs/resolver")
async def get_resolver_logs(start_time: Optional[str] = None, end_time: Optional[str] = None):
    """Retrieve resolver log with optional time-range filter."""
    return await persistence.get_resolver_logs(start_time, end_time)

# --- Serve the dashboard at root ---
#  1. Route for Orbital Ops Map Dashboard (Served at the root URL)

def resource_path(relative_path):
    return os.path.join(base_path, relative_path)

@app.get("/", response_class=FileResponse)
async def serve_map_dashboard():
    """Serves the new orbital map and scheduler tracking screen."""
    file_path = resource_path(os.path.join("static", "dashboard.html"))
    return FileResponse(file_path)

# 2. Route for Telemetry Dashboard (Served at /telemetry)
@app.get("/telemetry", response_class=FileResponse)
async def serve_telemetry_dashboard():
    """Serves your NASA/ESA styled telemetry and alarm monitoring screen."""
    # Replace "index.html" with the exact name of your Project 1 HTML file!
    file_path = resource_path(os.path.join("static", "index.html"))  # ✅
    return FileResponse(file_path)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
