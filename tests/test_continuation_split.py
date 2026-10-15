"""A conversation whose turns Codex records under another id (issue #30, openai/codex#43422).

The `threads` row holds the conversation's id A; its current rollout file is named `..._A_B.jsonl` and its
session_meta says A; its turns are projected under B, and B has no `threads` row. Before v0.6.16-beta.3 the
watcher rejected B as an unknown conversation, read an older turn under A, and missed the failure.

`SplitHome` is codexsim's Codex home, split the way that report found it: once `rotate` has run, every turn,
item and event written for A goes under B and into the A_B file, as Codex writes them. codexsim itself is not
changed (test_released_calls compares its helpers with v0.6.10's).
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import codexsim  # noqa: E402
from codexsim import BASE, RESET, new_id  # noqa: E402
import shutil  # noqa: E402

from codex_auto_resume.codex import LocalSource, chains, rollout  # noqa: E402
from codex_auto_resume.domain import ids  # noqa: E402
from test_engine import Harness  # noqa: E402

A = "0a1b2c3d-0001-7000-8000-00000000000a"
OTHER = "0a1b2c3d-0001-7000-8000-00000000000c"


class SplitHome(codexsim.CodexHome):
    """codexsim's Codex home, with conversations Codex has split."""

    def __init__(self, root):
        self.split, self.current = {}, {}     # B -> A, and A -> the id its turns go under now
        super().__init__(root)

    def _to(self, thread_id):
        return self.current.get(thread_id, thread_id)

    def rollout(self, thread_id):
        owner = self.split.get(thread_id)
        if owner is None:
            return super().rollout(thread_id)
        # Codex starts each file's name with its time, so a later split's name sorts after an earlier one's.
        return self.root / "sessions" / ("rollout-2026-10-14T12-00-%02d-%s_%s.jsonl"
                                         % (list(self.split).index(thread_id), owner, thread_id))

    def add_thread(self, thread_id, **kwargs):
        if thread_id in self.split:
            self.catch_up(thread_id)
            return
        super().add_thread(thread_id, **kwargs)

    def rotate(self, thread_id, *, meta_id=None, thread_source="user", originator="Codex Desktop", turns=None):
        """Codex starts the conversation's next file, A_B.jsonl, and projects its turns under B from now on."""
        self.add_thread(thread_id, thread_source=thread_source, originator=originator)
        turns = turns or new_id()
        self.split[turns], self.current[thread_id] = thread_id, turns
        meta = {"type": "session_meta", "payload": {"id": meta_id or thread_id, "originator": originator,
                                                    "source": "vscode", "thread_source": thread_source}}
        self.rollout(turns).write_bytes(json.dumps(meta).encode("utf-8") + b"\n")
        with self._db("state_5.sqlite") as db:
            db.execute("UPDATE threads SET rollout_path=? WHERE id=?", (str(self.rollout(turns)), thread_id))
        self.catch_up(turns)
        return turns

    # Everything written for A after a split goes where Codex writes it: under B, into the A_B file.
    def add_turn(self, thread_id, *args, **kwargs):
        return super().add_turn(self._to(thread_id), *args, **kwargs)

    def add_item(self, thread_id, *args, **kwargs):
        return super().add_item(self._to(thread_id), *args, **kwargs)

    def set_turn(self, thread_id, turn_id, **columns):
        return super().set_turn(self._to(thread_id), turn_id, **columns)

    def fail_usage(self, thread_id, *args, **kwargs):
        return super().fail_usage(self._to(thread_id), *args, **kwargs)

    def _append(self, thread_id, events):
        return super()._append(self._to(thread_id), events)

    def catch_up(self, thread_id):
        return super().catch_up(self._to(thread_id))

    def turns(self, thread_id):
        return super().turns(self._to(thread_id))

    def next_ordinal(self, thread_id):
        # Codex's ordinals run on across the split (openai/codex#43422: the new file starts past A's).
        own = super().next_ordinal(self._to(thread_id))
        owner = self.split.get(thread_id)
        return max(own, super().next_ordinal(owner)) if owner else own


class SplitCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = SplitHome(Path(folder.name) / "codex-home")
        self.source = LocalSource(self.home.root)

    def failures(self):
        return self.source.latest_failures(BASE - 3600)


