"""Send now (v0.6.14, stage 3b): a person's request, in the Dashboard, that one waiting recovery go at
the watcher's next look - SEND_NOW at P7, and the claim that uses it.

Held against the shipped definition and statement and against core's own engine, store and
simulated Codex home (takingcase.py): the request is refused off, watched, under each policy key and
for an id of the wrong shape; armed, a waiting recovery it names goes at the next look, paid with one
unit, and the request is used; one not used lapses after fifteen minutes, and one made before the
capability last moved - turned off and on again, or read down by ForceShadow - passes nothing; the
claim uses it once; and its paid send gone unknown turns it off. No MCP tool reaches it.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase as ac  # noqa: E402
from takingcase import TakingCase  # noqa: E402
from codex_auto_resume import failures, ladder  # noqa: E402
from codex_auto_resume.domain.plug import DEFER, Alternative, Point  # noqa: E402
from codex_auto_resume_advanced import policy, surfaces  # noqa: E402
from codex_auto_resume_advanced.control import sendnow  # noqa: E402
from codex_auto_resume_advanced.control.sendnow import LIFETIME, SendNow  # noqa: E402
from codex_auto_resume_advanced.engine import credits  # noqa: E402
from codex_auto_resume_advanced.registry import RESET_CREDIT, SEND_NOW  # noqa: E402
from codex_auto_resume_advanced.vocabulary import (Actor, ArmingState, JournalCode, McpTool,  # noqa: E402
                                                   Measurement, OffReason, OverrideKind, Refusal,
                                                   Verdict)
from test_engine import T1, TURN_A  # noqa: E402
from test_plug_points import OVERLOADED  # noqa: E402

CAP = "send_now"


class SendNowCase(TakingCase):
    DEFINITION = SEND_NOW

    def setUp(self):
        super().setUp()
        woken = patch.object(sendnow, "wake", side_effect=lambda paths: self.woken.append(paths) or True)
        self.woken = []
        woken.start()
        self.addCleanup(woken.stop)

    def waiting(self, h=None):
        """A temporary failure, registered and waiting for its retry."""
        h = h or self.h
        self.failing(OVERLOADED, h)
        h.tick()
        row = h.record()
        self.assertEqual(row["state"], "waiting_backoff")
        self.assertGreater(row["next_retry_at"], h.now + 1)
        return row

    def ask(self, plug, key):
        return surfaces.answer(plug.runtime, "bridge", {"command": "advanced-send-now",
                                                        "argument": {"interruption_id": key}})

    def requests(self, plug):
        with plug.runtime.state._read() as connection:
            return [tuple(row) for row in connection.execute(
                "SELECT interruption_id, kind, used_at IS NULL FROM overrides WHERE capability=?", (CAP,))]


class RequestTests(SendNowCase):
    def test_refused_off_watched_under_each_policy_key_and_for_a_bad_id(self):
        plug = self.advanced()
        self.assertEqual(self.ask(plug, ac.KEY)["refusal"], Refusal.NOT_ON, "off")
        self.arm(plug, state="shadow")
        self.assertEqual(self.ask(plug, ac.KEY)["refusal"], Refusal.NOT_ON, "watched")
        self.arm(plug)
        for given in (policy.Policy(forbid=True), policy.Policy(allowed=frozenset({"capacity_retry"})),
                      policy.Policy(force_shadow=True)):
            with self.subTest(given):
                self.policy = given
                self.assertEqual(self.ask(plug, ac.KEY)["refusal"], Refusal.NOT_ON)
        self.policy = policy.NONE
        for key in ("A" * 64, "a" * 63, None, 7, "../" + "a" * 61):
            with self.subTest(key=key):
                self.assertEqual(self.ask(plug, key)["refusal"], Refusal.INVALID_REQUEST)
        self.assertEqual(surfaces.answer(plug.runtime, "bridge", {"command": "advanced-send-now", "argument": {
            "interruption_id": ac.KEY, "now": True}})["refusal"], Refusal.INVALID_REQUEST)
        self.assertEqual(self.requests(plug), [])
        self.assertEqual(self.woken, [])

    def test_on_it_is_one_request_that_lapses_after_fifteen_minutes_and_wakes_the_watcher(self):
        plug = self.advanced()
        self.arm(plug)
        found = self.ask(plug, ac.KEY)
        self.assertEqual(found, {"done": True, "refusal": None, "expires_at": self.h.now + LIFETIME})
        self.assertTrue(self.ask(plug, ac.KEY)["done"], "a second click renews it")
        self.assertEqual(self.requests(plug), [(ac.KEY, OverrideKind.FORCE_ONCE, 1)])
        self.assertEqual(len(self.woken), 2)
        self.assertIn(("sendnow.requested", None, None), self.journal(plug))
        code = ac.code_of(plug.runtime, CAP)
        record = {"interruption_id": ac.KEY, "state": "waiting_backoff"}
        self.h.now += LIFETIME - 1
        self.assertIs(code.schedule(record, self.h.now), Alternative.SEND_NOW)
        self.h.now += 1
        self.assertIs(code.schedule(record, self.h.now), DEFER, "lapsed")

    def test_only_for_a_waiting_record_with_a_request_made_since_it_last_moved(self):
        plug = self.advanced()
        self.arm(plug)
        self.ask(plug, ac.KEY)
        code = ac.code_of(plug.runtime, CAP)
        for state, answer in (("waiting_backoff", Alternative.SEND_NOW), ("waiting_reset", Alternative.SEND_NOW),
                              ("submission_unknown", DEFER), ("queued", DEFER), ("recovered", DEFER)):
            with self.subTest(state):
                self.assertIs(code.schedule({"interruption_id": ac.KEY, "state": state}, self.h.now), answer)
        self.assertIs(code.schedule({"interruption_id": "b" * 64, "state": "waiting_backoff"}, self.h.now), DEFER)
        # Turned off and on again within the fifteen minutes: the request is from before.
        self.h.now += 10
        plug.runtime.arming.disarm(CAP, actor=Actor.TRAY)
        self.h.now += 10
        self.arm(plug)
        self.assertIs(code.schedule({"interruption_id": ac.KEY, "state": "waiting_backoff"}, self.h.now), DEFER)

    def test_read_down_by_force_shadow_the_sweep_voids_it_and_lifting_the_policy_passes_nothing(self):
        plug = self.advanced()
        self.arm(plug)
        self.ask(plug, ac.KEY)
        self.policy = policy.Policy(force_shadow=True)
        plug.runtime.tick(self.h.engine.store)
        self.assertEqual(self.requests(plug), [(ac.KEY, OverrideKind.FORCE_ONCE, 0)], "closed by the sweep")
        self.policy = policy.NONE
        plug.runtime.states(fresh=True)
        code = ac.code_of(plug.runtime, CAP)
        self.assertIs(code.schedule({"interruption_id": ac.KEY, "state": "waiting_backoff"}, self.h.now), DEFER)

    def test_no_mcp_tool_reaches_it(self):
        plug = self.armed()
        tools = {tool["name"] for tool in surfaces.mcp(plug.runtime, {"request": "tools"})["tools"]}
        self.assertEqual(tools, set(McpTool))
        for tool in tools:
            self.assertNotIn("send", tool)
        self.assertIs(surfaces.mcp(plug.runtime, {"request": "call", "tool": "advanced-send-now",
                                                  "arguments": {"interruption_id": ac.KEY}}), DEFER)


class ArmedTests(SendNowCase):
    def test_a_waiting_recovery_it_names_goes_at_the_next_look_and_pays_one_unit(self):
        plug = self.armed()
        row = self.waiting()
        key = row["interruption_id"]
        self.h.tick(advance=1)
        self.assert_no_send()
        self.assertTrue(self.ask(plug, key)["done"])
        self.h.tick(advance=1)
        self.assertEqual(len(self.h.backend.send_calls), 1)
        self.assertLess(self.h.now, row["next_retry_at"], "before its retry's wait was over")
        self.assertEqual(self.spends(plug), [(CAP, T1, key)])
        self.assertEqual(self.requests(plug), [(key, OverrideKind.FORCE_ONCE, 0)], "used by the claim")
        self.assertIn((JournalCode.ACTED, Point.SCHEDULE, Alternative.SEND_NOW), self.journal(plug))
        self.follow()
        self.assertEqual(self.h.record()["state"], "recovered")

    def test_off_or_never_asked_it_waits_for_its_schedule(self):
        for armed in (False, True):
            with self.subTest(armed=armed):
                h = self.fresh()
                plug = self.armed(h) if armed else self.advanced(h)
                if not armed:
                    self.plugged(plug, h)
                self.waiting(h)
                h.tick(advance=1)
                self.assertEqual(h.backend.send_calls, [])

    def test_the_claim_uses_a_request_once_and_holds_a_second(self):
        plug = self.armed()
        row = dict(self.waiting())
        runtime = plug.runtime
        self.assertTrue(self.ask(plug, row["interruption_id"])["done"])
        with self.h.store._transaction() as connection:
            self.assertIs(runtime.ledger.claim(connection, row, self.h.now, {CAP: {Alternative.SEND_NOW}}), DEFER)
        with self.h.store._transaction() as connection:
            self.assertIs(runtime.ledger.claim(connection, row, self.h.now + 1, {CAP: {Alternative.SEND_NOW}}),
                          Alternative.HOLD, "used")
        self.h.now += LIFETIME
        self.assertTrue(self.ask(plug, row["interruption_id"])["done"])
        self.h.now += LIFETIME
        with self.h.store._transaction() as connection:
            self.assertIs(runtime.ledger.claim(connection, row, self.h.now, {CAP: {Alternative.SEND_NOW}}),
                          Alternative.HOLD, "lapsed")

    def test_its_paid_send_gone_unknown_turns_it_off(self):
        plug = self.armed()
        key = self.waiting()["interruption_id"]
        self.ask(plug, key)
        self.h.backend.default_outcome = "unknown"
        self.h.tick(advance=1)
        self.assertEqual(self.h.record()["state"], "submission_unknown")
        stored = plug.runtime.state.arming()[CAP]
        self.assertEqual((stored["state"], stored["reason"]), (ArmingState.OFF, OffReason.SUBMISSION_UNKNOWN))


class BesideAnEarlyLookTests(SendNowCase):
    """P7 is a first-wins point and reset_credit is asked before Send now: for fifteen minutes after one of its
    credits reset a window it answers EARLY for every usage-limited recovery that waits. A person's explicit
    request is the answer taken all the same (v0.6.17) - an early look is core's own optimisation, and core makes
    none at a wait an early look does not pass, so there EARLY sent nobody and the request went nowhere.

    reset_credit's own conditions are the shipped ones; only the credit spend behind them is stubbed out.
    """
    BESIDE = (RESET_CREDIT,)

    def setUp(self):
        super().setUp()
        self.compat = {"status": "ok", "engine": {"found": True, "version": ac.ENGINE},
                       "capabilities": {name: {"state": "COMPATIBLE", "reason": "local_checks_passed"}
                                        for name in (SEND_NOW.compat, RESET_CREDIT.compat)}}
        self.measured = {name: (Verdict.PASS, ac.ENGINE)
                         for name in (Measurement.MU, Measurement.MN, Measurement.MR)}
        looking = patch.object(credits.ResetCredit, "schedule", self.early)
        looking.start()
        self.addCleanup(looking.stop)

    def early(self, record, due):
        """reset_credit's P7 while a credit of its own has just reset a window (engine/credits.py): its shipped
        conditions, with the spend that opens the fifteen minutes stubbed out."""
        if (not isinstance(record, dict) or record.get("category") != failures.USAGE_LIMIT
                or record.get("state") not in ladder.EARLY_STATES or not isinstance(due, (int, float))
                or due <= self.h.now):
            return DEFER
        return Alternative.EARLY

    def armed(self, h=None, state="armed"):
        """Both capabilities on, each with the warnings its own statement carries."""
        h = h or self.h
        plug = self.advanced(h)
        for definition in (*self.BESIDE, self.DEFINITION):
            found = plug.runtime.registry.get(definition.id)
            self.arm(plug, state=state if definition is self.DEFINITION else "armed", capability=definition.id,
                     warnings=list(plug.runtime.arming.warnings(found)))
        self.plugged(plug, h)
        return plug

    def limited(self, h=None):
        """A usage-limited recovery with no reset time, registered before either capability stood on, so no
        early look reaches it while it is being set up: its record, waiting_poll and not yet due."""
        h = h or self.h
        h.home.fail_usage(T1, TURN_A, reset=None)
        h.backend.loaded_map[T1] = "loaded"
        h.tick()
        row = h.record()
        self.assertEqual(row["state"], "waiting_poll")
        return row

    def postponed(self, h=None):
        """That recovery, past its next look, postponed by the person: a wait Send now passes and an early
        look does not, so only Send now can send it."""
        h = h or self.h
        row = self.limited(h)
        h.now = row["next_retry_at"] + 1
        accepted, _detail = h.store.postpone(row["interruption_id"], T1, h.now + 1800, h.now)
        self.assertTrue(accepted)
        return h.record()

    def test_the_persons_request_is_taken_though_the_early_look_is_offered_first(self):
        """Fails with the preference reverted: EARLY is P7's answer, Send now is never seen, and the postponed
        recovery the person asked for goes nowhere - EARLY passes no postponement, so it sends nobody either."""
        key = self.postponed()["interruption_id"]
        plug = self.armed()
        self.h.tick(advance=1)
        self.assert_no_send()
        self.assertTrue(self.ask(plug, key)["done"])
        self.h.tick(advance=1)
        self.assertEqual(len(self.h.backend.send_calls), 1)
        self.assertEqual(self.spends(plug), [(CAP, T1, key)], "paid by Send now, which carried it")
        self.assertIn((JournalCode.ACTED, Point.SCHEDULE, Alternative.SEND_NOW), self.journal(plug))

    def test_an_early_look_is_still_the_answer_where_nobody_asked(self):
        """The preference is for a person's own request alone: with none, EARLY wins P7 as it always did."""
        self.limited()
        plug = self.armed()
        self.h.tick(advance=1)
        self.assertEqual(len(self.h.backend.send_calls), 1, "looked at early, before its next look was due")
        self.assertEqual([spent[0] for spent in self.spends(plug)], [RESET_CREDIT.id], "the early look paid")

    def reset_ahead(self, h=None):
        """A usage-limited recovery waiting for its reset, registered before either capability stood on: the wait
        an early look exists for, and one core never carries a Send now out before."""
        h = h or self.h
        h.home.fail_usage(T1, TURN_A)
        h.backend.loaded_map[T1] = "loaded"
        h.tick()
        row = h.record()
        self.assertEqual(row["state"], "waiting_reset")
        self.assertGreater(row["reset_at"], h.now + 60)
        return row

    def test_waiting_for_a_reset_the_early_look_carries_the_persons_request(self):
        """Fails with the gate check in `_preferred` reverted: SEND_NOW is taken in EARLY's place, core never
        carries a Send now out before a reset, and the record waits out the early window a credit bought."""
        row = self.reset_ahead()
        plug = self.armed()
        self.assertTrue(self.ask(plug, row["interruption_id"])["done"])
        self.h.tick(advance=1)
        self.assertEqual(len(self.h.backend.send_calls), 1, "sent at once by the early look")
        self.assertLess(self.h.now, row["reset_at"], "before its reset")
        self.assertEqual([spent[0] for spent in self.spends(plug)], [RESET_CREDIT.id], "the early look paid")


