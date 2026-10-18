"""P18 SESSIONS (v0.6.16-beta.4): a plug may ask core to watch the conversations of a terminal's Codex CLI and TUI
and of VS Code too, and every eligibility check core makes reads what it answered.

The standard edition watches the Codex app's own conversations alone (A15), and the NULL plug keeps it so. A plug that
names `cli` or `ide` makes those conversations detected, recovered and checked as the app's are - and a kind it no
longer names ends the waiting records of its conversations. A subagent's, an archived one and an `exec` session are
never eligible, whatever is named. The engine runs against codexsim with a plug of the test's own.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_engine import T1, T2, archive  # noqa: E402
from test_plug_points import Asked, PluggedCase  # noqa: E402
from unittest.mock import patch  # noqa: E402
from codex_auto_resume import machine  # noqa: E402
from codex_auto_resume.codex import LocalSource, eligibility  # noqa: E402
from codex_auto_resume.domain.plughands import SessionKind, kinds_of  # noqa: E402

CLI = {"source": "cli", "originator": "codex-tui"}
IDE = {"source": "vscode", "originator": "codex_vscode"}


def add_thread(home, thread_id, *, source, originator, thread_source="user", cli_version=None):
    """A conversation as a terminal's Codex TUI or VS Code records one - codexsim (v0.6.10's file) makes the app's -
    with the Codex version that wrote it on its first line where `cli_version` is given, as Codex writes it."""
    path = home.rollout(thread_id)
    meta = {"type": "session_meta", "payload": {"id": thread_id, "originator": originator, "source": source,
                                                "thread_source": thread_source}}
    if cli_version is not None:
        meta["payload"]["cli_version"] = cli_version
    path.write_bytes(json.dumps(meta).encode("utf-8") + b"\n")
    with home._db("state_5.sqlite") as db:
        db.execute("INSERT INTO threads (id, rollout_path, source, thread_source, archived, history_mode, name) "
                   "VALUES (?,?,?,?,0,'paginated',NULL)", (thread_id, str(path), source, thread_source))
    home.catch_up(thread_id)


class KindsAsked(Asked):
    """test_plug_points' plug, with P18's hook."""

    def sessions(self):
        return self._answer("sessions")


class KindsCase(PluggedCase):
    def failing(self, h, thread_id, kind):
        """A usage limit in a conversation of `kind` (a terminal's, VS Code's), past its reset, held by the app."""
        add_thread(h.home, thread_id, **kind)
        self.ready_after_reset(h, thread_id=thread_id)

    def watching(self, kinds, h=None):
        plug = KindsAsked(sessions=frozenset(kinds))
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
        add_thread(self.h.home, T1, thread_source="subagent", **CLI)
        self.ready_after_reset(self.h, thread_id=T1)
        add_thread(self.h.home, T2, **CLI)
        self.h.home.fail_usage(T2)
        archive(self.h.home, T2)
        self.h.tick()
        self.assertEqual(self.h.records(T1), [])
        self.assertEqual(self.h.records(T2), [])
        self.assertEqual(eligibility.row_problem({"source": "exec", "archived": 0, "thread_source": "user",
                                                  "history_mode": "paginated"}, frozenset({"cli", "ide"})),
                         "source exec")
        self.assertIsNone(eligibility.kind_of("cli", {"source": "cli", "originator": "codex_exec"},
                                              frozenset({"cli", "ide"})), "a codex exec run is never a person's TUI")

    def test_paused_it_is_not_asked(self):
        plug = self.watching({"cli"})
        self.h.store.set_enabled(False, self.h.now)
        self.h.tick()
        self.assertNotIn("sessions", plug.hooks())


class VersionSkewTests(KindsCase):
    """Design-4 4.3: a terminal's or VS Code's conversation whose first line says a Codex newer than the engine's
    `codex --version` wrote it waits, identity / version_newer_than_engine, and nothing is sent."""
    ENGINE = "codex-cli 0.162.0-alpha.17.2"

    def skewed(self, kind, written, *, named=("cli", "ide")):
        if named:
            self.watching(set(named))
        self.h.backend.engine_version = self.ENGINE
        add_thread(self.h.home, T1, cli_version=written, **kind)
        self.ready_after_reset(self.h, thread_id=T1)
        self.h.tick()
        return self.h.record(T1)

    def test_one_a_newer_codex_wrote_waits_and_nothing_is_sent(self):
        """Fails with the guard reverted: it would be sent to an engine older than what wrote it."""
        for kind, written in ((CLI, "0.163.0"), (IDE, "0.162.0")):
            with self.subTest(kind=kind["originator"]):
                self.setUp()
                row = self.skewed(kind, written)
                self.assertEqual((row["state"], row["last_error"]),
                                 ("waiting_for_loaded_thread", "version_newer_than_engine"))
                self.assertEqual(machine.decode_gates(row["gate_eval"])["identity"],
                                 (machine.WAIT, "version_newer_than_engine"))
                self.assertEqual(self.h.backend.send_calls, [])

    def test_one_the_same_or_an_older_codex_wrote_is_sent(self):
        for written in ("0.162.0-alpha.17.2", "0.161.0", None, "not a version"):
            with self.subTest(written=written):
                self.setUp()
                self.skewed(CLI, written)
                self.h.tick(advance=1)
                self.assertEqual(len(self.h.backend.send_calls), 1)

    def test_an_engine_version_that_cannot_be_read_holds_nothing_back(self):
        self.h.backend.engine_version = None
        self.watching({"cli"})
        add_thread(self.h.home, T1, cli_version="0.163.0", **CLI)
        self.ready_after_reset(self.h, thread_id=T1)
        self.h.tick()
        self.h.tick(advance=1)
        self.assertEqual(len(self.h.backend.send_calls), 1)

    def test_the_apps_own_conversation_is_never_held_and_with_no_kind_named_nothing_is_read(self):
        """The standard edition, which names no kind, reads no version: A15 and B6 as ever."""
        with patch.object(LocalSource, "written_by", side_effect=AssertionError("read with no kind named")):
            self.skewed({"source": "vscode", "originator": "Codex Desktop"}, "9.0.0", named=())
            self.h.tick(advance=1)
        self.assertEqual(len(self.h.backend.send_calls), 1)
        self.setUp()
        self.skewed({"source": "vscode", "originator": "Codex Desktop"}, "9.0.0")
        self.h.tick(advance=1)
        self.assertEqual(len(self.h.backend.send_calls), 1, "the app's own conversation is the app's to run")

    def test_versions_are_read_as_the_compatibility_data_reads_them(self):
        newer = eligibility.newer_than_engine
        self.assertTrue(newer("0.162.0", "codex-cli 0.162.0-alpha.17.2"), "a release after its pre-release")
        self.assertFalse(newer("0.162.0-alpha.17.2", "codex-cli 0.162.0"))
        self.assertTrue(newer("0.162.0-alpha.18", "codex-cli 0.162.0-alpha.17.2"))
        for written, engine in ((None, "codex-cli 0.1.0"), ("0.2.0", None), ("0.2.0", "something else"), (3, "x")):
            self.assertFalse(newer(written, engine))


class ShrinkTests(KindsCase):
    def test_a_kind_no_longer_named_cancels_its_waiting_records(self):
        plug = self.watching({"cli"})
        add_thread(self.h.home, T1, **CLI)
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


class RestartTests(KindsCase):
    """v0.6.16 (live acceptance item 8 e): a watcher that starts does not know what the one before it watched. A kind
    no longer named by then - turned off with the watcher stopped, the advanced edition entered again, the standard
    edition installed - ends the waiting records of its conversations as it would have in the running watcher:
    cancelled, session_kind_off. It used to leave them to the next check, which could no longer read the conversation
    and retired the record as superseded, latest_turn_changed - untrue of a conversation with one turn."""

    def waiting_cli(self):
        self.watching({"cli"})
        self.h.home.fail_usage(T1)       # the app's own, beside it
        add_thread(self.h.home, T2, **CLI)
        self.ready_after_reset(self.h, thread_id=T2, loaded=False)
        self.h.tick()
        self.assertEqual(self.h.record(T2)["state"], "waiting_for_loaded_thread")

    def restarted(self, plug):
        """A new watcher: a new reader, which watches the app's alone until its plug is asked, and a new engine."""
        self.h.source.session_kinds = frozenset()
        self.plugged(plug)

    def test_a_kind_no_longer_named_when_the_watcher_starts_is_cancelled_as_off(self):
        """Fails with the fix reverted: superseded, latest_turn_changed."""
        for plug in (KindsAsked(sessions=frozenset()), KindsAsked(sessions=frozenset({"ide"})), None):
            with self.subTest(plug=plug and sorted(plug.answers["sessions"])):
                self.setUp()
                self.waiting_cli()
                self.restarted(plug)
                self.h.tick(advance=60)    # the next check, past its poll
                row = self.h.record(T2)
                self.assertEqual((row["state"], row["last_error"]), ("cancelled", "session_kind_off"))
                self.assertNotEqual(self.h.record(T1)["state"], "cancelled", "the app's own record was ended")
                self.assertEqual(self.h.backend.send_calls, [])

    def test_a_kind_still_named_when_the_watcher_starts_keeps_waiting(self):
        self.waiting_cli()
        self.restarted(KindsAsked(sessions=frozenset({"cli"})))
        self.h.tick(advance=60)    # the next check, past its poll
        self.assertEqual(self.h.record(T2)["state"], "waiting_for_loaded_thread")


class AnswerTests(unittest.TestCase):
    def test_only_the_closed_words_are_taken(self):
        self.assertEqual(kinds_of(frozenset({"cli"})), frozenset({SessionKind.CLI}))
        self.assertEqual(kinds_of(("cli", "ide")), frozenset({SessionKind.CLI, SessionKind.IDE}))
        for answer in ("cli", ["cli"], {"cli", "desktop"}, {1}, None, object()):
            self.assertEqual(kinds_of(answer), frozenset(), answer)


if __name__ == "__main__":
    unittest.main()