class SplitReadTests(SplitCase):
    def test_a_failure_recorded_under_b_is_found_as_the_conversation_a(self):
        """The reported case: fails on v0.6.16-beta.2, which found nothing and read an older turn under A."""
        self.home.add_turn(A, status="completed", completed=int(BASE - 600))
        b = self.home.rotate(A)
        turn = self.home.fail_usage(A)
        self.assertEqual([row["thread_id"] for row in self.home.turns(A)], [b])
        found = self.failures()
        self.assertEqual([(entry["thread_id"], entry["turn_id"]) for entry in found], [(A, turn)])
        entry = found[0]
        self.assertEqual(entry["interruption_id"], ids.interruption_id(A, turn, entry["completed_at"],
                                                                       entry["ordinal"]))
        latest = self.source.latest(A)
        self.assertEqual((latest["thread_id"], latest["turn_id"], latest["status"]), (A, turn, "failed"))
        self.assertEqual(self.source.reset_hint(A, turn)["reset_at"], RESET)
        self.assertEqual(self.source.projection(A), {"table": True, "fresh": True})
        self.assertIs(self.source.turn_progress(A, turn), False)
        self.assertIsNone(self.source.latest(b), "B is no conversation of its own")

    def test_a_later_turn_under_b_never_replays_the_failure(self):
        self.home.rotate(A)
        failed = self.home.fail_usage(A)
        ordinal = self.source.latest(A)["ordinal"]
        later = self.home.add_turn(A, status="completed")
        self.assertEqual(self.failures(), [])
        self.assertEqual(self.source.latest(A)["turn_id"], later)
        self.assertNotEqual(later, failed)
        self.assertTrue(self.source.progress(A, ordinal)["later_turn"])

    def test_an_older_failure_under_a_is_not_replayed_once_its_turns_go_on_under_b(self):
        old = self.home.fail_usage(A)
        self.assertEqual([entry["turn_id"] for entry in self.failures()], [old])
        self.home.rotate(A)
        self.assertEqual([entry["turn_id"] for entry in self.failures()], [old],
                         "until B has a turn, A's own is still the conversation's latest")
        newer = self.home.add_turn(A, status="completed")
        self.assertEqual(self.failures(), [])
        self.assertEqual(self.source.latest(A)["turn_id"], newer)

    def test_a_second_split_follows_the_new_id_and_leaves_the_old_failure(self):
        self.home.rotate(A)
        first = self.home.fail_usage(A)
        c = self.home.rotate(A)
        self.home.add_turn(A, status="completed")
        self.assertEqual(self.failures(), [], "B's failure is not the latest any more, and B is nobody's now")
        second = self.home.fail_usage(A)
        self.assertEqual([(entry["thread_id"], entry["turn_id"]) for entry in self.failures()], [(A, second)])
        self.assertNotEqual(first, second)
        self.assertEqual(self.home.turns(A)[-1]["thread_id"], c)

    def test_a_normal_conversation_reads_as_it_did(self):
        turn = self.home.fail_usage(OTHER)
        self.assertEqual([(entry["thread_id"], entry["turn_id"]) for entry in self.failures()], [(OTHER, turn)])
        self.assertEqual(self.source.latest(OTHER)["turn_id"], turn)
        self.assertEqual(self.source.reset_hint(OTHER, turn)["reset_at"], RESET)

    def test_a_subagent_stays_out_split_or_not(self):
        self.home.add_thread(A, thread_source="subagent")
        self.home.rotate(A, thread_source="subagent")
        self.home.fail_usage(A)
        self.assertEqual(self.failures(), [])
        self.assertIsNone(self.source.latest(A))

    def test_a_session_meta_of_another_id_is_not_followed(self):
        self.home.add_thread(A)
        self.home.rotate(A, meta_id=OTHER)
        self.home.fail_usage(A)
        self.assertEqual(self.failures(), [])
        self.assertIsNone(self.source.latest(A))

    def test_b_with_a_conversation_of_its_own_is_not_taken(self):
        b = self.home.rotate(A)
        self.home.fail_usage(A)
        with self.home._db("state_5.sqlite") as db:
            db.execute("INSERT INTO threads (id, rollout_path, source, thread_source, archived, history_mode) "
                       "VALUES (?,?,'vscode','user',0,'paginated')", (b, str(self.home.root / "nowhere.jsonl")))
        self.assertEqual(self.failures(), [])
        self.assertIsNone(self.source.latest(A), "A's own turns: there are none")

    def test_b_named_by_two_conversations_is_nobodys(self):
        b = self.home.rotate(A)
        self.home.fail_usage(A)
        self.home.add_thread(OTHER)
        with self.home._db("state_5.sqlite") as db:
            db.execute("UPDATE threads SET rollout_path=? WHERE id=?",
                       (str(self.home.root / "sessions" / ("rollout-x-%s_%s.jsonl" % (OTHER, b))), OTHER))
        self.assertEqual(self.failures(), [])
        self.assertIsNone(self.source.latest(A), "B is not followed: A's own turns, of which there are none")
        self.assertEqual(self.source.turn_chain(A), (A,))

    def test_a_stray_file_named_after_another_conversations_id_never_joins_the_chain(self):
        """A file named <A>_<X> whose first line is another conversation's: X is not one of A's ids."""
        self.home.add_turn(A, status="completed")
        x = self.home.rotate(OTHER)
        stray = self.home.root / "sessions" / ("rollout-2026-10-14T11-00-00-%s_%s.jsonl" % (A, x))
        stray.write_bytes(self.home.rollout(x).read_bytes())
        b = self.home.rotate(A)                                    # A now under B, no turn there yet
        failed = self.home.fail_usage(OTHER)                        # OTHER's failure, under X
        rollout._SPLITS.clear()
        self.assertEqual(self.source.turn_chain(A), (A, b))
        self.assertEqual(self.source.latest(A)["status"], "completed", "A's own turn, not OTHER's failure")
        self.assertEqual([(entry["thread_id"], entry["turn_id"]) for entry in self.failures()], [(OTHER, failed)])

    def test_a_stray_file_whose_first_line_is_another_conversations_never_joins_the_chain(self):
        """The same, where no conversation's current file names X any more: only its first line tells."""
        self.home.add_turn(A, status="completed")
        x = self.home.rotate(OTHER)
        failed = self.home.fail_usage(OTHER)                        # OTHER's failure, under X
        stray = self.home.root / "sessions" / ("rollout-2026-10-14T11-00-00-%s_%s.jsonl" % (A, x))
        stray.write_bytes(self.home.rollout(x).read_bytes())
        self.home.rotate(OTHER)                                     # OTHER goes on under Y, no turn there yet
        b = self.home.rotate(A)
        rollout._SPLITS.clear()
        self.assertEqual(self.source.turn_chain(A), (A, b))
        self.assertEqual(self.source.latest(A)["status"], "completed")
        self.assertEqual([(entry["thread_id"], entry["turn_id"]) for entry in self.failures()], [(OTHER, failed)])

    def test_a_file_named_otherwise_is_not_a_split(self):
        b = self.home.rotate(A)
        self.home.fail_usage(A)
        moved = self.home.root / "sessions" / ("rollout-2026-10-14T12-00-00-%s_%s.old.jsonl" % (A, b))
        self.home.rollout(b).replace(moved)
        with self.home._db("state_5.sqlite") as db:
            db.execute("UPDATE threads SET rollout_path=? WHERE id=?", (str(moved), A))
        self.assertEqual(self.failures(), [])

    def test_a_stalled_turn_under_b_is_the_conversations(self):
        self.home.rotate(A)
        turn = self.home.add_turn(A, status="inProgress", started=int(BASE - 900), user_text=None, progress=False)
        found = self.source.stalled_turns(int(BASE - 3600), 300, BASE)
        self.assertEqual([(entry["thread_id"], entry["turn_id"]) for entry in found], [(A, turn)])

    def test_the_power_actions_check_reads_the_split_files_projection(self):
        self.home.rotate(A)
        self.home.add_turn(A, status="completed")
        self.assertTrue(self.source.activity((A,), BASE)["history"])
        self.home.make_stale(A)
        self.assertFalse(self.source.activity((A,), BASE)["history"])


