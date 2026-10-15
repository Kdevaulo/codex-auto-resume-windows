"""The Dashboard in a motion picture: frames drawn by the window itself, offscreen, from canned answers.

The window has a render mode (gui/WindowRender.cs). Given a job - the replies its reads get, and a list of frames,
each a state (page, Settings section, scroll, a control's hover or pressed face, a drop-down's unsaved value, its
open list) and the moment of the lights - it builds itself as the layout audit builds it, never shown and not a
top-level window, puts itself in each state, waits until it holds still as a capture waits, and draws itself into a
bitmap; only what changed since the frame before is written, as raw RGB, with frames.json beside it (the client size,
each frame's rectangle, the bounds of the controls a pointer goes to, every read nobody answered).

The replies are the bridge's own, asked here of the generator's pinned scratch installation
(make_screenshots.pinned_installation: the same records, the same clock, the same stand-in registry and engine the
wire goldens and the envelope are asked of), one set per language the picture shows, with what a Save in the picture
stored (`forms` in the plan). Every command the window sends that is not among them - each one that would change
something - is refused, so the render mode can neither write nor start anything.

This compiles its own copy of the window (gui/window.sources, gui/app.manifest - which makes the window DPI-aware, so
it draws at this machine's scale as the captured pictures were) into a scratch folder, and runs it there with
CREATE_NO_WINDOW. Nothing is shown on the screen and nothing of the real installation is read.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import motion_plan  # noqa: E402

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
# Reads the pictured pages make beyond the envelope's: the power action's card on Settings > General, and the
# Diagnostics page's State folder and its plugin copy.
EXTRA_READS = (("power-action", None), ("state-access", None), ("plugin-copy", None))
# How many lines a turn of the wheel scrolls in a picture (WindowRender.RenderWheelLines): Windows' default.
WHEEL_LINES = 3
# The longest a render job may take, in seconds.
RENDER_LIMIT = 30 * 60


def compile_window(folder: Path) -> Path:
    """The window built from the working tree into `folder`, with its manifest (DPI awareness) as the release has it."""
    import make_screenshots
    exe = Path(folder) / "CodexAutoResumeSettings.exe"
    arguments = [str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/optimize+", "/out:" + str(exe),
                 "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                 "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll"]
    arguments += [str(ROOT / name) for name in make_screenshots.window_sources()]
    done = subprocess.run(arguments, capture_output=True, text=True, timeout=600, creationflags=NO_WINDOW)
    if done.returncode != 0 or not exe.is_file():
        raise RuntimeError("the window did not compile:\n" + (done.stdout or "") + (done.stderr or ""))
    return exe


def answers(locale: str, stored: dict | None = None) -> list:
    """[{command, argument, reply}]: the bridge's replies to every read the pictured pages make, in `locale`, from
    the pinned scratch installation with `stored` written over its settings (what a Save in the picture stored)."""
    import make_screenshots as shots
    from codex_auto_resume import config, l10n
    out = []
    previous = os.environ.get(l10n.ENV_LANG)
    with tempfile.TemporaryDirectory() as name:
        workspace = Path(name)
        with shots.pinned_installation(workspace) as surface:
            home = workspace / "home"
            if stored:
                path = home / "config" / "settings.json"
                values = json.loads(path.read_text(encoding="utf-8"))
                values.update(stored)
                path.write_text(json.dumps(values, indent=2), encoding="utf-8")
            if os.name == "nt":
                shots.owner_only(config.Paths(home).state_dir)
            os.environ[l10n.ENV_LANG] = locale
            try:
                replies = {}
                for command, argument in shots.WINDOW_READS + EXTRA_READS:
                    replies[command] = shots.ask(surface, command, argument)
                    out.append({"command": command, "argument": None if argument is None else
                                json.dumps(argument, separators=(",", ":")), "reply": replies[command]})
                preview = shots.preview_request((replies["describe"] or {}).get("schema") or [],
                                                (replies["settings"] or {}).get("settings") or {})
                if preview is not None:
                    out.append({"command": preview[0], "argument": None, "reply": shots.ask(surface, *preview)})
            finally:
                if previous is None:
                    os.environ.pop(l10n.ENV_LANG, None)
                else:
                    os.environ[l10n.ENV_LANG] = previous
    failed = [item["command"] for item in out if not item["reply"].get("ok")]
    if failed:
        raise RuntimeError("the pinned installation could not answer %s" % failed)
    for item in out:
        _as_captured(item["reply"])
    return out


def _as_captured(value) -> None:
    """A reply as the captured pictures' bridge gives it: the watcher's heartbeat there is written every second by
    the capture's own mutex holder (make_screenshots.HOLD_MUTEX), which hands it no usage reading, so the window
    pictured shows none - while the pinned installation's heartbeat carries one (write_heartbeat). The motion shows
    what the pictures show: the watcher's `usage` is taken out wherever a reply carries the watcher."""
    if isinstance(value, dict):
        watcher = value.get("watcher")
        if isinstance(watcher, dict):
            watcher.pop("usage", None)
        for item in value.values():
            _as_captured(item)
    elif isinstance(value, list):
        for item in value:
            _as_captured(item)


