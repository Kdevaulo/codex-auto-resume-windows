"""The lossless APNG a motion picture is written as, held to a byte budget.

Generalised from make_screenshots.write_apng_patches and make_social.write_motion: the first frame is written whole
- and, where a still of it exists, as that still's PNG chunk for chunk, so a viewer that does not animate shows
exactly the still - and every later frame as the one rectangle that changed since the frame before, drawn over it
(APNG_KEEP, APNG_OVER; every pixel opaque, so it is exact) - or, where its changes lie far apart, one rectangle
each, all but the last shown for the shortest time a browser keeps (`patches`). A frame the same as the one before
only lengthens it.
Delays are whole hundredths of a second, never under SHORTEST: browsers show 10 ms or less as 100 ms. No palette, no
dither, nothing lossy - the reason it is an APNG and not a GIF (make_social.py's docstring).

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
APNG_KEEP, APNG_OVER = 0, 1
LEVEL = 9
# Changed rows this many unchanged rows apart are written as rectangles of their own (`patches`).
BAND_GAP = 48
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


def rows(rgb: bytes, width: int, box: tuple) -> bytes:
    """The scanlines of `box` (left, top, width, height) of an RGB picture `width` wide, each after PNG's filter byte 0."""
    left, top, wide, tall = box
    out = bytearray()
    for y in range(top, top + tall):
        out.append(0)
        out += rgb[(y * width + left) * 3:(y * width + left + wide) * 3]
    return bytes(out)


def _same_prefix(a: bytes, b: bytes, pixels: int) -> int:
    """How many whole pixels from the start of two rows are the same (binary search on slice equality)."""
    low, high = 0, pixels
    while low < high:
        middle = (low + high + 1) // 2
        if a[:middle * 3] == b[:middle * 3]:
            low = middle
        else:
            high = middle - 1
    return low


def _same_suffix(a: bytes, b: bytes, pixels: int) -> int:
    low, high = 0, pixels
    while low < high:
        middle = (low + high + 1) // 2
        if a[len(a) - middle * 3:] == b[len(b) - middle * 3:]:
            low = middle
        else:
            high = middle - 1
    return low


def changed(before: bytes, after: bytes, width: int, height: int):
    """The smallest (left, top, width, height) that differs between two RGB pictures, or None when they are the same."""
    if before == after:
        return None
    stride = width * 3
    top = 0
    while before[top * stride:(top + 1) * stride] == after[top * stride:(top + 1) * stride]:
        top += 1
    bottom = height - 1
    while before[bottom * stride:(bottom + 1) * stride] == after[bottom * stride:(bottom + 1) * stride]:
        bottom -= 1
    left, right = width, -1
    for y in range(top, bottom + 1):
        a, b = before[y * stride:(y + 1) * stride], after[y * stride:(y + 1) * stride]
        if a == b:
            continue
        left = min(left, _same_prefix(a, b, width))
        right = max(right, width - 1 - _same_suffix(a, b, width))
    return left, top, right - left + 1, bottom - top + 1


def patches(before: bytes, after: bytes, width: int, height: int) -> list:
    """The rectangles that differ between two RGB pictures, one per band of changed rows that BAND_GAP unchanged rows
    keep apart from the next: a breathing light at the top of the picture and the tray icon at its bottom are two
    small rectangles, where one round both would be most of the picture. [] when they are the same."""
    if before == after:
        return []
    stride = width * 3
    rows = [y for y in range(height) if before[y * stride:(y + 1) * stride] != after[y * stride:(y + 1) * stride]]
    bands, start = [], rows[0]
    for previous, row in zip(rows, rows[1:]):
        if row - previous > BAND_GAP:
            bands.append((start, previous))
            start = row
    bands.append((start, rows[-1]))
    boxes = []
    for top, bottom in bands:
        left, right = width, -1
        for y in range(top, bottom + 1):
            a, b = before[y * stride:(y + 1) * stride], after[y * stride:(y + 1) * stride]
            if a == b:
                continue
            left = min(left, _same_prefix(a, b, width))
            right = max(right, width - 1 - _same_suffix(a, b, width))
        boxes.append((left, top, right - left + 1, bottom - top + 1))
    return boxes


