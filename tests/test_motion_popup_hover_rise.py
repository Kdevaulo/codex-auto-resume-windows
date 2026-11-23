"""While the popup rises, a pointer over one of its buttons is tested where the picture shows it (v0.6.26, audit4 F3).

make_motion lays the popup's picture `below` its place while it opens and hands PopupFrames.drawn the pointer in that
picture's own pixels - the rise already taken out, as the product hit-tests in the risen window's own coordinates.
drawn then took the rise out a second time (`hovered(pointer, below)`), so for the opening's 160 ms a pointer at a
button's top edge was missed. Drawn in memory by the popup's own layout and renderer: nothing on the screen.
"""
from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)


class HoverWhileRisingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import motion_popup
        cls.popup = motion_popup.PopupFrames("en", scale=2.0)
        cls.buttons = {item["target"]: item["rect"] for item in cls.popup.view()[1]["items"] if item["kind"] == "button"}

    @classmethod
    def tearDownClass(cls):
        cls.popup.close()

    def hover_drawn(self, frame, pointer):
        """The hover drawn takes for `pointer` at `frame`: what it hands the button faces."""
        seen = []
        faces = self.popup.faces

        def watch(plan, hover, now):
            seen.append(hover)
            return faces(plan, hover, now)
        self.popup.faces = watch
        try:
            self.popup._held, self.popup._face_states, self.popup._faces = None, None, {}
            self.popup.drawn(frame, b"", pointer=pointer)
        finally:
            del self.popup.faces
        return seen[-1]

    def test_a_pointer_at_a_buttons_top_while_the_popup_rises_is_over_it(self):
        frame = SimpleNamespace(t=40, popup={"opened": 0, "off": (), "busy": (), "glides": ()})
        _alpha, below, arrived = self.popup.opening(frame)
        self.assertFalse(arrived)
        self.assertGreater(below, 0, "the frame is one the popup is still rising at")
        for target, (left, top, right, _bottom) in self.buttons.items():
            # The pointer at the button's top row in the picture's own pixels, as make_motion hands it over.
            pointer = ((left + right) // 2 + self.popup.shift[0], top + self.popup.shift[1])
            with self.subTest(target=target):
                self.assertEqual(self.hover_drawn(frame, pointer), target)

    def test_once_it_has_arrived_the_same_pointer_is_over_it_too(self):
        frame = SimpleNamespace(t=5000, popup={"opened": 0, "off": (), "busy": (), "glides": ()})
        self.assertTrue(self.popup.opening(frame)[2])
        for target, (left, top, right, _bottom) in self.buttons.items():
            pointer = ((left + right) // 2 + self.popup.shift[0], top + self.popup.shift[1])
            with self.subTest(target=target):
                self.assertEqual(self.hover_drawn(frame, pointer), target)


if __name__ == "__main__":
    unittest.main()
