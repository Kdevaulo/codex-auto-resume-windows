"""Compose the repository's social preview card.

GitHub shows this image whenever a link to the repository is unfurled - in a chat, in a
search result, on a social site - so for a lot of people it is the first and sometimes the
only thing they see. It is 1280x640, and GitHub does not crop or pad it.

It is generated rather than drawn so it cannot drift from the palette and the mark, and it
lives under `build/` because it is a repository asset, not something the product ships.

The image itself has to be uploaded by hand: Settings -> General -> Social preview. There
is no API for it that a push can reach, so this writes the PNG into `docs/images/` and the
upload is a step someone with repository settings access does once.

The headline is the README's opening sentence, deliberately: this card is what a search
result and an unfurled link show, and a card whose first sentence differs from the page's
is two different products to whoever is skimming.

Run: python build/make_social.py

It writes the page and then rasterises it with Microsoft Edge headless - the same renderer
build/make_screenshots.py uses for the Codex panel - so the committed picture cannot drift
from the palette, the mark or the sentence without somebody running this. Pass --page-only
to write the HTML and stop, which is what to do on a machine with no Chromium.

It also writes docs/images/social-preview-motion.png, an animated PNG: the same card, its mark
moving exactly as the notification-area icon moves while the product is watching - three breaths
of the head, then a sweep out clockwise along the white stroke and back - one whole cycle of it,
22 s, looping forever. The motion is not drawn here: it is the icon's own curve (ui.tray.icon_turn
for the sweep, brand._breath over the monitoring breath for the tint), sampled every 25 ms as the
README's moving logo samples it (build/motion_logo.py: cycle, moment, tint) - the same curve as the
tray's, only denser than the tray's timer can afford (the owner, 2026-10-18: "그 소셜 프리뷰도
새로"). Every picture of the head is Edge's, from the card's own page with the head's circle placed
at that sample's angle and tinted - a sprite sheet of the card clipped round the mark, in a few
headless runs, each of which also draws the mark at rest to prove it draws the card's pixels.

An APNG and not a GIF: a GIF holds 256 colours, and the card is two soft gradients and anti-aliased
text, which a palette and its dither visibly degrade (the owner, on a first cut as a GIF). An APNG
keeps every pixel: its default image is the card's PNG itself, chunk for chunk, so a viewer that
does not animate PNGs - and most link unfurlers, which show one still picture anyway - shows
exactly docs/images/social-preview.png, the mark at rest at full brightness. Each later frame is
only the rectangle round the head that changed. Quality comes before size (the owner, 2026-10-18):
the motion is held under MOTION_LIMIT (8 MB) and is no longer meant for GitHub's social preview
upload, which takes a PNG of less than 1 MB - the still card, held under STILL_LIMIT, is that.

Upload the still card (Settings -> General -> Social preview -> Edit -> Upload an image). Pass
--png-only to make only the still card.
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "build"))

from codex_auto_resume import brand      # noqa: E402

PAGE = ROOT / "build" / "dist" / "social.html"
TARGET = ROOT / "docs" / "images" / "social-preview.png"
MOTION = ROOT / "docs" / "images" / "social-preview-motion.png"
WIDTH, HEIGHT = 1280, 640
# The mark's side on the card (TEMPLATE's .mark) and in its SVG's own units.
MARK_PX, SVG_BOX = 264, 512
# GitHub takes a social preview of less than a megabyte: the still card is the one uploaded.
STILL_LIMIT = 1000000
# The moving card's ceiling: quality before size, so a ceiling and no target (the owner, 2026-10-18).
MOTION_LIMIT = 8000000
# How often the icon's curve is sampled, in ms: motion_logo's step, forty frames a second.
STEP_MS = 25
# Sprite cells per headless run, the mark at rest among them: a sheet of 8 x 6 cells.
SPRITE_BATCH = 48
# Room round the mark in each sprite cell, so its rounded corners' edges are inside the cell.
CELL_PAD = 6
# How far past the head's edge a frame takes its own pixels, for the edge Edge softens.
MASK_REACH = 2.5
# How far a cell's mark at rest may be from the card's, in levels of a channel: Edge's dither, and nothing else.
SPRITE_DRIFT = 3
# Edge dithers a gradient on a pattern fixed to the screen's pixels, so a cell repeats the card's pixels only where
# it sits on the pattern as the card does: every cell and its box round the mark start on a multiple of this.
DITHER = 16
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

EDGE_CANDIDATES = tuple(
    Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
    for base in (os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                 os.environ.get("PROGRAMFILES", r"C:\Program Files")))

TEMPLATE = """<style>
  html,body{margin:0;padding:0}
  body{width:1280px;height:640px;overflow:hidden;
       background:radial-gradient(120%% 140%% at 18%% 30%%, #17457F 0%%, %(navy)s 55%%, #06182D 100%%);
       font:16px/1.4 "Segoe UI Variable Display","Segoe UI",system-ui,sans-serif;color:#fff}
  .wrap{display:flex;align-items:center;justify-content:center;gap:60px;height:100%%;
        padding:0 76px;box-sizing:border-box}
  .mark{width:264px;height:264px;flex:none;
        filter:drop-shadow(0 18px 46px rgba(3,12,26,.55))}
  .mark svg{width:100%%;height:100%%;display:block}
  h1{margin:0;font-size:66px;line-height:1.02;font-weight:700;letter-spacing:-.018em}
  .rule{width:104px;height:5px;border-radius:3px;margin:26px 0 22px;
        background:linear-gradient(90deg,%(cyan)s,%(sky)s)}
  p{margin:0;font-size:29px;line-height:1.34;color:#C3D4E8;max-width:730px}
  .tags{display:flex;gap:10px;margin-top:30px;flex-wrap:wrap}
  .tag{font-size:18px;letter-spacing:.02em;color:#9FC4E8;
       border:1px solid rgba(159,196,232,.35);border-radius:999px;padding:6px 16px}
</style>
<div class="wrap">
  <div class="mark">%(svg)s</div>
  <div>
    <h1>Codex&nbsp;Auto&nbsp;Resume</h1>
    <div class="rule"></div>
    <p>Automatically resume the exact same Codex task on Windows
       after a usage limit resets.</p>
    <div class="tags"><span class="tag">Windows</span><span class="tag">exact conversation</span>
      <span class="tag">acts only on failures it can name</span></div>
  </div>
</div>
"""


def find_edge() -> Path:
    for candidate in EDGE_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise SystemExit("Microsoft Edge was not found; pass --page-only to write just the HTML.")


def rasterise(page: Path) -> None:
    """The picture, at exactly the size GitHub asks for and no other.

    Checked rather than assumed: a renderer that quietly produced a different size would
    give GitHub something to crop, and the crop is not the card anybody looked at.
    """
    with tempfile.TemporaryDirectory() as workspace:
        shot = Path(workspace) / "social.png"
        subprocess.run(
            [str(find_edge()), "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=1", "--virtual-time-budget=3000",
             "--window-size=%d,%d" % (WIDTH, HEIGHT),
             "--screenshot=" + str(shot), page.as_uri()],
            check=True, capture_output=True, timeout=180, cwd=workspace, creationflags=NO_WINDOW)
        if not shot.is_file():
            raise SystemExit("the renderer produced nothing")
        header = shot.read_bytes()[:24]
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            raise SystemExit("the renderer did not produce a PNG")
        width, height = struct.unpack(">II", header[16:24])
        if (width, height) != (WIDTH, HEIGHT):
            raise SystemExit("expected %dx%d, got %dx%d" % (WIDTH, HEIGHT, width, height))
        if shot.stat().st_size >= STILL_LIMIT:
            raise SystemExit("the card is %d bytes: GitHub takes less than %d" % (shot.stat().st_size, STILL_LIMIT))
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_bytes(shot.read_bytes())


def page_text(svg: str) -> str:
    """The card's page around a mark's SVG."""
    return TEMPLATE % {"navy": brand.RAMP[0], "cyan": brand.RAMP[4], "sky": brand.RAMP[3], "svg": svg}


# ------------------------------------------------------------------ the mark, moving
def watching_loop_ms() -> float:
    """One whole cycle of watching's motion, in ms: its breaths and its sweep's slot, each a monitoring breath -
    the arithmetic ui.tray.icon_turn runs on."""
    from codex_auto_resume.ui import tray
    motion = tray.ICON_MOTION
    return float(brand.GLOW["monitoring_ms"]) * (motion["breaths"] + motion["sweep_breaths"])


def rest_head() -> tuple:
    """(angle, colour) of the head at rest: in its place at the sweep's end, in watching's full colour."""
    from codex_auto_resume.ui import tray
    return (round(brand.ICON_SHAPE["arc_end"], 6), tuple(tray.icon_head_colour("watching")))


def schedule(step_ms: int = STEP_MS) -> list:
    """[(delay in ms, head angle, head colour)] for one cycle of watching from the moment it is entered: the icon's own
    curve sampled every `step_ms` (motion_logo.cycle - icon_turn's angle, the monitoring breath's tint), each sample
    held until the next, the last to the cycle's end. A sample whose head is the one before's - the same angle and
    the same colour - only lengthens that one, so no two frames running are the same picture. The delays sum to the
    cycle exactly, and every one is a whole number of steps."""
    import motion_logo
    from codex_auto_resume.ui import tray
    colour = tray.icon_head_colour("watching")
    out = []
    for delay, angle, dim in motion_logo.cycle("watching", step_ms):
        head = (round(angle, 6), tuple(motion_logo.tint(colour, dim)))
        if out and out[-1][1:] == head:
            out[-1] = (out[-1][0] + delay,) + head
        else:
            out.append((delay,) + head)
    return out


def mark_svg(svg: str, angle: float, colour) -> str:
    """The mark's SVG with its head at `angle` degrees round the ring in `colour` (red, green, blue): the head the
    icon draws at that moment, written as assets/make_icon.py writes it. At rest - rest_head() - it is the SVG as it
    is, byte for byte."""
    import re
    x, y = brand.icon_head_centre(angle)
    centre = SVG_BOX / 2.0
    head = '<circle cx="%.3f" cy="%.3f" r="%.3f" fill="#%02X%02X%02X"/>' % (
        (centre + x * centre, centre - y * centre, brand.ICON_SHAPE["head_radius"] * centre) + tuple(colour))
    made, count = re.subn(r'<circle [^>]*/>', lambda _match: head, svg)
    if count != 1:
        raise SystemExit("the mark's SVG has %d circles; its head is the one" % count)
    return made


def mark_box(rgb: bytes) -> tuple:
    """(left, top, head): the box round the card's mark, in whole pixels on DITHER, and the head's centre there,
    (x, y) in the card's pixels - found from the head's pixels of pure accent, which sit round that centre."""
    accent = bytes(brand.rgb(brand.ICON_ACCENT))
    xs, ys = [], []
    for y in range(HEIGHT):
        row = rgb[y * WIDTH * 3:(y + 1) * WIDTH * 3]
        at = row.find(accent)
        while at >= 0:
            if at % 3 == 0:
                xs.append(at // 3)
                ys.append(y)
            at = row.find(accent, at + 1)
    if not xs:
        raise SystemExit("the card shows no head in the accent")
    scale = MARK_PX / float(SVG_BOX)
    hx, hy = brand.icon_head_centre()
    head = ((min(xs) + max(xs) + 1) / 2.0, (min(ys) + max(ys) + 1) / 2.0)
    left = head[0] - (SVG_BOX / 2.0) * (1 + hx) * scale
    top = head[1] - (SVG_BOX / 2.0) * (1 - hy) * scale
    return (int(left - CELL_PAD) // DITHER * DITHER, int(top - CELL_PAD) // DITHER * DITHER, head)


def head_mask(head: tuple, angle: float, left: int, top: int) -> list:
    """The cell's pixel offsets a frame with the head at `angle` takes from its own cell: those within reach of
    the head at rest or at `angle` (MASK_REACH past its edge, for the edge's softening). Everything else is the
    card's own pixel, so nothing but the head changes - however Edge's dither falls in a cell."""
    scale = MARK_PX / 2.0
    rest = brand.icon_head_centre()
    there = brand.icon_head_centre(angle)
    reach = brand.ICON_SHAPE["head_radius"] * scale + MASK_REACH
    centres = [(head[0] - left, head[1] - top),
               (head[0] - left + (there[0] - rest[0]) * scale, head[1] - top - (there[1] - rest[1]) * scale)]
    cell = cell_size()
    offsets = set()
    for cx, cy in centres:
        for y in range(max(0, int(cy - reach) - 1), min(cell, int(cy + reach) + 2)):
            for x in range(max(0, int(cx - reach) - 1), min(cell, int(cx + reach) + 2)):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= reach * reach:
                    offsets.add(y * cell + x)
    return sorted(offsets)


def cell_size() -> int:
    """A sprite cell's side: the mark, CELL_PAD each way, a pixel for where it falls between two and as much as
    mark_box's rounding down to DITHER can move it, in whole DITHERs."""
    return -(-(MARK_PX + 2 * CELL_PAD + 2 + DITHER - 1) // DITHER) * DITHER


def sprite_page(svg: str, heads: list, left: int, top: int) -> tuple:
    """A page of cells, one per (angle, colour) of `heads`: each the whole card page in a frame of its own,
    clipped to the box at (left, top) round the mark - so each is laid out and drawn as the card is, pixel for
    pixel. (html, columns, rows)."""
    import html
    cell = cell_size()
    columns = max(1, min(len(heads), 8))
    rows = (len(heads) + columns - 1) // columns
    parts = ["<style>html,body{margin:0;padding:0;background:#000;overflow:hidden}"
             ".c{position:absolute;width:%dpx;height:%dpx;overflow:hidden}"
             ".c iframe{position:absolute;left:%dpx;top:%dpx;width:%dpx;height:%dpx;border:0}</style>"
             % (cell, cell, -left, -top, WIDTH, HEIGHT)]
    for index, (angle, colour) in enumerate(heads):
        parts.append('<div class="c" style="left:%dpx;top:%dpx"><iframe scrolling="no" srcdoc="%s"></iframe></div>'
                     % (index % columns * cell, index // columns * cell,
                        html.escape(page_text(mark_svg(svg, angle, colour)), quote=True)))
    return "".join(parts), columns, rows


def sprite_batches(heads: list) -> list:
    """`heads` in sheets of SPRITE_BATCH cells, the head at rest first in every one: each headless run then shows
    that it draws the card's own pixels, not only the first."""
    rest = rest_head()
    moving = [head for head in heads if head != rest]
    size = SPRITE_BATCH - 1
    return [[rest] + moving[at:at + size] for at in range(0, max(1, len(moving)), size)]


def render_sheet(svg: str, heads: list, left: int, top: int) -> dict:
    """{(angle, colour): that cell's RGB}, every cell of `heads` from one headless Edge run."""
    import make_screenshots
    page_html, columns, rows = sprite_page(svg, heads, left, top)
    cell = cell_size()
    with tempfile.TemporaryDirectory() as workspace:
        page, shot = Path(workspace) / "sprites.html", Path(workspace) / "sprites.png"
        page.write_text(page_html, encoding="utf-8")
        subprocess.run(
            [str(find_edge()), "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=1", "--virtual-time-budget=8000",
             "--window-size=%d,%d" % (columns * cell, rows * cell),
             "--screenshot=" + str(shot), page.as_uri()],
            check=True, capture_output=True, timeout=300, cwd=workspace, creationflags=NO_WINDOW)
        if not shot.is_file():
            raise SystemExit("the renderer produced no sprite sheet")
        width, height, rgb = make_screenshots.read_png_rgb(shot)
    if (width, height) != (columns * cell, rows * cell):
        raise SystemExit("the sprite sheet is %dx%d, not %dx%d" % (width, height, columns * cell, rows * cell))
    cells = {}
    for index, head in enumerate(heads):
        x, y = index % columns * cell, index // columns * cell
        cells[head] = b"".join(rgb[((y + row) * width + x) * 3:((y + row) * width + x + cell) * 3]
                               for row in range(cell))
    return cells


def render_sprites(svg: str, heads: list, left: int, top: int, card: bytes) -> dict:
    """{(angle, colour): that cell's RGB} for every head, sprite_batches' sheets one headless run each. Each sheet's
    mark at rest must be the card's within SPRITE_DRIFT (Edge's dither), or it is not the same picture."""
    cells = {}
    region = card_region(card, left, top)
    for batch in sprite_batches(heads):
        sheet = render_sheet(svg, batch, left, top)
        drift = max(abs(one - other) for one, other in zip(sheet[batch[0]], region))
        if drift > SPRITE_DRIFT:
            raise SystemExit("a sprite sheet's mark at rest is %d levels off the card's: not the same picture" % drift)
        cells.update(sheet)
    return cells


def card_region(rgb: bytes, left: int, top: int) -> bytes:
    """The card's pixels a sprite cell at (left, top) covers."""
    cell = cell_size()
    return b"".join(rgb[((top + row) * WIDTH + left) * 3:((top + row) * WIDTH + left + cell) * 3]
                    for row in range(cell))


def motion_pictures(card: bytes, cells: dict, plan: list, box: tuple):
    """(delay in ms, the whole frame's RGB) for each frame of `plan`, one at a time: the card, with the pixels of the
    frame's head_mask taken from its cell. Every other pixel is the card's own, so only the head ever changes, and
    the frame at rest is the card exactly."""
    cell = cell_size()
    left, top, head = box
    rest = rest_head()
    for delay, angle, colour in plan:
        picture = bytearray(card)
        if (angle, colour) != rest:
            source = cells[(angle, colour)]
            for offset in head_mask(head, angle, left, top):
                at = ((top + offset // cell) * WIDTH + left + offset % cell) * 3
                picture[at:at + 3] = source[offset * 3:offset * 3 + 3]
        yield delay, bytes(picture)


def png_chunks(raw: bytes) -> list:
    """[(kind, data)] of a PNG's chunks, in order."""
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("not a PNG")
    chunks, at = [], 8
    while at < len(raw):
        length, kind = struct.unpack(">I4s", raw[at:at + 8])
        chunks.append((kind, raw[at + 8:at + 8 + length]))
        at += 12 + length
    return chunks


def write_motion(path: Path, still: bytes, pictures) -> int:
    """An APNG that loops forever, whose default image is `still` - the card's PNG - chunk for chunk, so a viewer
    without APNG shows exactly the card; returns its frame count. `pictures` is motion_pictures' (a delay is whole ms,
    or a Fraction of a second, as make_screenshots._delay_parts takes it): the first is the
    card, each later one is written as the rectangle that differs from the frame before, drawn over it with the
    frame before kept (APNG_KEEP, APNG_OVER - every pixel of the rectangle is opaque, so it is exact). The writing is
    make_screenshots.write_apng_patches', but for the default image, which that writes from pixels again."""
    import zlib
    import make_screenshots as shots
    chunks = png_chunks(still)
    header = dict(chunks)[b"IHDR"]
    if struct.unpack(">IIBBBBB", header)[2:] != (8, 2, 0, 0, 0):
        raise SystemExit("the card is not an 8-bit RGB PNG, the only kind its frames are written as")
    pictures = iter(pictures)
    delay, previous = next(pictures)
    numerator, denominator = shots._delay_parts(delay)
    body, sequence, count = bytearray(), 1, 1
    for delay, picture in pictures:
        box = shots._apng_changed(previous, picture, WIDTH, HEIGHT) or (0, 0, 1, 1)
        left, top, wide, tall = box
        later = shots._delay_parts(delay)
        body += shots._png_chunk(b"fcTL", struct.pack(">IIIIIHHBB", sequence, wide, tall, left, top,
                                                      later[0], later[1], shots.APNG_KEEP, shots.APNG_OVER))
        rows = shots._png_rows(shots._region(picture, WIDTH, box), wide, tall, wide, 0, 0)
        body += shots._png_chunk(b"fdAT", struct.pack(">I", sequence + 1) + zlib.compress(rows, 9))
        sequence += 2
        count += 1
        previous = picture
    out = bytearray(b"\x89PNG\r\n\x1a\n")
    out += shots._png_chunk(b"IHDR", header)
    out += shots._png_chunk(b"acTL", struct.pack(">II", count, 0))
    out += shots._png_chunk(b"fcTL", struct.pack(">IIIIIHHBB", 0, WIDTH, HEIGHT, 0, 0, numerator, denominator,
                                                 shots.APNG_KEEP, shots.APNG_OVER))
    out += b"".join(shots._png_chunk(kind, data) for kind, data in chunks if kind == b"IDAT")
    out += body
    out += shots._png_chunk(b"IEND", b"")
    shots.write_file(path, bytes(out))
    return count


def render_motion(svg: str) -> list:
    """docs/images/social-preview-motion.png, from the card as it is and sprite sheets of its mark; the plan."""
    import make_screenshots
    width, height, card = make_screenshots.read_png_rgb(TARGET)
    if (width, height) != (WIDTH, HEIGHT):
        raise SystemExit("the card is %dx%d" % (width, height))
    plan = schedule()
    if plan[0][1:] != rest_head():
        raise SystemExit("frame 1 is not the mark at rest at full brightness")
    box = mark_box(card)
    left, top, _head = box
    heads = sorted({(angle, colour) for _, angle, colour in plan})
    cells = render_sprites(svg, heads, left, top, card)
    count = write_motion(MOTION, TARGET.read_bytes(), motion_pictures(card, cells, plan, box))
    if count != len(plan):
        raise SystemExit("%d frames written of %d" % (count, len(plan)))
    size = MOTION.stat().st_size
    if size >= MOTION_LIMIT:
        raise SystemExit("%s is %d bytes: its ceiling is %d" % (MOTION, size, MOTION_LIMIT))
    return plan


def main(argv=None) -> int:
    """--page-only writes the page and stops; --png-only makes the still card alone; --out DIR writes both pictures
    into DIR instead of docs/images (a scratch render, which leaves the committed pictures alone)."""
    global TARGET, MOTION
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--out" in argv:
        folder = Path(argv[argv.index("--out") + 1]).resolve()
        TARGET, MOTION = folder / TARGET.name, folder / MOTION.name
    svg = (ROOT / "assets" / "brand" / "icon.svg").read_text(encoding="utf-8")
    PAGE.parent.mkdir(parents=True, exist_ok=True)
    PAGE.write_text(page_text(svg), encoding="utf-8")
    print("page  : %s" % PAGE)
    if "--page-only" in argv:
        print("rasterise it with a headless Chromium at %dx%d; see this file's docstring"
              % (WIDTH, HEIGHT))
        return 0
    rasterise(PAGE)
    print("card  : %s (%dx%d, %d bytes)" % (TARGET, WIDTH, HEIGHT, TARGET.stat().st_size))
    if "--png-only" not in argv:
        plan = render_motion(svg)
        loop = sum(each[0] for each in plan)
        print("motion: %s (%d frames, %.3f s a cycle, %.1f frames a second, %d bytes)"
              % (MOTION, len(plan), loop / 1000.0, len(plan) * 1000.0 / loop, MOTION.stat().st_size))
    print("upload: Settings -> General -> Social preview -> Edit -> Upload an image (the still card)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
