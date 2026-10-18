"""One frame of the README's motion picture, laid together: the window in its frame, the taskbar strip with the tray
icon, the card, and a pointer drawn over them.

Everything the product draws is the product's: the window's client area from its render mode (motion_window), the
card from its own paint (motion_card), the tray icon from `ui.tray.IconFrames` at `icon_frame`. What Windows draws
around a window - its caption, its frame, the corners it rounds - is taken from one captured still per theme
(`assets/screenshot-dashboard.png`): its caption rows and its transparency, laid round every frame's client area; the
caption reads "Codex Auto Resume" in every language, so one still serves both pictures. A captured still carries no
shadow (PrintWindow draws the window, not what the compositor puts round it), so the window's shadow is drawn here:
a soft one under the window's rectangle, worked out once.

The pointer is never the real one, nor Windows' cursor bitmap: an arrow of our own, white with a dark edge, its
coverage sampled sixteen times a pixel; a click is a ring of the brand's accent that spreads and fades on brand.ease
(TOOLING 2.3). Both are pure functions of a frame, so the same frame is the same pixels on every machine.
"""
from __future__ import annotations

import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import motion_plan  # noqa: E402

# The arrow, in pixels at 100 %, its tip at (0, 0): Windows' arrow's outline, drawn by us.
ARROW = ((0.0, 0.0), (0.0, 17.0), (4.2, 13.0), (7.2, 19.6), (10.0, 18.4), (7.1, 12.0), (12.2, 12.0))
ARROW_EDGE = (0.9, 0.6)              # the dark edge's width inside and outside the outline, at 100 %
ARROW_FILL, ARROW_PRESSED, ARROW_INK = (255, 255, 255), (232, 234, 238), (26, 26, 30)
SAMPLES = 4                          # a pixel's coverage is sampled SAMPLES x SAMPLES times
# The click's ring (TOOLING 2.3): out to RIPPLE_RADIUS px on the canvas, RIPPLE_WIDTH wide, from RIPPLE_ALPHA to none.
RIPPLE_RADIUS, RIPPLE_WIDTH, RIPPLE_ALPHA = 18.0, 3.0, 0.35
# The window's shadow, at 100 %: how far it falls, how soft it is, how dark at its darkest.
SHADOW_DROP, SHADOW_SOFTNESS, SHADOW_ALPHA = 6.0, 10.0, 0.20


# ---------------------------------------------------------------------------------------------------- the pointer
def _inside(x: float, y: float, polygon) -> bool:
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _distance(x: float, y: float, polygon) -> float:
    best = float("inf")
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = x2 - x1, y2 - y1
        t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)))
    return best


_SPRITES = {}


