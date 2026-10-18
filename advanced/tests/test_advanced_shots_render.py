"""The Advanced features page drawn offscreen by the window's render mode, for its pictures (build/advanced_shots.py).

The window is compiled from the working tree - the advanced edition's with advanced/gui/window.sources - and drawn
never shown, answered from the generator's seeded scratch installation: the page with the capability a frame names
open, or the one the job's command line names (`--capability=`), the compatibility report written and checked, and
a page or a capability the window does not have refused rather than drawn as another. Only where it is a fair
question, as tests/test_motion_fidelity.py's live tests: on Windows with the C# compiler, at the display scale the
stills were captured at and while they are of this working tree's window - or when CAR_MOTION_FIDELITY=1 asks anyway.
A GUI set: run it under plans/proof/gui_lock.sh.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for _path in (str(ROOT / "advanced" / "src"), str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import advanced_shots as shots_made  # noqa: E402
from test_motion_fidelity import fair  # noqa: E402


@unittest.skipIf(fair() is not None, fair() or "")
class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.work = Path(cls.folder.name)
        cls.advanced = shots_made.compile_window(cls.work / "advanced", "advanced")
        cls.standard = shots_made.compile_window(cls.work / "standard", "standard")
        read, _envelope = shots_made.read_answers("advanced", "base", "en", report=True)
        cls.forms = {"en": shots_made.form_answers(read)}

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def draw(self, exe, frames, name, arguments=None):
        data = {"out": str(self.work / name / "frames"), "theme": "light", "design": "soft", "forms": self.forms,
                "targets": [], "frames": [dict(frame, index=index, locale="en", light=0)
                                          for index, frame in enumerate(frames)]}
        if arguments:
            data["arguments"] = arguments
        pictures, _size = shots_made.render(exe, data, self.work / name)
        self.assertEqual(len(pictures), len(frames))
        return [picture for _index, picture in pictures]

    def test_the_page_opens_the_capability_its_frame_or_its_command_line_names_and_writes_the_report(self):
        """Fails with `--capability=` taken out of ArgumentParsed: the second job opens the report, as the first does."""
        first, credit, report = self.draw(self.advanced, [{"page": "advanced"},
                                                          {"page": "advanced", "capability": "reset_credit"},
                                                          {"page": "advanced", "capability": "compat_report",
                                                           "report": {"login": shots_made.LOGIN, "check": True},
                                                           "show": "report.file"}],
                                          "frames")
        self.assertNotEqual(first, credit, "a capability a frame names is open")
        self.assertNotEqual(first, report, "the report is written and checked on its card")
        (asked,) = self.draw(self.advanced, [{"page": "advanced"}], "argument", ["--capability=reset_credit"])
        self.assertEqual(asked, credit, "the capability the command line names is the one open")

    def test_the_usage_numbers_picture_scrolls_to_the_choices_and_opens_custom_on_the_five_hour_warning(self):
        """v0.6.16 (P8): fails with RenderCustom or the `choices` part taken out - the column would stay at the top, or
        Custom... stay shut."""
        top, choices, custom = self.draw(self.advanced, [
            {"page": "advanced", "capability": "usage_meter"},
            {"page": "advanced", "capability": "usage_meter", "show": "choices"},
            {"page": "advanced", "capability": "usage_meter", "show": "choices",
             "custom": {"key": "warn_five_hour", "text": "88"}}], "usage")
        self.assertNotEqual(top, choices, "the column is scrolled to the Choices card")
        self.assertNotEqual(choices, custom, "Custom... is open, the number typed in its box")
        with self.assertRaisesRegex(RuntimeError, "no choice called window_five_hour takes a number typed in"):
            self.draw(self.advanced, [{"page": "advanced", "capability": "usage_meter",
                                       "custom": {"key": "window_five_hour", "text": "1"}}], "switch")

    def test_a_page_or_a_capability_the_window_does_not_have_stops_the_render(self):
        """Fails with RenderState drawing what it has instead: the standard window's Overview for the advanced page."""
        with self.assertRaisesRegex(RuntimeError, "no page called advanced is in this window"):
            self.draw(self.standard, [{"page": "advanced"}], "standard")
        with self.assertRaisesRegex(RuntimeError, "no capability called no_such_capability is in this tree"):
            self.draw(self.advanced, [{"page": "advanced", "capability": "no_such_capability"}], "unknown")
        with self.assertRaisesRegex(RuntimeError, "no part called report.file shows on reset_credit"):
            self.draw(self.advanced, [{"page": "advanced", "capability": "reset_credit", "show": "report.file"}], "part")


if __name__ == "__main__":
    unittest.main()
