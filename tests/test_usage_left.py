"""v0.6.24 final: every surface says what is LEFT of a usage window, not what is used.

The owner, 2026-11-18, of the icon's card showing "5시간 0% / 주간 100%" with full bars: "사용한 양보다 남은 양이 뜨는게
자연스럽지 않나?" (wouldn't what is left be more natural than what is used?) - and of the scope, "다 바꾸자" (change all of
it). Left is 100 minus the whole share used (ui/words.left), so 0 only where a window is used up: 99.6% used leaves 1, and
a reading above 100 leaves 0. A bar is as full as what is left. Display only: the reading, the wire's numbers and every
decision keep the share used.

Each surface here is held to the same table of edges - the popup's line (Python), the panel's (its own JavaScript, in
Node), the Dashboard's (the compiled window's own UsageLeft, through reflection: no window is made or shown) and the
catalog words they all fill in, in every language. The icon's card and its bars are tests/test_tray_tipcard.py's, the
notice's tests/test_usage_surfaces.py's, the Diagnostics check's tests/test_checkup.py's.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codex_auto_resume import interface, l10n  # noqa: E402
from codex_auto_resume.ui import words  # noqa: E402
from codex_auto_resume.ui.popup import model  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
NOW = 1788628000.0
# (share used, share left): nothing used, a sliver, a share, almost all, all, more than all.
EDGES = ((0, 100), (0.4, 100), (37.5, 63), (62.7, 38), (99.6, 1), (100, 0), (130, 0))


def english(key, **fields):
    return l10n.text(key, "en", **fields)


def reading(*used):
    return {"read_at": NOW - 120, "windows": [{"window_minutes": 300, "used_percent": share} for share in used]}


class WordsTests(unittest.TestCase):
    def test_left_is_100_minus_the_whole_share_used(self):
        for used, left in EDGES:
            with self.subTest(used=used):
                self.assertEqual(words.left({"used_percent": used}), left)
                self.assertEqual(words.left({"used_percent": used}) + words.share({"used_percent": used}), 100)

    def test_the_popups_line_says_what_is_left(self):
        for used, left in EDGES:
            with self.subTest(used=used):
                self.assertEqual(words.usage_line(reading(used), english, NOW),
                                 "Codex usage, read 2m ago: 5-hour %d%% left" % left)
        view = model.view_model([], {"watcher": {"usage": reading(62.7)}}, l10n.catalog("ko"), NOW)
        self.assertIn("5시간 38% 남음", view["usage_note"])

    def test_no_reading_says_nothing_as_before(self):
        for missing in (None, {}, {"read_at": NOW, "windows": []}, {"windows": reading(10)["windows"]}):
            with self.subTest(missing=missing):
                self.assertIsNone(words.usage_line(missing, english, NOW))

    def test_every_language_says_left_in_a_word_of_its_own(self):
        """Each catalog's window words carry a word for "left" beside the share: none is the bare share any more."""
        for locale, strings in interface.STRINGS.items():
            for key in ("usage.window", "usage.window_resets", "check.usage"):
                with self.subTest(locale=locale, key=key):
                    text = strings[key]
                    bare = re.sub(r"\{[a-z]+\}|[%\s:,.،、，：。—–;-]", "", text)
                    if key == "usage.window":
                        self.assertTrue(bare, "the share alone: %r" % text)
                    if locale != "en":
                        self.assertNotEqual(text, interface.STRINGS["en"][key])
        self.assertEqual(interface.STRINGS["ko"]["usage.window"], "{window} {percent}% 남음")
        self.assertEqual(interface.STRINGS["en"]["usage.window"], "{window} {percent}% left")


class PanelTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "needs Node to run the panel's own code")
    def test_the_panel_says_what_is_left_at_every_edge(self):
        from test_mcpui_v063 import run_javascript
        for used, left in EDGES:
            with self.subTest(used=used):
                said = run_javascript(["age", "windowName", "clockTime", "usageLine", "fill", "t"],
                                      "process.stdout.write(JSON.stringify(usageLine(%s, %r)));"
                                      % (json.dumps(reading(used)), NOW))
                self.assertEqual(said, "Codex usage, read 2m ago: 5-hour %d%% left" % left)


class WindowSourceTests(unittest.TestCase):
    def test_the_dashboards_fallback_words_are_the_catalogs(self):
        source = (ROOT / "gui" / "DashboardData.cs").read_text(encoding="utf-8")
        for key in ("usage.window", "usage.window_resets"):
            with self.subTest(key=key):
                self.assertIn('S("%s", "%s")' % (key, interface.STRINGS["en"][key]), source)
        self.assertIn("string share = UsageLeft(used).ToString(CultureInfo.InvariantCulture);", source)


PROBE = r"""
$ErrorActionPreference = 'Stop'
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$form = $assembly.GetType('CodexAutoResume.SettingsForm', $true)
$method = $form.GetMethod('UsageLeft', [Reflection.BindingFlags]'Static,NonPublic,Public')
$out = @{}
foreach ($used in @(USED)) { $out["$used"] = [int]$method.Invoke($null, [object[]]@([double]$used)) }
$out['nan'] = [int]$method.Invoke($null, [object[]]@([double]::NaN))
$out['negative'] = [int]$method.Invoke($null, [object[]]@([double]-5))
[IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'result.json'), ($out | ConvertTo-Json), [Text.Encoding]::UTF8)
"""


class WindowTests(unittest.TestCase):
    """The compiled window's own arithmetic, asked through reflection: a static method, no form made, nothing shown."""

    def test_the_dashboard_says_what_is_left_at_every_edge(self):
        from test_gui_v0611_access import CSC, POWERSHELL, compile_window, run_probe
        if not (CSC.is_file() and POWERSHELL.is_file()):
            self.skipTest("needs the in-box compiler and PowerShell")
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            exe = compile_window(work)
            script = PROBE.replace("USED", ", ".join(repr(float(used)) for used, _ in EDGES))
            answer = run_probe(script, work, 300, CAR_EXE=str(exe))
        for used, left in EDGES:
            with self.subTest(used=used):
                self.assertEqual(answer[str(float(used)).rstrip("0").rstrip(".") if float(used) != int(used)
                                        else str(int(used))], left)
        self.assertEqual((answer["nan"], answer["negative"]), (100, 100))
        self.assertFalse(math.isnan(answer["nan"]))


if __name__ == "__main__":
    unittest.main()
