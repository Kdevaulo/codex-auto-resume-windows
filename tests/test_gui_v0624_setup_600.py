"""The setup window is 600 x 600 (v0.6.24, the owner's choice of 2026-11-16: "the setup window exactly as it is, only
taller"): gui/InstallerWindow.cs opens 600 logical pixels wide and tall at text size 1, as large as that at any
display scaling, and taller only where its pages need more - a larger text size - never cut.

What is held, on the window built and never shown (the probe pattern of tests/test_installer_window.py, with the
scaling and text size stood in as InstallerAudit stands them in):
* the client size: 600 x 600 at 100 %, 900 x 900 at 150 %;
* the content card takes the extra height: it ends 16 px (scaled) above the button row, the header card keeps its
  place and height - the formula's (16, 16, width - 32, HeaderHeight) - and the button row keeps its 16 px inset;
* every page of the first installation, an update, the Dashboard's update, an uninstall and a finished run lays out
  in that size, the page's rows ending inside the card;
* a larger text size still grows the window past 600 where a page needs it (never cut).
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from codex_auto_resume import l10n
from test_installer_window import CSC, POWERSHELL, _build, _powershell

ROOT = Path(__file__).resolve().parents[1]
WINDOW = (ROOT / "gui" / "InstallerWindow.cs").read_text(encoding="utf-8")

# Each way the window is shown, on every page and on a finished run, at the display scale and text size asked.
PROBE = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$any = [Reflection.BindingFlags]'Static,Instance,NonPublic,Public'
function T($name) { $assembly.GetType('CodexAutoResume.' + $name, $true) }
$FlowType = T 'InstallerFlow'
$WindowType = T 'InstallerWindow'
$WordsType = T 'InstallerWords'
$FormType = T 'SettingsForm'
$SoftType = T 'Soft'
function Of($object, $name) { $object.GetType().GetProperty($name, $any).GetValue($object, $null) }
function Field($object, $name) { $object.GetType().GetField($name, $any).GetValue($object) }
function CallOn($object, $name, $arguments) { $object.GetType().GetMethod($name, $any).Invoke($object, [object[]]$arguments) }
function Box($rectangle) { @($rectangle.X, $rectangle.Y, $rectangle.Width, $rectangle.Height) }
$parse = $FlowType.GetMethod('ParseObject', $any)
function WordsOf($locale) {
    if (-not $locale) { return $WordsType.GetConstructors($any)[0].Invoke([object[]]@($null, 'en')) }
    $path = if ($locale -eq 'canary') { $env:CAR_CANARY } else { Join-Path $env:CAR_LOCALES ($locale + '.json') }
    $WordsType.GetConstructors($any)[0].Invoke([object[]]@($parse.Invoke($null, [object[]]@([IO.File]::ReadAllText($path, [Text.Encoding]::UTF8))), $(if ($locale -eq 'canary') { 'en' } else { $locale })))
}
function NewFlow($mode, $edition, $installed, $from, $notes) {
    $flow = $FlowType.GetConstructors($any)[0].Invoke([object[]]@([string]$mode, 'C:\Users\ExampleUser\.codex-auto-resume',
                                                               [string]$edition, $installed, '9.9.9'))
    $FlowType.GetField('From', $any).SetValue($flow, [string]$from)
    if ($notes) { $FlowType.GetField('NotesText', $any).SetValue($flow, [string]$notes) }
    $flow
}
function Px($value) { [int]$SoftType.GetMethod('Px', $any).Invoke($null, [object[]]@([int]$value)) }
function Measured($window, $name) {
    $window.PerformLayout()
    $header = Field $window 'header'
    $body = Field $window 'body'
    $buttons = @(@(CallOn $window 'Buttons' @()) | ForEach-Object { , (Box $_.Bounds) })
    @{ page = $name; client = @($window.ClientSize.Width, $window.ClientSize.Height); header = (Box $header.Bounds);
       body = (Box $body.Bounds); buttons = $buttons; headerHeight = [int](CallOn $window 'HeaderHeight' @());
       used = [int](CallOn $window 'Arrange' @((Of $window 'Body').Width));
       cardInner = ((Of $window 'Body').Height); px16 = (Px 16); px600 = (Px 600) }
}
$notes = "v0.6.24 - something new`n`n**Both editions.** A line of what is new, long enough to take a second line in a window of this width, and one more after it.`n- A line.`n- Another line.`n"
$out = @{}
foreach ($case in (ConvertFrom-Json $env:CAR_CASES)) {
    $display = [double]$case[0]; $text = [double]$case[1]; $work = [int]$case[3];
    $WindowType.GetField('WorkHeightStandIn', $any).SetValue($null, $work); $english = WordsOf ([string]$case[2])
    $FormType.GetMethod('StandIn', $any).Invoke($null, [object[]]@($display, $text)) | Out-Null
    $box = [System.Drawing.SystemFonts]::MessageBoxFont
    $system = [double]$FormType.GetField('SystemScale', $any).GetValue($null)
    $font = New-Object System.Drawing.Font($box.FontFamily, [single]($box.SizeInPoints * $text * $display / $system), $box.Style, [System.Drawing.GraphicsUnit]::Point)
    $ways = [ordered]@{
        first = (NewFlow 'install' 'standard' $null '' $null)
        update = (NewFlow 'install' 'standard' 'standard' '9.9.8' $notes)
        dashboard = (NewFlow 'update' 'standard' 'standard' '9.9.8' $notes)
        uninstall = (NewFlow 'uninstall' 'standard' 'standard' '' $null)
    }
    $rows = @()
    foreach ($way in $ways.Keys) {
        $window = $WindowType.GetConstructors($any)[0].Invoke([object[]]@($ways[$way], $english, $null, $null, $null, $font.PSObject.BaseObject))
        foreach ($page in @(CallOn $ways[$way] 'Pages' @())) {
            CallOn $window 'ShowPage' @([string]$page) | Out-Null
            $rows += ,(Measured $window ($way + '/' + $page))
        }
        CallOn $window 'Finished' @(0, "  Checking the installation`nInstalled and running.") | Out-Null
        $rows += ,(Measured $window ($way + '/finished'))
        $window.Dispose()
    }
    $out[('{0:F2}/{1:F2}/{2}/{3}' -f $display, $text, [string]$case[2], $work)] = $rows
}
$FormType.GetMethod('StandIn', $any).Invoke($null, [object[]]@([double]$FormType.GetField('SystemScale', $any).GetValue($null), 1.0)) | Out-Null
$WindowType.GetField('WorkHeightStandIn', $any).SetValue($null, 0)
[IO.File]::WriteAllText($env:CAR_RESULT, ($out | ConvertTo-Json -Depth 6 -Compress), (New-Object Text.UTF8Encoding $false))
"""

