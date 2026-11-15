"""The popup on screen as its card (v0.6.24): the window that is the card, the shadow below it, and its still.

Until v0.6.24 the popup was a grey window - DWM's rounded corner and hairline round a canvas - holding one big card with
everything in it. The owner, 2026-11-15, looking at it: the grey part outside the card should go. So the popup IS the card:

- its window is one per-pixel-alpha layered window (UpdateLayeredWindowIndirect) exactly the card's size, its picture the
  renderer's canvas drawn with the card alone (`Renderer.lone`: transparent round it, no lift of its own), the card's
  rectangle of it handed over by `pptSrc`. Its corners are the renderer's own fill through the shared GDI+ path
  (gdiplus._Painter._path), so whatever shape that path draws is the window's shape; a pixel with alpha 0 lets the
  mouse through ("areas of the window that are color-keyed or whose alpha value is zero will let the mouse messages
  through" - Microsoft Learn, Window Features, Layered Windows);
- its shadow lies on the desktop in a second layered window below it, as the notification card's does (ui/card/card.py):
  WS_EX_TRANSPARENT, so "the shape of the layered window will be ignored and the mouse events will be passed to other
  windows underneath" (the same page), and the card window is owned by it - "an owned window is always above its owner
  in the z-order" - so the two never cross. The shadows are the card recipe's outer ones as they may be drawn over a
  wallpaper (`float_shadows`, the notification card's rule, notice_card.float_shadows), stamped from the shared shadow
  helpers (elevation.lift_coverage, gdiplus._ShadowImage, elevation.shadow_step); a design without depth and High
  Contrast float none, and their card stands on the desktop as its fill and its hairline;
- a frame of the light uploads only the rows it drew: `prcDirty` - "If it is non-NULL, only the area in this rectangle
  is updated from the source DC" (Microsoft Learn, UPDATELAYEREDWINDOWINFO) - and a move or a fade of the opening
  uploads none (an empty `prcDirty`), since "For maximum efficiency in animating windows, call UpdateLayeredWindow to
  change the position and the size of a layered window" (Window Features). SetLayeredWindowAttributes is never called on
  these windows: "after SetLayeredWindowAttributes has been called, subsequent UpdateLayeredWindow calls will fail until
  the layering style bit is cleared and set again" (the same page).

`card_still` draws the same card and shadow over nothing, offscreen, for the pictures and the tests.
"""
from __future__ import annotations

from ctypes import wintypes as W
import ctypes as C
import math

from ... import brand
from .elevation import lift_coverage, shadow_step
from .gdiplus import PIXEL_FORMAT_32BPP_PARGB, _Canvas, _Painter, _ShadowImage, _gdiplus_made
from .theme import appearance
from .win32 import (DWMWA_USE_IMMERSIVE_DARK_MODE,
                    DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1,
                    DWMWA_WINDOW_CORNER_PREFERENCE,
                    DWMWCP_ROUND,
                    GWL_EXSTYLE,
                    HWND_TOPMOST,
                    MENU_BLEND,
                    MENU_SIZE,
                    SWP_NOACTIVATE,
                    SW_HIDE,
                    SW_SHOWNOACTIVATE,
                    UNIT_PIXEL,
                    WM_APP,
                    WS_EX_LAYERED,
                    WS_EX_TOOLWINDOW,
                    WS_EX_TOPMOST,
                    WS_POPUP,
                    _PerMonitorDpi,
                    _dll,
                    _signature)


ULW_ALPHA, AC_SRC_ALPHA, SWP_NOMOVE_NOSIZE = 0x2, 0x1, 0x0002 | 0x0001
WS_EX_NOACTIVATE, WS_EX_TRANSPARENT = 0x08000000, 0x00000020
WM_POPUP_PAINT = WM_APP + 4              # the card's picture is owed (PopupCard._redraw)


