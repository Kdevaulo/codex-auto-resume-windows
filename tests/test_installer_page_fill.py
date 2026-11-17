"""The setup window's 600 x 600 room, filled (v0.6.24-beta.3, the owner's option A of 2026-11-17: "설치앱은 세로가
늘어난게 빈공간으로만 늘어났네"). The window keeps its size and its header; only the content card of three pages gains
what a person installing it wants to know:

* the Welcome page - three numbered points under the guide's link and before the language picker: it notices a
  conversation that stopped, it carries on once it can, and the words it sends are the person's to choose;

What is held here, on the window built and never shown (the probe pattern of tests/test_installer_window.py and
tests/test_gui_v0624_setup_600.py, the scaling and text size stood in as InstallerAudit stands them in), in every
language at Windows' usual text size and in a few at other scalings and text sizes: each page's rows are there, in
their order, in the catalog's words; each mark stands at the card's leading edge beside its row - on the right where
the language is written right to left; nothing is cut, overlaps or leaves the card; and at text size 1 the window is
still 600 x 600 (scaled) in every language.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from codex_auto_resume import l10n
from test_installer_window import CSC, POWERSHELL, _build, _powershell

ROOT = Path(__file__).resolve().parents[1]
RIGHT_TO_LEFT = ("ar", "he", "fa")

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
$GetState = [System.Windows.Forms.Control].GetMethod('GetState', [Reflection.BindingFlags]'NonPublic,Instance')
function Own($control) { [bool]$GetState.Invoke($control, [object[]]@(2)) }
function Of($object, $name) { $object.GetType().GetProperty($name, $any).GetValue($object, $null) }
function CallOn($object, $name, $arguments) { $object.GetType().GetMethod($name, $any).Invoke($object, [object[]]$arguments) }
function Box($c) { @($c.Left, $c.Top, $c.Width, $c.Height) }
$parse = $FlowType.GetMethod('ParseObject', $any)
function WordsOf($locale) {
    $path = Join-Path $env:CAR_LOCALES ($locale + '.json')
    $WordsType.GetConstructors($any)[0].Invoke([object[]]@($parse.Invoke($null, [object[]]@([IO.File]::ReadAllText($path, [Text.Encoding]::UTF8))), $locale))
}
function NewFlow($mode, $edition, $installed, $from) {
    $flow = $FlowType.GetConstructors($any)[0].Invoke([object[]]@([string]$mode, 'C:\Users\ExampleUser\.codex-auto-resume',
                                                               [string]$edition, $installed, '9.9.9'))
    $FlowType.GetField('From', $any).SetValue($flow, [string]$from)
    $flow
}
function Font($c) { $c.Font.Name + '|' + [int]$c.Font.Style + '|' + $c.Font.SizeInPoints }
function Snapshot($window, $name) {
    $window.PerformLayout()
    $sheet = Of $window 'Body'
    $card = $sheet.Parent
    $width = $card.Width - $card.Padding.Horizontal
    $height = $card.Height - $card.Padding.Vertical
    $used = [int](CallOn $window 'Arrange' @($width))
    $rows = @()
    foreach ($c in @(CallOn $window 'ShownRows' @())) {
        $wanted = $c.GetPreferredSize((New-Object System.Drawing.Size($c.Width, 0)))
        $rows += ,@{ type = $c.GetType().Name; text = [string]$c.Text; box = (Box $c); font = (Font $c);
                     want = @($wanted.Width, $wanted.Height); state = [string]$c.AccessibleDescription }
    }
    $marks = @()
    foreach ($c in $sheet.Controls) {
        if ($c.GetType().Name -ceq 'StepMark' -and (Own $c)) { $marks += ,@{ kind = [string](Of $c 'Kind'); box = (Box $c); name = [string]$c.AccessibleName } }
    }
    $shown = @()
    foreach ($c in $sheet.Controls) { if (Own $c) { $shown += ,@{ type = $c.GetType().Name; box = (Box $c) } } }
    @{ page = $name; client = @($window.ClientSize.Width, $window.ClientSize.Height); width = $width; height = $height;
       used = $used; rows = $rows; marks = $marks; shown = $shown }
}
$notes = "v9.9.9 - something new`n`n**Both editions.** A line of what is new, long enough to take a second line in a window of this width.`n- A line.`n"
$out = @{}
foreach ($case in (ConvertFrom-Json $env:CAR_CASES)) {
    $locale = [string]$case[0]; $display = [double]$case[1]; $text = [double]$case[2]
    $FormType.GetMethod('StandIn', $any).Invoke($null, [object[]]@($display, $text)) | Out-Null
    $WindowType.GetField('WorkHeightStandIn', $any).SetValue($null, 5000)
    $box = [System.Drawing.SystemFonts]::MessageBoxFont
    $system = [double]$FormType.GetField('SystemScale', $any).GetValue($null)
    $font = New-Object System.Drawing.Font($box.FontFamily, [single]($box.SizeInPoints * $text * $display / $system), $box.Style, [System.Drawing.GraphicsUnit]::Point)
    $words = WordsOf $locale
    $ways = [ordered]@{
        first = (NewFlow 'install' 'standard' $null '')
        advanced = (NewFlow 'install' 'advanced' $null '')
        update = (NewFlow 'install' 'standard' 'standard' '9.9.8')
        change = (NewFlow 'install' 'advanced' 'standard' '9.9.8')
        dashboard = (NewFlow 'update' 'standard' 'standard' '9.9.8')
        uninstall = (NewFlow 'uninstall' 'standard' 'standard' '')
    }
    $ways.update.GetType().GetField('NotesText', $any).SetValue($ways.update, $notes)
    $ways.dashboard.GetType().GetField('NotesText', $any).SetValue($ways.dashboard, $notes)
    # A setup program's window speaks every language (its picker on the Welcome page); the Dashboard's and the uninstall's
    # one. Never called here: nothing picks another language.
    $script:spoken = $words
    $speaker = [System.Management.Automation.LanguagePrimitives]::ConvertTo([scriptblock]{ param($language) $script:spoken }, (T 'InstallerWindow+Speaker'))
    $snaps = @()
    foreach ($way in $ways.Keys) {
        $says = if ([string]$FlowType.GetField('Mode', $any).GetValue($ways[$way]) -ceq 'install') { $speaker } else { $null }
        $window = $WindowType.GetConstructors($any)[0].Invoke([object[]]@($ways[$way], $words, $says, $null, $null, $font.PSObject.BaseObject))
        foreach ($page in @(CallOn $ways[$way] 'Pages' @())) {
            CallOn $window 'ShowPage' @([string]$page) | Out-Null
            $snaps += ,(Snapshot $window ($way + '/' + $page))
        }
        $window.Dispose()
    }
    $out[('{0}/{1:F2}/{2:F2}' -f $locale, $display, $text)] = $snaps
}
$FormType.GetMethod('StandIn', $any).Invoke($null, [object[]]@([double]$FormType.GetField('SystemScale', $any).GetValue($null), 1.0)) | Out-Null
$WindowType.GetField('WorkHeightStandIn', $any).SetValue($null, 0)
[IO.File]::WriteAllText($env:CAR_RESULT, ($out | ConvertTo-Json -Depth 8 -Compress), (New-Object Text.UTF8Encoding $false))
"""

