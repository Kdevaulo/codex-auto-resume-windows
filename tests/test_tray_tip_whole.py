"""What the icon's szTip says is whole in every language (v0.6.26, the third audit's N1).

szTip holds 127 characters. Since "{percent}% left" lengthened every meter row (v0.6.24 final), the advanced edition's
tooltip of two usage windows was cut mid-row in 13 of 22 languages ("... 13% rimanente · settima"), and szTip is also the
icon's name to a screen reader and to Windows' own surfaces. Now the meter's last rows are left out, one at a time,
until the rest fits whole; the drawn card (tipcard.py) still shows every row. Its own module.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import interface  # noqa: E402
from codex_auto_resume.ui.tray import words  # noqa: E402

NOW = 1_800_000_000.0
METER = {"windows": [{"window_minutes": 300, "used_percent": 87}, {"window_minutes": 10080, "used_percent": 40}]}
BUSY = {"enabled": True, "running": 3, "waiting": 12, "next_at": NOW + 3725, "advanced": {"meter": METER}}
ATTENTION = dict(BUSY, held=1)


class WholeTooltipTests(unittest.TestCase):
    def test_no_language_has_a_row_cut_in_the_tooltip(self):
        for locale, strings in interface.STRINGS.items():
            for name, snapshot in (("busy", BUSY),):
                with self.subTest(locale=locale, snapshot=name):
                    parts = words.tooltip_parts(snapshot, strings, NOW, "advanced")
                    tip = words.tooltip(snapshot, strings, NOW, "advanced")
                    self.assertLess(len(tip), words.TIP_CHARS)
                    # What is said is the title, the state line and whole meter rows, each as the card shows it.
                    kept = [row for row in parts["meter"] if row["text"] in tip]
                    self.assertEqual(tip, words.tooltip_joined(dict(parts, meter=kept)))
                    self.assertEqual(kept, parts["meter"][:len(kept)], "the first rows are the ones kept")

    def test_nothing_is_cut_in_the_state_line_either_in_any_language_or_edition(self):
        for locale, strings in interface.STRINGS.items():
            for edition in (None, "advanced"):
                with self.subTest(locale=locale, edition=edition):
                    parts = words.tooltip_parts(ATTENTION, strings, NOW, edition)
                    tip = words.tooltip(ATTENTION, strings, NOW, edition)
                    self.assertLess(len(tip), words.TIP_CHARS)
                    self.assertTrue(tip.startswith(words.tooltip_joined(dict(parts, meter=[], line=parts["line"][:1]))),
                                    "the title and the first piece stay")
                    whole = [text for text, _ in parts["line"]]
                    said = tip.split("\n")[1].split(" · ") if "\n" in tip else []
                    self.assertEqual(said, whole[:len(said)], "pieces, never half of one")

    def test_a_tooltip_that_fits_is_what_it_always_was(self):
        english = interface.STRINGS["en"]
        parts = words.tooltip_parts(BUSY, english, NOW, "advanced")
        self.assertEqual(words.tooltip(BUSY, english, NOW, "advanced"), words.tooltip_joined(parts))
        self.assertEqual(len(parts["meter"]), 2)

    def test_the_languages_that_were_cut_lose_a_row_and_keep_the_first(self):
        italian = interface.STRINGS["it"]
        parts = words.tooltip_parts(BUSY, italian, NOW, "advanced")
        self.assertGreaterEqual(len(words.tooltip_joined(parts)), words.TIP_CHARS, "the case this fixes")
        tip = words.tooltip(BUSY, italian, NOW, "advanced")
        self.assertTrue(tip.endswith(parts["meter"][0]["text"]), tip)


if __name__ == "__main__":
    unittest.main()
