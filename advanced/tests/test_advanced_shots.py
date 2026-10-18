"""The Advanced features pictures' generator (build/advanced_shots.py), with no window and no Edge.

`NeedsTests`: what each picture needs is one table, and a need this tree lacks stops the run before anything is drawn.
`SeedTests`: the advanced edition's scratch installation, seeded through its own bridge and state - what the window is
then answered, the same every time, its times whole seconds. `JobTests`, `ComposeTests`: the render job each picture
is drawn by, and the picture laid in its still's caption and corners, written the same bytes every time.
`StalenessTests`, `MadeTests`: what a picture is made from moves with each of its inputs, and a made picture is the
one its manifest (assets/advanced-shots.json) records. The window itself is drawn by test_advanced_shots_render.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for _path in (str(ROOT / "advanced" / "src"), str(ROOT / "src"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import advanced_shots as shots_made  # noqa: E402
from advanced_shots import Need, Shot  # noqa: E402
# Imported here, before any pinned clock, as the advanced package's report tests import it before this module runs:
# the report a seed writes must still be stamped with the pinned clock (SeedTests' same-every-time).
from codex_auto_resume_advanced.report import flow as _report_flow  # noqa: E402,F401

BEFORE_AFTER = {"P1-before": "advanced-page-before", "P1-after": "advanced-page-after",
                "P4-before": "advanced-scheduled-before", "P4-after": "advanced-scheduled-after",
                "P5": "advanced-report", "P7-before": "advanced-pause-before", "P7-after": "advanced-pause-after",
                "P8": "advanced-usage-numbers"}


class NeedsTests(unittest.TestCase):
    def test_every_window_picture_of_before_after_is_listed_with_its_file(self):
        self.assertEqual({each.name: each.file for each in shots_made.SHOTS}, BEFORE_AFTER)
        self.assertEqual(shots_made.chosen(["P1"]), [shots_made.shot("P1-before"), shots_made.shot("P1-after")])
        with self.assertRaises(SystemExit):
            shots_made.chosen(["P2"])

    def test_each_kind_of_need_is_looked_for_in_this_tree(self):
        present = shots_made.present
        self.assertTrue(present(Need("capability", "compat_report", "")))
        self.assertFalse(present(Need("capability", "no_such_capability", "")))
        self.assertTrue(present(Need("option", "attempts", "")))
        self.assertFalse(present(Need("option", "no_such_option", "")))
        self.assertTrue(present(Need("command", "advanced-list", "")))
        self.assertFalse(present(Need("command", "advanced-no-such-command", "")))
        self.assertTrue(present(Need("module", "codex_auto_resume_advanced.engine.usage", "")))
        self.assertFalse(present(Need("module", "codex_auto_resume_advanced.engine.no_such_module", "")))
        self.assertTrue(present(Need("source", "advanced/gui/AdvancedRender.cs", "")))
        self.assertFalse(present(Need("source", "advanced/gui/NoSuchPage.cs", "")))
        self.assertFalse(present(Need("decision", "anything", "")), "a decision is made by writing it in, never found")
        with self.assertRaises(ValueError):
            present(Need("colour", "blue", ""))

    def test_a_picture_that_needs_what_this_tree_lacks_stops_the_run_before_anything_is_drawn(self):
        """Fails with `make` drawing without asking `require` first: the window would be compiled and run."""
        lacking = dict(shots_made.NEEDS, **{"P1-after": (Need("capability", "no_such_capability", "later"),)})
        with mock.patch.object(shots_made, "NEEDS", lacking), \
                mock.patch.object(shots_made, "compile_window", side_effect=AssertionError("drawn")) as compiled, \
                mock.patch.object(shots_made, "read_answers", side_effect=AssertionError("asked")):
            with self.assertRaisesRegex(shots_made.NotInThisTree, "not in this tree: P1-after needs capability "
                                                                  "no_such_capability"):
                shots_made.make([shots_made.shot("P1-after")], ("en",), ROOT / "nowhere", ROOT / "nowhere")
            compiled.assert_not_called()
            with self.assertRaisesRegex(SystemExit, "not in this tree"):
                shots_made.main(["P1-after", "--out", str(ROOT / "nowhere")])

    def test_what_beta4_brings_is_named_in_the_table_and_now_in_this_tree_every_picture_is_ready(self):
        """v0.6.16 final: beta.4 is merged and P7's and P8's decisions are written in (the module docstring), so no
        decision is left to hold a picture back and every picture this tree names can be drawn."""
        for name in ("P7-after", "P8"):
            with self.subTest(name):
                coming = [need for need in shots_made.NEEDS[name] if need.comes == shots_made.BETA4]
                self.assertTrue(coming, "what the picture shows of beta.4 is named")
        self.assertEqual([need for needs in shots_made.NEEDS.values() for need in needs if need.kind == "decision"], [])
        for each in shots_made.SHOTS:
            with self.subTest(each.name):
                self.assertEqual(shots_made.missing(each), [])
        # Every advanced picture names what it needs; a standard one needs nothing of the edition.
        for each in shots_made.SHOTS:
            self.assertEqual(each.name in shots_made.NEEDS, each.edition == "advanced", each.name)


class SeedTests(unittest.TestCase):
    """One seeded installation, read as the advanced window reads it in English with the report written."""

    @classmethod
    def setUpClass(cls):
        cls.read, cls.envelope = shots_made.read_answers("advanced", "base", "en", report=True)

    def answer(self, command, argument=None):
        for asked, given, reply in self.read:
            if asked == command and (argument is None or given == argument):
                return reply.get("result", reply)
        self.fail("%s %s was not read" % (command, argument))

    def test_the_seed_turns_on_and_watches_through_the_bridge_as_the_dashboard_does(self):
        listing = self.answer("advanced-list")
        states = {item["id"]: item["state"] for item in listing["capabilities"]}
        for capability, state in shots_made.BASE_TURNED:
            self.assertEqual(states[capability], shots_made.STATE_WORDS[state], capability)
        self.assertEqual(sum(state != "off" for state in states.values()), len(shots_made.BASE_TURNED))
        self.assertTrue(all(item["by"] == "dashboard" for item in listing["capabilities"] if item["state"] != "off"))

    def test_the_scheduled_message_the_credit_rule_and_the_queued_messages_are_the_page_s_to_show(self):
        import make_screenshots as shots
        rules = {rule["capability"]: rule for rule in self.answer("advanced-resets")["rules"]}
        self.assertEqual((rules["reset_message"]["words"], rules["reset_message"]["thread_id"]),
                         (shots_made.RESET_WORDS, shots.WINDOW_THREADS[0]))
        self.assertEqual((rules["reset_credit"]["minutes"], rules["reset_credit"]["ask_first"]), (300, True))
        prompts = self.answer("advanced-prompts")["prompts"]
        self.assertEqual([(prompt["trigger"], prompt["words"]) for prompt in prompts],
                         [("after_turn", shots_made.AFTER_TURN_WORDS), ("recurring", shots_made.DAILY_WORDS)])
        self.assertEqual((prompts[1]["at"], prompts[1]["every"], prompts[1]["occurrences"]),
                         (shots.ENVELOPE_NOW + shots_made.DAILY_AT, "day", shots_made.DAILY_TIMES))
        self.assertEqual([rule["tag"] for rule in self.answer("advanced-rules")["rules"]], [shots_made.RULE["tag"]])
        self.assertEqual([(sample["tag"], sample["count"]) for sample in self.answer("advanced-samples")["samples"]],
                         [("someNewCode", 2)])

    def test_the_report_is_written_and_checked_with_no_gh_and_its_jobs_named_for_what_they_are(self):
        self.assertEqual(self.answer("advanced-report-build")["job"], "report-build")
        built = self.answer("advanced-report-job", {"job": "report-build"})
        self.assertEqual((built["status"], built["login"]), ("built", shots_made.LOGIN))
        self.assertEqual(self.answer("advanced-report-check", {"sha256": built["sha256"]})["job"], "report-check")
        checked = self.answer("advanced-report-job", {"job": "report-check"})
        self.assertEqual((checked["status"], checked["why"]), ("web", "no_gh"))

    def test_every_capability_s_statement_and_watch_log_is_answered_in_the_page_s_own_request(self):
        """The page asks `{"capability":...,"locale":...}` in that order (AdvancedPage.LocaleArgument); the render mode
        matches a request's argument exactly, so another order would go unanswered."""
        preference = [reply.get("preference") for asked, _given, reply in self.read if asked == "strings"]
        self.assertEqual(preference, ["system"])
        form = shots_made.form_answers(self.read)["answers"]
        statements = {item["argument"] for item in form if item["command"] == "advanced-statement"}
        logs = {item["argument"] for item in form if item["command"] == "advanced-watch-log"}
        for item in self.answer("advanced-list")["capabilities"]:
            self.assertIn('{"capability":"%s","locale":"system"}' % item["id"], statements)
            self.assertEqual('{"capability":"%s"}' % item["id"] in logs, item["kind"] != "action", item["id"])
        self.assertIn({"command": "advanced-words", "argument": '{"locale":"system"}'},
                      [{"command": item["command"], "argument": item["argument"]} for item in form])

    def test_the_same_seed_is_answered_the_same_every_time(self):
        """Fails with the report's job ids left as drawn: they are random."""
        _read, again = shots_made.read_answers("advanced", "base", "en", report=True)
        self.assertEqual(again, self.envelope)

    def test_every_time_the_advanced_edition_answers_is_a_whole_second(self):
        """The window prints a time as its distance from the pinned moment (make_screenshots.capture_moment): a seed
        written at a fraction of a second would show a minute early."""
        def times(value, key=""):
            if isinstance(value, dict):
                for name, item in value.items():
                    yield from times(item, name)
            elif isinstance(value, list):
                for item in value:
                    yield from times(item, key)
            elif (key.endswith("_at") or key in ("at", "since", "until")) and isinstance(value, (int, float)) \
                    and not isinstance(value, bool):
                yield key, value
        found = [(key, value) for command, _argument, reply in self.read if command.startswith("advanced-")
                 for key, value in times(reply)]
        self.assertTrue(found)
        self.assertEqual([(key, value) for key, value in found if value != int(value)], [])

    def test_the_seed_writes_through_the_edition_s_own_code_and_no_sql_of_its_own(self):
        """So the seed follows the advanced state's schema as it moves (5, then 6 and 7), with no edit."""
        text = (ROOT / "build" / "advanced_shots.py").read_text(encoding="utf-8")
        for word in ("sqlite3", "execute(", "INSERT ", "UPDATE ", "CREATE TABLE"):
            self.assertNotIn(word, text)


