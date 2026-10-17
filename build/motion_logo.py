"""The README's logo, moving: the mark as the notification-area icon moves while the product is watching.

Nothing here draws the mark or decides how it moves. Every frame's moment, head position and brightness is the
icon's own (ui.tray.icon_frame, stepped by icon_frame_ms as the icon's timer steps, through make_social.schedule -
one whole cycle of watching's motion, three breaths of the head and a sweep, so it loops without a seam), and every
head is the icon's own (ui.tray.IconFrames.compose at that position, in watching's colour at that breathing level).
The rest of each frame is the logo itself (brand.icon_render, with assets/make_icon.py's LOGO_RIM for the dark one):
a frame takes from the icon's frame only the pixels where it differs from the icon at rest, so frame 1 - the head
in its place at full colour - is the static logo exactly, which is what a viewer that does not animate shows, and
the dark logo keeps its rim in every frame.

Drawn at 192 px - shown at width 96, two device pixels to one - as RGBA, its rounded corners clear.

    python -X utf8 build/make_motion.py logo-light logo-dark
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

KIND = "logo"


def logo_rim(dark: bool) -> float:
    """The dark logo's rim, as assets/make_icon.py draws logo-dark.png; none for the light one."""
    if not dark:
        return 0.0
    spec = importlib.util.spec_from_file_location("make_icon", ROOT / "assets" / "make_icon.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.LOGO_RIM


def static(size: int, dark: bool) -> bytes:
    """The logo at rest, RGBA, as make_icon draws logo.png and logo-dark.png."""
    from codex_auto_resume import brand
    return brand.icon_render(size, logo_rim(dark))


def frames(plan: dict):
    """(delay in hundredths, scene, RGBA) for one cycle of the icon's motion in `plan["state"]`, frame 1 at rest."""
    import make_social
    from codex_auto_resume.ui import tray
    size, state = int(plan["size"]), plan.get("state", "watching")
    if state != "watching":
        raise ValueError("the logo moves as the icon does while watching, the one cycle make_social schedules")
    logo = static(size, bool(plan.get("dark")))
    icons = tray.IconFrames(size)
    top = tray.ICON_MOTION["levels"] - 1
    rest = icons.compose(0, tray.icon_level_colour(tray.icon_head_colour(state), top))
    for delay, position, level in make_social.schedule():
        moving = icons.compose(position, tray.icon_level_colour(tray.icon_head_colour(state), level))
        picture = bytearray(logo)
        for index in range(0, len(moving), 4):
            if moving[index:index + 4] != rest[index:index + 4]:
                blue, green, red, alpha = moving[index:index + 4]
                picture[index:index + 4] = bytes((red, green, blue, alpha))
        yield delay, "breath" if position == 0 else "sweep", bytes(picture)


def make(plan: dict):
    """Draws the logo plan into its output; the assembler's Report."""
    import motion_apng
    size = int(plan["size"])
    budget = plan.get("budget") or {}
    return motion_apng.assemble(ROOT / plan["output"], size, size, frames(plan), alpha=True,
                                target=budget.get("target"), cap=budget.get("cap"))


def render_input(plan: dict) -> str:
    """What the logo's picture is made from: its plan, what draws and moves the icon (make_screenshots.ICON_ROOTS),
    what draws the logo (brand.icon_render, followed), make_icon.py's rim and this file."""
    import hashlib
    import json
    import make_screenshots as shots
    package = ROOT / "src" / "codex_auto_resume"
    parts = [json.dumps(plan, sort_keys=True), shots.icon_drawing(),
             "\n".join(sorted(shots.reached_definitions(package, (("brand", "icon_render"),)))),
             repr(logo_rim(True)), shots.input_digest(Path(__file__)), shots.input_digest(ROOT / "build" / "make_social.py")]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
