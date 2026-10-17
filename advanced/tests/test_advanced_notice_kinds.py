"""This edition's kinds of notice, registered with core's registry as its plug is made (v0.6.16).

Core lists the kinds a person can keep on screen until clicked (codex_auto_resume/notice_kinds.py); an edition adds
its own through `register`, which this package calls from `create`, so the standard build names none of them. The
one this edition has is its usage meter's warning (issue #29), named by its notice's own title in every language.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT / "tests", ROOT / "advanced" / "src", ROOT / "src"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from codex_auto_resume import config, l10n, notice_kinds, notifier, settings  # noqa: E402
from codex_auto_resume_advanced import plug as advanced  # noqa: E402


class NoticeKindTests(unittest.TestCase):
    def setUp(self):
        held = patch.dict(notice_kinds._registered, clear=True)
        held.start()
        self.addCleanup(held.stop)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.paths = config.Paths(Path(folder.name) / "home")

    def test_making_the_plug_registers_the_usage_warning_in_every_language(self):
        self.assertIsNone(notice_kinds.kind_of("near_limit"))
        advanced.create(self.paths)
        kind = notice_kinds.kind_of("near_limit")
        self.assertIsNotNone(kind)
        self.assertEqual((kind.id, kind.notices), ("near_limit", ("near_limit",)))
        self.assertEqual(notice_kinds.ids()[-1], "near_limit", "after core's own")
        for locale in l10n.LOCALES:
            with self.subTest(locale=locale):
                self.assertEqual(kind.label(locale), l10n.text("msg.toast_near_limit", locale))
        advanced.create(self.paths)
        self.assertEqual(notice_kinds.ids().count("near_limit"), 1, "a second plug changes nothing")

    def test_its_notice_stays_when_chosen_and_the_window_is_given_its_words(self):
        advanced.create(self.paths)
        notice = notifier.build("near_limit", {"minutes": 300, "percent": 92, "reset_at": None},
                                stay=["near_limit"])
        self.assertTrue(notice.stays)
        self.assertFalse(notifier.build("near_limit", {"minutes": 300, "percent": 92, "reset_at": None}).stays)
        with patch.object(l10n, "current", lambda: "ko"):
            entry = [entry for entry in settings.describe() if entry["name"] == notice_kinds.FIELD][0]
        self.assertIn("near_limit", entry["kinds"])
        self.assertEqual(entry["labels"], {"near_limit": l10n.text("msg.toast_near_limit", "ko")})


if __name__ == "__main__":
    unittest.main()
