"""audit4 B5 (the owner's answer of 2026-11-23): reset_message's statement names the route of a conversation the forced
stop paused, in every catalog.

Its statement said the message goes "through every check a continuation passes - the conversation open in the app,
nothing else queued there, usage available" and that twenty are sent in a day. In a conversation usage_pause stopped, the
stop's own turn after the reset carries the message instead (engine/usagestop.py `_carry`, review V1; audit4 B3 for a
message of either window): that turn passes core's errand guard alone, not those checks, is not counted in the claim's
pace, and the message waits for the stop's window even when written for the other one. Now the statement says so, in a
sentence of its own that names Stop near a limit in each catalog's own words.

review4 V1-V5 corrected it (the owner's answers of 2026-11-23): the message waits until every limit the stop holds has
reset; it goes even with Continue after the reset off; the turn still needs the app to hold the conversation; and Resume
before then returns it to the usual route.

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

    def test_every_catalog_names_continue_after_the_reset(self):
        """review4 V4/V5: the carry goes even with Continue after the reset off - every catalog names that choice there.
        Fails with B5's first sentence, which did not."""
        for path in CATALOGS:
            with self.subTest(path.name):
                table = catalog(path)
                self.assertIn(table["page.option.wrap_after_reset"], table["statement.reset_message.does"])

    def test_the_english_words(self):
        """review4 V1-V5: every held limit first, Continue after the reset off too, the app must still hold the
        conversation, and Resume returns it to the usual route."""
        does = catalog(statement.DIRECTORY / "en.json")["statement.reset_message.does"]
        self.assertTrue(does.endswith(
            " In a conversation Stop near a limit has stopped, the message waits until every limit the stop holds has "
            "reset, even one written for the other limit, and the stop's own turn then carries it, even with Continue "
            "after the reset off: that turn still needs the conversation open in the app, but not the other two checks, "
            "and it does not count toward the twenty a day. If you press Resume in Codex before then, the message goes "
            "the usual way at its own reset."))
        self.assertNotIn("does not go through those checks", does)


if __name__ == "__main__":
    unittest.main()
