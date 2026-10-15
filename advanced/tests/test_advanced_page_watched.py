# ADVANCED-EDITION-CODE: in the advanced edition's tree, never the standard one's.
"""The Dashboard's Advanced features page in the window itself: a watched capability that needs rows to watch shows
the card they are set up in (v0.6.16-beta.3).

A message at a reset, a reset credit, Keep a conversation going and Queue messages for later had their cards - the
rules, the conversations kept going, the queued messages, and the forms that add them - only while on, so a watched one
could not be set up and had nothing to watch (the owner, 2026-10-11). Each card is built now for a watched capability as
for one that is on, from the real bridge's answers in a home of its own; off, there is none.

GUI test module: compiles real executables, so it runs on its own.

    PYTHONPATH=src;advanced/src python -m unittest discover -s advanced/tests -p test_advanced_page_watched.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pagecase import CSC, POWERSHELL, PageCase, snapshot  # noqa: E402

READS = {"reset_message": "advanced-resets", "reset_credit": "advanced-resets", "keep_going": "advanced-keep-going",
         "prompt_queue": "advanced-prompts"}
TITLES = {"reset_message": "page.resets.message.title", "reset_credit": "page.resets.credit.title",
          "keep_going": "page.keep.title", "prompt_queue": "page.queue.title"}


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class PageTests(PageCase):
    @classmethod
    def shown(cls, bridge, capability, state):
        if state is not None:
            cls.watched(bridge, capability, state=state)
        script = cls.opening(bridge, "en")
        script["advanced-resets"] = [bridge("advanced-resets", {})]
        script["advanced-keep-going"] = [bridge("advanced-keep-going", {})]
        script["advanced-prompts"] = [bridge("advanced-prompts", {})]
        steps = [{"do": "snapshot", "reply": snapshot()}, {"do": "show"}, {"do": "choose", "id": capability},
                 {"do": "look"}]
        return "en", {"script": script, "steps": steps}, {"words": script["advanced-words"][0]["result"]["words"]}

    @classmethod
    def scenario_watched_reset_message(cls, bridge):
        return cls.shown(bridge, "reset_message", "shadow")

    @classmethod
    def scenario_watched_reset_credit(cls, bridge):
        return cls.shown(bridge, "reset_credit", "shadow")

    @classmethod
    def scenario_watched_keep_going(cls, bridge):
        return cls.shown(bridge, "keep_going", "shadow")

    @classmethod
    def scenario_watched_prompt_queue(cls, bridge):
        return cls.shown(bridge, "prompt_queue", "shadow")

    @classmethod
    def scenario_off_prompt_queue(cls, bridge):
        return cls.shown(bridge, "prompt_queue", None)

    def of(self, name) -> tuple:
        found = self.results.get(name)
        if found is None or "error" in found:
            self.fail("%s did not run: %s" % (name, (found or {}).get("error")))
        return found, self.expected[name]

    def test_each_card_is_built_for_a_watched_capability(self):
        for capability in TITLES:
            with self.subTest(capability):
                result, expected = self.of("scenario_watched_" + capability)
                (look,) = result["looks"]
                titles = [card[0] for card in look["cards"]]
                self.assertIn(expected["words"][TITLES[capability]], titles)

    def test_off_there_is_no_card_to_set_up(self):
        result, expected = self.of("scenario_off_prompt_queue")
        (look,) = result["looks"]
        self.assertNotIn(expected["words"][TITLES["prompt_queue"]], [card[0] for card in look["cards"]])


if __name__ == "__main__":
    unittest.main()
