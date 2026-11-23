"""The near-limit notification names a window as every surface does, a whole-day one in days (v0.6.26, the third
audit's U3): notify.near_limit_content named 1440 minutes "24-hour" where the popup, the card, the panel and the
Dashboard say "1-day" (ui/words.window_name). Its own module."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import l10n, notify  # noqa: E402
from codex_auto_resume.ui import words  # noqa: E402


class NearLimitWindowNameTests(unittest.TestCase):
    def named(self, minutes, locale):
        say = lambda key, **fields: l10n.text(key, locale, **fields)  # noqa: E731
        return words.window_name(minutes, say)

    def test_a_window_is_named_as_the_popup_names_it_in_every_language(self):
        for locale in l10n.LOCALES:
            for minutes in (300, 1440, 2880, 10080, 90, None, 0):
                with self.subTest(locale=locale, minutes=minutes), patch.object(l10n, "current", return_value=locale):
                    content = notify.near_limit_content(minutes, 90, None)
                    self.assertIn(self.named(minutes, locale), content["body"])

    def test_a_whole_day_is_said_in_days(self):
        with patch.object(l10n, "current", return_value="en"):
            content = notify.near_limit_content(1440, 90, None)
        self.assertIn("1-day 10% left", content["body"])
        self.assertNotIn("24-hour", content["body"])


if __name__ == "__main__":
    unittest.main()