class JobTests(unittest.TestCase):
    def test_each_picture_is_a_frame_of_its_page_capability_and_report_the_report_last(self):
        group = [shots_made.shot("P5"), shots_made.shot("P1-after"), shots_made.shot("P4-after")]
        data, order = shots_made.job(group, ("en", "ko"), {"en": {}, "ko": {}}, ROOT / "nowhere")
        self.assertEqual([(each.name, locale) for each, locale in order],
                         [("P1-after", "en"), ("P4-after", "en"), ("P5", "en"),
                          ("P1-after", "ko"), ("P4-after", "ko"), ("P5", "ko")])
        self.assertEqual([frame["index"] for frame in data["frames"]], list(range(6)))
        self.assertEqual(data["frames"][0], {"index": 0, "locale": "en", "page": "advanced", "light": 0,
                                             "capability": "compat_report"})
        self.assertEqual(data["frames"][1], {"index": 1, "locale": "en", "page": "pending", "light": 0})
        self.assertEqual(data["frames"][2]["report"], {"login": shots_made.LOGIN, "check": True})
        self.assertEqual(data["frames"][2]["show"], "report.file")
        self.assertEqual((data["theme"], data["design"], data["targets"]), ("light", "soft", []))

    def test_p8_is_the_meter_s_choices_card_with_a_number_of_its_own_on_the_five_hour_warning(self):
        """The P8 decision (STOP-NOTES): the meter on, its column scrolled to the Choices card, the five-hour warning
        holding a number of its own as its Custom... dialog leaves one (v0.6.16 final) - a number the card would take
        (its custom range), not a preset."""
        each = shots_made.shot("P8")
        data, _order = shots_made.job([each], ("en",), {"en": {}}, ROOT / "nowhere")
        self.assertEqual(data["frames"][0], {"index": 0, "locale": "en", "page": "advanced", "light": 0,
                                             "capability": "usage_meter", "show": "choices",
                                             "custom": {"key": "warn_five_hour", "value": "88"}})
        self.assertIn(("usage_meter", "armed"), shots_made.VARIANTS[each.variant]["turned"])
        read, _envelope = shots_made.read_answers("advanced", each.variant, "en")
        listing = [reply["result"] for command, _argument, reply in read if command == "advanced-list"][0]
        meter = [item for item in listing["capabilities"] if item["id"] == "usage_meter"][0]
        self.assertEqual(meter["state"], "armed")
        option = [option for option in meter["options"] if option["key"] == "warn_five_hour"][0]
        low, high = option["custom"]
        self.assertTrue(low <= int(each.custom[1]) <= high)
        self.assertNotIn(int(each.custom[1]), option["choices"], "a number of its own, beside the presets")
        self.assertIn("warn_weekly", [option["key"] for option in meter["options"]], "both windows")

    def test_p7_s_status_card_says_the_five_hour_window_at_96_and_the_recoveries_waiting(self):
        """The P7 decision (STOP-NOTES): the reason the Overview's status card shows near a limit is the window's own -
        the recoveries waiting under "Waiting" and the usage line with the five-hour window at 96 % and its reset -
        with the stop near a limit on, and nothing of the edition's own words."""
        each = shots_made.shot("P7-after")
        self.assertEqual((each.page, each.variant, each.show, each.custom), ("overview", "near_limit", None, None))
        read, _envelope = shots_made.read_answers("advanced", each.variant, "en")
        status = [reply["status"] for command, _argument, reply in read if command == "status"][0]
        windows = {window["window_minutes"]: window for window in status["watcher"]["usage"]["windows"]}
        self.assertEqual(windows[300]["used_percent"], 96)
        self.assertIsInstance(windows[300]["reset_at"], int)
        self.assertEqual(status["pending"], 2)
        listing = [reply["result"] for command, _argument, reply in read if command == "advanced-list"][0]
        states = {item["id"]: item["state"] for item in listing["capabilities"]}
        self.assertEqual((states["usage_meter"], states["usage_pause"]), ("armed", "armed"))

    def test_a_read_nobody_answered_or_anything_the_render_noted_stops_the_run(self):
        import motion_window
        for result, said in (({"misses": ["advanced-keep-going {}"], "notes": []}, "nobody answered"),
                             ({"misses": [], "notes": ["no control is called x"]}, "noted")):
            with self.subTest(said), mock.patch.object(motion_window, "render", return_value=dict(result, client=[1, 1],
                                                                                                    frames=[])):
                with self.assertRaisesRegex(RuntimeError, said):
                    shots_made.render(Path("x.exe"), {"out": "nowhere"}, Path("nowhere"))


