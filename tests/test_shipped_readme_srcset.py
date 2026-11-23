"""The archive's README makes a <picture>'s srcset absolute too (v0.6.26).

The README opens with a <picture> whose <source> for a dark theme names assets/logo-motion-dark.png in srcset=, a file the
archive does not carry. build/make_release.py absolute_links rewrote src= and href= but not srcset=, and a browser that
takes a <source> never falls back to its <img>: in a dark viewer the installed README's logo was broken. Every candidate of
a srcset is now rewritten as a src= is, and what the archive carries, an address and a link inside the page stay.

Nothing here reaches the network, an installation or the registry.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_shipped_readme_links import REPOSITORY, builder  # noqa: E402

AT = REPOSITORY + "/raw/v2.1.0-beta.3/"


class SrcsetTests(unittest.TestCase):
    CARRIED = {"assets/logo.png", "LICENSE"}

    def setUp(self):
        self.make = builder()

    def rewrite(self, text):
        return self.make.absolute_links(text, "2.1.0-beta.3", self.CARRIED)

    def test_the_dark_logos_source_is_a_raw_address_at_the_tag(self):
        text = ('<picture>\n  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-motion-dark.png">\n'
                '  <img src="assets/logo-motion.png" alt="x" width="96">\n</picture>\n')
        self.assertEqual(self.rewrite(text),
                         '<picture>\n  <source media="(prefers-color-scheme: dark)" srcset="%sassets/logo-motion-dark.png">\n'
                         '  <img src="%sassets/logo-motion.png" alt="x" width="96">\n</picture>\n' % (AT, AT))

    def test_every_candidate_is_rewritten_and_its_descriptor_kept(self):
        self.assertEqual(self.rewrite("<img srcset='docs/images/a.png 1x,docs/images/b.png 2x, assets/logo.png 3x'>"),
                         "<img srcset='%sdocs/images/a.png 1x,%sdocs/images/b.png 2x, assets/logo.png 3x'>" % (AT, AT))

    def test_an_address_and_what_the_archive_carries_stay(self):
        for text in ('<source srcset="https://example.org/a.png">', '<source srcset="assets/logo.png">',
                     '<source srcset="#here">', '<source srcset="">'):
            self.assertEqual(self.rewrite(text), text)

    def test_the_rewrite_is_done_once(self):
        once = self.rewrite('<source srcset="assets/logo-motion-dark.png"><img src="docs/images/a.png">')
        self.assertEqual(self.rewrite(once), once)
        self.assertEqual(once.count(REPOSITORY), 2)


if __name__ == "__main__":
    unittest.main()
