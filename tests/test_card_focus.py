"""Who has the keyboard around a card (v0.6.16-beta.3, issue #32: typing lost when a card appears).

The card host asks, just before a card is shown and FOCUS_AFTER after, which window class and program are in
front and which window class has the focus (ui/card/win32.focus_snapshot), and writes one line only when they
differ - so the next time it happens the log says where the keyboard went. Never a title, a text or a path.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codex_auto_resume.ui.card import stack, win32  # noqa: E402

CODEX = {"front_class": "Chrome_WidgetWin_1", "front_process": "Codex.exe", "focus_class": "Chrome_RenderWidgetHostHWND"}
MOVED = dict(CODEX, focus_class=None)


class FocusLineTests(unittest.TestCase):
    def host(self, *answers):
        said, asked = [], list(answers)
        host = stack.CardStack(log=said.append, focus=lambda: asked.pop(0))
        return host, said

    def test_a_change_is_one_line_and_no_change_is_none(self):
        host, said = self.host(dict(CODEX))
        host._focus_after(dict(CODEX))
        self.assertEqual(said, [])
        host, said = self.host(dict(MOVED))
        host._focus_after(dict(CODEX))
        self.assertEqual(len(said), 1)
        self.assertIn("Chrome_RenderWidgetHostHWND", said[0])
        self.assertIn("Codex.exe", said[0])

    def test_a_probe_that_fails_says_nothing(self):
        def broken():
            raise OSError("no")
        said = []
        host = stack.CardStack(log=said.append, focus=broken)
        host._focus_after(dict(CODEX))
        self.assertEqual(said, [])
        self.assertIsNone(stack.focus_line(None, CODEX))

    def test_only_plain_words_reach_the_log(self):
        self.assertEqual(win32._plain("Chrome_WidgetWin_1"), "Chrome_WidgetWin_1")
        self.assertEqual(win32._plain("a window title with words"), "other")
        self.assertIsNone(win32._plain(""))

    def test_the_probe_answers_its_three_keys_on_this_machine(self):
        self.assertEqual(set(win32.focus_snapshot()), {"front_class", "front_process", "focus_class"})



@unittest.skipUnless(os.name == "nt", "the card is a Windows window")
class SecondLookTests(unittest.TestCase):
    """The look FOCUS_AFTER after a card is the card host's own timer on its own thread, never a thread of its own: a
    thread that has asked user32 holds a USER object while it lives, and the card stack leaves nothing behind
    (test_notice_card.test_cards_leave_nothing_behind found two on dev CI, 2026-10-15)."""

    def setUp(self):
        from test_notice_card import EVENTS, WindowsTests, build, tray_popup
        tray_popup._gdiplus_acquire()
        self.addCleanup(tray_popup._gdiplus_release)
        self.now = 0.0
        self.said, self.asked = [], [dict(CODEX), dict(MOVED), dict(MOVED)]
        self.host = stack.CardStack(log=self.said.append, focus=lambda: self.asked.pop(0), clock=lambda: self.now,
                                    locate=lambda: dict(WindowsTests.WHERE),
                                    appearance=lambda: dict(WindowsTests.LIGHT)).create()
        self.addCleanup(self.host.destroy)
        self.card = lambda index: build("interruption", EVENTS[index][1], thread="t%d" % index)

    def test_cards_shown_start_no_thread_and_the_timer_takes_one_look_from_before_the_first(self):
        threads = threading.active_count()
        self.assertIsNotNone(self.host.show(self.card(0)))
        self.assertIsNotNone(self.host.show(self.card(1)))
        self.assertEqual(threading.active_count(), threads, "no thread waits to look again")
        self.assertEqual(self.said, [])
        self.assertEqual(self.host._handle(self.host.hwnd, stack.WM_TIMER, win32.TIMER_FOCUS, 0), 0)
        self.assertEqual(len(self.said), 1, "one look, for both cards")
        self.assertIn("Codex.exe", self.said[0])
        self.assertEqual(self.asked, [], "asked before each card and once after the last")
        self.host._handle(self.host.hwnd, stack.WM_TIMER, win32.TIMER_FOCUS, 0)
        self.assertEqual(len(self.said), 1, "a timer that comes again finds no look waiting")


if __name__ == "__main__":
    unittest.main()
