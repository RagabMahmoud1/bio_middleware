import os
import subprocess
from pathlib import Path

import servicemanager
import win32event
import win32service
import win32serviceutil


BASE_DIR = Path(__file__).resolve().parent.parent
SERVICE_NAME = "RaidatBiometricConnector"


class RaidatBiometricService(win32serviceutil.ServiceFramework):
    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = "Raidat Biometric Connector"
    _svc_description_ = (
        "Collects biometric events, keeps a durable local queue, "
        "and synchronizes attendance events to Odoo."
    )

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.process = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        self._stop_child()

    def _stop_child(self):
        if not self.process or self.process.poll() is not None:
            return
        try:
            self.process.terminate()
            self.process.wait(timeout=20)
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass

    def SvcDoRun(self):
        servicemanager.LogInfoMsg(
            f"{SERVICE_NAME} starting from {BASE_DIR}"
        )
        os.chdir(BASE_DIR)

        python_exe = BASE_DIR / ".venv" / "Scripts" / "python.exe"
        if not python_exe.exists():
            raise RuntimeError(f"Python virtualenv not found: {python_exe}")

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            [str(python_exe), "-m", "app.main"],
            cwd=str(BASE_DIR),
            creationflags=creation_flags,
        )

        try:
            while True:
                rc = win32event.WaitForSingleObject(
                    self.stop_event,
                    5000,
                )
                if rc == win32event.WAIT_OBJECT_0:
                    break

                child_code = self.process.poll()
                if child_code is not None:
                    raise RuntimeError(
                        "Middleware child process stopped unexpectedly "
                        f"with exit code {child_code}"
                    )
        finally:
            self._stop_child()
            servicemanager.LogInfoMsg(f"{SERVICE_NAME} stopped")


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(RaidatBiometricService)
