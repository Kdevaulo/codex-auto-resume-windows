"""The Codex panel's header reads as one line to the eye (v0.6.24 final), as the icon's card's does.

The owner, 2026-11-18, of the hover card's first row: "여기도 정렬이 안 맞아보여" - and the same was asked of every header
with that pattern. The panel's has it twice: the light beside the state word (".hero-state": the light and an h1), and
the edition's word after the version in the line above it (".eyebrow .edition").

The light was centred on the word's line box by `align-items: center`, which put its centre 3.4 CSS px above the word's
x-height middle (3.4, 4.1 and 6.8 device pixels at 100, 150 and 200%). Now the row aligns by baselines and the light moves
down by half its height less half the word's x-height (panel.css, `.hero-state > .halo`). The edition's word was already
on the version's baseline (`vertical-align: baseline`); this holds it there.

Laid out by a real browser engine (headless Edge, where it is installed; nothing on the screen and no picture): the
page measures itself - the light's box, the word's baseline (a zero-height inline box at it) and the word's x-height
(the font's own "x", measureText's ink ascent) - at device scale factors 1, 1.5 and 2, in light and dark, at a wide and a
narrow panel. Each is held to under 1 device pixel.
"""
from __future__ import annotations

import html as html_text
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codex_auto_resume import l10n  # noqa: E402
from codex_auto_resume.mcp import panel as mcpui  # noqa: E402
from test_mcpui_v064 import snapshot  # noqa: E402
from test_panel_access import EDGE  # noqa: E402

PROBE = "CAR-HEAD-PROBE:"
SCRIPT = r"""<script>window.addEventListener('load',function(){setTimeout(function(){
function base(el){var m=document.createElement('span');m.style.cssText='display:inline-block;width:0;height:0;vertical-align:baseline';
  el.appendChild(m);var y=m.getBoundingClientRect().top;m.remove();return y;}
function xh(el){var s=getComputedStyle(el);var c=document.createElement('canvas').getContext('2d');
  c.font=s.fontStyle+' '+s.fontWeight+' '+s.fontSize+' '+s.fontFamily;return c.measureText('x').actualBoundingBoxAscent;}
var h=document.querySelector('.hero-state h1'),d=document.querySelector('.hero-state .halo'),
    e=document.querySelector('.hero .eyebrow'),p=e&&e.querySelector('.edition'),r=d.getBoundingClientRect();
document.title='%s'+JSON.stringify({dpr:devicePixelRatio,dot:(r.top+r.bottom)/2,base:base(h),xh:xh(h),
  eyebrow:e?base(e):null,edition:p?base(p):null});
},300);});</script>""" % PROBE
SCALES = (1, 1.5, 2)
THEMES = ("light", "dark")
WIDTHS = (900, 480)


def measure(scale, theme, width):
    data = snapshot()
    data["status"]["edition"] = "advanced"
    with unittest.mock.patch.object(l10n, "preference", lambda: "en"), \
            unittest.mock.patch("codex_auto_resume.interface.language", lambda: "en"):
        page = mcpui.settings_page(data, theme=theme, design="soft", text=1)
    with tempfile.TemporaryDirectory() as folder:
        probe = Path(folder) / "panel.html"
        probe.write_text(page.replace("</body>", SCRIPT + "</body>"), encoding="utf-8")
        done = subprocess.run([str(EDGE / "Microsoft/Edge/Application/msedge.exe"), "--headless=new", "--disable-gpu",
                               "--hide-scrollbars", "--virtual-time-budget=3000", "--user-data-dir=" + folder + "/p",
                               "--force-device-scale-factor=%s" % scale, "--window-size=%d,1200" % width, "--dump-dom",
                               probe.as_uri()], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for piece in done.stdout.split(PROBE)[1:]:
        try:
            return json.loads(html_text.unescape(piece.split("</title>", 1)[0]))
        except ValueError:
            continue
    raise AssertionError("the browser said nothing: " + done.stderr[-1500:])


@unittest.skipUnless(EDGE is not None, "needs Microsoft Edge to lay the page out")
class PanelHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.found = {(scale, theme, width): measure(scale, theme, width)
                     for scale in SCALES for theme in THEMES for width in WIDTHS}

    def test_the_light_is_centred_on_the_state_words_x_height_middle(self):
        for (scale, theme, width), found in self.found.items():
            with self.subTest(scale=scale, theme=theme, width=width):
                self.assertEqual(found["dpr"], scale)
                off = (found["dot"] - (found["base"] - found["xh"] / 2.0)) * found["dpr"]
                self.assertLess(abs(off), 1.0, "the light %.2f device px from the x-height middle" % off)

    def test_the_editions_word_is_on_the_versions_baseline(self):
        for (scale, theme, width), found in self.found.items():
            with self.subTest(scale=scale, theme=theme, width=width):
                self.assertIsNotNone(found["edition"], "the advanced edition's word is in the heading")
                self.assertLess(abs(found["edition"] - found["eyebrow"]) * found["dpr"], 1.0)


if __name__ == "__main__":
    unittest.main()
