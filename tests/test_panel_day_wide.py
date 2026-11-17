r"""v0.6.24-beta.3: the Codex panel's header takes the day spread wide (W2, the owner's pick of 2026-11-17).

The panel is laid out by headless Edge (where it is installed; --dump-dom, no picture) with a day given by the test, never
today's date, and the page itself says where the day stands: the band from past the hero's top words to the card's outer
side, its specks laid band after band across all of it, its scene as tall as the band at the outer end, the card's colour
fading into it - and the hero's words, light and buttons exactly where they are on any other day. Node checks that the page
moves the specks as brand does (dayElementAt), and the page's data carries brand's one list of specks.

Headless, nothing shown: run on its own, through gui_lock.sh.
"""
from __future__ import annotations

import html as html_text
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from codex_auto_resume import brand  # noqa: E402
from codex_auto_resume.mcp import panel as mcpui  # noqa: E402
from test_mcpui_v064 import snapshot  # noqa: E402

EDGE = next((path for path in (Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")),
                               Path(os.environ.get("ProgramFiles", "C:/Program Files")))
             if (path / "Microsoft/Edge/Application/msedge.exe").is_file()), None)
NODE = shutil.which("node")
PROBE = "CAR-DAY-PROBE:"
LOOKS = ("birthday", "new_year", "christmas", "seollal", "chuseok")
SCRIPT = (ROOT / "src/codex_auto_resume/mcp/assets/panel.js").read_text(encoding="utf-8")

MEASURE = r"""<script>window.addEventListener('load',function(){setTimeout(function(){
var hero=document.querySelector('.card.hero'),out={hero:null};
if(hero){var box=hero.getBoundingClientRect();out.hero=[box.left,box.top,box.width,box.height];
var day=hero.querySelector('.day-scene');
out.words=[];Array.prototype.forEach.call(hero.children,function(c){if(c===day)return;var r=c.getBoundingClientRect();
out.words.push([c.className,r.left-box.left,r.top-box.top,r.width,r.height]);});
if(day){var d=day.getBoundingClientRect();out.day=[d.left-box.left,d.top-box.top,d.width,d.height];
out.ground=getComputedStyle(day).backgroundColor;
var specks=day.querySelectorAll('.day-specks > g > *'),xs=[];
Array.prototype.forEach.call(specks,function(n){var r=n.getBoundingClientRect();if(r.width>0)xs.push(r.left-d.left);});
out.specks=[specks.length,xs.length?Math.min.apply(null,xs):-1,xs.length?Math.max.apply(null,xs):-1];
var p=day.querySelector('.day-picture');if(p){var q=p.getBoundingClientRect();out.picture=[q.left-d.left,q.top-d.top,q.width,q.height];}
var v=day.querySelector('.day-veil');out.veil=v?getComputedStyle(v).backgroundImage:null;
out.moving=day.querySelectorAll('.day-fall,.day-twinkle').length;}}
document.title='%s'+JSON.stringify(out);},400);});</script>""" % PROBE