# The third is a catalog whose first page's words are far longer than any language's: a page that needs more than 600.
# (display scale, text size, catalog, the work area's height in device px: a tall screen, or the stood-in one)
CASES = [(1.0, 1.0, "", 5000), (1.5, 1.0, "", 5000), (1.0, 2.25, "", 5000), (1.0, 1.0, "canary", 5000),
         (1.0, 2.25, "canary", 5000),
         # 1280 x 720 at 125 % (a work area of about 544 logical px), 1366 x 768 at 125 % (about 582), and a screen with room
         (1.25, 1.0, "", 680), (1.25, 1.0, "", 728), (1.25, 1.0, "", 5000),
         # a work area of 1 px: the height the pages need alone
         (1.25, 1.0, "", 1), (1.25, 2.25, "canary", 1), (1.25, 2.25, "canary", 680)]


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class SetupWindowSizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="setup-600-"))
        exe = _build(cls.work)
        result = cls.work / "result.json"
        canary = cls.work / "canary.json"
        canary.write_text(json.dumps(dict(l10n.catalog("en"), **{"installer.welcome.what": "Words that run on. " * 120,
                                                                  "installer.update.no_notes": "More words. " * 80})),
                          encoding="utf-8")
        cls.probe = _powershell(PROBE, cls.work, 600, CAR_EXE=str(exe), CAR_CASES=json.dumps(CASES), CAR_LOCALES=str(l10n.DIRECTORY), CAR_CANARY=str(canary), CAR_RESULT=str(result))
        cls.answer = (json.loads(result.read_text(encoding="utf-8-sig"))
                      if cls.probe.returncode == 0 and result.is_file() else {})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def setUp(self):
        if not self.answer:
            self.fail("the probe did not run: " + (self.probe.stderr or self.probe.stdout)[-3000:])

    def rows(self, display, text, locale="", work=5000):
        rows = self.answer["%.2f/%.2f/%s/%d" % (display, text, locale, work)]
        self.assertGreater(len(rows), 8, "every way's pages and its finish were measured")
        return rows

    def test_the_window_is_600_by_600_at_100_percent_and_900_by_900_at_150(self):
        for display, size in ((1.0, 600), (1.5, 900)):
            for row in self.rows(display, 1.0):
                with self.subTest(display=display, page=row["page"]):
                    self.assertEqual(row["client"], [size, size])
                    self.assertEqual(row["px600"], size)

    def test_the_content_card_ends_16_px_above_the_button_row(self):
        for display in (1.0, 1.5):
            for row in self.rows(display, 1.0):
                gap = row["px16"]
                self.assertEqual(gap, int(round(16 * display)))
                with self.subTest(display=display, page=row["page"]):
                    body, buttons = row["body"], row["buttons"]
                    self.assertTrue(buttons, "a page has its buttons")
                    for button in buttons:
                        self.assertEqual(button[1] - (body[1] + body[3]), gap, "the card ends one gap above the buttons")
                        self.assertEqual(row["client"][1] - (button[1] + button[3]), gap, "the row keeps its inset")
                    self.assertEqual(body[0], gap)
                    self.assertEqual(body[2], row["client"][0] - 2 * gap)

    def test_the_header_card_is_where_and_as_tall_as_the_formula_has_it(self):
        for display in (1.0, 1.5):
            for row in self.rows(display, 1.0):
                gap = row["px16"]
                with self.subTest(display=display, page=row["page"]):
                    self.assertEqual(row["header"], [gap, gap, row["client"][0] - 2 * gap, row["headerHeight"]])
                    self.assertEqual(row["body"][1], gap + row["headerHeight"] + gap, "the content card starts below it")

    def test_every_page_lies_inside_the_card_in_that_size(self):
        for display in (1.0, 1.5):
            for row in self.rows(display, 1.0):
                with self.subTest(display=display, page=row["page"]):
                    self.assertLessEqual(row["used"], row["cardInner"], "the page's rows end inside the card")

    def test_a_page_that_needs_more_than_600_grows_the_window_and_is_never_cut(self):
        """The canary's long first page: at text size 1 and at 2.25 the window is as tall as that page needs - one height
        for every page of a way - which is more than 600 logical px, and its card holds every page."""
        for text, floor in ((1.0, 600), (2.25, 1350)):
            rows = self.rows(1.0, text, "canary")
            self.assertEqual(rows[0]["px600"], floor)
            ways = {}
            for row in rows:
                ways.setdefault(row["page"].split("/")[0], set()).add(row["client"][1])
            with self.subTest(text=text):
                for way, heights in ways.items():
                    self.assertEqual(len(heights), 1, way + ": one height for every page")
                    self.assertGreaterEqual(min(heights), floor)
                self.assertTrue([way for way, heights in ways.items() if min(heights) > floor],
                                "a way whose page needs more than 600 grew past it: " + str(ways))
                for row in rows:
                    self.assertLessEqual(row["used"], row["cardInner"], row["page"] + ": nothing is cut")
                    gap = row["px16"]
                    for button in row["buttons"]:
                        self.assertEqual(row["client"][1] - (button[1] + button[3]), gap)
                        self.assertEqual(button[1] - (row["body"][1] + row["body"][3]), gap)

    def test_a_larger_text_size_alone_never_makes_the_window_smaller_than_600(self):
        for row in self.rows(1.0, 2.25):
            self.assertGreaterEqual(row["client"][1], row["px600"])


    def test_the_600_never_makes_the_window_taller_than_its_work_area_but_the_pages_still_get_what_they_need(self):
        """On a work area shorter than 600 logical px (1280 x 720 at 125 % holds about 544, 1366 x 768 about 582) the
        floor is the work area's height; what the pages need is what it was, and never cut."""
        room = self.rows(1.25, 1.0, "", 5000)
        self.assertEqual({row["client"][1] for row in room}, {750}, "with room it is 600 logical px at 125 %")
        needs = {row["page"]: row["client"][1] for row in self.rows(1.25, 1.0, "", 1)}
        held = 0
        for work in (680, 728):
            for row in self.rows(1.25, 1.0, "", work):
                need = needs[row["page"]]
                with self.subTest(work=work, page=row["page"]):
                    self.assertEqual(row["client"][1], max(work, need), "the work area's height, or what the page needs")
                    self.assertLessEqual(row["used"], row["cardInner"])
                    for button in row["buttons"]:
                        self.assertEqual(row["client"][1] - (button[1] + button[3]), row["px16"])
                    held += row["client"][1] == work and work < 750
        self.assertGreater(held, 0, "some window was held to a work area shorter than 600 logical px")
        # A page that needs more than the work area holds keeps what it needs.
        tall = {row["page"]: row["client"][1] for row in self.rows(1.25, 2.25, "canary", 1)}
        self.assertGreater(max(tall.values()), 680)
        for row in self.rows(1.25, 2.25, "canary", 680):
            with self.subTest(page=row["page"]):
                self.assertEqual(row["client"][1], max(680, tall[row["page"]]))
                self.assertLessEqual(row["used"], row["cardInner"])


class SourceTests(unittest.TestCase):
    def test_the_height_is_the_larger_of_600_and_what_the_pages_need(self):
        fit = WINDOW[WINDOW.index("private void Fit()"):]
        fit = fit[:fit.index("private static int Inner")]
        self.assertIn("HeightFor(needed, WorkHeight())", fit)
        pure = WINDOW[WINDOW.index("internal static int HeightFor"):]
        self.assertIn("Math.Max(floor, needed)", pure[:pure.index("private static int Inner")])
        self.assertIn("Math.Min(Px(OpeningHeight), workHeight)", pure[:pure.index("private static int Inner")])
        self.assertIn("Px(16) + HeaderHeight() + Px(16) + tallest + Px(32) + Px(16) + Px(Brand.ButtonHeight) + Px(16)", fit,
                      "what the pages need is what it was")
        self.assertEqual(re.search(r"internal const int OpeningWidth = (\d+);", WINDOW).group(1), "600")
        self.assertEqual(re.search(r"internal const int OpeningHeight = (\d+);", WINDOW).group(1), "600")


if __name__ == "__main__":
    unittest.main()
