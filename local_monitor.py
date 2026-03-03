"""
Local host monitoring via psutil.
Collects CPU, memory, disk, and network stats from the machine running the app.
"""

import time
import psutil
import logging

log = logging.getLogger(__name__)

_prev_net = None
_prev_net_ts = None


def collect_local_metrics() -> dict:
    """
    Return a dict with current local system metrics.
    Keys: cpu_pct, mem_pct, disk_pct, net_in_bps, net_out_bps,
          mem_total_mb, mem_used_mb, disk_total_gb, disk_used_gb,
          cpu_count, load_avg (Windows: None)
    """
    global _prev_net, _prev_net_ts

    # CPU (non-blocking, uses cached interval)
    cpu_pct = psutil.cpu_percent(interval=1)

    # Memory
    mem = psutil.virtual_memory()
    mem_total_mb = round(mem.total / 1024 / 1024, 1)
    mem_used_mb  = round(mem.used  / 1024 / 1024, 1)
    mem_pct      = mem.percent

    # Disk (root partition)
    try:
        disk = psutil.disk_usage("/")
        disk_total_gb = round(disk.total / 1024 ** 3, 2)
        disk_used_gb  = round(disk.used  / 1024 ** 3, 2)
        disk_pct      = disk.percent
    except Exception:
        disk_total_gb = disk_used_gb = disk_pct = None

    # Network throughput (bytes/sec since last call)
    now  = time.time()
    net  = psutil.net_io_counters()
    if _prev_net is not None and _prev_net_ts is not None:
        elapsed = now - _prev_net_ts
        if elapsed > 0:
            net_in_bps  = round((net.bytes_recv - _prev_net.bytes_recv) / elapsed, 1)
            net_out_bps = round((net.bytes_sent - _prev_net.bytes_sent) / elapsed, 1)
        else:
            net_in_bps = net_out_bps = 0.0
    else:
        net_in_bps = net_out_bps = 0.0

    _prev_net    = net
    _prev_net_ts = now

    # CPU count and load
    cpu_count = psutil.cpu_count(logical=True)
    try:
        load_avg = psutil.getloadavg()
    except AttributeError:
        load_avg = None

    return {
        "cpu_pct":       round(cpu_pct, 1),
        "mem_pct":       round(mem_pct, 1),
        "disk_pct":      round(disk_pct, 1) if disk_pct is not None else None,
        "net_in_bps":    max(0.0, net_in_bps),
        "net_out_bps":   max(0.0, net_out_bps),
        "mem_total_mb":  mem_total_mb,
        "mem_used_mb":   mem_used_mb,
        "disk_total_gb": disk_total_gb,
        "disk_used_gb":  disk_used_gb,
        "cpu_count":     cpu_count,
        "load_avg":      load_avg,
    }


def top_processes(n=10):
    """Return top N processes by CPU usage."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent",
                                  "status", "username"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    # Sort by CPU then memory
    procs.sort(key=lambda x: (x.get("cpu_percent") or 0,
                               x.get("memory_percent") or 0), reverse=True)
    return procs[:n]


def disk_partitions():
    """Return stats for all mounted disk partitions."""
    result = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            result.append({
                "device":      part.device,
                "mountpoint":  part.mountpoint,
                "fstype":      part.fstype,
                "total_gb":    round(usage.total / 1024 ** 3, 2),
                "used_gb":     round(usage.used  / 1024 ** 3, 2),
                "free_gb":     round(usage.free  / 1024 ** 3, 2),
                "percent":     usage.percent,
            })
        except (PermissionError, OSError):
            pass
    return result


def network_interfaces():
    """Return per-interface stats."""
    stats   = psutil.net_if_stats()
    addrs   = psutil.net_if_addrs()
    io      = psutil.net_io_counters(pernic=True)
    result  = []
    for name, stat in stats.items():
        iface = {
            "name":     name,
            "is_up":    stat.isup,
            "speed":    stat.speed,
            "mtu":      stat.mtu,
            "addrs":    [],
            "bytes_sent":   0,
            "bytes_recv":   0,
            "packets_sent": 0,
            "packets_recv": 0,
            "errin":  0,
            "errout": 0,
        }
        for addr in addrs.get(name, []):
            iface["addrs"].append({"family": str(addr.family), "address": addr.address})
        if name in io:
            c = io[name]
            iface.update({
                "bytes_sent":   c.bytes_sent,
                "bytes_recv":   c.bytes_recv,
                "packets_sent": c.packets_sent,
                "packets_recv": c.packets_recv,
                "errin":  c.errin,
                "errout": c.errout,
            })
        result.append(iface)
    return result
