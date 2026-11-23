"""A cut is one frame (v0.6.26, audit-apng M1).

A plan's `set` changes what the product paints in one go: the window reopened in another language, a refresh's
snapshot, a page of the setup window. build/motion_apng.py used to cut any frame whose changes lay far apart into
rectangles 15 ms apart, so a viewer saw states the product never shows (Korean words under an English header, "paused"
beside "on"). These hold that a frame marked whole is written as the one rectangle round its changes, that what moves by
itself between cuts (a light, the icon, the pointer) is still cut apart, and that the runners mark exactly the cuts.
Pure Python, synthetic pictures: nothing is drawn by a window."""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import make_motion  # noqa: E402
import motion_apng  # noqa: E402
import motion_plan  # noqa: E402
from test_social_motion import composite, read_apng  # noqa: E402

WIDTH, HEIGHT = 120, 120


def picture(top=False, bottom=False) -> bytes:
    """A grey ground with a mark at the top left and one at the bottom right, each far from the other."""
    out = bytearray(b"\xee" * (WIDTH * HEIGHT * 3))
    for on, (x0, y0) in ((top, (2, 2)), (bottom, (110, 110))):
        if on:
            for y in range(y0, y0 + 6):
                for x in range(x0, x0 + 6):
                    out[(y * WIDTH + x) * 3:(y * WIDTH + x) * 3 + 3] = b"\x10\x50\xc0"
    return bytes(out)


def boxes(path: Path) -> list:
    """(width, height, left, top) of every frame control after the first, in order."""
    raw, at, found = path.read_bytes(), 8, []
    while at < len(raw):
        length, kind = struct.unpack(">I4s", raw[at:at + 8])
        if kind == b"fcTL":
            found.append(struct.unpack(">IIII", raw[at + 12:at + 28]))
        at += 12 + length
    return found[1:]


class WholeFrameTests(unittest.TestCase):
    def write(self, frames):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "cut.png"
        report = motion_apng.assemble(path, WIDTH, HEIGHT, iter(frames))
        return path, report

    def test_a_cut_is_one_rectangle_round_all_it_changes(self):
        path, report = self.write([(100, "A", picture()), (200, "B", picture(True, True), True)])
        self.assertEqual(report.frames, 2, "the cut is one frame, not a piece shown 15 ms before the rest")
        self.assertEqual(boxes(path), [(114, 114, 2, 2)])
        shown = list(composite(read_apng(path.read_bytes())))
        self.assertTrue(shown[-1] == picture(True, True), "the cut comes back whole")
        self.assertEqual(report.ms, 300)

    def test_what_moves_by_itself_is_still_cut_apart(self):
        path, report = self.write([(100, "A", picture()), (200, "B", picture(True, True), False)])
        self.assertEqual(report.frames, 3)
        self.assertEqual(sorted(boxes(path)), [(6, 6, 2, 2), (6, 6, 110, 110)])
        path, report = self.write([(100, "A", picture()), (200, "B", picture(True, True))])
        self.assertEqual(report.frames, 3, "a frame that says nothing is cut apart as before")


def plan_of(*steps, **extra) -> dict:
    plan = dict({"format": motion_plan.FORMAT, "name": "test", "locale": "en", "pointer": {"rest": [10, 20]},
                 "scenes": [{"id": "A", "steps": list(steps)}]}, **extra)
    motion_plan.check(plan)
    return plan


class CutTests(unittest.TestCase):
    def test_a_set_is_a_cut_and_the_light_and_the_pointer_are_not(self):
        plan = plan_of({"hold": 100}, {"move": {"at": [50, 60]}, "frames": 3, "step": 20},
                       {"set": {"page": "pending"}, "hold": 200}, light_step_ms=33)
        frames, _held, _end = make_motion.schedule(plan)
        cuts = {frame.t: motion_plan.is_cut(before, frame)
                for before, frame in zip([None] + frames[:-1], frames)}
        self.assertTrue(cuts[0], "the first frame is whole")
        self.assertTrue(cuts[160], "the page shown")
        self.assertFalse(cuts[100], "the pointer setting off")
        self.assertFalse(cuts[120], "the pointer on its way")
        self.assertFalse(any(cuts[at] for at in cuts if at not in (0, 160)), cuts)

    def test_the_runner_says_which_pictures_are_cuts(self):
        plan = plan_of({"hold": 100}, {"set": {"page": "pending"}, "hold": 100}, light_step_ms=33)
        drawn = list(make_motion.run(plan, lambda frame: (motion_plan.thawed(frame.window)["page"] + str(frame.t)).encode()))
        self.assertEqual([(picture.decode(), whole) for _delay, _scene, picture, whole in drawn],
                         [("overview0", True), ("overview33", False), ("overview66", False), ("pending100", True),
                          ("pending132", False), ("pending165", False)])

    def test_the_popup_its_card_and_the_notification_card_changing_are_cuts(self):
        frame = motion_plan.Frame(0, "A", (), (), ("at", "x"), ())
        self.assertTrue(motion_plan.is_cut(frame, frame._replace(popup=(("opened", 0),))))
        self.assertTrue(motion_plan.is_cut(frame, frame._replace(tip=(("born", 0),))))
        self.assertTrue(motion_plan.is_cut(frame, frame._replace(card=(("born", 0),))))
        self.assertFalse(motion_plan.is_cut(frame, frame._replace(t=16, pointer=("at", "y"), ripple=("y", 0))))


if __name__ == "__main__":
    unittest.main()
