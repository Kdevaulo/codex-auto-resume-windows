"""v0.6.26 third round A5 and S2: two statements say what their code does, in every catalog.

* window_anchor (A5): the request is sent with the person's MCP servers, hooks, plugins, apps and notify program switched
  off; where Codex refuses that switch it is sent once more without it (engine/anchor.py `_again`), and where config.toml
  cannot be read its MCP servers are not switched off (`config_unreadable`) - then those programs may run, and the
  watcher's log says so. The statement said nothing of the person's own programs.
* python_choice (S2): the package's standard library cannot carry an Authenticode signature, so it rests on the SHA-256
  python.org publishes alone (control/pythons.py `_signed` checks every .exe, .dll and .pyd; the zip and ._pth run at
  the import step). The risks said nothing of it.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;tests" python -m unittest test_advanced_statement_programs
"""
from __future__ import annotations

import json
import unittest

from codex_auto_resume_advanced import statement

CATALOGS = sorted(statement.DIRECTORY.glob("*.json"))


def risks(path, capability):
    return json.loads(path.read_text(encoding="utf-8"))["statement.%s.risks" % capability]


class EveryCatalogTests(unittest.TestCase):
    def test_there_are_twenty_two(self):
        self.assertEqual(len(CATALOGS), 22)

    def test_window_anchor_says_the_persons_programs_may_run(self):
        """Fails with the old risks: no catalog named MCP servers, config.toml or notify there."""
        for path in CATALOGS:
            with self.subTest(path.name):
                text = risks(path, "window_anchor")
                for word in ("MCP", "config.toml", "notify"):
                    self.assertIn(word, text)

    def test_python_choice_says_what_rests_on_the_digest_alone(self):
        """Fails with the old risks: the SHA-256 was named only in what it does, as if it covered every file signed."""
        for path in CATALOGS:
            with self.subTest(path.name):
                self.assertIn("SHA-256", risks(path, "python_choice"))

    def test_the_english_words(self):
        path = statement.DIRECTORY / "en.json"
        self.assertIn("those programs may then run for that request, and the watcher's log says so",
                      risks(path, "window_anchor"))
        self.assertIn("The standard library inside the package cannot carry a signature, so it rests on python.org's "
                      "published SHA-256 alone.", risks(path, "python_choice"))


if __name__ == "__main__":
    unittest.main()
