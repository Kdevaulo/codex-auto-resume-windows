"""The advanced state's version 5 (v0.6.16-beta.3, issue #29): the usage meter's table, and `options` and
`continuations` made again with the meter's, the wrap-up's and the pause's words - a version-4 file brought to it with
every row kept, and the way down the way every earlier version has it.

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
from test_advanced_state import StateCase  # noqa: E402
from codex_auto_resume import config  # noqa: E402
from codex_auto_resume_advanced.state import AdvancedState, StateError  # noqa: E402
from codex_auto_resume_advanced.state import schema as schema_module  # noqa: E402

KEY = "%064x" % 4242


class VersionFiveTests(StateCase):
    def version_four(self):
        """A file exactly as v0.6.15 and v0.6.16-beta.2 made it - version 4, its `options` and `continuations`
        CHECKs without the words version 5 added - holding a choice and a continuation."""
        self.paths.advanced_dir.mkdir(parents=True)
        (self.paths.advanced_dir / config.OWNER_MARKER).write_text(config.OWNER_TEXT, encoding="utf-8")
        path = self.paths.advanced_dir / schema_module.FILE_NAME
        statements = (schema_module._STATEMENTS_V2 + schema_module._STATEMENTS_V3 + schema_module._STATEMENTS_V4
                      + ("PRAGMA user_version=4",))
        with contextlib.closing(sqlite3.connect(path)) as connection:
            for statement in statements:
                if statement.lstrip().startswith(("CREATE TABLE options", "CREATE TABLE continuations")):
                    for word in schema_module.V5_OPTION_WORDS + schema_module.V5_CONTINUATION_WORDS:
                        statement = statement.replace(", '%s'" % word, "")
                connection.execute(statement)
            connection.execute("INSERT INTO arming VALUES ('test_wake','shadow',?,'dashboard',NULL,1,NULL,NULL)",
                               (self.now,))
            connection.execute("INSERT INTO options VALUES ('test_wake', 'attempts', 2)")
            connection.execute("INSERT INTO continuations (answer_id, capability, kind, thread_id, chain, created_at) "
                               "VALUES (?, 'keep_going', 'keep_going', ?, 1, 1.0)", (KEY, ac.THREAD))
            connection.commit()
            with self.assertRaises(sqlite3.IntegrityError, msg="version 4's options CHECK"):
                connection.execute("INSERT INTO options VALUES ('test_wake', 'poll_minutes', 15)")
            with self.assertRaises(sqlite3.IntegrityError, msg="version 4's continuations CHECK"):
                connection.execute("INSERT INTO continuations (answer_id, capability, kind, thread_id, chain, "
                                   "created_at) VALUES (?, 'usage_wrap_up', 'wrap_up', ?, 1, 1.0)",
                                   ("%064x" % 1, ac.THREAD))
        return path

    def test_a_version_four_file_is_brought_to_five_and_keeps_every_row(self):
        path = self.version_four()
        state = self.state()
        self.assertEqual(state.arming()["test_wake"]["state"], "shadow")
        self.assertEqual(state.meter(), {})
        state.close()
        with contextlib.closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], schema_module.SCHEMA_VERSION)
            self.assertEqual(AdvancedState._tables(connection), schema_module.TABLES)
            self.assertEqual(connection.execute("SELECT * FROM options").fetchall(), [("test_wake", "attempts", 2)])
            self.assertEqual(connection.execute("SELECT answer_id FROM continuations").fetchall(), [(KEY,)])
            connection.execute("INSERT INTO options VALUES ('test_wake', 'poll_minutes', 15)")     # the new CHECKs
            connection.execute("INSERT INTO continuations (answer_id, capability, kind, thread_id, chain, created_at) "
                               "VALUES (?, 'usage_wrap_up', 'wrap_up', ?, 1, 1.0)", ("%064x" % 1, ac.THREAD))

    def test_the_way_down_is_every_capability_off_and_nothing_written(self):
        """A build that knows only version 4 refuses this file as newer - every capability reads as off - and
        writes nothing to it: held here by a build that knows one version fewer than the file has."""
        state = self.state()
        state.move("test_wake", "shadow", actor="dashboard", revision=1)
        # What only version 5 holds - a meter row - is in the file the older build is shown, and stays.
        self.assertEqual(state.save_meter([{"bucket": "codex", "window_minutes": 300, "used_percent": 91.0,
                                            "reset_at": 1_800_003_600}], at=self.now), 1)
        state.close()
        path = self.paths.advanced_dir / schema_module.FILE_NAME
        with contextlib.closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], schema_module.SCHEMA_VERSION)
            self.assertEqual(connection.execute("SELECT count(*) FROM meter").fetchone()[0], 1)
        before = path.read_bytes()
        from unittest.mock import patch
        from codex_auto_resume_advanced.state import session
        with patch.object(session, "SCHEMA_VERSION", schema_module.SCHEMA_VERSION - 1):
            older = AdvancedState(self.paths, registry=ac.Registry((ac.definition(),)), clock=lambda: self.now)
            self.addCleanup(older.close)
            with self.assertRaises(StateError):
                older.arming()
        self.assertEqual(path.read_bytes(), before)

    def test_the_meter_keeps_numbers_only_and_one_row_a_window(self):
        state = self.state()
        state.move("test_wake", "shadow", actor="dashboard", revision=1)
        windows = [{"bucket": "codex", "window_minutes": 300, "used_percent": 41.5, "reset_at": 1_800_003_600},
                   {"bucket": "codex", "window_minutes": 300, "used_percent": 42.0, "reset_at": 1_800_003_600},
                   {"bucket": "codex", "window_minutes": 10080, "used_percent": 7, "reset_at": None},
                   {"bucket": "nobody", "window_minutes": 300, "used_percent": 1, "reset_at": 1},
                   {"bucket": "codex", "window_minutes": 60, "used_percent": float("nan"), "reset_at": 1}]
        self.assertEqual(state.save_meter(windows, at=self.now), 2)
        self.assertEqual({key: row["used_percent"] for key, row in state.meter().items()},
                         {("codex", 300): 42.0, ("codex", 10080): 7.0})
        self.assertTrue(state.mark_meter("codex", 300, warned_reset_at=1_800_003_600, at=self.now))
        state.save_meter(windows[:1], at=self.now + 60)
        self.assertEqual(list(state.meter()), [("codex", 300)], "a window the reading no longer shows is gone")
        self.assertEqual(state.meter()[("codex", 300)]["warned_reset_at"], 1_800_003_600, "the marks are kept")


if __name__ == "__main__":
    unittest.main()
