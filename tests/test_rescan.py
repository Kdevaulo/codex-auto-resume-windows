"""Rescan and reconcile (v0.6.16, issue #39, suggested by weng-wen-jun): every waiting recovery looked at again.

The rules the reply on issue #39 promised, each held here:

* a waiting record is retired ONLY on positive evidence of newer work - its exact failed turn (that turn id at the
  ordinal the record holds) followed by a turn a person started, our own continuations excluded - and where Codex's
  history is behind, the same proof in the conversation's current file; anything uncertain stays and is unresolved
  (EvidenceTests, StaleProjectionTests);
* a valid wait is left to every normal gate: nothing about it changes - reset grace, a postponement, a hold, the
  consent switches, the budgets (GateTests);
* each record is read again in the transaction that applies a finding, and one that changed meanwhile is skipped
  (RaceTests);
* nothing is sent, nothing is written to Codex, no budget is given back, and cancelled, finished and in-flight
  records and History are kept (LeftAloneTests);
* the answer says retired / rechecked / unresolved / changed meanwhile, each journalled under a word of its own,
  and the bridge's `rescan` reaches it with no argument (AnswerTests).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codexsim import BASE, RESET  # noqa: E402
from codex_auto_resume import controlcli, rescan  # noqa: E402
from codex_auto_resume.codex import LocalSource, rollout  # noqa: E402
from codex_auto_resume.domain import ids  # noqa: E402
from codex_auto_resume.store import Store  # noqa: E402
from test_continuation_split import SplitHome  # noqa: E402
from test_control import ControlTestCase  # noqa: E402

A = "0a1b2c3d-0039-7000-8000-000000000001"
OTHER = "0a1b2c3d-0039-7000-8000-000000000002"
NOW = BASE + 600


class RescanCase(ControlTestCase):
    def setUp(self):
        super().setUp()
        self.codex = SplitHome(self.home / "codex")
        environment = patch.dict(os.environ, {"CODEX_HOME": str(self.codex.root),
                                              "LOCALAPPDATA": str(self.home / "local")})
        environment.start()
        self.addCleanup(environment.stop)
        self.asked = []

    # ------------------------------------------------------------------ helpers
    def fail(self, thread=A, **kwargs):
        """A usage-limit failure in `thread`, registered as the watcher registers it; returns its record."""
        self.codex.add_thread(thread)
        turn = self.codex.fail_usage(thread, **kwargs)
        found = [row for row in LocalSource(self.codex.root).latest_failures(BASE - 3600) if row["turn_id"] == turn][0]
        return self.register(found)

    def register(self, found, **changes):
        detection = {key: found[key] for key in ("thread_id", "turn_id", "completed_at", "started_at", "ordinal",
                                                 "interruption_id")}
        detection.update(reset_at=None, limit_type="unknown", uncertain=True, category="usage_limit")
        detection.update(changes)
        with Store(self.paths.state_dir) as store:
            self.assertTrue(store.register(detection, BASE, state="waiting_poll", next_retry_at=NOW + 900))
            return store.get(detection["interruption_id"])

    def record(self, key):
        with Store(self.paths.state_dir) as store:
            return store.get(key)

    def events(self, key):
        with Store(self.paths.state_dir) as store:
            return [event["code"] for event in store.events(key)]

    def write(self, sql, *arguments):
        with Store(self.paths.state_dir) as store:
            with store._transaction() as connection:
                connection.execute(sql, arguments)

    def judge(self, **kwargs):
        real = rescan.judge_for(self.control, {"": LocalSource(self.codex.root)}, now=NOW, **kwargs)

        def spy(row, kin):
            self.asked.append(row["interruption_id"])
            return real(row, kin)
        return spy

    def run_rescan(self, judge=None):
        return self.control.rescan_pending(judge or self.judge())

    def outcome(self, result, key):
        return [(row["outcome"], row["reason"]) for row in result["records"] if row["interruption_id"] == key][0]

    def person(self, thread=A, **kwargs):
        """A turn a person starts after the failure."""
        return self.codex.add_turn(thread, status="completed", **kwargs)

    def stale(self, thread=A):
        """Codex's history stops following the conversation's file."""
        self.codex.make_stale(thread)

    def events_in_file(self, thread, *events):
        """Lines written into the conversation's current file, the projection not following."""
        self.codex._append(thread, list(events))

    @staticmethod
    def task_complete(turn):
        return {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn,
                                                 "error": {"codex_error_info": "usage_limit_exceeded"}}}

    @staticmethod
    def user_message(text="and now something else"):
        return {"type": "event_msg", "payload": {"type": "user_message", "message": text}}


