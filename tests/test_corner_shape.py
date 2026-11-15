"""brand/shape.py's own shape (v0.6.24): the surface it gives, and that it stays geometry.

The corner is read by the window's generator (build/make_brand.py), the popup's painter and masks, the notification
card and the panel's stylesheet, so a name that went missing would silently send one of them back to a circle - or,
behind an `except`, to nothing. Held here: the names, that the module is pure (no Windows, no I/O, nothing above it
in brand's order but the scale and the tokens), and its place among brand's files.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from codex_auto_resume.brand import shape

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "src" / "codex_auto_resume" / "brand" / "shape.py"

SURFACE = ("CSS_CORNER", "Corner", "DESIGN_SMOOTHING", "Profile", "RHO_STEPS", "corner", "corner_segments",
           "design_smoothing", "distance", "edge_at", "flatten", "inside", "inside_corner", "outline", "profile",
           "smoothed")


class ShapeModuleTests(unittest.TestCase):
    def test_its_surface(self):
        public = sorted(name for name in vars(shape) if not name.startswith("_") and name not in
                        ("annotations", "bisect", "math", "namedtuple", "CORNER_SMOOTHING", "design_name"))
        self.assertEqual(public, sorted(SURFACE))

    def test_it_is_pure_geometry(self):
        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add("." * node.level + (node.module or ""))
        self.assertEqual(imported, {"__future__", "bisect", "collections", "math", ".scale", ".tokens"})

    def test_what_reads_it(self):
        readers = {"build/make_brand.py": "from codex_auto_resume.brand import shape",
                   "src/codex_auto_resume/brand/css.py": "from .shape import",
                   "src/codex_auto_resume/ui/popup/gdiplus.py": "from ...brand import shape",
                   "src/codex_auto_resume/ui/popup/elevation.py": "from ...brand import shape",
                   "src/codex_auto_resume/notice_card.py": "from .brand import shape",
                   "src/codex_auto_resume/ui/card/card.py": "from ...brand import shape"}
        for path, line in readers.items():
            with self.subTest(path=path):
                self.assertIn(line, (ROOT / path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
