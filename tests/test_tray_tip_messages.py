"""What the icon does with the shell's words about hovering (v0.6.24): its own tooltip card shown and hidden.

Under NOTIFYICON_VERSION_4 the icon leaves NIF_SHOWTIP out while its card can be shown, so Windows draws no tooltip and
says NIN_POPUPOPEN as the pointer rests on the icon and NIN_POPUPCLOSE as it leaves. The icon shows the card at the
shell's anchor point and hides it as the pointer leaves, on a click, the menu, the popup, Explorer starting again, a
locked session and the icon's end; where the card cannot be made or shown, or the version is not 4, or the shell never
says the pointer rests there, Windows' own tooltip comes back (NIF_SHOWTIP) - never none. szTip is the whole tooltip
throughout.

The icon's window procedure is called directly here with a stand-in card and a stand-in shell, as the other tray tests
call it. LiveCardTests shows the real card - far off the screen, never activated - so this module runs under the GUI lock.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
import time
import types
import unittest
from unittest import mock

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import interface  # noqa: E402
from codex_auto_resume.ui import tray  # noqa: E402
from codex_auto_resume.ui.tray import icon as icon_module, words  # noqa: E402
from codex_auto_resume.ui.tray.win32 import (CALLBACK, NIF_SHOWTIP, NIF_TIP, NIM_ADD, NIM_MODIFY,  # noqa: E402
                                             NIM_SETVERSION, NIN_KEYSELECT, NIN_SELECT, WM_CONTEXTMENU,
                                             WM_DESTROY, WM_LBUTTONDBLCLK, WM_TIMER, WM_WTSSESSION_CHANGE,
                                             WTS_SESSION_LOCK,
                                             WTS_REMOTE_DISCONNECT)

EN = interface.STRINGS["en"]
NIN_POPUPOPEN, NIN_POPUPCLOSE = 0x0406, 0x0407
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_RBUTTONDOWN = 0x0200, 0x0201, 0x0204
ICON_RECT = (1700, 1040, 1724, 1064)


class Shell:
    """user32 and shell32 as the icon calls them: every call kept; Shell_NotifyIconW's flags read off its structure."""

    def __init__(self, version=1):
        self.calls, self.version = [], version

    def __call__(self, name):
        return self

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def call(*arguments):
            self.calls.append((name, arguments))
            if name == "Shell_NotifyIconW":
                action, data = arguments[0], arguments[1]._obj
                if action == NIM_SETVERSION:
                    return self.version
                self.notified.append((action, data.uFlags, data.szTip))
            return 1
        return call

    @property
    def notified(self):
        if "_notified" not in self.__dict__:
            self.__dict__["_notified"] = []
        return self.__dict__["_notified"]


class Card:
    """The card as the icon uses it."""

    made = []

    def __init__(self, *, content=None, held=None, log=None, fail=None):
        self.content, self.held, self.fail = content, held, fail
        self.shown, self.hidden, self.destroyed = [], [], 0
        self.visible = False

    def show(self, icon=None, point=None):
        if self.fail == "show":
            raise OSError("UpdateLayeredWindow")
        self.shown.append((icon, point))
        self.visible = True

    def hide(self, at_once=True):
        self.hidden.append(at_once)
        self.visible = False

    def destroy(self):
        self.destroyed += 1


def anchor(x, y):
    return (x & 0xFFFF) | ((y & 0xFFFF) << 16)


class IconCase(unittest.TestCase):
    def setUp(self):
        self.shell = Shell()
        patcher = mock.patch.object(icon_module, "_dll", self.shell)
        patcher.start()
        self.addCleanup(patcher.stop)
        rect = mock.patch("codex_auto_resume.ui.popup.icon_rect", return_value=ICON_RECT)
        rect.start()
        self.addCleanup(rect.stop)
        self.icon = tray.Tray(strings=EN, edition="advanced")
        self.icon._hwnd = 0x1234
        self.icon._version4 = True
        self.icon.update({"enabled": True, "waiting": 2, "next_at": time.time() + 200})
        # What a click would open: nothing here, so the tests see the card's part alone.
        self.icon._adopt_settings = lambda: None
        self.icon._theme_menu = lambda: None
        self.icon._draw_menu = lambda items, paused: True
        self.icon._power_armed = lambda: False
        self.icon._refresh = lambda: None

    def event(self, event, wparam=0):
        return self.icon._wndproc(self.icon._hwnd, CALLBACK, wparam, event | (1 << 16))

    def with_card(self):
        card = Card()
        self.icon._tip = card
        return card