# --------------------------------------------------------------------- the shadow's recipe
# The notification card's rule (notice_card.float_shadows and shadow_margin), held equal to it by
# tests/test_popup_card_window.py: the popup cannot call it there - the card's module imports the popup - and the two
# cards are one product, so one rule draws both.
class FloatShadow(tuple):
    """(dx, dy, blur, colour, alpha): one shadow under the card, equal to the notification card's of the same five."""

    __slots__ = ()

    def __new__(cls, dx, dy, blur, colour, alpha):
        return tuple.__new__(cls, (dx, dy, blur, colour, alpha))

    dx, dy, blur = property(lambda self: self[0]), property(lambda self: self[1]), property(lambda self: self[2])
    colour, alpha = property(lambda self: self[3]), property(lambda self: self[4])


FLOAT_SHADOW_INK, FLOAT_SHADOW_THEME, DARK_ENOUGH = "shadow_dark", "dark", 0.05
_FLOATS = {}                             # (theme, design) -> float_shadows: asked on every frame, the same each time


def float_shadows(theme, design="soft") -> tuple:
    """The card recipe's outer shadows as they may be drawn over a wallpaper: one in a light colour redrawn in
    FLOAT_SHADOW_INK at the alpha that darkens a white ground as much, a highlight (lighter than the canvas it was made
    for) dropped, inset shadows left to the card; none for a design without depth."""
    if (theme, design) in _FLOATS:
        return _FLOATS[(theme, design)]
    tokens = brand.palette(theme, design)
    ink = brand.palette(FLOAT_SHADOW_THEME)[FLOAT_SHADOW_INK]
    ground = brand.luminance(tokens["canvas"])
    found = []
    for shadow in brand.shadows("card", theme, design):
        if shadow.inset:
            continue
        colour = tokens[shadow.token]
        if brand.luminance(colour) >= ground:
            continue
        if brand.luminance(colour) <= DARK_ENOUGH:
            found.append(FloatShadow(shadow.dx, shadow.dy, shadow.blur, colour, shadow.alpha))
            continue
        darkening = shadow.alpha * (1.0 - brand.luminance(colour)) / (1.0 - brand.luminance(ink))
        found.append(FloatShadow(shadow.dx, shadow.dy, shadow.blur, ink, round(darkening, 4)))
    if len(_FLOATS) < 32:                # two themes by three designs; nothing grows without end
        _FLOATS[(theme, design)] = tuple(found)
    return tuple(found)


def float_reach(shadows, scale) -> int:
    """How far the shadows reach past the card, in device pixels (three sigmas), and 0 for none."""
    if not shadows:
        return 0
    reach = max(max(abs(shadow.dx), abs(shadow.dy)) + 1.5 * shadow.blur for shadow in shadows)
    return int(math.ceil(reach * scale)) + 2


def card_shadows(theme, design, contrast) -> tuple:
    """What floats under the card: nothing in High Contrast (system colours, hairlines, no shadow), else float_shadows."""
    return () if contrast else float_shadows(theme, design)


def card_radius(renderer, plan) -> int:
    """The card's corner in device px, as the renderer rounds it in its design (High Contrast: Soft's)."""
    card = next(item for item in plan["items"] if item["kind"] == "card")
    return renderer._corner(card, plan["scale"])


def stamp_shadows(canvas, shadows, size, radius, scale, origin, images):
    """`shadows` under a card of `size` whose corner is at `origin` in `canvas` (PARGB, premultiplied), from the shared
    shadow images - made once per shadow and kept in `images` - with their middles left out: the card covers them."""
    width, height = size
    with _Painter(canvas, PIXEL_FORMAT_32BPP_PARGB) as paint:
        for shadow in reversed(shadows):
            key = (shadow, width, height, radius, scale)
            image = images.get(key)
            if image is None:
                image = images[key] = _ShadowImage(lift_coverage(width, height, radius, shadow.blur * scale),
                                                   brand.rgb(shadow.colour), shadow.alpha)
            extent = image.extent
            image.stamp(paint, origin[0] - extent + shadow_step(shadow.dx * scale),
                        origin[1] - extent + shadow_step(shadow.dy * scale), width + 2 * extent, height + 2 * extent,
                        middle=False)


