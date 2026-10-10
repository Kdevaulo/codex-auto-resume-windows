"""One watcher recovers in every Codex home it holds, and a record goes only to its own home (v0.6.15-beta).

Each home is a codexsim home of its own - a scratch folder, never the real CODEX_HOME - with its own reader,
its own simulated backend and its own engine; the two engines share one store and the watcher's one dispatch
lock. The same conversation and the same failed turn in both homes (a copied home, as MH's own setup made)
are two records with two ids, each sent through its own home's backend. The runtime's part - which homes are
watched, removed, locked - is driven through `runtime.homes.Homes` over an App-shaped stand-in whose locks
live under a scratch folder and whose backends are the simulated ones.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codexsim import BASE, RESET, CodexHome, SimBackend  # noqa: E402
from codex_auto_resume import homes as configured, machine  # noqa: E402
from codex_auto_resume.codex import LocalSource  # noqa: E402
from codex_auto_resume.codex import pairing  # noqa: E402
from codex_auto_resume.domain.errors import AdapterError  # noqa: E402
from codex_auto_resume.domain.plug import Plug  # noqa: E402
from codex_auto_resume.engine import Engine, StoreView  # noqa: E402
from codex_auto_resume.runtime import homes as runtime_homes  # noqa: E402
from codex_auto_resume.store import Store  # noqa: E402
from codex_auto_resume.win.homelock import HomeLock  # noqa: E402

T1 = "11111111-1111-7111-8111-111111111111"
TURN = "aaaaaaaa-aaaa-7aaa-8aaa-aaaaaaaaaaaa"
OPTIONS = {"reset_grace_seconds": 60, "state_poll_seconds": 60, "conservative_poll_seconds": 900,
           "delivery_timeout_seconds": 180}


class Recording(Plug):
    """A plug that only writes down which records it was asked about at the gates and shown in its view."""

    def __init__(self):
        self.asked, self.viewed = [], []

    def gate(self, name, row, vector):
        self.asked.append(row["interruption_id"])
        return super().gate(name, row, vector)

    def tick(self, view):
        self.viewed.extend(row["interruption_id"] for row in view.records_in(machine.WAITING | machine.WATCHED))
        return super().tick(view)


class TwoHomes(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.now = BASE + 10.0
        self.store = Store(self.root / "state")
        self.addCleanup(self.store.close)
        self.store.set_enabled(True, self.now)
        self.lock = threading.RLock()
        self.homes, self.backends, self.engines, self.held = {}, {}, {}, {"": True, "b": True}
        self.key_b = configured.key(self.root / "home-b")
        for name, key, plug in (("a", "", Recording()), ("b", self.key_b, None)):
            home = CodexHome(self.root / ("home-" + name))
            home.clock = lambda: self.now
            backend = SimBackend(home)
            backend.loaded_map[T1] = "loaded"
            flag = "" if name == "a" else "b"
            self.homes[name], self.backends[name] = home, backend
            self.engines[name] = Engine(self.store, LocalSource(home.root), backend, clock=lambda: self.now,
                                        options=dict(OPTIONS), plug=plug, dispatch_lock=lambda: self.lock,
                                        home_key=key, home_lock=lambda flag=flag: self.held[flag])
        self.plug = self.engines["a"].plug.plug

    def tick(self, advance=0.0):
        self.now += advance
        for name in ("a", "b"):
            self.engines[name].tick()

    def failed_in_both(self):
        for name in ("a", "b"):
            self.homes[name].fail_usage(T1, TURN)
        self.tick()
        self.now = RESET + 61

    def records(self):
        return {row["home_key"]: row for row in self.store.all_records()}


class RecordsTests(TwoHomes):
    def test_one_failure_in_two_homes_is_two_records_each_sent_to_its_own_home(self):
        self.failed_in_both()
        records = self.records()
        self.assertEqual(set(records), {"", self.key_b})
        self.assertNotEqual(records[""]["interruption_id"], records[self.key_b]["interruption_id"])
        self.tick()
        # Each home's backend got one send, for its own record: the default home's first (the UUID-keyed
        # "one in flight" makes the pair stricter - the second waits until the first leaves flight).
        self.assertEqual([call[0] for call in self.backends["a"].send_calls], [T1])
        first = self.records()
        sent = {key for key, row in first.items() if row["state"] not in machine.WAITING}
        self.assertEqual(sent, {""})
        self.assertEqual(self.backends["b"].send_calls, [])
        self.assertEqual(first[self.key_b]["last_error"], "other_recovery_in_flight")
        # And the conversation's fifteen minutes, counted by its UUID across homes, before the second home's.
        self.tick(advance=61)
        self.assertEqual(self.backends["b"].send_calls, [])
        self.assertEqual(self.records()[self.key_b]["last_error"], "thread_submission_cooldown")
        self.tick(advance=901)
        self.assertEqual([call[0] for call in self.backends["b"].send_calls], [T1])
        marker_b = self.records()[self.key_b]["marker"]
        self.assertIn(marker_b, self.backends["b"].send_calls[0][1])
        self.assertNotIn(marker_b, "".join(call[1] for call in self.backends["a"].send_calls))

    def test_a_home_whose_lock_is_not_held_waits_while_the_other_sends(self):
        self.held["b"] = False
        self.failed_in_both()
        for _ in range(3):
            self.tick(advance=61)
        self.assertEqual(len(self.backends["a"].send_calls), 1)
        self.assertEqual(self.backends["b"].send_calls, [])
        self.assertEqual(self.records()[self.key_b]["last_error"], "home_lock_unavailable")

    def test_the_plug_is_asked_and_shown_only_the_default_homes_records(self):
        self.failed_in_both()
        self.tick()
        records = self.records()
        self.assertTrue(self.plug.asked)
        self.assertEqual(set(self.plug.asked), {records[""]["interruption_id"]})
        self.assertEqual(set(self.plug.viewed), {records[""]["interruption_id"]})
        view = StoreView(self.store, self.now, home_key="")
        self.assertEqual({row["home_key"] for row in view.records_in(machine.STATES)}, {""})
        self.assertEqual({row["home_key"] for row in view.claimed_on_thread(T1)} - {""}, set())

    def test_an_app_not_on_that_home_leaves_its_record_waiting(self):
        self.backends["b"].app = None
        self.failed_in_both()
        for _ in range(3):
            self.tick(advance=61)
        self.assertEqual(self.backends["b"].send_calls, [])
        self.assertEqual(self.records()[self.key_b]["last_error"], "desktop_app_unavailable")


class PairingTests(unittest.TestCase):
    def test_an_extra_homes_server_must_hold_that_homes_state_open(self):
        rows = [{"pid": 10, "path": "C:\\Program Files\\WindowsApps\\OpenAI.ChatGPT\\app\\ChatGPT.exe", "parent": 1},
                {"pid": 11, "path": "C:\\engine\\codex.exe", "parent": 10}]
        with mock.patch.object(pairing, "_app_main", return_value=rows[0]), \
                mock.patch.object(pairing, "process_identity",
                                  side_effect=lambda pid: {"pid": pid, "path": rows[pid - 10]["path"].lower(),
                                                           "created": pid}), \
                mock.patch.object(pairing, "_state_holder",
                                  side_effect=AdapterError("desktop_server_missing_or_ambiguous")) as holder:
            # The default home: one server is the server, as it always was; the holder is never asked.
            self.assertEqual(pairing.desktop_pair(rows, "C:\\engine\\codex.exe", "C:\\home")["server"]["pid"], 11)
            holder.assert_not_called()
            with self.assertRaises(AdapterError):
                pairing.desktop_pair(rows, "C:\\engine\\codex.exe", "C:\\other", require_holder=True)
            holder.assert_called_once()


class App:
    """What runtime.homes asks of the watcher, over scratch folders and simulated backends."""

    def __init__(self, root, store, now):
        self.root, self.store, self.now = root, store, now
        self.settings = {configured.FIELD: []}
        self.codex_home = root / "home-a"
        self.lock_dir = root / "locks"
        self._home_lock = HomeLock(self.codex_home, self.lock_dir).__enter__()
        self.dispatch = threading.RLock()
        self.backends, self.engines, self.failures = {}, [], []
        self.logger = mock.Mock()
        self.default = SimBackend(CodexHome(self.codex_home))

    def backend(self):
        return mock.Mock(codex_exe=self.root / "codex.exe", app_identity=lambda: {"pid": 1})

    def home_backend(self, path, exe):
        backend = self.backends.get(str(path))
        if backend is None:
            home = CodexHome(Path(path)) if not (Path(path) / "state_5.sqlite").exists() else None
            backend = self.backends[str(path)] = SimBackend(home or self.homes[str(path)])
            backend.loaded_map[T1] = "loaded"
        return backend

    def home_source(self, path):
        return LocalSource(Path(path))

    def extra_home_lock(self, path):
        return HomeLock(path, self.lock_dir, require_identity=True)

    def home_engine(self, store, source, backend, key, held):
        engine = Engine(store, source, backend, clock=lambda: self.now[0], options=dict(OPTIONS), plug=None,
                        dispatch_lock=lambda: self.dispatch, home_key=key, home_lock=held)
        self.engines.append(engine)
        return engine

    def _record_failure(self, label):
        self.failures.append(label)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.now = [RESET + 61]
        self.store = Store(self.root / "state")
        self.addCleanup(self.store.close)
        self.store.set_enabled(True, BASE)
        self.app = App(self.root, self.store, self.now)
        self.addCleanup(self.app._home_lock.__exit__, None, None, None)
        self.home_b = CodexHome(self.root / "home-b")
        self.home_b.clock = lambda: self.now[0]
        self.app.homes = {str(self.root / "home-b"): self.home_b}
        self.homes = runtime_homes.Homes(self.app, clock=lambda: self.now[0])
        self.addCleanup(self.homes.close)
        self.key_b = configured.key(self.root / "home-b")

    def configure(self, *paths):
        self.app.settings = {configured.FIELD: [{"path": str(path), "alias": "home %d" % index}
                                                for index, path in enumerate(paths)]}

    def test_one_home_is_no_run_and_nothing_written(self):
        self.homes.sync(self.store)
        self.assertEqual(self.homes.runs, {})
        self.assertIsNone(self.homes.heartbeat())

    def test_a_configured_home_gets_its_own_reader_backend_lock_and_engine_with_no_plug(self):
        self.configure(self.root / "home-b")
        self.homes.sync(self.store)
        run = self.homes.runs[self.key_b]
        self.assertTrue(run.lock.held)
        self.assertEqual(run.engine.home_key, self.key_b)
        self.assertTrue(run.engine.plug.null, "another home is the standard edition's")
        self.assertIs(run.engine.dispatch_lock(), self.app.dispatch)
        self.assertEqual(self.homes.heartbeat(), [{"key": "", "state": "watched"}, {"key": self.key_b, "state": "watched"}])

    def test_a_home_another_watcher_holds_is_not_read_at_all(self):
        other = HomeLock(self.root / "home-b", self.app.lock_dir).__enter__()
        self.addCleanup(other.__exit__, None, None, None)
        self.configure(self.root / "home-b")
        self.home_b.fail_usage(T1, TURN)
        self.homes.sync(self.store)
        self.homes.tick()
        self.assertEqual(self.homes.runs, {})
        self.assertEqual(self.homes.heartbeat()[1], {"key": self.key_b, "state": "lock_busy"})
        self.assertEqual(self.store.all_records(), [], "no reader, no record")

    def test_the_default_home_named_again_is_not_watched_twice(self):
        self.configure(self.app.codex_home)
        (self.app.codex_home / "state_5.sqlite").exists() or CodexHome(self.app.codex_home)
        self.homes.sync(self.store)
        self.assertEqual(self.homes.runs, {})
        self.assertEqual(self.homes.heartbeat()[1]["state"], "duplicate")

    def test_removing_a_home_cancels_what_waits_there_and_lets_go_only_when_nothing_is_queued(self):
        self.configure(self.root / "home-b")
        self.homes.sync(self.store)
        run = self.homes.runs[self.key_b]
        self.home_b.fail_usage(T1, TURN)
        self.app.backends[str(self.root / "home-b")].after_accept = "queue"
        self.homes.tick()                       # detected
        self.now[0] += 31
        self.homes.tick()                       # sent, and left in Codex's queue
        queued = self.store.all_records()[0]
        self.assertEqual(queued["state"], "queued")
        other = "22222222-2222-7222-8222-222222222222"
        self.home_b.fail_usage(other, "bbbbbbbb-bbbb-7bbb-8bbb-bbbbbbbbbbbb", reset=RESET + 86400)
        run.engine.collect()
        waiting = [row for row in self.store.all_records() if row["thread_id"] == other][0]
        self.assertIn(waiting["state"], machine.WAITING)
        self.configure()                        # removed in Settings
        self.homes.sync(self.store)
        self.assertEqual(self.store.get(waiting["interruption_id"])["state"], "cancelled")
        self.assertEqual(self.store.get(waiting["interruption_id"])["last_error"], "home_removed")
        self.assertIn(self.key_b, self.homes.runs, "kept while its continuation may be in Codex's queue")
        self.assertTrue(run.lock.held)
        self.assertEqual(self.homes.heartbeat(), [{"key": "", "state": "watched"}, {"key": self.key_b, "state": "retiring"}])
        third = "33333333-3333-7333-8333-333333333333"
        self.home_b.fail_usage(third, "cccccccc-cccc-7ccc-8ccc-cccccccccccc")
        self.homes.tick()
        self.assertEqual(len(self.app.backends[str(self.root / "home-b")].send_calls), 1, "a retiring home sends nothing")
        self.assertEqual([row for row in self.store.all_records() if row["thread_id"] == third], [],
                         "and detects nothing")
        self.home_b.dispatch(T1)                # Codex runs it: the watch follows it out of flight
        for _ in range(3):
            self.now[0] += 20
            self.homes.tick()
        self.assertNotIn(self.store.get(queued["interruption_id"])["state"], machine.WATCHED)
        self.homes.sync(self.store)
        self.assertNotIn(self.key_b, self.homes.runs)
        self.assertFalse(run.lock.held, "its lock is let go once nothing of it is in flight")

    def test_a_record_of_a_home_no_settings_name_is_cancelled_at_the_start(self):
        key = "c" * 64
        self.store.register({"thread_id": T1, "turn_id": TURN, "completed_at": BASE, "started_at": BASE - 5,
                             "ordinal": 1, "interruption_id": "d" * 64, "reset_at": None, "limit_type": "x",
                             "uncertain": False, "category": "server_5xx"}, BASE, home_key=key)
        self.homes.sync(self.store)
        row = self.store.get("d" * 64)
        self.assertEqual((row["state"], row["last_error"]), ("cancelled", "home_removed"))


if __name__ == "__main__":
    unittest.main()
