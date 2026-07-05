"""Runtime diagnostics for Wayland Feather Shot."""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass


@dataclass(slots=True)
class Check:
    name: str
    ok: bool
    detail: str


def module_exists(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def run_checks() -> list[Check]:
    checks: list[Check] = []
    checks.append(Check("Wayland session", os.environ.get("XDG_SESSION_TYPE") == "wayland", f"XDG_SESSION_TYPE={os.environ.get('XDG_SESSION_TYPE', '<unset>')}"))
    checks.append(Check("python gi", module_exists("gi"), "PyGObject module import"))
    checks.append(Check("Pillow", module_exists("PIL"), "PIL/Pillow module import"))
    checks.append(Check("pycairo", module_exists("cairo"), "cairo module import"))
    checks.append(Check("gdbus", shutil.which("gdbus") is not None, "optional CLI introspection helper"))

    if shutil.which("gdbus"):
        import subprocess
        try:
            proc = subprocess.run(
                [
                    "gdbus",
                    "introspect",
                    "--session",
                    "--dest",
                    "org.freedesktop.portal.Desktop",
                    "--object-path",
                    "/org/freedesktop/portal/desktop",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            stdout = proc.stdout
            stderr = proc.stderr.strip()
        except Exception as exc:
            stdout = ""
            stderr = str(exc)
        for iface in ["org.freedesktop.portal.Screenshot", "org.freedesktop.portal.GlobalShortcuts", "org.freedesktop.portal.ScreenCast"]:
            found = iface in stdout
            detail = "available" if found else (stderr or "not found in portal introspection")
            checks.append(Check(iface, found, detail))
    return checks


def print_diagnostics() -> int:
    checks = run_checks()
    for check in checks:
        mark = "OK" if check.ok else "NO"
        print(f"[{mark}] {check.name}: {check.detail}")
    return 0 if all(c.ok for c in checks[:4]) else 1