def _over(canvas, source, card, at):
    """The card's rectangle of `source` (premultiplied) laid over `canvas` with its corner at `at`, by GDI+ (exact
    source-over between two premultiplied surfaces, one pixel to one pixel)."""
    left, top, right, bottom = card
    width, height = right - left, bottom - top
    gp, bitmap = _dll("gdiplus"), C.c_void_p()
    _dll("gdi32").GdiFlush()
    status = gp.GdipCreateBitmapFromScan0(width, height, source.width * 4, PIXEL_FORMAT_32BPP_PARGB,
                                          C.c_void_p(source.bits.value + (top * source.width + left) * 4),
                                          C.byref(bitmap))
    if status != 0:
        raise OSError("GdipCreateBitmapFromScan0 failed (%d)" % status)
    _gdiplus_made(1)
    try:
        with _Painter(canvas, PIXEL_FORMAT_32BPP_PARGB) as paint:
            gp.GdipDrawImageRectRectI(paint.graphics, bitmap, at[0], at[1], width, height, 0, 0, width, height,
                                      UNIT_PIXEL, None, None, None)
    finally:
        gp.GdipDisposeImage(bitmap)
        _gdiplus_made(-1)


def still_pad(scale) -> int:
    """How much transparent room a still keeps round the card: the deepest theme's Soft shadow, so a light and a dark
    still, and one of a design that floats none, are the same size and stand side by side (as the card's stills do)."""
    return max(float_reach(float_shadows(theme), scale) for theme in brand.THEMES)


def card_still(renderer, plan, pad=None) -> tuple:
    """(width, height, premultiplied BGRA): the card the renderer last drew alone (`lone`) and its shadow, over nothing.

    Drawn as the screen has it - the shadow window's picture, then the card window's laid over it - with `pad` px of
    room round the card (`still_pad` unless said)."""
    scale, card = plan["scale"], plan["card"]
    pad = still_pad(scale) if pad is None else pad
    width, height = card[2] - card[0], card[3] - card[1]
    canvas, images = _Canvas(), {}
    try:
        canvas.ensure(width + 2 * pad, height + 2 * pad)
        _dll("gdi32").GdiFlush()
        C.memset(canvas.bits, 0, canvas.width * canvas.height * 4)
        shadows = card_shadows(renderer._theme(), renderer._design(), renderer.contrast)
        if shadows:
            stamp_shadows(canvas, shadows, (width, height), card_radius(renderer, plan), scale, (pad, pad), images)
        _over(canvas, renderer.canvas, card, (pad, pad))
        _dll("gdi32").GdiFlush()
        return canvas.width, canvas.height, canvas.pixels()
    finally:
        for image in images.values():
            image.close()
        canvas.close()


# ------------------------------------------------------------------------------ on screen
class UPDATELAYEREDWINDOWINFO(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("hdcDst", C.c_void_p), ("pptDst", C.POINTER(W.POINT)),
                ("psize", C.POINTER(MENU_SIZE)), ("hdcSrc", C.c_void_p), ("pptSrc", C.POINTER(W.POINT)),
                ("crKey", W.DWORD), ("pblend", C.POINTER(MENU_BLEND)), ("dwFlags", W.DWORD),
                ("prcDirty", C.POINTER(W.RECT))]


_LAYERS_DECLARED = []


def _declare_layers():
    if not _LAYERS_DECLARED:
        _signature(_dll("user32").UpdateLayeredWindowIndirect, W.BOOL, C.c_void_p, C.POINTER(UPDATELAYEREDWINDOWINFO))
        _LAYERS_DECLARED.append(True)


NOTHING = (0, 0, 0, 0)                 # a dirty rectangle that uploads no pixel: a move or a fade