def arrow_sprite(scale: float, pressed: bool = False) -> tuple:
    """(width, height, [(red, green, blue, coverage 0-255)] row by row) of the arrow at `scale`, its tip at (1, 1)."""
    key = (round(scale, 4), bool(pressed))
    if key in _SPRITES:
        return _SPRITES[key]
    polygon = [(1.0 + x * scale, 1.0 + y * scale) for x, y in ARROW]
    inner, outer = ARROW_EDGE[0] * scale, ARROW_EDGE[1] * scale
    width = int(math.ceil(max(x for x, _ in polygon) + outer)) + 2
    height = int(math.ceil(max(y for _, y in polygon) + outer)) + 2
    fill = ARROW_PRESSED if pressed else ARROW_FILL
    pixels = []
    for py in range(height):
        for px in range(width):
            light = dark = 0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x, y = px + (sx + 0.5) / SAMPLES, py + (sy + 0.5) / SAMPLES
                    inside = _inside(x, y, polygon)
                    edge = _distance(x, y, polygon)
                    if inside and edge >= inner:
                        light += 1
                    elif (inside and edge < inner) or (not inside and edge < outer):
                        dark += 1
            covered = light + dark
            if not covered:
                pixels.append((0, 0, 0, 0))
                continue
            colour = tuple((fill[c] * light + ARROW_INK[c] * dark) // covered for c in range(3))
            pixels.append(colour + ((covered * 255 + SAMPLES * SAMPLES // 2) // (SAMPLES * SAMPLES),))
    _SPRITES[key] = (width, height, pixels)
    return _SPRITES[key]


def _blend(canvas: bytearray, width: int, height: int, x: int, y: int, colour, coverage: int) -> None:
    """`colour` at `coverage` (0-255) over one pixel of an RGB canvas - or of an RGBA one with straight alpha, where
    what is under may itself be partly or wholly clear, as the ground of a window pictured on its own is."""
    if not coverage or x < 0 or y < 0 or x >= width or y >= height:
        return
    keep = 255 - coverage
    if len(canvas) == width * height * 4:
        at = (y * width + x) * 4
        under = canvas[at + 3] * keep
        alpha = coverage * 255 + under                  # in 255ths of 255
        if not alpha:
            return
        for c in range(3):
            canvas[at + c] = (colour[c] * coverage * 255 + canvas[at + c] * under + alpha // 2) // alpha
        canvas[at + 3] = (alpha + 127) // 255
        return
    at = (y * width + x) * 3
    for c in range(3):
        canvas[at + c] = (colour[c] * coverage + canvas[at + c] * keep + 127) // 255


def draw_pointer(canvas: bytearray, width: int, height: int, x: float, y: float, *, scale: float = 1.5,
                 pressed: bool = False, ripple=None, accent=(0, 120, 212)) -> None:
    """The pointer with its tip at (x, y) on the RGB canvas, and under it, when `ripple` is (spread 0-1, opacity 0-1),
    a click's ring of `accent` round the tip."""
    tip_x, tip_y = int(round(x)), int(round(y))
    if ripple is not None:
        spread, opacity = ripple
        radius, half = RIPPLE_RADIUS * spread, RIPPLE_WIDTH / 2.0
        reach = int(math.ceil(radius + half)) + 1
        level = RIPPLE_ALPHA * opacity
        for py in range(tip_y - reach, tip_y + reach + 1):
            for px in range(tip_x - reach, tip_x + reach + 1):
                hits = 0
                for sy in range(SAMPLES):
                    for sx in range(SAMPLES):
                        d = math.hypot(px + (sx + 0.5) / SAMPLES - x, py + (sy + 0.5) / SAMPLES - y)
                        hits += abs(d - radius) <= half
                if hits:
                    _blend(canvas, width, height, px, py, accent,
                           int(round(255 * level * hits / float(SAMPLES * SAMPLES))))
    sprite_w, sprite_h, pixels = arrow_sprite(scale, pressed)
    for row in range(sprite_h):
        for column in range(sprite_w):
            red, green, blue, coverage = pixels[row * sprite_w + column]
            _blend(canvas, width, height, tip_x - 1 + column, tip_y - 1 + row, (red, green, blue), coverage)


# ---------------------------------------------------------------------------------------------------- the window
def _phi(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


class WindowChrome:
    """The window's caption, frame and corners from one captured still, and a shadow of its rectangle, on a canvas.

    `still` is (width, height, RGB, alpha or None) of a window picture as the generator writes it (the caption
    kept, the frame cut away, the corners Windows rounds left clear); `client` the client area's size the render
    mode drew. The window's top-left goes at `at` on a canvas `size` in `ground`'s colour - or, with `ground` None,
    on a clear canvas: RGBA, every pixel outside the window and its shadow wholly transparent, the shadow and the
    corners Windows rounds laid with their alpha, so the picture sits on any page."""

    def __init__(self, still: tuple, client: tuple, *, size: tuple, at: tuple, ground, scale: float = 1.5):
        width, height, rgb, alpha = still
        client_w, client_h = client
        if width != client_w or height < client_h:
            raise ValueError("the still is %dx%d and the client area %dx%d: not the same window"
                             % (width, height, client_w, client_h))
        self.size, self.at, self.width, self.height = tuple(size), tuple(at), width, height
        self.caption = height - client_h
        self.alpha = alpha
        canvas_w, canvas_h = size
        self.bpp = 3 if ground is not None else 4
        base = bytearray(bytes(ground) * (canvas_w * canvas_h)) if ground is not None else bytearray(
            canvas_w * canvas_h * 4)
        self._shadow(base, scale)
        left, top = at
        for y in range(height):
            for x in range(width):
                cover = 255 if alpha is None else alpha[y * width + x]
                if y >= self.caption and cover == 255:
                    continue                                 # the client area: every frame's own
                cx, cy = left + x, top + y
                if not cover or cx >= canvas_w or cy >= canvas_h:
                    continue
                source = rgb[(y * width + x) * 3:(y * width + x) * 3 + 3] if y < self.caption else None
                if source is None:
                    continue                                 # a rounded client corner: laid per frame
                _blend(base, canvas_w, canvas_h, cx, cy, source, cover)
        self.base = bytes(base)
        # The client pixels the rounded corners only partly cover, laid over the shadow and ground per frame.
        self.corners = [(x, y - self.caption, alpha[y * width + x]) for y in range(self.caption, height)
                        for x in range(width) if alpha is not None and alpha[y * width + x] < 255]

    def _shadow(self, base: bytearray, scale: float) -> None:
        canvas_w, canvas_h = self.size
        left, top = self.at
        right, bottom = left + self.width, top + self.height + SHADOW_DROP * scale
        top += SHADOW_DROP * scale
        soft = SHADOW_SOFTNESS * scale
        reach = int(3 * soft) + 1
        xs = range(max(0, int(left) - reach), min(canvas_w, int(right) + reach))
        ys = range(max(0, int(top) - reach), min(canvas_h, int(bottom) + reach))
        across = {x: _phi((x + 0.5 - left) / soft) - _phi((x + 0.5 - right) / soft) for x in xs}
        down = {y: _phi((y + 0.5 - top) / soft) - _phi((y + 0.5 - bottom) / soft) for y in ys}
        for y in ys:
            row = down[y]
            for x in xs:
                level = int(round(255 * SHADOW_ALPHA * row * across[x]))
                _blend(base, canvas_w, canvas_h, x, y, (0, 0, 0), level)

    def empty_border(self) -> tuple:
        """(left, top, right, bottom): how many columns and rows at each edge of a clear canvas hold nothing at all -
        no window, no shadow, every pixel wholly transparent. A picture drawn as it should be has none of them."""
        if self.bpp != 4:
            return 0, 0, 0, 0
        width, height = self.size
        alpha = self.base[3::4]
        rows = [any(alpha[y * width:(y + 1) * width]) for y in range(height)]
        if not any(rows):
            return width, height, width, height
        columns = [x for y in range(height) if rows[y] for x in range(width) if alpha[y * width + x]]
        return (min(columns), rows.index(True), width - 1 - max(columns), rows[::-1].index(True))

    def client_origin(self) -> tuple:
        """Where the client area's top-left is on the canvas."""
        return self.at[0], self.at[1] + self.caption

    def frame(self, client: bytes) -> bytearray:
        """The canvas with the window, its client area `client` (RGB), in its frame."""
        canvas = bytearray(self.base)
        canvas_w, canvas_h = self.size
        left, top = self.client_origin()
        width, height = self.width, self.height - self.caption
        visible = min(width, canvas_w - left)
        bpp = self.bpp
        opaque = bytes((255,)) * visible
        for y in range(height):
            if top + y >= canvas_h:
                break
            at = ((top + y) * canvas_w + left) * bpp
            source = client[y * width * 3:(y * width + visible) * 3]
            if bpp == 3:
                canvas[at:at + visible * 3] = source
                continue
            line = bytearray(visible * 4)
            line[0::4], line[1::4], line[2::4], line[3::4] = source[0::3], source[1::3], source[2::3], opaque
            canvas[at:at + visible * 4] = line
        for x, y, cover in self.corners:
            at = ((top + y) * canvas_w + left + x) * bpp
            canvas[at:at + bpp] = self.base[at:at + bpp]
            _blend(canvas, canvas_w, canvas_h, left + x, top + y, client[(y * width + x) * 3:(y * width + x) * 3 + 3],
                   cover)
        return canvas


# ---------------------------------------------------------------------------------------------------- the taskbar
def draw_strip(canvas: bytearray, width: int, height: int, top: int, tall: int, colour: tuple) -> None:
    """The taskbar's strip: one colour, the whole width - nothing that pretends to be Windows' taskbar."""
    row = bytes(colour) * width
    for y in range(top, min(height, top + tall)):
        canvas[y * width * 3:(y + 1) * width * 3] = row


def draw_icon(canvas: bytearray, width: int, height: int, pixels: bytes, size: int, left: int, top: int) -> None:
    """The tray icon's frame - top-down BGRA with straight alpha, as icon bitmaps are - over the canvas."""
    for y in range(size):
        for x in range(size):
            blue, green, red, alpha = pixels[(y * size + x) * 4:(y * size + x) * 4 + 4]
            _blend(canvas, width, height, left + x, top + y, (red, green, blue), alpha)


# ---------------------------------------------------------------------------------------------------- where things are
def locate(ref, bounds: dict, origin: tuple, card=None) -> tuple:
    """(x, y) on the canvas of a pointer target: the centre of a control the window named in `bounds` (client
    coordinates, from `origin`), of a card button (`card.<verb>`, motion_card.CardFrames), a point `{"at": ...}`, or
    one `{"by": ..., "from": ...}` away from another."""
    if isinstance(ref, tuple):
        ref = motion_plan.thawed(ref)
    if isinstance(ref, dict):
        if "at" in ref:
            return float(ref["at"][0]), float(ref["at"][1])
        x, y = locate(ref["from"], bounds, origin, card)
        return x + ref["by"][0], y + ref["by"][1]
    if ref.startswith("card."):
        if card is None:
            raise KeyError("no card to point at for %s" % ref)
        left, top, right, bottom = card.button(ref[len("card."):])
        return (left + right) / 2.0, (top + bottom) / 2.0
    if ref not in bounds:
        raise KeyError("the window did not say where %s is" % ref)
    x, y, wide, tall = bounds[ref]
    return origin[0] + x + wide / 2.0, origin[1] + y + tall / 2.0


def pointer_at(frame, bounds: dict, origin: tuple, card=None) -> tuple:
    """Where the frame's pointer tip stands: at its target, or `fraction` of the way between two (already eased)."""
    if frame.pointer[0] == "at":
        return locate(frame.pointer[1], bounds, origin, card)
    _kind, start, end, fraction = frame.pointer
    x1, y1 = locate(start, bounds, origin, card)
    x2, y2 = locate(end, bounds, origin, card)
    return x1 + (x2 - x1) * fraction, y1 + (y2 - y1) * fraction