def _delay(hundredths: int) -> tuple:
    if hundredths < SHORTEST:
        raise ValueError("a frame held %d hundredths of a second: browsers show at least %d" % (hundredths, SHORTEST))
    share = Fraction(hundredths, 100)
    if share.numerator > 0xFFFF or share.denominator > 0xFFFF:
        raise ValueError("an APNG cannot hold a delay of %d hundredths" % hundredths)
    return share.numerator, share.denominator


def assemble(path, width: int, height: int, frames, *, still: bytes | None = None, target: int | None = None,
             cap: int | None = None) -> Report:
    """Writes `frames` - (delay in hundredths, scene, RGB picture) each, taken one at a time - to `path` as an APNG that
    loops forever, and reports it. `still` is a PNG whose pixels frame 1 must be and whose chunks frame 1 is written
    as. Nothing is written when the picture is over `cap` (BudgetExceeded)."""
    frames = iter(frames)
    first = next(frames, None)
    if first is None:
        raise ValueError("an APNG needs at least one picture")
    first = list(first)
    later, previous, scenes = [], first[2], {}
    for delay, scene, picture in frames:
        if len(picture) != width * height * 3:
            raise ValueError("a frame of %d bytes in a %dx%d picture" % (len(picture), width, height))
        if picture == previous:
            (later[-1] if later else first)[0] += delay
            continue
        boxes = patches(previous, picture, width, height)
        if len(boxes) > 1 and delay < len(boxes) * SHORTEST:
            boxes = [changed(previous, picture, width, height)]
        # Each rectangle but the last is shown for the shortest time a browser keeps, the last for the rest.
        for number, box in enumerate(boxes):
            last = number == len(boxes) - 1
            later.append([delay - (len(boxes) - 1) * SHORTEST if last else SHORTEST, scene, picture, box])
        previous = picture
    body, sequence = bytearray(), 1
    for delay, scene, picture, box in later:
        numerator, denominator = _delay(delay)
        control = chunk(b"fcTL", struct.pack(">IIIIIHHBB", sequence, box[2], box[3], box[0], box[1],
                                             numerator, denominator, APNG_KEEP, APNG_OVER))
        data = chunk(b"fdAT", struct.pack(">I", sequence + 1) + zlib.compress(rows(picture, width, box), LEVEL))
        body += control + data
        scenes[scene] = scenes.get(scene, 0) + len(control) + len(data)
        sequence += 2
    numerator, denominator = _delay(first[0])
    if still is not None:
        header, idat = _still_chunks(still, width, height, first[2])
    else:
        header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        idat = [chunk(b"IDAT", zlib.compress(rows(first[2], width, (0, 0, width, height)), LEVEL))]
    head = bytearray(SIGNATURE)
    head += chunk(b"IHDR", header)
    head += chunk(b"acTL", struct.pack(">II", 1 + len(later), 0))
    head += chunk(b"fcTL", struct.pack(">IIIIIHHBB", 0, width, height, 0, 0, numerator, denominator,
                                       APNG_KEEP, APNG_OVER))
    whole = b"".join(idat)
    scenes[first[1]] = scenes.get(first[1], 0) + len(whole)
    out = bytes(head) + whole + bytes(body) + chunk(b"IEND", b"")
    if cap is not None and len(out) > cap:
        raise BudgetExceeded(len(out), cap, scenes)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(out)
    return Report(len(out), 1 + len(later), first[0] + sum(item[0] for item in later), scenes,
                  target is not None and len(out) > target)


def _still_chunks(still: bytes, width: int, height: int, picture: bytes) -> tuple:
    """(IHDR data, [IDAT chunks as written]) of a still frame 1 must be: an 8-bit RGB PNG of the picture's size whose
    pixels are frame 1's."""
    import make_screenshots
    import tempfile
    found = chunks(still)
    header = dict(found)[b"IHDR"]
    if struct.unpack(">IIBBBBB", header) != (width, height, 8, 2, 0, 0, 0):
        raise ValueError("the still is not an 8-bit RGB PNG of %dx%d" % (width, height))
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "still.png"
        copy.write_bytes(still)
        _w, _h, pixels = make_screenshots.read_png_rgb(copy)
    if pixels != picture:
        raise ValueError("frame 1 is not the still")
    return header, [chunk(kind, data) for kind, data in found if kind == b"IDAT"]
