import aiosqlite
from datetime import datetime

# Path to the SQLite database file
DB_PATH = "mission_log.sqlite"


async def init_db():
    """Create mission log tables if they don't exist with unique constraints."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Telemetry table now uniquely identifies records by satellite + channel
        await db.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_log (
                satellite_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                value REAL NOT NULL,
                alarm_state TEXT NOT NULL,
                PRIMARY KEY (satellite_id, channel)
            )
        """)
        # Keep other tables (command_log, resolver_log) as they are
        await db.execute("""
            CREATE TABLE IF NOT EXISTS command_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                satellite_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                procedure_name TEXT NOT NULL,
                outcome TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS resolver_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                alert_condition TEXT NOT NULL,
                procedure_fired TEXT NOT NULL,
                result TEXT NOT NULL
            )
        """)
        await db.commit()

async def log_telemetry(satellite_id, channel, value, alarm_state):
    """Write or overwrite a telemetry reading in the mission log."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO telemetry_log 
            (satellite_id, channel, timestamp, value, alarm_state) 
            VALUES (?, ?, ?, ?, ?)
        """, (satellite_id, channel, datetime.utcnow().isoformat(), value, alarm_state))
        await db.commit()


async def log_command(satellite_id, task_type, procedure_name, outcome):
    """Write a command execution record to the mission log."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO command_log (timestamp, satellite_id, task_type, procedure_name, outcome) VALUES (?, ?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), satellite_id, task_type, procedure_name, outcome)
        )
        await db.commit()

async def log_resolver(alert_condition, procedure_fired, result):
    """Write a resolver action record to the mission log."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO resolver_log (timestamp, alert_condition, procedure_fired, result) VALUES (?, ?, ?, ?)",
            (datetime.utcnow().isoformat(), alert_condition, procedure_fired, result)
        )
        await db.commit()

async def get_telemetry_logs(start_time=None, end_time=None):
    """Retrieve telemetry log entries with optional time-range filter."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM telemetry_log"
        params = []
        filters = []
        if start_time:
            filters.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            filters.append("timestamp <= ?")
            params.append(end_time)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY timestamp DESC"
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_command_logs(start_time=None, end_time=None):
    """Retrieve command log entries with optional time-range filter."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM command_log"
        params = []
        filters = []
        if start_time:
            filters.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            filters.append("timestamp <= ?")
            params.append(end_time)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY timestamp DESC"
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_resolver_logs(start_time=None, end_time=None):
    """Retrieve resolver log entries with optional time-range filter."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM resolver_log"
        params = []
        filters = []
        if start_time:
            filters.append("timestamp >= ?")
            params.append(start_time)
        if end_time:
            filters.append("timestamp <= ?")
            params.append(end_time)
        if filters:
            query += " WHERE " + " AND ".join(filters)
        query += " ORDER BY timestamp DESC"
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]