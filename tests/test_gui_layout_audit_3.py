"""The window's layout audit in share 3 of tests/test_gui_layout.py's AUDIT_MODULES shares of the languages.

Every page of the real window, at its opening size, at five scalings, in this module's languages
(test_gui_layout.audit_share(3)): nothing cut off, the header's light, the save card's note, the buttons in their corners,
the lists, the Overview through the watcher's states and in its shortest window, Right now's names - the tests in
test_gui_layout.PER_LANGUAGE, over the same probe, which here runs those audits alone. tests/test_gui_layout.py audits the
first share and holds the rest; one file held all 22 languages and was the slowest of every lane (v0.6.26 audit Z2).

GUI test module (it compiles the window and builds windows that are never shown): run on its own, through gui_lock.sh.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_gui_layout  # noqa: E402

LayoutAuditShareTests = test_gui_layout.share_case(3, __name__)


if __name__ == "__main__":
    unittest.main()