def still(width=6, caption=2, client=3):
    rgb = bytes((10 + i) % 256 for i in range(width * (caption + client) * 3))
    alpha = bytearray(b"\xff" * (width * (caption + client)))
    alpha[-1] = alpha[-width] = 0
    return width, caption + client, rgb, bytes(alpha)


class ComposeTests(unittest.TestCase):
    def test_the_client_area_is_laid_under_the_still_s_caption_its_corners_kept(self):
        width, height, rgb, alpha = still()
        client = bytes([200] * (width * 3 * 3))
        made = shots_made.compose((width, height, rgb, alpha), client, (width, 3))
        self.assertEqual(made[:2], (width, height))
        self.assertEqual(made[2][:2 * width * 3], rgb[:2 * width * 3])
        self.assertEqual(made[2][2 * width * 3:], client)
        self.assertEqual(made[3], alpha)
        with self.assertRaises(ValueError):
            shots_made.compose((width, height, rgb, alpha), client, (width + 1, 3))

    def test_a_picture_is_written_the_same_bytes_every_time_and_reads_back_as_it_was_drawn(self):
        import make_screenshots as shots
        width, height, rgb, alpha = still()
        first = shots_made.png(width, height, rgb, alpha)
        self.assertEqual(first, shots_made.png(width, height, rgb, alpha))
        path = ROOT / "build" / "__advanced_shots_test.png"
        try:
            path.write_bytes(first)
            self.assertEqual(shots.read_png(path), (width, height, rgb, alpha))
        finally:
            path.unlink(missing_ok=True)


