"""The social preview's motion: one cycle of the watching icon's motion on the card, as an APNG, under 1 MB.

build/make_social.py writes docs/images/social-preview-motion.png: an animated PNG whose default image is the
still card's PNG itself, and whose later frames are only the head's changed rectangle, at the icon's own timing
(make_screenshots.icon_timeline). These tests read what it wrote with a reader of their own, written from the PNG
and APNG specifications and sharing no code with the writer - chunks, CRCs, sequence numbers, inflate, the five
row filters, dispose - and hold it to what the owner asked: the mark moving as the real icon moves, looping
forever, every pixel kept (no palette and no dither, which a GIF had needed), frame 1 the card exactly.

The reader is pure Python, so its work is kept to what changes: the still card is decoded once for the module,
the motion's default image is not decoded again when its IDAT chunks are the still's byte for byte, and the frames
are composited on a canvas the size of the mark's box only. CAR_SOCIAL_MOTION points the committed-motion tests
at another file (a mutated copy, to prove they fail).
"""
from __future__ import annotations

from fractions import Fraction
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "build"))

import make_social        # noqa: E402
from codex_auto_resume import brand     # noqa: E402
from codex_auto_resume.ui import tray   # noqa: E402

MOTION = Path(os.environ.get("CAR_SOCIAL_MOTION") or ROOT / "docs" / "images" / "social-preview-motion.png")
STILL = ROOT / "docs" / "images" / "social-preview.png"
CARD = {}


def setUpModule():
    """The still card, decoded once: its raw bytes, its IDAT chunks and its pixels."""
    raw = STILL.read_bytes()
    apng = read_apng(raw)
    CARD.update(raw=raw, idat=apng["idat"], pixels=apng["default"])


def chunks(raw: bytes) -> list:
    """[(kind, data)], each chunk's CRC checked, nothing after IEND."""
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    out, at = [], 8
    while at < len(raw):
        length, kind = struct.unpack(">I4s", raw[at:at + 8])
        data = raw[at + 8:at + 8 + length]
        crc, = struct.unpack(">I", raw[at + 8 + length:at + 12 + length])
        if zlib.crc32(kind + data) & 0xFFFFFFFF != crc:
            raise ValueError("a bad CRC in %r" % kind)
        out.append((kind, data))
        at += 12 + length
        if kind == b"IEND":
            break
    if at != len(raw):
        raise ValueError("bytes after IEND")
    return out


