"""The social preview's GIF: one cycle of the watching icon's motion on the card, small enough for GitHub.

build/make_social.py writes docs/images/social-preview.gif with the encoder the README's GIFs use
(make_screenshots.write_gif) and the icon's own timer (make_screenshots.icon_timeline). These tests decode
what it wrote with a decoder of their own, written from the GIF89a specification and sharing no code with
the encoder, and hold it to what the owner asked: the mark moving as the real icon moves, looping forever,
under 1 MB, frame 1 the card as it is.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "build"))

import make_social        # noqa: E402
import make_screenshots   # noqa: E402
from codex_auto_resume import brand     # noqa: E402
from codex_auto_resume.ui import tray   # noqa: E402

GIF = ROOT / "docs" / "images" / "social-preview.gif"


def _lzw_decode(data: bytes, minimum: int, count: int) -> bytes:
    """GIF's LZW, codes least significant bit first, the table growing to 12 bits and cleared by the clear code."""
    clear, stop = 1 << minimum, (1 << minimum) + 1
    out = bytearray()
    size, table, previous = minimum + 1, None, None
    bits, held, at = 0, 0, 0

    def reset():
        return [bytes((value,)) for value in range(clear)] + [b"", b""]

    table = reset()
    while True:
        while held < size:
            if at >= len(data):
                return bytes(out[:count])
            bits |= data[at] << held
            held += 8
            at += 1
        code = bits & ((1 << size) - 1)
        bits >>= size
        held -= size
        if code == clear:
            table, size, previous = reset(), minimum + 1, None
            continue
        if code == stop:
            break
        if code < len(table):
            entry = table[code]
            if previous is not None:
                table.append(previous + entry[:1])
        elif code == len(table) and previous is not None:
            entry = previous + previous[:1]
            table.append(entry)
        else:
            raise ValueError("an LZW code out of the table: %d" % code)
        out += entry
        previous = entry
        if len(table) == (1 << size) and size < 12:
            size += 1
    return bytes(out[:count])


def decode(raw: bytes) -> dict:
    """The GIF's screen, global palette, loop count and frames: [{delay, disposal, transparent, box, indices}]."""
    if raw[:6] != b"GIF89a":
        raise ValueError("not a GIF89a")
    width, height, packed, _background, _aspect = struct.unpack("<HHBBB", raw[6:13])
    at, palette = 13, []
    if packed & 0x80:
        entries = 2 << (packed & 0x07)
        palette = [tuple(raw[at + 3 * i:at + 3 * i + 3]) for i in range(entries)]
        at += 3 * entries
    loops, frames, control = None, [], {}

    def blocks(at):
        body = bytearray()
        while raw[at]:
            body += raw[at + 1:at + 1 + raw[at]]
            at += 1 + raw[at]
        return bytes(body), at + 1

    while True:
        kind = raw[at]
        if kind == 0x3B:
            at += 1
            break
        if kind == 0x21:
            label = raw[at + 1]
            if label == 0xF9:
                size = raw[at + 2]
                flags, delay, transparent = struct.unpack("<BHB", raw[at + 3:at + 3 + size])
                control = {"delay": delay, "disposal": (flags >> 2) & 0x07,
                           "transparent": transparent if flags & 0x01 else None}
                at += 3 + size
                if raw[at] != 0:
                    raise ValueError("a graphic control extension without its terminator")
                at += 1
            elif label == 0xFF:
                size = raw[at + 2]
                name = raw[at + 3:at + 3 + size]
                body, at = blocks(at + 3 + size)
                if name == b"NETSCAPE2.0" and body[:1] == b"\x01":
                    loops = struct.unpack("<H", body[1:3])[0]
            else:
                _body, at = blocks(at + 2)
        elif kind == 0x2C:
            left, top, w, h, flags = struct.unpack("<HHHHB", raw[at + 1:at + 10])
            at += 10
            if flags & 0x80:
                at += 3 * (2 << (flags & 0x07))
            if flags & 0x40:
                raise ValueError("an interlaced frame")
            minimum = raw[at]
            data, at = blocks(at + 1)
            frames.append(dict(control, box=(left, top, w, h), indices=_lzw_decode(data, minimum, w * h)))
            control = {}
        else:
            raise ValueError("an unknown block 0x%02X at %d" % (kind, at))
    return {"width": width, "height": height, "palette": palette, "loops": loops, "frames": frames,
            "trailing": len(raw) - at}


def canvases(gif: dict):
    """Each frame's whole picture, as palette indices: a frame's transparent index keeps what is there."""
    width, height = gif["width"], gif["height"]
    canvas = bytearray(width * height)
    for frame in gif["frames"]:
        left, top, w, h = frame["box"]
        indices, clear = frame["indices"], frame["transparent"]
        for y in range(h):
            row = indices[y * w:(y + 1) * w]
            start = (top + y) * width + left
            if clear is None:
                canvas[start:start + w] = row
            else:
                for x, index in enumerate(row):
                    if index != clear:
                        canvas[start + x] = index
        yield bytes(canvas)