class StalenessTests(unittest.TestCase):
    def test_what_a_picture_is_made_from_moves_with_each_of_its_inputs(self):
        import make_screenshots as shots
        each = shots_made.shot("P4-after")
        before = shots_made.render_input(each, "envelope")
        self.assertEqual(shots_made.render_input(copy.deepcopy(each), "envelope"), before)
        self.assertNotEqual(shots_made.render_input(each, "another envelope"), before)
        self.assertNotEqual(shots_made.render_input(each._replace(capability="reset_credit"), "envelope"), before)
        with mock.patch.object(shots_made, "RESET_WORDS", "Other words."):
            self.assertNotEqual(shots_made.render_input(each, "envelope"), before)
        with mock.patch.object(shots_made, "NEEDS", dict(shots_made.NEEDS, **{"P4-after": ()})):
            self.assertNotEqual(shots_made.render_input(each, "envelope"), before)
        with mock.patch.object(shots, "window_digest", return_value="moved"):
            self.assertNotEqual(shots_made.render_input(each, "envelope"), before)
        real = shots.input_digest
        for path in ("advanced/gui/AdvancedResets.cs", "assets/screenshot-dashboard.png", "build/advanced_shots.py",
                     "build/motion_window.py"):
            with self.subTest(path), mock.patch.object(
                    shots, "input_digest", side_effect=lambda p, path=path: "moved" if Path(p) == ROOT / path else real(p)):
                self.assertNotEqual(shots_made.render_input(each, "envelope"), before)

    def test_a_standard_picture_does_not_move_with_the_advanced_window_s_sources(self):
        import make_screenshots as shots
        each = shots_made.shot("P4-before")
        before = shots_made.render_input(each, "envelope")
        real = shots.input_digest
        with mock.patch.object(shots, "input_digest", side_effect=lambda p: "moved"
                               if Path(p) == ROOT / "advanced/gui/AdvancedResets.cs" else real(p)):
            self.assertEqual(shots_made.render_input(each, "envelope"), before)