def unfilter(data: bytes, width: int, height: int, channels: int = 3) -> bytes:
    """A frame's pixels from its inflated scanlines: every one of PNG's five filters."""
    stride, out, previous = width * channels, bytearray(), bytearray(width * channels)
    if len(data) != height * (stride + 1):
        raise ValueError("%d bytes of scanlines for %dx%d" % (len(data), width, height))
    for y in range(height):
        kind = data[y * (stride + 1)]
        line = bytearray(data[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if kind == 0:
            pass
        elif kind == 2:
            line = bytearray((value + up) & 0xFF for value, up in zip(line, previous))
        else:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = previous[i]
                c = previous[i - channels] if i >= channels else 0
                if kind == 1:
                    line[i] = (line[i] + a) & 0xFF
                elif kind == 3:
                    line[i] = (line[i] + (a + b) // 2) & 0xFF
                elif kind == 4:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
                else:
                    raise ValueError("filter %d" % kind)
        out += line
        previous = line
    return bytes(out)


def read_apng(raw: bytes, known=None) -> dict:
    """The picture's size, its plays, its default image and its frames: [{box, delay, dispose, blend, pixels}].

    `known` is (IDAT chunks, pixels) of a picture decoded before. When this one's IDAT chunks are those byte for
    byte, its default image is those pixels without decoding them again: equal compressed bytes inflate to equal
    scanlines, and equal scanlines unfilter to equal pixels. Likewise a frame whose data is the IDAT's own (frame 1,
    when its fcTL comes before the IDAT) at the picture's size is the default image."""
    parts = chunks(raw)
    width, height, depth, colour, _c, _f, interlace = struct.unpack(">IIBBBBB", dict(parts)[b"IHDR"])
    if (depth, colour, interlace) != (8, 2, 0):
        raise ValueError("not 8-bit RGB without interlace")
    frames, current, sequence, idat, plays, count = [], None, 0, bytearray(), None, None
    for kind, data in parts:
        if kind == b"acTL":
            count, plays = struct.unpack(">II", data)
        elif kind == b"fcTL":
            number, w, h, x, y, num, den, dispose, blend = struct.unpack(">IIIIIHHBB", data)
            if number != sequence:
                raise ValueError("fcTL out of sequence")
            sequence += 1
            current = {"box": (x, y, w, h), "delay": Fraction(num, den or 100), "dispose": dispose,
                       "blend": blend, "data": bytearray()}
            frames.append(current)
        elif kind == b"IDAT":
            idat += data
            if current is not None and len(frames) == 1:
                current["data"] += data
        elif kind == b"fdAT":
            number, = struct.unpack(">I", data[:4])
            if number != sequence:
                raise ValueError("fdAT out of sequence")
            sequence += 1
            current["data"] += data[4:]
    idats = [data for kind, data in parts if kind == b"IDAT"]
    if known is not None and known[0] == idats:
        default = known[1]
    else:
        default = unfilter(zlib.decompress(bytes(idat)), width, height)
    for frame in frames:
        _, _, w, h = frame["box"]
        data = bytes(frame.pop("data"))
        if data == idat and (w, h) == (width, height):
            frame["pixels"] = default
        else:
            frame["pixels"] = unfilter(zlib.decompress(data), w, h)
    if count is not None and count != len(frames):
        raise ValueError("acTL says %d frames, %d are there" % (count, len(frames)))
    return {"width": width, "height": height, "plays": plays, "default": default, "frames": frames,
            "idat": idats}


def composite(apng: dict, box=None):
    """Each frame's picture, RGB, as a viewer shows it: dispose 0 keeps the frame, 1 clears its rectangle,
    2 restores what was before it; an opaque frame's blend 'over' is its 'source'.

    With `box` (left, top, width, height) only that crop of each picture is made: frame 1 may cover more than the
    box (its part inside is drawn), but every later frame must lie inside it, or this raises - so outside the box
    every picture is frame 1's, and the crops hold everything that changes."""
    left, top, wide, tall = box or (0, 0, apng["width"], apng["height"])
    if left < 0 or top < 0 or left + wide > apng["width"] or top + tall > apng["height"]:
        raise ValueError("the box %r is not inside the picture" % (box,))
    canvas = bytearray(wide * tall * 3)
    for index, frame in enumerate(apng["frames"]):
        x, y, w, h = frame["box"]
        if index and not (x >= left and y >= top and x + w <= left + wide and y + h <= top + tall):
            raise ValueError("frame %d's rectangle %r is outside the box %r" % (index + 1, frame["box"], box))
        x0, y0, x1, y1 = max(x, left), max(y, top), min(x + w, left + wide), min(y + h, top + tall)
        before = bytes(canvas)
        for row in range(y0, y1):
            at, source = ((row - top) * wide + x0 - left) * 3, ((row - y) * w + x0 - x) * 3
            canvas[at:at + (x1 - x0) * 3] = frame["pixels"][source:source + (x1 - x0) * 3]
        yield bytes(canvas)
        if frame["dispose"] == 1:
            for row in range(y0, y1):
                at = ((row - top) * wide + x0 - left) * 3
                canvas[at:at + (x1 - x0) * 3] = bytes((x1 - x0) * 3)
        elif frame["dispose"] == 2:
            canvas[:] = before


def same(test, first, second, message="they differ"):
    """assertEqual for pictures: a failing assertEqual on megabytes of bytes, or lists of them, has unittest diff
    their reprs, which takes minutes; this says where they first differ instead."""
    if first == second:
        return
    if isinstance(first, (list, tuple)) and isinstance(second, (list, tuple)):
        if len(first) != len(second):
            test.fail("%s: %d items, not %d" % (message, len(first), len(second)))
        index = next(i for i, (one, other) in enumerate(zip(first, second)) if one != other)
        test.fail("%s: item %d of %d differs" % (message, index, len(first)))
    if len(first) != len(second):
        test.fail("%s: %d bytes, not %d" % (message, len(first), len(second)))
    index = next(i for i, (one, other) in enumerate(zip(first, second)) if one != other)
    test.fail("%s: first at byte %d of %d" % (message, index, len(first)))


def crop(picture: bytes, width: int, box: tuple) -> bytes:
    """The (left, top, width, height) rectangle of a picture `width` px wide."""
    left, top, wide, tall = box
    return b"".join(picture[((top + row) * width + left) * 3:((top + row) * width + left + wide) * 3]
                    for row in range(tall))


def still_png(width: int, height: int, rgb: bytes) -> bytes:
    """A still PNG written here with the Sub filter, so the writer's default image is not one it filtered."""
    rows = bytearray()
    for y in range(height):
        line = rgb[y * width * 3:(y + 1) * width * 3]
        rows.append(1)
        rows += bytes((line[i] - (line[i - 3] if i >= 3 else 0)) & 0xFF for i in range(len(line)))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b""))


class TheReaderReadsTheWriter(unittest.TestCase):
    """The reader and make_social.write_motion agree on pictures made up here - on a small card, so the pure-Python
    filters cost what its few pixels do: the writer takes its size from make_social.WIDTH and HEIGHT, the reader
    from the IHDR, and the committed motion is read at the card's own size below."""

    @mock.patch.object(make_social, "HEIGHT", 64)
    @mock.patch.object(make_social, "WIDTH", 96)
    def test_a_small_motion_round_trips_frame_by_frame(self):
        width, height = make_social.WIDTH, make_social.HEIGHT
        first = bytes((i // 3 % width + i // 3 // width + i % 3 * 40) % 256 for i in range(width * height * 3))
        second = bytearray(first)
        for x in range(40, 60):
            second[(30 * width + x) * 3:(30 * width + x) * 3 + 3] = b"\x10\x20\x30"
        third = bytearray(second)
        third[(5 * width + 7) * 3] = 255
        pictures = [(Fraction(31, 100), first), (Fraction(6, 100), bytes(second)),
                    (Fraction(12, 100), bytes(third)), (Fraction(1, 10), bytes(third))]
        still = still_png(width, height, first)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "small.png"
            count = make_social.write_motion(path, still, iter(pictures))
            apng = read_apng(path.read_bytes())
        self.assertEqual(count, 4)
        self.assertEqual(apng["plays"], 0, "an APNG that does not loop forever")
        same(self, apng["idat"], [data for kind, data in chunks(still) if kind == b"IDAT"],
                         "the default image is not the still PNG's own")
        same(self, apng["default"], first, "the default image")
        self.assertEqual([frame["delay"] for frame in apng["frames"]], [delay for delay, _ in pictures])
        same(self, list(composite(apng)), [picture for _, picture in pictures], "the pictures")
        self.assertEqual(apng["frames"][1]["box"], (40, 30, 20, 1), "a later frame is more than what changed")


class TheScheduleIsTheIcons(unittest.TestCase):
    """The frames, their moments and their heads come from the tray icon's own code."""

    def setUp(self):
        self.plan = make_social.schedule()

    def test_one_whole_cycle_of_watching(self):
        loop = make_social.watching_loop_ms()
        for at in (0.0, 1234.0, 15000.0, 17777.0):
            self.assertEqual(tray.icon_frame("watching", at), tray.icon_frame("watching", at + loop),
                             "watching_loop_ms is not watching's cycle")
        self.assertEqual(sum(delay for delay, _, _ in self.plan) * 10, int(round(loop)))

    def test_frame_one_is_the_mark_at_rest_at_full_brightness(self):
        self.assertEqual(self.plan[0][1:], (0, tray.ICON_MOTION["levels"] - 1))
        self.assertEqual(self.plan[0][1:], tray.icon_frame("watching", 0.0))

    def test_every_frame_is_the_one_the_icons_timer_shows_then(self):
        """Stepped here as the icon's timer steps - icon_frame_ms from the moment watching is entered - and each
        frame is the icon's frame on show when it starts, on the hundredth it starts."""
        loop, ticks, at = make_social.watching_loop_ms(), [], 0.0
        while at < loop:
            ticks.append((int(round(at / 10.0)), tray.icon_frame("watching", at, at)))
            at += tray.icon_frame_ms("watching", at, at)
        start = 0
        for delay, position, level in self.plan:
            shown = [frame for hundredth, frame in ticks if hundredth <= start][-1]
            self.assertEqual((position, level), shown, "the frame at %d0 ms is not the icon's" % start)
            self.assertGreaterEqual(delay, make_social.SHORTEST)
            start += delay

    def test_it_breathes_three_times_then_sweeps_out_and_back_without_breathing(self):
        top = tray.ICON_MOTION["levels"] - 1
        moving = [(position, level) for _, position, level in self.plan if position]
        self.assertTrue(moving, "the head never leaves its place")
        self.assertEqual({level for _, level in moving}, {top}, "the head breathes while it travels")
        far = max(position for position, _ in moving)
        self.assertEqual(far, int(round(tray.ICON_SWEEP / (360.0 / tray.ICON_MOTION["positions"]))))
        before = [level for _, position, level in self.plan[:[p for _, p, _ in self.plan].index(1)]]
        dips = sum(1 for one, other in zip(before, before[1:]) if one == top and other < top)
        self.assertEqual(dips, tray.ICON_MOTION["breaths"])

    def test_the_svg_head_at_rest_is_the_marks_own(self):
        svg = (ROOT / "assets" / "brand" / "icon.svg").read_text(encoding="utf-8")
        self.assertEqual(make_social.mark_svg(svg, 0, tray.ICON_MOTION["levels"] - 1), svg)
        self.assertIn("width:%dpx;height:%dpx" % (make_social.MARK_PX, make_social.MARK_PX), make_social.TEMPLATE)


class TheCommittedMotion(unittest.TestCase):
    """docs/images/social-preview-motion.png as committed."""

    @classmethod
    def setUpClass(cls):
        cls.raw = MOTION.read_bytes()
        cls.card = CARD["pixels"]
        cls.apng = read_apng(cls.raw, (CARD["idat"], cls.card))
        cls.plan = make_social.schedule()
        try:
            left, top, cls.head = make_social.mark_box(cls.card)
        except SystemExit as error:   # the builder's way to stop; here it is a failure, not the end of the run
            raise AssertionError("the card's mark is not found: %s" % error) from None
        cls.box = (left, top, make_social.cell_size(), make_social.cell_size())
        cls.card_crop = crop(cls.card, make_social.WIDTH, cls.box)
        try:
            cls.pictures, cls.outside = list(composite(cls.apng, cls.box)), None
        except ValueError as error:
            cls.pictures, cls.outside = [], str(error)

    def pixel(self, picture, x, y):
        """A picture's pixel at the card's (x, y): `picture` is the crop of the mark's box, outside which every
        picture is the card."""
        left, top, wide, tall = self.box
        x, y = int(x), int(y)
        if not (left <= x < left + wide and top <= y < top + tall):
            return tuple(self.card[(y * make_social.WIDTH + x) * 3:(y * make_social.WIDTH + x) * 3 + 3])
        at = ((y - top) * wide + x - left) * 3
        return tuple(picture[at:at + 3])

    def test_every_later_frame_lies_in_the_marks_box(self):
        """So outside the box every picture is frame 1, and comparing the box's crops compares the pictures."""
        self.assertIsNone(self.outside)

    def test_it_is_under_githubs_megabyte(self):
        self.assertLess(len(self.raw), make_social.MOTION_LIMIT)

    def test_it_is_the_cards_size_and_loops_forever(self):
        self.assertEqual((self.apng["width"], self.apng["height"]), (make_social.WIDTH, make_social.HEIGHT))
        self.assertEqual(self.apng["plays"], 0)

    def test_its_default_image_and_frame_one_are_the_still_card_exactly(self):
        same(self, self.apng["idat"], [data for kind, data in chunks(CARD["raw"]) if kind == b"IDAT"],
             "the IDAT chunks are not the still's")
        same(self, self.apng["default"], self.card, "a viewer without APNG does not show the card")
        self.assertEqual(self.apng["frames"][0]["box"], (0, 0, make_social.WIDTH, make_social.HEIGHT))
        same(self, self.apng["frames"][0]["pixels"], self.card, "frame 1 is not the card")
        self.assertIsNone(self.outside)
        same(self, self.pictures[0], self.card_crop, "frame 1's mark is not the card's")
        same(self, self.pictures[-1], self.card_crop, "the cycle does not end on the card it starts with")

    def test_its_frames_and_delays_are_the_schedules(self):
        self.assertEqual(len(self.apng["frames"]), len(self.plan))
        self.assertEqual([frame["delay"] for frame in self.apng["frames"]],
                         [Fraction(delay, 100) for delay, _, _ in self.plan])
        self.assertEqual(sum(frame["delay"] for frame in self.apng["frames"]),
                         Fraction(int(round(make_social.watching_loop_ms())), 1000))

    def test_only_the_heads_rectangle_changes_after_frame_one(self):
        """Every later frame keeps the frame before and draws a rectangle inside the mark: the text, the rule, the
        tags and the ground never change."""
        rest = brand.icon_head_centre()
        scale = make_social.MARK_PX / 2.0
        left = self.head[0] - (1 + rest[0]) * scale
        top = self.head[1] - (1 - rest[1]) * scale
        for frame in self.apng["frames"][1:]:
            x, y, w, h = frame["box"]
            self.assertEqual(frame["dispose"], 0)
            self.assertGreaterEqual(x, left)
            self.assertGreaterEqual(y, top)
            self.assertLessEqual(x + w, left + make_social.MARK_PX)
            self.assertLessEqual(y + h, top + make_social.MARK_PX)

    def test_the_head_is_where_and_what_the_icons_is_in_every_frame(self):
        """The head's centre in each frame is the icon's head for that frame - the accent where it travels, the
        breath's tint where it breathes in its place - and home is not lit while the head is away."""
        rest = brand.icon_head_centre()
        scale = make_social.MARK_PX / 2.0
        accent = tuple(brand.rgb(brand.ICON_ACCENT))
        self.assertIsNone(self.outside)
        self.assertEqual(len(self.pictures), len(self.plan))
        for (_, position, level), picture in zip(self.plan, self.pictures):
            there = brand.icon_head_centre(brand.ICON_SHAPE["arc_end"]
                                           - 360.0 * position / tray.ICON_MOTION["positions"])
            x = self.head[0] + (there[0] - rest[0]) * scale
            y = self.head[1] - (there[1] - rest[1]) * scale
            want = tuple(tray.icon_level_colour(tray.icon_head_colour("watching"), level))
            self.assertEqual(self.pixel(picture, x, y), want, "the head at %d, level %d" % (position, level))
            if position >= 4:
                self.assertNotEqual(self.pixel(picture, *self.head), accent, "home is lit while the head is away")


if __name__ == "__main__":
    unittest.main()
