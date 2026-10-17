"""The Dashboard's Advanced features page in the window itself: the near-the-limit choices (v0.6.16-beta.4, the owner's
additions to issue #29) - the wrap-up's Custom wording for each window.

The window is compiled once for this module and every scenario_* below runs in one window process
(pagecase.PageCase); each makes its replies with this edition's real bridge in a home of its own, so nothing
here reads the real installation, the real Software\\Policies keys or a real Codex.

GUI test module: compiles real executables, so it runs on its own.

    PYTHONPATH=src;advanced/src python -m unittest discover -s advanced/tests -p test_advanced_page_usage.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pagecase import CSC, POWERSHELL, Bridge, PageCase, sent, snapshot  # noqa: E402

WRAP = "usage_wrap_up"
FIVE, WEEKLY = "wrap_custom_five_hour", "wrap_custom_weekly"


def custom_wording(bridge, five_hour=None):
    """The wrap-up's Wording set to Custom through the real bridge - and the five-hour window's words, where given."""
    generation = bridge("advanced-list", {})["result"]["generation"]
    done = bridge("advanced-option", {"capability": WRAP, "key": "wrap_style", "value": 5, "generation": generation})
    assert done["result"]["done"], done
    if five_hour is not None:
        done = bridge("advanced-wording", {"capability": WRAP, "key": FIVE, "words": five_hour,
                                           "generation": done["result"]["generation"]})
        assert done["result"]["done"], done


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class PageTests(PageCase):
    """The page driven as a person would, every scenario of this module in one window process."""

    @classmethod
    def scenario_wordings(cls, bridge):
        """Wrap up near a limit with Custom wording: a box for each window with the person's words - the five-hour
        one's, the weekly one empty - and Save words under each; the weekly words saved; words with a placeholder of no
        meaning refused by the bridge, and told why."""
        custom_wording(bridge, "Finish at {percent}% of {window}.")
        script = cls.opening(bridge, "en")
        script["advanced-wordings"] = [bridge("advanced-wordings", {"capability": WRAP})]
        refused = bridge("advanced-wording", {"capability": WRAP, "key": FIVE, "words": "Bad {prompt}",
                                              "generation": script["advanced-list"][0]["result"]["generation"]})
        steps = [{"do": "snapshot", "reply": snapshot()}, {"do": "show"}, {"do": "choose", "id": WRAP}, {"do": "look"},
                 {"do": "reply", "key": "advanced-wording", "with": [{"ok": True, "result": {"done": True}}]},
                 {"do": "wording", "key": WEEKLY, "text": "Weekly: stop at {stop_at}%."},
                 {"do": "reply", "key": "advanced-wording", "with": [refused]},
                 {"do": "wording", "key": FIVE, "text": "Bad {prompt}"}, {"do": "look"}]
        return "en", {"script": script, "steps": steps}, {
            "generation": script["advanced-list"][0]["result"]["generation"], "refused": refused["result"],
            "words": script["advanced-words"][0]["result"]["words"],
            "previews": script["advanced-wordings"][0]["result"]["previews"]}

    @classmethod
    def scenario_standard_wording(cls, bridge):
        """Wrap up near a limit with the standard wording: no boxes."""
        script = cls.opening(bridge, "en")
        script["advanced-wordings"] = [bridge("advanced-wordings", {"capability": WRAP})]
        steps = [{"do": "snapshot", "reply": snapshot()}, {"do": "show"}, {"do": "choose", "id": WRAP}, {"do": "look"}]
        return "en", {"script": script, "steps": steps}, {
            "words": script["advanced-words"][0]["result"]["words"],
            "previews": script["advanced-wordings"][0]["result"]["previews"]}

    @classmethod
    def scenario_custom_numbers(cls, bridge):
        """(f): the five-hour wrap-up percentage typed in as 93 through the real bridge - shown as itself, Custom... last;
        then the weekly one typed in as 88 and set; then letters typed in, refused before anything is sent."""
        generation = bridge("advanced-list", {})["result"]["generation"]
        done = bridge("advanced-option", {"capability": WRAP, "key": "wrap_five_hour", "value": 93, "generation": generation})
        assert done["result"]["done"], done
        script = cls.opening(bridge, "en")
        script["advanced-wordings"] = [bridge("advanced-wordings", {"capability": WRAP})]
        steps = [{"do": "snapshot", "reply": snapshot()}, {"do": "show"}, {"do": "choose", "id": WRAP}, {"do": "look"},
                 {"do": "reply", "key": "advanced-option", "with": [{"ok": True, "result": {"done": True}}]},
                 {"do": "custom_option", "key": "wrap_weekly", "text": "88"},
                 {"do": "custom_option", "key": "wrap_weekly", "text": "eighty"}, {"do": "look"}]
        return "en", {"script": script, "steps": steps}, {
            "generation": script["advanced-list"][0]["result"]["generation"],
            "words": script["advanced-words"][0]["result"]["words"]}

    @classmethod
    def scenario_order(cls, bridge):
        """(j): a forced stop below the words' stop taken, and said; a wrap-up above the words' stop refused, and told."""
        script = cls.opening(bridge, "en")
        generation = script["advanced-list"][0]["result"]["generation"]
        taken = bridge("advanced-option", {"capability": "usage_pause", "key": "pause_five_hour", "value": 92,
                                           "generation": generation})
        refused = bridge("advanced-option", {"capability": WRAP, "key": "wrap_weekly", "value": 96,
                                             "generation": taken["result"]["generation"]})
        steps = [{"do": "snapshot", "reply": snapshot()}, {"do": "show"}, {"do": "choose", "id": "usage_pause"},
                 {"do": "reply", "key": "advanced-option", "with": [taken]},
                 {"do": "set_option", "key": "pause_five_hour", "value": 97}, {"do": "look"},
                 {"do": "choose", "id": WRAP}, {"do": "reply", "key": "advanced-option", "with": [refused]},
                 {"do": "set_option", "key": "wrap_weekly", "value": 96}]
        script["advanced-wordings"] = [bridge("advanced-wordings", {"capability": WRAP})]
        return "en", {"script": script, "steps": steps}, {
            "taken": taken["result"], "refused": refused["result"], "words": script["advanced-words"][0]["result"]["words"]}

    @classmethod
    def scenario_switches(cls, bridge):
        """v0.6.16 final: the on/off choices drawn as switches - the meter's two windows, the wrap-up's Include the reset
        time and Continue after the reset. The five-hour one pressed as UI Automation presses it, the weekly one by Space;
        each sends Off with the generation the page read, and the page is drawn again from the list it reads - here the
        same list, so both switches still show On: a switch moves only once the change is taken. Asked for the value it
        already shows, nothing is sent."""
        script = cls.opening(bridge, "en")
        script["advanced-wordings"] = [bridge("advanced-wordings", {"capability": WRAP})]
        steps = [{"do": "snapshot", "reply": snapshot()}, {"do": "show"}, {"do": "choose", "id": "usage_meter"},
                 {"do": "look"},
                 {"do": "reply", "key": "advanced-option", "with": [{"ok": True, "result": {"done": True}}]},
                 {"do": "set_option", "key": "window_five_hour", "value": 2},
                 {"do": "set_option", "key": "window_weekly", "value": 2, "by": "keyboard"},
                 {"do": "set_option", "key": "window_weekly", "value": 1}, {"do": "look"},
                 {"do": "choose", "id": WRAP}, {"do": "look"}]
        return "en", {"script": script, "steps": steps}, {
            "generation": script["advanced-list"][0]["result"]["generation"],
            "words": script["advanced-words"][0]["result"]["words"]}

    def test_on_off_choices_are_switches_that_move_only_once_the_change_is_taken(self):
        result, expected = self.of("scenario_switches")
        words = expected["words"]
        first, after, wrap = result["looks"]
        self.assertEqual(first["switches"], [
            {"key": key, "on": True, "enabled": True, "name": words["page.option." + key], "role": "CheckButton"}
            for key in ("window_five_hour", "window_weekly")])
        self.assertEqual([choice["key"] for choice in first["choices"]], ["poll_minutes", "warn_five_hour", "warn_weekly"],
                         "no on/off choice is a drop-down")
        self.assertEqual(sent(result, "advanced-option"), [
            {"capability": "usage_meter", "key": key, "value": 2, "generation": expected["generation"]}
            for key in ("window_five_hour", "window_weekly")])
        self.assertEqual([each["on"] for each in after["switches"]], [True, True], "drawn from what the list says")
        self.assertEqual(result["disabled"], [])
        # v0.6.16 final: the wrap-up's own pair of window switches, after its other two.
        self.assertEqual([each["key"] for each in wrap["switches"]],
                         ["wrap_reset_time", "wrap_after_reset", "window_five_hour", "window_weekly"])
        self.assertEqual([each["name"] for each in wrap["switches"]][2:],
                         [words["page.option.window_five_hour"], words["page.option.window_weekly"]])
        self.assertFalse({each["key"] for each in wrap["switches"]} & {choice["key"] for choice in wrap["choices"]})
        self.assertEqual({each["role"] for each in wrap["switches"]}, {"CheckButton"})
        for look in (first, wrap):
            self.assertNotIn(words["page.option.no_window"], next(card for card in look["cards"]
                                                                   if card[0] == words["page.options"]))

    @classmethod
    def scenario_no_window(cls, bridge):
        """v0.6.16 final: Stop near a limit with both its windows switched off through the real bridge, and the meter
        with its weekly one alone off."""
        generation = bridge("advanced-list", {})["result"]["generation"]
        for capability, key in (("usage_pause", "window_five_hour"), ("usage_pause", "window_weekly"),
                                ("usage_meter", "window_weekly")):
            done = bridge("advanced-option", {"capability": capability, "key": key, "value": 2, "generation": generation})
            assert done["result"]["done"], done
            generation = done["result"]["generation"]
        script = cls.opening(bridge, "en")
        steps = [{"do": "snapshot", "reply": snapshot()}, {"do": "show"}, {"do": "choose", "id": "usage_pause"},
                 {"do": "look"}, {"do": "choose", "id": "usage_meter"}, {"do": "look"}]
        return "en", {"script": script, "steps": steps}, {"words": script["advanced-words"][0]["result"]["words"]}

    def test_a_capability_with_both_windows_off_says_it_acts_on_neither(self):
        result, expected = self.of("scenario_no_window")
        words = expected["words"]
        stop, meter = result["looks"]
        self.assertEqual([(each["key"], each["on"]) for each in stop["switches"]],
                         [("window_five_hour", False), ("window_weekly", False)])
        self.assertIn(words["page.option.no_window"], next(card for card in stop["cards"] if card[0] == words["page.options"]))
        self.assertEqual([(each["key"], each["on"]) for each in meter["switches"]],
                         [("window_five_hour", True), ("window_weekly", False)])
        self.assertNotIn(words["page.option.no_window"],
                         next(card for card in meter["cards"] if card[0] == words["page.options"]), "one window is on")

    def test_out_of_order_is_told_and_a_forced_stop_below_the_words_is_said(self):
        result, expected = self.of("scenario_order")
        words = expected["words"]
        self.assertEqual(expected["taken"]["warning"], "stop_before_words")
        self.assertEqual(expected["refused"]["refusal"], "option_order")
        (look,) = result["looks"]
        self.assertEqual(look["note"], words["page.warn.stop_before_words"])
        self.assertEqual(result["told"], [words["page.refused.option_order"]])

    def test_a_number_can_be_typed_in_beside_the_presets_and_is_checked_before_it_is_sent(self):
        result, expected = self.of("scenario_custom_numbers")
        words = expected["words"]
        first, after = result["looks"]
        five = next(choice for choice in first["choices"] if choice["key"] == "wrap_five_hour")
        self.assertEqual((five["value"], five["items"][-2:]), ("93%", ["93%", words["page.option.custom"]]))
        style = next(choice for choice in first["choices"] if choice["key"] == "wrap_style")
        self.assertNotIn(words["page.option.custom"], style["items"], "a wording is no number")
        self.assertEqual(first["custom"]["wrap_weekly"], False, "the box shows only once Custom... is chosen")
        self.assertTrue(after["custom"]["wrap_weekly"])
        self.assertEqual(sent(result, "advanced-option"), [
            {"capability": WRAP, "key": "wrap_weekly", "value": 88, "generation": expected["generation"]}])
        self.assertEqual(result["told"], [words["page.refused.option_range"].replace("{low}", "1").replace("{high}", "100")])

    def test_custom_wording_has_a_box_for_each_window_with_the_persons_words(self):
        result, expected = self.of("scenario_wordings")
        words = expected["words"]
        first, after = result["looks"]
        self.assertEqual(first["wordings"], {FIVE: "Finish at {percent}% of {window}.", WEEKLY: ""})
        choices = next(card for card in first["cards"] if card[0] == words["page.options"])
        for key in ("page.wording.help", "page.wording." + FIVE, "page.wording." + WEEKLY):
            self.assertIn(words[key], choices)
        self.assertEqual(sent(result, "advanced-wording"), [
            {"capability": WRAP, "key": WEEKLY, "words": "Weekly: stop at {stop_at}%.", "generation": expected["generation"]},
            {"capability": WRAP, "key": FIVE, "words": "Bad {prompt}", "generation": expected["generation"]}])
        self.assertEqual(expected["refused"]["problem"], "placeholder")
        self.assertEqual(result["told"], [words["page.refused.wording.placeholder"]])
        self.assertEqual(after["note"], words["page.done.wording"].replace("{name}", words["name." + WRAP]))

    def test_the_standard_wording_has_no_boxes(self):
        result, _ = self.of("scenario_standard_wording")
        (look,) = result["looks"]
        self.assertEqual(look["wordings"], {})

    def test_what_is_sent_is_shown_under_the_choice_for_each_window(self):
        """(a): under the wording choice, for each window, the words the bridge says would be sent - exactly."""
        for name in ("scenario_standard_wording", "scenario_wordings"):
            with self.subTest(name):
                result, expected = self.of(name)
                words, previews = expected["words"], expected["previews"]
                look = result["looks"][0]
                self.assertEqual(look["previews"], [words["page.preview.300"] + "\r\n" + previews["300"],
                                                    words["page.preview.10080"] + "\r\n" + previews["10080"]])
                choices = next(card for card in look["cards"] if card[0] == words["page.options"])
                self.assertIn(words["page.preview.title"], choices)

    def test_what_save_words_sends_is_what_the_real_bridge_takes(self):
        with tempfile.TemporaryDirectory() as home:
            bridge = Bridge(Path(home))
            try:
                custom_wording(bridge, "Finish at {percent}% of {window}.")      # as the scenario's home was made
                line = next(line for line in self.of("scenario_wordings")[0]["sent"] if line.startswith("advanced-wording "))
                self.assertTrue(bridge.request(line)["result"]["done"])
                read = bridge("advanced-wordings", {"capability": WRAP})["result"]
                self.assertEqual(read["wordings"][WEEKLY], "Weekly: stop at {stop_at}%.")
            finally:
                bridge.close()


if __name__ == "__main__":
    unittest.main()