class TheDecoderReadsTheEncoder(unittest.TestCase):
    """The decoder and the encoder agree on pictures made up here, so what the GIF tests read is what was written."""

    def test_a_small_animation_round_trips_frame_by_frame(self):
        width, height = 23, 9
        palette = [(index, 255 - index, (index * 7) % 256) for index in range(40)]
        first = bytes((x * 3 + y * 5) % 40 for y in range(height) for x in range(width))
        second = bytearray(first)
        for x in range(4, 9):
            second[3 * width + x] = 39
        third = bytearray(second)
        third[8 * width + 22] = 1
        frames = [(31, first), (6, bytes(second)), (12, bytes(third)), (6, bytes(third))]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "small.gif"
            make_screenshots.write_gif(path, width, height, palette, frames)
            gif = decode(path.read_bytes())
        self.assertEqual((gif["width"], gif["height"]), (width, height))
        self.assertEqual(gif["palette"][:40], palette)
        self.assertEqual(gif["loops"], 0, "a GIF that does not loop forever")
        self.assertEqual(gif["trailing"], 0)
        self.assertEqual([frame["delay"] for frame in gif["frames"]], [31, 6, 12, 6])
        self.assertEqual(list(canvases(gif)), [first, bytes(second), bytes(third), bytes(third)])
        self.assertEqual(gif["frames"][0]["box"], (0, 0, width, height), "frame 1 is not written whole")
        self.assertEqual(gif["frames"][1]["box"], (4, 3, 4, 1), "a later frame is more than what changed")

    def test_a_long_run_passes_the_twelve_bit_table(self):
        width, height = 300, 40
        palette = [(index, index, index) for index in range(200)]
        picture = bytes((x * x + y * 31 + x * y) % 200 for y in range(height) for x in range(width))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long.gif"
            make_screenshots.write_gif(path, width, height, palette, [(5, picture)])
            gif = decode(path.read_bytes())
        self.assertEqual(next(canvases(gif)), picture)


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
        """Stepped here as the icon's timer steps - icon_frame_ms from the moment watching is entered - and each GIF
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
        self.assertIn('width:%dpx;height:%dpx' % (make_social.MARK_PX, make_social.MARK_PX), make_social.TEMPLATE)


class TheCommittedGif(unittest.TestCase):
    """docs/images/social-preview.gif as committed."""

    @classmethod
    def setUpClass(cls):
        cls.raw = GIF.read_bytes()
        cls.gif = decode(cls.raw)
        cls.plan = make_social.schedule()

    def test_it_is_under_githubs_megabyte(self):
        self.assertLess(len(self.raw), make_social.MOTION_LIMIT)

    def test_it_is_the_cards_size_and_loops_forever(self):
        self.assertEqual((self.gif["width"], self.gif["height"]), (make_social.WIDTH, make_social.HEIGHT))
        self.assertEqual(self.gif["loops"], 0)
        self.assertEqual(self.gif["trailing"], 0)

    def test_its_frames_are_the_schedules(self):
        self.assertEqual([frame["delay"] for frame in self.gif["frames"]], [delay for delay, _, _ in self.plan])
        self.assertEqual(sum(frame["delay"] for frame in self.gif["frames"]) * 10,
                         int(round(make_social.watching_loop_ms())))

    def test_only_the_marks_area_changes_after_frame_one(self):
        first = self.gif["frames"][0]
        self.assertEqual(first["box"], (0, 0, make_social.WIDTH, make_social.HEIGHT))
        self.assertIsNone(first["transparent"])
        side = make_social.MARK_PX
        for frame in self.gif["frames"][1:]:
            left, top, w, h = frame["box"]
            self.assertLessEqual(w, side)
            self.assertLessEqual(h, side)
            self.assertIsNotNone(frame["transparent"])

    def test_frame_one_is_the_card(self):
        """The card's PNG in 255 colours, dithered: about a level off on average, and the colours the card is drawn
        in - the text's white, the head's accent - exact."""
        _, _, card = make_screenshots.read_png_rgb(make_social.TARGET)
        first = next(canvases(self.gif))
        palette = self.gif["palette"]
        total = sum(max(abs(one - other) for one, other in zip(palette[first[at]], card[at * 3:at * 3 + 3]))
                    for at in range(0, len(first), 7))
        self.assertLess(total / float(len(range(0, len(first), 7))), 2.0, "frame 1 is not the card's picture")
        _, _, (x, y) = make_social.mark_box(card)
        accent = brand.rgb(brand.ICON_ACCENT)
        self.assertEqual(palette[first[int(y) * make_social.WIDTH + int(x)]], accent, "frame 1's head is not at rest")
        self.assertIn((255, 255, 255), palette)

    def test_the_head_travels_in_the_gif_and_comes_home(self):
        _, _, card = make_screenshots.read_png_rgb(make_social.TARGET)
        _, _, head = make_social.mark_box(card)
        accent = brand.rgb(brand.ICON_ACCENT)
        far = max(position for _, position, _ in self.plan)
        rest = brand.icon_head_centre()
        there = brand.icon_head_centre(brand.ICON_SHAPE["arc_end"] - 360.0 * far / tray.ICON_MOTION["positions"])
        scale = make_social.MARK_PX / 2.0
        away = (int(head[0] + (there[0] - rest[0]) * scale), int(head[1] - (there[1] - rest[1]) * scale))
        palette, seen = self.gif["palette"], []
        for (_, position, _), canvas in zip(self.plan, canvases(self.gif)):
            if position == far:
                seen.append(palette[canvas[away[1] * make_social.WIDTH + away[0]]])
                self.assertNotEqual(palette[canvas[int(head[1]) * make_social.WIDTH + int(head[0])]], accent,
                                    "the head is still home while it is away")
        self.assertTrue(seen and all(colour == accent for colour in seen), "the head is not where the icon's is")
        last = list(canvases(self.gif))[-1]
        self.assertEqual(last, next(canvases(self.gif)), "the cycle does not end on the card it starts with")


if __name__ == "__main__":
    unittest.main()