class Restarted(SplitHome):
    """Each split's ordinals start again (the reviewer's collision case): a later id's turns are later anyway."""

    def next_ordinal(self, thread_id):
        return codexsim.CodexHome.next_ordinal(self, self._to(thread_id))


class SecondSplitTests(SplitCase):
    """A -> B, then A -> C before C has a turn: the conversation's turns are A's, B's and C's, in that order."""

    def forget(self):
        """As a watcher started afresh knows it: nothing remembered of the names it listed."""
        rollout._SPLITS.clear()
        rollout._ASKED.clear()

    def test_an_old_failure_never_comes_back_while_the_newest_id_has_no_turn(self):
        old = self.home.fail_usage(A)
        self.home.rotate(A)
        newer = self.home.add_turn(A, status="completed")
        c = self.home.rotate(A)
        with self.home._db("thread_history_1.sqlite") as db:     # A's projection row at the new file's end
            db.execute("UPDATE thread_history_projection_state SET next_rollout_byte_offset=? WHERE thread_id=?",
                       (self.home.rollout(c).stat().st_size, A))
        for fresh in (False, True):
            if fresh:
                self.forget()
            with self.subTest(restarted=fresh):
                self.assertEqual(self.failures(), [])
                self.assertEqual(self.source.latest(A)["turn_id"], newer)
                self.assertNotEqual(newer, old)

    def test_a_failure_under_b_is_still_the_latest_after_a_split_to_c(self):
        b = self.home.rotate(A)
        failed = self.home.fail_usage(A)
        self.home.rotate(A)
        self.forget()
        self.assertEqual([entry["turn_id"] for entry in self.failures()], [failed])
        self.assertEqual(self.source.latest(A)["turn_id"], failed)
        self.assertEqual(self.source.reset_hint(A, failed)["reset_at"], RESET, "read from B's file")
        self.assertIn(b, self.source.turn_chain(A))

    def test_a_later_id_comes_after_an_earlier_one_whatever_its_ordinals(self):
        self.home = Restarted(self.home.root.parent / "restarted")
        self.source = LocalSource(self.home.root)
        self.home.add_turn(A, status="completed")
        self.home.add_turn(A, status="completed")
        self.home.rotate(A)
        stopped = self.home.add_turn(A, status="interrupted", progress=False)
        latest = self.source.latest(A)
        self.assertEqual(latest["turn_id"], stopped)
        self.assertGreater(latest["ordinal"], rollout.SPAN)
        self.assertTrue(self.source.progress(A, 6)["later_turn"], "A's turn at 6 has B's after it")


