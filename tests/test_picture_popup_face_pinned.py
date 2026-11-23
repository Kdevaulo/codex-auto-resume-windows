"""The tray popup's, the notification card's and the tip's pictures are set in each language's own Windows face,
whatever face this machine's Windows answers (v0.6.26, audit4 F1).

The window's pictures pin Segoe UI as Windows' UI font (audit-apng M2, test_motion_face_pinned), and so does the panel's
(make_screenshots: face=typeface.SEGOE). The popup's renderer asked this machine (fonts.message_face), so on the Korean
Windows the pictures are made on, the English popup and card were drawn in Malgun Gothic's Latin. The generators now draw
inside `make_screenshots.pinned_face()` (fonts.windows_ui_face): a picture made where Windows answers another face is the
picture an English Windows makes, and each language then takes its own face (Korean its script face). The product never
enters the pin, so its own choice is still what Windows answers. Everything is drawn into memory; no window opens.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# A face every Windows has that is not Segoe UI: this machine's answer stood in as "another Windows' UI font".
ELSEWHERE = "Times New Roman"


@unittest.skipUnless(os.name == "nt", "the popup is drawn by GDI+")
class PinnedPopupFaceTests(unittest.TestCase):
    def setUp(self):
        import make_screenshots
        from codex_auto_resume.ui.popup import fonts
        self.shots, self.fonts = make_screenshots, fonts

    def machine(self, face):
        """This machine's Windows answering `face` for its UI font."""
        return mock.patch.object(self.fonts, "message_face", return_value=face)

    def unpinned(self):
        """The generators as they were: no stand-in, the machine's answer."""
        return mock.patch.object(self.shots, "pinned_face", contextlib.nullcontext)

    def faces(self, locale, *, pinned):
        from codex_auto_resume.ui import popup as tray_popup
        strings, view = self.shots.popup_view(locale)
        renderer = tray_popup.Renderer()
        try:
            with (self.shots.pinned_face() if pinned else contextlib.nullcontext()):
                renderer.layout(view, 1.0, tray_popup.locale_of(strings))
            return dict(renderer.fonts.faces)
        finally:
            renderer.close()

    def test_the_pin_stands_in_segoe_ui_and_each_language_takes_its_own_face(self):
        with self.machine(ELSEWHERE):
            english = self.faces("en", pinned=True)
            korean = self.faces("ko", pinned=True)
        for role, face in english.items():
            self.assertTrue(face.lower().startswith("segoe ui"), (role, face))
            self.assertNotIn(ELSEWHERE, face)
        self.assertIn("Malgun Gothic", korean.values(), "Korean keeps the face its Windows sets it in")

    def test_the_product_still_takes_what_windows_answers(self):
        with self.machine(ELSEWHERE):
            live = self.faces("en", pinned=False)
        self.assertIn(ELSEWHERE, live.values(), "outside a picture the popup follows Windows' UI font")
        self.assertIsNone(self.fonts._PINNED[-1] if self.fonts._PINNED else None)

    def test_a_popup_still_made_here_is_the_one_an_english_windows_makes(self):
        with tempfile.TemporaryDirectory() as folder:
            here, english = Path(folder, "here.png"), Path(folder, "english.png")
            with self.machine(ELSEWHERE):
                self.shots.render_popup(here, "en", moving=False, scale=1.0)
            with self.machine("Segoe UI"), self.unpinned():
                self.shots.render_popup(english, "en", moving=False, scale=1.0)
            self.assertEqual(here.read_bytes(), english.read_bytes(),
                             "the English popup's picture depends on this machine's UI font")

    def test_a_card_still_made_here_is_the_one_an_english_windows_makes(self):
        with self.machine(ELSEWHERE):
            here = self.shots.card_pixels("en", "light", scale=1.0)
        with self.machine("Segoe UI"), self.unpinned():
            english = self.shots.card_pixels("en", "light", scale=1.0)
        self.assertEqual(here[:2], english[:2])
        self.assertTrue(here[2] == english[2], "the English card's picture depends on this machine's UI font")

    def test_the_motion_frames_draw_inside_the_pin(self):
        import motion_card
        import motion_popup
        import motion_tip
        for module, calls in ((motion_popup, ("self.renderer.layout(", "self.renderer.draw(")),
                              (motion_tip, ("self.renderer.tip_layout(", "self.renderer.draw_tip(")),
                              (motion_card, ("notice_window.Card(", "self._drawn("))):
            source = Path(module.__file__).read_text(encoding="utf-8")
            for call in calls:
                at = source.index(call)
                before = source[source.rfind("\n    def ", 0, at):at]
                self.assertRegex(before, r"with [\w.]*(pinned_face|_pinned)\(\):",
                                 "%s: %s is drawn outside the pinned face" % (module.__name__, call))

    def test_the_popup_motion_is_set_in_segoe_ui_here_too(self):
        import motion_popup
        with self.machine(ELSEWHERE):
            frames = motion_popup.PopupFrames("en", scale=1.0)
            try:
                frames.view()
                faces = dict(frames.renderer.fonts.faces)
            finally:
                frames.close()
        for role, face in faces.items():
            self.assertTrue(face.lower().startswith("segoe ui"), (role, face))


if __name__ == "__main__":
    unittest.main()
