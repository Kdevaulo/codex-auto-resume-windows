"""The icon's own tooltip card (v0.6.24): its window, its picture, and what a screen reader is told.

tipplan.py says where everything goes; this puts it on the screen. Under NOTIFYICON_VERSION_4 with NIF_SHOWTIP left out,
Windows draws no tooltip of its own and tells the icon when the pointer rests on it (NIN_POPUPOPEN) and leaves
(NIN_POPUPCLOSE); the icon (icon.py) then shows and hides this card. It lives on the icon's thread in the watcher, as
the popup and the menu do (standard F8: one watcher process hosts the icon, the popup and the card), and is one layered
window - an alpha for every pixel - that never takes the focus or a click: WS_EX_NOACTIVATE | WS_EX_TRANSPARENT, as the
menu has while it fades. It is made on the first hover, kept, and hidden between hovers.

It is drawn by the popup's renderer, in the popup's palette, fonts, radii and lights, at the scale of the monitor the
icon is on: the status light is the popup header's own drawing, breathing as it does and held by the same stoppers
(Reduce motion, Windows' animation setting, High Contrast, battery saver, a locked session - O15). In High Contrast it is
the system's colours; right to left it is mirrored. It is placed by the popup's own placement: beside the icon, on the
taskbar's side, TIP_GAP from it and inside the work area (O16). Each second it is shown it is drawn again, for the
countdown; while the light breathes, only the light's band is.

A screen reader keeps the text it always had: szTip stays the tooltip's whole text (icon.py), and the card answers
WM_GETOBJECT with a tooltip whose name is that same text. Nothing here acts: hovering shows, and that is all.

The card draws with no window at all (TipRenderer, `draw_offscreen`), as the popup does, so the main session can make
its picture (O17).
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os
import time

from ... import brand, l10n
from ...win import textsize
from ...win.dll import WNDCLASSW, WNDPROC
from .. import popup
from ..popup import access
from ..popup.motion import GLIDE_FRAME_MS, closing, opening
from ..popup.win32 import MENU_BLEND, MENU_SIZE, WM_SYSCOLORCHANGE
from .tipplan import TIP_GAP, tip_anchor, tip_layout
from .words import tooltip_joined

ULW_ALPHA, AC_SRC_ALPHA = 0x2, 0x1
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_NOACTIVATE = 0x00080000, 0x00000020, 0x08000000
# Never activated, never hit: what the card is to the pointer and the keyboard.
TIP_STYLE = WS_EX_LAYERED | popup.WS_EX_TOOLWINDOW | popup.WS_EX_TOPMOST | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT
WM_MOUSEACTIVATE, MA_NOACTIVATE, WM_NCHITTEST, HTTRANSPARENT = 0x0021, 3, 0x0084, -1
WM_DISPLAYCHANGE, WM_THEMECHANGED, WM_DPICHANGED = 0x007E, 0x031A, 0x02E0
# Its timers: the one-second redraw (the countdown, and what the snapshot says now), the light's frames while it
# breathes, and its fade's.
TIP_TICK, TIP_FRAME, TIP_FADE = 1, 2, 3
# What a screen reader is told of it (oleacc.h): a tooltip, read only, shown and hidden.
ROLE_SYSTEM_TOOLTIP, STATE_SYSTEM_READONLY = 0x0D, 0x40
EVENT_OBJECT_SHOW, EVENT_OBJECT_HIDE = 0x8002, 0x8003


def tip_light(snapshot, now=None) -> str:
    """The light the card's dot shows: the popup header's word for the icon's own snapshot (popup.snapshot_activity),
    a failure nobody has seen red as the icon shows it. The watcher hosts the card, so it is known to be running."""
    if snapshot.get("failed"):
        return "failed"
    return popup.snapshot_activity(snapshot, time.time() if now is None else now)


def tip_place(plan, work, monitor, box) -> tuple:
    """Where the window goes, (x, y): the popup's placement for the card's size - beside `box` (tip_anchor), on the
    taskbar's side of the monitor, TIP_GAP from the taskbar and the icon, inside the work area. Physical pixels,
    negative on a monitor left of or above the primary one."""
    card = plan["card"]
    gap = int(round(TIP_GAP * plan["scale"]))
    x, y, _ = popup.place((card[2] - card[0], card[3] - card[1]), work, monitor, icon=box, gap=gap)
    return x - card[0], y - card[1]


def tip_screen(icon=None, point=None) -> dict:
    """Where the card is to stand now, read from Windows in physical pixels: the box it stands by (tip_anchor, from the
    icon's rectangle, the shell's anchor point and the pointer), the work area and the whole of the monitor that box is
    on, and that monitor's DPI. `icon` is the rectangle or what asks for it (popup.icon_rect), asked here in per-monitor
    pixels as the popup asks it."""
    popup._declare()
    user32 = popup._dll("user32")
    with popup._PerMonitorDpi():
        icon = icon() if callable(icon) else icon
        spot = W.POINT()
        user32.GetCursorPos(C.byref(spot))
        box = tip_anchor(icon, point, (spot.x, spot.y)) or (spot.x, spot.y, spot.x + 1, spot.y + 1)
        probe = W.RECT(*box)
        monitor = user32.MonitorFromRect(C.byref(probe), popup.MONITOR_DEFAULTTONEAREST)
        info = popup.MONITORINFO()
        info.cbSize = C.sizeof(popup.MONITORINFO)
        user32.GetMonitorInfoW(monitor, C.byref(info))
        dpi = 0
        try:
            x, y = W.UINT(0), W.UINT(0)
            if popup._dll("shcore").GetDpiForMonitor(C.c_void_p(monitor), 0, C.byref(x), C.byref(y)) == 0:
                dpi = x.value
        except Exception:
            dpi = 0
    work, whole = info.rcWork, info.rcMonitor
    return {"box": box, "dpi": dpi or 96, "work": (work.left, work.top, work.right, work.bottom),
            "monitor": (whole.left, whole.top, whole.right, whole.bottom)}


# ------------------------------------------------------------------------------ the picture
class TipRenderer(popup.Renderer):
    """The popup's renderer, drawing the card: its ground and hairline over nothing, its chip, bars, words and light."""

    def tip_layout(self, parts, light, scale, locale):
        """The card's plan in `locale` at `scale`: mirrored, as the popup's is, when the language is written right to left."""
        self.use(locale, scale)
        laid = tip_layout(parts, light, scale, self.measure)
        return popup.mirror(laid) if l10n.right_to_left(locale) else laid

    def draw_tip(self, plan, frame=None):
        """The whole card into the canvas, premultiplied, its alpha kept: transparent but for the card. Returns the canvas."""
        width, height = plan["size"]
        scale, canvas = plan["scale"], self.canvas
        canvas.ensure(width, height)
        popup._dll("gdi32").GdiFlush()
        C.memset(canvas.bits, 0, width * height * 4)
        self._use_scale(scale)
        card = plan["items"][0]
        radius = self._corner(card, scale)
        with popup._Painter(canvas, popup.PIXEL_FORMAT_32BPP_PARGB) as paint:
            # The card's ground and hairline, and nothing round it: no lift, no drop shadow and no lit edge, exactly as
            # the icon's menu (the owner, 2026-11-01 and 11-02; tests/test_tray_menu_no_glow.py) - a floating surface by the
            # taskbar showed its shadow and highlight as a halo on a dark taskbar. The card fills its window for that reason.
            ground = (self._argb("surface") if self.contrast
                      else popup._pack(brand.rgb(brand.card_ground(self._theme(), self._design()))))
            paint.fill_round(card["rect"], radius, ground)
            paint.stroke_round(card["rect"], radius, self._argb("line"), max(1.0, round(scale)))
            for item in plan["items"]:
                if item["kind"] in ("chip", "meter"):
                    self._ground_item(paint, item, scale, None)
        self._text(canvas.dc, plan, ())
        self._opaque_words(plan)
        self._keep_halo_band(plan)
        return self.draw_tip_light(plan, frame, restore=False)

    def draw_tip_light(self, plan, frame, *, restore=True):
        """Only the light, for one of its frames: the band of rows behind it put back, and the light drawn on it."""
        item = next((entry for entry in plan["items"] if entry["kind"] == "halo"), None)
        if item is None:
            return self.canvas
        if restore:
            if self._halo_plan is not plan or self._halo_band is None:
                raise ValueError("the whole card has to be drawn before its light")
            offset, band = self._halo_band
            C.memmove(self.canvas.bits.value + offset, band, len(band))
        with popup._Painter(self.canvas, popup.PIXEL_FORMAT_32BPP_PARGB) as paint:
            self._halo(paint, item, plan["scale"], frame)
        return self.canvas

    def _opaque_words(self, plan):
        """GDI's text clears the alpha of what it touches: every line lies on the opaque card, so it is put back whole."""
        canvas = self.canvas
        popup._dll("gdi32").GdiFlush()
        width, height = canvas.width, canvas.height
        memory = memoryview((C.c_ubyte * (width * height * 4)).from_address(canvas.bits.value)).cast("B")
        for item in plan["items"]:
            if item["kind"] != "text":
                continue
            left, top, right, bottom = (int(value) for value in item["rect"])
            left, right = max(0, left), min(width, right)
            if right <= left:
                continue
            for row in range(max(0, top), min(height, bottom)):
                start = (row * width + left) * 4 + 3
                memory[start:(row * width + right) * 4:4] = b"\xff" * (right - left)


