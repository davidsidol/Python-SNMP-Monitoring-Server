"""
Database layer — SQLite via built-in sqlite3.
"""

import sqlite3
import time
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                host        TEXT NOT NULL,
                port        INTEGER NOT NULL DEFAULT 161,
                community   TEXT NOT NULL DEFAULT 'public',
                version     TEXT NOT NULL DEFAULT 'v2c',
                enabled     INTEGER NOT NULL DEFAULT 1,
                created_at  INTEGER NOT NULL,
                last_seen   INTEGER,
                sys_descr   TEXT,
                sys_name    TEXT,
                status      TEXT DEFAULT 'unknown'
            );

            CREATE TABLE IF NOT EXISTS metrics (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id   INTEGER NOT NULL,
                ts          INTEGER NOT NULL,
                cpu_pct     REAL,
                mem_pct     REAL,
                disk_pct    REAL,
                uptime_secs INTEGER,
                if_in_bps   REAL,
                if_out_bps  REAL,
                FOREIGN KEY(device_id) REFERENCES devices(id)
            );

            CREATE INDEX IF NOT EXISTS idx_metrics_device_ts
                ON metrics(device_id, ts DESC);

            CREATE TABLE IF NOT EXISTS local_metrics (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          INTEGER NOT NULL,
                cpu_pct     REAL,
                mem_pct     REAL,
                disk_pct    REAL,
                net_in_bps  REAL,
                net_out_bps REAL,
                mem_total_mb REAL,
                mem_used_mb  REAL,
                disk_total_gb REAL,
                disk_used_gb  REAL
            );

            CREATE INDEX IF NOT EXISTS idx_local_metrics_ts
                ON local_metrics(ts DESC);

            CREATE TABLE IF NOT EXISTS alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          INTEGER NOT NULL,
                device_id   INTEGER,
                source      TEXT NOT NULL,
                severity    TEXT NOT NULL,
                message     TEXT NOT NULL,
                acknowledged INTEGER DEFAULT 0
            );
        """)


# ---------- Devices ----------

def add_device(name, host, port, community, version):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO devices (name, host, port, community, version, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (name, host, int(port), community, version, int(time.time()))
        )
        return cur.lastrowid


def get_devices(enabled_only=True):
    with get_conn() as conn:
        if enabled_only:
            rows = conn.execute(
                "SELECT * FROM devices WHERE enabled=1 ORDER BY name"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM devices ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_device(device_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()
    return dict(row) if row else None


def update_device_status(device_id, status, sys_descr=None, sys_name=None):
    with get_conn() as conn:
        conn.execute(
            "UPDATE devices SET status=?, last_seen=?, sys_descr=COALESCE(?,sys_descr), "
            "sys_name=COALESCE(?,sys_name) WHERE id=?",
            (status, int(time.time()), sys_descr, sys_name, device_id)
        )


def delete_device(device_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM metrics WHERE device_id=?", (device_id,))
        conn.execute("DELETE FROM devices WHERE id=?", (device_id,))


# ---------- Metrics ----------

def save_metric(device_id, cpu_pct=None, mem_pct=None, disk_pct=None,
                uptime_secs=None, if_in_bps=None, if_out_bps=None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO metrics (device_id,ts,cpu_pct,mem_pct,disk_pct,"
            "uptime_secs,if_in_bps,if_out_bps) VALUES (?,?,?,?,?,?,?,?)",
            (device_id, int(time.time()), cpu_pct, mem_pct, disk_pct,
             uptime_secs, if_in_bps, if_out_bps)
        )


def get_metrics(device_id, hours=24):
    cutoff = int(time.time()) - hours * 3600
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM metrics WHERE device_id=? AND ts>=? ORDER BY ts",
            (device_id, cutoff)
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_metric(device_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM metrics WHERE device_id=? ORDER BY ts DESC LIMIT 1",
            (device_id,)
        ).fetchone()
    return dict(row) if row else None


# ---------- Local metrics ----------

def save_local_metric(cpu_pct, mem_pct, disk_pct, net_in_bps, net_out_bps,
                      mem_total_mb, mem_used_mb, disk_total_gb, disk_used_gb):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO local_metrics (ts,cpu_pct,mem_pct,disk_pct,"
            "net_in_bps,net_out_bps,mem_total_mb,mem_used_mb,"
            "disk_total_gb,disk_used_gb) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (int(time.time()), cpu_pct, mem_pct, disk_pct, net_in_bps,
             net_out_bps, mem_total_mb, mem_used_mb, disk_total_gb, disk_used_gb)
        )


def get_local_metrics(hours=24):
    cutoff = int(time.time()) - hours * 3600
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM local_metrics WHERE ts>=? ORDER BY ts",
            (cutoff,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_latest_local_metric():
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM local_metrics ORDER BY ts DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


# ---------- Alerts ----------

def add_alert(source, severity, message, device_id=None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO alerts (ts, device_id, source, severity, message) "
            "VALUES (?,?,?,?,?)",
            (int(time.time()), device_id, source, severity, message)
        )


def get_alerts(limit=100, unacked_only=False):
    with get_conn() as conn:
        if unacked_only:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE acknowledged=0 ORDER BY ts DESC LIMIT ?",
                (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def ack_alert(alert_id):
    with get_conn() as conn:
        conn.execute("UPDATE alerts SET acknowledged=1 WHERE id=?", (alert_id,))


def prune_old_data(days=30):
    """Remove records older than `days` days to keep the DB tidy."""
    cutoff = int(time.time()) - days * 86400
    with get_conn() as conn:
        conn.execute("DELETE FROM metrics WHERE ts<?", (cutoff,))
        conn.execute("DELETE FROM local_metrics WHERE ts<?", (cutoff,))
        conn.execute("DELETE FROM alerts WHERE ts<? AND acknowledged=1", (cutoff,))
