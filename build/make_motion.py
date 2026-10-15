"""Make the README's motion pictures: the product at work, every frame drawn by its own code, offscreen.

    python -X utf8 build/make_motion.py --dry-run [PLAN ...]   # the frames each plan asks for, scene by scene

PLAN is a plan's name under build/motion/ (readme-en, readme-ko) or a path; with none, every README plan. The plans
and their format are build/motion_plan.py's; what a frame is drawn from is the window's own render mode, the card's
own paint and the tray icon's own frames, laid on one canvas with the pointer drawn over them.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import motion_plan  # noqa: E402

PLAN_NAMES = ("readme-en", "readme-ko")


def plan_path(name) -> Path:
    """A plan named by its file under build/motion/, or a path to one."""
    path = Path(name)
    if path.suffix == ".json" and path.is_file():
        return path
    return motion_plan.PLANS / ("%s.json" % name)


def schedule(plan: dict, also=()) -> tuple:
    """(frames, delays in hundredths, end in ms): every frame the plan's steps emit, with the frames the lights, the
    ripples and `also` (the tray icon's frame times) add, each with the delay it is held for."""
    end = motion_plan.plan_end(plan)
    frames = motion_plan.fill(motion_plan.expand(plan), end, int(plan.get("lights_per_second") or 0), also,
                              first_hold=int(plan.get("first_hold") or 0), ripple_step=int(plan.get("ripple_step") or 0))
    return frames, motion_plan.delays([frame.t for frame in frames], end), end


def run(plan: dict, draw, also=()):
    """(delay in hundredths, scene, picture) for each frame of the plan, drawn by `draw(frame)`, one at a time: a
    frame whose picture is the one before's only lengthens it, so a picture is written once however long it holds.
    The first is always frame 1, even when the next is the same."""
    frames, held, _end = schedule(plan, also)
    previous = None
    for frame, delay in zip(frames, held):
        picture = draw(frame)
        if previous is not None and picture == previous[2]:
            previous[0] += delay
            continue
        if previous is not None:
            yield tuple(previous)
        previous = [delay, frame.scene, picture]
    if previous is not None:
        yield tuple(previous)


def describe(plan: dict, also=()) -> str:
    """The frames a plan asks for, scene by scene, for reading before anything is drawn."""
    frames, held, end = schedule(plan, also)
    lines, counts = [], {}
    for frame, delay in zip(frames, held):
        entry = counts.setdefault(frame.scene, [0, 0, frame.t])
        entry[0] += 1
        entry[1] += delay
    for scene, (count, hundredths, start) in counts.items():
        lines.append("  %-5s at %6.2f s  %3d frames  %5.2f s" % (scene, start / 1000.0, count, hundredths / 100.0))
    lines.append("  %d frames, %.2f s, %d window states, targets: %s"
                 % (len(frames), end / 1000.0, len(motion_plan.window_states(frames)),
                    ", ".join(sorted(motion_plan.pointer_targets(frames)))))
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    dry = "--dry-run" in argv
    names = [item for item in argv if not item.startswith("--")] or list(PLAN_NAMES)
    if not dry:
        raise SystemExit("only --dry-run is built so far")
    for name in names:
        plan = motion_plan.load(plan_path(name))
        print("%s -> %s" % (plan["name"], plan.get("output")))
        print(describe(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
