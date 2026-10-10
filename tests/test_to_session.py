"""P16's TO_SESSION (v0.6.15-beta.3): a conversation another Codex session holds - a terminal's TUI, VS Code's server
- is sent the ordinary continuation through `codex queue` where the plug says so, and taken back when that session
lets go of it or does not take it in time; and none of it stores a word an older schema-5 reader refuses.

The plug is a test's own (test_plug_points.Asked) answering TO_SESSION at P16; the engine runs against codexsim.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_engine import T1  # noqa: E402
from test_plug_points import Asked, Channel, PluggedCase  # noqa: E402
from codex_auto_resume import machine  # noqa: E402
from codex_auto_resume.domain.plug import Alternative, DEFER  # noqa: E402
from codex_auto_resume.engine.tosession import STORED  # noqa: E402

# What v0.6.15-beta and beta.2 accept as a withdrawal's word (their domain/reason_vocabulary.WithdrawReason, schema 5):
# written out, so this build's own list cannot move under the test that holds it to theirs.
BETA2_WITHDRAW_REASONS = frozenset({
    "cancel", "paused", "paused_unknown", "thread_disabled", "superseded", "superseded_by_user", "user_queued_input",
    "not_loaded", "expired", "projection_stale", "duplicate_owner", "observe_only", "observe_only_unknown",
    "window_ended", "not_delivered_on_open"})
BETA2_RELEASABLE = frozenset({"paused", "observe_only", "window_ended", "not_delivered_on_open"})


class SessionCase(PluggedCase):
    def queued(self, h=None, **answers):
        """A usage-limited conversation another session holds, sent for that session to take."""
        h = h or self.h
        self.ready_after_reset(h, loaded=False)
        h.backend.loaded_map[T1] = "elsewhere"
        h.backend.after_accept = "queue"
        plug = Asked(unloaded=lambda record: Alternative.TO_SESSION if record.get("holder") == "session" else DEFER,
                     **answers)
        self.plugged(plug, h)
        h.tick()
        row = h.record()
        self.assertEqual(row["state"], "queued", row["last_error"])
        return plug, row

    def state(self, h=None):
        row = (h or self.h).record()
        return row["state"], row["last_error"], row["withdraw_reason"]


class SendTests(SessionCase):
    def test_it_goes_the_ordinary_way_with_its_marker(self):
        plug, row = self.queued()
        self.assertEqual(len(self.h.backend.send_calls), 1)
        self.assertIn(row["marker"], self.h.backend.send_calls[0][1])
        self.assertEqual(machine.decode_gates(row["gate_eval"])["thread_available"], (machine.PASS, machine.SESSION))
        asked = [arguments[0] for hook, arguments in plug.asked if hook == "unloaded"]
        self.assertEqual((asked[0]["holder"], asked[0]["app"]), ("session", True))

    def test_only_for_a_conversation_another_session_holds(self):
        for loaded in ("notLoaded", "unknown"):
            with self.subTest(loaded):
                h = self.fresh()
                self.ready_after_reset(h, loaded=False)
                h.backend.loaded_map[T1] = loaded
                self.plugged(Asked(unloaded=Alternative.TO_SESSION), h)
                h.tick()
                self.assertEqual(h.backend.send_calls, [])

    def test_the_holder_gone_at_the_recheck_sends_nothing(self):
        h = self.h
        self.ready_after_reset(loaded=False)
        h.backend.loaded_map[T1] = "elsewhere"

        def answer(record):
            if record.get("holder") == "session":
                h.backend.loaded_map[T1] = "notLoaded"      # the session ends before the claim's re-check
                return Alternative.TO_SESSION
            return DEFER
        self.plugged(Asked(unloaded=answer))
        h.tick()
        self.assertEqual(h.backend.send_calls, [])
        self.assertEqual(h.record()["last_error"], "loaded_recheck_failed")

    def test_a_channel_waits_with_its_own_reason(self):
        h = self.h
        self.ready_after_reset(loaded=False)
        h.backend.loaded_map[T1] = "elsewhere"
        self.plugged(Asked(unloaded=Alternative.TO_SESSION, sender=lambda record, backend: Channel(h)))
        h.tick()
        self.assertEqual(h.backend.send_calls, [])
        self.assertEqual(h.record()["last_error"], "held_by_other_session")


class WithdrawTests(SessionCase):
    def test_the_session_letting_go_takes_it_back_and_gives_it_back(self):
        """Fails with the release reverted: the record would be failed, never sent again."""
        plug, row = self.queued()
        self.h.backend.loaded_map[T1] = "notLoaded"
        self.h.watch(advance=2)
        self.assertEqual(self.state(), ("withdrawn_unconfirmed", "session_ended", STORED["session_ended"]))
        for _ in range(4):
            self.h.watch(advance=60)
        released = self.h.record()
        self.assertIn(released["state"], machine.WAITING)
        self.assertEqual(released["last_error"], "released_after_withdrawal")

    def test_not_taken_within_the_window_is_taken_back_and_given_back(self):
        plug, row = self.queued()
        self.h.watch(advance=200)
        self.assertEqual(self.state(), ("withdrawn_unconfirmed", "session_expired", STORED["session_expired"]))
        for _ in range(4):
            self.h.watch(advance=60)
        self.assertIn(self.h.record()["state"], machine.WAITING)

    def test_the_standard_editions_own_expiry_still_settles_failed(self):
        """The review's blocker 1: `expired` never joins the releasable withdrawals."""
        self.assertNotIn("expired", machine.RELEASABLE_WITHDRAWALS)
        h = self.h
        h.backend.after_accept = "queue"
        self.ready_after_reset(h)
        h.tick()
        self.assertEqual(h.record()["state"], "queued")
        h.watch(advance=200)
        self.assertEqual(h.record()["withdraw_reason"], "expired")
        for _ in range(4):
            h.watch(advance=60)
        self.assertEqual(h.record()["state"], "failed")

    def test_every_other_withdrawal_still_fires_at_once(self):
        plug, row = self.queued()
        self.h.tick(advance=1)
        self.h.store.set_enabled(False, self.h.now)
        self.h.watch(advance=1)
        self.assertEqual(self.state()[2], "paused")


class StoredWordTests(unittest.TestCase):
    def test_no_word_stored_is_one_beta_or_beta2_refuses(self):
        """The review's blocker 2: what a withdrawal stores is a word v0.6.15-beta and beta.2 read, and release."""
        self.assertTrue(set(STORED.values()) <= BETA2_WITHDRAW_REASONS)
        self.assertTrue(set(STORED.values()) <= BETA2_RELEASABLE)
        self.assertEqual(set(machine.WITHDRAW_REASONS), BETA2_WITHDRAW_REASONS,
                         "a new withdrawal word would make an older build's validator refuse the state")

    def test_an_older_reader_sees_the_gate_word_as_a_pass_of_no_kind_it_knows(self):
        from codex_auto_resume.domain import gates
        older = gates.GATE_REASONS - {machine.SESSION}
        stored = gates.encode_gates({"thread_available": (machine.PASS, machine.SESSION)})
        with patch.object(gates, "GATE_REASONS", older):
            self.assertEqual(gates.decode_gates(stored)["thread_available"], (machine.PASS, "other"))


if __name__ == "__main__":
    unittest.main()
