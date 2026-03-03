"""
Configuration for SNMP Monitor
Edit this file to add monitored devices and adjust settings.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Web server
HOST = "0.0.0.0"
PORT = 5000
SECRET_KEY = "snmp-monitor-secret-change-me"

# Database
DB_PATH = os.path.join(BASE_DIR, "monitor.db")

# Polling interval in seconds
POLL_INTERVAL = 60

# Local host SNMP (Windows SNMP service)
LOCAL_SNMP_HOST = "127.0.0.1"
LOCAL_SNMP_PORT = 161
LOCAL_SNMP_COMMUNITY = "public"

# Alert thresholds (%)
ALERT_CPU_THRESHOLD = 85
ALERT_MEM_THRESHOLD = 90
ALERT_DISK_THRESHOLD = 90

# Initial devices to monitor (can also be added via the web UI)
# Format: {"name": str, "host": str, "port": int, "community": str, "version": "v1"|"v2c"}
INITIAL_DEVICES = [
    {
        "name": "Localhost",
        "host": "127.0.0.1",
        "port": 161,
        "community": "public",
        "version": "v2c",
    }
]

# Standard SNMP OIDs (RFC 1213 / MIB-II)
OID_SYS_DESCR    = "1.3.6.1.2.1.1.1.0"
OID_SYS_NAME     = "1.3.6.1.2.1.1.5.0"
OID_SYS_UPTIME   = "1.3.6.1.2.1.1.3.0"
OID_IF_TABLE     = "1.3.6.1.2.1.2.2"
OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
OID_IF_OUT_OCTETS= "1.3.6.1.2.1.2.2.1.16"

# Windows HOST-RESOURCES-MIB OIDs
OID_HR_PROCESSOR_LOAD = "1.3.6.1.2.1.25.3.3.1.2"
OID_HR_STORAGE_TABLE  = "1.3.6.1.2.1.25.2.3.1"
