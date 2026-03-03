# Python SNMP Monitoring Server

A self-hosted server and network monitoring application built with Python. It combines SNMP polling for remote devices with real-time local host metrics, all presented through a dark-themed web dashboard with live charts and alerting.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Flask](https://img.shields.io/badge/Flask-3.1-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Features

- **Local host monitoring** — CPU, memory, disk, and network throughput via `psutil`
- **SNMP device polling** — Query any SNMPv1/v2c-capable device (routers, switches, servers, NAS)
- **24-hour history charts** — Trend graphs for CPU, memory, disk, and network
- **Alerting** — Threshold-based alerts with acknowledge support
- **Process table** — Live top-process view with CPU and memory usage
- **Disk partitions** — Usage bars for every mounted volume
- **Network interfaces** — Per-interface stats and IP addresses
- **Auto-refresh** — Dashboard updates every 30 seconds; background polling every 60 seconds
- **Windows Service** — Runs as a persistent background service via `pywin32`
- **SQLite storage** — No external database required; 30-day automatic data retention

---

## Screenshots

| Local Host Dashboard | SNMP Devices | Alerts |
|---|---|---|
| CPU / RAM / Disk gauges, history charts, top processes | Per-device cards with live metrics, on-demand poll | Severity-tagged alert list with acknowledge |

---

## Requirements

- Python 3.10 or later
- Windows (for the Windows Service feature — the app itself runs on any OS)
- SNMP enabled on any devices you want to monitor

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/davidsidol/Python-SNMP-Monitoring-Server.git
cd Python-SNMP-Monitoring-Server
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. (Windows) Enable the local SNMP service

Open **Services** → **SNMP Service** → Properties, then:

- Under **Security**, add community name `public` with **READ ONLY** access
- Under **Security**, add `localhost` and `127.0.0.1` to **Accepted hosts**
- Restart the SNMP service

Or run the following in an elevated PowerShell:

```powershell
python -c "
import winreg
key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
    r'SYSTEM\CurrentControlSet\Services\SNMP\Parameters\ValidCommunities',
    0, winreg.KEY_SET_VALUE)
winreg.SetValueEx(key, 'public', 0, winreg.REG_DWORD, 4)
winreg.CloseKey(key)
"
net stop SNMP && net start SNMP
```

---

## Running

### Development (foreground)

```bash
python app.py
```

Then open **http://localhost:5000** in your browser.

### Production (Windows Service)

Run the following commands from an **elevated (Administrator) terminal**:

```bash
# Install
python service.py install

# Start
python service.py start

# Stop
python service.py stop

# Uninstall
python service.py remove
```

The service is named **SNMPMonitor** and will start automatically with Windows.

---

## Configuration

All settings live in `config.py`:

```python
# Web server
HOST = "0.0.0.0"   # Listen on all interfaces
PORT = 5000

# How often to poll devices (seconds)
POLL_INTERVAL = 60

# Alert thresholds (%)
ALERT_CPU_THRESHOLD  = 85
ALERT_MEM_THRESHOLD  = 90
ALERT_DISK_THRESHOLD = 90

# Pre-configured devices (can also be added via the web UI)
INITIAL_DEVICES = [
    {
        "name":      "Localhost",
        "host":      "127.0.0.1",
        "port":      161,
        "community": "public",
        "version":   "v2c",
    }
]
```

---

## Adding Devices

Devices can be added two ways:

**Via the web UI** — Go to the **SNMP Devices** tab and click **Add Device**. Fill in the device name, IP address, SNMP port (default 161), community string, and SNMP version.

**Via `config.py`** — Add entries to the `INITIAL_DEVICES` list before first run. These are seeded into the database automatically on startup.

---

## SNMP OIDs Queried

| Metric | OID |
|---|---|
| System description | `1.3.6.1.2.1.1.1.0` |
| System name | `1.3.6.1.2.1.1.5.0` |
| System uptime | `1.3.6.1.2.1.1.3.0` |
| CPU load (per core) | `1.3.6.1.2.1.25.3.3.1.2` |
| Storage descriptors | `1.3.6.1.2.1.25.2.3.1.3` |
| Storage size / used | `1.3.6.1.2.1.25.2.3.1.5-6` |
| Interface in octets | `1.3.6.1.2.1.2.2.1.10` |
| Interface out octets | `1.3.6.1.2.1.2.2.1.16` |

These are standard MIB-II / HOST-RESOURCES-MIB OIDs supported by most network devices and Windows/Linux SNMP agents.

---

## REST API

The dashboard is backed by a JSON API you can query directly:

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/summary` | Overall status summary |
| GET | `/api/local/current` | Live local host metrics |
| GET | `/api/local/history?hours=24` | Local metrics history |
| GET | `/api/local/processes` | Top processes by CPU |
| GET | `/api/local/disks` | Disk partition usage |
| GET | `/api/local/interfaces` | Network interface stats |
| GET | `/api/devices` | All configured SNMP devices |
| POST | `/api/devices` | Add a new device |
| DELETE | `/api/devices/<id>` | Remove a device |
| GET | `/api/devices/<id>/metrics?hours=24` | Device metric history |
| POST | `/api/devices/<id>/poll` | Trigger an immediate poll |
| GET | `/api/alerts` | Alert list |
| POST | `/api/alerts/<id>/ack` | Acknowledge an alert |
| POST | `/api/alerts/ack-all` | Acknowledge all alerts |
| GET | `/health` | Health check |

---

## Project Structure

```
.
├── app.py              # Flask application and REST API routes
├── snmp_poller.py      # SNMP polling engine (pysnmp 7.x asyncio)
├── local_monitor.py    # Local host metrics via psutil
├── scheduler.py        # APScheduler background polling loop
├── db.py               # SQLite database layer
├── config.py           # All configuration settings
├── service.py          # Windows Service wrapper (pywin32)
├── requirements.txt    # Python dependencies
├── templates/
│   └── index.html      # Single-page web dashboard
└── .claude/
    └── launch.json     # Dev server launch configuration
```

---

## Tech Stack

| Component | Library |
|---|---|
| Web framework | [Flask](https://flask.palletsprojects.com/) 3.1 |
| SNMP | [pysnmp](https://github.com/lextudio/pysnmp) 7.x (asyncio) |
| System metrics | [psutil](https://github.com/giampaolo/psutil) |
| Job scheduler | [APScheduler](https://apscheduler.readthedocs.io/) 3.x |
| Windows Service | [pywin32](https://github.com/mhammond/pywin32) |
| Database | SQLite (built-in) |
| Frontend charts | [Chart.js](https://www.chartjs.org/) 4.x |
| UI framework | [Bootstrap](https://getbootstrap.com/) 5.3 |

---

## License

MIT License. See [LICENSE](LICENSE) for details.
