"""The Dashboard's Advanced features page in the window itself: the layout audit, share 4 of 5 of the languages.

The page is audited in this module's languages (pagecase.layout_languages(4)) at every scaling - each capability
open with every warning there is, then unread, the narrowest window on two screens (its tabs on the narrowest screen
too), the compatibility report's card in each of its states, and Pending's scheduled group - through the window's
own hook (AdvancedLayoutAudit in advanced/gui/AdvancedPageAudit.cs). The five layout modules together audit every
language; one file held them all and bounded a CI part (scripts/test_parts.py deals by file). The window is compiled
once for this module, and its replies are made by this edition's real bridge in a temporary home
(pagecase.LayoutCase), so nothing here reads the real installation, the real Software\\Policies keys or a real
Codex.

GUI test module: compiles real executables, so it runs on its own.

    PYTHONPATH=src;advanced/src python -m unittest discover -s advanced/tests -p test_advanced_page_layout_4.py
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pagecase  # noqa: E402
from pagecase import CSC, POWERSHELL  # noqa: E402


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class LayoutTests(pagecase.LayoutCase):
    """The page in this module's languages at five scalings."""

    LANGUAGES = pagecase.layout_languages(4)


if __name__ == "__main__":
    unittest.main()
