"""The popup's status light, drawn (v0.6.24, out of renderer.py).

The dot, its glow, the checking arc and the seventh press's sweep. The renderer is made of this: `draw_halo` puts one frame of
the light over the whole frame it kept the band of rows behind (`_keep_halo_band`), so a frame of the light is one memory copy
and two antialiased circles. It uses the renderer's colours (`_rgb`, `_argb`, `_theme`) and its `contrast` - it is a part of
the renderer's class and not a class of its own, so no caller can tell it from one.
"""
from __future__ import annotations

import ctypes as C
import math
from ... import brand
from .gdiplus import _Painter
from .theme import system_rgb
from .win32 import _dll, _pack


# What each state is drawn with. Fill tokens for the dot, text tokens for its word: `active`
# is fill-only and never carries text, which is why the two tables are separate. The dot is
# brand's status light, as in the window and the panel: every state in which the watcher runs
# with recovery on is the `active` cyan it had before v0.6.3, a pause keeps its grey, and a
# problem is amber. The word beside it, and its glow, tell the running states apart. Keyed by
# light, not by word: brand's own table, so a watcher not known to be running is `idle` grey
# (v0.6.10), which no word is.
DOT_FILL = dict(brand.STATUS_FILL)


class StatusLight:
    """The light's drawing, for the Renderer to be made of."""

    # How far on the seventh press's sweep is, or None: the window says, and it is drawn with the light.
    sweep_ms = None

    def _sweep(self, paint, item, milliseconds):
        """The arc round the light with its head leading, then two rings, in the room the plan keeps for it (`sweep_reach`)."""
        numbers = brand.SWEEP
        cx, cy = item["cx"], item["cy"]
        unit = item["sweep_reach"] / numbers["reach"]
        colour = brand.rgb(brand.status_colour(item["state"], self._theme()))
        covered, opacity, rings = brand.sweep_at(milliseconds, brand.ease)
        for (spread, ring), width in zip(rings, (1.6, 1.2)):
            if ring > 0:
                radius = unit * (numbers["ring_from"] + (numbers["reach"] - numbers["ring_from"]) * spread)
                paint.stroke_round((cx - radius, cy - radius, cx + radius, cy + radius), radius, _pack(colour, ring), max(1.0, unit * width))
        if opacity <= 0:
            return
        radius = unit * numbers["arc_radius"]
        if covered > 0.001:
            paint.arc(cx, cy, radius, -90.0, 360.0 * covered, _pack(colour, opacity), max(1.0, unit * 2.4))
        angle = math.radians(360.0 * covered - 90.0)
        paint.fill_circle(cx + radius * math.cos(angle), cy + radius * math.sin(angle), max(1.5, unit * numbers["head_radius"]),
                          _pack(brand.rgb(brand.ICON_ACCENT), opacity))

    def draw_halo(self, plan, frame, *, restore=True):
        """Only the halo, for an animation frame; everything else in the canvas is kept.

        The band of rows behind the halo was saved when the whole frame was drawn, so a
        frame is one memory copy and two antialiased circles rather than the whole window.
        """
        item = next((entry for entry in plan["items"] if entry["kind"] == "halo"), None)
        if item is None:
            return self.canvas
        if restore:
            if self._halo_plan is not plan or self._halo_band is None:
                raise ValueError("the whole frame has to be drawn before its halo")
            offset, band = self._halo_band
            C.memmove(self.canvas.bits.value + offset, band, len(band))
        with _Painter(self.canvas) as paint:
            self._halo(paint, item, plan["scale"], frame)
            if self.sweep_ms is not None:
                self._sweep(paint, item, self.sweep_ms)
        return self.canvas

    @property
    def halo_plan(self):
        return self._halo_plan

    @property
    def halo_rows(self):
        """(first row, row after the last) of the band draw_halo draws into, or None: all a frame of the
        light changes, which the notification card copies out and nothing else (v0.6.10)."""
        if self._halo_band is None:
            return None
        offset, band = self._halo_band
        row = self.canvas.width * 4
        return offset // row, (offset + len(band)) // row

    def _keep_halo_band(self, plan):
        canvas = self.canvas
        item = next((entry for entry in plan["items"] if entry["kind"] == "halo"), None)
        self._halo_plan = plan
        if item is None:
            self._halo_band = None
            return
        _dll("gdi32").GdiFlush()
        # The item's radius is the largest glow any frame draws; leave room for its soft edge.
        reach = max(item["radius"], item.get("sweep_reach", 0.0)) + 2 * plan["scale"] + 2
        top = max(0, int(item["cy"] - reach))
        bottom = min(canvas.height, int(math.ceil(item["cy"] + reach)))
        offset = top * canvas.width * 4
        self._halo_band = (offset, C.string_at(canvas.bits.value + offset, (bottom - top) * canvas.width * 4))

    def _halo(self, paint, item, scale, frame):
        """The state dot, flat and the size it always was, with its glow and the checking arc."""
        state, cx, cy = item["state"], item["cx"], item["cy"]
        dot, light = brand.STATUS_DOT["popup"], brand.GLOW
        arc = frame.get("arc") if frame is not None else None
        arc_radius, arc_width = (dot + light["arc_gap"]) * scale, light["arc_width"] * scale
        if self.contrast:
            # A solid dot in a system colour, and the arc, if any, in the same colour.
            colour = _pack(system_rgb(brand.status_system(state)))
            paint.fill_circle(cx, cy, dot * scale, colour)
            if arc is not None:
                paint.arc(cx, cy, arc_radius, arc, light["arc_sweep"], colour, arc_width)
            return
        self._light(paint, cx, cy, dot, scale, DOT_FILL.get(state, "idle"), frame)
        if arc is not None:
            paint.arc(cx, cy, arc_radius, arc, light["arc_sweep"], self._argb("active", light["arc_alpha"]),
                      arc_width)

    def _light(self, paint, cx, cy, dot, scale, fill, frame):
        """The dot and its glow for a brand.glow frame (None: off). Dimmed, the dot is its colour over the card."""
        dim, opacity = (frame["dim"], frame["opacity"]) if frame is not None else (0.0, 0.0)
        if opacity > 0:
            paint.glow(cx, cy, brand.glow_radius(dot, frame["spread"]) * scale, brand.glow_stops(dot), self._rgb(fill),
                       opacity)
        paint.fill_circle(cx, cy, dot * scale, self._argb(fill, 1.0 - dim))
