"""Tests for the portal app-id registration (no D-Bus needed: the bus is faked).

Run:  python3 tests/test_portal_registry.py
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib
    from wayland_feather_shot import APP_ID
    from wayland_feather_shot import portal
    HAVE_GI = True
except (ImportError, ValueError):
    HAVE_GI = False


class FakeBus:
    """Records portal calls; raises *error* from every call when set."""

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def call_sync(self, bus, path, iface, method, params, reply, flags,
                  timeout, cancellable):
        self.calls.append((iface, method, params.unpack()))
        if self.error:
            raise GLib.Error(self.error)
        return None

    def get_unique_name(self):
        return ":1.42"


def fresh_bus_state():
    return patch.dict(portal._BUS, {"conn": None, "app_id_error": None})


@unittest.skipUnless(HAVE_GI, "PyGObject unavailable")
class RegisterAppIdTests(unittest.TestCase):
    def test_registers_the_app_id_with_the_host_registry(self):
        bus = FakeBus()
        self.assertIsNone(portal.register_app_id(bus, "org.example.App"))
        self.assertEqual(bus.calls, [
            (portal.IFACE_REGISTRY, "Register", ("org.example.App", {}))])

    def test_reports_the_portal_error_instead_of_raising(self):
        bus = FakeBus(error="App info not found for 'org.example.App'")
        self.assertIn("App info not found",
                      portal.register_app_id(bus, "org.example.App"))


@unittest.skipUnless(HAVE_GI, "PyGObject unavailable")
class PortalConnectionTests(unittest.TestCase):
    def test_registers_before_any_other_portal_call_and_only_once(self):
        bus = FakeBus()
        with fresh_bus_state(), patch.object(
                portal, "_new_private_connection", return_value=bus) as new:
            first = portal.Portal(registered=True)
            second = portal.Portal(registered=True)
        new.assert_called_once()
        self.assertIs(first.bus, bus)
        self.assertIs(second.bus, bus)
        self.assertEqual(bus.calls, [
            (portal.IFACE_REGISTRY, "Register", (APP_ID, {}))])
        self.assertEqual(first._sender_token, "1_42")

    def test_registration_failure_is_kept_for_diagnostics(self):
        bus = FakeBus(error="Could not register app ID: App info not found")
        with fresh_bus_state(), patch.object(
                portal, "_new_private_connection", return_value=bus):
            portal.Portal(registered=True)
            self.assertIn("App info not found", portal.app_id_error())

    def test_the_capture_path_stays_on_the_shared_bus_without_an_app_id(self):
        shared = FakeBus()
        with fresh_bus_state(), \
                patch.object(portal, "_new_private_connection") as private, \
                patch.object(portal.Gio, "bus_get_sync", return_value=shared):
            self.assertIs(portal.Portal().bus, shared)
        private.assert_not_called()
        self.assertEqual(shared.calls, [])

    def test_falls_back_to_the_shared_bus_when_a_private_one_fails(self):
        shared = FakeBus()
        with fresh_bus_state(), \
                patch.object(portal, "_new_private_connection",
                             side_effect=GLib.Error("no address")), \
                patch.object(portal.Gio, "bus_get_sync", return_value=shared):
            self.assertIs(portal.Portal(registered=True).bus, shared)


if __name__ == "__main__":
    unittest.main()
