"""v0.6.26 (update resilience, proposal 9): an engine named in Settings that the Codex app does not run is said so.

The engine a person names is never second-guessed, so where the app runs another one nothing is ever matched - and
the record said only "could not match its server". The reason app_server_unmatched:named_engine (the backend's
app_unmatched_reason, codex/transport.py) asks for a person as app_server_unmatched does, and every catalog says which engine is the cause.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import types  # noqa: E402

from codex_auto_resume import l10n, logbook, machine  # noqa: E402
from codex_auto_resume.engine.freshness import FreshnessMixin  # noqa: E402
from codex_auto_resume.domain.vocabulary import ReasonCode  # noqa: E402

REASON = "app_server_unmatched:named_engine"
RECORD = {"state": "waiting_for_app", "last_error": REASON}


class NamedEngineTests(unittest.TestCase):
    def test_it_is_a_reason_of_its_own(self):
        self.assertIn(REASON, set(ReasonCode))

    def test_a_record_waiting_for_it_asks_for_a_person_as_an_unmatched_server_does(self):
        self.assertEqual(machine.overlays(RECORD), ["app_server_unmatched"])
        self.assertEqual(machine.overlays(RECORD, enabled=False), ["paused"])

    def test_every_language_says_which_engine_is_the_cause(self):
        english = l10n.catalog("en")["why." + REASON]
        self.assertIn("Settings", english)
        for language in l10n.LOCALES:
            with self.subTest(language):
                self.assertTrue(l10n.catalog(language).get("why." + REASON))

    def test_a_record_waiting_for_the_app_takes_the_kind_the_backend_names(self):
        # The backend's look says which kind of unmatched server it found (codex/transport.py app_unmatched_reason).
        def reason(**backend):
            engine = types.SimpleNamespace(backend=types.SimpleNamespace(**backend))
            return FreshnessMixin._no_app_reason(engine)
        self.assertEqual(reason(app_look="unmatched", app_unmatched_reason=REASON), REASON)
        self.assertEqual(reason(app_look="unmatched"), "app_server_unmatched")
        self.assertEqual(reason(app_look="unmatched", app_unmatched_reason="send_everything_now"), "app_server_unmatched")
        self.assertEqual(reason(app_look="closed", app_unmatched_reason=REASON), "desktop_app_unavailable")

    def test_the_log_says_it(self):
        self.assertIn(("waiting_for_app", REASON), logbook._MESSAGES)


if __name__ == "__main__":
    unittest.main()
