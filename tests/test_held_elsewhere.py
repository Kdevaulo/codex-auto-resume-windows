"""A conversation open in a terminal or VS Code waits with a reason of its own (v0.6.16-beta.4, the standard edition).

The app's queue reaches only a conversation the Codex app holds. One whose writer lock another Codex session holds -
a TUI the app's bundled engine runs in a terminal, or the VS Code extension's own server - read "unknown" until now,
and waited as if nothing could be told. `loaded()` now tells it apart from anything unknown, with the inventory rows
the app's pairing already read and the same Restart Manager look (B12, E1): one holder that is such a session is
"elsewhere", and the record waits `held_by_other_session` - WAIT, not UNKNOWN - and nothing is sent. Anything else
still fails closed: another install, two holders, a reused pid, and our own headless server (this process's child).
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_engine import T1, EngineCase  # noqa: E402
from codex_auto_resume import machine, windows as w  # noqa: E402
from codex_auto_resume.codex import pairing, transport  # noqa: E402

THREAD = "0a1b2c3d-0001-7000-8000-000000000001"
PROFILE = r"C:\Users\ExampleUser"
ENGINE = r"C:\Users\ExampleUser\AppData\Local\OpenAI\Codex\bin\0123abcd\codex.exe"
EXTENSION = PROFILE + r"\.vscode\extensions\openai.chatgpt-26.1.0-win32-x64\bin\windows-x86_64\codex.exe"
APP_MAIN = (r"C:\Program Files\WindowsApps\OpenAI.Codex_26.930.0.0_x64__2p2nqsd0c76g0\app\ChatGPT.exe")
APP = {"pid": 10, "created": 100, "path": APP_MAIN.lower(), "server": {"pid": 20, "created": 200, "path": ENGINE.lower()}}


def rows(*extra):
    """The inventory as the pairing read it: the app main, its server, and `extra`."""
    return [{"pid": 10, "parent": 1, "path": APP_MAIN}, {"pid": 20, "parent": 10, "path": ENGINE}, *extra]


class LoadedTests(unittest.TestCase):
    def setUp(self):
        self.backend = w.Backend(Path("state"), Path(ENGINE))
        for patcher in (patch.object(self.backend, "_compatible"),
                        patch.dict(os.environ, {"USERPROFILE": PROFILE, "ProgramW6432": r"C:\Program Files"})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def loaded(self, holders, inventory, identities=None):
        """loaded() with the inventory `inventory` read by the pairing and `holders` holding the writer lock;
        `identities` is what each pid's process says it is (its image and creation time), the rows' by default."""
        known = {row["pid"]: {"pid": row["pid"], "path": row["path"].lower(), "created": row["pid"] * 10}
                 for row in inventory}
        known.update(identities or {})

        def app_identity():
            self.backend._rows = list(inventory)
            return dict(APP)

        def identity(pid):
            if pid not in known:
                raise w.AdapterError("process_exited")
            return dict(known[pid])
        with patch.object(self.backend, "app_identity", side_effect=app_identity), \
                patch.object(transport, "resource_users", return_value=holders), \
                patch.object(pairing, "process_identity", side_effect=identity):
            return self.backend.loaded(THREAD, dict(APP))

    def test_the_apps_own_server_is_loaded(self):
        self.assertEqual(self.loaded([{"pid": 20, "created": 200}], rows()), "loaded")

    def test_a_tui_of_the_bundled_engine_not_run_by_the_app_is_elsewhere(self):
        """Fails with the classification reverted: it read "unknown"."""
        tui = {"pid": 30, "parent": 5, "path": ENGINE}
        self.assertEqual(self.loaded([{"pid": 30, "created": 300}], rows(tui)), "elsewhere")
        self.assertEqual(self.backend.session_holder, (30, 300), "who holds it, for the re-check (tosession.py)")
        self.assertEqual(self.loaded([], rows(tui)), "notLoaded")
        self.assertIsNone(self.backend.session_holder, "no stale holder after another answer")

    def test_the_vs_code_extensions_own_engine_is_elsewhere(self):
        ide = {"pid": 40, "parent": 6, "path": EXTENSION}
        self.assertEqual(self.loaded([{"pid": 40, "created": 400}], rows(ide)), "elsewhere")

    def test_another_install_of_codex_is_unknown(self):
        other = {"pid": 50, "parent": 7, "path": r"C:\Tools\codex\codex.exe"}
        self.assertEqual(self.loaded([{"pid": 50, "created": 500}], rows(other)), "unknown")

    def test_two_holders_are_unknown(self):
        tui = {"pid": 30, "parent": 5, "path": ENGINE}
        ide = {"pid": 40, "parent": 6, "path": EXTENSION}
        self.assertEqual(self.loaded([{"pid": 30, "created": 300}, {"pid": 40, "created": 400}], rows(tui, ide)),
                         "unknown")

    def test_a_reused_pid_is_unknown(self):
        tui = {"pid": 30, "parent": 5, "path": ENGINE}
        self.assertEqual(self.loaded([{"pid": 30, "created": 301}], rows(tui)), "unknown")

    def test_a_pid_now_another_image_is_unknown(self):
        tui = {"pid": 30, "parent": 5, "path": ENGINE}
        self.assertEqual(self.loaded([{"pid": 30, "created": 300}], rows(tui),
                                     {30: {"pid": 30, "path": r"c:\other\codex.exe", "created": 300}}), "unknown")

    def test_our_own_headless_server_is_never_another_session(self):
        """A codex.exe this process started (a headless turn's own app server) is never "elsewhere"."""
        ours = {"pid": 30, "parent": os.getpid(), "path": ENGINE}
        self.assertEqual(self.loaded([{"pid": 30, "created": 300}], rows(ours)), "unknown")

    def test_a_second_server_of_the_app_main_is_not_a_session(self):
        child = {"pid": 30, "parent": 10, "path": ENGINE}
        self.assertEqual(self.loaded([{"pid": 30, "created": 300}], rows(child)), "unknown")

    def test_no_holder_is_still_not_loaded(self):
        self.assertEqual(self.loaded([], rows()), "notLoaded")

    def test_nothing_new_is_asked_of_windows(self):
        """The rows are the ones the app's pairing read: no second inventory is started for it."""
        tui = {"pid": 30, "parent": 5, "path": ENGINE}
        with patch.object(pairing, "inventory", side_effect=AssertionError("a second inventory")), \
                patch.object(transport, "inventory", side_effect=AssertionError("a second inventory")):
            self.assertEqual(self.loaded([{"pid": 30, "created": 300}], rows(tui)), "elsewhere")


class OwnServerTests(unittest.TestCase):
    """With the Codex app closed, a route's own app server - this process's child - holds the writer lock once it has
    resumed the conversation: Backend.holder says "ours" only for the pid AND creation time of our own spawn
    (pairing.own_server), and the route's last look (engine/routes.py) takes that, and nothing else, as no holder."""

    def setUp(self):
        self.backend = w.Backend(Path("state"), Path(ENGINE))
        for patcher in (patch.object(self.backend, "_compatible"),
                        patch.dict(os.environ, {"USERPROFILE": PROFILE, "ProgramW6432": r"C:\Program Files"})):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.child = {"pid": 30, "parent": os.getpid(), "path": ENGINE}

    def own(self, created=300):
        with patch.object(pairing, "process_identity", return_value={"pid": 30, "path": ENGINE.lower(),
                                                                     "created": created}):
            mark = pairing.own_server(30)
        self.addCleanup(pairing.own_server_gone, mark)
        return mark

    def holder(self, users):
        def app_identity():
            self.backend._rows = [dict(self.child)]       # Codex closed: only our own server runs
            return None
        with patch.object(self.backend, "app_identity", side_effect=app_identity), \
                patch.object(transport, "resource_users", return_value=users), \
                patch.object(pairing, "process_identity", return_value={"pid": 30, "path": ENGINE.lower(),
                                                                        "created": 300}):
            self.backend.app_identity()
            return self.backend.holder(THREAD), self.last_look(ours=True), self.last_look(ours=False)

    def last_look(self, ours):
        from codex_auto_resume.engine.routes import RoutesMixin

        class Engine(RoutesMixin):
            backend = self.backend
        return Engine()._unheld_now(THREAD, ours=ours)

    def test_the_lock_our_own_server_holds_is_ours_and_passes_the_last_look(self):
        """Fails with the own-server word reverted: "unknown", and no headless turn ever starts."""
        self.own()
        self.assertEqual(self.holder([{"pid": 30, "created": 300}]), ("ours", True, False))

    def test_never_by_its_name_a_server_we_did_not_count_is_unknown(self):
        self.assertEqual(self.holder([{"pid": 30, "created": 300}]), ("unknown", False, False))

    def test_a_reused_pid_is_not_ours(self):
        self.own(created=299)
        self.assertEqual(self.holder([{"pid": 30, "created": 300}]), ("unknown", False, False))

    def test_a_server_shut_no_longer_counts(self):
        pairing.own_server_gone(self.own())
        self.assertEqual(self.holder([{"pid": 30, "created": 300}]), ("unknown", False, False))

    def test_nothing_holding_it_passes_both_looks(self):
        self.assertEqual(self.holder([]), ("none", True, True))


class WaitTests(EngineCase):
    def test_a_conversation_another_session_holds_waits_with_its_own_reason_and_nothing_is_sent(self):
        """Fails with dispatch's reason reverted: loaded_state_unknown, UNKNOWN."""
        self.ready_after_reset(loaded=False)
        self.h.backend.loaded_map[T1] = "elsewhere"
        self.h.tick()
        row = self.h.record()
        self.assert_no_send()
        self.assertEqual((row["state"], row["last_error"]), ("waiting_for_loaded_thread", "held_by_other_session"))
        self.assertEqual(machine.decode_gates(row["gate_eval"])["thread_available"],
                         (machine.WAIT, "held_by_other_session"))
        self.assertEqual(machine.public_code(row), "waiting_thread")

    def test_it_continues_once_the_app_holds_it(self):
        self.ready_after_reset(loaded=False)
        self.h.backend.loaded_map[T1] = "elsewhere"
        self.h.tick()
        self.h.backend.loaded_map[T1] = "loaded"
        self.h.tick(advance=61)
        self.assertEqual(len(self.h.backend.send_calls), 1)


if __name__ == "__main__":
    unittest.main()
