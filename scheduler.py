"""
Background polling scheduler using APScheduler.
Polls all enabled devices and the local host on a configurable interval.
"""

import logging
import time
from apscheduler.schedulers.background import BackgroundScheduler

import db
import snmp_poller
import local_monitor
from config import (
    POLL_INTERVAL, INITIAL_DEVICES,
    ALERT_CPU_THRESHOLD, ALERT_MEM_THRESHOLD, ALERT_DISK_THRESHOLD
)

log = logging.getLogger(__name__)

_scheduler = None


def _check_thresholds(source, cpu, mem, disk, device_id=None):
    if cpu is not None and cpu >= ALERT_CPU_THRESHOLD:
        db.add_alert(source, "warning", f"CPU usage {cpu}% >= {ALERT_CPU_THRESHOLD}%",
                     device_id=device_id)
    if mem is not None and mem >= ALERT_MEM_THRESHOLD:
        db.add_alert(source, "critical", f"Memory usage {mem}% >= {ALERT_MEM_THRESHOLD}%",
                     device_id=device_id)
    if disk is not None and disk >= ALERT_DISK_THRESHOLD:
        db.add_alert(source, "warning", f"Disk usage {disk}% >= {ALERT_DISK_THRESHOLD}%",
                     device_id=device_id)


def _poll_local():
    """Collect local system metrics and save to DB."""
    try:
        m = local_monitor.collect_local_metrics()
        db.save_local_metric(
            cpu_pct=m["cpu_pct"],
            mem_pct=m["mem_pct"],
            disk_pct=m["disk_pct"],
            net_in_bps=m["net_in_bps"],
            net_out_bps=m["net_out_bps"],
            mem_total_mb=m["mem_total_mb"],
            mem_used_mb=m["mem_used_mb"],
            disk_total_gb=m["disk_total_gb"],
            disk_used_gb=m["disk_used_gb"],
        )
        _check_thresholds("localhost", m["cpu_pct"], m["mem_pct"], m["disk_pct"])
        log.debug("Local metrics: CPU=%.1f%% MEM=%.1f%% DISK=%.1f%%",
                  m["cpu_pct"], m["mem_pct"], m.get("disk_pct") or 0)
    except Exception as exc:
        log.error("Local poll error: %s", exc)


def _poll_snmp_devices():
    """Poll all enabled SNMP devices and save results to DB."""
    devices = db.get_devices(enabled_only=True)
    for dev in devices:
        try:
            result = snmp_poller.poll_device(dev)
            db.update_device_status(
                dev["id"],
                result["status"],
                sys_descr=result.get("sys_descr"),
                sys_name=result.get("sys_name"),
            )
            if result["status"] == "up":
                db.save_metric(
                    device_id=dev["id"],
                    cpu_pct=result.get("cpu_pct"),
                    mem_pct=result.get("mem_pct"),
                    disk_pct=result.get("disk_pct"),
                    uptime_secs=result.get("uptime_secs"),
                    if_in_bps=result.get("if_in_bps"),
                    if_out_bps=result.get("if_out_bps"),
                )
                _check_thresholds(
                    dev["name"],
                    result.get("cpu_pct"),
                    result.get("mem_pct"),
                    result.get("disk_pct"),
                    device_id=dev["id"],
                )
                log.info("Polled %s (%s): CPU=%s MEM=%s DISK=%s",
                         dev["name"], dev["host"],
                         result.get("cpu_pct"), result.get("mem_pct"),
                         result.get("disk_pct"))
            else:
                db.add_alert(dev["name"], "critical",
                             f"Device {dev['host']} is unreachable",
                             device_id=dev["id"])
                log.warning("Device %s (%s) is DOWN: %s",
                            dev["name"], dev["host"], result.get("error"))
        except Exception as exc:
            log.error("Error polling %s: %s", dev["name"], exc)


def _prune():
    try:
        db.prune_old_data(days=30)
    except Exception as exc:
        log.error("Prune error: %s", exc)


def seed_initial_devices():
    """Add INITIAL_DEVICES from config if they don't exist yet."""
    existing_hosts = {d["host"] for d in db.get_devices(enabled_only=False)}
    for dev in INITIAL_DEVICES:
        if dev["host"] not in existing_hosts:
            db.add_device(
                dev["name"], dev["host"], dev.get("port", 161),
                dev.get("community", "public"), dev.get("version", "v2c")
            )
            log.info("Added initial device: %s (%s)", dev["name"], dev["host"])


def start():
    global _scheduler
    if _scheduler is not None:
        return

    # Do one immediate local poll so the dashboard has data right away
    _poll_local()
    _poll_snmp_devices()

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_poll_local,        "interval", seconds=POLL_INTERVAL,
                       id="local_poll",   max_instances=1)
    _scheduler.add_job(_poll_snmp_devices, "interval", seconds=POLL_INTERVAL,
                       id="snmp_poll",    max_instances=1)
    _scheduler.add_job(_prune,             "interval", hours=6,
                       id="prune",        max_instances=1)
    _scheduler.start()
    log.info("Scheduler started (interval=%ds)", POLL_INTERVAL)


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
