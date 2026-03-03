"""
SNMP Monitor — Flask web application entry point.
Run directly:  python app.py
Service mode:  python service.py install / start
"""

import logging
import time
import os
from flask import Flask, render_template, jsonify, request, abort

import db
import scheduler
import local_monitor
from config import HOST, PORT, SECRET_KEY

# ---- Logging ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---- Flask app ----
app = Flask(__name__)
app.secret_key = SECRET_KEY


# ============================================================
#  HTML pages
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
#  REST API — Local host
# ============================================================

@app.route("/api/local/current")
def api_local_current():
    m = local_monitor.collect_local_metrics()
    return jsonify(m)


@app.route("/api/local/history")
def api_local_history():
    hours = int(request.args.get("hours", 24))
    rows  = db.get_local_metrics(hours=min(hours, 168))
    return jsonify(rows)


@app.route("/api/local/processes")
def api_local_processes():
    return jsonify(local_monitor.top_processes(20))


@app.route("/api/local/disks")
def api_local_disks():
    return jsonify(local_monitor.disk_partitions())


@app.route("/api/local/interfaces")
def api_local_interfaces():
    return jsonify(local_monitor.network_interfaces())


# ============================================================
#  REST API — Devices
# ============================================================

@app.route("/api/devices", methods=["GET"])
def api_devices():
    devices  = db.get_devices(enabled_only=False)
    enriched = []
    for dev in devices:
        latest = db.get_latest_metric(dev["id"])
        dev["latest"] = latest
        enriched.append(dev)
    return jsonify(enriched)


@app.route("/api/devices", methods=["POST"])
def api_add_device():
    data = request.get_json(force=True)
    required = ("name", "host")
    if not all(k in data for k in required):
        abort(400, description="name and host are required")
    try:
        dev_id = db.add_device(
            name=data["name"],
            host=data["host"],
            port=int(data.get("port", 161)),
            community=data.get("community", "public"),
            version=data.get("version", "v2c"),
        )
        return jsonify({"id": dev_id}), 201
    except Exception as exc:
        abort(500, description=str(exc))


@app.route("/api/devices/<int:device_id>", methods=["DELETE"])
def api_delete_device(device_id):
    db.delete_device(device_id)
    return jsonify({"ok": True})


@app.route("/api/devices/<int:device_id>/metrics")
def api_device_metrics(device_id):
    hours = int(request.args.get("hours", 24))
    rows  = db.get_metrics(device_id, hours=min(hours, 168))
    return jsonify(rows)


@app.route("/api/devices/<int:device_id>/poll", methods=["POST"])
def api_poll_now(device_id):
    """Trigger an immediate on-demand poll for a device."""
    import snmp_poller
    dev = db.get_device(device_id)
    if not dev:
        abort(404)
    result = snmp_poller.poll_device(dev)
    db.update_device_status(device_id, result["status"],
                            sys_descr=result.get("sys_descr"),
                            sys_name=result.get("sys_name"))
    if result["status"] == "up":
        db.save_metric(
            device_id=device_id,
            cpu_pct=result.get("cpu_pct"),
            mem_pct=result.get("mem_pct"),
            disk_pct=result.get("disk_pct"),
            uptime_secs=result.get("uptime_secs"),
            if_in_bps=result.get("if_in_bps"),
            if_out_bps=result.get("if_out_bps"),
        )
    return jsonify(result)


# ============================================================
#  REST API — Alerts
# ============================================================

@app.route("/api/alerts")
def api_alerts():
    unacked = request.args.get("unacked", "false").lower() == "true"
    rows    = db.get_alerts(limit=200, unacked_only=unacked)
    return jsonify(rows)


@app.route("/api/alerts/<int:alert_id>/ack", methods=["POST"])
def api_ack_alert(alert_id):
    db.ack_alert(alert_id)
    return jsonify({"ok": True})


@app.route("/api/alerts/ack-all", methods=["POST"])
def api_ack_all():
    alerts = db.get_alerts(limit=10000, unacked_only=True)
    for a in alerts:
        db.ack_alert(a["id"])
    return jsonify({"acked": len(alerts)})


# ============================================================
#  REST API — Summary / health
# ============================================================

@app.route("/api/summary")
def api_summary():
    devices     = db.get_devices(enabled_only=False)
    up_count    = sum(1 for d in devices if d.get("status") == "up")
    down_count  = sum(1 for d in devices if d.get("status") == "down")
    unack_alerts= len(db.get_alerts(limit=10000, unacked_only=True))
    local_last  = db.get_latest_local_metric()
    return jsonify({
        "total_devices":   len(devices),
        "up_devices":      up_count,
        "down_devices":    down_count,
        "unack_alerts":    unack_alerts,
        "local":           local_last,
        "server_time":     int(time.time()),
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok", "ts": int(time.time())})


# ============================================================
#  App startup
# ============================================================

def create_app():
    db.init_db()
    scheduler.seed_initial_devices()
    scheduler.start()
    return app


if __name__ == "__main__":
    create_app()
    log.info("Starting SNMP Monitor on http://%s:%s", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
