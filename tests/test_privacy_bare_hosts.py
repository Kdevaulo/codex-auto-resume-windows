"""C3 sees a host written without a scheme too (v0.6.26, the third audit's T4).

docs/STANDARDS.md C3 says the shipped files name no unexpected host, and test_privacy_claims checks only hosts written
as URLs (`https://...`). Two comments named one bare - the lunar table's source (brand/days.py) and the squircle's
article (brand/shape.py) - and a third a documentation address (mcp/tools.py), which nothing connects to, but which the
sentence's letter forbids. Now a host written as a name is looked for as well, in what ships - the window's sources
and the skills too (the review's W2: the advanced page's example named example.com where the card shows the address masked,
domain and all) - and only the hosts the product has a reason to name stand: GitHub's, python.org's, ChatGPT's
(pinned, handed to Codex), the Windows `chcp.com`,
and, in the advanced edition's package, the courier's two. Its own module; the lookup knows a name by its ending
(com, org, net, kr, gov, hk, edu, io, ai), so `args.dev` and `self.app` are not read as hosts.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from test_privacy_claims import tracked  # noqa: E402

BARE_HOST = re.compile(r"\b(?:[a-z0-9]+(?:-[a-z0-9]+)*\.)+(?:com|org|net|kr|gov|hk|edu|io|ai)\b")
ALLOWED = re.compile(r"^(?:(?:api|raw|objects|release-assets)\.)?github(?:usercontent)?\.com$|^(?:www\.)?python\.org$"
                     r"|^chatgpt\.com$|^chcp\.com$|^agent-plugins\.org$|^(?:schemas|docs|learn)\.microsoft\.com$")
COURIER_ONLY = re.compile(r"^(?:api\.telegram\.org|status\.openai\.com)$")
ADVANCED = "advanced/src/"


def bare_hosts():
    found = []
    for path in (tracked("scripts/*") + tracked("build/install/*") + tracked("src/*") + tracked("advanced/src/*")
                 + tracked("gui/*") + tracked("advanced/gui/*") + tracked("skills/*") + tracked("advanced/skills/*")):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        name = str(path.relative_to(ROOT)).replace("\\", "/")
        for host in set(BARE_HOST.findall(text)):
            if ALLOWED.match(host) or (name.startswith(ADVANCED) and COURIER_ONLY.match(host)):
                continue
            found.append("%s: %s" % (name, host))
    return sorted(found)


class BareHostTests(unittest.TestCase):
    def test_no_shipped_file_names_a_host_the_product_has_no_reason_to(self):
        self.assertEqual(bare_hosts(), [], "a shipped file names a host without a scheme that we do not expect")

    def test_the_lookup_sees_what_it_is_for(self):
        for sample, expected in (("the Institute, astro.kasi.re.kr) computes", ["astro.kasi.re.kr"]),
                                 ("(figma.com/blog)", ["figma.com"]), ("args.dev self.app.logger.info", [])):
            self.assertEqual(BARE_HOST.findall(sample), expected, sample)
        self.assertIsNone(ALLOWED.match("figma.com"))
        self.assertIsNone(ALLOWED.match("github.com.example.org"))
        self.assertIsNotNone(ALLOWED.match("raw.githubusercontent.com"))


if __name__ == "__main__":
    unittest.main()
