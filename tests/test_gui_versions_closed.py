r"""Install another version closed before its list came (v0.6.26, plans/v0626-audit4/audit-gui.md C2).

The listing holds the window busy (SetBusy) while the installed bootstrap reads up to twenty pages of GitHub's list,
up to 430 seconds. Closing the dialog before the answer left that hold on: every action of the Dashboard grey and the
wait cursor on until the listing ended, with nothing on the screen to say why. Now the window is free the moment the
dialog closes; the listing, which only reads, runs on, and its answer, when it comes, acts on nothing - neither the
closed dialog nor the window's busy count, which the close ended already and which a later listing holds for itself.

Read from the window's own source by its braces (tests/guiscan.py); nothing is compiled or shown.
"""
from __future__ import annotations

import unittest

import guiscan


def body(name: str) -> str:
    return guiscan.member_body("SettingsForm", name)


class ClosedBeforeTheListTests(unittest.TestCase):
    def test_closing_the_dialog_ends_the_listings_wait_at_once(self):
        opened = body("OpenVersions")
        order = [opened.index(text) for text in ("StartVersionsListing(dialog, root, script);", "dialog.ShowDialog(this)",
                                                 "versionsToken++;", "EndVersionsWait();", "ConfirmPick(")]
        self.assertEqual(order, sorted(order), "after the dialog has closed, before anything is asked")
        # Outside the `using` block and before any return: however the dialog closed - Close, Esc, Install... - the
        # window's hold ends.
        after = opened[opened.index("dialog.ShowDialog(this)"):opened.index("EndVersionsWait();")]
        self.assertNotIn("return", after)

    def test_the_wait_is_ended_once_whichever_comes_first(self):
        ended = body("EndVersionsWait")
        self.assertLess(ended.index("if (!versionsWaiting) return;"), ended.index("versionsWaiting = false;"))
        self.assertLess(ended.index("versionsWaiting = false;"), ended.index("SetBusy(false);"))
        listing = body("StartVersionsListing")
        self.assertLess(listing.index("SetBusy(true);"), listing.index("versionsWaiting = true;"))
        self.assertLess(listing.index("versionsWaiting = true;"), listing.index("QueueUserWorkItem("))

    def test_a_late_answer_acts_on_nothing(self):
        listing = body("StartVersionsListing")
        apply = listing[listing.index("MethodInvoker apply"):]
        guard = apply.index("if (mine != versionsToken || dialog.IsDisposed) return;")
        self.assertNotIn("SetBusy(", apply, "only EndVersionsWait ends the listing's hold")
        self.assertLess(guard, apply.index("EndVersionsWait();"))
        self.assertLess(guard, apply.index("ShowVersionRows("))

    def test_the_only_release_of_the_listings_hold_is_end_versions_wait(self):
        source = (guiscan.ROOT / "gui" / "DashboardVersions.cs").read_text(encoding="utf-8")
        listing_part = source[source.index("private void OpenVersions()"):source.index("private void ShowVersionRows(")]
        self.assertEqual(listing_part.count("SetBusy(false);"), 1, "in EndVersionsWait alone")
        self.assertEqual(listing_part.count("SetBusy(true);"), 1, "as the listing starts")


if __name__ == "__main__":
    unittest.main()