def update(hwnd, *, at, alpha, dc, size, source=(0, 0), dirty=None) -> bool:
    """One UpdateLayeredWindowIndirect: the window at `at` (screen px) at `alpha` (0-255), its picture `size` px of `dc`
    from `source`; only the `dirty` rectangle of it (window px) is uploaded when one is given - none at all for NOTHING."""
    _declare_layers()
    point, blend = W.POINT(int(at[0]), int(at[1])), MENU_BLEND(0, 0, max(0, min(255, int(alpha))), AC_SRC_ALPHA)
    info = UPDATELAYEREDWINDOWINFO()
    info.cbSize = C.sizeof(UPDATELAYEREDWINDOWINFO)
    info.pptDst, info.pblend, info.dwFlags = C.pointer(point), C.pointer(blend), ULW_ALPHA
    info.hdcSrc = dc
    info.psize = C.pointer(MENU_SIZE(int(size[0]), int(size[1])))
    info.pptSrc = C.pointer(W.POINT(int(source[0]), int(source[1])))
    if dirty is not None:
        info.prcDirty = C.pointer(W.RECT(*(int(value) for value in dirty)))
    with _PerMonitorDpi():
        return bool(_dll("user32").UpdateLayeredWindowIndirect(hwnd, C.byref(info)))


class CardLayers:
    """The popup's two pictures on screen: its own window, which is the card, and the shadow window it is owned by.

    Owns the shadow window, its picture and its shadow images. The card window is the popup's; this only updates it."""

    def __init__(self, shadow_hwnd):
        self.shadow_hwnd = shadow_hwnd
        self.picture = _Canvas()
        self.images = {}
        self.shadows, self.margin = (), 0
        self._shadow_key = None
        self._shadow_owed = True         # the shadow window's picture is not yet on screen
        self._body = None                # (dc, size, source) last handed to the card window
        self.shown = False
        self._shadow_shown = False

    def shade(self, renderer, plan) -> bool:
        """The shadow picture for this plan's card, drawn again only when its size, scale or look changed."""
        shadows = card_shadows(renderer._theme(), renderer._design(), renderer.contrast)
        card, scale = plan["card"], plan["scale"]
        size, radius = (card[2] - card[0], card[3] - card[1]), card_radius(renderer, plan)
        key = (shadows, size, radius, scale)
        if key == self._shadow_key:
            return False
        if self._shadow_key is None or self._shadow_key[3] != scale or self._shadow_key[0] != shadows:
            self._drop_images()
        self.shadows, self.margin = shadows, float_reach(shadows, scale)
        if shadows:
            self.picture.ensure(size[0] + 2 * self.margin, size[1] + 2 * self.margin)
            _dll("gdi32").GdiFlush()
            C.memset(self.picture.bits, 0, self.picture.width * self.picture.height * 4)
            stamp_shadows(self.picture, shadows, size, radius, scale, (self.margin, self.margin), self.images)
        self._shadow_key, self._shadow_owed = key, True
        return True

    def push(self, hwnd, canvas, plan, at, alpha, rows=None) -> bool:
        """The card window at `at` (the card's corner on screen) at `alpha`, its picture the card's rectangle of `canvas`:
        whole, or only `rows` (canvas rows, first and after the last) when its size is what it was. Then the shadow."""
        card = plan["card"]
        size = (card[2] - card[0], card[3] - card[1])
        dirty = None
        if rows is not None and self._body == (canvas.dc, size, card[:2]):
            top, bottom = max(rows[0], card[1]) - card[1], min(rows[1], card[3]) - card[1]
            dirty = NOTHING if bottom <= top else (0, top, size[0], bottom)
        if not update(hwnd, at=at, alpha=alpha, dc=canvas.dc, size=size, source=card[:2], dirty=dirty):
            self._body = None
            return False
        self._body = (canvas.dc, size, card[:2])
        return self.stand_shadow(at, alpha)

    def stand(self, hwnd, at, alpha) -> bool:
        """Both windows moved to `at` at `alpha`, nothing uploaded: a frame of the opening."""
        if self._body is None:
            return True                  # nothing on screen yet; the first push puts it there
        dc, size, source = self._body
        if not update(hwnd, at=at, alpha=alpha, dc=dc, size=size, source=source, dirty=NOTHING):
            return False
        return self.stand_shadow(at, alpha)

    def stand_shadow(self, at, alpha) -> bool:
        if self.shown and bool(self.shadows) != self._shadow_shown:
            self._show_shadow()              # High Contrast or a design without depth came or went while it was open
        if not self.shadows:
            return True
        where = (at[0] - self.margin, at[1] - self.margin)
        owed, size = self._shadow_owed, (self.picture.width, self.picture.height)
        ok = update(self.shadow_hwnd, at=where, alpha=alpha, dc=self.picture.dc, size=size,
                    dirty=None if owed else NOTHING)
        self._shadow_owed = owed and not ok
        return ok

    def show(self):
        """The shadow window raised to the top of the topmost windows - the card window it owns goes above it - and shown."""
        with _PerMonitorDpi():
            _dll("user32").SetWindowPos(self.shadow_hwnd, C.c_void_p(HWND_TOPMOST), 0, 0, 0, 0,
                                        SWP_NOACTIVATE | SWP_NOMOVE_NOSIZE)
        self._show_shadow()
        self.shown = True

    def _show_shadow(self):
        """The shadow window shown while there is a shadow, hidden while there is none."""
        _dll("user32").ShowWindow(self.shadow_hwnd, SW_SHOWNOACTIVATE if self.shadows else SW_HIDE)
        self._shadow_shown = bool(self.shadows)

    def hide(self):
        _dll("user32").ShowWindow(self.shadow_hwnd, SW_HIDE)
        self.shown = self._shadow_shown = False

    def forget(self):
        """What is on screen is no longer known (the card window was hidden or remade): the next push is whole."""
        self._body = None

    def _drop_images(self):
        for image in self.images.values():
            image.close()
        self.images = {}

    def close(self):
        """The shadow window and everything drawn for it. Its owned card window goes with it, so the popup's goes first."""
        self._drop_images()
        hwnd, self.shadow_hwnd = self.shadow_hwnd, None
        if hwnd:
            _dll("user32").DestroyWindow(hwnd)
        if self.picture is not None:
            self.picture.close()
            self.picture = None