class MadeTests(unittest.TestCase):
    def test_a_made_picture_is_the_bytes_its_manifest_records_from_the_inputs_it_records(self):
        manifest = shots_made.read_manifest()
        for each in shots_made.SHOTS:
            for locale in shots_made.LOCALES:
                path = shots_made.target(each, locale)
                key = str(path.relative_to(ROOT)).replace("\\", "/")
                with self.subTest(key):
                    if not path.exists():
                        self.assertNotIn(key, manifest["images"])
                        continue
                    recorded = manifest["images"].get(key)
                    self.assertIsNotNone(recorded, "%s is not in assets/advanced-shots.json" % key)
                    self.assertEqual(recorded["sha256"], hashlib.sha256(path.read_bytes()).hexdigest(),
                                     "the picture is not the one made: run build/advanced_shots.py")
                    _read, envelope = shots_made.read_answers(each.edition, each.variant, locale, each.report)
                    self.assertEqual(manifest["inputs"].get(shots_made.manifest_key(each, locale)),
                                     shots_made.render_input(each, envelope),
                                     "what %s is made from moved: run build/advanced_shots.py" % key)
                    self.assertTrue(manifest["fidelity"] and all(result["passed"] for name, result in
                                                                 manifest["fidelity"].items() if name != "window"))


if __name__ == "__main__":
    unittest.main()
