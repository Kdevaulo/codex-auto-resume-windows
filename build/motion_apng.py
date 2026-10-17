"""The lossless APNG a motion picture is written as, held to a byte budget.

Generalised from make_screenshots.write_apng_patches and make_social.write_motion: the first frame is written whole
- and, where a still of it exists, as that still's PNG chunk for chunk, so a viewer that does not animate shows
exactly the still - and every later frame as the one rectangle that changed since the frame before, drawn over it
(APNG_KEEP, APNG_OVER; every pixel opaque, so it is exact) - or, where its changes lie far apart, one rectangle
each, all but the last shown for the shortest time a browser keeps (`patches`). A frame the same as the one before
only lengthens it.
Delays are whole hundredths of a second, never under SHORTEST: browsers show 10 ms or less as 100 ms. No palette, no
dither, nothing lossy - the reason it is an APNG and not a GIF (make_social.py's docstring).

A picture whose ground is clear - the window on its own, the card on its own, the logo - is RGBA with straight alpha
(`alpha=True`): every frame's rectangle then replaces what was there (APNG_SOURCE) instead of being laid over it,
so a pixel that turns clearer - a card fading out - is clear and not the frame before showing through.

The budget (APNG-storyboard.md section 2) is a target and a hard cap: over the cap the file is not written and
BudgetExceeded names the bytes each scene took, largest first, so the levers can be pulled where they count; over the
target it is written and the report says so. The same frames make the same bytes: nothing here reads a clock, a
machine or a random number, and zlib is asked for one fixed level.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import struct
import sys
from typing import NamedTuple
import zlib

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

SHORTEST = 2                         # hundredths of a second
APNG_KEEP = 0                        # dispose: leave the frame as it is
APNG_SOURCE, APNG_OVER = 0, 1        # blend: replace the rectangle, or draw over it
LEVEL = 9
# Changed rows this many unchanged rows apart are written as rectangles of their own (`patches`).
BAND_GAP = 32
SIGNATURE = b"\x89PNG\r\n\x1a\n"


class BudgetExceeded(ValueError):
    """A picture over its hard cap: what each scene cost, so the storyboard's levers can be pulled."""

    def __init__(self, size: int, cap: int, scenes: dict):
        self.size, self.cap, self.scenes = size, cap, dict(scenes)
        costly = ", ".join("%s %d" % (name, cost) for name, cost in sorted(scenes.items(), key=lambda item: -item[1]))
        super().__init__("%d bytes is over the cap of %d; bytes by scene: %s" % (size, cap, costly))


class Report(NamedTuple):
    """What was written: its size, how many frames, how long it plays (hundredths), each scene's bytes, and whether
    it is over its target."""
    size: int
    frames: int
    hundredths: int
    scenes: dict
    over_target: bool


def chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def chunks(raw: bytes) -> list:
    """[(kind, data)] of a PNG's chunks, in order."""
    if raw[:8] != SIGNATURE:
        raise ValueError("not a PNG")
    out, at = [], 8
    while at < len(raw):
        length, kind = struct.unpack(">I4s", raw[at:at + 8])
        out.append((kind, raw[at + 8:at + 8 + length]))
        at += 12 + length
    return out


def rows(rgb: bytes, width: int, box: tuple, bpp: int = 3) -> bytes:
    """The scanlines of `box` (left, top, width, height) of a picture `width` wide, `bpp` bytes a pixel (3, RGB; 4,
    RGBA), each after PNG's filter byte 0."""
    left, top, wide, tall = box
    out = bytearray()
    for y in range(top, top + tall):
        out.append(0)
        out += rgb[(y * width + left) * bpp:(y * width + left + wide) * bpp]
    return bytes(out)


def _same_prefix(a: bytes, b: bytes, pixels: int, bpp: int = 3) -> int:
    """How many whole pixels from the start of two rows are the same (binary search on slice equality)."""
    low, high = 0, pixels
    while low < high:
        middle = (low + high + 1) // 2
        if a[:middle * bpp] == b[:middle * bpp]:
            low = middle
        else:
            high = middle - 1
    return low


def _same_suffix(a: bytes, b: bytes, pixels: int, bpp: int = 3) -> int:
    low, high = 0, pixels
    while low < high:
        middle = (low + high + 1) // 2
        if a[len(a) - middle * bpp:] == b[len(b) - middle * bpp:]:
            low = middle
        else:
            high = middle - 1
    return low