# ------------------------------------------------------------------------------ the window's side
class PopupCard:
    """A mixin of the window (window.Popup): how its picture reaches the screen - as the card (v0.6.24), or as the plain
    window it was before and falls back to - and where a point of its window is on the card's plan."""

    @staticmethod
    def _can_be_card() -> bool:
        """Whether this Windows has UpdateLayeredWindowIndirect (Vista on), which the card is put on screen with."""
        return getattr(_dll("user32"), "UpdateLayeredWindowIndirect", None) is not None

    def _make_layers(self, instance):
        """The shadow window (layers.CardLayers), which the card's window is then made owned by; None, and the popup is a
        plain window as before v0.6.24, where it cannot be made."""
        user32 = _dll("user32")
        style = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST
        shadow = user32.CreateWindowExW(style, self._class, "", WS_POPUP, 0, 0, 1, 1, None, None, instance, None)
        if not shadow:
            self.log("tray popup card window unavailable (CreateWindowExW)")
            return None
        try:
            self._layers = CardLayers(shadow)
        except Exception as exc:
            self.log("tray popup card window unavailable (%s)" % type(exc).__name__)
            user32.DestroyWindow(shadow)
            return None
        return shadow

    def _redraw(self):
        """The picture is owed: a plain window's invalidated (WM_PAINT), the card's pushed once the messages already
        queued are handled (WM_POPUP_PAINT), so several changes in one turn cost one frame, as WM_PAINT gathers them."""
        if not self.hwnd:
            return
        if not self._card:
            _dll("user32").InvalidateRect(self.hwnd, None, False)
        elif not self._owed:
            self._owed = True
            _dll("user32").PostMessageW(self.hwnd, WM_POPUP_PAINT, 0, 0)

    def _push(self):
        """The card's picture drawn and handed to Windows now - only the rows a frame of the light drew, when that is all
        it drew - with its shadow, where the opening has it and as opaque. Windows refusing it, the popup is a plain window
        from then on (`_plain`)."""
        self._owed = False
        if not self._card or not self.hwnd or self._renderer is None or not self.visible or self._home is None:
            return
        canvas = self.render()
        layers = self._layers
        layers.shade(self._renderer, self._plan)
        if layers.push(self.hwnd, canvas, self._plan, (self._home[0], self._home[1] + self._below), self._alpha,
                       self._rows):
            self._painted_plan = self._plan
            return
        self._plain("UpdateLayeredWindowIndirect")

    def _plain(self, why):
        """What Windows would not put on screen as the card is shown as the plain window it was before v0.6.24: no longer
        layered, its grey ground drawn round the card, DWM's corner - for as long as this popup lives."""
        self.log("tray popup card window unavailable (%s)" % why)
        user32 = _dll("user32")
        self._end_opening()
        self._card, self._alpha, self._owed = False, 255, False
        if self._layers is not None:
            self._layers.hide()                  # kept: its window owns the popup's, and goes with it
        if self._renderer is not None:
            self._renderer.lone = False
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE) & ~WS_EX_LAYERED)
        self._round_corners()
        self._static_dirty = True
        if self._plan is not None and self._screen is not None:
            card, origin = self._plan["card"], self._origin       # the card's corner, as the card was placed
            self._move(self._plan, None if origin is None else (origin[0] - card[0], origin[1] - card[1]))
            self._frame_theme()
        user32.InvalidateRect(self.hwnd, None, False)

    # ------------------------------------------------------------ the plain window (before v0.6.24)
    def _round_corners(self):
        try:
            value = C.c_int(DWMWCP_ROUND)
            dwm = _dll("dwmapi")
            _signature(dwm.DwmSetWindowAttribute, C.c_long, C.c_void_p, W.DWORD, C.c_void_p, W.DWORD)
            self._rounded = dwm.DwmSetWindowAttribute(self.hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                                      C.byref(value), C.sizeof(value)) == 0
        except Exception:
            self._rounded = False

    def _shape(self, width, height):
        if self._rounded or self._card:              # the card's shape is its picture's alpha, never a region
            return
        radius = int(round(8 * self.dpi / 96.0)) * 2
        region = _dll("gdi32").CreateRoundRectRgn(0, 0, width + 1, height + 1, radius, radius)
        if region and not _dll("user32").SetWindowRgn(self.hwnd, region, True):
            _dll("gdi32").DeleteObject(region)            # only a region the system took is its own

    def _frame_theme(self):
        """Tell DWM whether the window is dark, so the hairline Windows 11 draws round it matches."""
        dark = appearance(self._theme, contrast=self._contrast) == "dark"
        if not self.hwnd or dark == self._framed_dark or self._card:        # the card has no frame of Windows'
            return
        self._framed_dark = dark
        try:
            value = C.c_int(1 if dark else 0)
            dwm = _dll("dwmapi")
            _signature(dwm.DwmSetWindowAttribute, C.c_long, C.c_void_p, W.DWORD, C.c_void_p, W.DWORD)
            for attribute in (DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1):
                if dwm.DwmSetWindowAttribute(self.hwnd, attribute, C.byref(value), C.sizeof(value)) == 0:
                    break
        except Exception:
            pass                                   # a frame that stays light is not worth a failure

    def _client_offset(self):
        """Where the card's window's (0, 0) is on the plan: the card's corner, for the window is the card (v0.6.24); the
        plain window's is the plan's own."""
        plan = self._painted_plan or self._plan
        return (int(plan["card"][0]), int(plan["card"][1])) if self._card and plan else (0, 0)

    def _client_point(self, lparam):
        """A mouse message's point, in the plan's pixels."""
        dx, dy = self._client_offset()
        return C.c_short(lparam & 0xFFFF).value + dx, C.c_short((lparam >> 16) & 0xFFFF).value + dy
