"""audit4 B5 (the owner's answer of 2026-11-23): reset_message's statement names the route of a conversation the forced
stop paused, in every catalog.

Its statement said the message goes "through every check a continuation passes - the conversation open in the app,
nothing else queued there, usage available" and that twenty are sent in a day. In a conversation usage_pause stopped, the
stop's own turn after the reset carries the message instead (engine/usagestop.py `_carry`, review V1; audit4 B3 for a
message of either window): that turn passes core's errand guard alone, not those checks, is not counted in the claim's
pace, and the message waits for the stop's window even when written for the other one. Now the statement says so, in a
sentence of its own that names Stop near a limit in each catalog's own words.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;tests" python -m unittest test_advanced_statement_stopped_route
"""
from __future__ import annotations

import json
import unittest

from codex_auto_resume_advanced import statement

CATALOGS = sorted(statement.DIRECTORY.glob("*.json"))


def catalog(path):
    return json.loads(path.read_text(encoding="utf-8"))


class StoppedRouteTests(unittest.TestCase):
    def test_there_are_twenty_two(self):
        self.assertEqual(len(CATALOGS), 22)

    def test_every_catalog_names_the_stop_in_what_reset_message_does(self):
        """Fails with the old words: no catalog's reset_message statement named Stop near a limit."""
        for path in CATALOGS:
            with self.subTest(path.name):
                table = catalog(path)
                self.assertIn(table["name.usage_pause"], table["statement.reset_message.does"])

    def test_the_english_words(self):
        does = catalog(statement.DIRECTORY / "en.json")["statement.reset_message.does"]
        self.assertTrue(does.endswith(
            " In a conversation Stop near a limit has stopped, the stop's own turn after its reset carries the message "
            "instead: that turn does not go through those checks or count toward the twenty a day, and the message "
            "waits for that reset even when it was written for the other limit."))


if __name__ == "__main__":
    unittest.main()
