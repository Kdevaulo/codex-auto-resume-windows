"""Why a failed turn was not taken up, said once per turn and reason (v0.6.16-beta.3, asked for in issue #27).

Every place the watcher passes a failed turn over writes one line saying why - not on every check - and a
line saying how many failed turns a check saw whenever that number changes. The lines carry codes, ids and
the kind words Codex itself uses, and nothing of a conversation: no title, message or prompt.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
import tempfile
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codexsim import BASE, new_id, transient_error  # noqa: E402
from codex_auto_resume import logbook, settings  # noqa: E402
from codex_auto_resume.domain import skips  # noqa: E402
from test_continuation_split import SplitHome  # noqa: E402
from test_engine import Harness  # noqa: E402

T1 = "0a1b2c3d-0003-7000-8000-000000000001"
T2 = "0a1b2c3d-0003-7000-8000-000000000002"
SECRET = "a secret prompt nobody may log"


class SkipCase(unittest.TestCase):
    def harness(self, *, enable=True, home=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        h = Harness(root / "state", home=home(root / "codex-home") if home else None)
        self.addCleanup(h.close)
        if enable:
            h.enable()
        return h

    @staticmethod
    def skips(h, thread_id=None):
        return [entry[2][1:] for entry in h.logs if entry[1] == "not_taken_up"
                and (thread_id is None or entry[0] == thread_id)]

    @staticmethod
    def seen(h):
        return [entry[2] for entry in h.logs if entry[1] == "failed_turns_seen"]

    def ticks(self, h, count=3):
        for _ in range(count):
            h.tick(advance=30)


class SkipReasonTests(SkipCase):
    def test_another_kind_of_conversation_is_said_once_with_its_kind(self):
        h = self.harness()
        h.home.add_thread(T1, thread_source="subagent")
        h.home.fail_usage(T1)
        self.ticks(h)
        self.assertEqual(self.skips(h, T1), [(skips.OTHER_KIND, "thread_source subagent")])
        self.assertIsNone(h.record(T1))

    def test_an_archived_conversation_says_so(self):
        h = self.harness()
        h.home.fail_usage(T1)
        with h.home._db("state_5.sqlite") as db:
            db.execute("UPDATE threads SET archived=1 WHERE id=?", (T1,))
        self.ticks(h)
        self.assertEqual(self.skips(h, T1), [(skips.OTHER_KIND, "archived")])

    def test_a_failure_before_the_look_back_window_is_said_once(self):
        h = self.harness()
        h.home.fail_usage(T1, completed=int(BASE - 8 * 3600))
        self.ticks(h)
        self.assertEqual(self.skips(h, T1), [(skips.BEFORE_WINDOW, None)])

    def test_a_failure_a_newer_turn_came_after_is_said_once(self):
        h = self.harness()
        h.home.fail_transient(T1)
        h.home.add_turn(T1, status="completed")
        self.ticks(h)
        self.assertEqual(self.skips(h, T1), [(skips.NEWER_TURN, None)])

    def test_a_kind_it_does_not_recover_is_said_with_the_kind(self):
        h = self.harness()
        h.home.add_turn(T1, status="failed", error_json=json.dumps({"codexErrorInfo": "badRequest", "message": SECRET}),
                        progress=False)
        self.ticks(h)
        found = self.skips(h, T1)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][0], skips.NOT_RECOVERED)
        self.assertNotIn("secret", repr(h.logs))

    def test_a_conversation_switched_off_is_said_once(self):
        h = self.harness()
        h.home.fail_usage(T1)
        h.store.set_thread_enabled(T1, False)
        self.ticks(h)
        self.assertEqual(self.skips(h, T1), [(skips.CONVERSATION_OFF, None)])
        self.assertIsNone(h.record(T1))

    def test_a_kind_switched_off_in_settings_is_said_once(self):
        h = self.harness()
        h.engine.apply_policy(dict(settings.defaults(), recover_server_5xx=False))
        h.home.fail_transient(T1, code="serverOverloaded")
        self.ticks(h)
        self.assertEqual(self.skips(h, T1), [(skips.CATEGORY_OFF, "server_5xx")])
        self.assertEqual(h.codes(T1).count("category_recovery_disabled"), 1)

    def test_an_unknown_conversation_id_is_said_once(self):
        h = self.harness()
        h.home.fail_usage(T1)
        with h.home._db("state_5.sqlite") as db:
            db.execute("DELETE FROM threads WHERE id=?", (T1,))
        self.ticks(h)
        self.assertEqual(self.skips(h, T1), [(skips.UNKNOWN_CONVERSATION, None)])

    def test_an_old_failure_with_a_newer_turn_under_another_id_says_so(self):
        h = self.harness(home=SplitHome)
        h.home.fail_transient(T1)
        h.home.rotate(T1)
        h.home.add_turn(T1, status="completed")
        self.ticks(h)
        self.assertEqual(self.skips(h, T1), [(skips.NEWER_TURN, None)])

    def test_automatic_recovery_off_is_said_once_each_time_it_is_found_off(self):
        h = self.harness(enable=False)
        h.home.fail_usage(T1)
        self.ticks(h)
        self.assertEqual(h.codes(None).count(skips.RECOVERY_OFF), 1)
        h.enable()
        h.tick(advance=30)
        h.store.set_enabled(False, h.now)
        self.ticks(h)
        self.assertEqual(h.codes(None).count(skips.RECOVERY_OFF), 2)

    def test_a_failure_taken_up_is_said_nothing_of(self):
        h = self.harness()
        h.home.fail_usage(T1)
        self.ticks(h)
        self.assertIsNotNone(h.record(T1))
        self.assertEqual(self.skips(h), [])

    def test_the_number_of_failed_turns_seen_is_said_when_it_changes(self):
        h = self.harness()
        self.ticks(h)
        self.assertEqual(self.seen(h), ["0"])
        h.home.fail_usage(T1)
        h.home.add_thread(T2, thread_source="subagent")
        h.home.fail_transient(T2)
        self.ticks(h)
        self.assertEqual(self.seen(h), ["0", "2"])


class SkipLineTests(unittest.TestCase):
    """What the log file gets: one line, its codes and ids, and nothing of a conversation."""

    def test_the_line_names_the_turn_the_reason_and_the_kind_and_reads_back(self):
        records = []

        class Keep(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())
        logger = logging.getLogger("test_skip_reasons")
        logger.propagate = False
        handler = Keep()
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        logger.setLevel(logging.INFO)
        turn = new_id()
        logbook.EngineLog(logger)(T1, "not_taken_up", (turn, skips.OTHER_KIND, "thread_source subagent"))
        self.assertEqual(len(records), 1)
        line = records[0]
        self.assertTrue(line.startswith("thread %s: failed turn %s not taken up (other_kind: thread_source subagent)"
                                        % (T1, turn)), line)
        found = logbook.SKIP_LINE.search(line).groupdict()
        self.assertEqual((found["thread"], found["turn"], found["reason"], found["kind"]),
                         (T1, turn, skips.OTHER_KIND, "thread_source subagent"))

    def test_a_kind_word_that_is_not_plain_is_never_printed(self):
        self.assertEqual(skips.kind("{\"subagent\": {\"parent\": 1}}"), "subagent")
        self.assertEqual(skips.kind(SECRET), "other")
        self.assertEqual(skips.kind(None), "none")
        line = logbook.skipped(T1, new_id(), skips.OTHER_KIND, SECRET + "\nmore")
        self.assertNotIn("secret", line)
        self.assertNotIn(transient_error(), line)


if __name__ == "__main__":
    unittest.main()