def frame_state(frame: motion_plan.Frame, index: int) -> dict:
    """What the render mode is told for one frame: its window state and the moment of its lights."""
    state = motion_plan.thawed(frame.window)
    state["index"] = index
    state["light"] = frame.t
    return state


def job(plan: dict, frames: list, out: Path, forms: dict | None = None) -> dict:
    """The render job for `frames` of `plan`: one entry per frame that needs the window drawn, in order."""
    targets = sorted(name for name in motion_plan.pointer_targets(frames) if not name.startswith("card."))
    targets += sorted({value for frame in frames for key, value in frame.window if key in ("hover", "pressed")
                       and isinstance(value, str)} - set(targets))
    if forms is None:
        forms = {locale: {"answers": answers(locale, stored)} for locale, stored in plan.get("forms", {}).items()}
    canvas = plan.get("canvas") or {}
    return {"out": str(out), "theme": canvas.get("theme", "light"), "design": canvas.get("design", "soft"),
            "forms": forms, "targets": targets,
            "frames": [frame_state(frame, index) for index, frame in enumerate(frames)]}


def render(exe: Path, job_data: dict, folder: Path) -> dict:
    """Runs the window's render mode on `job_data` (written into `folder`), and returns its frames.json - raising
    when it failed or any read it made went unanswered."""
    import make_screenshots as shots
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "job.json"
    path.write_text(json.dumps(job_data, ensure_ascii=False), encoding="utf-8")
    environment = dict(os.environ, CODEX_AR_RENDER_PLAN=str(path), CODEX_AR_STILL_READY="Local\\CodexAutoResume.Render",
                       CODEX_AR_STILL_NOW=repr(shots.ENVELOPE_NOW), CODEX_AR_STILL_CLOCK=repr(shots.WINDOW_CLOCK),
                       CODEX_AR_STILL_LIGHT="0", CODEX_HOME=str(folder / "no-codex"),
                       LOCALAPPDATA=str(folder / "no-local"))
    from codex_auto_resume import config
    for override in (config.ENV_HOME, config.ENV_CODEX_EXE):
        environment.pop(override, None)
    done = subprocess.run([str(exe)], env=environment, timeout=RENDER_LIMIT, creationflags=NO_WINDOW,
                          capture_output=True)
    result = Path(job_data["out"]) / "frames.json"
    if not result.is_file():
        raise RuntimeError("the render mode wrote no frames.json (exit %d)" % done.returncode)
    read = json.loads(result.read_text(encoding="utf-8"))
    if read.get("error") or done.returncode != 0:
        raise RuntimeError("the render mode failed (exit %d): %s" % (done.returncode, read.get("error")))
    return read


def pictures(result: dict, folder: Path):
    """(frame index, client RGB, bounds) for each frame the render mode drew, the client picture rebuilt whole from
    each frame's changed rectangle."""
    width, height = result["client"]
    picture = None
    for entry in result["frames"]:
        left, top, wide, tall = entry["box"]
        if picture is None:
            if (left, top, wide, tall) != (0, 0, width, height):
                raise RuntimeError("the render's first frame is not whole")
            picture = bytearray((Path(folder) / entry["file"]).read_bytes())
        elif entry["file"]:
            patch = (Path(folder) / entry["file"]).read_bytes()
            for row in range(tall):
                at = ((top + row) * width + left) * 3
                picture[at:at + wide * 3] = patch[row * wide * 3:(row + 1) * wide * 3]
        yield int(entry["index"]), bytes(picture), entry.get("bounds") or {}