class EvidenceTests(RescanCase):
    """Retired only on a person's turn after the exact failed turn; uncertain is unresolved."""

    def test_a_persons_later_turn_retires_the_wait(self):
        row = self.fail()
        self.person()
        result = self.run_rescan()
        self.assertEqual(self.outcome(result, row["interruption_id"]), ("retired", "later_turn_exists"))
        after = self.record(row["interruption_id"])
        self.assertEqual((after["state"], after["last_error"]), ("superseded_by_user", "later_turn_exists"))
        self.assertIn("rescan_retired", self.events(row["interruption_id"]))

    def test_a_held_or_postponed_wait_is_retired_too(self):
        """The case the watcher never looks at: a wait held for a person, or postponed, is not due."""
        row = self.fail()
        with Store(self.paths.state_dir) as store:
            store.hold_waiting([row["interruption_id"]], "ask", NOW, actor="gui")
            store.postpone(row["interruption_id"], A, NOW + 3600, NOW, actor="gui")
        self.person()
        self.assertEqual(self.outcome(self.run_rescan(), row["interruption_id"])[0], "retired")

    def test_the_latest_failure_is_rechecked_and_left_waiting(self):
        row = self.fail()
        result = self.run_rescan()
        self.assertEqual(self.outcome(result, row["interruption_id"]), ("rechecked", None))
        self.assertEqual(self.record(row["interruption_id"])["state"], "waiting_poll")

    def test_a_turn_our_own_continuation_started_is_no_evidence(self):
        row = self.fail()
        self.person(user_text="carry on\n\n" + row["marker"])
        result = self.run_rescan()
        self.assertEqual(self.outcome(result, row["interruption_id"]), ("unresolved", "latest_turn_changed"))
        self.assertEqual(self.record(row["interruption_id"])["state"], "waiting_poll")

    def test_a_turn_another_record_of_ours_started_is_no_evidence(self):
        """Own continuation markers are excluded - any record's of the conversation, not only this one's."""
        row = self.fail()
        earlier = ids.short_marker("b" * 64)
        sibling = dict(row, interruption_id="b" * 64, turn_id="0a1b2c3d-0039-7000-8000-0000000000ff",
                       ordinal=row["ordinal"] - 1)
        self.register(sibling)
        self.control.cancel_interruption("b" * 64)
        self.assertEqual(self.record("b" * 64)["marker"], earlier)
        self.person(user_text="carry on\n\n" + earlier)
        result = self.run_rescan()
        self.assertEqual(self.outcome(result, row["interruption_id"])[0], "unresolved")

    def test_a_turn_with_no_message_of_a_persons_is_no_evidence(self):
        row = self.fail()
        self.person(user_text=None)
        self.assertEqual(self.outcome(self.run_rescan(), row["interruption_id"])[0], "unresolved")

    def test_a_turn_still_starting_is_no_evidence(self):
        row = self.fail()
        self.codex.add_turn(A, status="inProgress", first_user=False)
        self.assertEqual(self.outcome(self.run_rescan(), row["interruption_id"])[0], "unresolved")

    def test_without_the_exact_failed_turn_nothing_is_proven(self):
        """The anchor: the failed turn must be found at the ordinal the record holds. Read from an ordinal before it,
        a person's turn that came before the failure would look like newer work."""
        self.codex.add_thread(A)
        self.person()
        turn = self.codex.fail_usage(A)
        found = [row for row in LocalSource(self.codex.root).latest_failures(BASE - 3600) if row["turn_id"] == turn][0]
        wrong = dict(found, ordinal=found["ordinal"] - 2,
                     interruption_id=ids.interruption_id(A, turn, found["completed_at"], found["ordinal"] - 2))
        row = self.register(wrong)
        result = self.run_rescan()
        self.assertEqual(self.outcome(result, row["interruption_id"])[0], "unresolved")
        self.assertEqual(self.record(row["interruption_id"])["state"], "waiting_poll")


