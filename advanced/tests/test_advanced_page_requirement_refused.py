"""What a feature needs could not be turned on with it: the page says so in its own sentence (v0.6.26, audit R3).

Turn on for a capability whose requirement is off, refused by the bridge as requirement_refused each time it is asked
again (AdvancedAsks rounds: the requirement keeps changing underneath), ended on the generic "That request was
refused." - page.refused.requirement, the sentence written for this, was in all 22 catalogs and shown nowhere. Now the
last round tells that sentence (AdvancedPage.AdvancedRefusal).

The refusal is the real bridge's own answer to a request without what it needs (`also`); the window is compiled once and
driven as a person would (pagecase.PageCase). GUI test module: compiles real executables, so it runs on its own.

    PYTHONPATH=src;advanced/src python -m unittest discover -s advanced/tests -p test_advanced_page_requirement_refused.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pagecase import CSC, POWERSHELL, PageCase, sent, snapshot  # noqa: E402


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class RequirementRefusedTests(PageCase):
    @classmethod
    def scenario_requirement_refused(cls, bridge):
        """Turn on for Wrap up near a limit, answered yes every round; the bridge refuses each request as one whose
        requirement could not be turned on with it."""
        bridge.measured = {}
        script = cls.opening(bridge, "en")
        wrap = script["advanced-statement usage_wrap_up"][0]["result"]
        refused = bridge("advanced-arm", {"capability": "usage_wrap_up", "state": "armed", "revision": wrap["revision"],
                                          "generation": script["advanced-list"][0]["result"]["generation"],
                                          "engine_version": wrap["engine_version"],
                                          "warnings": [item["warning"] for item in wrap["warnings"]["items"]]})
        steps = [{"do": "snapshot", "reply": snapshot()}, {"do": "show"}, {"do": "choose", "id": "usage_wrap_up"},
                 {"do": "reply", "key": "advanced-arm", "with": [refused, refused, refused]},
                 {"do": "press", "button": "on"}]
        return "en", {"answers": [True, True, True], "script": script, "steps": steps}, {
            "refused": refused["result"], "words": script["advanced-words"][0]["result"]["words"]}

    def test_the_last_round_tells_what_it_needs_could_not_be_turned_on(self):
        result, expected = self.of("scenario_requirement_refused")
        self.assertEqual(expected["refused"].get("refusal"), "requirement_refused", expected["refused"])
        self.assertEqual(len(sent(result, "advanced-arm")), 3, "asked again while it kept changing, three rounds")
        self.assertEqual(result["told"], [expected["words"]["page.refused.requirement"]])
        self.assertNotEqual(result["told"], [expected["words"]["page.refused.other"]])


if __name__ == "__main__":
    unittest.main()
