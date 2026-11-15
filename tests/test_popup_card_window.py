"""v0.6.24 (O14 amended by the owner, 2026-11-15): the popup's window IS its card.

The grey window round the card is gone: the popup is one per-pixel-alpha layered window exactly the card's size, owned
by a second, mouse-transparent layered window that holds the card's shadow on the desktop (ui/popup/layers.py), as the
notification card's two windows are. No DWM corner, no window region, no class shadow; a frame of the light uploads only
its rows (UpdateLayeredWindowIndirect's prcDirty); the opening fades through the layers' blend, never
SetLayeredWindowAttributes (after which UpdateLayeredWindow fails); clicks, hover and a screen reader's boxes are the
card's; and where Windows will not take the card the popup is the plain window it was.

Window tests: real popups far off every screen, never activated, nothing captured - run on their own through
gui_lock.sh. The windows' styles, owners, rectangles and the calls made are read; no pixel of the screen is.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import sys
import time
import unittest
from unittest import mock

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codex_auto_resume import brand  # noqa: E402

if os.name == "nt":
    from codex_auto_resume.ui import popup as tray_popup  # noqa: E402
    from codex_auto_resume.ui.popup import layers, access  # noqa: E402
    import test_tray_popup  # noqa: E402,F401  (loaded before any frame is waited on)

OFFSCREEN = (-32000, -32000)
GWL_EXSTYLE, GW_OWNER, GCL_STYLE = -20, 4, -26
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = 0x00080000, 0x00000020, 0x08000000


def _user32():
    user32 = ctypes.WinDLL("user32")
    user32.GetWindowLongW.argtypes, user32.GetWindowLongW.restype = [ctypes.c_void_p, ctypes.c_int], ctypes.c_long
    user32.GetWindow.argtypes, user32.GetWindow.restype = [ctypes.c_void_p, ctypes.c_uint], ctypes.c_void_p
    user32.GetClassLongW.argtypes, user32.GetClassLongW.restype = [ctypes.c_void_p, ctypes.c_int], ctypes.c_ulong
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRgnBox.argtypes, user32.GetWindowRgnBox.restype = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)], ctypes.c_int
    user32.IsWindow.argtypes, user32.IsWindow.restype = [ctypes.c_void_p], wintypes.BOOL
    user32.IsWindowVisible.argtypes, user32.IsWindowVisible.restype = [ctypes.c_void_p], wintypes.BOOL
    return user32


@unittest.skipUnless(os.name == "nt", "a Windows window")
class CardWindowTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(tray_popup.theme, "reduced_motion", lambda: True)    # motion has its own tests
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user32 = _user32()

    def pump(self, seconds=0.05):
        from test_tray_popup import WindowsTests
        WindowsTests.pump(self, seconds)

    def make(self, **extra):
        from test_tray_popup import EN, FakeControl, WindowsTests
        window = tray_popup.Popup(control=FakeControl(WindowsTests.ROWS), strings=EN, **extra)
        window.create()
        self.addCleanup(window.destroy)
        window.model.apply_outcome(("read",), tray_popup.perform(("read",), window.control), time.time())
        return window

    def rect(self, hwnd):
        box = wintypes.RECT()
        with tray_popup._PerMonitorDpi():                 # physical pixels, as the popup places its windows
            self.user32.GetWindowRect(hwnd, ctypes.byref(box))
        return box.left, box.top, box.right, box.bottom

    def style(self, hwnd):
        return self.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

    def recorded(self):
        """Every UpdateLayeredWindowIndirect the layers make, as (hwnd, its keywords), still made."""
        calls, real = [], layers.update

        def update(hwnd, **keywords):
            calls.append((hwnd, keywords))
            return real(hwnd, **keywords)
        patcher = mock.patch.object(layers, "update", update)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    # ---------------------------------------------------------------- what the windows are
    def test_the_popup_is_one_layered_window_owned_by_its_shadow_and_nothing_of_windows_frame(self):
        window = self.make()
        shadow = window._layers.shadow_hwnd
        self.assertTrue(window._card)
        self.assertTrue(self.style(window.hwnd) & WS_EX_LAYERED)
        self.assertEqual(self.user32.GetWindow(window.hwnd, GW_OWNER), shadow, "above its shadow, always")
        self.assertEqual(self.style(shadow) & (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE),
                         WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE, "its shadow never takes a click")
        self.assertFalse(self.user32.GetClassLongW(window.hwnd, GCL_STYLE) & tray_popup.CS_DROPSHADOW,
                         "no rectangle's shadow from the class")
        self.assertTrue(window._renderer.lone)
        window.show(activate=False, origin=OFFSCREEN)
        self.assertFalse(window._rounded, "DWM is asked for no corner")
        self.assertEqual(self.user32.GetWindowRgnBox(window.hwnd, ctypes.byref(wintypes.RECT())), 0,
                         "no window region (ERROR: none set)")

    def test_its_window_is_exactly_the_card_and_its_shadow_reaches_round_it(self):
        for theme in brand.THEMES:
            with self.subTest(theme=theme), mock.patch.object(tray_popup.window, "effective_theme", lambda *a: theme):
                window = self.make()
                window.show(activate=False, origin=OFFSCREEN)
                card = window._plan["card"]
                width, height = card[2] - card[0], card[3] - card[1]
                self.assertEqual(self.rect(window.hwnd), (OFFSCREEN[0], OFFSCREEN[1], OFFSCREEN[0] + width,
                                                          OFFSCREEN[1] + height))
                margin = window._layers.margin
                self.assertEqual(margin, tray_popup.float_reach(tray_popup.float_shadows(theme), window._plan["scale"]))
                self.assertEqual(self.rect(window._layers.shadow_hwnd),
                                 (OFFSCREEN[0] - margin, OFFSCREEN[1] - margin, OFFSCREEN[0] + width + margin,
                                  OFFSCREEN[1] + height + margin))
                self.assertTrue(self.user32.IsWindowVisible(window._layers.shadow_hwnd))
                window.hide()
                self.assertFalse(self.user32.IsWindowVisible(window._layers.shadow_hwnd), "hidden with it")

    def test_high_contrast_and_a_design_without_depth_float_no_shadow(self):
        for name, patch in (("contrast", mock.patch.object(tray_popup.theme, "high_contrast", lambda: True)),
                            ("plain", mock.patch.object(tray_popup.window, "design_setting", lambda: "plain"))):
            with self.subTest(name), patch:
                window = self.make()
                window.show(activate=False, origin=OFFSCREEN)
                self.assertEqual(window._layers.shadows, ())
                self.assertFalse(self.user32.IsWindowVisible(window._layers.shadow_hwnd))
                self.assertTrue(window._card, "still the card: its fill and its hairline")

    def test_high_contrast_coming_while_it_is_open_takes_its_shadow_away_and_going_brings_it_back(self):
        window = self.make()
        window.show(activate=False, origin=OFFSCREEN)
        shadow = window._layers.shadow_hwnd
        self.assertTrue(self.user32.IsWindowVisible(shadow))
        with mock.patch.object(tray_popup.theme, "high_contrast", lambda: True):
            window._read_look()
            window._invalidate()
            window._push()
            self.assertFalse(self.user32.IsWindowVisible(shadow), "no shadow in High Contrast")
        window._read_look()
        window._invalidate()
        window._push()
        self.assertTrue(self.user32.IsWindowVisible(shadow), "and back with the theme")

    def test_destroyed_both_windows_go(self):
        window = self.make()
        window.show(activate=False, origin=OFFSCREEN)
        body, shadow = window.hwnd, window._layers.shadow_hwnd
        window.destroy()
        self.assertFalse(self.user32.IsWindow(body))
        self.assertFalse(self.user32.IsWindow(shadow))

    # ---------------------------------------------------------------- what it costs a frame
    def test_a_frame_of_the_light_uploads_only_its_rows(self):
        window = self.make()
        window.show(activate=False, origin=OFFSCREEN)
        calls = self.recorded()
        window._static_dirty = False
        window._push()
        body = [keywords for hwnd, keywords in calls if hwnd == window.hwnd]
        self.assertEqual(len(body), 1)
        top, bottom = window._renderer.halo_rows
        card = window._plan["card"]
        self.assertEqual(body[0]["dirty"], (0, top - card[1], card[2] - card[0], bottom - card[1]))
        shadow = [keywords for hwnd, keywords in calls if hwnd == window._layers.shadow_hwnd]
        self.assertEqual(shadow, [], "its shadow did not change: no call at all")
        window._push()
        self.assertEqual(len(calls), 2, "a frame of the light is one call, on the card")

    def test_a_whole_frame_uploads_the_card_from_its_corner_of_the_canvas(self):
        window = self.make()
        window.show(activate=False, origin=OFFSCREEN)
        calls = self.recorded()
        window.hover = window._plan["targets"][0][0]
        window._invalidate()
        self.assertTrue(window._owed)
        self.pump(0.05)
        body = [keywords for hwnd, keywords in calls if hwnd == window.hwnd]
        self.assertEqual(len(body), 1, "one push for what one turn changed")
        card = window._plan["card"]
        self.assertIsNone(body[0]["dirty"])
        self.assertEqual(body[0]["source"], card[:2])
        self.assertEqual(body[0]["size"], (card[2] - card[0], card[3] - card[1]))

    # ---------------------------------------------------------------- the opening
    def test_the_opening_fades_through_the_layers_and_never_sets_layered_attributes(self):
        calls = self.recorded()
        with mock.patch.object(tray_popup.theme, "reduced_motion", lambda: False):
            window = self.make()
            refused = mock.Mock(side_effect=AssertionError("SetLayeredWindowAttributes on the card"))
            with mock.patch.object(tray_popup.messages, "_dll", side_effect=lambda name: _Guard(name, refused)):
                window.show(activate=False, origin=OFFSCREEN)
                self.assertIsNotNone(window._opening)
                self.assertEqual(window._alpha, 0, "its first picture is put up see-through")
                deadline = time.monotonic() + 5.0
                while window._opening is not None and time.monotonic() < deadline:
                    self.pump(0.016)
        self.assertIsNone(window._opening, "it arrives")
        self.assertEqual((window._alpha, window._below), (255, 0))
        alphas = [keywords["alpha"] for hwnd, keywords in calls if hwnd == window.hwnd]
        frames = len(alphas)
        self.assertLessEqual(len(calls), 2 * frames + 2, "a frame of the opening: one call each window")
        self.assertEqual(alphas[0], 0)
        self.assertEqual(alphas[-1], 255)
        self.assertEqual(alphas, sorted(alphas), "only ever more opaque")
        self.assertTrue(self.style(window.hwnd) & WS_EX_LAYERED, "and still the card")

    # ---------------------------------------------------------------- where things are
    def test_it_opens_its_card_the_window_s_gap_from_the_taskbar(self):
        window = self.make()
        # A monitor of its own far off every real one (placement reads only the rectangles it is given), its taskbar at
        # the bottom: nothing is put on this machine's screen.
        x0, y0 = OFFSCREEN
        work, monitor = (x0, y0, x0 + 1920, y0 + 1040), (x0, y0, x0 + 1920, y0 + 1080)
        icon = (x0 + 1200, y0 + 1050, x0 + 1224, y0 + 1074)
        with mock.patch.object(tray_popup.window.Popup, "_screen_now",
                               lambda self: {"icon": icon, "cursor": (icon[0] + 10, icon[1] + 10), "dpi": 144,
                                             "work": work, "monitor": monitor}):
            window.show(activate=False)
            try:
                left, top, right, bottom = self.rect(window.hwnd)
                gap = int(round(brand.SPACING["m"] * 1.5))
                self.assertEqual(bottom, work[3] - gap, "the card's edge, where the grey window's was")
                self.assertEqual((left + right) // 2, (icon[0] + icon[2]) // 2)
            finally:
                window.hide()

    def test_a_click_and_a_screen_reader_find_what_is_drawn_there(self):
        window = self.make()
        window.show(keyboard=True, activate=False, origin=OFFSCREEN)
        card = window._plan["card"]
        target, (left, top, right, bottom) = window._plan["targets"][0]
        x, y = (left + right) // 2 - card[0], (top + bottom) // 2 - card[1]       # the card window's own pixels
        self.assertEqual(window._hit((y << 16) | x), target)
        self.assertIsNone(window._hit(0), "its corner is no button")
        box = access.PopupAccessible(window)
        items = box.items()
        index = next(number for number, item in enumerate(items, 1) if item["target"] == target)
        out = [ctypes.c_long() for _ in range(4)]
        child = access.VARIANT()
        child.vt, child.value.lVal = 3, index                       # VT_I4: the item's child id
        variant = (ctypes.addressof(child),) if access._WIDE else (3, 0, index, 0)
        self.assertEqual(box._location(None, *[ctypes.pointer(value) for value in out], *variant), 0)
        screen_left, screen_top = OFFSCREEN[0] + items[index - 1]["rect"][0] - card[0], \
            OFFSCREEN[1] + items[index - 1]["rect"][1] - card[1]
        self.assertEqual((out[0].value, out[1].value), (screen_left, screen_top))

    # ---------------------------------------------------------------- where Windows will not
    def test_refused_it_is_the_plain_window_it_was(self):
        logged = []
        window = self.make(log=logged.append)
        with mock.patch.object(layers, "update", lambda hwnd, **keywords: False):
            window.show(activate=False, origin=OFFSCREEN)
        self.assertFalse(window._card)
        self.assertFalse(self.style(window.hwnd) & WS_EX_LAYERED)
        self.assertFalse(window._renderer.lone, "its grey ground again")
        self.assertTrue(window.visible)
        self.assertTrue(any("card window unavailable" in line for line in logged), logged)
        self.assertEqual(window._client_offset(), (0, 0))
        canvas = window.render()
        self.assertEqual(canvas.pixels()[3], 255, "drawn opaque, for WM_PAINT")


class _Guard:
    """A DLL whose SetLayeredWindowAttributes fails the test; everything else is the real DLL's."""

    def __init__(self, name, refused):
        self._real, self._refused = tray_popup.win32._dll(name), refused

    def __getattr__(self, name):
        return self._refused if name == "SetLayeredWindowAttributes" else getattr(self._real, name)


if __name__ == "__main__":
    unittest.main()
