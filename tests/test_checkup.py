"""The Diagnostics check (v0.6.16-beta.3, checkup.py): why a failed turn is not taken up, asked of the watcher.

It replaces the two one-click scripts issue #27 was diagnosed with, and unlike the second of them it copies
no rule: a verdict changes when the watcher's own rule does (test_it_asks_the_watchers_own_rule). Read only,
content-free, conversation ids as aliases.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codexsim import BASE  # noqa: E402
from codex_auto_resume import checkup, controlcli, diagnostics, logbook  # noqa: E402
from codex_auto_resume.codex import LocalSource, history  # noqa: E402
from codex_auto_resume.domain import skips  # noqa: E402
from codex_auto_resume.store import Store  # noqa: E402
from test_continuation_split import SplitHome  # noqa: E402
from test_control import ControlTestCase  # noqa: E402

A = "0a1b2c3d-0004-7000-8000-000000000001"
B = "0a1b2c3d-0004-7000-8000-000000000002"
NOW = BASE + 60
SECRET = "a secret prompt nobody may see"
QUIET = {"route": "toast", "do_not_disturb": False, "app_allowed": True}


class CheckupCase(ControlTestCase):
    def setUp(self):
        super().setUp()
        self.codex = SplitHome(self.home / "codex")
        environment = patch.dict(os.environ, {"CODEX_HOME": str(self.codex.root),
                                              "LOCALAPPDATA": str(self.home / "local")})
        environment.start()
        self.addCleanup(environment.stop)
        self.enable(True)

    def enable(self, on):
        with Store(self.paths.state_dir) as store:
            store.set_enabled(on, BASE - 600)

    def run_check(self, **kwargs):
        return checkup.run(self.control, now=NOW, presence=lambda: dict(QUIET), locale="en", **kwargs)

    @staticmethod
    def rows(result):
        return result["conversations"]


class VerdictTests(CheckupCase):
    def test_a_failure_it_would_take_up_says_what_still_holds_it(self):
        self.codex.add_thread(A, name=SECRET)
        self.codex.fail_usage(A)
        result = self.run_check()
        [row] = self.rows(result)
        self.assertTrue(row["brought"])
        self.assertEqual((row["status"], row["category"], row["reason"]), ("failed", "usage_limit", None))
        self.assertEqual(result["summary"], "watcher_stopped", "the test's watcher is not running")
        self.assertTrue(result["lines"][0].startswith("Most likely: the watcher is not running"), result["lines"][0])

    def test_another_kind_of_conversation_says_which(self):
        self.codex.add_thread(A, thread_source="subagent")
        self.codex.fail_usage(A)
        result = self.run_check()
        self.assertEqual([(row["reason"], row["kind"]) for row in self.rows(result)],
                         [(skips.OTHER_KIND, "thread_source subagent")])
        self.assertEqual(result["summary"], skips.OTHER_KIND)

    def test_it_asks_the_watchers_own_rule(self):
        """issue27-check27b copied an old 'user'-only rule; the check reads whatever rule the watcher has."""
        self.codex.add_thread(A, thread_source="chatgpt_handoff", originator="codex_work_desktop")
        self.codex.fail_usage(A)
        self.assertTrue(self.rows(self.run_check())[0]["brought"])
        with patch.object(history, "OWN_THREAD_SOURCES", frozenset({"user"})):
            self.assertEqual(self.rows(self.run_check())[0]["reason"], skips.OTHER_KIND)

    def test_recovery_off_and_a_conversation_switched_off_are_named(self):
        self.codex.fail_usage(A)
        self.enable(False)
        with Store(self.paths.state_dir) as store:
            store.set_thread_enabled(A, False)
        [row] = self.rows(self.run_check())
        self.assertEqual(row["remaining"], [skips.RECOVERY_OFF, skips.CONVERSATION_OFF])
        self.assertEqual(self.run_check()["summary"], skips.RECOVERY_OFF)

    def test_a_failure_already_taken_up_says_its_state(self):
        self.codex.fail_usage(A)
        found = LocalSource(self.codex.root).latest_failures(BASE - 3600)[0]
        detection = {key: found[key] for key in ("thread_id", "turn_id", "completed_at", "started_at", "ordinal",
                                                 "interruption_id")}
        detection.update(reset_at=None, limit_type="unknown", uncertain=True, category="usage_limit")
        with Store(self.paths.state_dir) as store:
            store.register(detection, BASE)
        result = self.run_check()
        self.assertEqual(self.rows(result)[0]["records"], ["waiting_reset"])
        self.assertEqual(result["summary"], "taken")

    def test_a_conversation_recorded_under_another_id_is_listed(self):
        self.codex.add_thread(A)
        self.codex.rotate(A)
        self.codex.fail_usage(A)
        result = self.run_check()
        [row] = self.rows(result)
        self.assertTrue(row["brought"])
        self.assertEqual(result["split"], [{"thread": row["thread"], "turns_under": row["turns_under"]}])
        self.assertTrue(row["turns_under"].startswith("thread-"))

    def test_nothing_failed_and_cloud_tasks_say_so(self):
        self.codex.add_turn(A, status="completed")
        (self.codex.root / ".codex-global-state.json").write_text(json.dumps(
            {"cloud-thread-prototype-threads-by-account-v1.someone": ["t1", "t2"], "other": {"x": 1}}),
            encoding="utf-8")
        result = self.run_check()
        self.assertEqual((result["summary"], result["cloud_tasks"]), ("cloud", 2))
        self.assertIn("Cloud tasks the app knows: 2.", "\n".join(result["lines"]))


class FactTests(CheckupCase):
    def test_each_home_says_when_its_databases_were_written_and_which_is_current(self):
        self.codex.fail_usage(A)
        os.utime(self.codex.root / "thread_history_1.sqlite", (NOW - 120, NOW - 120))
        [home] = self.run_check()["homes"]
        self.assertEqual((home["home"], home["current"], home["readable"]), (None, True, True))
        self.assertEqual(home["history_written"], NOW - 120)
        self.assertIn("The default Codex home: its state written", "\n".join(self.run_check()["lines"]))

    def test_usage_notices_and_codex_are_said_even_when_unknown(self):
        said = "\n".join(self.run_check()["lines"])
        self.assertIn("No usage reading has worked yet.", said)
        self.assertIn("Notices are shown as Windows notifications. Do not disturb: off.", said)
        self.assertIn("compatibility:", said)

    def test_the_last_skip_lines_come_from_the_log_as_aliases(self):
        self.paths.logs_dir.mkdir(parents=True, exist_ok=True)
        line = logbook.skipped(A, B, skips.BEFORE_WINDOW)
        self.paths.log_file.write_text("[2026-10-15 10:00:00] %s\n" % line, encoding="utf-8")
        result = self.run_check()
        self.assertEqual(len(result["skips"]), 1)
        self.assertNotIn(A, result["skips"][0])
        self.assertIn("not taken up (before_window)", result["skips"][0])

    def test_no_content_and_no_real_id_anywhere(self):
        self.codex.add_thread(A, name=SECRET)
        self.codex.add_turn(A, status="failed", user_text=SECRET, progress=False,
                            error_json=json.dumps({"codexErrorInfo": "badRequest", "message": SECRET}))
        result = self.run_check()
        text = json.dumps(result)
        self.assertNotIn("secret", text)
        self.assertNotIn(A, text)
        self.assertEqual(self.rows(result)[0]["reason"], skips.NOT_RECOVERED)

    def test_it_writes_nothing(self):
        self.codex.fail_usage(A)
        before = {path: path.stat().st_mtime_ns for path in self.home.rglob("*") if path.is_file()}
        self.run_check()
        after = {path: path.stat().st_mtime_ns for path in self.home.rglob("*") if path.is_file()}
        self.assertEqual(before, after)


class BoundTests(CheckupCase):
    """A big Codex home is checked within the window's wait: the newest conversations, and what was left out."""

    def many(self, count):
        rows, state = [], []
        for number in range(count):
            thread = "0a1b2c3d-0006-7000-8000-%012d" % number
            path = self.codex.root / "sessions" / ("rollout-x-%s.jsonl" % thread)
            path.write_bytes(json.dumps({"type": "session_meta", "payload": {
                "id": thread, "originator": "Codex Desktop", "source": "vscode", "thread_source": "user"}}).encode()
                + bytes([10]))
            state.append((thread, str(path)))
            rows.append((thread, "0a1b2c3d-0007-7000-8000-%012d" % number, 5, "failed",
                         json.dumps({"codexErrorInfo": "usageLimitExceeded"}), int(NOW - 3600 - number),
                         int(NOW - 3500 - number)))
        self.codex.add_thread(A)
        with self.codex._db("thread_history_1.sqlite") as db:
            db.executemany("INSERT INTO thread_turns (thread_id, turn_id, rollout_ordinal, status, error_json, "
                           "started_at, completed_at) VALUES (?,?,?,?,?,?,?)", rows)
        with self.codex._db("state_5.sqlite") as db:
            db.executemany("INSERT INTO threads (id, rollout_path, source, thread_source, archived, history_mode) "
                           "VALUES (?,?,'vscode','user',0,'paginated')", state)

    def test_only_the_newest_conversations_and_it_says_how_many_more(self):
        self.many(checkup.NEWEST + 50)
        result = self.run_check()
        self.assertEqual(len(self.rows(result)), checkup.NEWEST)
        self.assertEqual(result["left_out"], {"conversations": 50, "unchecked": 0})
        self.assertIn("50 older conversations are not shown (only the newest %d)." % checkup.NEWEST,
                      "\n".join(result["lines"]))

    def test_past_its_time_it_stops_and_says_how_many_it_did_not_check(self):
        self.many(30)
        with patch.object(checkup, "SECONDS", -1):
            result = self.run_check()
        self.assertEqual(self.rows(result), [])
        self.assertEqual(result["left_out"]["unchecked"], 30)
        self.assertIn("30 conversations could not be checked in time.", "\n".join(result["lines"]))


