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
    out = [(40, "S0", picture())]
    out += [(4, "S1", picture(x)) for x in range(0, 30, 6)]
    out += [(10, "S2", picture(27)), (10, "S2", picture(27))]
    out += [(4, "S3", picture(27, fade)) for fade in (0.25, 0.5, 0.75)]
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
        self.assertEqual(sum(delays), Fraction(sum(delay for delay, _scene, _picture in frames()), 100))
        self.assertEqual(delays[6], Fraction(1, 5), "the repeated frame is one frame held for both")
        self.assertEqual((report.frames, report.hundredths, report.size), (len(unique), 92, self.path.stat().st_size))
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
            self.write([(4, "A", picture()), (1, "B", picture(3))])

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
