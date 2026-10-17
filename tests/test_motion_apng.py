"""The README motion's APNG writer (build/motion_apng.py), read back with the reader test_social_motion wrote from the
PNG and APNG specifications - sharing no code with any writer - on synthetic frames: every frame comes back pixel for
pixel, the same frames make the same bytes, a frame no browser shows is refused, the budget's cap refuses to write
and names what each scene cost, and frame 1 is a given still chunk for chunk."""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import motion_apng  # noqa: E402
from test_social_motion import chunks, composite, read_apng  # noqa: E402

WIDTH, HEIGHT = 40, 30
GROUND = (238, 240, 243)


def picture(square_x=None, fade=None) -> bytes:
    """The ground, a 6 px square at `square_x`, and a card-like rectangle `fade` of the way to dark."""
    out = bytearray(bytes(GROUND) * (WIDTH * HEIGHT))
    if square_x is not None:
        for y in range(4, 10):
            for x in range(square_x, square_x + 6):
                out[(y * WIDTH + x) * 3:(y * WIDTH + x) * 3 + 3] = bytes((20, 90, 200))
    if fade is not None:
        for y in range(18, 27):
            for x in range(5, 35):
                out[(y * WIDTH + x) * 3:(y * WIDTH + x) * 3 + 3] = bytes(int(c * (1 - fade)) for c in GROUND)
    return bytes(out)


def frames():
    """(delay, scene, picture): a square crossing, a held frame repeated, a rectangle fading in."""
    out = [(400, "S0", picture())]
    out += [(16, "S1", picture(x)) for x in range(0, 30, 6)]
    out += [(100, "S2", picture(27)), (100, "S2", picture(27))]
    out += [(33, "S3", picture(27, fade)) for fade in (0.25, 0.5, 0.75)]
    return out


def png(rgb: bytes, width: int, height: int, level: int) -> bytes:
    rows = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + motion_apng.chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + motion_apng.chunk(b"IDAT", zlib.compress(rows, level)) + motion_apng.chunk(b"IEND", b""))


class AssembleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "motion.png"

    def write(self, given=None, **budget):
        return motion_apng.assemble(self.path, WIDTH, HEIGHT, iter(given or frames()), **budget)

    def test_every_frame_comes_back_pixel_for_pixel_and_a_repeat_only_lengthens_its_frame(self):
        report = self.write()
        apng = read_apng(self.path.read_bytes())
        self.assertEqual(apng["plays"], 0, "it loops forever")
        shown = list(composite(apng))
        unique = [item for index, item in enumerate(frames()) if index == 0 or item[2] != frames()[index - 1][2]]
        self.assertEqual(len(shown), len(unique))
        for index, (got, (_delay, _scene, want)) in enumerate(zip(shown, unique)):
            self.assertTrue(got == want, "frame %d differs" % (index + 1))
        delays = [frame["delay"] for frame in apng["frames"]]
        self.assertEqual(sum(delays), Fraction(sum(delay for delay, _scene, _picture in frames()), 1000))
        self.assertEqual(delays[6], Fraction(1, 5), "the repeated frame is one frame held for both")
        self.assertEqual(delays[1], Fraction(16, 1000), "a 16 ms step is written exactly")
        self.assertEqual((report.frames, report.ms, report.size), (len(unique), 779, self.path.stat().st_size))
        self.assertTrue(all(frame["box"][2] * frame["box"][3] < WIDTH * HEIGHT for frame in apng["frames"][1:]),
                        "a later frame is only what changed")

    def test_the_same_frames_make_the_same_bytes(self):
        self.write()
        once = self.path.read_bytes()
        self.path.unlink()
        self.write()
        self.assertEqual(self.path.read_bytes(), once)

    def test_a_frame_no_browser_shows_is_refused(self):
        with self.assertRaises(ValueError):
            self.write([(40, "A", picture()), (10, "B", picture(3))])

    def test_over_the_cap_nothing_is_written_and_each_scene_s_bytes_are_named(self):
        size = self.write().size
        self.path.unlink()
        with self.assertRaises(motion_apng.BudgetExceeded) as caught:
            self.write(cap=size - 1)
        self.assertFalse(self.path.exists())
        self.assertEqual(sorted(caught.exception.scenes), ["S0", "S1", "S2", "S3"])
        self.assertEqual(sum(caught.exception.scenes.values()) + 8 + 25 + 20 + 38 + 12, size,
                         "every byte but the signature, header, acTL, first fcTL and IEND is a scene's")
        self.assertIn("over the cap", str(caught.exception))
        self.assertTrue(self.write(target=size - 1, cap=size).over_target)
        self.assertFalse(self.write(target=size, cap=size).over_target)

    def test_frame_one_is_the_still_chunk_for_chunk(self):
        still = png(frames()[0][2], WIDTH, HEIGHT, 1)
        self.write(still=still)
        written = chunks(self.path.read_bytes())
        self.assertEqual([data for kind, data in written if kind == b"IDAT"],
                         [data for kind, data in chunks(still) if kind == b"IDAT"])
        with self.assertRaises(ValueError):
            self.write(still=png(picture(3), WIDTH, HEIGHT, 1))