class ShowTests(IconCase):
    def test_the_pointer_resting_shows_the_card_at_the_shells_anchor(self):
        card = self.with_card()
        self.event(NIN_POPUPOPEN, anchor(-100, 1050))
        (icon, point), = card.shown
        self.assertEqual((icon(), point), (ICON_RECT, (-100, 1050)), "the anchor is read signed: a monitor left of the primary")

    def test_the_first_rest_makes_the_card_with_what_the_tooltip_says(self):
        made = []

        def make(**given):
            made.append(Card(**given))
            return made[-1]
        with mock.patch("codex_auto_resume.ui.tray.tipcard.TipCard", side_effect=make):
            self.event(NIN_POPUPOPEN, anchor(1710, 1050))
            self.event(NIN_POPUPCLOSE)
            self.event(NIN_POPUPOPEN, anchor(1710, 1050))
        self.assertEqual(len(made), 1, "made once and kept")
        self.assertEqual(len(made[0].shown), 2)
        parts, snapshot, strings = made[0].content()
        self.assertEqual(words.tooltip_joined(parts)[:words.TIP_CHARS - 1],
                         words.tooltip(snapshot, strings, time.time(), "advanced"))
        self.assertEqual(parts["edition"], "Advanced")
        self.assertIs(made[0].held.__func__, tray.Tray._popup_held)

    def test_not_over_the_popup_or_the_menu(self):
        card = self.with_card()
        self.icon._popup = types.SimpleNamespace(visible=True, hide=lambda: None)
        self.event(NIN_POPUPOPEN, anchor(1710, 1050))
        self.icon._popup = None
        self.icon._menu_drawn = types.SimpleNamespace(visible=True)
        self.event(NIN_POPUPOPEN, anchor(1710, 1050))
        self.assertEqual(card.shown, [])

    def test_without_version_4_there_is_no_card(self):
        self.icon._version4 = False
        with mock.patch("codex_auto_resume.ui.tray.tipcard.TipCard") as make:
            self.icon._show_tip(anchor(1710, 1050))
        make.assert_not_called()


class HideTests(IconCase):
    def test_each_way_away_hides_it(self):
        ways = {
            "the pointer leaves": lambda: self.event(NIN_POPUPCLOSE),
            "a press": lambda: self.event(WM_LBUTTONDOWN),
            "a right press": lambda: self.event(WM_RBUTTONDOWN),
            "a click": lambda: self.event(NIN_SELECT),
            "Enter on the icon": lambda: self.event(NIN_KEYSELECT),
            "a double click": lambda: self.event(WM_LBUTTONDBLCLK),
            "the menu": lambda: self.event(WM_CONTEXTMENU),
            "the menu's Open the popup": lambda: self.icon._open_popup(),
            "Explorer again": lambda: self.icon._wndproc(self.icon._hwnd, self.icon._taskbar_created, 0, 0),
            "a locked session": lambda: self.icon._wndproc(self.icon._hwnd, WM_WTSSESSION_CHANGE, WTS_SESSION_LOCK, 0),
            "a session away": lambda: self.icon._wndproc(self.icon._hwnd, WM_WTSSESSION_CHANGE, WTS_REMOTE_DISCONNECT, 0),
        }
        self.icon._taskbar_created = 0xC0DE
        for name, way in ways.items():
            with self.subTest(name):
                self.icon._session_locked = self.icon._session_away = False
                card = self.with_card()
                card.visible = True
                way()
                self.assertEqual(card.hidden, [name != "the pointer leaves"],
                                 "fading as the pointer leaves, at once otherwise")

    def test_the_icons_end_destroys_it(self):
        card = self.with_card()
        self.icon._wndproc(self.icon._hwnd, WM_DESTROY, 0, 0)
        self.assertEqual(card.destroyed, 1)
        self.assertIsNone(self.icon._tip)


