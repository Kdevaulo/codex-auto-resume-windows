"""The notification-area popup in a motion picture: its own paint at a pinned moment, offscreen.

The popup is drawn as the product draws it (`ui/popup/renderer.py`), from the same sample rows the still is
(make_screenshots.popup_view), at the stills' scale. What a person sees happen to it is only what the product does:

- It has no entrance. `Popup.show` places the window and calls ShowWindow, and `hide` calls SW_HIDE: it is there at
  once and gone at once, so a plan opens and closes it with a cut (motion_plan's `popup` step).
- Its status light breathes on the clock of the state it shows (`ui.popup.motion.halo`), which starts when the state
  is entered and is not restarted by closing and opening again: the picture's own clock, from its first moment. A
  picture whose length is whole breaths loops without a jump.
- Its countdowns are drawn again every second it is open (TIMER_TICK, 1000 ms): the picture's `ticks` since it was
  opened, one more second of the sample's clock each.
- Nothing of the popup is drawn for a pointer over a switch or a row (the renderer's hover face is a button's only,
  and a press has none on a switch), so the pointer is all a viewer sees of it.
- A press on a row's switch only fades the switch (PopupModel.begin: busy) while the control layer's answer is
  awaited; the answer (PopupModel.apply_outcome) changes the row and the switch then glides, knob and track, in
  brand's transition time on its curve (`glide_amount`) - at the popup's own 33 ms frame timer.

Each view below is the model's own: the rows are read, a press is `action_for` + `begin`, an answer is
`apply_outcome` - nothing is drawn that the model would not say. Frames are drawn whole when the ground changes
(a countdown, a row's tone, a busy switch, a glide) and only the light otherwise (`Renderer.draw_halo`), as the
popup's frame timer does.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)


class PopupFrames:
    """One popup, for one picture: `drawn(frame, closed)` is the picture at the frame's moment.

    Close it when done: the renderer holds GDI+ objects."""

    def __init__(self, locale: str, *, scale: float, theme: str = "light", design: str | None = None):
        import make_screenshots as shots
        from codex_auto_resume import brand, interface
        from codex_auto_resume.ui import popup as tray_popup
        from codex_auto_resume.ui.popup.motion import glide_amount
        self.shots, self.tray, self.glide_amount = shots, tray_popup, glide_amount
        self.strings = interface.STRINGS[locale]
        self.locale = tray_popup.locale_of(self.strings)
        self.scale = scale
        self.design = design or brand.DEFAULT_DESIGN
        self.renderer = tray_popup.Renderer()
        self.renderer.theme = theme
        self.renderer.design = self.design
        # v0.6.24: the popup is its card alone, with a float shadow under it (the card window and the shadow window);
        # a picture of it is that card and its shadow on a clear ground, `pad` round it, as the stills are
        # (popup_picture): RGBA, so the plan's canvas is a transparent one.
        self.renderer.lone = True
        self.theme = theme
        self.pad = tray_popup.layers.still_pad(scale)
        self._views = {}
        self._held = None             # the view whose ground the renderer's canvas holds, or None
        card = self.view((), (), 0)[1]["card"]
        self.shift = (self.pad - card[0], self.pad - card[1])
        self.size = (card[2] - card[0] + 2 * self.pad, card[3] - card[1] + 2 * self.pad)

    def view(self, off=(), busy=(), ticks=0):
        """(the model's view, its layout) with the rows in `off` switched off, the rows in `busy` awaiting an answer,
        and `ticks` seconds of the sample's clock gone since the popup was opened. Rows count from 1."""
        key = (tuple(off), tuple(busy), int(ticks))
        if key not in self._views:
            shots = self.shots
            model = self.tray.PopupModel(self.strings)
            now = shots.POPUP_NOW + key[2]
            model.apply_outcome(("read",), ("ok", {"rows": shots.popup_rows(), "status": shots.popup_status()}), now)
            vm = model.view(now)
            tasks = [task["interruption_id"] for task in vm["tasks"]]
            for row in key[0]:
                action = model.action_for(("check", tasks[row - 1]))
                model.begin(action)
                model.apply_outcome(action, ("ok", {"enabled": bool(action[3])}), now)
                vm = model.view(now)
            for row in key[1]:
                model.begin(model.action_for(("check", tasks[row - 1])))
                vm = model.view(now)
            self._views[key] = (vm, self.renderer.layout(vm, self.scale, self.locale), tasks)
        vm, plan, _tasks = self._views[key]
        return vm, plan

    def bounds(self) -> dict:
        """{"popup.switch.<n>": (left, top, width, height)} of each row's Auto-resume switch, rows counted from 1, in
        the canvas's pixels - where the popup's own layout puts them, moved with the card in the picture."""
        plan = self.view()[1]
        dx, dy = self.shift
        rects = [item["rect"] for item in plan["items"] if item["kind"] == "switch"]
        return {"popup.switch.%d" % (index + 1): (rect[0] + dx, rect[1] + dy, rect[2] - rect[0], rect[3] - rect[1])
                for index, rect in enumerate(rects)}

    def drawn(self, frame, closed: bytes) -> bytes:
        """The RGBA picture (straight alpha) at `frame`: `closed`, a clear canvas, while no popup is open."""
        if not frame.popup:
            self._held = None
            return closed
        state = dict(frame.popup)
        ticks = (frame.t - state["opened"]) // 1000
        key = (tuple(state["off"]), tuple(state["busy"]), int(ticks))
        vm, plan = self.view(*key)
        tasks = self._views[key][2]
        gliding = {}
        for row, (started, begin, end) in state["glides"]:
            amount, done = self.glide_amount((started, begin, end), frame.t)
            if not done:
                gliding[("check", tasks[row - 1])] = amount
        light = self.tray.halo(vm["light"], frame.t, frame.t, design=self.design)
        if gliding:
            self.renderer.draw(vm, plan, frame=light, glides=gliding)
            self._held = None
        elif self._held == key:
            self.renderer.draw_halo(plan, light)
        else:
            self.renderer.draw(vm, plan, frame=light)
            self._held = key
        _w, _h, bgra = self.shots.popup_picture(self.renderer, plan, self.pad, self.theme, self.design)
        return self.shots.clear_rgba(bgra)

    def is_the_still(self, frame, closed: bytes, still: Path) -> bool:
        """Whether the picture at `frame` is, pixel for pixel, the first frame of the committed `still`: the popup the
        README's other pictures and the guide show, made by make_screenshots.render_popup. The motion's first frame is
        what a viewer that does not animate shows, so it must be that one."""
        width, height, rgb, alpha = self.shots.read_png(still)
        picture = self.drawn(frame, closed)
        self._held = None
        if (width, height) != tuple(self.size) or alpha is None:
            return False
        rgba = bytearray(width * height * 4)
        rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4] = rgb[0::3], rgb[1::3], rgb[2::3], alpha
        return bytes(rgba) == picture

    def close(self) -> None:
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None