@unittest.skipUnless(EDGE is not None, "needs Microsoft Edge to lay the page out")
class PanelDayTests(unittest.TestCase):
    def measure(self, day, width=900, extra="", flags=()):
        page = mcpui.settings_page(snapshot(), theme="light", design="soft", text=1.0, face="Segoe UI", day=day)
        with tempfile.TemporaryDirectory() as folder:
            probe = Path(folder) / "panel.html"
            probe.write_text(page.replace("</head>", extra + "</head>").replace("</body>", MEASURE + "</body>"), encoding="utf-8")
            done = subprocess.run([str(EDGE / "Microsoft/Edge/Application/msedge.exe"), "--headless=new", "--disable-gpu",
                                   "--hide-scrollbars", "--virtual-time-budget=3000", "--user-data-dir=" + folder + "/p", *flags,
                                   "--window-size=%d,%d" % (width, 1200), "--dump-dom", probe.as_uri()],
                                  capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for piece in done.stdout.split(PROBE)[1:]:
            try:
                return json.loads(html_text.unescape(piece.split("</title>", 1)[0]))
            except ValueError:
                continue
        self.fail("the browser said nothing: " + done.stderr[-1500:])

    @classmethod
    def setUpClass(cls):
        cls.found = {}

    def day(self, look, width=900):
        key = (look, width)
        if key not in self.found:
            self.found[key] = self.measure(look, width)
        return self.found[key]

    def test_an_ordinary_day_has_no_band(self):
        self.assertNotIn("day", self.day(None))

    def test_the_header_is_in_the_day_past_the_words(self):
        plain = self.day(None)
        for look in LOOKS:
            with self.subTest(look=look):
                found = self.day(look)
                left, top, width, height = found["day"]
                hero = found["hero"]
                tall = min(66, hero[3])
                self.assertAlmostEqual(left + width, hero[2] - 1, delta=1, msg="to the card's outer side")
                self.assertLess(left, hero[2] * 0.66, "wider than a corner")
                self.assertAlmostEqual(height, tall, delta=1)
                # Every word where it is on any other day (the band is past them: placeDayScene measures their text).
                self.assertEqual(found["words"], plain["words"])
                r, g, b = brand.rgb(brand.DAY_LOOKS[look][2])
                self.assertEqual(found["ground"], "rgb(%d, %d, %d)" % (r, g, b))
                self.assertTrue(found["veil"].startswith("linear-gradient"), found["veil"])

    def test_the_specks_are_across_the_band_and_the_scene_at_its_outer_end(self):
        for look in LOOKS:
            with self.subTest(look=look):
                found = self.day(look)
                width = found["day"][2]
                count, first, last = found["specks"]
                self.assertGreaterEqual(count, len(brand.speck_elements(look)))
                self.assertGreater(last - first, width * 0.5, "across the band, not in a corner")
                picture = found.get("picture")
                self.assertIsNotNone(picture, "a scene where its main piece is whole")
                self.assertAlmostEqual(picture[0] + picture[2], width, delta=1)
                self.assertAlmostEqual(picture[3], found["day"][3], delta=1, msg="as tall as the band")
                self.assertGreater(found["moving"], 0)

    def test_held_still_nothing_moves(self):
        found = self.measure("christmas", flags=("--force-prefers-reduced-motion",))
        self.assertIn("day", found)
        self.assertEqual(found["moving"], 0, "the first instant, standing still")

    def test_none_in_classic(self):
        page = self.measure("seollal", extra="<script>document.documentElement.setAttribute('data-design','classic');</script>")
        self.assertNotIn("day", page)


class PanelDayDataTests(unittest.TestCase):
    def test_the_page_carries_brands_one_list_of_specks(self):
        page = mcpui.settings_page(theme="light", text=1.0, face="Segoe UI", day="chuseok")
        marker = "window.__CODEX_AUTO_RESUME_DAY__="
        data = json.JSONDecoder().raw_decode(page[page.index(marker) + len(marker):].replace("\\u003c", "<"))[0]
        self.assertEqual(data["specks"], json.loads(json.dumps(brand.speck_elements("chuseok"))))
        self.assertEqual(data["speckBand"], brand.SPECK_BAND)
        self.assertEqual(data["wide"], {"gap": brand.WIDE["gap"], "fade": brand.WIDE["fade"]})

    @unittest.skipUnless(NODE, "needs Node to run the page's own code")
    def test_the_page_moves_the_specks_as_brand_does(self):
        art = SCRIPT[SCRIPT.index("// day-art begin"):SCRIPT.index("// day-art end")]
        cases = {look: brand.speck_elements(look) for look in LOOKS}
        program = art + ("var cases = %s; var out = {}; Object.keys(cases).forEach(function (look) {"
                         " out[look] = []; [0, 1.3, 9.7].forEach(function (t) { cases[look].forEach(function (e) {"
                         " out[look].push(dayElementAt(e, t)); }); }); });"
                         " process.stdout.write(JSON.stringify(out));" % json.dumps(cases))
        done = subprocess.run([NODE, "-e", program], capture_output=True, text=True, encoding="utf-8", timeout=60,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertEqual(done.returncode, 0, done.stderr[-400:])
        got = json.loads(done.stdout)
        for look in LOOKS:
            expected = [brand.element_at(element, seconds) for seconds in (0.0, 1.3, 9.7) for element in brand.speck_elements(look)]
            for (_, numbers, _, opacity), (_, python, _, alpha) in zip(got[look], expected):
                self.assertAlmostEqual(opacity, alpha, places=6, msg=look)
                for one, other in zip(numbers, python):
                    self.assertAlmostEqual(one, other, places=6, msg=look)


if __name__ == "__main__":
    unittest.main()
