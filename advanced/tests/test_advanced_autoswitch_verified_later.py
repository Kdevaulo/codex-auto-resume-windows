"""v0.6.26 third round A2: a switch whose account read gave no answer (UNVERIFIED) and that a later look finds made is
settled as fully as one the switch itself saw made.

The later look's SWITCHED wrote switch.last alone: the target's seen_at and used_at stayed unset, so the card kept the old
account as the one in use (and refused Switch to this account on it, while the row of the account really in use ended
FAILED); the look journalled no "switched", where the same settling while the capability is off did; and between the
swap and that read the usage rule (engine/usage.of_account) did not know the account had changed.

Every home is a temporary folder and every sign-in file a fixture of no one's; the app, its restart and every read are
fakes (test_advanced_autoswitch_swap.SwapCase).

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests" python -m unittest test_advanced_autoswitch_verified_later
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_advanced_autoswitch import EngineCase  # noqa: E402
from test_advanced_autoswitch_swap import NOW, ONE, TWO  # noqa: E402
from test_advanced_autoswitch_unknown_read import UNKNOWN, Reads  # noqa: E402
from codex_auto_resume_advanced import profiles  # noqa: E402
from codex_auto_resume_advanced.codex import swap  # noqa: E402
from codex_auto_resume_advanced.control.autoswitch import _in_use  # noqa: E402
from codex_auto_resume_advanced.engine import usage  # noqa: E402
from codex_auto_resume_advanced.vocabulary import OptionKey  # noqa: E402


class VerifiedLater(EngineCase):
    def setUp(self):
        super().setUp()
        self.one = self.store.save(ONE, "one@example.com", "plus")
        self.store.update(self.one, seen_at=NOW - 600, used_at=NOW - 600)   # the account in use before the switch

    def unverified(self):
        """The switch to `two` made, its account read answering nothing: UNVERIFIED, the intent kept."""
        found = swap.switch(None, self.store, self.codex, self.two, restart=self.fake.restart,
                            read_real=Reads(self.fake, UNKNOWN), now=NOW)
        self.assertEqual(found, swap.UNVERIFIED)
        self.assertEqual((self.codex / "auth.json").read_bytes(), TWO)

    def test_the_card_shows_the_target_in_use_once_a_look_settles_it(self):
        """Fails with switch.last alone: in use = one | two seen_at None | two used_at None (the report's repro)."""
        self.unverified()
        self.look(rows=[])
        self.assertIsNone(self.store.intent())
        two = self.store.get(self.two)
        self.assertEqual((two["seen_at"], two["used_at"]), (NOW, NOW))
        self.assertEqual(_in_use([dict(self.store.get(key), id=key) for key in (self.one, self.two, self.three)]),
                         self.two)

    def test_the_look_journals_switched(self):
        """Fails without the count: settled while on it said nothing, settled while off it said "switched"."""
        self.unverified()
        self.look(rows=[])
        self.assertEqual(self.scoped.counted, ["switched"])
        self.assertEqual(self.scoped.stamps[str(OptionKey.AUTO_SWITCHED_AT)], NOW)


class TheUsageRuleKnowsTheChange(VerifiedLater):
    def paths(self):
        return SimpleNamespace(home=self.home)

    def rows(self):
        return {("codex", usage.FIVE_HOUR): {"bucket": "codex", "minutes": usage.FIVE_HOUR, "read_at": NOW - 10,
                                             "used_percent": 96.0, "reset_at": NOW + 3600}}

    def test_a_reading_before_the_swap_is_the_old_accounts_while_it_is_unverified(self):
        """Fails with switch.last alone: nothing was written at the swap, so the old account's 96 % stayed actionable for
        turns now running on the new account."""
        self.unverified()
        with patch.object(profiles, "Profiles", lambda home: self.store):
            self.assertEqual(usage.changed_at(self.paths()), NOW)
            self.assertEqual(usage.of_account(self.rows(), self.paths()), [])

    def test_with_no_switch_under_way_the_reading_stands(self):
        """A guard: no intent and no switch.last, no change (passes with the fix reverted)."""
        with patch.object(profiles, "Profiles", lambda home: self.store):
            self.assertIsNone(usage.changed_at(self.paths()))
            self.assertEqual(len(usage.of_account(self.rows(), self.paths())), 1)

    # The two tests of the card and the journal are VerifiedLater's; not run twice here.
    test_the_card_shows_the_target_in_use_once_a_look_settles_it = None
    test_the_look_journals_switched = None


if __name__ == "__main__":
    unittest.main()
