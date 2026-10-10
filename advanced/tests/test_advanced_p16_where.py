"""Where P16 is asked, as the two capabilities that answered it before v0.6.15-beta.3 read it.

From this version core tells a P16 record where it is asked: `holder="app_free", app=True` for a conversation the
running app does not hold, and `holder="none", app=False` where the app is closed and nothing holds it (core's
engine/delivery.py). The goal continuation and queue for opening act only on the first - a goal set while another
server holds the conversation is not seen (M2), and a queued item waits for an app that is not there - and the watch
of an item already queued for opening, which hands neither word, is still kept as before (the review's blocker 3).
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import advancedcase  # noqa: E402,F401
from codex_auto_resume.domain.plug import DEFER, Alternative  # noqa: E402
from codex_auto_resume_advanced.engine.foropen import QueueForOpen  # noqa: E402
from codex_auto_resume_advanced.engine.goal import GoalContinuation  # noqa: E402
from codex_auto_resume_advanced.vocabulary import OptionKey, OverrideKind  # noqa: E402
from test_advanced_goal import goals_db, set_goal  # noqa: E402

THREAD = "0a1b2c3d-0001-7000-8000-000000000001"
KEY = "%064x" % 7
NOW = 1_800_000_000.0
WHERE = {"app_free": {"holder": "app_free", "app": True}, "closed": {"holder": "none", "app": False},
         "session": {"holder": "session", "app": True}, "unsaid": {}}


def record(where, **more):
    return dict({"interruption_id": KEY, "thread_id": THREAD, "category": "usage_limit"}, **WHERE[where], **more)


class Scoped:
    def __init__(self, override=None):
        self.override = override

    def request(self, key):
        return self.override

    def options(self):
        return {OptionKey.DAYS: 3}

    def now(self):
        return NOW


class GoalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        goals_db(root)
        set_goal(root, THREAD, "usage_limited")
        self.code = GoalContinuation(None, home=root)

    def test_a_conversation_the_running_app_does_not_hold_is_its_route(self):
        self.assertIs(self.code.unloaded(record("app_free")), self.code)

    def test_never_with_the_app_closed_held_by_another_session_or_unsaid(self):
        """Fails with the guard reverted: the goal route would answer for a conversation another server holds."""
        for where in ("closed", "session", "unsaid"):
            with self.subTest(where):
                self.assertIs(self.code.unloaded(record(where)), DEFER)


class QueueForOpenTests(unittest.TestCase):
    def code(self, override=None):
        made = QueueForOpen(None)
        made.bind(Scoped(override))
        return made

    def test_queued_only_for_a_conversation_the_running_app_does_not_hold(self):
        self.assertIs(self.code().unloaded(record("app_free")), Alternative.QUEUE_FOR_OPEN)
        for where in ("closed", "session", "unsaid"):
            with self.subTest(where):
                self.assertIs(self.code().unloaded(record(where)), DEFER)

    def test_a_watched_item_is_still_kept_though_the_watch_says_neither_word(self):
        """Fails with the guard applied to the watch too: every item queued for opening withdrawn at once."""
        override = {"kind": OverrideKind.QUEUE_FOR_OPEN, "created_at": NOW - 3600}
        watched = record("unsaid", loaded="notLoaded", queued_since=NOW - 3600)
        self.assertIs(self.code(override).unloaded(watched), Alternative.QUEUE_FOR_OPEN)


if __name__ == "__main__":
    unittest.main()
