"""The Dashboard's Advanced features page in the window itself: the layout audit, share 5 of 5 of the languages.

The page is audited in this module's languages (pagecase.layout_languages(5)) at every scaling - each capability
open with every warning there is, then unread, the narrowest window on two screens (its tabs on the narrowest screen
too), the compatibility report's card in each of its states, and Pending's scheduled group - through the window's
own hook (AdvancedLayoutAudit in advanced/gui/AdvancedPageAudit.cs), with a canary that shows the audit finds what
does not fit. The five layout modules together audit every language; one file held them all and bounded a CI part
(scripts/test_parts.py deals by file). The window is compiled once for this module, and its replies are made by this
edition's real bridge in a temporary home (pagecase.LayoutCase), so nothing here reads the real installation, the
real Software\\Policies keys or a real Codex.

GUI test module: compiles real executables, so it runs on its own.

    PYTHONPATH=src;advanced/src python -m unittest discover -s advanced/tests -p test_advanced_page_layout_5.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pagecase  # noqa: E402
from pagecase import CSC, IDS, POWERSHELL  # noqa: E402


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class LayoutTests(pagecase.LayoutCase):
    """The page in this module's languages at five scalings - and a canary that shows the audit finds what does not
    fit."""

    LANGUAGES = pagecase.layout_languages(5)
    CANARY = True

    def test_the_audit_finds_what_does_not_fit(self):
        report = self.answer["canary"]["report"]
        self.assertIn("Label'WWWW", report, "a 400-character heading went unreported, so a quiet report proves nothing")
        self.assertRegex(report, r"advanced/%s/[^\n]*Label'NNNN[^\n]* :: needs " % IDS[0],
                         "a name 400 characters wide over the open capability's cards went unreported, so a quiet report "
                         "on them proves nothing")
        self.assertRegex(report, r"at the narrowest on the narrowest screen/[^\n]*NavButton'TTTT",
                         "a tab wider than the narrowest screen went unreported, so a quiet report on the tabs there "
                         "proves nothing")


if __name__ == "__main__":
    unittest.main()
