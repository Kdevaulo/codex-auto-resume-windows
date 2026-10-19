"""The advanced state's version 8 (v0.6.17, the owner's decision of 2026-10-18): `options` without the CHECK on its names
- the code alone keeps a name it does not know out, and passes one over that a later version wrote - and the
readable-from mark (schema.READABLE_FROM), by which a reader uses a later version's file that says it may, and still
refuses one marked newer than itself. A version-7 file - v0.6.16's - is brought to it with every row kept, once, and a
run cut short leaves version 7 as it was. The way down: v0.6.16 predates the mark, refuses the file as newer and writes
nothing to it.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sqlite3  # noqa: E402

import advancedcase as ac  # noqa: E402
from codex_auto_resume import config  # noqa: E402
from test_advanced_state import StateCase  # noqa: E402
from codex_auto_resume_advanced.registry import Option, Registry, RegistryError  # noqa: E402
from codex_auto_resume_advanced.state import AdvancedState, Refused, StateError, session  # noqa: E402
from codex_auto_resume_advanced.state import schema as schema_module  # noqa: E402
from codex_auto_resume_advanced.vocabulary import (Actor, ArmingState, KeepOn, OptionKey,  # noqa: E402
                                                   Refusal)

ROOT = Path(__file__).resolve().parents[2]
UNKNOWN = "tries"                                   # a name no version's vocabulary holds
MARKED_7 = schema_module.MARK | 7


def dump(path) -> dict:
    """Every row of every table, sorted: what "every row kept" compares."""
    with contextlib.closing(sqlite3.connect(path)) as connection:
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {name: sorted(map(tuple, connection.execute("SELECT * FROM %s" % name)), key=repr) for name in names}


def header(path) -> tuple:
    with contextlib.closing(sqlite3.connect(path)) as connection:
        return (connection.execute("PRAGMA user_version").fetchone()[0],
                connection.execute("PRAGMA application_id").fetchone()[0],
                connection.execute("SELECT sql FROM sqlite_master WHERE name='options'").fetchone()[0])


class V8Case(StateCase):
    def definition(self, **changes):
        fields = dict(options=(Option(OptionKey.ATTEMPTS, (1, 2, 3), 1),))
        fields.update(changes)
        return ac.definition(**fields)

    def opened(self):
        """The file opened once - a read - and closed: what brings it to this version."""
        state = self.state(self.definition())
        state.arming()
        state.close()

    def version_seven(self):
        """A file exactly as v0.6.16 made it - version 7, no mark, `options` with its CHECK on names - holding a row in
        `arming`, `options` (a choice and Keep it on), `spend`, `journal`, `wordings` and `chat_messages`."""
        self.paths.advanced_dir.mkdir(parents=True)
        (self.paths.advanced_dir / config.OWNER_MARKER).write_text(config.OWNER_TEXT, encoding="utf-8")
        path = self.paths.advanced_dir / schema_module.FILE_NAME
        with contextlib.closing(sqlite3.connect(path)) as connection:
            for statement in schema_module.STATEMENTS_V7:
                connection.execute(statement)
            connection.execute("INSERT INTO arming VALUES ('test_wake','armed',?,'dashboard',NULL,1,NULL,NULL)",
                               (self.now,))
            connection.execute("INSERT INTO options VALUES ('test_wake', 'attempts', 3)")
            connection.execute("INSERT INTO options VALUES ('test_wake', 'keep_on', 1)")
            connection.execute("INSERT INTO spend (at, capability, thread_id) VALUES (?, 'test_wake', ?)",
                               (self.now, ac.THREAD))
            connection.execute("INSERT INTO journal (at, code) VALUES (?, 'other')", (self.now,))
            connection.execute("INSERT INTO wordings VALUES ('usage_wrap_up', 'wrap_custom_weekly', 'Stop soon.', 1.0)")
            connection.execute("INSERT INTO chat_messages (thread_id, words, state, record_id, created_at) "
                               "VALUES (?, 'mine', 'waiting', ?, 1.0)", (ac.THREAD, "%064x" % 5))
            connection.commit()
            with self.assertRaises(sqlite3.IntegrityError, msg="version 7's CHECK on names"):
                connection.execute("INSERT INTO options VALUES ('test_wake', ?, 1)", (UNKNOWN,))
        self.assertEqual(header(path)[:2], (7, 0))
        return path


class UpgradeTests(V8Case):
    def test_a_version_seven_file_is_brought_to_eight_and_keeps_every_row(self):
        """Fails with the step reverted: the file is refused, every capability off."""
        path = self.version_seven()
        before = dump(path)
        state = self.state(self.definition())
        self.assertEqual(state.arming()["test_wake"]["state"], ArmingState.ARMED)
        self.assertTrue(state.arming()["test_wake"]["keep_on"])
        self.assertEqual(state.options("test_wake"), {OptionKey.ATTEMPTS: 3})
        state.close()
        version, mark, options = header(path)
        self.assertEqual((version, mark), (schema_module.SCHEMA_VERSION, MARKED_7))
        self.assertEqual(schema_module.SCHEMA_VERSION, 8)
        self.assertNotIn("choice IN", options)
        self.assertEqual(dump(path), before, "every row of every table kept, and no table more or less")
        with contextlib.closing(sqlite3.connect(path)) as connection:
            self.assertEqual(AdvancedState._tables(connection), schema_module.TABLES)
            connection.execute("INSERT INTO options VALUES ('test_wake', ?, 1)", (UNKNOWN,))   # no CHECK on names
            with self.assertRaises(sqlite3.IntegrityError, msg="the value's CHECK stays"):
                connection.execute("INSERT INTO options VALUES ('test_wake', 'workers', 0)")

    def test_a_new_file_is_version_eight_marked_and_without_the_check(self):
        state = self.state(self.definition())
        state.move("test_wake", ArmingState.SHADOW, actor=Actor.DASHBOARD, revision=1)
        state.close()
        version, mark, options = header(state.path)
        self.assertEqual((version, mark), (schema_module.SCHEMA_VERSION, MARKED_7))
        self.assertNotIn("choice IN", options)

    def test_the_step_runs_once(self):
        """Opened again, the file is left as the first opening made it: no step is taken twice."""
        path = self.version_seven()
        self.opened()
        after = (dump(path), header(path))
        with patch.object(session, "UPGRADE_FROM_7", ("SELECT no_such_column FROM options",)):
            again = self.state(self.definition())
            self.assertEqual(again.options("test_wake"), {OptionKey.ATTEMPTS: 3})
            again.close()
        self.assertEqual((dump(path), header(path)), after)

    def test_a_run_cut_short_leaves_version_seven_and_is_taken_again(self):
        """The step is taken in the opening's one transaction: cut short after `options` was dropped, the file is version
        7 as v0.6.16 left it, every row there; the next opening takes the step whole."""
        path = self.version_seven()
        before = dump(path)
        steps = schema_module.UPGRADE_FROM_7
        cut = steps[:3] + ("INSERT INTO no_such_table VALUES (1)",) + steps[3:]       # after the DROP TABLE options
        self.assertTrue(steps[2].startswith("DROP TABLE options"))
        with patch.object(session, "UPGRADE_FROM_7", cut):
            with self.assertRaises(StateError):
                self.state(self.definition()).arming()
        version, mark, options = header(path)
        self.assertEqual((version, mark), (7, 0))
        self.assertIn("choice IN", options)
        self.assertEqual(dump(path), before)
        state = self.state(self.definition())
        self.assertEqual(state.options("test_wake"), {OptionKey.ATTEMPTS: 3})
        state.close()
        self.assertEqual(header(path)[:2], (schema_module.SCHEMA_VERSION, MARKED_7))
        self.assertEqual(dump(path), before)


class NameTests(V8Case):
    def test_a_name_the_vocabulary_does_not_hold_is_refused_by_the_code(self):
        """With no CHECK on names, the code is what refuses one, twice: the registry takes no capability offering a
        choice the vocabulary does not hold (registry._option_problem), and were one let through, set_option still
        stores nothing under it. Fails with the vocabulary's check in set_option reverted: the row is written."""
        offering = self.definition(options=(Option(UNKNOWN, (1, 2, 3), 1),))
        with self.assertRaises(RegistryError):
            Registry((offering,))
        state = AdvancedState(self.paths, registry=SimpleNamespace(
            get=lambda capability: offering if capability == "test_wake" else None), clock=lambda: self.now)
        self.addCleanup(state.close)
        state.move("test_wake", ArmingState.SHADOW, actor=Actor.DASHBOARD, revision=1)
        with self.assertRaises(Refused) as raised:
            state.set_option("test_wake", UNKNOWN, 2, generation=state.meta()["generation"], actor=Actor.DASHBOARD)
        self.assertEqual(raised.exception.refusal, Refusal.OPTION_INVALID)
        with self.assertRaises(Refused):
            state.set_option("test_wake", OptionKey.WORKERS, 2, generation=state.meta()["generation"],
                             actor=Actor.DASHBOARD)                     # a word it holds, not offered here
        with contextlib.closing(sqlite3.connect(state.path)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM options").fetchone()[0], 0)

    def test_a_name_a_later_version_wrote_is_passed_over(self):
        """A row under a name this version does not know - a later version's choice - is read past: the choices are
        the defaults and the stored ones offered, Keep it on reads from its own words only. Fails with version 8's step
        reverted: the file refuses the row."""
        path = self.version_seven()
        self.opened()
        with contextlib.closing(sqlite3.connect(path)) as connection:
            connection.execute("INSERT INTO options VALUES ('test_wake', ?, 2)", (UNKNOWN,))
            connection.execute("INSERT INTO options VALUES ('test_wake', 'a_later_choice', 1)")
            connection.commit()
        state = self.state(self.definition())
        self.assertEqual(state.options("test_wake"), {OptionKey.ATTEMPTS: 3})
        found = state.arming()["test_wake"]
        self.assertEqual((found["keep_on"], found["send_again"]), (True, False))
        state.set_keep_on("test_wake", False, actor=Actor.DASHBOARD, generation=state.meta()["generation"])
        state.close()
        with contextlib.closing(sqlite3.connect(path)) as connection:
            kept = {row[0] for row in connection.execute("SELECT choice FROM options")}
        self.assertEqual(kept, {"attempts", UNKNOWN, "a_later_choice"}, "a later version's rows are left as they are")
        self.assertNotIn(str(KeepOn.KEEP_ON), kept)

    def test_the_frozen_names_are_the_vocabularys_at_version_seven(self):
        """V7_OPTION_WORDS is what v0.6.16's CHECK named: every word of it is still the vocabulary's."""
        self.assertEqual(set(schema_module.V7_OPTION_WORDS) - {str(word) for word in (*OptionKey, *KeepOn)}, set())


class MarkTests(V8Case):
    def later(self, readable, *, extra=True):
        """This version's file as a later version (9) would leave it, marked readable from `readable`: with a table of
        its own and a column at the end of `journal`, each holding a row."""
        state = self.state(self.definition())
        state.move("test_wake", ArmingState.SHADOW, actor=Actor.DASHBOARD, revision=1)
        state.close()
        with contextlib.closing(sqlite3.connect(state.path)) as connection:
            if extra:
                connection.execute("CREATE TABLE later_things (thing TEXT)")
                connection.execute("INSERT INTO later_things VALUES ('kept')")
                connection.execute("ALTER TABLE journal ADD COLUMN later TEXT")
                connection.execute("UPDATE journal SET later='kept'")
            connection.execute("PRAGMA application_id=%d" % (schema_module.MARK | readable))
            connection.execute("PRAGMA user_version=%d" % (schema_module.SCHEMA_VERSION + 1))
            connection.commit()
        return state.path

    def test_a_later_file_marked_readable_from_this_version_is_used_as_it_is(self):
        """Read and written, with nothing upgraded and nothing taken away: its version, its mark, its table and column
        stay. Fails with the mark not honoured: the file is refused as newer."""
        path = self.later(schema_module.SCHEMA_VERSION)
        state = self.state(self.definition())
        self.assertEqual(state.arming()["test_wake"]["state"], ArmingState.SHADOW)
        state.move("test_wake", ArmingState.OFF, actor=Actor.DASHBOARD)
        state.set_option("test_wake", OptionKey.ATTEMPTS, 2, generation=state.meta()["generation"],
                         actor=Actor.DASHBOARD)
        state.close()
        self.assertEqual(header(path)[:2], (schema_module.SCHEMA_VERSION + 1,
                                            schema_module.MARK | schema_module.SCHEMA_VERSION))
        with contextlib.closing(sqlite3.connect(path)) as connection:
            self.assertEqual(connection.execute("SELECT thing FROM later_things").fetchall(), [("kept",)])
            self.assertEqual(connection.execute("SELECT state FROM arming").fetchall(), [("off",)])
            self.assertIn("later", AdvancedState._tables(connection)["journal"])

    def test_an_older_reader_honours_the_mark(self):
        """A version-7 reader that reads the mark uses this version's file (marked readable from 7) and refuses one
        marked readable from 8 only - as each later reader will judge a file newer than itself."""
        state = self.state(self.definition())
        state.move("test_wake", ArmingState.SHADOW, actor=Actor.DASHBOARD, revision=1)
        state.close()
        with patch.object(session, "SCHEMA_VERSION", 7):
            older = self.state(self.definition())
            self.assertEqual(older.arming()["test_wake"]["state"], ArmingState.SHADOW)
            older.close()
            with contextlib.closing(sqlite3.connect(state.path)) as connection:
                connection.execute("PRAGMA application_id=%d" % (schema_module.MARK | 8))
                connection.commit()
            before = state.path.read_bytes()
            with self.assertRaises(StateError):
                self.state(self.definition()).arming()
            self.assertEqual(state.path.read_bytes(), before)

    def test_a_later_file_marked_newer_than_this_version_is_refused_and_left_untouched(self):
        path = self.later(schema_module.SCHEMA_VERSION + 1)
        before = path.read_bytes()
        for attempt in (lambda state: state.arming(),
                        lambda state: state.move("test_wake", ArmingState.ARMED, actor=Actor.DASHBOARD, revision=1)):
            with self.assertRaises(StateError):
                attempt(self.state(self.definition()))
        self.assertEqual(path.read_bytes(), before)

    def test_a_later_file_without_a_table_this_version_knows_is_refused(self):
        path = self.later(schema_module.SCHEMA_VERSION, extra=False)
        with contextlib.closing(sqlite3.connect(path)) as connection:
            connection.execute("DROP TABLE chat_messages")
            connection.commit()
        with self.assertRaises(StateError):
            self.state(self.definition()).arming()

    def test_without_a_mark_a_file_is_readable_from_its_own_version(self):
        with contextlib.closing(sqlite3.connect(":memory:")) as connection:
            self.assertEqual(schema_module.readable_from(connection, 9), 9)
            connection.execute("PRAGMA application_id=%d" % (0x12340000 | 7))      # somebody else's application id
            self.assertEqual(schema_module.readable_from(connection, 9), 9)
            connection.execute("PRAGMA application_id=%d" % MARKED_7)
            self.assertEqual(schema_module.readable_from(connection, 9), 7)


class DowngradeTests(V8Case):
    """v0.6.16 (version 7) reads no mark: `version > SCHEMA_VERSION` is refused as newer (its state/session.py:190).
    Every capability reads off there, nothing is written, and every row waits for this version."""

    def migrated(self):
        path = self.version_seven()
        self.opened()
        return path

    def test_v0_6_16s_gate_refuses_the_migrated_file_and_writes_nothing(self):
        """Its gate, as it is: version 7 and no mark read. Fails with the file kept at version 7 (the proposal): it is
        read."""
        path = self.migrated()
        before = path.read_bytes()
        with patch.object(session, "SCHEMA_VERSION", 7), \
                patch.object(session, "readable_from", lambda connection, version: version):
            older = self.state(self.definition())
            for attempt in (lambda: older.arming(), lambda: older.meta(),
                            lambda: older.move("test_wake", ArmingState.ARMED, actor=Actor.DASHBOARD, revision=1),
                            lambda: older.all_off(actor=Actor.DASHBOARD, reason="all_off")):
                with self.assertRaises(StateError):
                    attempt()
            older.close()
        self.assertEqual(path.read_bytes(), before)
        back = self.state(self.definition())
        self.assertEqual(back.options("test_wake"), {OptionKey.ATTEMPTS: 3})
        self.assertTrue(back.arming()["test_wake"]["keep_on"])

    def test_v0_6_16s_own_code_refuses_it_and_writes_nothing(self):
        """The same with v0.6.16's own sources, from its tag, in a process of their own: skipped where the tag is not
        in the checkout."""
        path = self.migrated()
        before = path.read_bytes()
        archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", "v0.6.16", "--",
                                  "src/codex_auto_resume", "advanced/src/codex_auto_resume_advanced"],
                                 capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if archive.returncode != 0:
            self.skipTest("the v0.6.16 tag is not in this checkout")
        with tempfile.TemporaryDirectory() as tree:
            with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
                tar.extractall(tree, filter="data")
            script = ("import sys\nsys.path[:0] = sys.argv[2:]\nfrom pathlib import Path\n"
                      "from codex_auto_resume import config\n"
                      "from codex_auto_resume_advanced.registry import Registry\n"
                      "from codex_auto_resume_advanced.state import AdvancedState, StateError\n"
                      "state = AdvancedState(config.Paths(Path(sys.argv[1])), registry=Registry(()), "
                      "clock=lambda: 1.8e9)\n"
                      "try:\n    state.arming()\n    print('read')\n"
                      "except StateError as exc:\n    print('refused: %s' % exc)\n")
            environment = dict(os.environ, CODEX_AR_EDITION="advanced")
            ran = subprocess.run([sys.executable, "-I", "-c", script, str(self.home), str(Path(tree) / "src"),
                                  str(Path(tree) / "advanced" / "src")], capture_output=True,
                                 text=True, env=environment, cwd=tree, timeout=120,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(ran.stdout.strip(), "refused: the advanced state was written by a newer version", ran.stderr)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
