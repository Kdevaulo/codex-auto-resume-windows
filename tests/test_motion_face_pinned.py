"""The motion pictures and the window's stills are set in each language's own Windows face (v0.6.26, audit-apng M2).

They are made on whatever Windows the main session runs - a Korean one here - and an English window there kept
Windows' UI font, Malgun Gothic: Latin in its metrics, and every backslash of the setup motion's log a won sign. A
render whose scale the job pins (every picture) now starts from the face an English Windows has, Segoe UI, as the
panel's picture does (make_screenshots: face=typeface.SEGOE), and the window sets each language from it in the face
that language's Windows sets it in (Typeface.ForLanguage). Read from the sources: nothing is drawn."""
from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import guiscan  # noqa: E402


class PinnedFaceTests(unittest.TestCase):
    def test_the_dashboard_drawn_for_a_picture_starts_from_segoe_ui(self):
        body = guiscan.member_body("SettingsForm", "RenderFont")
        self.assertIn("if (!RenderPinned) return null;", body, "a render that pins no scale keeps the machine's font")
        self.assertIn("new Font(Typeface.Segoe, box.SizeInPoints, box.Style", body)
        self.assertIn("AtDisplayScale(TextScale.Apply(face, textRead, TextSize))", body,
                      "at the size the window's own font is made at")
        opened = guiscan.member_body("SettingsForm", "OpenForRender")
        self.assertRegex(opened, r"new SettingsForm\([^;]*strings, RenderFont\(\)\)")

    def test_each_language_then_takes_its_own_windows_face(self):
        faces = guiscan.type_body("Typeface")
        for language, face in (("ko", "Malgun Gothic"), ("ja", "Yu Gothic UI"), ("zh-CN", "Microsoft YaHei UI"),
                               ("zh-TW", "Microsoft JhengHei UI"), ("th", "Leelawadee UI")):
            self.assertIn('{ "%s", "%s" }' % (language, face), faces)
        self.assertIn("Typeface.ForLanguage(Font, strings, wordsLanguage)", guiscan.settings())

    def test_the_setup_window_drawn_for_a_picture_starts_from_segoe_ui(self):
        shim = (ROOT / "build" / "motion" / "InstallerRender.cs").read_text(encoding="utf-8")
        pinned = shim[shim.index("if (scale >= 0.5)"):shim.index("else", shim.index("if (scale >= 0.5)"))]
        self.assertRegex(pinned, r"font = new Font\(Typeface\.Segoe, box\.SizeInPoints \* SettingsForm\.FontFactor")
        self.assertNotRegex(re.sub(r"if \(!string\.Equals[^;]*;", "", pinned),
                            r"font = new Font\(box\.FontFamily", "the machine's face only where Segoe UI is missing")


if __name__ == "__main__":
    unittest.main()
