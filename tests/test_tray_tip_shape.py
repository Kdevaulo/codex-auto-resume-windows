"""The shape of the icon's tooltip card (v0.6.24): two files, one pure and one that calls Windows, loaded only on a hover.

tipplan.py says where everything goes and asks Windows nothing - only brand's numbers - so the card is laid out and checked
with no screen, as the popup's layout is. tipcard.py is the window and the renderer that draws it, and nothing loads it
until the pointer first rests on the icon: a watcher whose icon is never hovered never loads it. tests/test_tray_shape.py
places both among the icon's files; this holds what each of them is.
"""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
_SRC = str(Path(_HERE).parent / "src")
for entry in (_SRC, _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import srcscan  # noqa: E402
from codex_auto_resume.ui.tray import tipcard, tipplan  # noqa: E402

PACKAGE = "codex_auto_resume.ui.tray"


def imports(module):
    """Every module `module` imports, at any depth of function: (level, name) for each."""
    found = set()
    for node in ast.walk(srcscan.package_asts()[srcscan.modules()[PACKAGE + "." + module]]):
        if isinstance(node, ast.ImportFrom):
            found.add((node.level, node.module))
        elif isinstance(node, ast.Import):
            found.update((0, alias.name) for alias in node.names)
    return found


class TipShapeTests(unittest.TestCase):
    def test_the_plan_imports_only_the_brand(self):
        self.assertEqual(imports("tipplan"), {(0, "__future__"), (3, None)})
        source = srcscan.read(srcscan.modules()[PACKAGE + ".tipplan"])
        self.assertNotIn("ctypes", source)
        self.assertIn("from ... import brand", source)

    def test_the_card_is_made_by_the_icon_on_a_hover_and_loaded_by_nothing_else(self):
        users = [name for name in srcscan.modules() if name.startswith(PACKAGE + ".") and name != PACKAGE + ".tipcard"
                 and any(module in ("tipcard",) for level, module in imports(name.rsplit(".", 1)[1]) if level == 1)]
        self.assertEqual(users, [PACKAGE + ".icon"])
        code = ("import sys; import codex_auto_resume.ui.tray as t; "
                "print(sorted(m for m in sys.modules if m.endswith(('.tipcard', '.tipplan'))))")
        loaded = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", timeout=60,
                                env={"PYTHONPATH": _SRC, "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")},
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(loaded.returncode, 0, loaded.stderr)
        self.assertEqual(loaded.stdout.strip(), "[]")

    def test_the_cards_window_never_takes_the_focus_or_a_click(self):
        for flag in (tipcard.WS_EX_LAYERED, tipcard.WS_EX_NOACTIVATE, tipcard.WS_EX_TRANSPARENT):
            self.assertTrue(tipcard.TIP_STYLE & flag)

    def test_what_the_icon_asks_of_the_card(self):
        public = {name for name, value in vars(tipcard.TipCard).items() if callable(value) and not name.startswith("_")}
        self.assertEqual(public, {"create", "destroy", "show", "hide", "tick", "watch", "frame", "render"})
        self.assertEqual(tipplan.TIP_WIDTH, (280, 360))
        self.assertEqual(tipplan.TIP_GAP, 8)


if __name__ == "__main__":
    unittest.main()
