"""The render mode draws the fades and the answer the plans now ask for (v0.6.26, audit-apng M3, M4, M5, M7): one small
job of the real window, offscreen, never on the screen - the row menu part way in, at rest and part way out, Retry now's
answer, the Timeline part way in over a veil part way in, and the Interface language list part way in, open and part
way out, the drop-down looking open while it is. Nothing is captured; the frames are compared with each other."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import motion_window  # noqa: E402

PENDING = {"locale": "en", "page": "pending", "light": 0, "selected": {"pending": 0}}
SETTINGS = {"locale": "en", "page": "settings", "section": "general", "light": 0}
LIST = {"field": "interface_language", "hover": None}


@unittest.skipUnless(os.name == "nt" and motion_window.CSC.is_file(), "the window is built with Windows' C# compiler")
class FadeRenderTests(unittest.TestCase):
    FRAMES = [
        dict(PENDING),                                                                   # 0 at rest
        dict(PENDING, menu={"at": "task.0", "appear_ms": 75}),                           # 1 menu part way in
        dict(PENDING, menu={"at": "task.0"}),                                            # 2 menu at rest
        dict(PENDING, menu={"at": "task.0", "close_ms": 30}),                            # 3 menu part way out
        dict(PENDING),                                                                   # 4 closed
        dict(PENDING, answered="retry-now"),                                             # 5 Retry now answered
        dict(PENDING, answered="retry-now", dialog={"kind": "timeline", "appear_ms": 60}),  # 6 dialog part way in
        dict(PENDING, answered="retry-now", dialog={"kind": "timeline"}),                # 7 dialog at rest
        dict(SETTINGS),                                                                  # 8 settings at rest
        dict(SETTINGS, droplist=dict(LIST, appear_ms=75)),                               # 9 list part way in
        dict(SETTINGS, droplist=dict(LIST)),                                             # 10 list open
        dict(SETTINGS, droplist=dict(LIST, close_ms=30)),                                # 11 list part way out
        dict(SETTINGS),                                                                  # 12 closed
    ]

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = motion_window.compile_window(work)
        job = {"out": str(work / "out"), "theme": "light", "design": "soft",
               "forms": {"en": {"answers": motion_window.answers("en")}},
               "targets": ["task.0", "menu.0", "dialog.window", "setting.interface_language", "row.en"],
               "frames": [dict(frame, index=index) for index, frame in enumerate(cls.FRAMES)]}
        cls.result = motion_window.render(exe, job, work)
        cls.pictures = list(motion_window.pictures(cls.result, work / "out"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def picture(self, index):
        return self.pictures[index][1]

    def pixel(self, index, x, y):
        width = self.result["client"][0]
        at = (int(y) * width + int(x)) * 3
        return self.picture(index)[at:at + 3]

    def level(self, index, box):
        """The mean of every channel of frame `index` over `box` (left, top, width, height)."""
        width = self.result["client"][0]
        x, y, wide, tall = (int(value) for value in box)
        total = 0
        for row in range(y, y + tall):
            total += sum(self.picture(index)[(row * width + x) * 3:(row * width + x + wide) * 3])
        return total / float(wide * tall * 3)

    def between(self, index, rest, full, box):
        """Whether frame `index` over `box` stands strictly between frames `rest` and `full` there, on average: a card
        part way through its fade."""
        part, low, high = self.level(index, box), self.level(rest, box), self.level(full, box)
        return abs(high - low) > 1 and min(low, high) + 0.2 < part < max(low, high) - 0.2

    def test_every_frame_was_drawn_and_every_read_answered(self):
        self.assertEqual(self.result["notes"], [])
        self.assertEqual(self.result["misses"], [])
        self.assertEqual(len(self.pictures), len(self.FRAMES))

    def test_the_row_menu_fades_in_and_out(self):
        item = self.pictures[2][2]["menu.0"]
        self.assertTrue(self.between(1, 0, 2, item), "part way in is part way between")
        self.assertTrue(self.between(3, 4, 2, item), "part way out is part way between")
        self.assertEqual(self.picture(4), self.picture(0), "gone")

    def test_retry_now_s_answer_writes_its_note(self):
        self.assertNotEqual(self.picture(5), self.picture(4), "the note under the list")

    def test_the_dialog_and_its_veil_fade_in_together(self):
        window = self.pictures[7][2]["dialog.window"]
        # Part way in, over a veil part way in: neither the window as it was nor the dialog at rest (darker than both
        # where a clear dialog shows the window veiled under it).
        levels = [self.level(index, window) for index in (5, 6, 7)]
        self.assertTrue(abs(levels[1] - levels[0]) > 0.5 and abs(levels[1] - levels[2]) > 0.5, levels)
        self.assertTrue(self.between(6, 5, 7, (2, 2, 6, self.result["client"][1] - 4)), "the veil part way in with it")

    def test_the_list_fades_in_and_out_and_the_drop_down_looks_open_while_it_is(self):
        row = self.pictures[10][2]["row.en"]
        self.assertTrue(self.between(9, 8, 10, row))
        self.assertTrue(self.between(11, 12, 10, row))
        fx, fy, fwide, ftall = self.pictures[8][2]["setting.interface_language"]
        width = self.result["client"][0]

        def field(index):
            return [self.picture(index)[(row * width + fx) * 3:(row * width + fx + fwide) * 3] for row in range(fy, fy + ftall // 2)]
        self.assertNotEqual(field(10), field(8), "open: its edge and its chevron")
        # v0.6.26 (review P1): this job's frames carry no moment, so the drop-down's own glide back (CloseList) is drawn
        # arrived; a clocked motion draws it gliding (test_motion_render_clock).
        self.assertEqual(field(11), field(12), "closing, outside the picture's clock: its closed look arrived")


if __name__ == "__main__":
    unittest.main()
