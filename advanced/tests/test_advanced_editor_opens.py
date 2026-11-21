# ADVANCED-EDITION-CODE: in the advanced edition's tree, never the standard one's.
"""v0.6.24 final (live re-check 3, L5): Schedule a message... opens its editor as quickly as the Timeline opens.

The live re-check found the editor's window first on the screen about 2.5 s after Pending > Schedule... was pressed, with
no sign meanwhile that the press was taken; the Timeline faded in in 0.14 s on the same PC. Here the page's own button is
pressed through its hook (AdvancedPageRun's "editor_shown") with the real bridge's answers and a picker of many
conversations, and the editor is shown as ShowDialog shows a person's - made, held off the screen until painted, faded in
- but 30000 px off every screen and never activated, and timed from the press: built, made, first seen, opaque.

Where the time went, on this PC (Stopwatch marks and a sampler of the window's thread; the PC busy with other work, the
Timeline opening in 0.13 to 0.7 s the same way): BuildEditor laid the whole card out again for every row, line and value
put in it (BuildEditor took 1.2 to 3.3 s; 0.3 to 1.0 s laid out once); as the dialog was shown each of its five drop-downs handed its items to
its window with redrawing on (0.5 to 2.2 s for the five, 0.3 to 0.75 s with it off: SoftCombo.OnHandleCreated); and
each control that holds others laid itself out on being made visible, and the card, its body and its page with it,
eight times each (LayoutOnceShown). Pressed to on the screen, 4 rounds of 4 opens each way, interleaved: before 2.4 to
7.6 s, median 3.5 s (the live re-check's 2.5 s on a quiet PC); after 0.84 to 2.9 s, median 1.3 s. The rest is the
making of its hundred-odd windows, which must come first; the window's wait cursor shows from the press that it was
taken (OpenEditor).

The opening is held to SEEN_MEDIAN_MOST_MS, on the median of its opens (one open can meet a busy moment of the PC):
after, the medians of a round were 1.1 to 1.8 s; before, 2.8 to 4.3 s.

GUI test module: compiles real executables and shows a window off the screen, so it runs on its own (gui_lock.sh, one
module at a time).

    CODEX_AR_EDITION=advanced PYTHONPATH=src;advanced/src;tests python -m unittest advanced/tests/test_advanced_editor_opens.py
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase as ac  # noqa: E402
from pagecase import CSC, POWERSHELL, PageCase, snapshot  # noqa: E402
from codex_auto_resume_advanced import surfaces  # noqa: E402

# Conversations in the picker: the Dashboard's fullest lists and this many more in History, each its own conversation.
MORE_CONVERSATIONS = 60
# How long after the press the editor may first be on the screen (DWM no longer holding it off), in ms, on the median
# of its opens - after 1.1 to 1.8 s on this PC busy with other work, before 2.8 to 4.3 s (the docstring).
SEEN_MEDIAN_MOST_MS = 2200
# Opens: runs of the same press, the first one included (a window's first dialog builds what later ones reuse).
OPENS = 4


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class EditorOpensTests(PageCase):
    @classmethod
    def scenario_opens(cls, bridge):
        cls.watched(bridge, "prompt_queue", state="armed")
        reply = snapshot(on=1)
        base = reply["history"][0]
        for n in range(MORE_CONVERSATIONS):
            row = copy.deepcopy(base)
            row["thread_id"] = "%08x-0000-7000-8000-%012x" % (0x100 + n, n)
            row["interruption_id"] = "%064x" % (0x1000 + n)
            row["name"] = "conversation number %d about the release and its tests" % n
            reply["history"].append(row)
        reply["status"]["advanced"].update(surfaces.status(bridge.plug.runtime))
        script = cls.opening(bridge, "en")
        script["advanced-resets"] = [bridge("advanced-resets", {})]
        script["advanced-prompts"] = [bridge("advanced-prompts", {})]
        steps = [{"do": "snapshot", "reply": reply}, {"do": "page", "name": "pending"}]
        for _ in range(OPENS):
            steps += [{"do": "timeline_shown"}, {"do": "editor_shown"}]
        return "en", {"script": script, "steps": steps}, {"conversations": len(reply["pending"]) + len(reply["history"])}

    def opens(self):
        found, _expected = self.of("scenario_opens")
        shown = [record for record in found["dialogs"] if "seen" in record and record.get("kind") != "timeline"]
        self.assertEqual(len(shown), OPENS, found.get("disabled"))
        return shown

    def timelines(self):
        found, _expected = self.of("scenario_opens")
        shown = [record for record in found["dialogs"] if record.get("kind") == "timeline"]
        self.assertEqual(len(shown), OPENS, found.get("disabled"))
        return shown

    def test_print_the_opening_times(self):
        for n, record in enumerate(self.timelines()):
            print("\n[timeline %d] built %.0f, shown %.0f, seen %.0f, opaque %.0f ms"
                  % (n, record["built"], record["shown"], record["seen"], record["whole"]), end="")
        for n, record in enumerate(self.opens()):
            print("\n[editor %d] built %.0f, shown %.0f, seen %.0f, opaque %.0f ms (fades: %s)"
                  % (n, record["built"], record.get("shown", -1), record["seen"], record["whole"], record["fades"]), end="")

    def test_it_is_on_the_screen_within_its_budget_of_the_press(self):
        opens = self.opens()
        for n, record in enumerate(opens):
            with self.subTest(open=n):
                self.assertGreater(record["seen"], 0, "the editor came on the screen")
        seen = sorted(record["seen"] for record in opens)
        median = (seen[len(seen) // 2 - 1] + seen[len(seen) // 2]) / 2.0
        self.assertLessEqual(median, SEEN_MEDIAN_MOST_MS, "on the screen a median %.0f ms after the press: %s"
                             % (median, ", ".join("%.0f (built %.0f)" % (r["seen"], r["built"]) for r in opens)))

    def test_the_press_shows_at_once_that_it_was_taken(self):
        for n, record in enumerate(self.opens()):
            with self.subTest(open=n):
                self.assertTrue(record["waiting"], "the window's wait cursor from the press while the editor is made")
                self.assertFalse(record["waitingAfter"], "and off once the editor is on the screen")


if __name__ == "__main__":
    unittest.main()
