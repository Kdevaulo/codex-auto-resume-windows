"""The advanced state's version 5 (v0.6.16-beta.4): a turn run here, Codex's own settings changed, the Dashboard's
chat - three tables added to version 4 and none remade, every row of an older file kept.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

import contextlib
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase as ac  # noqa: E402
from codex_auto_resume import config  # noqa: E402
from test_advanced_state import StateCase  # noqa: E402
from codex_auto_resume_advanced.state import StateError  # noqa: E402
from codex_auto_resume_advanced.state import schema as schema_module  # noqa: E402
from codex_auto_resume_advanced.vocabulary import ChatReason, ChatState, ConfigOutcome, RunEnd  # noqa: E402

KEY = "%064x" % 77
RECORD = "%064x" % 78
REQUEST = "model_providers.openai.request_max_retries"


class UpgradeTests(StateCase):
    def version_four(self):
        """A version-4 file as v0.6.15-beta and beta.2 make it, with a row in a table of each version."""
        self.paths.advanced_dir.mkdir(parents=True)
        (self.paths.advanced_dir / config.OWNER_MARKER).write_text(config.OWNER_TEXT, encoding="utf-8")
        path = self.paths.advanced_dir / schema_module.FILE_NAME
        with contextlib.closing(sqlite3.connect(path)) as connection:
            for statement in schema_module.STATEMENTS_V4:
                connection.execute(statement)
            connection.execute("INSERT INTO spend (at, capability, thread_id) VALUES (?, 'test_wake', ?)",
                               (self.now, ac.THREAD))
            connection.execute("INSERT INTO keep_going VALUES (?, 2, 0, ?, 'on', NULL, NULL)", (ac.THREAD, self.now))
            connection.commit()
        return path

    def test_a_version_four_file_is_brought_to_five_and_keeps_every_row(self):
        """Fails with the step from 4 reverted: the file would be refused, every capability off."""
        path = self.version_four()
        opened = self.state()
        opened.arming()
        self.assertEqual(opened.runs(live=False), [])
        opened.close()
        with contextlib.closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 5)
            self.assertEqual(connection.execute("SELECT count(*) FROM spend").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM keep_going").fetchone()[0], 1)
            for name in schema_module.V5_TABLES:
                self.assertEqual(connection.execute("SELECT count(*) FROM %s" % name).fetchone()[0], 0)

    def test_the_step_adds_and_remakes_nothing(self):
        self.assertTrue(all(statement.startswith(("CREATE TABLE", "CREATE INDEX", "PRAGMA"))
                            for statement in (s.strip() for s in schema_module.UPGRADE_FROM_4)))
        self.assertEqual(set(schema_module.TABLES) - set(schema_module.TABLES_V4), set(schema_module.V5_TABLES))

    def test_a_newer_version_is_refused(self):
        made = self.state()
        made.run_started(KEY, "headless_run", ac.THREAD, started_at=self.now, ends_by=self.now)
        made.close()
        with contextlib.closing(sqlite3.connect(made.path)) as connection:
            connection.execute("PRAGMA user_version=6")
            connection.commit()
        with self.assertRaises(StateError):
            self.state().arming()


class RunTests(StateCase):
    def test_a_run_is_written_stopped_and_ended(self):
        state = self.state()
        state.run_started(KEY, "headless_run", ac.THREAD, started_at=self.now, ends_by=self.now + 3600)
        self.assertEqual([row["interruption_id"] for row in state.runs()], [KEY])
        self.assertTrue(state.run_stop(KEY))
        self.assertIsNotNone(state.runs()[0]["stop_requested_at"])
        self.assertTrue(state.run_ended(KEY, RunEnd.INTERRUPTED))
        self.assertEqual(state.runs(), [])
        self.assertFalse(state.run_stop(KEY), "nothing to stop once it ended")

    def test_only_its_capabilities_and_ends_are_held(self):
        state = self.state()
        with self.assertRaises(StateError):
            state.run_started(KEY, "goal_continuation", ac.THREAD, started_at=self.now, ends_by=self.now)
        state.run_started(KEY, "headless_run", ac.THREAD, started_at=self.now, ends_by=self.now)
        with self.assertRaises(StateError):
            state.run_ended(KEY, "exploded")


class ConfigTests(StateCase):
    def test_the_prior_value_is_kept_and_a_second_write_keeps_the_first_prior(self):
        state = self.state()
        state.config_written(REQUEST, prior_present=True, prior_value=4, written_value=8)
        state.config_written(REQUEST, prior_present=True, prior_value=8, written_value=10)
        row = state.config_rows()[REQUEST]
        self.assertEqual((row["prior_present"], row["prior_value"], row["written_value"], row["outcome"]),
                         (1, 4, 10, ConfigOutcome.APPLIED))
        state.config_ended(REQUEST, ConfigOutcome.RESTORED)
        self.assertEqual(state.config_rows()[REQUEST]["outcome"], ConfigOutcome.RESTORED)

    def test_keys_outside_the_two_are_refused(self):
        state = self.state()
        with self.assertRaises(StateError):
            state.config_written("model", prior_present=False, prior_value=None, written_value=8)
        connection = sqlite3.connect(state.path)
        self.addCleanup(connection.close)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO codex_config VALUES ('model', 0, NULL, 8, 1, NULL, 'applied')")


class ChatTests(StateCase):
    def test_words_are_kept_only_while_a_message_waits(self):
        state = self.state()
        state.add_chat(ac.THREAD, "my own words", RECORD)
        self.assertEqual(state.chats()[0]["words"], "my own words")
        self.assertTrue(state.chat_sent(RECORD))
        found = state.chats()[0]
        self.assertEqual((found["state"], found["words"]), (ChatState.IN_FLIGHT, None))
        self.assertTrue(state.chat_ended(RECORD, "delivered"))
        self.assertEqual(state.chats()[0]["reason"], ChatReason.DELIVERED)

    def test_the_file_refuses_words_on_a_message_not_waiting(self):
        state = self.state()
        state.add_chat(ac.THREAD, "mine", RECORD)
        state.chat_sent(RECORD)
        connection = sqlite3.connect(state.path)
        self.addCleanup(connection.close)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("UPDATE chat_messages SET words='back again'")

    def test_a_cancel_takes_the_words_with_it(self):
        state = self.state()
        state.add_chat(ac.THREAD, "mine", RECORD)
        self.assertEqual(state.cancel_chat(ChatReason.CANCELLED, record_id=RECORD), 1)
        found = state.chats()[0]
        self.assertEqual((found["state"], found["words"]), (ChatState.CANCELLED, None))

    def test_over_two_thousand_characters_is_refused(self):
        with self.assertRaises(StateError):
            self.state().add_chat(ac.THREAD, "x" * 2001, RECORD)


if __name__ == "__main__":
    unittest.main()