class SplitTests(unittest.TestCase):
    def test_changes_far_apart_are_two_small_rectangles_and_the_picture_comes_out_whole(self):
        tall = 200
        ground = bytes(GROUND) * (WIDTH * tall)

        def lit(top_colour, bottom_colour):
            out = bytearray(ground)
            out[(3 * WIDTH + 2) * 3:(3 * WIDTH + 2) * 3 + 3] = bytes(top_colour)
            out[(190 * WIDTH + 30) * 3:(190 * WIDTH + 30) * 3 + 3] = bytes(bottom_colour)
            return bytes(out)
        given = [(100, "A", lit((1, 1, 1), (2, 2, 2))), (100, "B", lit((9, 9, 9), (8, 8, 8))),
                 (20, "C", lit((5, 5, 5), (6, 6, 6)))]
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "split.png"
            report = motion_apng.assemble(path, WIDTH, tall, iter(given))
            apng = read_apng(path.read_bytes())
        boxes = [frame["box"] for frame in apng["frames"]]
        self.assertEqual(boxes[1:3], [(2, 3, 1, 1), (30, 190, 1, 1)], "two rectangles, not one round both")
        self.assertEqual([frame["delay"] for frame in apng["frames"]][1:3], [Fraction(15, 1000), Fraction(85, 1000)])
        self.assertEqual(boxes[3], (2, 3, 29, 188), "too short a frame to split is one rectangle")
        shown = list(composite(apng))
        self.assertTrue(shown[2] == given[1][2] and shown[3] == given[2][2])
        self.assertEqual(report.ms, 220)


