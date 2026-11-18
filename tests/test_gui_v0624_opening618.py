r"""v0.6.24: the Dashboard opens 1000 by 618 (the owner's decision of 2026-11-18, from real renders).

The owner found beta.2's 1000 by 588 too short. They compared real renders at 588, 612, 625 and 645, and at 612, 615, 618,
621 and 625 with the Overview's cards not growing, and chose 618: "better not to grow the cards". So:

- the window opens 1000 by 618 at text size 1 (SettingsForm.OpeningHeight);
- the Overview's cards keep their comfortable height: OverviewComfort is still Brand.SpaceXl and FitOverview is the rule
  it was, so under the last row the Overview has a little more than its own padding - the owner's choice, not a defect;
- the layout audit holds that band to the decision without going blind (WindowAudit.OpeningBandMax: the 30 px the
  opening height adds to beta.2's 588 and 6 for a short font, plus BandTolerance): the Overview as FitOverview lays it
  out at the opening size is quiet in every state and at every scaling; a band up to the limit is quiet and one a pixel
  past it is reported, with the rows as they were laid out - the audit measuring rather than seeing nothing;
- the README motion's canvas is the 1500 by 927 window the still pictures show at the pinned 150 %.

The band is measured by the probe below at 100, 150 and 200 % in English, Korean and Traditional Chinese (the language
with the shortest lines, so the widest band). The pictures and the motion plans are the main session's: this module
reads their sources, never their pixels. Run alone it compiles the window once (csc).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest

import guiscan
import test_gui_layout as layout
from codex_auto_resume import l10n

ROOT = Path(__file__).resolve().parents[1]
OPENING = (1000, 618)
SCALES = (1.0, 1.5, 2.0)
LOCALES = ("en", "ko", "zh-TW")

PROBE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
[Windows.Forms.Application]::EnableVisualStyles()
[Windows.Forms.Application]::SetCompatibleTextRenderingDefault($false)
$static = [Reflection.BindingFlags]'Static,NonPublic,Public'
$instance = [Reflection.BindingFlags]'Instance,NonPublic,Public'
$utf8 = New-Object Text.UTF8Encoding $false
$work = [string]$env:CAR_WORK
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$form = $assembly.GetType('CodexAutoResume.SettingsForm', $true)
$out = @{ states = @{} }
try {
    $out.constants = @{
        width = [int]$form.GetField('OpeningWidth', $static).GetValue($null)
        height = [int]$form.GetField('OpeningHeight', $static).GetValue($null)
        bandMax = [int]$form.GetField('OpeningBandMax', $static).GetValue($null)
        tolerance = [int]$form.GetField('BandTolerance', $static).GetValue($null)
        comfort = [int]$form.GetField('OverviewComfort', $static).GetValue($null)
    }
    $band = $form.GetField('AuditedBand', $static)
    $audit = $form.GetMethod('OverviewStatesAudit', $static)
    $states = [IO.File]::ReadAllText((Join-Path $work 'states.json'), $utf8)
    foreach ($locale in (ConvertFrom-Json $env:CAR_LOCALES)) {
        $catalog = [IO.File]::ReadAllText((Join-Path $work ('strings-' + $locale + '.json')), $utf8)
        $out.states[$locale] = @{}
        foreach ($scale in (ConvertFrom-Json $env:CAR_SCALES)) {
            $key = ([double]$scale).ToString('0.00', [Globalization.CultureInfo]::InvariantCulture)
            $findings = [string]$audit.Invoke($null, [object[]]@($catalog, $states, [double]$scale))
            $out.states[$locale][$key] = @{ findings = $findings; band = [int]$band.GetValue($null) }
        }
    }

    # The rows as FitOverview gave them at the opening size, in a window made taller until the band under them (past the
    # page's padding) is exactly `want` device pixels: the audit must be quiet at the most it allows and speak a pixel
    # past it. At this machine's scale, in English, with the fullest reply.
    $json = $assembly.GetType('CodexAutoResume.Json', $true)
    $parse = $json.GetMethod('Parse', $static)
    $materialise = $form.GetMethod('Materialise', $static)
    $systemScale = [double]$form.GetField('SystemScale', $static).GetValue($null)
    $english = $parse.Invoke($null, [object[]]@([IO.File]::ReadAllText((Join-Path $work 'strings-en.json'), $utf8)))
    $snapshot = $parse.Invoke($null, [object[]]@([IO.File]::ReadAllText((Join-Path $work 'snapshot.json'), $utf8)))
    $nowhere = [string](Join-Path $work 'nowhere')
    $bridgeType = $assembly.GetType('CodexAutoResume.Bridge', $true)
    $persistentType = $assembly.GetType('CodexAutoResume.PersistentBridge', $true)
    $three = @($form.GetConstructors($instance) | Where-Object { $_.GetParameters().Count -eq 3 })[0]
    $px = $form.GetMethod('Px', $instance)
    function Get-Band([int]$more) {
        $once = $bridgeType.GetConstructors($instance)[0].Invoke([object[]]@($nowhere))
        $bridge = $persistentType.GetConstructors($instance)[0].Invoke([object[]]@($nowhere, $once))
        $window = $three.Invoke([object[]]@($bridge, $english, [Drawing.SystemFonts]::MessageBoxFont))
        try {
            $form.GetField('auditing', $instance).SetValue($window, $true)
            $window.TopLevel = $false
            $window.MinimumSize = [Drawing.Size]::Empty
            $window.ClientSize = New-Object Drawing.Size ([int]$form.GetField('OpeningWidth', $static).GetValue($null)), ([int]$form.GetField('OpeningHeight', $static).GetValue($null))
            @($form.GetMethods($instance) | Where-Object { $_.Name -eq 'ApplySnapshot' -and $_.GetParameters().Count -eq 1 })[0].Invoke($window, [object[]]@($snapshot)) | Out-Null
            @($form.GetMethods($instance) | Where-Object { $_.Name -eq 'ShowPage' -and $_.GetParameters().Count -eq 1 })[0].Invoke($window, [object[]]@('overview')) | Out-Null
            $null = $materialise.Invoke($null, [object[]]@($window))
            $window.PerformLayout()
            # Rows as they are: only the window grows.
            $form.GetField('fitOverview', $instance).SetValue($window, $false)
            $window.ClientSize = New-Object Drawing.Size $window.ClientSize.Width, ($window.ClientSize.Height + $more)
            $null = $materialise.Invoke($null, [object[]]@($window))
            $window.PerformLayout()
            $findings = New-Object 'System.Collections.Generic.List[string]'
            $form.GetField('AuditedBand', $static).SetValue($null, -1)
            @($form.GetMethods($instance) | Where-Object { $_.Name -eq 'AuditRows' })[0].Invoke($window, [object[]]@('canary', $true, $findings.PSObject.BaseObject)) | Out-Null
            return @{ findings = ($findings -join "`n"); band = [int]$form.GetField('AuditedBand', $static).GetValue($null)
                      limit = [int]$px.Invoke($window, [object[]]@([int]$out.constants.bandMax)) + [int]$px.Invoke($window, [object[]]@([int]$out.constants.tolerance)) }
        } finally { $window.Dispose() }
    }
    $natural = Get-Band 0
    $out.natural = $natural
    $out.atLimit = Get-Band ($natural.limit - [Math]::Max(0, $natural.band))
    $out.pastLimit = Get-Band ($natural.limit - [Math]::Max(0, $natural.band) + 1)
    $out.forty = Get-Band ([int][Math]::Round(40 * $systemScale))
} catch {
    $out.error = [string]$_
    $out.errorAt = [string]$_.ScriptStackTrace
}
[IO.File]::WriteAllText((Join-Path $work 'result.json'), (ConvertTo-Json $out -Depth 8), $utf8)
if ($out.error) { exit 1 }
"""


