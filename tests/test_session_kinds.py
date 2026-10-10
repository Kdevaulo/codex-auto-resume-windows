"""P18 SESSIONS (v0.6.15-beta.3): a plug may ask core to watch the conversations of a terminal's Codex CLI and TUI
and of VS Code too, and every eligibility check core makes reads what it answered.

The standard edition watches the Codex app's own conversations alone (A15), and the NULL plug keeps it so. A plug that
names `cli` or `ide` makes those conversations detected, recovered and checked as the app's are - and a kind it no
longer names ends the waiting records of its conversations. A subagent's, an archived one and an `exec` session are
never eligible, whatever is named. The engine runs against codexsim with a plug of the test's own.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_engine import T1, T2, archive  # noqa: E402
from test_plug_points import Asked, PluggedCase  # noqa: E402
from codex_auto_resume.codex import eligibility  # noqa: E402
from codex_auto_resume.domain.plughands import SessionKind, kinds_of  # noqa: E402

CLI = {"source": "cli", "originator": "codex_cli_rs"}
IDE = {"source": "vscode", "originator": "codex_vscode"}


class KindsCase(PluggedCase):
    def failing(self, h, thread_id, kind):
        """A usage limit in a conversation of `kind` (a terminal's, VS Code's), past its reset, held by the app."""
        h.home.add_thread(thread_id, **kind)
        self.ready_after_reset(h, thread_id=thread_id)

    def watching(self, kinds, h=None):
        plug = Asked(sessions=frozenset(kinds))
        self.plugged(plug, h or self.h)
        return plug


class DetectionTests(KindsCase):
    def test_null_never_detects_a_terminal_or_vs_code_conversation(self):
        """Fails with the default widened: A15 would be broken in the standard edition."""
        self.failing(self.h, T1, CLI)
        self.failing(self.h, T2, IDE)
        self.h.tick()
        self.assertEqual(self.h.records(T1), [])
        self.assertEqual(self.h.records(T2), [])

    def test_cli_named_detects_cli_alone(self):
        self.watching({"cli"})
        self.failing(self.h, T1, CLI)
        self.failing(self.h, T2, IDE)
        self.h.tick()
        self.assertEqual(len(self.h.records(T1)), 1)
        self.assertEqual(self.h.records(T2), [])

    def test_a_named_kind_is_dispatched_and_not_superseded(self):
        """The review's finding: every eligibility check reads the kinds, valid_interruption's too."""
        self.watching({"cli"})
        self.failing(self.h, T1, CLI)
        self.h.tick()
        self.h.tick(advance=1)
        self.assertEqual(len(self.h.backend.send_calls), 1)
        self.assertNotIn(self.h.record(T1)["state"], ("superseded", "superseded_by_user"))

    def test_a_subagent_an_archived_one_and_an_exec_session_never(self):
        self.watching({"cli", "ide"})
        self.h.home.add_thread(T1, thread_source="subagent", **CLI)
        self.ready_after_reset(self.h, thread_id=T1)
        self.failing(self.h, T2, CLI)
        archive(self.h.home, T2)
        self.h.tick()
        self.assertEqual(self.h.records(T1), [])
        self.assertEqual(self.h.records(T2), [])
        self.assertFalse(eligibility.row_eligible({"source": "exec", "archived": 0, "thread_source": "user",
                                                   "history_mode": "paginated", "rollout_path": "x"},
                                                  frozenset({"cli", "ide"})))

    def test_paused_it_is_not_asked(self):
        plug = self.watching({"cli"})
        self.h.store.set_enabled(False, self.h.now)
        self.h.tick()
        self.assertNotIn("sessions", plug.hooks())


class ShrinkTests(KindsCase):
    def test_a_kind_no_longer_named_cancels_its_waiting_records(self):
        plug = self.watching({"cli"})
        self.h.home.add_thread(T1, **CLI)
        self.h.home.fail_usage(T1)
        self.h.tick()
        self.assertEqual(self.h.record(T1)["state"] in ("waiting_reset", "waiting_poll"), True)
        plug.answers["sessions"] = frozenset()
        self.h.tick(advance=1)
        row = self.h.record(T1)
        self.assertEqual((row["state"], row["last_error"]), ("cancelled", "session_kind_off"))

    def test_the_apps_own_records_are_untouched(self):
        plug = self.watching({"cli"})
        self.h.home.fail_usage(T2)
        self.h.tick()
        plug.answers["sessions"] = frozenset()
        self.h.tick(advance=1)
        self.assertNotEqual(self.h.record(T2)["state"], "cancelled")


class AnswerTests(unittest.TestCase):
    def test_only_the_closed_words_are_taken(self):
        self.assertEqual(kinds_of(frozenset({"cli"})), frozenset({SessionKind.CLI}))
        self.assertEqual(kinds_of(("cli", "ide")), frozenset({SessionKind.CLI, SessionKind.IDE}))
        for answer in ("cli", ["cli"], {"cli", "desktop"}, {1}, None, object()):
            self.assertEqual(kinds_of(answer), frozenset(), answer)


if __name__ == "__main__":
    unittest.main()
