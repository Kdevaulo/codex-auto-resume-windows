"""v0.6.26 (update resilience, proposal 1): the watcher says, within minutes, when recovery cannot work here.

#67 left every recovery waiting for ever under "Open in another Codex session" beside the open Codex app: Codex 26.1117
ran its app server under a helper of the app, the pairing took the exec-server, and nothing said that Codex had changed.
The judge (engine/impossible.py) reads each look's facts - who holds the writer lock and the newest databases, as the
Restart Manager answers - and after 10 minutes of looks that contradict each other one word says so; every surface
reads it as attention (domain/public.py codex_changed). It never sends and never decides "loaded".

No test asks this PC anything: the Restart Manager, the process list and the pairing are stubs throughout.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import config  # noqa: E402
from codex_auto_resume.domain import public  # noqa: E402
from codex_auto_resume.engine import impossible  # noqa: E402
from codex_auto_resume.runtime import loop  # noqa: E402
from codex_auto_resume.ui.popup import model as popup  # noqa: E402

T1 = "019a0000-0000-7000-8000-000000000001"
EXEC_SERVER, HELPER_SERVER, TUI = 40, 50, 60
ELSEWHERE = "recovery_blocked:held_elsewhere"


def look_over(judge, facts, *, minutes=11, runs=True, start=1000.0):
    """One look a minute for `minutes` minutes, each finding `facts`; the time of the last."""
    now = start
    for step in range(minutes + 1):
        now = start + 60.0 * step
        judge.look(now, runs, facts)
    return now


class RulesTests(unittest.TestCase):
    def test_67s_rows_with_v0624s_rule_are_held_elsewhere(self):
        # v0.6.24's pairing took the exec-server (40); the helper-parented app server (50) holds the lock and both
        # databases, and the record waits "held by another session".
        facts = impossible.recovery_facts(matched=True, server=EXEC_SERVER, reasons={"held_by_other_session"},
                                          lock_holders={HELPER_SERVER}, database_holders={HELPER_SERVER},
                                          locks_folder=True, older_holders=[])
        self.assertIs(facts["held_elsewhere"], True)
        judge = impossible.Judge()
        self.assertEqual(judge.word(look_over(judge, facts)), ELSEWHERE)

    def test_a_terminal_holding_the_lock_beside_the_apps_server_is_no_contradiction(self):
        facts = impossible.recovery_facts(matched=True, server=HELPER_SERVER, reasons={"held_by_other_session"},
                                          lock_holders={TUI}, database_holders={HELPER_SERVER, TUI},
                                          locks_folder=True, older_holders=[])
        self.assertEqual(set(facts.values()), {False})
        judge = impossible.Judge()
        self.assertIsNone(judge.word(look_over(judge, facts)))

    def test_a_home_without_its_lock_folder_while_the_server_is_paired_is_locks_unread(self):
        facts = impossible.recovery_facts(matched=True, server=HELPER_SERVER, reasons={"notLoaded"}, lock_holders=set(),
                                          database_holders={HELPER_SERVER}, locks_folder=False, older_holders=[])
        self.assertIs(facts["locks_unread"], True)
        judge = impossible.Judge()
        self.assertEqual(judge.word(look_over(judge, facts)), "recovery_blocked:locks_unread")
        # A lock folder that is there is no contradiction: the conversation is simply not open.
        there = impossible.recovery_facts(matched=True, server=HELPER_SERVER, reasons={"notLoaded"},
                                          lock_holders=set(), database_holders={HELPER_SERVER}, locks_folder=True,
                                          older_holders=[])
        self.assertIs(there["locks_unread"], False)

    def test_a_newer_generation_nobody_holds_beside_the_older_one_the_server_holds_is_stale(self):
        facts = impossible.recovery_facts(matched=True, server=HELPER_SERVER, reasons={"notLoaded"}, lock_holders=set(),
                                          database_holders=set(), locks_folder=True, older_holders=[{HELPER_SERVER}])
        self.assertIs(facts["stale_database"], True)

    def test_with_the_app_closed_nothing_is_judged(self):
        judge = impossible.Judge()
        facts = {"held_elsewhere": True, "locks_unread": True, "stale_database": True, "usage_protocol": True}
        self.assertIsNone(judge.word(look_over(judge, facts, runs=False)))
        self.assertIsNone(judge.word(look_over(judge, facts, runs=None)))
        unpaired = impossible.recovery_facts(matched=False, server=None, reasons={"held_by_other_session"},
                                             lock_holders={HELPER_SERVER}, database_holders={HELPER_SERVER},
                                             locks_folder=True, older_holders=[])
        self.assertEqual(set(unpaired.values()), {None})

    def test_ten_minutes_of_looks_are_needed_and_the_first_look_that_breaks_it_clears_it(self):
        judge = impossible.Judge()
        held = {"held_elsewhere": True}
        self.assertIsNone(judge.word(look_over(judge, held, minutes=8)))
        last = look_over(judge, held, minutes=2, start=1000.0 + 9 * 60)
        self.assertEqual(judge.word(last), ELSEWHERE)
        judge.look(last + 60, True, {"held_elsewhere": False})
        self.assertIsNone(judge.word(last + 60))

    def test_looks_far_apart_start_the_count_again(self):
        # A PC that slept for two hours between two looks has not watched the contradiction for two hours.
        judge = impossible.Judge()
        judge.look(1000.0, True, {"held_elsewhere": True})
        judge.look(1000.0 + 7200, True, {"held_elsewhere": True})
        self.assertIsNone(judge.word(1000.0 + 7200))

    def test_a_usage_read_codex_answered_unknowably_is_said_after_half_an_hour(self):
        judge = impossible.Judge()
        facts = {"usage_protocol": True}
        self.assertIsNone(judge.word(look_over(judge, facts, minutes=20)))
        judge = impossible.Judge()
        self.assertEqual(judge.word(look_over(judge, facts, minutes=31)), "recovery_blocked:usage_protocol")


class Store:
    def __init__(self, rows):
        self.rows = rows

    def records_in(self, states, home_key=None):
        return [dict(row) for row in self.rows]


class Watcher(loop.WatchLoop):
    """The watch loop's self-check alone, over a scratch home."""

    def __init__(self, root):
        self.paths = config.Paths(root)
        self.paths.state_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("test_recovery_blocked")
        self.failures = []

    def _record_failure(self, label):
        self.failures.append(label)