def changed(before: bytes, after: bytes, width: int, height: int, bpp: int = 3):
    """The smallest (left, top, width, height) that differs between two pictures, or None when they are the same."""
    if before == after:
        return None
    return _tight(before, after, width, (0, 0, width, height), bpp)


def patches(before: bytes, after: bytes, width: int, height: int, bpp: int = 3) -> list:
    """The rectangles that differ between two pictures, cut apart wherever BAND_GAP unchanged rows or columns lie
    between changes: a breathing light at the top of the picture and the tray icon at its bottom, or the card's light
    and a pointer beside it, are small rectangles each, where one round them would be much of the picture. Largest
    first; [] when the pictures are the same."""
    if before == after:
        return []
    found = []
    _cut(before, after, width, (0, 0, width, height), found, bpp)
    return sorted(found, key=lambda box: (-box[2] * box[3], box[1], box[0]))


def _tight(before: bytes, after: bytes, width: int, box: tuple, bpp: int = 3):
    """The smallest rectangle inside `box` that holds every change there, or None."""
    left0, top0, wide, tall = box
    stride = width * bpp
    found = []
    left, right = left0 + wide, left0 - 1
    for y in range(top0, top0 + tall):
        a = before[y * stride + left0 * bpp:y * stride + (left0 + wide) * bpp]
        b = after[y * stride + left0 * bpp:y * stride + (left0 + wide) * bpp]
        if a == b:
            continue
        found.append(y)
        left = min(left, left0 + _same_prefix(a, b, wide, bpp))
        right = max(right, left0 + wide - 1 - _same_suffix(a, b, wide, bpp))
    if not found:
        return None
    return left, found[0], right - left + 1, found[-1] - found[0] + 1