class SplitRecoveryTests(unittest.TestCase):
    """The whole path on a split conversation: detected as A, sent to A's queue, its turn followed under B."""

    def test_a_usage_limit_recovers_with_the_queue_and_the_app_check_under_a(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        h = Harness(root / "state", home=SplitHome(root / "codex-home"))
        self.addCleanup(h.close)
        h.enable()
        b = h.home.rotate(A)
        h.home.fail_usage(A)
        h.backend.loaded_map[A] = "loaded"
        h.tick()
        row = h.record(A)
        self.assertIsNotNone(row, "the failure recorded under B is detected as A's")
        self.assertEqual((row["state"], row["reset_at"]), ("waiting_reset", RESET))
        h.now = RESET + 61
        h.tick()
        self.assertEqual([call[0] for call in h.backend.send_calls], [A], "codex queue is asked for A")
        self.assertEqual(h.home.turns(A)[-1]["thread_id"], b, "and the app ran the turn under B")
        h.tick(advance=6)
        self.assertEqual(h.record(A)["recovery_turn_id"], h.home.turns(A)[-1]["turn_id"])
        h.tick(advance=10)
        self.assertEqual(h.record(A)["state"], "recovered")
        self.assertEqual(h.records(b), [])

    def harness(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        h = Harness(root / "state", home=SplitHome(root / "codex-home"))
        self.addCleanup(h.close)
        h.backend.loaded_map[A] = "loaded"
        return h

    def test_an_earlier_file_that_leaves_never_brings_an_old_failure_back(self):
        """The chain a conversation had is remembered (codex/chains.py), not read again from files that can go."""
        h = self.harness()
        old = h.home.fail_usage(A)
        b = h.home.rotate(A)
        h.home.add_turn(A, status="completed")
        h.enable(at=BASE - 60)
        h.tick()
        h.home.rotate(A)
        h.tick(advance=5)
        archived = h.home.root / "archived_sessions"
        archived.mkdir()
        shutil.move(str(h.home.rollout(b)), str(archived / h.home.rollout(b).name))
        rollout._SPLITS.clear()
        h.now = max(h.now, RESET + 61)
        for _ in range(10):
            h.tick(advance=60)
        self.assertEqual([row for row in h.records(A) if row["turn_id"] == old], [])
        self.assertEqual(h.backend.send_calls, [])

    def test_an_id_keeps_its_place_while_its_continuation_waits_in_the_queue(self):
        h = self.harness()
        h.home.add_turn(A, status="completed", completed=int(BASE - 600))
        b = h.home.rotate(A)
        h.home.add_turn(A, status="completed", completed=int(BASE - 300))
        h.home.rotate(A)
        h.home.fail_usage(A)                                      # under C, the third id
        h.enable(at=BASE - 60)
        h.tick()
        h.backend.after_accept = "queue"
        h.now = RESET + 61
        h.tick()
        self.assertEqual(h.record(A)["state"], "queued")
        h.home.rollout(b).unlink()                                # B's file goes: C keeps its place
        rollout._SPLITS.clear()
        h.tick(advance=5)
        self.assertEqual(h.record(A)["state"], "queued")
        h.home.dispatch(A)
        for _ in range(10):
            h.tick(advance=61)
        self.assertEqual(h.record(A)["state"], "recovered")

    def test_a_failure_under_b_is_found_at_once_after_a_split_to_c_inside_one_listing(self):
        """A listing made before A's split files existed does not hide B's failure for its minute."""
        h = self.harness()
        h.home.rotate(OTHER)                                      # some split in the home, so it has a listing
        h.enable(at=BASE - 60)
        h.home.add_turn(A, status="completed", completed=int(BASE - 600))
        h.tick()
        rollout._splits(h.home.root, fresh=True)                  # listed now: no file of A's split yet
        h.home.rotate(A)
        failed = h.home.fail_usage(A)
        h.home.rotate(A)
        h.tick(advance=5)
        self.assertEqual([row["turn_id"] for row in h.records(A)], [failed])

    def test_the_chain_is_kept_in_the_state_folder_for_a_watcher_started_again(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        home = SplitHome(root / "codex-home")
        kept = root / "config" / "split-chains.json"
        b = home.rotate(A)
        home.add_turn(A, status="completed")
        c = home.rotate(A)
        LocalSource(home.root, chains=chains.ChainMemory(kept)).latest(A)
        home.rollout(b).unlink()
        rollout._SPLITS.clear()
        again = LocalSource(home.root, chains=chains.ChainMemory(kept))       # a new process reads the file
        self.assertEqual(again.turn_chain(A), (A, b, c))
        self.assertEqual(json.loads(kept.read_text(encoding="utf-8"))["format"], chains.FORMAT)
        self.assertNotIn("codex-home", kept.read_text(encoding="utf-8"), "ids and a home's digest, never a path")

    def test_a_purge_takes_the_remembered_chains_and_their_temporary_files(self):
        """config/split-chains.json is the product's own state: Uninstall.cmd -Purge and `uninstall` take it."""
        from codex_auto_resume import config
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        paths = config.Paths(Path(folder.name) / "home")
        paths.ensure()
        memory = chains.ChainMemory(paths.split_chains_file)
        memory.extend(paths.home / "codex", A, [new_id()])
        stray = paths.state_dir / "split-chains.4242.tmp"
        stray.write_text("{}", encoding="utf-8")
        owned = paths.owned_state_files()
        self.assertTrue(paths.split_chains_file.is_file())
        self.assertIn(paths.split_chains_file, owned)
        self.assertIn(stray, owned)
        self.assertEqual([path.name for path in paths.state_dir.glob("split-chains.*.tmp")], ["split-chains.4242.tmp"],
                         "the atomic write leaves no temporary file of its own")

    def test_an_old_failure_is_never_sent_once_a_person_worked_under_b(self):
        h = self.harness()
        old = h.home.fail_usage(A)
        h.home.rotate(A)
        h.home.add_turn(A, status="completed")
        h.enable()
        h.tick()
        c = h.home.rotate(A)
        with h.home._db("thread_history_1.sqlite") as db:
            db.execute("UPDATE thread_history_projection_state SET next_rollout_byte_offset=? WHERE thread_id=?",
                       (h.home.rollout(c).stat().st_size, A))
        for _ in range(20):
            h.tick(advance=60)
        self.assertEqual([row for row in h.records(A) if row["turn_id"] == old], [])
        self.assertEqual(h.backend.send_calls, [])

    def test_a_failure_waiting_under_b_still_waits_and_recovers_after_a_split_to_c(self):
        h = self.harness()
        h.home.add_turn(A, status="completed", completed=int(BASE - 600))
        h.home.rotate(A)
        h.home.fail_usage(A)
        h.enable()
        h.tick()
        self.assertEqual(h.record(A)["state"], "waiting_reset")
        h.home.rotate(A)
        h.tick(advance=5)
        self.assertEqual(h.record(A)["state"], "waiting_reset", "not superseded by A's own old turn")
        h.now = RESET + 61
        h.tick()
        self.assertEqual([call[0] for call in h.backend.send_calls], [A])
        h.tick(advance=6)
        h.tick(advance=10)
        self.assertEqual(h.record(A)["state"], "recovered")


if __name__ == "__main__":
    unittest.main()
