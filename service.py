"""
Windows Service wrapper for SNMP Monitor.

Usage (run as Administrator):
  python service.py install   -- install the service
  python service.py start     -- start it
  python service.py stop      -- stop it
  python service.py remove    -- uninstall it
  python service.py debug     -- run in foreground (for testing)
"""

import sys
import os
import logging

# Make sure the app directory is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import win32serviceutil
import win32service
import win32event
import servicemanager

import app as flask_app
from config import HOST, PORT

log = logging.getLogger("snmp-monitor-service")


class SNMPMonitorService(win32serviceutil.ServiceFramework):
    _svc_name_        = "SNMPMonitor"
    _svc_display_name_= "SNMP Network Monitor"
    _svc_description_ = "SNMP-based server and network monitoring with web dashboard"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self._server = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        import scheduler
        scheduler.stop()
        if self._server:
            self._server.shutdown()

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        self._run()

    def _run(self):
        from werkzeug.serving import make_server
        import threading

        flask_app.create_app()

        self._server = make_server(HOST, PORT, flask_app.app)
        log.info("SNMP Monitor service listening on %s:%s", HOST, PORT)

        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()

        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Called by SCM
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SNMPMonitorService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SNMPMonitorService)