class CodeTests(unittest.TestCase):
    class Scoped:
        def __init__(self, request, since, now):
            self._request, self._since, self.at = request, since, now

        def now(self):
            return self.at

        def request(self, key):
            if isinstance(self._request, Exception):
                raise self._request
            return self._request

        def since(self):
            return self._since

    def code(self, request, since=100.0, now=500.0):
        made = SendNow(None)
        made.bind(self.Scoped(request, since, now))
        return made

    def test_fail_closed(self):
        record = {"interruption_id": ac.KEY, "state": "waiting_backoff"}
        good = {"kind": OverrideKind.FORCE_ONCE, "created_at": 200.0, "used_at": None}
        self.assertIs(self.code(good).schedule(record, 0), Alternative.SEND_NOW)
        for request, since in ((None, 100.0), (dict(good, used_at=300.0), 100.0), (dict(good, kind="early_reset"), 100.0),
                               (good, 250.0), (good, None), (RuntimeError("locked"), 100.0),
                               (dict(good, created_at=500.0 - LIFETIME), 100.0)):
            with self.subTest(request=request, since=since):
                self.assertIs(self.code(request, since).schedule(record, 0), DEFER)
        self.assertIs(SendNow(None).schedule(record, 0), DEFER, "unbound")


if __name__ == "__main__":
    unittest.main()
