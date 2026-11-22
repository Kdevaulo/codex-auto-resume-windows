r"""The window's optical alignment, as the third round's audit proposed it (v0.6.26, plans/v0626-audit/audit-design-motion.md;
the owner, 2026-11-22: "제안대로 모두 고침" - every place fixed as the report proposes, its first choice where it names two).

D7. The chart in "How recoveries ended" kept the unscaled default 3 px Margin that Facts was cured of: it stood 2-3 px in
from its card's heading. Now it has none, and starts in the heading's column.

D1. The page cards' outer edges stood 2 px (left) and 3 px (right) inside the header card's (CardRoom's 16 and 17
against HeaderSide 14), the tab row's ends between them. Now the page cards are flush with the header card (PageRoom's
sides are HeaderSide), the report's first choice.

D2. The caption buttons' glyphs stood closer to the header card's top than to its side (the cross's ink 18 logical px
below the top, 22 in from the edge) and above the headline's line. Now the group stands 14 below the card's top
(brand.LAYOUT["caption_inset_top"], the report's choice A), 10 in from its edge as before.

D5. In "Why it is waiting" each result chip ended exactly where the row's hairline ends, and in the Pending and History
lists the status chip started 5 px (at 150 %) before its column heading's first letter. Now the chip ends
Brand.PillInset inside the hairline's end (GateList.ChipBox) and starts at the heading's first letter, the cell's start
and Windows' text lead (SettingsForm.ChipCell, SoftDialog.TitleLead).

D6. Each Statistics bar was centred on its label's line box, 2.7 logical px above the middle of its lowercase letters.
Now it is centred on the label's x-height middle: an "x" drawn in the chart's font and read here, not the window's
own measure.

D8. The Overview's two stacked fact tables (Right now, Last 7 days) put their values at different x - 9 px apart in
English, 55 in German. Now they keep one value column, the wider (SettingsForm.OneLabelColumn).

D13. The setup window's header centred its light on the two lines' boxes, 2.5 px above the middle of their ink at 150 %
(the second line is the smaller version). Now the light is centred on their ink. (The Dashboard's was within a pixel.)

D12. The version's pill, moved into the header card, ended Brand.PillInset (4) inside the card's edge under caption
buttons that end Brand.CaptionInsetEnd (10) inside it. Now it ends under the caption group's end (the pill room's own
module holds it, tests/test_gui_pill_room.py).

The window is compiled from the shipped sources and laid out by its own layout audit (SettingsForm.LayoutAudit), never
shown; what is held is where the audit wrote everything down (AuditedGeometry). GUI test module: run on its own, through
gui_lock.sh.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import time
import unittest

from codex_auto_resume import brand, l10n, settings

import guiscan
import test_gui_layout
from test_gui_v0611_access import CSC, POWERSHELL, compile_window, run_probe

LOCALES = ("en", "de")
SCALES = (1.0, 1.5)

PROBE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
[Windows.Forms.Application]::EnableVisualStyles()
[Windows.Forms.Application]::SetCompatibleTextRenderingDefault($false)
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$static = [Reflection.BindingFlags]'Static,NonPublic,Public'
function T([string]$name) { return $assembly.GetType('CodexAutoResume.' + $name, $true) }
$form = T 'SettingsForm'
$work = [string]$env:CAR_WORK
$utf8 = New-Object Text.UTF8Encoding $false
$schema = [IO.File]::ReadAllText((Join-Path $work 'schema.json'), $utf8)
$current = [IO.File]::ReadAllText((Join-Path $work 'settings.json'), $utf8)
$snapshot = [IO.File]::ReadAllText((Join-Path $work 'snapshot.json'), $utf8)
$out = @{ audit = @{} }
$audit = $form.GetMethod('LayoutAudit', $static)
foreach ($locale in (ConvertFrom-Json $env:CAR_LOCALES)) {
    $catalog = [IO.File]::ReadAllText((Join-Path $work ('strings-' + $locale + '.json')), $utf8)
    $out.audit[$locale] = @{}
    foreach ($scale in (ConvertFrom-Json $env:CAR_SCALES)) {
        $key = ([double]$scale).ToString('0.00', [Globalization.CultureInfo]::InvariantCulture)
        $report = [string]$audit.Invoke($null, [object[]]@($schema, $current, $catalog, $snapshot, [double]$scale))
        $out.audit[$locale][$key] = @{ report = $report; geometry = [string]$form.GetField('AuditedGeometry', $static).GetValue($null) }
    }
}
[IO.File]::WriteAllText((Join-Path $work 'result.json'), ($out | ConvertTo-Json -Depth 8 -Compress), $utf8)
"""
CHART = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$static = [Reflection.BindingFlags]'Static,NonPublic,Public'
$instance = [Reflection.BindingFlags]'Instance,NonPublic,Public'
function T([string]$name) { return $assembly.GetType('CodexAutoResume.' + $name, $true) }
function Bare([object[]]$items) { $bare = New-Object 'object[]' $items.Length; for ($i = 0; $i -lt $items.Length; $i++) { $one = $items[$i]; if ($one -is [Management.Automation.PSObject]) { $one = $one.PSObject.BaseObject }; $bare[$i] = $one }; return ,$bare }
$null = (T 'Palette').GetMethod('Adopt', $static, $null, [Type[]]@([string]), $null).Invoke($null, [object[]]@('light'))
$out = @{ charts = @(); chips = @() }
foreach ($scale in 1.0, 1.5, 2.0) {
    (T 'SettingsForm').GetField('dpiScale', $static).SetValue($null, [double]$scale)
    $chartType = T 'OutcomeChart'
    $chart = $chartType.GetConstructors($instance)[0].Invoke([object[]]@())
    $chart.Font = New-Object Drawing.Font 'Segoe UI', ([single](9 * $scale))
    $bars = $chartType.GetField('Bars', $instance).GetValue($chart)
    $barType = $chartType.GetNestedType('Bar', $instance)
    foreach ($bar in @(@('recovered', 5, 'success'), @('failed', 2, 'failure'))) {
        $bars.Add($barType.GetConstructors($instance)[0].Invoke([object[]]@([string]$bar[0], [int]$bar[1], [string]$bar[2])))
    }
    $chart.Size = New-Object Drawing.Size 420, 120
    $row = [int]$chartType.GetMethod('RowHeight', $instance).Invoke($chart, @())
    $faces = @($chartType.GetMethod('Faces', $instance).Invoke($chart, @()))
    # The "x" of the chart's font, drawn as the label is (TextRenderer, from a point): its ink rows.
    $h = $chart.Font.Height
    $drawn = New-Object Drawing.Bitmap (2 * $h), $h
    $g = [Drawing.Graphics]::FromImage($drawn)
    $g.Clear([Drawing.Color]::White)
    [Windows.Forms.TextRenderer]::DrawText($g, 'x', $chart.Font, (New-Object Drawing.Point 0, 0), [Drawing.Color]::Black, [Drawing.Color]::White)
    $g.Dispose()
    $top = -1; $bottom = -1
    for ($y = 0; $y -lt $h; $y++) { for ($x = 0; $x -lt 2 * $h; $x++) { $c = $drawn.GetPixel($x, $y); if ($c.R -lt 207) { if ($top -lt 0) { $top = $y }; $bottom = $y; break } } }
    $drawn.Dispose()
    $lead = [int][Math]::Round(4 * $scale)
    $out.charts += ,@{ scale = $scale; row = $row; lead = $lead; ink = @($top, $bottom); height = $h;
                       faces = @($faces | ForEach-Object { ,@($_.X, $_.Y, $_.Width, $_.Height) }) }
    $chart.Dispose()
    # D5: the gate list's chip and the list's status chip.
    $box = (T 'GateList').GetMethod('ChipBox', $static)
    $cellOf = (T 'SettingsForm').GetMethod('ChipCell', $static)
    $font = New-Object Drawing.Font 'Segoe UI', ([single](9 * $scale))
    # The heading's first ink, drawn as DrawHeader draws it (from the cell's start, one line, from its left), read here.
    $flags = [Windows.Forms.TextFormatFlags]'VerticalCenter, Left, SingleLine, EndEllipsis'
    $drawn = New-Object Drawing.Bitmap 200, 40
    $g = [Drawing.Graphics]::FromImage($drawn); $g.Clear([Drawing.Color]::White)
    [Windows.Forms.TextRenderer]::DrawText($g, 'Status', $font, (New-Object Drawing.Rectangle 0, 0, 200, 40), [Drawing.Color]::Black, [Drawing.Color]::White, $flags)
    $g.Dispose()
    $ink = -1
    for ($x = 0; $x -lt 200 -and $ink -lt 0; $x++) { for ($y = 0; $y -lt 40; $y++) { $c = $drawn.GetPixel($x, $y); if ($c.R -lt 207) { $ink = $x; break } } }
    $drawn.Dispose()
    $chip = @{ scale = $scale; inset = [int][Math]::Round(4 * $scale); lead = $ink }
    if ($box) {
        $r = $box.Invoke($null, (Bare @($false, 300, 0, 60, 24))); $chip.box = @($r.X, $r.Width)
        $r = $box.Invoke($null, (Bare @($true, 300, 0, 60, 24))); $chip.mirrored = @($r.X, $r.Width)
    }
    if ($cellOf) {
        $r = $cellOf.Invoke($null, (Bare @((New-Object Drawing.Rectangle 10, 0, 200, 24), 'Status', $font, $false))); $chip.cell = @($r.X, $r.Width)
        $r = $cellOf.Invoke($null, (Bare @((New-Object Drawing.Rectangle 10, 0, 200, 24), 'Status', $font, $true))); $chip.cellMirrored = @($r.X, $r.Width)
    }
    $out.chips += ,$chip
}
[IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'result.json'), ($out | ConvertTo-Json -Depth 6 -Compress), (New-Object Text.UTF8Encoding $false))
"""
SETUP = r"""
param([string]$Unused)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
$asm = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$any = [Reflection.BindingFlags]'Static,Instance,NonPublic,Public'
Add-Type -ReferencedAssemblies System.Windows.Forms -TypeDefinition @'
using System;
public static class CarOpticalRunner { public static int Run(object flow, Action<string> line, Action<double> unpacked) { return 0; } }
'@
$out = @{ setup = @() }
foreach ($scale in 1.0, 1.5) {
    $asm.GetType('CodexAutoResume.SettingsForm', $true).GetField('dpiScale', $any).SetValue($null, [double]$scale)
    $flowType = $asm.GetType('CodexAutoResume.InstallerFlow', $true)
    $windowType = $asm.GetType('CodexAutoResume.InstallerWindow', $true)
    $flow = [Activator]::CreateInstance($flowType, $any, $null, [object[]]@('update', 'C:\Users\ExampleUser\.codex-auto-resume', 'standard', 'standard', '0.6.26'), $null)
    $words = [Activator]::CreateInstance($asm.GetType('CodexAutoResume.InstallerWords', $true), $any, $null, [object[]]@($null, 'en'), $null)
    $runner = [Delegate]::CreateDelegate($windowType.GetNestedType('Runner', $any), [CarOpticalRunner].GetMethod('Run'))
    $window = [Activator]::CreateInstance($windowType, $any, $null, [object[]]@($flow, $words, $null, $runner, $null, $null), $null)
    $window.StartPosition = 'Manual'; $window.Location = New-Object Drawing.Point -30000, -30000
    $null = $window.Handle
    $window.PerformLayout()
    [Windows.Forms.Application]::DoEvents()
    $light = $windowType.GetProperty('HeaderLight', $any)
    $one = @{ scale = $scale; found = $null -ne $light }
    if ($light) {
        $l = $light.GetValue($window, $null); $t = $windowType.GetProperty('HeaderTitle', $any).GetValue($window, $null)
        $v = $windowType.GetProperty('HeaderVersion', $any).GetValue($window, $null)
        $one.light = @($l.Top, $l.Height); $one.head = [int]$l.Parent.Height
        $rows = @()
        foreach ($line in $t, $v) {
            $b = New-Object Drawing.Bitmap $line.Width, $line.Height
            $line.DrawToBitmap($b, (New-Object Drawing.Rectangle 0, 0, $line.Width, $line.Height))
            $g = $line.BackColor; $first = -1; $last = -1
            for ($y = 0; $y -lt $line.Height; $y++) { for ($x = 0; $x -lt $line.Width; $x++) { $c = $b.GetPixel($x, $y)
                if ([Math]::Abs($c.R - $g.R) -gt 48 -or [Math]::Abs($c.G - $g.G) -gt 48 -or [Math]::Abs($c.B - $g.B) -gt 48) { if ($first -lt 0) { $first = $y }; $last = $y; break } } }
            $b.Dispose()
            $rows += ,@($line.Top, $first, $last)
        }
        $one.lines = $rows
    }
    $out.setup += ,$one
    $window.Dispose()
}
[IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'result.json'), ($out | ConvertTo-Json -Depth 6 -Compress), (New-Object Text.UTF8Encoding $false))
"""

LINE = re.compile(r"^(?P<path>\S+) (?P<x>-?\d+),(?P<y>-?\d+),(?P<w>\d+),(?P<h>\d+) m(?P<m>[\d,-]+) p(?P<p>[\d,-]+)$")


def pages(geometry: str) -> dict:
    """Each page or section the audit laid out: its lines as (path, bounds, margin, padding), in order."""
    found, now = {}, None
    for line in geometry.splitlines():
        if line.startswith("== "):
            now = found.setdefault(line[3:].strip(), [])
            continue
        match = LINE.match(line)
        if match and now is not None:
            now.append((match["path"], tuple(int(match[k]) for k in "xywh"),
                        tuple(int(v) for v in match["m"].split(",")), tuple(int(v) for v in match["p"].split(","))))
    return found


def absolute(page: list) -> dict:
    """Each control's bounds in the window, by its path."""
    found = {}
    for path, (x, y, w, h), _margin, _padding in page:
        parent = path.rsplit("/", 1)[0]
        px, py = found.get(parent, (0, 0, 0, 0))[:2]
        found[path] = (px + x, py + y, w, h)
    return found


