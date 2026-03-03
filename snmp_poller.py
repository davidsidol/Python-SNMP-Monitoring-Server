"""
SNMP polling engine using pysnmp 7.x asyncio API.
Provides synchronous wrappers for use in threaded contexts.
"""

import asyncio
import logging
import sys

from pysnmp.hlapi.v3arch.asyncio import (
    get_cmd, next_cmd, walk_cmd,
    CommunityData, UdpTransportTarget,
    ContextData, ObjectType, ObjectIdentity,
    SnmpEngine,
)

log = logging.getLogger(__name__)


def _get_or_create_loop():
    """Return a usable event loop (works in threads without an existing loop)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
        return loop
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def _community(community, version):
    mp = 1 if version == "v2c" else 0
    return CommunityData(community, mpModel=mp)


async def _async_get(host, port, community, version, oid, timeout, retries):
    engine = SnmpEngine()
    try:
        err_ind, err_stat, err_idx, var_binds = await get_cmd(
            engine,
            _community(community, version),
            await UdpTransportTarget.create((host, port), timeout=timeout, retries=retries),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )
        if err_ind or err_stat:
            return None, None
        for vb in var_binds:
            return vb[1].prettyPrint(), type(vb[1]).__name__
        return None, None
    except Exception as exc:
        log.debug("SNMP GET %s %s: %s", host, oid, exc)
        return None, None


async def _async_walk(host, port, community, version, oid, timeout, retries):
    engine = SnmpEngine()
    results = []
    try:
        async for err_ind, err_stat, err_idx, var_binds in walk_cmd(
            engine,
            _community(community, version),
            await UdpTransportTarget.create((host, port), timeout=timeout, retries=retries),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lexicographicMode=False,
        ):
            if err_ind or err_stat:
                break
            for vb in var_binds:
                results.append((str(vb[0]), vb[1].prettyPrint()))
    except Exception as exc:
        log.debug("SNMP WALK %s %s: %s", host, oid, exc)
    return results


def snmp_get(host, port, community, version, oid, timeout=3, retries=1):
    loop = _get_or_create_loop()
    return loop.run_until_complete(
        _async_get(host, port, community, version, oid, timeout, retries)
    )


def snmp_walk(host, port, community, version, oid, timeout=3, retries=1):
    loop = _get_or_create_loop()
    return loop.run_until_complete(
        _async_walk(host, port, community, version, oid, timeout, retries)
    )


# -----------------------------------------------------------------------

def poll_device(device: dict) -> dict:
    host      = device["host"]
    port      = int(device.get("port", 161))
    community = device.get("community", "public")
    version   = device.get("version", "v2c")

    result = {
        "status": "down", "sys_descr": None, "sys_name": None,
        "cpu_pct": None, "mem_pct": None, "disk_pct": None,
        "uptime_secs": None, "if_in_bps": None, "if_out_bps": None, "error": None,
    }

    # Reachability
    descr, _ = snmp_get(host, port, community, version, "1.3.6.1.2.1.1.1.0")
    if descr is None:
        result["error"] = "SNMP timeout / unreachable"
        return result

    result["status"]   = "up"
    result["sys_descr"] = (descr[:255] if descr else None)

    sys_name, _ = snmp_get(host, port, community, version, "1.3.6.1.2.1.1.5.0")
    result["sys_name"] = sys_name

    uptime_raw, _ = snmp_get(host, port, community, version, "1.3.6.1.2.1.1.3.0")
    if uptime_raw:
        try:
            result["uptime_secs"] = int(uptime_raw) // 100
        except (ValueError, TypeError):
            pass

    # CPU — HOST-RESOURCES-MIB hrProcessorLoad
    cpu_rows = snmp_walk(host, port, community, version, "1.3.6.1.2.1.25.3.3.1.2")
    if cpu_rows:
        try:
            loads = [float(v) for _, v in cpu_rows if v.lstrip('-').isdigit()]
            if loads:
                result["cpu_pct"] = round(sum(loads) / len(loads), 1)
        except Exception:
            pass

    # Storage
    _parse_storage(host, port, community, version, result)

    # Network interfaces
    _parse_interfaces(host, port, community, version, result)

    return result


def _parse_storage(host, port, community, version, result):
    descr_rows = snmp_walk(host, port, community, version, "1.3.6.1.2.1.25.2.3.1.3")
    unit_rows  = snmp_walk(host, port, community, version, "1.3.6.1.2.1.25.2.3.1.4")
    size_rows  = snmp_walk(host, port, community, version, "1.3.6.1.2.1.25.2.3.1.5")
    used_rows  = snmp_walk(host, port, community, version, "1.3.6.1.2.1.25.2.3.1.6")

    def idx(rows):
        return {r[0].rsplit(".", 1)[-1]: r[1] for r in rows}

    descr_map = idx(descr_rows)
    unit_map  = idx(unit_rows)
    size_map  = idx(size_rows)
    used_map  = idx(used_rows)

    ram_pct_vals, disk_pct_vals = [], []
    for i, descr in descr_map.items():
        try:
            unit  = int(unit_map.get(i, 0))
            total = int(size_map.get(i, 0))
            used  = int(used_map.get(i, 0))
            if total == 0 or unit == 0:
                continue
            pct = round(used / total * 100, 1)
            dl  = descr.lower()
            if "ram" in dl or "physical memory" in dl or "real memory" in dl:
                ram_pct_vals.append(pct)
            elif "virtual memory" not in dl and (
                    "disk" in dl or "storage" in dl or "volume" in dl or "fixed" in dl):
                disk_pct_vals.append(pct)
        except Exception:
            continue

    if ram_pct_vals:
        result["mem_pct"]  = round(sum(ram_pct_vals)  / len(ram_pct_vals),  1)
    if disk_pct_vals:
        result["disk_pct"] = round(sum(disk_pct_vals) / len(disk_pct_vals), 1)


def _parse_interfaces(host, port, community, version, result):
    in_rows  = snmp_walk(host, port, community, version, "1.3.6.1.2.1.2.2.1.10")
    out_rows = snmp_walk(host, port, community, version, "1.3.6.1.2.1.2.2.1.16")

    def total(rows):
        s = 0
        for _, v in rows:
            try:
                s += int(v)
            except (ValueError, TypeError):
                pass
        return s

    result["if_in_bps"]  = total(in_rows)
    result["if_out_bps"] = total(out_rows)
