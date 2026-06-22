# GroundOps Console

A satellite operations backend.
Propagates real satellite orbits using SGP4, predicts contact windows over a
ground station, queues operational tasks against upcoming passes, and
auto-executes them during the pass window.

## Architecture

```
TLE Data
  │
  ▼
orbital.py (SGP4 propagation, TEME-to-geodetic, registry)
  │
  ├──▶ REST: /satellites, /satellites/{id}/position, /ground-track, /passes
  │
  ▼
scheduler.py (pass prediction, task queue, greedy first-fit scheduling)
  │
  ├──▶ REST: /scheduler/queue-task, /scheduler/passes, /scheduler/tasks
  │
  ▼
autopilot sequencer (executes tasks during pass window)
  │
  ▼
persistence.py (SQLite: telemetry_log, command_log, resolver_log)
  │
  ├──▶ REST: /logs/telemetry, /logs/commands, /logs/resolver
  │
  ▼
dashboard (Leaflet map, contact timeline, telemetry panel, log viewer)
  └──▶ GET /
```

## Data Flow

1. **SGP4 Propagation** - orbital.py loads TLEs into Satrec objects and
  propagates positions in the TEME frame, then converts to lat/lon/alt.
2. **Contact Windows** - scheduler.py steps forward in 30s increments over 24h,
  detecting AOS/LOS crossings when elevation > 0 degrees.
3. **Task Scheduling** - Greedy first-fit algorithm assigns queued tasks to
  available pass windows based on duration.
4. **Auto-Execution** - When a pass window opens, the autopilot sequencer
  fires all scheduled tasks in sequence via the procedure engine.
5. **Persistence** - Every telemetry reading, command execution, and resolver
  action is logged to SQLite for post-pass audit.

## Local Setup

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn main:app --reload
```

Visit [http://localhost:8000](http://localhost:8000) for the live dashboard.

## API Endpoints


| Endpoint                        | Method | Description                         |
| ------------------------------- | ------ | ----------------------------------- |
| `/`                             | GET    | Live dashboard (HTML)               |
| `/satellites`                   | GET    | List all tracked satellites         |
| `/satellites/{id}/position`     | GET    | Current lat/lon/alt                 |
| `/satellites/{id}/ground-track` | GET    | Next 90 min positions               |
| `/satellites/{id}/passes`       | GET    | Next 24h passes over ground station |
| `/scheduler/queue-task`         | POST   | Queue a task for a satellite        |
| `/scheduler/passes`             | GET    | Upcoming passes with queued tasks   |
| `/scheduler/tasks`              | GET    | All tasks with status               |
| `/logs/telemetry`               | GET    | Telemetry log (filterable)          |
| `/logs/commands`                | GET    | Command execution log               |
| `/logs/resolver`                | GET    | Resolver action log                 |


## Deployment

Deployed on Render (free tier). The render.yaml Blueprint defines the service.
SQLite database is ephemeral on Render free tier and resets on redeploy.

## Tech Stack

- **Python 3.10+** with FastAPI and Uvicorn
- **sgp4** for orbital propagation (C++ accelerated backend)
- **aiosqlite** for async database operations
- **Leaflet.js** for the interactive map
- **Render** for cloud hosting

