"""The Dashboard's Advanced features page in the window itself: the compatibility report's card.

The window is compiled once for this module and every scenario_* below runs in one window process
(pagecase.PageCase); each makes its replies with this edition's real bridge in a home of its own, so nothing
here reads the real installation, the real Software\\Policies keys or a real Codex.

Held here: the compatibility report - an action - says it sends nothing to Codex where the others show their
limits, and its card writes, shows, saves, checks and sends a report only as its state allows, sends only on
exactly the word send, holds the window's reopen while a check or a send runs, keeps Turn off live meanwhile,
shows a send it cannot account for as lost, and keeps the last ending once it is off.

GUI test module: compiles real executables, so it runs on its own.

    PYTHONPATH=src;advanced/src python -m unittest discover -s advanced/tests -p test_advanced_page_report.py
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced import surfaces  # noqa: E402
from pagecase import (  # noqa: E402
    BRANCH, BUILT, CHECKED, CSC, FILE, PARTIAL, POWERSHELL, PROJECT, REPORT, RUNNING, SENT, SHA, TARGET, WEB,
    WRITES, Bridge, job, ok, PageCase, sent, snapshot)


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class PageTests(PageCase):
    """The page driven as a person would, every scenario of this module in one window process."""

    @staticmethod
    def report_on(bridge, state="armed"):
        """The compatibility report turned on, or watched, through the real bridge, as the page turns it."""
        shown = bridge("advanced-statement", {"capability": REPORT, "locale": "en"})["result"]
        done = bridge("advanced-arm", {"capability": REPORT, "state": state, "revision": shown["revision"],
                                       "generation": bridge("advanced-list", {})["result"]["generation"],
                                       "engine_version": shown["engine_version"],
                                       "warnings": [item["warning"] for item in shown["warnings"]["items"]]})
        assert done["result"]["done"], done

    @classmethod
    def scenario_report_sent(cls, bridge):
        """On: the login typed, the report written, saved, checked and - on exactly the word send - sent."""
        cls.report_on(bridge)
        script = cls.opening(bridge, "en")
        script["advanced-report-build"] = [job("j1")]
        script["advanced-report-check"] = [job("j2")]
        script["advanced-report-send"] = [job("j3")]
        script["advanced-report-save"] = [ok({"done": True, "status": "saved"})]
        script["advanced-report-job"] = [ok(RUNNING), ok(BUILT), ok(CHECKED), ok(RUNNING), ok(SENT)]
        steps = [{"do": "snapshot", "reply": snapshot(on=1)}, {"do": "show"}, {"do": "choose", "id": REPORT},
                 {"do": "look"},                                                        # 0: nothing written yet
                 {"do": "type", "into": "login", "text": " ExampleUser "}, {"do": "press", "button": "report_write"},
                 {"do": "look"},                                                        # 1: writing
                 {"do": "poll"}, {"do": "poll"}, {"do": "look"},                        # 2: written
                 {"do": "save_to", "path": "C:\\Reports\\codex-cli-0.158.0.json"},
                 {"do": "press", "button": "report_save"}, {"do": "look"},              # 3: saved
                 {"do": "press", "button": "report_check"}, {"do": "look"},             # 4: checking, held
                 {"do": "poll"}, {"do": "look"},                                        # 5: checked
                 {"do": "type", "into": "word", "text": "Send"}, {"do": "look"},        # 6: not the word
                 {"do": "press", "button": "report_send"},
                 {"do": "type", "into": "word", "text": "send"}, {"do": "look"},        # 7: the word
                 {"do": "press", "button": "report_send"}, {"do": "look"},              # 8: sending, held
                 {"do": "poll"}, {"do": "look"},                                        # 9: still sending
                 {"do": "poll"}, {"do": "look"}]                                        # 10: sent
        return "en", {"script": script, "steps": steps}, {"words": script["advanced-words"][0]["result"]["words"],
                                                          "listing": script["advanced-list"][0]["result"]}

    @classmethod
    def scenario_report_watched(cls, bridge):
        """Watched: written and saved, never checked or sent; and an action's limits say it sends nothing to Codex."""
        cls.report_on(bridge, "shadow")
        script = cls.opening(bridge, "ko")
        script["advanced-report-build"] = [job("j1")]
        script["advanced-report-job"] = [ok(BUILT)]
        steps = [{"do": "snapshot", "reply": snapshot()}, {"do": "show"}, {"do": "choose", "id": REPORT},
                 {"do": "type", "into": "login", "text": "ExampleUser"}, {"do": "press", "button": "report_write"},
                 {"do": "poll"}, {"do": "look"}]
        return "ko", {"script": script, "steps": steps}, {"words": script["advanced-words"][0]["result"]["words"]}

    @classmethod
    def scenario_report_lost(cls, bridge):
        """A send whose start the one-shot bridge answered as an unknown command, and a check whose job the service no
        longer held: both are lost, shown with the way to tell, and neither holds the reopen after."""
        cls.report_on(bridge)
        script = cls.opening(bridge, "en")
        script["advanced-report-build"] = [job("j1")]
        script["advanced-report-check"] = [job("j2")]
        script["advanced-report-send"] = [{"ok": False, "error": "unknown command", "error_code": "request_failed"}]
        script["advanced-report-job"] = [ok(BUILT), ok(CHECKED), ok({"done": True, "status": "lost"})]
        steps = [{"do": "snapshot", "reply": snapshot(on=1)}, {"do": "show"}, {"do": "choose", "id": REPORT},
                 {"do": "type", "into": "login", "text": "ExampleUser"}, {"do": "press", "button": "report_write"},
                 {"do": "poll"}, {"do": "press", "button": "report_check"}, {"do": "poll"},
                 {"do": "type", "into": "word", "text": "send"}, {"do": "press", "button": "report_send"},
                 {"do": "look"},                                                        # 0: the send is lost
                 {"do": "press", "button": "report_check"}, {"do": "poll"}, {"do": "look"}]  # 1: the check is lost
        return "en", {"script": script, "steps": steps}, {"words": script["advanced-words"][0]["result"]["words"]}

    @classmethod
    def scenario_report_turned_off(cls, bridge):
        """Turned off while a send runs - Turn off is live then - the send ends part way; the card, off, keeps that."""
        cls.report_on(bridge)
        script = cls.opening(bridge, "en")
        off_listing = bridge("advanced-list", {})
        off_listing = copy.deepcopy(off_listing)
        entry = next(item for item in off_listing["result"]["capabilities"] if item["id"] == REPORT)
        entry["state"], entry["stored"], entry["by"], entry["reason"] = "off", "off", "dashboard", "disarmed"
        script["advanced-report-build"] = [job("j1")]
        script["advanced-report-check"] = [job("j2")]
        script["advanced-report-send"] = [job("j3")]
        script["advanced-report-job"] = [ok(BUILT), ok(CHECKED), ok(RUNNING), ok(PARTIAL)]
        steps = [{"do": "snapshot", "reply": snapshot(on=1)}, {"do": "show"}, {"do": "choose", "id": REPORT},
                 {"do": "type", "into": "login", "text": "ExampleUser"}, {"do": "press", "button": "report_write"},
                 {"do": "poll"}, {"do": "press", "button": "report_check"}, {"do": "poll"},
                 {"do": "type", "into": "word", "text": "send"}, {"do": "press", "button": "report_send"},
                 {"do": "poll"}, {"do": "look"},                                        # 0: sending
                 {"do": "reply", "key": "advanced-disarm", "with": [{"ok": True, "result": {"done": True, "changed": True}}]},
                 {"do": "reply", "key": "advanced-list", "with": [off_listing]},
                 {"do": "press", "button": "off"}, {"do": "look"},                      # 1: off, still sending
                 {"do": "poll"}, {"do": "look"}]                                        # 2: ended part way
        return "en", {"script": script, "steps": steps}, {"words": script["advanced-words"][0]["result"]["words"]}

    @classmethod
    def scenario_report_web(cls, bridge):
        """gh signed in as someone else: the web's four steps, the names to type as text that can be selected."""
        cls.report_on(bridge)
        script = cls.opening(bridge, "en")
        script["advanced-report-build"] = [job("j1")]
        script["advanced-report-check"] = [job("j2")]
        script["advanced-report-job"] = [ok(BUILT), ok(WEB)]
        steps = [{"do": "snapshot", "reply": snapshot(on=1)}, {"do": "show"}, {"do": "choose", "id": REPORT},
                 {"do": "type", "into": "login", "text": "ExampleUser"}, {"do": "press", "button": "report_write"},
                 {"do": "poll"}, {"do": "press", "button": "report_check"}, {"do": "poll"}, {"do": "look"}]
        return "en", {"script": script, "steps": steps}, {"words": script["advanced-words"][0]["result"]["words"]}

    # ---------------------------------------------------------------- the compatibility report
    def report_card(self, look, words) -> list:
        """The report's card among the open capability's cards: under its heading's, which bears the capability's
        name - the same words, "Compatibility report", in English."""
        (card,) = [card for card in look["cards"][1:] if card and card[0] == words["page.report.title"]]
        return card

    def test_an_action_says_it_sends_nothing_to_codex_where_the_others_show_their_limits(self):
        result, expected = self.of("scenario_report_watched")
        words = expected["words"]
        (look,) = result["looks"]
        self.assertEqual(look["open"], REPORT)
        limits = next(card for card in look["cards"] if card[0] == words["page.limits"])
        self.assertIn(words["page.action_limits"], limits)
        self.assertNotIn(words["page.per_day"], limits)
        self.assertNotIn(words["page.nominal"], limits)
        cards = [card[0] for card in look["cards"]][1:]
        self.assertLess(cards.index(words["page.about"]), cards.index(words["page.report.title"]))
        self.assertLess(cards.index(words["page.report.title"]), cards.index(words["page.limits"]))

    def test_watched_the_report_is_written_and_saved_and_never_checked_or_sent(self):
        result, expected = self.of("scenario_report_watched")
        words = expected["words"]
        (look,) = result["looks"]
        card = self.report_card(look, words)
        self.assertIn(words["page.report.watched"], card)
        self.assertEqual(look["report"]["buttons"], {"write": True, "save": True, "check": None, "send": None})
        self.assertEqual(look["report"]["file"].replace("\r\n", "\n"), FILE)
        self.assertEqual(sent(result, "advanced-report-check"), [])
        self.assertEqual(sent(result, "advanced-report-build"), [{"login": "ExampleUser"}])

    def test_on_the_report_is_written_saved_checked_and_sent_only_on_exactly_the_word(self):
        result, expected = self.of("scenario_report_sent")
        words = expected["words"]
        looks = result["looks"]
        fresh, writing, written, saved, checking, checked, not_word, word, sending, still, done = looks
        self.assertEqual(fresh["report"]["buttons"], {"write": True, "save": None, "check": None, "send": None})
        self.assertEqual(sent(result, "advanced-report-build"), [{"login": "ExampleUser"}], "the login, trimmed")
        self.assertIn(words["page.report.writing"], self.report_card(writing, words))
        self.assertEqual((writing["report"]["kind"], writing["report"]["buttons"]["write"]), ("build", False))
        self.assertIn(SHA, written["report"]["boxes"])
        self.assertEqual(written["report"]["buttons"], {"write": True, "save": True, "check": True, "send": None})
        self.assertEqual(sent(result, "advanced-report-save"), [{"sha256": SHA, "path": "C:\\Reports\\codex-cli-0.158.0.json"}])
        self.assertEqual(saved["report"]["told"], words["page.report.saved"])
        self.assertEqual(sent(result, "advanced-report-check"), [{"sha256": SHA}])
        self.assertEqual((checking["report"]["kind"], checking["report"]["holds"]), ("check", 1))
        card = self.report_card(checked, words)
        self.assertIn(words["page.report.interrupted"], card)
        self.assertIn("• " + words["page.report.w.branch_new"].replace("{name}", BRANCH), card)
        self.assertIn(CHECKED["gh"], checked["report"]["boxes"])
        self.assertEqual(checked["report"]["holds"], 0, "the check let the reopen go")
        self.assertFalse(not_word["report"]["buttons"]["send"])
        self.assertIn("report_send", result["disabled"], "Send could not be pressed on any other word")
        self.assertTrue(word["report"]["buttons"]["send"])
        (request,) = sent(result, "advanced-report-send")
        self.assertEqual(request, {"sha256": SHA, "writes": WRITES, "word": "send"})
        self.assertEqual(set(request), set(surfaces.ARGUMENTS["advanced-report-send"]))
        self.assertEqual((sending["report"]["kind"], sending["report"]["holds"]), ("send", 1))
        self.assertIn(words["page.report.sending"], self.report_card(sending, words))
        self.assertTrue(sending["buttons"]["off"], "Turn off stays live while a send runs")
        self.assertEqual(still["report"]["holds"], 1)
        self.assertEqual((done["report"]["holds"], done["report"]["last"], done["report"]["job"]), (0, "sent", None))
        self.assertIn(SENT["url"], done["report"]["boxes"])
        self.assertIn(words["page.report.after"], self.report_card(done, words))
        self.assertEqual(sending["report"]["word"], "", "the word is typed again for every send")
        self.assertIsNone(done["report"]["word"], "no box for the word once the send has ended")

    def test_what_the_card_sends_is_what_the_real_bridge_takes(self):
        result, _ = self.of("scenario_report_sent")
        for command in ("advanced-report-build", "advanced-report-save", "advanced-report-check", "advanced-report-send",
                        "advanced-report-job"):
            with self.subTest(command):
                for request in sent(result, command):
                    self.assertEqual(set(request), set(surfaces.ARGUMENTS[command]))
        with tempfile.TemporaryDirectory() as home:
            bridge = Bridge(Path(home))
            try:
                self.report_on(bridge)
                for line in result["sent"]:
                    if line.startswith("advanced-report-"):
                        with self.subTest(line=line[:40]):
                            reply = bridge.request(line)
                            self.assertTrue(reply["ok"], reply)
                            self.assertNotEqual(reply["result"].get("refusal"), "invalid_request")
            finally:
                bridge.close()

    def test_a_send_it_cannot_account_for_is_lost_and_checking_again_is_the_way_to_tell(self):
        result, expected = self.of("scenario_report_lost")
        words = expected["words"]
        send_lost, check_lost = result["looks"]
        for look in (send_lost, check_lost):
            self.assertEqual((look["report"]["last"], look["report"]["holds"]), ("lost", 0))
            self.assertIn(words["page.report.lost"], self.report_card(look, words))
        self.assertEqual(result["told"], [], "a lost send is shown, never told as a refusal")

    def test_turned_off_mid_send_the_card_keeps_how_the_send_ended(self):
        result, expected = self.of("scenario_report_turned_off")
        words = expected["words"]
        sending, off, ended = result["looks"]
        self.assertTrue(sending["buttons"]["off"])
        self.assertEqual(sent(result, "advanced-disarm"), [{"capability": REPORT}])
        self.assertEqual(off["report"]["buttons"], {"write": None, "save": None, "check": None, "send": None})
        self.assertEqual(off["report"]["holds"], 1, "the send still runs, and still holds the reopen")
        card = self.report_card(ended, words)
        self.assertEqual(card[:2], [words["page.report.title"], words["page.report.last"]])
        self.assertIn(words["page.report.partial"], card)
        self.assertIn(words["page.report.refused.paused"], card)
        self.assertIn(words["page.report.again"], card)
        self.assertEqual(ended["report"]["holds"], 0)

    def test_on_the_web_the_names_to_type_can_be_selected_and_nothing_is_opened(self):
        result, expected = self.of("scenario_report_web")
        words = expected["words"]
        (look,) = result["looks"]
        card = self.report_card(look, words)
        self.assertIn(words["page.report.web.gh_other_login"].replace("{name}", "SomeoneElse"), card)
        self.assertIn(words["page.report.web.intro"].replace("{name}", "ExampleUser"), card)
        for step in ("1", "2", "3", "4"):
            self.assertIn("%s. %s" % (step, words["page.report.web." + step]), card)
        for name in (PROJECT, BRANCH, TARGET):
            self.assertIn(name, look["report"]["boxes"])
        self.assertIsNone(look["report"]["buttons"]["send"])


if __name__ == "__main__":
    unittest.main()
