import asyncio
import sqlite3
import aiosqlite
from datetime import datetime

DB_PATH = "mission_log.sqlite"
SNAPSHOT_PATH = "mission_log_snapshot.sqlite"

# Single persistent connection — opened once at startup, reused for all writes.
# Avoids the lock contention of opening a new connection every second.
_db: aiosqlite.Connection | None = None


async def init_db():
    """Open the persistent connection and create tables."""
    global _db
    _db = await aiosqlite.connect(DB_PATH)
    # DELETE journal (default): no -wal / -shm sidecar files ever created.
    await _db.execute("PRAGMA journal_mode=DELETE")
    await _db.execute("PRAGMA synchronous=NORMAL")

    await _db.execute("""
        CREATE TABLE IF NOT EXISTS telemetry_log (
            satellite_id TEXT NOT NULL,
            channel      TEXT NOT NULL,
            timestamp    TEXT NOT NULL,
            value        REAL NOT NULL,
            alarm_state  TEXT NOT NULL,
            PRIMARY KEY (satellite_id, channel)
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS command_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp      TEXT NOT NULL,
            satellite_id   TEXT NOT NULL,
            task_type      TEXT NOT NULL,
            procedure_name TEXT NOT NULL,
            outcome        TEXT NOT NULL
        )
    """)
    await _db.execute("""
        CREATE TABLE IF NOT EXISTS resolver_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            alert_condition TEXT NOT NULL,
            procedure_fired TEXT NOT NULL,
            result          TEXT NOT NULL
        )
    """)
    await _db.commit()


async def close_db():
    """Close the persistent connection cleanly on shutdown."""
    global _db
    if _db:
        await _db.close()
        _db = None


async def snapshot_loop(interval_seconds: int = 10):
    """Every N seconds, copy the live DB to a clean snapshot file.

    Open mission_log_snapshot.sqlite in your viewer — it is always a
    consistent, unlocked copy of the live data, never mid-write.
    This is the programmatic equivalent of the dump → rebuild you were
    doing manually, run automatically in the background.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            # sqlite3.Connection.backup() is atomic w.r.t. ongoing writes.
            src = sqlite3.connect(DB_PATH)
            dst = sqlite3.connect(SNAPSHOT_PATH)
            src.backup(dst)
            dst.close()
            src.close()
        except Exception as e:
            print(f"[DB] Snapshot failed: {e}")


# ── Write helpers ─────────────────────────────────────────────────────────────

async def log_telemetry(satellite_id, channel, value, alarm_state):
    await _db.execute(
        """INSERT OR REPLACE INTO telemetry_log
           (satellite_id, channel, timestamp, value, alarm_state)
           VALUES (?, ?, ?, ?, ?)""",
        (satellite_id, channel, datetime.utcnow().isoformat(), value, alarm_state),
    )
    await _db.commit()


async def log_command(satellite_id, task_type, procedure_name, outcome):
    await _db.execute(
        """INSERT INTO command_log
           (timestamp, satellite_id, task_type, procedure_name, outcome)
           VALUES (?, ?, ?, ?, ?)""",
        (datetime.utcnow().isoformat(), satellite_id, task_type, procedure_name, outcome),
    )
    await _db.commit()


async def log_resolver(alert_condition, procedure_fired, result):
    await _db.execute(
        """INSERT INTO resolver_log
           (timestamp, alert_condition, procedure_fired, result)
           VALUES (?, ?, ?, ?)""",
        (datetime.utcnow().isoformat(), alert_condition, procedure_fired, result),
    )
    await _db.commit()


# ── Read helpers ──────────────────────────────────────────────────────────────

def _build_query(table: str, start_time, end_time) -> tuple[str, list]:
    query = f"SELECT * FROM {table}"
    params, filters = [], []
    if start_time:
        filters.append("timestamp >= ?")
        params.append(start_time)
    if end_time:
        filters.append("timestamp <= ?")
        params.append(end_time)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY timestamp DESC"
    return query, params


async def get_telemetry_logs(start_time=None, end_time=None):
    _db.row_factory = aiosqlite.Row
    q, p = _build_query("telemetry_log", start_time, end_time)
    async with _db.execute(q, p) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_command_logs(start_time=None, end_time=None):
    _db.row_factory = aiosqlite.Row
    q, p = _build_query("command_log", start_time, end_time)
    async with _db.execute(q, p) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_resolver_logs(start_time=None, end_time=None):
    _db.row_factory = aiosqlite.Row
    q, p = _build_query("resolver_log", start_time, end_time)
    async with _db.execute(q, p) as cur:
        return [dict(r) for r in await cur.fetchall()]