def _cut(before: bytes, after: bytes, width: int, box: tuple, found: list, bpp: int = 3) -> None:
    box = _tight(before, after, width, box, bpp)
    if box is None:
        return
    left, top, wide, tall = box
    stride = width * bpp

    def span(y, x, count):
        return slice(y * stride + x * bpp, y * stride + (x + count) * bpp)
    # Rows: a run of BAND_GAP unchanged rows inside the rectangle.
    run = 0
    for y in range(top, top + tall):
        run = run + 1 if before[span(y, left, wide)] == after[span(y, left, wide)] else 0
        if run >= BAND_GAP:
            _cut(before, after, width, (left, top, wide, y - top + 1), found, bpp)
            _cut(before, after, width, (left, y + 1, wide, top + tall - y - 1), found, bpp)
            return
    # Columns: a strip BAND_GAP wide unchanged on every row of the rectangle, looked for every half of it.
    for x in range(left + 1, left + wide - BAND_GAP, max(1, BAND_GAP // 2)):
        if all(before[span(y, x, BAND_GAP)] == after[span(y, x, BAND_GAP)] for y in range(top, top + tall)):
            _cut(before, after, width, (left, top, x - left, tall), found, bpp)
            _cut(before, after, width, (x + BAND_GAP, top, left + wide - x - BAND_GAP, tall), found, bpp)
            return
    found.append(box)


def _join(one: tuple, other: tuple) -> tuple:
    left, top = min(one[0], other[0]), min(one[1], other[1])
    return (left, top, max(one[0] + one[2], other[0] + other[2]) - left,
            max(one[1] + one[3], other[1] + other[3]) - top)


def _area(box: tuple) -> int:
    return box[2] * box[3]


def _delay(hundredths: int) -> tuple:
    if hundredths < SHORTEST:
        raise ValueError("a frame held %d hundredths of a second: browsers show at least %d" % (hundredths, SHORTEST))
    share = Fraction(hundredths, 100)
    if share.numerator > 0xFFFF or share.denominator > 0xFFFF:
        raise ValueError("an APNG cannot hold a delay of %d hundredths" % hundredths)
    return share.numerator, share.denominator


def assemble(path, width: int, height: int, frames, *, still: bytes | None = None, target: int | None = None,
             cap: int | None = None, alpha: bool = False) -> Report:
    """Writes `frames` - (delay in hundredths, scene, picture) each, taken one at a time - to `path` as an APNG that
    loops forever, and reports it. A picture is RGB, or with `alpha` RGBA with straight alpha, every later rectangle
    then replacing what was under it. `still` is a PNG whose pixels frame 1 must be and whose chunks frame 1 is written
    as. Nothing is written when the picture is over `cap` (BudgetExceeded)."""
    bpp = 4 if alpha else 3
    blend = APNG_SOURCE if alpha else APNG_OVER
    frames = iter(frames)
    first = next(frames, None)
    if first is None:
        raise ValueError("an APNG needs at least one picture")
    first = list(first)
    if len(first[2]) != width * height * bpp:
        raise ValueError("a frame of %d bytes in a %dx%d picture" % (len(first[2]), width, height))
    later, previous, scenes = [], first[2], {}
    for delay, scene, picture in frames:
        if len(picture) != width * height * bpp:
            raise ValueError("a frame of %d bytes in a %dx%d picture" % (len(picture), width, height))
        if picture == previous:
            (later[-1] if later else first)[0] += delay
            continue
        boxes = patches(previous, picture, width, height, bpp)
        while len(boxes) > max(1, delay // SHORTEST):
            # Not time enough to show each for SHORTEST: the two that make the smallest rectangle together are one.
            pairs = [(i, j) for i in range(len(boxes)) for j in range(i + 1, len(boxes))]
            i, j = min(pairs, key=lambda pair: _area(_join(boxes[pair[0]], boxes[pair[1]])))
            rest = [box for index, box in enumerate(boxes) if index not in (i, j)]
            boxes = sorted(rest + [_join(boxes[i], boxes[j])], key=lambda box: (-box[2] * box[3], box[1], box[0]))
        # Each rectangle but the last is shown for the shortest time a browser keeps, the last for the rest.
        for number, box in enumerate(boxes):
            last = number == len(boxes) - 1
            later.append([delay - (len(boxes) - 1) * SHORTEST if last else SHORTEST, scene, picture, box])
        previous = picture
    body, sequence = bytearray(), 1
    for delay, scene, picture, box in later:
        numerator, denominator = _delay(delay)
        control = chunk(b"fcTL", struct.pack(">IIIIIHHBB", sequence, box[2], box[3], box[0], box[1],
                                             numerator, denominator, APNG_KEEP, blend))
        data = chunk(b"fdAT", struct.pack(">I", sequence + 1) + zlib.compress(rows(picture, width, box, bpp), LEVEL))
        body += control + data
        scenes[scene] = scenes.get(scene, 0) + len(control) + len(data)
        sequence += 2
    numerator, denominator = _delay(first[0])
    if still is not None:
        header, idat = _still_chunks(still, width, height, first[2], alpha)
    else:
        header = struct.pack(">IIBBBBB", width, height, 8, 6 if alpha else 2, 0, 0, 0)
        idat = [chunk(b"IDAT", zlib.compress(rows(first[2], width, (0, 0, width, height), bpp), LEVEL))]
    head = bytearray(SIGNATURE)
    head += chunk(b"IHDR", header)
    head += chunk(b"acTL", struct.pack(">II", 1 + len(later), 0))
    head += chunk(b"fcTL", struct.pack(">IIIIIHHBB", 0, width, height, 0, 0, numerator, denominator,
                                       APNG_KEEP, blend))
    whole = b"".join(idat)
    scenes[first[1]] = scenes.get(first[1], 0) + len(whole)
    out = bytes(head) + whole + bytes(body) + chunk(b"IEND", b"")
    if cap is not None and len(out) > cap:
        raise BudgetExceeded(len(out), cap, scenes)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(out)
    return Report(len(out), 1 + len(later), first[0] + sum(item[0] for item in later), scenes,
                  target is not None and len(out) > target)


def _still_chunks(still: bytes, width: int, height: int, picture: bytes, alpha: bool = False) -> tuple:
    """(IHDR data, [IDAT chunks as written]) of a still frame 1 must be: an 8-bit PNG of the picture's size and kind
    (RGB; RGBA with `alpha`) whose pixels are frame 1's."""
    import make_screenshots
    import tempfile
    found = chunks(still)
    header = dict(found)[b"IHDR"]
    if struct.unpack(">IIBBBBB", header) != (width, height, 8, 6 if alpha else 2, 0, 0, 0):
        raise ValueError("the still is not an 8-bit %s PNG of %dx%d" % ("RGBA" if alpha else "RGB", width, height))
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "still.png"
        copy.write_bytes(still)
        _w, _h, rgb, clear = make_screenshots.read_png(copy)
    if alpha:
        pixels = bytearray(width * height * 4)
        pixels[0::4], pixels[1::4], pixels[2::4] = rgb[0::3], rgb[1::3], rgb[2::3]
        pixels[3::4] = clear if clear is not None else b"\xff" * (width * height)
        pixels = bytes(pixels)
    else:
        pixels = rgb
    if pixels != picture:
        raise ValueError("frame 1 is not the still")
    return header, [chunk(kind, data) for kind, data in found if kind == b"IDAT"]