def draw_offscreen(parts, light, *, scale=1.0, locale=l10n.DEFAULT, theme="light", design=brand.DEFAULT_DESIGN,
                   contrast=False, frame=None) -> tuple:
    """The card drawn with no window (O17): (plan, BGRA premultiplied pixels) for `parts` (words.tooltip_parts) and the
    light, at `scale`, in `locale`, the theme, the design and High Contrast or not - what a picture of it is made from."""
    renderer = TipRenderer()
    try:
        renderer.theme, renderer.design, renderer.contrast = theme, design, contrast
        plan = renderer.tip_layout(parts, light, scale, locale)
        return plan, bytes(renderer.draw_tip(plan, frame).pixels())
    finally:
        renderer.close()


# ------------------------------------------------------------------------------ a screen reader
class TipAccessible(popup.PopupAccessible):
    """The card's client object for MSAA: a tooltip with no children, named with the tooltip's whole text - what szTip
    says, untruncated."""

    def items(self):
        return []

    def _name(self, this, *arguments):
        return self._string(arguments, lambda item: self.popup.text if item is None else None)

    def _description(self, this, *arguments):
        return self._string(arguments, lambda item: None)

    def _role(self, this, *arguments):
        *variant, out = arguments
        child, _ = self._item(variant)
        if child is None:
            return access.E_INVALIDARG
        return self._number(out, ROLE_SYSTEM_TOOLTIP)

    def _state(self, this, *arguments):
        *variant, out = arguments
        child, _ = self._item(variant)
        if child is None:
            return access.E_INVALIDARG
        return self._number(out, STATE_SYSTEM_READONLY)