# Every language at Windows' usual text size and scaling, and a few at other scalings and text sizes - a language
# written right to left among them.
CASES = ([[locale, 1.0, 1.0] for locale in l10n.LOCALES] +
         [["ko", 1.5, 1.0], ["de", 1.25, 1.0], ["ar", 1.75, 1.0], ["ja", 2.0, 1.0], ["en", 1.0, 1.5], ["ru", 1.0, 2.25],
          ["he", 1.0, 1.5]])


def _words(locale):
    return l10n.catalog(locale)


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class PageFillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="setup-fill-"))
        exe = _build(cls.work)
        result = cls.work / "result.json"
        cls.probe = _powershell(PROBE, cls.work, 1500, CAR_EXE=str(exe), CAR_CASES=json.dumps(CASES),
                                CAR_LOCALES=str(l10n.DIRECTORY), CAR_RESULT=str(result))
        cls.answer = (json.loads(result.read_text(encoding="utf-8-sig"))
                      if cls.probe.returncode == 0 and result.is_file() else {})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def setUp(self):
        if not self.answer:
            self.fail("the probe did not run: " + (self.probe.stderr or self.probe.stdout)[-3000:])

    def snaps(self, locale, display=1.0, text=1.0):
        return self.answer["%s/%.2f/%.2f" % (locale, display, text)]

    def page(self, locale, name, display=1.0, text=1.0):
        found = [snap for snap in self.snaps(locale, display, text) if snap["page"] == name]
        self.assertEqual(len(found), 1, name)
        return found[0]

    def every(self):
        for case in CASES:
            for snap in self.snaps(*case):
                yield case, snap

    def assertBeside(self, snap, mark, row, mirrored):
        """The mark at the card's leading edge, the row in its column past it, the mark centred on the row's first line."""
        width = snap["width"]
        x, y, w, h = mark["box"]
        rx, ry, rw, rh = row["box"]
        if mirrored:
            self.assertEqual(x + w, width, "the mark stands at the card's right edge")
            self.assertLess(rx + rw, x, "the row stands left of its mark")
            self.assertEqual(rx, 0)
        else:
            self.assertEqual(x, 0, "the mark stands at the card's left edge")
            self.assertGreater(rx, x + w, "the row stands right of its mark")
            self.assertEqual(rx + rw, width)
        self.assertLess(abs((y + h / 2) - (ry + min(rh, h) / 2)), max(h, rh), "the mark is beside its row")

    # ------------------------------------------------------------------ the Welcome page

    def test_the_welcome_page_has_three_numbered_points_between_the_guide_and_the_language(self):
        for case in CASES:
            locale = case[0]
            words = _words(locale)
            with self.subTest(case=case):
                snap = self.page(locale, "first/welcome", case[1], case[2])
                texts = [row["text"] for row in snap["rows"]]
                guide = texts.index(words["installer.welcome.guide"])
                language = texts.index(words["installer.language"])
                self.assertEqual(texts[guide + 1:language],
                                 [words["installer.welcome.notices"], words["installer.welcome.notices_help"],
                                  words["installer.welcome.resumes"], words["installer.welcome.resumes_help"],
                                  words["installer.welcome.message"], words["installer.welcome.message_help"]])
                rows = snap["rows"][guide + 1:language]
                self.assertEqual({row["type"] for row in rows}, {"WrapLabel"})
                # The titles in the name's weight, the lines under them in the body's; each title above its line.
                titles, helps = rows[0::2], rows[1::2]
                self.assertEqual(len({row["font"] for row in titles}), 1)
                self.assertNotEqual(titles[0]["font"], helps[0]["font"])
                for title, help_ in zip(titles, helps):
                    self.assertLessEqual(title["box"][1] + title["box"][3], help_["box"][1])
                    self.assertEqual(title["box"][0], help_["box"][0], "a title and its line share the column")
                numbers = sorted((mark for mark in snap["marks"] if mark["kind"] == "Number"), key=lambda mark: mark["box"][1])
                self.assertEqual(len(numbers), 3, "a numbered disc beside each point")
                for mark, title in zip(numbers, titles):
                    self.assertBeside(snap, mark, title, locale in RIGHT_TO_LEFT)
                # Below the guide's link, above the language's label.
                guide_box, language_box = snap["rows"][guide]["box"], snap["rows"][language]["box"]
                self.assertGreater(numbers[0]["box"][1], guide_box[1] + guide_box[3])
                self.assertLess(numbers[-1]["box"][1] + numbers[-1]["box"][3], language_box[1])

    def test_the_dashboards_and_the_uninstalls_pages_have_no_welcome_points(self):
        for snap in self.snaps("en"):
            if snap["page"].startswith(("dashboard/", "uninstall/")):
                with self.subTest(snap["page"]):
                    self.assertNotIn("It notices when one stops", [row["text"] for row in snap["rows"]])
                    self.assertFalse([mark for mark in snap["marks"] if mark["kind"] == "Number"])

    # ------------------------------------------------------------------ every page

    def test_nothing_is_cut_overlaps_or_leaves_the_card(self):
        for case, snap in self.every():
            with self.subTest(case=case, page=snap["page"]):
                width = snap["width"]
                self.assertLessEqual(snap["used"], snap["height"], "the page's rows end inside the card")
                boxes = []
                for row in snap["rows"]:
                    x, y, w, h = row["box"]
                    self.assertGreaterEqual(x, 0, row["text"][:40])
                    self.assertLessEqual(x + w, width, row["text"][:40])
                    self.assertLessEqual(y + h, snap["height"], row["text"][:40])
                    if row["type"] in ("WrapLabel", "SoftCheck", "SoftCallout"):
                        self.assertLessEqual(row["want"][0], w, row["text"][:40] + ": as wide as its words need")
                        self.assertLessEqual(row["want"][1], h, row["text"][:40] + ": as tall as its lines need")
                    boxes.append((row["text"][:40], row["box"]))
                for mark in snap["marks"]:
                    x, y, w, h = mark["box"]
                    self.assertGreaterEqual(x, 0)
                    self.assertLessEqual(x + w, width)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(y + h, snap["height"])
                    boxes.append(("a %s mark" % mark["kind"], mark["box"]))
                for i, (one, a) in enumerate(boxes):
                    for other, b in boxes[i + 1:]:
                        overlap = a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
                        self.assertFalse(overlap, "%r %s overlaps %r %s" % (one, a, other, b))

    def test_at_windows_usual_text_size_the_window_stays_600_by_600_in_every_language(self):
        for case, snap in self.every():
            if case[2] != 1.0:
                continue
            size = int(round(600 * case[1]))
            with self.subTest(case=case, page=snap["page"]):
                self.assertEqual(snap["client"], [size, size])


if __name__ == "__main__":
    unittest.main()