class StaleProjectionTests(RescanCase):
    """Codex's history behind its file: the file read for the same proof, and nothing retired without it."""

    def split_failure(self):
        """issue #39's case: the conversation's file is replaced by A_B, its history behind it."""
        row = self.fail()
        self.codex.rotate(A)
        return row

    def test_a_stale_projection_with_replacement_evidence_retires(self):
        row = self.split_failure()
        # The replacement file replays the work up to the failed turn's end, then a person's message.
        self.events_in_file(A, self.user_message("the old prompt"), self.task_complete(row["turn_id"]),
                            self.user_message())
        result = self.run_rescan()
        self.assertEqual(self.outcome(result, row["interruption_id"]), ("retired", "later_turn_exists"))
        self.assertEqual(self.record(row["interruption_id"])["state"], "superseded_by_user")

    def test_a_stale_projection_without_evidence_stays_unresolved(self):
        row = self.split_failure()
        self.events_in_file(A, self.user_message("the old prompt"), self.task_complete(row["turn_id"]))
        result = self.run_rescan()
        self.assertEqual(self.outcome(result, row["interruption_id"]), ("unresolved", "projection_stale"))
        self.assertEqual(self.record(row["interruption_id"])["state"], "waiting_poll")

    def test_a_message_before_the_failed_turns_end_proves_nothing(self):
        row = self.split_failure()
        self.events_in_file(A, self.user_message("earlier work"))
        self.assertEqual(self.outcome(self.run_rescan(), row["interruption_id"]), ("unresolved", "projection_stale"))

    def test_our_own_message_after_it_proves_nothing(self):
        row = self.split_failure()
        self.events_in_file(A, self.task_complete(row["turn_id"]), self.user_message("go on\n\n" + row["marker"]))
        self.assertEqual(self.outcome(self.run_rescan(), row["interruption_id"]), ("unresolved", "projection_stale"))

    def test_a_stale_projection_in_one_file_too(self):
        row = self.fail()
        self.stale()
        self.events_in_file(A, self.user_message())
        result = self.run_rescan()
        self.assertEqual(self.outcome(result, row["interruption_id"]), ("retired", "later_turn_exists"),
                         "fail_usage wrote the failed turn's end into the file; the message is after it")

    def test_an_oversized_file_stays_unresolved(self):
        row = self.split_failure()
        self.events_in_file(A, self.task_complete(row["turn_id"]), self.user_message())
        with patch.object(rollout, "RESCAN_BYTES", 64):
            result = self.run_rescan()
        self.assertEqual(self.outcome(result, row["interruption_id"]), ("unresolved", "too_large"))
        self.assertEqual(self.record(row["interruption_id"])["state"], "waiting_poll")

    def test_an_unreadable_file_stays_unresolved(self):
        row = self.split_failure()
        self.events_in_file(A, self.task_complete(row["turn_id"]), self.user_message())
        opened = Path.open

        def refuse(path, *args, **kwargs):
            if str(path).endswith(".jsonl"):
                raise PermissionError("held by another program")
            return opened(path, *args, **kwargs)
        with patch.object(Path, "open", refuse):
            result = self.run_rescan()
        self.assertEqual(self.outcome(result, row["interruption_id"]), ("unresolved", "unreadable"))
        self.assertEqual(self.record(row["interruption_id"])["state"], "waiting_poll")

    def test_a_line_too_long_is_passed_over_and_proves_nothing(self):
        row = self.split_failure()
        self.events_in_file(A, self.task_complete(row["turn_id"]), self.user_message("x" * 300))
        with patch.object(rollout, "MAX_ITEM_BYTES", 120):
            result = self.run_rescan()
        self.assertEqual(self.outcome(result, row["interruption_id"]), ("unresolved", "projection_stale"))

    def test_a_continuation_sent_with_no_marker_keeps_the_file_unread(self):
        """A marker-free continuation (the advanced edition's) cannot be told from a person's message in the file."""
        row = self.split_failure()
        self.write("UPDATE interruptions SET recovery_client_id=? WHERE interruption_id=?",
                   ids.continuation_client_id(row["interruption_id"]), row["interruption_id"])
        self.events_in_file(A, self.task_complete(row["turn_id"]), self.user_message())
        self.assertEqual(self.outcome(self.run_rescan(), row["interruption_id"]), ("unresolved", "marker_free"))


