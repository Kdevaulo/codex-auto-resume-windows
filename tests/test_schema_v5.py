"""State schema 5 (v0.6.15-beta): which Codex home a record is of, and what the watcher found of each home.

One column on a record - `home_key`, '' for the default home, which is every record there was, else the
SHA-256 an extra home's lock is named by - and one on the heartbeat, `homes`. A migrated state means what
it meant; an id of the default home is the id it always was, and the same conversation in two homes is
two records; `downgrade-state --to 4` gives v0.6.11 to v0.6.14 a state they read, keeping every row
and leaving none of another home for them to act on. Temporary folders only.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import machine  # noqa: E402
from codex_auto_resume.domain import ids  # noqa: E402
from codex_auto_resume.store import SCHEMA_VERSION, Store, StoreError, downgrade_state  # noqa: E402
from codex_auto_resume.store.watcher import MAX_HOMES, homes_read, homes_text  # noqa: E402

import released  # noqa: E402

THREAD = "0a1b2c3d-0001-7000-8000-000000000001"
TURN = "0a1b2c3d-0002-7000-8000-000000000002"
OTHER_TURN = "0a1b2c3d-0002-7000-8000-000000000003"
HOME_B = "b" * 64
HOME_C = "c" * 64


def detection(key, turn=TURN, ordinal=2):
    return {"thread_id": THREAD, "turn_id": turn, "completed_at": 110.0, "started_at": 105.0,
            "ordinal": ordinal, "interruption_id": key, "reset_at": None, "limit_type": "x",
            "uncertain": False, "category": "server_5xx"}


def key_of(home_key="", turn=TURN, ordinal=2):
    return ids.interruption_id(THREAD, turn, 110.0, ordinal, home_key=home_key)


class Case(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / "state"

    def db(self):
        return closing(sqlite3.connect(self.root / "state.sqlite"))


class SchemaTests(Case):
    def test_a_fresh_state_is_schema_5_and_every_record_is_the_default_homes(self):
        self.assertEqual(SCHEMA_VERSION, 5)
        with Store(self.root) as store:
            self.assertEqual(store.schema_version(), 5)
            store.register(detection(key_of()), 120.0)
            self.assertEqual(store.get(key_of())["home_key"], "")

    def test_the_check_refuses_a_key_that_is_not_one(self):
        with Store(self.root) as store:
            store.register(detection(key_of()), 120.0)
        for bad in ("abc", "B" * 64, "g" * 64, "b" * 63):
            with self.subTest(bad), self.db() as db, self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE interruptions SET home_key=?", (bad,))

    def test_the_store_refuses_one_too(self):
        with Store(self.root) as store, self.assertRaises(StoreError):
            store.register(detection(key_of()), 120.0, home_key="ABC")

    def test_one_conversation_in_two_homes_is_two_records(self):
        default, other = key_of(), key_of(HOME_B)
        self.assertNotEqual(default, other)
        with Store(self.root) as store:
            self.assertTrue(store.register(detection(default), 120.0))
            # The same turn of the same conversation, in another home: not an identity drift.
            self.assertTrue(store.register(detection(other), 120.0, home_key=HOME_B))
            self.assertEqual({row["interruption_id"]: row["home_key"] for row in store.all_records()},
                             {default: "", other: HOME_B})
            # Within one home, the same turn under another id still is one.
            drifted = ids.interruption_id(THREAD, TURN, 111.0, 2, home_key=HOME_B)
            self.assertFalse(store.register(dict(detection(drifted), completed_at=111.0), 120.0, home_key=HOME_B))

    def test_a_schema_4_state_comes_up_with_every_row_and_nothing_moved(self):
        with Store(self.root) as store:
            store.set_enabled(True, 100.0)
            store.register(detection(key_of()), 120.0)
        downgrade_state(self.root, 4)
        with self.db() as db:
            db.row_factory = sqlite3.Row
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 4)
            before = {row["interruption_id"]: dict(row) for row in db.execute("SELECT * FROM interruptions")}
        with Store(self.root, migrate=True) as store:
            self.assertEqual((store.migrated_from, store.schema_version()), (4, 5))
            self.assertEqual([event["code"] for event in store.events()].count("migrated"), 1)
            after = {row["interruption_id"]: row for row in store.all_records()}
        for key, row in before.items():
            self.assertEqual({name: after[key][name] for name in row if name != "uncertain"},
                             {name: value for name, value in row.items() if name != "uncertain"})
            self.assertEqual(after[key]["home_key"], "")
        self.assertEqual(len(list(self.root.glob("state.v4-backup-*.sqlite"))), 1, "a forensic copy first")


class HomesTests(Case):
    def test_what_the_heartbeat_keeps_is_bounded_ids_and_closed_words(self):
        two = [{"key": "", "state": "watched"}, {"key": HOME_B, "state": "lock_busy"}]
        self.assertEqual(homes_read(homes_text(two)), two)
        too_many = [{"key": "", "state": "watched"}] + [
            {"key": letter * 64, "state": "watched"} for letter in "abcd"]
        self.assertEqual(len(too_many), MAX_HOMES + 1)
        for refused in (None, [], two[:1], too_many, [two[0], two[0]],
                        [two[0], {"key": HOME_B, "state": "on fire"}],
                        [two[0], {"key": "C:\\Users\\ExampleUser\\.codex", "state": "watched"}],
                        [two[0], {"key": HOME_B, "state": "watched", "alias": "work"}]):
            with self.subTest(refused):
                self.assertIsNone(homes_text(refused))

    def test_the_heartbeat_writes_them_and_none_with_one_home(self):
        two = [{"key": "", "state": "watched"}, {"key": HOME_C, "state": "unavailable"}]
        with Store(self.root) as store:
            beat = dict(pid=1, session_id="s", started_at=100.0, ok=True, engine_state="verified",
                        code_version="0.6.15-beta")
            store.heartbeat(120.0, **beat, homes=two)
            self.assertEqual(store.watcher_status()["homes"], two)
            store.heartbeat(121.0, **beat)
            self.assertIsNone(store.watcher_status()["homes"])


class IdTests(unittest.TestCase):
    def test_the_default_homes_ids_are_what_they_were(self):
        self.assertEqual(ids.interruption_id(THREAD, TURN, 110, 2), ids.interruption_id(THREAD, TURN, 110.0, 2, ""))
        self.assertEqual(ids.stalled_id(THREAD, TURN), ids.stalled_id(THREAD, TURN, ""))

    def test_another_homes_are_the_six_and_four_member_arrays(self):
        import hashlib
        import json
        text = json.dumps(["home", HOME_B, THREAD, TURN, (110.0).hex(), 2], separators=(",", ":"))
        self.assertEqual(ids.interruption_id(THREAD, TURN, 110, 2, home_key=HOME_B),
                         hashlib.sha256(text.encode("ascii")).hexdigest())
        text = json.dumps(["stalled", HOME_B, THREAD, TURN], separators=(",", ":"))
        self.assertEqual(ids.stalled_id(THREAD, TURN, HOME_B), hashlib.sha256(text.encode("ascii")).hexdigest())
        self.assertNotEqual(ids.stalled_id(THREAD, TURN, HOME_B), ids.stalled_id(THREAD, TURN))


class DowngradeToV4Tests(Case):
    """`downgrade-state --to 4`: for v0.6.11 to v0.6.14, which watch one home."""

    def state(self, other_state="waiting_backoff"):
        with Store(self.root) as store:
            store.set_enabled(True, 100.0)
            store.register(detection(key_of()), 120.0)
            store.register(detection(key_of(HOME_B)), 120.0, home_key=HOME_B)
            store.register(detection(key_of(HOME_C, OTHER_TURN, 3), OTHER_TURN, 3), 120.0, home_key=HOME_C)
        with self.db() as db:
            db.execute("UPDATE interruptions SET state='recovered', submitted_at=101, recovery_turn_id=? "
                       "WHERE interruption_id=?", ("0a1b2c3d-0002-7000-8000-000000000009", key_of(HOME_C, OTHER_TURN, 3)))
            if other_state != "waiting_backoff":
                db.execute("UPDATE interruptions SET state=?, submitted_at=101, queue_id=? WHERE interruption_id=?",
                           (other_state, "0a1b2c3d-0002-7000-8000-000000000008", key_of(HOME_B)))
            db.commit()

    def test_refused_while_a_record_of_another_home_may_be_queued(self):
        for state in sorted(machine.WATCHED):
            with self.subTest(state):
                shutil.rmtree(self.root, ignore_errors=True)
                self.state(state)
                with self.assertRaises(StoreError):
                    downgrade_state(self.root, 4)
                with self.db() as db:
                    self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 5, "left as it was")

    def test_every_row_is_kept_and_none_of_another_home_is_left_to_act_on(self):
        self.state()
        report = downgrade_state(self.root, 4)
        self.assertEqual((report["rows"], report["extra_home_rows"], report["made_final"]), (3, 2, 1))
        with self.db() as db:
            db.row_factory = sqlite3.Row
            columns = {row[1] for row in db.execute("PRAGMA table_info(interruptions)")}
            rows = {row["interruption_id"]: dict(row) for row in db.execute("SELECT * FROM interruptions")}
            self.assertNotIn("homes", {row[1] for row in db.execute("PRAGMA table_info(watcher_status)")})
        self.assertNotIn("home_key", columns)
        self.assertIn(rows[key_of()]["state"], machine.WAITING, "the default home's record waits as it did")
        cancelled = rows[key_of(HOME_B)]
        self.assertEqual((cancelled["state"], cancelled["last_error"], cancelled["cancel_requested"]),
                         ("cancelled", "home_not_watched", 1))
        self.assertEqual(rows[key_of(HOME_C, OTHER_TURN, 3)]["state"], "recovered", "a final row stays as it is")

    def test_to_3_goes_through_4(self):
        self.state()
        report = downgrade_state(self.root, 3)
        self.assertEqual((report["rows"], report["made_final"]), (3, 1))
        with self.db() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 3)

    def test_the_tagged_v0_6_13_store_opens_the_result_with_every_row(self):
        from test_downgrade import _TAGGED_STORE
        self.state()
        downgrade_state(self.root, 4)
        with self.db() as db:
            expected = dict(db.execute("SELECT interruption_id, state FROM interruptions"))
        read = released.run("v0.6.13", _TAGGED_STORE, self.root, "open")
        self.assertNotIn("refused", read)
        self.assertEqual((read["schema"], read["records"]), (4, expected))


if __name__ == "__main__":
    unittest.main()