@unittest.skipUnless(layout.CSC.is_file() and layout.POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class OpeningBandTests(unittest.TestCase):
    answer: dict = {}
    failure = ""

    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = work / "CodexAutoResumeSettings.exe"
        subprocess.run([str(layout.CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                        "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                        *[str(path) for path in guiscan.sources()]],
                       check=True, capture_output=True, timeout=300)
        for locale in LOCALES:
            reply = {"ok": True, "language": locale, "strings": l10n.catalog(locale), "endonyms": dict(l10n.ENDONYMS),
                     "preference": locale, "system_language": locale}
            (work / ("strings-%s.json" % locale)).write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        english = {"ok": True, "language": "en", "strings": l10n.catalog("en"), "endonyms": dict(l10n.ENDONYMS),
                   "preference": "en", "system_language": "en"}
        (work / "strings-en.json").write_text(json.dumps(english["strings"], ensure_ascii=False), encoding="utf-8")
        now = time.time()
        (work / "snapshot.json").write_text(json.dumps(layout.fullest_snapshot(now), ensure_ascii=False), encoding="utf-8")
        (work / "states.json").write_text(json.dumps(layout.overview_states(now), ensure_ascii=False), encoding="utf-8")
        probe = work / "probe.ps1"
        probe.write_text(PROBE, encoding="utf-8")
        done = subprocess.run(
            [str(layout.POWERSHELL), "-STA", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1500,
            env=dict(os.environ, CAR_EXE=str(exe), CAR_WORK=str(work), CAR_LOCALES=json.dumps(list(LOCALES)),
                     CAR_SCALES=json.dumps(list(SCALES))))
        result = work / "result.json"
        cls.answer = json.loads(result.read_text(encoding="utf-8-sig")) if result.is_file() else {}
        if done.returncode != 0 or cls.answer.get("error") or not cls.answer:
            cls.failure = "the probe failed (exit %d): %s %s %s" % (done.returncode, cls.answer.get("error"),
                                                                    cls.answer.get("errorAt"), done.stderr[-600:])

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_the_window_opens_1000_by_618_and_the_audit_allows_what_618_adds(self):
        said = self.answer["constants"]
        self.assertEqual((said["width"], said["height"]), OPENING)
        added = said["height"] - 588
        self.assertGreaterEqual(said["bandMax"], added, "at least what the opening height adds to beta.2's 588")
        self.assertLessEqual(said["bandMax"], added + 6, "and no more than a short font's rounding past it")
        self.assertEqual(said["tolerance"], 3)

    def test_the_overviews_cards_keep_their_comfortable_height(self):
        """The owner's choice: not growing the cards. The rule is the one the window has had since v0.6.5."""
        pages = guiscan.read("gui/DashboardPages.cs")
        self.assertIn("internal const int OverviewComfort = Brand.SpaceXl;", pages)
        self.assertEqual(self.answer["constants"]["comfort"], 24)
        fit = guiscan.member_body("SettingsForm", "FitOverview")
        self.assertIn("int[] heights = OverviewHeights(needs, room, rest, Px(OverviewComfort));", fit)

    def test_the_overview_at_the_opening_size_is_quiet_with_its_band_inside_the_limit(self):
        """In every state, in three languages at 100, 150 and 200 %: nothing reported, and the band under the last row
        (past the page's padding) there is - 618 gives the cards all the comfort they have and a little more - but no
        more than what 618 adds to 588."""
        said = self.answer["constants"]
        for locale in LOCALES:
            for scale in SCALES:
                key = "%.2f" % scale
                got = self.answer["states"][locale][key]
                with self.subTest(locale=locale, scale=scale):
                    self.assertEqual(got["findings"], "")
                    self.assertGreaterEqual(got["band"], 0, "the audit saw no band at all: it did not measure")
                    self.assertLessEqual(got["band"], round((said["bandMax"] + said["tolerance"]) * scale))

    def test_a_band_to_the_limit_is_quiet_and_a_pixel_past_it_is_reported(self):
        natural = self.answer["natural"]
        self.assertEqual(natural["findings"], "")
        at = self.answer["atLimit"]
        self.assertEqual(at["band"], natural["limit"], "the probe made the band the limit")
        self.assertEqual(at["findings"], "", "a band the opening height adds was reported")
        past = self.answer["pastLimit"]
        self.assertEqual(past["band"], natural["limit"] + 1)
        self.assertIn("canary :: leaves an empty band", past["findings"])

    def test_a_real_band_is_still_reported(self):
        """The rows as they were in a window 40 px taller - more than the opening height adds - are a band."""
        forty = self.answer["forty"]
        self.assertIn("canary :: leaves an empty band", forty["findings"],
                      "a dead band under cards already at comfort went unreported")


class NamesOfTheHeightTests(unittest.TestCase):
    def test_what_names_the_windows_height_says_618_and_the_readme_canvas_927(self):
        """The window's own source, the pictures' generator and the README motion's two plans: 618 at the pinned 150 %
        is 927, and the canvas is the window it pictures (1500 by 882 for beta.2's 588). Their pixels are the main
        session's to remake."""
        self.assertEqual(int(re.search(r"internal const int OpeningHeight = (\d+);", guiscan.read("gui/SettingsApp.cs")).group(1)),
                         OPENING[1])
        shots = re.search(r"^OPENING_HEIGHT = (\d+)$", (ROOT / "build" / "make_screenshots.py").read_text(encoding="utf-8"),
                          re.M)
        self.assertEqual(int(shots.group(1)), OPENING[1])
        for name in ("readme-en.json", "readme-ko.json"):
            with self.subTest(name):
                plan = json.loads((ROOT / "build" / "motion" / name).read_text(encoding="utf-8"))
                self.assertEqual(plan["canvas"]["size"], [round(OPENING[0] * 1.5), round(OPENING[1] * 1.5)])
        self.assertEqual(round(OPENING[1] * 1.5), 927)


if __name__ == "__main__":
    unittest.main()
