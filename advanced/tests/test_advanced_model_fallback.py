"""Another model when one is at capacity (v0.6.16-beta.4): only for a server error Codex coded serverOverloaded, only
after the person's Attempts, only where nothing holds the conversation while Codex is closed - never for a usage,
rate, sign-in or billing failure - one turn on the headless route in fallback mode, and a model Codex would not put
back journalled in a closed word.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from takingcase import TakingCase  # noqa: E402
from advancedcase import ENGINE  # noqa: E402
from codexsim import CodexHome, new_id  # noqa: E402
from codex_auto_resume.domain.plug import DEFER, Point  # noqa: E402
from codex_auto_resume_advanced import registry  # noqa: E402
from codex_auto_resume_advanced.codex import headless  # noqa: E402
from codex_auto_resume_advanced.codex.turns import Turns  # noqa: E402
from codex_auto_resume_advanced.engine.fallback import NOT_RESTORED, ModelFallback  # noqa: E402
from codex_auto_resume_advanced.registry import MODEL_FALLBACK  # noqa: E402
from codex_auto_resume_advanced.vocabulary import (Actor, ArmingState, ArmingWarning, Measurement, OptionKey,  # noqa: E402
                                                   Verdict)
from test_engine import T1  # noqa: E402

KEY = "%064x" % 9
TURN = "11111111-2222-3333-4444-555555555555"


class Codes:
    def __init__(self, code):
        self.code = code

    def turn_code(self, thread_id, turn_id):
        return self.code


class Scoped:
    def __init__(self, attempts=None):
        self.attempts, self.counted = attempts, []

    def options(self):
        return {} if self.attempts is None else {OptionKey.ATTEMPTS: self.attempts}

    def count(self, code):
        self.counted.append(code)


class CodeTests(unittest.TestCase):
    def code(self, error="serverOverloaded", attempts=None, follower=None):
        made = ModelFallback(None, turns=Codes(error), session=lambda capability: None,
                             follower=follower or headless.Follower(poll=0.01), app_running=lambda: False)
        made.bind(Scoped(attempts))
        return made

    @staticmethod
    def record(**changes):
        return dict({"interruption_id": KEY, "thread_id": T1, "turn_id": TURN, "category": "server_5xx",
                     "chain_continuations": 2, "holder": "none", "app": False}, **changes)

    def test_at_capacity_after_the_attempts_it_runs_one_turn_on_the_default_model(self):
        """Fails with the route's mode reverted: the turn would run on the conversation's own model."""
        run = self.code().unloaded(self.record())
        self.assertIsInstance(run, headless.HeadlessRun)
        self.assertEqual(run.mode, "fallback")

    def test_not_before_the_attempts_chosen(self):
        self.assertIs(self.code().unloaded(self.record(chain_continuations=1)), DEFER)
        self.assertIsNot(self.code(attempts=1).unloaded(self.record(chain_continuations=1)), DEFER)
        self.assertIs(self.code(attempts=3).unloaded(self.record(chain_continuations=2)), DEFER)

    def test_never_another_failure_nor_another_server_error(self):
        for category in ("usage_limit", "rate_limit_transient", "terminal_auth", "terminal_failure", "unknown"):
            self.assertIs(self.code().unloaded(self.record(category=category)), DEFER, category)
        for error in ("internalServerError", None, "usageLimitExceeded"):
            self.assertIs(self.code(error).unloaded(self.record()), DEFER, error)

    def test_only_where_nothing_holds_it_and_codex_is_closed(self):
        for where in ({"holder": "session", "app": True}, {"holder": "app_free", "app": True},
                      {"holder": "none", "app": True}):
            self.assertIs(self.code().unloaded(self.record(**where)), DEFER, where)

    def test_a_model_not_put_back_is_journalled_in_a_closed_word(self):
        class Ended:
            def live(self):
                return None

            def drain(self, capability):
                return [{"key": KEY, "end": "completed", "model_restored": False}]

        class Runs:
            def live(self):
                return []

            def ended(self, key, end):
                pass
        made = self.code(follower=Ended())
        made._scoped.runs = Runs()
        made.tick(None)
        self.assertEqual(made._scoped.counted, ["completed", NOT_RESTORED])


class ErrorCodeTests(unittest.TestCase):
    def test_only_codex_s_code_is_read_never_a_word_of_the_message(self):
        with tempfile.TemporaryDirectory() as folder:
            home = CodexHome(Path(folder))
            turn = home.add_turn(T1, None, "failed", progress=False, error_json=json.dumps(
                {"codexErrorInfo": "serverOverloaded", "message": "secret words"}))
            self.assertEqual(Turns(home.root).turn_code(T1, turn), "serverOverloaded")
            other = home.add_turn(T1, None, "failed", progress=False, error_json="not json")
            self.assertIsNone(Turns(home.root).turn_code(T1, other))
            self.assertIsNone(Turns(home.root).turn_code(T1, new_id()))


class RegistryTests(TakingCase):
    DEFINITION = MODEL_FALLBACK

    def test_it_answers_at_p16_before_headless_run_and_is_shown_after_compact_continue(self):
        at = tuple(d.id for d in registry.REGISTRY.at(Point.UNLOADED))
        self.assertLess(at.index(self.cap), at.index("headless_run"))
        shown = registry.SHOWN_ORDER
        self.assertEqual(shown.index(self.cap), shown.index("compact_continue") + 1)
        self.assertEqual(self.DEFINITION.option(OptionKey.ATTEMPTS).choices, (1, 2, 3))

    def test_unmeasured_on_this_codex_is_a_warning_never_a_refusal(self):
        plug = self.advanced()
        definition = plug.runtime.registry.get(self.cap)
        self.assertIn(ArmingWarning.UNMEASURED, plug.runtime.arming.warnings(definition))
        self.measured = {Measurement.MF: (Verdict.PASS, ENGINE)}
        self.assertNotIn(ArmingWarning.UNMEASURED, plug.runtime.arming.warnings(definition))
        self.measured = {}
        definition = plug.runtime.registry.get(self.cap)
        result = plug.runtime.arming.arm(
            self.cap, state="armed", revision=definition.revision, generation=plug.runtime.state.meta()["generation"],
            acknowledged_version=ENGINE, actor=Actor.DASHBOARD,
            warnings=[str(word) for word in plug.runtime.arming.warnings(definition)])
        self.assertTrue(result["done"], result)
        self.assertEqual(plug.runtime.states(fresh=True)[self.cap], ArmingState.ARMED)


if __name__ == "__main__":
    unittest.main()
