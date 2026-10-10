"""Every window the Dashboard opens has the product's icon in its title bar, or none (v0.6.15-beta).

The owner saw it in Install another version... (2026-10-10): a Form that sets neither ShowIcon = false nor an Icon
shows Windows' default form icon - the red, blue and yellow squares - in its title bar. The small dialogs hide their
icon; the windows with a list (Install another version..., Timeline, Log) take the Dashboard's own. This reads the
window's sources, so a new Form that forgets both fails here before anyone opens it.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted(list((ROOT / "gui").glob("*.cs")) + list((ROOT / "advanced" / "gui").glob("*.cs")))
MADE = re.compile(r"\b(?:var|Form)\s+(\w+)\s*=\s*new Form\(\)")
# How far after `new Form()` a builder sets the window up: every builder here does it in its first dozen lines.
REACH = 40


def forms_without_an_icon_choice():
    missing = []
    for path in SOURCES:
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            made = MADE.search(line)
            if not made:
                continue
            name = re.escape(made.group(1))
            chosen = re.compile(r"\b%s\.(?:ShowIcon\s*=\s*false|Icon\s*=)" % name)
            if not any(chosen.search(later) for later in lines[number:number + REACH]):
                missing.append("%s:%d" % (path.relative_to(ROOT).as_posix(), number))
    return missing


class DialogIconTests(unittest.TestCase):
    def test_the_sources_make_windows_at_all(self):
        # The scan is not vacuous: the Dashboard makes several windows of its own.
        made = sum(len(MADE.findall(path.read_text(encoding="utf-8"))) for path in SOURCES)
        self.assertGreaterEqual(made, 5)

    def test_every_window_has_the_products_icon_or_none(self):
        self.assertEqual(forms_without_an_icon_choice(), [],
                         "a window shows Windows' default icon: set ShowIcon = false, or Icon = Icon")

    def test_the_list_windows_take_the_dashboards_icon(self):
        for name in ("DashboardVersions.cs", "DashboardActions.cs", "DashboardTools.cs"):
            text = (ROOT / "gui" / name).read_text(encoding="utf-8")
            self.assertIn("dialog.Icon = Icon;", text, name)


if __name__ == "__main__":
    unittest.main()
