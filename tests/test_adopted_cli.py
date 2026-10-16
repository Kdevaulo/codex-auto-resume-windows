"""Issue #37 (v0.6.16-beta.4, both editions; reported by @Kdevaulo): a conversation started in the Codex CLI's TUI and
continued in the Desktop app is the app's own, and its failures are taken up - Codex rewrites its threads row to source
vscode when the app takes it over, while the rollout's first line keeps the CLI's originator and source. A TUI
conversation the app never took over (threads source cli), VS Code's own (codex_vscode) and a subagent stay as they
were; who holds the conversation still decides whether anything is sent (A11).
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_engine import T1, EngineCase  # noqa: E402
from codex_auto_resume.codex import eligibility  # noqa: E402


def conversation(home, thread_id, *, row_source, meta_source, originator, thread_source="user"):
    """A conversation whose threads row and rollout first line say what each is given."""
    path = home.rollout(thread_id)
    meta = {"type": "session_meta", "payload": {"id": thread_id, "originator": originator, "source": meta_source,
                                                "thread_source": thread_source}}
    path.write_bytes(json.dumps(meta).encode("utf-8") + b"\n")
    with home._db("state_5.sqlite") as db:
        db.execute("INSERT INTO threads (id, rollout_path, source, thread_source, archived, history_mode, name) "
                   "VALUES (?,?,?,?,0,'paginated',NULL)", (thread_id, str(path), row_source, thread_source))
    home.catch_up(thread_id)


class AdoptedTests(EngineCase):
    def detected(self, **shape):
        h = self.fresh()
        conversation(h.home, T1, **shape)
        h.home.fail_usage(T1)
        h.backend.loaded_map[T1] = "loaded"
        h.tick()
        return h.records(T1)

    def test_a_cli_conversation_the_app_took_over_is_taken_up(self):
        """Fails with the adopted shape reverted: "not taken up (other_kind: originator codex-tui)"."""
        self.assertEqual(len(self.detected(row_source="vscode", meta_source="cli", originator="codex-tui")), 1)

    def test_a_tui_conversation_the_app_never_took_over_is_not(self):
        self.assertEqual(self.detected(row_source="cli", meta_source="cli", originator="codex-tui"), [])

    def test_vs_codes_own_and_a_subagent_are_not(self):
        self.assertEqual(self.detected(row_source="vscode", meta_source="vscode", originator="codex_vscode"), [])
        self.assertEqual(self.detected(row_source="vscode", meta_source="cli", originator="codex-tui",
                                       thread_source="subagent"), [])

    def test_only_with_the_apps_row_and_only_the_tuis_originator(self):
        self.assertEqual(eligibility.kind_of("vscode", {"source": "cli", "originator": "codex-tui"}), "desktop")
        self.assertIsNone(eligibility.kind_of("vscode", {"source": "cli", "originator": "codex_exec"}))
        self.assertIsNone(eligibility.kind_of("cli", {"source": "cli", "originator": "codex-tui"}))
        self.assertIsNone(eligibility.kind_of("vscode", {"source": "vscode", "originator": "codex-tui"}))


if __name__ == "__main__":
    unittest.main()