class FlagTests(IconCase):
    def flags(self):
        self.icon._notify(NIM_MODIFY)
        return self.shell.notified[-1][1]

    def test_windows_tooltip_is_left_out_only_while_the_card_can_be_shown(self):
        for version4, tip, shows in ((True, None, False), (True, Card(), False), (True, False, True),
                                     (False, None, True), (False, False, True)):
            with self.subTest(version4=version4, tip=tip):
                self.icon._version4, self.icon._tip = version4, tip
                flags = self.flags()
                self.assertEqual(bool(flags & NIF_SHOWTIP), shows)
                self.assertTrue(flags & NIF_TIP, "szTip is there either way, for a screen reader")
        self.assertEqual(self.shell.notified[-1][2], words.tooltip(self.icon._shown(), EN, time.time(), "advanced"))

    def test_version_4_drops_windows_tooltip_as_the_icon_is_added_and_after_explorer_restarts(self):
        self.icon._version4 = False
        self.icon._notify(NIM_ADD)
        self.icon._set_version()
        self.assertEqual([(action, bool(flags & NIF_SHOWTIP)) for action, flags, _ in self.shell.notified],
                         [(NIM_ADD, True), (NIM_MODIFY, False)])
        self.shell.notified.clear()
        self.icon._taskbar_created = 0xC0DE
        self.icon._wndproc(self.icon._hwnd, 0xC0DE, 0, 0)
        self.assertEqual([(action, bool(flags & NIF_SHOWTIP)) for action, flags, _ in self.shell.notified],
                         [(NIM_ADD, False), (NIM_MODIFY, False)])

    def test_a_refused_version_keeps_windows_tooltip(self):
        self.shell.version = 0
        self.icon._version4 = False
        self.icon._notify(NIM_ADD)
        self.icon._set_version()
        self.assertFalse(self.icon._version4)
        self.assertEqual([(action, bool(flags & NIF_SHOWTIP)) for action, flags, _ in self.shell.notified],
                         [(NIM_ADD, True)])


class FallbackTests(IconCase):
    def assert_windows_tooltip_back(self):
        self.assertIs(self.icon._tip, False)
        action, flags, _ = self.shell.notified[-1]
        self.assertEqual(action, NIM_MODIFY)
        self.assertTrue(flags & NIF_SHOWTIP)
        self.assertFalse(self.icon._tip_shows())

    def test_a_card_that_cannot_be_made_gives_windows_tooltip_back(self):
        with mock.patch("codex_auto_resume.ui.tray.tipcard.TipCard", side_effect=OSError("RegisterClassW")):
            self.event(NIN_POPUPOPEN, anchor(1710, 1050))
        self.assert_windows_tooltip_back()

    def test_a_card_that_cannot_be_shown_gives_windows_tooltip_back(self):
        card = Card(fail="show")
        self.icon._tip = card
        self.event(NIN_POPUPOPEN, anchor(1710, 1050))
        self.assert_windows_tooltip_back()
        self.assertEqual(card.destroyed, 1)