class FeederTests(unittest.TestCase):
    """The watcher gathers the facts, writes the word beside its heartbeat, and every reader shows it."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.codex = self.root / "codex"
        (self.codex / "thread-writer-locks").mkdir(parents=True)
        for name in ("queue_1.sqlite", "state_5.sqlite"):
            (self.codex / name).write_bytes(b"")
        self.watcher = Watcher(self.root / "product")
        identity = {"pid": 10, "created": 1, "server": {"pid": EXEC_SERVER, "created": 2}}
        backend = types.SimpleNamespace(codex_home=self.codex, app_look="matched", engine_version="0.170.0",
                                        app_identity=lambda: identity)
        self.engine = types.SimpleNamespace(backend=backend, detection_failed=False)
        self.store = Store([{"thread_id": T1, "last_error": "held_by_other_session", "state": "waiting_for_loaded_thread"}])

        def users(*paths):
            # #67: the helper-parented app server holds the databases and the lock; the exec-server nothing.
            return [{"pid": HELPER_SERVER, "created": 3}] if paths else []
        stub = patch.object(loop, "resource_users", side_effect=users)
        stub.start()
        self.addCleanup(stub.stop)
        self.now = 0.0
        clock = patch.object(loop.time, "time", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

    def run_for(self, minutes, started=500.0):
        for step in range(minutes + 1):
            self.now = 1000.0 + 60.0 * step
            self.watcher._self_check(self.store, self.engine, started)

    def written(self):
        return json.loads(self.watcher.paths.self_check_file.read_text(encoding="utf-8"))

    def test_the_watcher_writes_the_word_and_a_status_reader_shows_it_as_attention(self):
        self.run_for(11)
        self.assertEqual(self.watcher.failures, [])
        self.assertEqual(self.written()["blocked"], ELSEWHERE)
        check = public.self_check(self.written(), 500.0)
        self.assertEqual(check, {"blocked": ELSEWHERE, "unknown_error": None, "layout_untested": None})
        watcher = {"running": True, "ticking": True, "engine_state": "structurally_compatible", "self_check": check}
        record = {"state": "waiting_for_loaded_thread", "last_error": "held_by_other_session"}
        self.assertIn("codex_changed", public.overlays(record, watcher=watcher))
        status = {"watcher_running": True, "enabled": True, "watcher": watcher}
        self.assertEqual(popup.activity(status, [], 0.0), "attention")
        self.assertTrue(popup.icon_attention(status, []))
        self.assertEqual(popup.snapshot_activity({"enabled": True, "blocked": True}, 0.0), "attention")

    def test_before_ten_minutes_and_of_another_watcher_nothing_is_said(self):
        self.run_for(5)
        self.assertIsNone(self.written()["blocked"])
        self.assertIsNone(public.self_check(self.written(), 500.0))
        self.run_for(11)
        self.assertIsNone(public.self_check(self.written(), 501.0))

    def test_the_paired_server_holding_the_databases_says_nothing(self):
        stub = patch.object(loop, "resource_users",
                            side_effect=lambda *paths: [{"pid": EXEC_SERVER, "created": 2}] if paths else [])
        with stub:
            self.run_for(11)
        self.assertIsNone(self.written()["blocked"])

    def test_with_nothing_waiting_for_it_the_restart_manager_is_not_asked(self):
        self.store.rows = [{"thread_id": T1, "last_error": "waiting_for_reset", "state": "waiting_reset"}]
        asked = patch.object(loop, "resource_users", side_effect=AssertionError("asked"))
        with asked, patch.object(loop, "app_running_now", side_effect=AssertionError("listed")):
            self.run_for(11)
        self.assertEqual(self.watcher.failures, [])
        self.assertIsNone(self.written()["blocked"])


if __name__ == "__main__":
    unittest.main()