class SourceTests(unittest.TestCase):
    def test_the_chart_has_no_margin_of_its_own(self):
        self.assertIn("chart.Margin = new Padding(0);", guiscan.member_body("SettingsForm", "BuildStatistics"))


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = compile_window(work)
        (work / "schema.json").write_text(json.dumps(settings.describe(), ensure_ascii=False), encoding="utf-8")
        (work / "settings.json").write_text(json.dumps(settings.defaults(), ensure_ascii=False), encoding="utf-8")
        (work / "snapshot.json").write_text(json.dumps(test_gui_layout.fullest_snapshot(time.time()), ensure_ascii=False),
                                            encoding="utf-8")
        for locale in LOCALES:
            reply = {"ok": True, "language": locale, "strings": l10n.catalog(locale), "endonyms": dict(l10n.ENDONYMS),
                     "preference": locale, "system_language": locale}
            (work / ("strings-%s.json" % locale)).write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        chart = work / "chart"
        chart.mkdir()
        cls.chart = run_probe(CHART, chart, 120, CAR_EXE=str(exe))
        setup = work / "setup"
        setup.mkdir()
        cls.setup = run_probe(SETUP, setup, 120, CAR_EXE=str(exe))
        cls.answer = run_probe(PROBE, work, 300 * len(LOCALES), CAR_EXE=str(exe), CAR_LOCALES=json.dumps(list(LOCALES)),
                               CAR_SCALES=json.dumps(list(SCALES)))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def each(self):
        for locale in LOCALES:
            for scale in SCALES:
                yield locale, scale, pages(self.answer["audit"][locale]["%.2f" % scale]["geometry"])

    def test_the_outcome_chart_starts_in_its_card_heading_s_column(self):
        for locale, scale, laid in self.each():
            with self.subTest(locale=locale, scale=scale):
                lines = [line for page in laid.values() for line in page]
                charts = [line for line in lines if line[0].endswith(":OutcomeChart")]
                self.assertTrue(charts, "the audit laid the chart out")
                for path, bounds, margin, _padding in charts:
                    self.assertEqual(margin, (0, 0, 0, 0))
                    card = path.rsplit("/", 1)[0]
                    heading = [line for line in lines if line[0].startswith(card + "/") and line[0].count("/") == path.count("/")
                               and line[0] != path]
                    self.assertTrue(heading, "the chart's card has its heading beside it")
                    self.assertEqual(bounds[0], min(line[1][0] for line in heading), heading)

    def test_the_page_cards_are_flush_with_the_header_card(self):
        for locale, scale, laid in self.each():
            for name in ("overview", "pending", "history", "statistics"):
                with self.subTest(locale=locale, scale=scale, page=name):
                    page = laid[name]
                    where = absolute(page)
                    header = [where[path] for path, *_rest in page if re.fullmatch(r"/\d+:SoftPage/0:SoftCard", path)
                              and where[path][1] < 40 * scale]
                    self.assertEqual(len(header), 1, "the header card")
                    hx, _hy, hw, _hh = header[0]
                    body = [path for path, *_rest in page if path.endswith(":SoftPage") and path.count("/") == 1
                            and where[path][1] > 60 * scale]
                    cards = [where[path] for path, *_rest in page if path.endswith(":SoftCard")
                             and any(path.startswith(top + "/") for top in body)]
                    self.assertTrue(cards, "the page's cards")
                    self.assertEqual(min(x for x, _y, _w, _h in cards), hx, "the left edges")
                    self.assertEqual(max(x + w for x, _y, w, _h in cards), hx + hw, "the right edges")

    def test_the_caption_buttons_stand_fourteen_below_the_header_card_s_top(self):
        self.assertEqual((brand.LAYOUT["caption_inset_top"], brand.LAYOUT["caption_inset_end"]), (14, 10))
        for locale, scale, laid in self.each():
            with self.subTest(locale=locale, scale=scale):
                page = laid["overview"]
                where = absolute(page)
                header = [where[path] for path, *_rest in page if re.fullmatch(r"/\d+:SoftPage/0:SoftCard", path)
                          and where[path][1] < 40 * scale]
                buttons = [where[path] for path, *_rest in page if path.endswith(":CaptionButton")]
                self.assertEqual(len(buttons), 3)
                self.assertEqual({y - header[0][1] for _x, y, _w, _h in buttons}, {int(round(14 * scale))})
                self.assertEqual(header[0][0] + header[0][2] - max(x + w for x, _y, w, _h in buttons), int(round(10 * scale)))

    def test_each_bar_is_centred_on_its_label_s_x_height(self):
        for chart in self.chart["charts"]:
            with self.subTest(scale=chart["scale"]):
                top, bottom = chart["ink"]
                self.assertGreaterEqual(top, 0, "the x was drawn")
                middle = (top + bottom + 1) / 2.0
                for index, (_x, y, _w, h) in enumerate(chart["faces"]):
                    label_top = index * chart["row"] + chart["lead"]
                    self.assertLessEqual(abs(y + h / 2.0 - (label_top + middle)), 0.5 + 1e-9,
                                         "the bar's centre on the label's x-height middle")

    def test_each_chip_stands_inside_the_row_end_and_under_its_heading_s_first_letter(self):
        for chip in self.chart["chips"]:
            with self.subTest(scale=chip["scale"]):
                self.assertIn("box", chip, "GateList.ChipBox")
                self.assertEqual(chip["box"], [300 - chip["inset"] - 60, 60], "PillInset inside the hairline's end")
                self.assertEqual(chip["mirrored"], [chip["inset"], 60], "mirrored: inside its left end")
                self.assertGreater(chip["lead"], 0, "the heading's first ink stands in from the cell's start")
                lead = chip["cell"][0] - 10
                self.assertLessEqual(abs(lead - chip["lead"]), 1, "from the heading's first letter")
                self.assertEqual(chip["cell"][1], 200 - lead)
                self.assertGreater(chip["cellMirrored"][1], 0)
                self.assertEqual(chip["cellMirrored"][0], 10)

    def test_the_overview_s_left_column_keeps_one_value_column(self):
        for locale, scale, laid in self.each():
            with self.subTest(locale=locale, scale=scale):
                page = laid["overview"]
                values = {}
                for path, (x, _y, _w, _h), _margin, _padding in page:
                    match = re.search(r"/(\d+):SoftCard/1:SoftStack/(\d+):\w+$", path)
                    if match and int(match[2]) % 2 == 1:
                        values.setdefault(int(match[1]), set()).add(x)
                self.assertIn(0, values, "Right now's facts")
                self.assertIn(2, values, "Last 7 days' facts")
                self.assertEqual(len(values[0]), 1)
                self.assertEqual(values[0], values[2], "one value column for the two tables")

    def test_the_setup_header_s_light_is_centred_on_its_lines_ink(self):
        for one in self.setup["setup"]:
            with self.subTest(scale=one["scale"]):
                self.assertTrue(one["found"], "InstallerWindow.HeaderLight")
                (title_top, title_first, _title_last), (version_top, _version_first, version_last) = one["lines"]
                self.assertGreaterEqual(title_first, 0)
                self.assertGreaterEqual(version_last, 0)
                ink = (title_top + title_first + version_top + version_last + 1) / 2.0
                top, height = one["light"]
                self.assertLessEqual(abs(top + height / 2.0 - ink), 0.5 + 1e-9, "the light's centre on the ink's middle")
                self.assertGreaterEqual(top, 0)
                self.assertLessEqual(top + height, one["head"])


if __name__ == "__main__":
    unittest.main()