class SilentShellTests(IconCase):
    """A shell that never says the pointer rests on the icon (NIN_POPUPOPEN) with Windows' tooltip off: each visit is timed
    from its first move (TIMER_TIP), so a pointer that comes to rest - and sends no more moves - is counted too; after
    TIP_SILENT_VISITS silent visits Windows' own tooltip comes back. One visit never decides, a shell that has said the word
    once is never timed again, and the word after a fallback turns the card back on at once."""

    def setUp(self):
        super().setUp()
        self.clock = [100.0]
        fake = types.SimpleNamespace(monotonic=lambda: self.clock[0], time=time.time)
        patcher = mock.patch.object(icon_module, "time", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.on_icon = True
        self.icon._pointer_on_icon = lambda: self.on_icon

    def visit(self, at, moves=(0.0, 0.1, 0.2), rest=10.0):
        """The pointer comes onto the icon - a few moves - and rests there; the visit's timer fires TIP_PROBE_S after its
        first move."""
        for offset in moves:
            self.clock[0] = at + offset
            self.event(WM_MOUSEMOVE)
        self.clock[0] = at + icon_module.TIP_PROBE_S
        self.icon._wndproc(self.icon._hwnd, WM_TIMER, icon_module.TIMER_TIP, 0)
        self.clock[0] = at + rest

    def showtip(self):
        return [bool(flags & NIF_SHOWTIP) for action, flags, _ in self.shell.notified if action == NIM_MODIFY]

    def test_a_resting_pointer_brings_windows_tooltip_back_after_two_silent_visits(self):
        """R1: moves only came while the pointer moved; resting, it sent none and was never counted."""
        self.visit(100.0)
        self.assertTrue(self.icon._tip_shows(), "one visit never decides")
        self.assertEqual(self.showtip(), [])
        self.visit(120.0)
        self.assertFalse(self.icon._tip_shows())
        self.assertEqual(self.showtip(), [True], "Windows' tooltip, never none")
        self.assertIsNot(self.icon._tip, False, "the card is not given up: the shell may still say the word")
        timers = [arguments for name, arguments in self.shell.calls if name == "SetTimer"]
        self.assertEqual([(timer[1], timer[2]) for timer in timers], [(icon_module.TIMER_TIP, 2000)] * 2)

    def test_a_pointer_that_only_passed_by_is_not_a_silent_visit(self):
        self.on_icon = False
        for at in (100.0, 120.0, 140.0):
            self.visit(at, moves=(0.0, 0.1))
        self.assertTrue(self.icon._tip_shows())

    def test_a_slow_drift_before_the_word_switches_nothing_off_for_good(self):
        """R2: a drift of moves for three seconds before the shell's first word used to give the card up for the icon's
        whole life; now one visit cannot, and the word that follows shows the card."""
        self.visit(100.0, moves=[0.25 * step for step in range(14)])
        card = self.with_card()
        self.event(NIN_POPUPOPEN, anchor(1710, 1050))
        self.assertEqual(len(card.shown), 1)
        for at in (120.0, 140.0, 160.0):
            self.visit(at)
        self.assertTrue(self.icon._tip_shows(), "a shell that has said the word is never timed again")

    def test_the_word_after_a_fallback_turns_the_card_back_on_at_once(self):
        self.visit(100.0)
        self.visit(120.0)
        self.assertFalse(self.icon._tip_shows())
        card = self.with_card()
        self.event(NIN_POPUPOPEN, anchor(1710, 1050))
        self.assertTrue(self.icon._tip_shows())
        self.assertEqual(self.showtip(), [True, False], "Windows' tooltip off again as the card comes back")
        self.assertEqual(len(card.shown), 1)


def _pump(seconds):
    user32 = ctypes.WinDLL("user32")
    message = wintypes.MSG()
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        time.sleep(0.01)


@unittest.skipUnless(os.name == "nt", "the card is a Windows window")
class LiveCardTests(unittest.TestCase):
    """The real card, placed far off every screen: it is made, shown without taking the foreground or a click, drawn,
    and hidden at once or fading."""

    # The icon in the taskbar, below the work area, as it stands: the card goes TIP_GAP above the taskbar's edge.
    FAR = {"box": (-31000, -30950, -30976, -30926), "dpi": 144, "work": (-32000, -32000, -30000, -30960),
           "monitor": (-32000, -32000, -30000, -30900)}

    def setUp(self):
        from codex_auto_resume.ui.tray import tipcard
        self.tipcard = tipcard
        snapshot = {"enabled": True, "waiting": 1, "next_at": time.time() + 90,
                    "advanced": {"meter": {"windows": [{"window_minutes": 300, "used_percent": 40}]}}}
        self.card = tipcard.TipCard(content=lambda: (words.tooltip_parts(snapshot, EN, time.time(), "advanced"),
                                                     snapshot, EN), held=lambda: False)
        self.addCleanup(self.card.destroy)
        patcher = mock.patch.object(tipcard, "tip_screen", lambda icon=None, point=None: dict(self.FAR))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_it_shows_without_the_foreground_and_lets_every_click_through(self):
        user32 = ctypes.WinDLL("user32")
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        before = user32.GetForegroundWindow()
        self.card.show(point=(-31000, -31000))
        _pump(0.3)
        self.assertTrue(self.card.visible)
        self.assertTrue(user32.IsWindowVisible(self.card.hwnd))
        self.assertEqual(user32.GetForegroundWindow(), before)
        style = user32.GetWindowLongW(self.card.hwnd, -20) & 0xFFFFFFFF
        self.assertEqual(style & self.tipcard.TIP_STYLE, self.tipcard.TIP_STYLE)
        rect = wintypes.RECT()
        from codex_auto_resume.ui import popup
        with popup._PerMonitorDpi():                 # the card's own pixels, as it placed itself
            user32.GetWindowRect(self.card.hwnd, ctypes.byref(rect))
        width, height = self.card._plan["size"]
        self.assertEqual((rect.right - rect.left, rect.bottom - rect.top), (width, height))
        self.assertEqual(rect.bottom, self.FAR["work"][3] - 12, "TIP_GAP at 150 % above the taskbar")
        self.assertIn("next check in", self.card.text)
        self.card.hide(at_once=True)
        self.assertFalse(user32.IsWindowVisible(self.card.hwnd))

    def test_as_the_pointer_leaves_it_fades_and_is_gone(self):
        user32 = ctypes.WinDLL("user32")
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        self.card.show(point=(-31000, -31000))
        _pump(0.4)
        self.card.hide(at_once=False)
        _pump(0.6)
        self.assertFalse(user32.IsWindowVisible(self.card.hwnd))
        self.assertIsNone(self.card._fade)


if __name__ == "__main__":
    unittest.main()
