"""One dispatch lock for the whole watcher, and a conversation's day and spacing counted in the claim.

v0.6.14-beta.2 gives a watcher several engines (one per Codex home it watches) and lets the receipt of a
send wait on a worker. Both stay safe on two things this file holds:

- every engine the App builds is handed the same `threading.RLock` as its dispatch lock - not the
  `nullcontext` an engine built alone has - so no two sends and no send and a record's watch run at once;
- the claim reads the conversation's claims of the day and its last claim again inside its own
  transaction (store/claims.py `_caps_refusal`), so a claim committed after the gates read them is
  counted - and is a wait, as at the gate, never the attempt budget's stop.

Temporary homes only: the App is built over a scratch Codex home and state, its engine check stood in for.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import config, ladder, machine  # noqa: E402
from codex_auto_resume.store import Store  # noqa: E402
from test_engine import EngineCase, T1, dispatch_and_fail  # noqa: E402

NOW = 1_800_000_000.0
THREAD = "0a1b2c3d-0001-7000-8000-000000000001"
TURN = "0a1b2c3d-0002-7000-8000-000000000002"
LATER_TURN = "0a1b2c3d-0003-7000-8000-000000000003"
FIRST, SECOND = "a" * 64, "b" * 64
LIMITS = {"max_chain_continuations": 6, "max_recovery_attempts": 5, "max_no_progress": 3}
ALL_PASS = {name: (machine.PASS, "ok") for name in machine.GATES}


def detection(key, turn, ordinal) -> dict:
    return {"thread_id": THREAD, "turn_id": turn, "completed_at": NOW - 600 + ordinal,
            "started_at": NOW - 700, "ordinal": ordinal, "interruption_id": key, "reset_at": NOW - 300,
            "limit_type": "codex:primary", "uncertain": False, "category": "usage_limit"}


class OneLockTests(unittest.TestCase):
    def app(self, root):
        from codex_auto_resume.codex import transport
        from codex_auto_resume.control import policy as control_policy
        from codex_auto_resume.runtime.app import App
        engine = root / "bin" / "codex.exe"
        engine.parent.mkdir(parents=True)
        engine.write_bytes(b"MZ")
        (root / "codex").mkdir()
        for target, name, value in ((transport.Backend, "_compatible", lambda backend: {}),
                                    (config, "candidate_codex_exes", lambda: [engine])):
            patcher = patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        with patch.object(control_policy, "managed_policy", return_value=control_policy.managed.NONE):
            return App(config.Paths(root / "home"), codex_exe=str(engine), codex_home=root / "codex",
                       enable_logging=False)

    def test_every_engine_of_a_watcher_holds_one_real_lock(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        app = self.app(root)
        store = Store(root / "state")
        self.addCleanup(store.close)
        first, second = app.engine(store), app.engine(store)
        lock = first.dispatch_lock()
        self.assertIs(type(lock), type(threading.RLock()), "a nullcontext would let two sends run at once")
        self.assertIs(second.dispatch_lock(), lock, "every engine of the watcher holds the same lock")
        self.assertIs(app.dispatch_lock(), lock)
        # Held by one thread, the lock keeps every other one out until it is let go.
        with first.dispatch_lock():
            seen = []
            other = threading.Thread(target=lambda: seen.append(second.dispatch_lock().acquire(timeout=0.05)))
            other.start()
            other.join()
        self.assertEqual(seen, [False])


class ClaimCountsTheDayTests(unittest.TestCase):
    """The claim's own reads: a claim of the conversation made after the gates looked is counted."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = Store(Path(folder.name))
        self.addCleanup(self.store.close)
        self.store.set_enabled(True, NOW - 3600)
        self.store.register(detection(FIRST, TURN, 1), NOW - 500)
        self.store.register(detection(SECOND, LATER_TURN, 2), NOW - 500)
        # The first is claimed a hundred seconds ago and given back unsent: its claim time still counts.
        self.assertTrue(self.store.reserve(FIRST, NOW - 100, limits=LIMITS, gates=ALL_PASS))
        self.assertTrue(self.store.release_claim(FIRST, "waiting_retry", "released_before_send", NOW - 99))

    def claim(self, **options):
        return self.store.reserve_detailed(SECOND, NOW, limits=LIMITS, gates=dict(ALL_PASS), **options)

    def test_without_caps_the_claim_is_what_it_was(self):
        self.assertEqual(self.claim(), (True, None, None))

    def test_the_spacing_is_counted_in_the_claim(self):
        self.assertEqual(self.claim(caps=(5, 900)), (False, "attempt_budget", "thread_submission_cooldown"))
        row = self.store.get(SECOND)
        self.assertIn(row["state"], machine.WAITING)
        self.assertEqual(machine.decode_gates(row["gate_eval"])["attempt_budget"],
                         (machine.WAIT, "thread_submission_cooldown"))
        self.assertEqual(self.claim(caps=(5, 60)), (True, None, None), "past the spacing it is claimed")

    def test_the_day_is_counted_in_the_claim(self):
        self.assertEqual(self.claim(caps=(1, 0)), (False, "attempt_budget", "daily_submission_cap"))

    def test_send_now_passes_the_spacing_and_never_the_day(self):
        self.assertEqual(self.claim(caps=(1, 900), forced=True),
                         (False, "attempt_budget", "daily_submission_cap"))
        self.assertEqual(self.claim(caps=(5, 900), forced=True), (True, None, None))


class EngineCountsInTheClaimTests(EngineCase):
    """The engine passes its numbers to the claim, and a refusal there is a wait, never a stop."""

    def second_due(self):
        self.h.backend.after_accept = "queue"
        self.ready_after_reset()
        self.h.tick()
        self.assertEqual(len(self.h.backend.send_calls), 1)
        dispatch_and_fail(self.h.home, T1, usage=True, progress=True, reset=self.h.now + 60)
        self.h.tick(advance=30)
        second = self.h.records()[1]
        self.assertEqual(second["state"], "waiting_reset")
        # The gates read nothing - as if the first claim had been committed after they looked.
        self.h.store.recent_claims = lambda thread_id, since: []
        self.h.store.recent_claim_count = lambda thread_id, since: 0
        return second

    def test_a_claim_the_gates_did_not_see_holds_the_spacing(self):
        self.h.engine.options.update({"thread_cooldown_seconds": 900, "max_submissions_per_thread_per_day": 5})
        second = self.second_due()
        self.h.tick(advance=200)
        self.assertEqual(len(self.h.backend.send_calls), 1, "a second send inside the spacing")
        row = self.h.store.get(second["interruption_id"])
        self.assertEqual((row["state"], row["last_error"]), ("waiting_retry", "thread_submission_cooldown"))

    def test_a_claim_the_gates_did_not_see_holds_the_day_and_waits(self):
        self.h.engine.options.update({"thread_cooldown_seconds": 0, "max_submissions_per_thread_per_day": 1})
        second = self.second_due()
        self.h.tick(advance=200)
        self.assertEqual(len(self.h.backend.send_calls), 1, "a second send over the day's count")
        row = self.h.store.get(second["interruption_id"])
        # A wait for the oldest claim to leave the day, never retry_budget_exhausted.
        self.assertEqual((row["state"], row["last_error"]), ("waiting_retry", "daily_submission_cap"))
        self.assertGreater(row["next_retry_at"], self.h.now)

    def test_capacity_keeps_its_own_numbers(self):
        self.assertEqual(self.h.engine.caps("capacity"), (ladder.CAPACITY_PER_DAY, ladder.CAPACITY_SPACING))
        self.assertEqual(self.h.engine.caps(), (5, 900))


if __name__ == "__main__":
    unittest.main()