# ------------------------------------------------------------------------------ the window
class TipCard:
    """The card's window: made the first time the pointer rests on the icon, shown and hidden after that, destroyed with
    the icon. On the icon's thread only.

    `content()` returns (parts, snapshot, strings): words.tooltip_parts of the icon's snapshot, that snapshot, and the
    catalog it is said in - read again each second it is shown. `held()` says whether battery saver or a locked session
    holds what moves (the icon's own reading, as the popup is handed it)."""

    def __init__(self, *, content, held=None, log=None):
        self.content, self.held = content, held
        self.log = log or (lambda *unused: None)
        self.hwnd = None
        self.visible = False
        self.text = ""                           # the tooltip's whole text, as a screen reader is told it
        self.strings, self.locale = {}, l10n.DEFAULT
        self.contrast, self._theme, self._design, self._reduced = False, "light", brand.DEFAULT_DESIGN, False
        self._renderer = None
        self._plan = None
        self._shown = None                       # (parts, light, locale, look) the plan was made from
        self._screen = None
        self._origin = (0, 0)
        self._proc = None
        self._class = None
        self._access = None
        self._light, self._light_since = None, time.monotonic()
        self._frame_running = False
        # How opaque it is, and its fade: ("in", started_ms) or ("out", started_ms, the alpha it left from), or None.
        self._alpha, self._fade = 255, None

    # ------------------------------------------------------------------ life
    def create(self):
        popup._declare()
        user32, kernel32 = popup._dll("user32"), popup._dll("kernel32")
        instance = kernel32.GetModuleHandleW(None)
        self._proc = WNDPROC(self._wndproc)
        klass = WNDCLASSW()
        klass.lpfnWndProc = self._proc
        klass.hInstance = instance
        klass.hCursor = user32.LoadCursorW(None, C.c_void_p(popup.IDC_ARROW))
        self._class = "CodexAutoResumeTip-%d-%d" % (os.getpid(), id(self))
        klass.lpszClassName = self._class
        if not user32.RegisterClassW(C.byref(klass)):
            self._class = None
            raise OSError("RegisterClassW")
        try:
            with popup._PerMonitorDpi():
                self.hwnd = user32.CreateWindowExW(TIP_STYLE, self._class, "Codex Auto Resume", popup.WS_POPUP,
                                                   0, 0, 1, 1, None, None, instance, None)
            if not self.hwnd:
                raise OSError("CreateWindowExW")
            self._renderer = TipRenderer()
        except Exception:
            self.destroy()
            raise

    def destroy(self):
        user32 = popup._dll("user32")
        access.disconnect(self)
        hwnd, self.hwnd = self.hwnd, None
        self.visible = False
        self._fade = None
        if hwnd:
            for timer in (TIP_TICK, TIP_FRAME, TIP_FADE):
                user32.KillTimer(hwnd, timer)
            user32.DestroyWindow(hwnd)
        self._frame_running = False
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
        self._plan = self._shown = None
        if self._class:
            user32.UnregisterClassW(self._class, popup._dll("kernel32").GetModuleHandleW(None))
            self._class = None

    # ------------------------------------------------------------------ the icon asks
    def show(self, icon=None, point=None):
        """Shown beside the icon - `icon` its rectangle, or what asks for it, or None; `point` the shell's anchor point or
        None - with what the icon says now; already shown, it is brought up to date where it is."""
        if self.hwnd is None:
            self.create()
        self._read_look()
        self._screen = tip_screen(icon, point)
        fading = self._fade is not None and self._fade[0] == "out"
        self._lay(force=True)
        user32 = popup._dll("user32")
        if not self.visible or fading:
            self._appear()
        self._push()
        width, height = self._plan["size"]
        with popup._PerMonitorDpi():
            user32.SetWindowPos(self.hwnd, C.c_void_p(popup.HWND_TOPMOST), self._origin[0], self._origin[1],
                                width, height, popup.SWP_NOACTIVATE)
        user32.ShowWindow(self.hwnd, popup.SW_SHOWNOACTIVATE)
        if not self.visible:
            access.tell(self.hwnd, EVENT_OBJECT_SHOW)
        self.visible = True
        user32.SetTimer(self.hwnd, TIP_TICK, 1000, None)
        self._sync_frames()

    def hide(self, at_once=True):
        """Hidden - at once, or (`at_once` False: the pointer left) fading out in brand's press time where motion is
        allowed. Hidden already, nothing."""
        if not self.visible or not self.hwnd:
            return
        self.visible = False
        user32 = popup._dll("user32")
        for timer in (TIP_TICK, TIP_FRAME):
            user32.KillTimer(self.hwnd, timer)
        self._frame_running = False
        access.tell(self.hwnd, EVENT_OBJECT_HIDE)
        if at_once or not self._moves() or self._alpha <= 0:
            return self._gone()
        self._fade = ("out", _now_ms(), self._alpha)
        user32.SetTimer(self.hwnd, TIP_FADE, GLIDE_FRAME_MS, None)

    def tick(self):
        """A second on: what the icon says now, drawn again where it changed (the countdown each second)."""
        if not self.visible:
            return
        self._still = self._ask_held()
        if self._lay():
            self._push()
            width, height = self._plan["size"]
            with popup._PerMonitorDpi():
                popup._dll("user32").SetWindowPos(self.hwnd, C.c_void_p(popup.HWND_TOPMOST), self._origin[0],
                                                  self._origin[1], width, height, popup.SWP_NOACTIVATE)
        self._sync_frames()

    # ------------------------------------------------------------------ what it shows
    _still = False

    def _read_look(self):
        """High Contrast, the theme, the design and what holds the light still, asked as the popup asks them: each time
        it is shown and whenever Windows says a setting changed, never per frame."""
        self.contrast = popup.high_contrast()
        self._theme = popup.effective_theme(popup.theme_setting(), popup.apps_use_light_theme())
        self._design = popup.design_setting()
        self._reduced = popup.reduced_motion() or self.contrast
        self._text_scale = popup.text_scale()
        self._still = self._ask_held()

    _text_scale = 1.0

    def _ask_held(self) -> bool:
        try:
            return bool(self.held()) if self.held is not None else False
        except Exception:
            return False

    def _holds(self) -> bool:
        return self._reduced or self._still

    def _moves(self) -> bool:
        """Whether it fades: the menus' rule - not with motion reduced, nor in High Contrast."""
        return bool(self.hwnd) and not (self.contrast or popup.reduced_motion())

    def _lay(self, force=False) -> bool:
        """Read what the icon says and lay the card out for it, placed by the icon. True when the plan is new."""
        parts, snapshot, strings = self.content()
        light = tip_light(snapshot)
        locale = popup.locale_of(strings)
        look = (self._theme, self._design, self.contrast, self._text_scale)
        key = (repr(parts), light, locale, look)
        if not force and key == self._shown and self._plan is not None:
            return False
        if light != self._light:
            self._light, self._light_since = light, time.monotonic()
        self.strings, self.locale = strings, locale
        self.text = tooltip_joined(parts)
        screen = self._screen
        scale = screen["dpi"] / 96.0
        work = screen["work"]
        plan = self._renderer.tip_layout(parts, light, scale, locale)
        fit = textsize.fitting(self._text_scale, plan["size"], (work[2] - work[0], work[3] - work[1]))
        if fit > 1.0:
            # Windows' text size draws the whole card that much larger, as it does the popup and the menu.
            plan = self._renderer.tip_layout(parts, light, scale * fit, locale)
        self._plan, self._shown = plan, key
        self._origin = tip_place(plan, work, screen["monitor"], screen["box"])
        return True

    def frame(self):
        """The light for this instant, its cycle starting with its state, as the popup's does."""
        since = (time.monotonic() - self._light_since) * 1000.0
        return popup.halo(self._light, since, since, reduced=self._holds(), design=self._design)

    def render(self):
        """The window's picture as it is now (the tests read it back)."""
        renderer = self._renderer
        renderer.theme, renderer.design, renderer.contrast = self._theme, self._design, self.contrast
        return renderer.draw_tip(self._plan, self.frame())

    def _push(self):
        self.render()
        self._blit()

    def _blit(self):
        width, height = self._plan["size"]
        blend = MENU_BLEND(0, 0, self._alpha, AC_SRC_ALPHA)
        where = W.POINT(self._origin[0], self._origin[1])
        with popup._PerMonitorDpi():
            ok = popup._dll("user32").UpdateLayeredWindow(self.hwnd, None, C.byref(where),
                                                          C.byref(MENU_SIZE(width, height)),
                                                          self._renderer.canvas.dc, C.byref(W.POINT(0, 0)), 0,
                                                          C.byref(blend), ULW_ALPHA)
        if not ok:
            raise OSError("UpdateLayeredWindow")

    # ------------------------------------------------------------------ its motion
    def _sync_frames(self):
        """The light's frame timer runs while it is shown and its light moves, and not while anything holds it."""
        user32 = popup._dll("user32")
        since = (time.monotonic() - self._light_since) * 1000.0
        wanted = self.visible and popup.animates(self._light, since, reduced=self._holds())
        if wanted and not self._frame_running:
            user32.SetTimer(self.hwnd, TIP_FRAME, popup.FRAME_MS, None)
            self._frame_running = True
        elif not wanted and self._frame_running:
            user32.KillTimer(self.hwnd, TIP_FRAME)
            self._frame_running = False

    def _light_step(self):
        if not self.visible or self._plan is None:
            return
        self._renderer.draw_tip_light(self._plan, self.frame())
        self._blit()

    def _appear(self):
        """It fades in over brand's transition, as the menus do, where motion is allowed; else it is simply there."""
        user32 = popup._dll("user32")
        user32.KillTimer(self.hwnd, TIP_FADE)
        if self._moves():
            self._alpha, self._fade = 0, ("in", None)
            user32.SetTimer(self.hwnd, TIP_FADE, GLIDE_FRAME_MS, None)
        else:
            self._alpha, self._fade = 255, None

    def _fade_step(self):
        if self._fade is None or not self.hwnd:
            return
        way, started = self._fade[0], self._fade[1]
        if started is None:                      # the clock starts at the first frame, the picture made and up
            started = _now_ms()
            self._fade = (way, started) + tuple(self._fade[2:])
        if way == "in":
            self._alpha, _, done = opening(_now_ms() - started, 0)
        else:
            self._alpha, done = closing(_now_ms() - started, self._fade[2])
        if done:
            popup._dll("user32").KillTimer(self.hwnd, TIP_FADE)
            self._fade = None
            if way == "out":
                return self._gone()
        self._blit()

    def _gone(self):
        user32 = popup._dll("user32")
        user32.KillTimer(self.hwnd, TIP_FADE)
        self._fade = None
        user32.ShowWindow(self.hwnd, popup.SW_HIDE)
        self._alpha = 255

    # ------------------------------------------------------------------ messages
    def _wndproc(self, hwnd, message, wparam, lparam):
        try:
            if message == popup.WM_TIMER:
                if wparam == TIP_TICK:
                    self.tick()
                elif wparam == TIP_FRAME:
                    self._light_step()
                elif wparam == TIP_FADE:
                    self._fade_step()
                return 0
            if message == access.WM_GETOBJECT:
                answered = access.answer(self, wparam, lparam, TipAccessible)
                if answered is not None:
                    return answered
            elif message == WM_MOUSEACTIVATE:
                return MA_NOACTIVATE
            elif message == WM_NCHITTEST:
                return HTTRANSPARENT
            elif message in (popup.WM_SETTINGCHANGE, WM_SYSCOLORCHANGE, WM_THEMECHANGED):
                if self.visible:
                    self._read_look()
                    self._lay(force=True)
                    self._push()
                    self._sync_frames()
            elif message in (WM_DISPLAYCHANGE, WM_DPICHANGED):
                self.hide()
        except Exception as exc:                 # the card must never take the watcher down
            self.log("tray tip card message failed (%s)" % type(exc).__name__)
            try:
                self.hide()
            except Exception:
                pass
            return 0
        return popup._dll("user32").DefWindowProcW(hwnd, message, wparam, lparam)


def _now_ms():
    return time.monotonic() * 1000.0
