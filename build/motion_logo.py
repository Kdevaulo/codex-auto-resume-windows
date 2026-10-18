"""The README's logo, moving: the mark as the notification-area icon moves while the product is watching.

Nothing here draws the mark or decides how it moves. The motion is the icon's own curve: watching's loop of five
monitoring breaths (make_social.watching_loop_ms), the head breathing toward the badge's blue on brand's raised cosine
(brand._breath over brand.GLOW monitoring_ms, ICON_MOTION dim - the curve ui.tray._breath_level steps into levels) and
sweeping clockwise along the stroke and back (ui.tray.icon_turn, at full colour). The tray draws that curve at the
steps its timer and explorer.exe can afford (ICON_MOTION breathe_frame_ms, 156 ms); the README's logo is not the tray,
so here the same curve is sampled every `step_ms` (25 ms: forty frames a second), its head at the exact angle and
tint for that moment - the same curve, only denser, and nothing it does not do (the owner, 2026-10-18: "이제 아이콘도
부드럽게 움직여?").

Every pixel is the logo's own rasteriser: each frame is the static logo (brand.icon_render, with assets/make_icon.py's
LOGO_RIM for the dark one) with the pixels a head can touch - where it rests and where it is - drawn again by the same
brand.icon_samples and icon_pixel, the head at that angle in that colour. So frame 1 - the head in its place at full
colour - is the static logo exactly, which is what a viewer that does not animate shows, and the dark logo keeps its
rim in every frame. One whole loop, so it repeats without a seam.

Drawn at 192 px - shown at width 96, two device pixels to one - as RGBA, its rounded corners clear.

    python -X utf8 build/make_motion.py logo-light logo-dark
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

KIND = "logo"
# How often the curve is sampled, in ms, unless the plan says (step_ms): forty frames a second.
STEP_MS = 25


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


def loop_ms() -> float:
    """One whole cycle of watching's motion: its breaths and its sweep's slot (make_social.watching_loop_ms)."""
    import make_social
    return make_social.watching_loop_ms()


def moment(at_ms: float, state: str = "watching") -> tuple:
    """(head angle in degrees, dim) at `at_ms` into the loop: the icon's own curve, unstepped. `dim` is how far the
    head's colour is toward the badge's blue, 0 to ICON_MOTION dim - what icon_level_colour does with a level, before
    _breath_level rounds it to one."""
    from codex_auto_resume import brand
    from codex_auto_resume.ui import tray
    if state != "watching":
        raise ValueError("the logo moves as the icon does while watching")
    rest = brand.ICON_SHAPE["arc_end"]
    turn = tray.icon_turn(state, at_ms)
    if turn is not None:
        return rest - turn, 0.0                          # sweeping, or home after it: full colour
    breath = brand._breath(at_ms, brand.GLOW[tray.ICON_BREATHS[state]])
    return rest, tray.ICON_MOTION["dim"] * breath


def tint(colour, dim: float) -> tuple:
    """`colour` `dim` of the way toward the badge's blue, rounded as icon_level_colour rounds it."""
    from codex_auto_resume import brand
    from codex_auto_resume.ui import tray
    target = brand.rgb(tray.ICON_DIM_TOWARD)
    return tuple(int(math.floor(one + (other - one) * dim + 0.5)) for one, other in zip(colour, target))


def cycle(state: str = "watching", step_ms: int = STEP_MS) -> list:
    """[(delay in ms, head angle, dim)] for one whole loop, sampled every `step_ms` from the moment it is entered; the
    last sample is held to the loop's end."""
    loop = int(round(loop_ms()))
    moments = list(range(0, loop, int(step_ms)))
    out = []
    for index, at in enumerate(moments):
        following = moments[index + 1] if index + 1 < len(moments) else loop
        angle, dim = moment(at, state)
        out.append((following - at, angle, dim))
    return out


def frames(plan: dict):
    """(delay in ms, scene, RGBA) for one loop of the icon's motion in `plan["state"]`, frame 1 at rest."""
    from codex_auto_resume import brand
    from codex_auto_resume.ui import tray
    size, state = int(plan["size"]), plan.get("state", "watching")
    dark = bool(plan.get("dark"))
    rim = logo_rim(dark)
    logo = static(size, dark)
    colour = tray.icon_head_colour(state)
    rest_angle = brand.ICON_SHAPE["arc_end"]
    rest_box = brand.icon_head_box(size, rest_angle)
    samples = {}
    for delay, angle, dim in cycle(state, int(plan.get("step_ms") or STEP_MS)):
        head = tint(colour, dim)
        picture = bytearray(logo)
        for box in {rest_box, brand.icon_head_box(size, angle)}:
            key = (round(angle, 9), box)
            if key not in samples:
                samples[key] = brand.icon_samples(size, rim, head_angle=angle, box=box)
            left, top = box[0], box[1]
            for y, row in enumerate(samples[key]):
                at = ((top + y) * size + left) * 4
                picture[at:at + len(row) * 4] = b"".join(bytes(brand.icon_pixel(sample, head)) for sample in row)
        if len(samples) > 64:
            samples.pop(next(iter(samples)))
        yield delay, "breath" if angle == rest_angle else "sweep", bytes(picture)


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
             "\n".join(sorted(shots.reached_definitions(package, (("brand", "icon_render"), ("ui.tray", "icon_turn"),
                                                                  ("brand", "_breath"))))),
             repr(logo_rim(True)), shots.input_digest(Path(__file__)), shots.input_digest(ROOT / "build" / "make_social.py")]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