class SurfaceTests(CheckupCase):
    def test_the_bridge_answers_it(self):
        self.codex.fail_usage(A)
        with patch.object(checkup, "_presence", return_value=dict(QUIET)):
            reply = controlcli.dispatch(self.control, "detection-check", {})
        self.assertTrue(reply["ok"], reply)
        self.assertIn("lines", reply["result"])

    def test_the_diagnostics_bundle_carries_it_with_the_bundles_aliases(self):
        self.codex.fail_usage(A)
        found = LocalSource(self.codex.root).latest_failures(BASE - 3600)[0]
        detection = {key: found[key] for key in ("thread_id", "turn_id", "completed_at", "started_at", "ordinal",
                                                 "interruption_id")}
        detection.update(reset_at=None, limit_type="unknown", uncertain=True, category="usage_limit")
        with Store(self.paths.state_dir) as store:
            store.register(detection, BASE)
        with patch.object(checkup, "_presence", return_value=dict(QUIET)),                 patch.object(checkup.time, "time", return_value=NOW):
            bundle = diagnostics.collect(self.control, check=checkup.for_bundle(self.control))
        check = bundle["detection_check"]
        self.assertEqual(check["conversations"][0]["thread"], bundle["records"][0]["thread"])
        self.assertTrue(check["lines"][0].startswith("The latest failed turn was taken up"))


if __name__ == "__main__":
    unittest.main()
