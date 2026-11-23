r"""The picture renders take no High Contrast and no message font size from the machine (v0.6.26,
plans/v0626-audit4/audit-tooling.md F2).

The window's render (gui/WindowRender.cs RenderFrames) and the setup window's (build/motion/InstallerRender.cs, its
Driver) pinned the face of the window's font (Segoe UI) and, for clocked jobs, Windows' animation switch; but the theme
was still Theme.Current, which answers High Contrast first whenever this machine has it on - every picture in the
contrast palette, and every glide cut (Soft.ReduceMotion) - and the font's size and style were this machine's message
font's. Now both renders stand their own answer in High Contrast (off), before the palette is adopted, and set the
font at Windows' default, 9 points regular, whatever this machine's message font is.

Read from the sources by their braces (tests/guiscan.py), and both programs compiled from the shipped sources so the
pins build; nothing is rendered or shown.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import guiscan
from test_gui_v0611_access import CSC, compile_window

ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / "build" / "motion" / "InstallerRender.cs"
PIN = "Theme.HighContrastOn = delegate { return false; };"
ADOPT = "Palette.Adopt(Theme.Current(theme));"


def braces(text: str, start: int) -> str:
    """The block whose opening brace is the first at or after `start`."""
    at = text.index("{", start)
    depth = 0
    for i in range(at, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[at:i + 1]
    raise AssertionError("no closing brace")


class WindowRenderTests(unittest.TestCase):
    def test_the_render_is_never_in_high_contrast(self):
        frames = guiscan.member_body("SettingsForm", "RenderFrames")
        self.assertEqual(frames.count(PIN), 1)
        self.assertLess(frames.index(PIN), frames.index("Palette.AdoptDesign(design);"))
        self.assertLess(frames.index(PIN), frames.index(ADOPT))

    def test_the_render_font_is_at_windows_default_size_and_style(self):
        font = guiscan.member_body("SettingsForm", "RenderFont")
        self.assertNotIn("MessageBoxFont", font)
        self.assertIn("new Font(Typeface.Segoe, RenderPoints, FontStyle.Regular, GraphicsUnit.Point)", font)
        source = (ROOT / "gui" / "WindowRender.cs").read_text(encoding="utf-8")
        self.assertRegex(source, r"internal const float RenderPoints = 9f;")


class InstallerRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = SHIM.read_text(encoding="utf-8")
        cls.driver = braces(text, text.index("internal Driver(Dictionary<string, object> job, Writer writer)"))
        cls.text = text

    def test_the_setup_render_is_never_in_high_contrast(self):
        self.assertEqual(self.driver.count(PIN), 1)
        self.assertLess(self.driver.index(PIN), self.driver.index(ADOPT))

    def test_the_pinned_scale_s_font_is_at_windows_default_size_and_style(self):
        pinned = braces(self.driver, self.driver.index("if (scale >= 0.5)"))
        self.assertNotIn("SizeInPoints", pinned)
        self.assertNotIn("box.Style", pinned)
        self.assertEqual(pinned.count("RenderPoints * SettingsForm.FontFactor, FontStyle.Regular"), 2,
                         "Segoe UI, and the machine's face only where Segoe UI is not there, at the same size")
        self.assertRegex(self.text, r"private const float RenderPoints = 9f;")


@unittest.skipUnless(CSC.is_file(), "needs the in-box compiler")
class BuildsTests(unittest.TestCase):
    def test_both_render_programs_compile_with_the_pins(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(compile_window(Path(folder)).is_file())
        if str(ROOT / "build") not in sys.path:
            sys.path.insert(0, str(ROOT / "build"))
        import make_install_motion
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(make_install_motion.compile_shim(Path(folder)).is_file())


if __name__ == "__main__":
    unittest.main()