class GateTests(RescanCase):
    """A valid wait is rechecked by leaving it to every normal gate: nothing about it moves."""

    def test_a_rechecked_wait_keeps_its_schedule_its_hold_its_postponement_and_its_budgets(self):
        row = self.fail()
        key = row["interruption_id"]
        self.write("UPDATE interruptions SET state='waiting_reset', reset_at=?, next_retry_at=?, recovery_attempts=2 "
                   "WHERE interruption_id=?", RESET, RESET + 60, key)
        with Store(self.paths.state_dir) as store:
            store.hold_waiting([key], "ask", NOW, actor="gui")
            store.postpone(key, A, NOW + 7200, NOW, actor="gui")
            store.set_thread_enabled(A, False)
            before = store.get(key)
        result = self.run_rescan()
        self.assertEqual(self.outcome(result, key)[0], "rechecked")
        after = self.record(key)
        for field in ("state", "reset_at", "next_retry_at", "not_before", "hold", "retry_now_count", "budget_resets",
                      "recovery_attempts", "attempt_count", "last_error", "cancel_requested"):
            self.assertEqual(after[field], before[field], field)
        with Store(self.paths.state_dir) as store:
            self.assertFalse(store.thread_enabled(A), "a conversation switched off stays off")


class RaceTests(RescanCase):
    """Re-read in the transaction that applies the finding; changed meanwhile is skipped."""

    def changing(self, change):
        real = self.judge()

        def judged(row, kin):
            found = real(row, kin)
            change(row)
            return found
        return judged

    def test_a_record_cancelled_mid_scan_is_skipped(self):
        row = self.fail()
        self.person()
        result = self.run_rescan(self.changing(lambda row: self.control.cancel_interruption(row["interruption_id"])))
        self.assertEqual(self.outcome(result, row["interruption_id"]), ("changed", None))
        self.assertEqual(result["changed"], 1)
        self.assertEqual(self.record(row["interruption_id"])["state"], "cancelled", "the person's cancel stands")
        self.assertIn("rescan_changed", self.events(row["interruption_id"]))
        self.assertNotIn("rescan_retired", self.events(row["interruption_id"]))

    def test_a_record_the_watcher_claimed_mid_scan_is_skipped(self):
        row = self.fail()
        self.person()
        result = self.run_rescan(self.changing(lambda row: self.write(
            "UPDATE interruptions SET state='submitting', submitted_at=? WHERE interruption_id=?", NOW,
            row["interruption_id"])))
        self.assertEqual(self.outcome(result, row["interruption_id"])[0], "changed")
        self.assertEqual(self.record(row["interruption_id"])["state"], "submitting")

    def test_a_record_postponed_or_retried_mid_scan_is_skipped(self):
        for change in (lambda row: self.control.request_retry_now(row["interruption_id"]),
                       lambda row: self.control.postpone(row["interruption_id"], A, minutes=30)):
            with self.subTest(change=change):
                self.write("DELETE FROM interruptions")
                row = self.fail()
                result = self.run_rescan(self.changing(change))
                self.assertEqual(self.outcome(result, row["interruption_id"])[0], "changed")

    def test_a_poll_that_only_moved_the_next_look_is_no_change(self):
        row = self.fail()
        self.person()
        result = self.run_rescan(self.changing(lambda row: self.write(
            "UPDATE interruptions SET next_retry_at=?, last_error='projection_stale' WHERE interruption_id=?",
            NOW + 60, row["interruption_id"])))
        self.assertEqual(self.outcome(result, row["interruption_id"])[0], "retired")