class AlphaTests(unittest.TestCase):
    """A picture on a clear ground: RGBA, and every later rectangle replaces what was under it."""

    @staticmethod
    def rgba(alpha_of_square):
        out = bytearray(WIDTH * HEIGHT * 4)
        for y in range(4, 10):
            for x in range(6, 12):
                out[(y * WIDTH + x) * 4:(y * WIDTH + x) * 4 + 4] = bytes((20, 90, 200, alpha_of_square))
        return bytes(out)

    def read(self, raw):
        from test_social_motion import unfilter
        parts = chunks(raw)
        width, height, depth, colour = struct.unpack(">IIBB", dict(parts)[b"IHDR"][:10])
        self.assertEqual((depth, colour), (8, 6), "8-bit RGBA")
        frames, current = [], None
        for kind, data in parts:
            if kind == b"fcTL":
                current = {"control": struct.unpack(">IIIIIHHBB", data), "data": bytearray()}
                frames.append(current)
            elif kind == b"IDAT":
                current["data"] += data
            elif kind == b"fdAT":
                current["data"] += data[4:]
        canvas, shown = bytearray(width * height * 4), []
        for frame in frames:
            _n, w, h, x, y, _num, _den, dispose, blend = frame["control"]
            self.assertEqual((dispose, blend), (0, 0), "kept, and laid as the source, never over")
            pixels = unfilter(zlib.decompress(bytes(frame["data"])), w, h, 4)
            for row in range(h):
                at = ((y + row) * width + x) * 4
                canvas[at:at + w * 4] = pixels[row * w * 4:(row + 1) * w * 4]
            shown.append(bytes(canvas))
        return shown

    def test_a_fading_square_fades_to_clear_and_not_to_the_frame_before(self):
        given = [(100, "A", self.rgba(255)), (100, "B", self.rgba(128)), (100, "C", self.rgba(0))]
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "clear.png"
            report = motion_apng.assemble(path, WIDTH, HEIGHT, iter(given), alpha=True)
            shown = self.read(path.read_bytes())
            again = Path(name) / "again.png"
            motion_apng.assemble(again, WIDTH, HEIGHT, iter(given), alpha=True)
            self.assertEqual(again.read_bytes(), path.read_bytes())
        self.assertEqual(shown, [picture for _delay, _scene, picture in given])
        self.assertEqual(report.frames, 3)

    def test_an_rgb_picture_is_refused_where_rgba_is_asked(self):
        with tempfile.TemporaryDirectory() as name, self.assertRaises(ValueError):
            motion_apng.assemble(Path(name) / "x.png", WIDTH, HEIGHT, iter([(100, "A", picture())]), alpha=True)


class CutTests(unittest.TestCase):
    def test_changes_side_by_side_are_cut_apart_by_the_columns_between_them(self):
        width, height = 200, 40
        before = bytes(bytes(GROUND) * (width * height))
        after = bytearray(before)
        for x, y in ((5, 10), (6, 30), (150, 12), (160, 20)):
            after[(y * width + x) * 3] = 0
        boxes = motion_apng.patches(before, bytes(after), width, height)
        self.assertEqual(sorted(boxes), [(5, 10, 2, 21), (150, 12, 11, 9)])
        self.assertEqual(motion_apng.patches(before, before, width, height), [])

    def test_a_frame_too_short_for_every_rectangle_joins_the_two_nearest(self):
        width, height = 200, 200
        before = bytes(bytes(GROUND) * (width * height))
        after = bytearray(before)
        for x, y in ((5, 5), (190, 190), (150, 185)):
            after[(y * width + x) * 3] = 0
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "short.png"
            motion_apng.assemble(path, width, height, iter([(40, "A", before), (40, "B", bytes(after))]))
            boxes = [frame["box"] for frame in read_apng(path.read_bytes())["frames"]][1:]
        self.assertEqual(sorted(boxes), [(5, 5, 1, 1), (150, 185, 41, 6)],
                         "the two far corners would have made one rectangle of the whole picture")


class ChangedTests(unittest.TestCase):
    def test_the_rectangle_is_the_smallest_that_holds_every_change(self):
        generator = random.Random(7)
        for _ in range(60):
            width, height = generator.randint(1, 30), generator.randint(1, 12)
            before = bytes(generator.randrange(4) for _ in range(width * height * 3))
            after = bytearray(before)
            for _ in range(generator.randint(0, 5)):
                at = generator.randrange(width * height * 3)
                after[at] = (after[at] + 1) % 256
            after = bytes(after)
            changed = [(i // 3 % width, i // 3 // width) for i in range(len(before)) if before[i] != after[i]]
            want = None if not changed else (min(x for x, _ in changed), min(y for _, y in changed),
                                             max(x for x, _ in changed) - min(x for x, _ in changed) + 1,
                                             max(y for _, y in changed) - min(y for _, y in changed) + 1)
            self.assertEqual(motion_apng.changed(before, after, width, height), want)


if __name__ == "__main__":
    unittest.main()
