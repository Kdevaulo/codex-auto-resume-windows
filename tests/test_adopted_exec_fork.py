"""Issue #66 (v0.6.24, both editions; reported by @7Magicbunny): a conversation a person forked from a `codex exec` run
into the Codex app, and kept working in there, is the app's own, and its failures are taken up. Its threads row is the
app's (source vscode, thread_source user); the fork's first line keeps the exec run's originator (codex_exec) with
source vscode and names the run it was forked from (forked_from_id, forked_from_ordinal_exclusive).

Only that shape (codex/eligibility.py "exec_forked"): a standalone exec run (threads source exec), a subagent, the
product's own exec request (the advanced edition's window anchor: an ephemeral `codex exec` that leaves no conversation,
and whose shape, were one left, is an exec run's) and a vscode row whose codex_exec first line names no fork stay out.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_adopted_cli import conversation  # noqa: E402
from test_engine import T1, EngineCase  # noqa: E402
from codex_auto_resume.codex import eligibility  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = ROOT / "advanced" / "src" / "codex_auto_resume_advanced" / "engine" / "anchor.py"
# The fork's first line as the report gives it (ids are the fixtures').
FORK = {"forked_from_id": "0a1b2c3d-0001-7000-8000-0000000000f1", "forked_from_ordinal_exclusive": 478,
        "cli_version": "0.169.0-alpha.11.1"}
EXEC = "codex_exec"


class ExecForkTests(EngineCase):
    def detected(self, **shape):
        h = self.fresh()
        conversation(h.home, T1, **shape)
        h.home.fail_usage(T1)
        h.backend.loaded_map[T1] = "loaded"
        h.tick()
        return h.records(T1), h

    def test_a_persons_fork_of_an_exec_run_is_taken_up(self):
        """Fails with the fix reverted: "not taken up (other_kind: originator codex_exec)"."""
        records, _h = self.detected(row_source="vscode", meta_source="vscode", originator=EXEC, **FORK)
        self.assertEqual(len(records), 1)
        self.assertEqual(eligibility.kind_of("vscode", {"source": "vscode", "originator": EXEC, **FORK}), "desktop")
        self.assertTrue(eligibility.originator_taken("vscode", {"originator": EXEC, **FORK}))

    def test_a_standalone_exec_run_is_not(self):
        for fork in ({}, FORK):
            with self.subTest(forked=bool(fork)):
                records, h = self.detected(row_source="exec", meta_source="exec", originator=EXEC, **fork)
                self.assertEqual(records, [])
                self.assertEqual(eligibility.row_problem({"source": "exec", "archived": 0, "thread_source": "user",
                                                          "history_mode": "paginated"}), "source exec")
                self.assertIsNone(eligibility.kind_of("exec", {"source": "exec", "originator": EXEC, **fork}))

    def test_a_subagent_of_the_fork_is_not(self):
        records, _h = self.detected(row_source="vscode", meta_source="vscode", originator=EXEC,
                                    thread_source="subagent", **FORK)
        self.assertEqual(records, [])

    def test_a_vscode_row_whose_exec_line_names_no_fork_is_not(self):
        """Kept out: nothing proves such a conversation is a person's own."""
        records, _h = self.detected(row_source="vscode", meta_source="vscode", originator=EXEC)
        self.assertEqual(records, [])
        for line in ({"source": "vscode", "originator": EXEC},
                     {"source": "vscode", "originator": EXEC, "forked_from_id": "not-an-id"},
                     {"source": "vscode", "originator": EXEC, "forked_from_id": None}):
            with self.subTest(line=line):
                self.assertIsNone(eligibility.kind_of("vscode", line))
                self.assertFalse(eligibility.originator_taken("vscode", line))

    def test_a_fork_whose_line_says_another_source_is_not(self):
        records, _h = self.detected(row_source="vscode", meta_source="exec", originator=EXEC, **FORK)
        self.assertEqual(records, [])
        self.assertIsNone(eligibility.kind_of("vscode", {"source": "cli", "originator": EXEC, **FORK}))

    def test_the_products_own_exec_request_is_not(self):
        """The advanced edition's window anchor is the one `codex exec` the product runs: ephemeral, so it leaves no
        conversation (MANCHOR), and names no fork. Its shape, were a row left, is a standalone exec run's."""
        if ANCHOR.is_file():
            tree = ast.parse(ANCHOR.read_text(encoding="utf-8"))
            value = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                         and any(getattr(t, "id", None) == "EXEC_ARGUMENTS" for t in node.targets))
            arguments = [item.value for item in value.elts if isinstance(item, ast.Constant)]
            self.assertEqual(arguments[0], "exec")
            self.assertIn("--ephemeral", arguments)
            self.assertNotIn("fork", " ".join(arguments))
        for row_source in ("exec", "vscode"):
            with self.subTest(row_source=row_source):
                records, _h = self.detected(row_source=row_source, meta_source="exec", originator=EXEC)
                self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