class LeftAloneTests(RescanCase):
    """Nothing sent, nothing written to Codex, no budget, and every record that is not a plain wait kept."""

    def digests(self):
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(self.codex.root.rglob("*")) if path.is_file()}

    def test_cancelled_finished_and_in_flight_records_are_never_asked_about_or_changed(self):
        waiting = self.fail()
        queued = self.fail(OTHER)
        self.write("UPDATE interruptions SET state='queued', submitted_at=?, queue_id=? WHERE interruption_id=?",
                   NOW, "0a1b2c3d-0039-7000-8000-0000000000aa", queued["interruption_id"])
        third = "0a1b2c3d-0039-7000-8000-000000000003"
        cancelled = self.fail(third)
        self.control.cancel_interruption(cancelled["interruption_id"])
        fourth = "0a1b2c3d-0039-7000-8000-000000000004"
        asking = self.fail(fourth)
        self.write("UPDATE interruptions SET cancel_requested=1 WHERE interruption_id=?", asking["interruption_id"])
        for thread in (A, OTHER, third, fourth):
            self.person(thread)
        with Store(self.paths.state_dir) as store:
            before = {row["interruption_id"]: row for row in store.all_records()}
            history = store.history(include_hidden=True)
        result = self.run_rescan()
        self.assertEqual(self.asked, [waiting["interruption_id"]])
        self.assertEqual((result["scanned"], result["not_waiting"], result["retired"]), (1, 2, 1))
        with Store(self.paths.state_dir) as store:
            after = {row["interruption_id"]: row for row in store.all_records()}
            self.assertEqual(sorted(row["interruption_id"] for row in store.history(include_hidden=True)),
                             sorted(row["interruption_id"] for row in history), "History keeps every record")
        for key in (queued["interruption_id"], cancelled["interruption_id"], asking["interruption_id"]):
            self.assertEqual(after[key], before[key])

    def test_nothing_is_written_to_codex_and_no_budget_is_given_back(self):
        row = self.fail()
        self.write("UPDATE interruptions SET recovery_attempts=3, budget_resets=1 WHERE interruption_id=?",
                   row["interruption_id"])
        self.person()
        before = self.digests()
        self.run_rescan()
        self.assertEqual(self.digests(), before)
        after = self.record(row["interruption_id"])
        self.assertEqual((after["recovery_attempts"], after["budget_resets"]), (3, 1))

    def test_the_engines_it_builds_cannot_send(self):
        engine = rescan.Engine(None, LocalSource(self.codex.root), None)
        self.assertIsNone(engine.backend)
        self.assertIsNone(engine.store)

    def test_a_record_of_a_home_no_longer_in_settings_is_unresolved(self):
        row = self.fail()
        self.write("UPDATE interruptions SET home_key=? WHERE interruption_id=?", "c" * 64, row["interruption_id"])
        self.person()
        self.assertEqual(self.outcome(self.run_rescan(), row["interruption_id"]), ("unresolved", "home_unknown"))

    def test_records_not_reached_in_time_are_unresolved(self):
        row = self.fail()
        self.person()
        self.assertEqual(self.outcome(self.run_rescan(self.judge(seconds=-1)), row["interruption_id"]),
                         ("unresolved", "out_of_time"))


class AnswerTests(RescanCase):
    def test_each_outcome_is_counted_and_journalled_in_its_own_word(self):
        retired = self.fail()
        self.person()
        rechecked = self.fail(OTHER)
        third = "0a1b2c3d-0039-7000-8000-000000000003"
        unresolved = self.fail(third)
        self.person(third, user_text=None)
        result = self.run_rescan()
        self.assertEqual({name: result[name] for name in ("retired", "rechecked", "unresolved", "changed")},
                         {"retired": 1, "rechecked": 1, "unresolved": 1, "changed": 0})
        for row, word in ((retired, "rescan_retired"), (rechecked, "rescan_rechecked"),
                          (unresolved, "rescan_unresolved")):
            self.assertEqual(self.events(row["interruption_id"])[-1], word)

    def test_the_timeline_keeps_the_code_of_a_record_left_as_it_was(self):
        row = self.fail()
        self.run_rescan()
        events = self.control.timeline(row["interruption_id"])["events"]
        self.assertEqual(events[-1]["code"], "rescan_rechecked")
        self.assertEqual(events[-1]["to_code"], events[-2]["to_code"])

    def test_the_bridge_answers_with_no_argument(self):
        row = self.fail()
        self.person()
        reply = controlcli.dispatch(self.control, "rescan", {})
        self.assertTrue(reply["ok"], reply)
        self.assertEqual(reply["result"]["retired"], 1)
        self.assertEqual(self.record(row["interruption_id"])["state"], "superseded_by_user")
        self.assertIn("rescan", controlcli.PLAIN)
        self.assertNotIn("rescan", controlcli.WITH_ARGUMENT)

    def test_nothing_waiting_is_not_an_error(self):
        result = self.run_rescan()
        self.assertEqual((result["scanned"], result["records"]), (0, []))

    def test_no_bulk_retry_hides_inside_it(self):
        """It brings nothing forward: no Retry now for everything, which the layer never offers."""
        row = self.fail()
        before = self.record(row["interruption_id"])
        self.run_rescan()
        after = self.record(row["interruption_id"])
        self.assertEqual((after["next_retry_at"], after["retry_now_count"]),
                         (before["next_retry_at"], before["retry_now_count"]))
        self.assertNotIn("retry_now", self.events(row["interruption_id"]))


class ScanTests(unittest.TestCase):
    """codex/rollout.py `superseded_in` on files of its own."""

    def setUp(self):
        import tempfile
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "rollout.jsonl"

    def scan(self, *events, raw=b""):
        self.path.write_bytes(b"".join(json.dumps(event).encode("utf-8") + b"\n" for event in events) + raw)
        return rollout.superseded_in(self.path, "t-1")

    def test_the_five_answers(self):
        end = RescanCase.task_complete("t-1")
        person = RescanCase.user_message()
        self.assertEqual(self.scan(end, person), rollout.LATER_MESSAGE)
        self.assertEqual(self.scan(person, end), rollout.NOTHING_LATER)
        self.assertEqual(self.scan(person), rollout.NO_ANCHOR)
        self.assertEqual(rollout.superseded_in(self.path, "t-1", limit=4), rollout.TOO_LARGE)
        self.assertEqual(rollout.superseded_in(self.path.with_name("missing.jsonl"), "t-1"), rollout.UNREADABLE)

    def test_another_turns_end_is_no_anchor(self):
        self.assertEqual(self.scan(RescanCase.task_complete("t-2"), RescanCase.user_message()), rollout.NO_ANCHOR)

    def test_broken_lines_are_passed_over(self):
        end = RescanCase.task_complete("t-1")
        self.assertEqual(self.scan(end, raw=b'{"type":"event_msg", broken\n\xff\xfe"event_msg"\n'),
                         rollout.NOTHING_LATER)


if __name__ == "__main__":
    unittest.main()
