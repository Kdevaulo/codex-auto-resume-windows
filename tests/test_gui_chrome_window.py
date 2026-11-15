r"""v0.6.24 (stage 1, surface A): the window's own caption, built and never shown (gui/SoftChrome.cs).

The window and its dialogs as the layout audit lays them out (SettingsForm.LayoutAudit: not even top-level windows, no
input): the caption buttons in the hero's top outer corner, Brand.CaptionInsetTop below its top and CaptionInsetEnd in from
its edge - the left, mirrored - the headline ending at least 8 px before them in every language tried, at every scaling,
with the Start button shown and without (AuditCaption); every dialog's title card 16 px in at its top with its buttons in
it and the dialog's own layout below it (AuditTitleCard).

A SoftDialog on its own: its ClientSize is what it was asked plus the title's strip, docked first, its own controls laid
out below it as they were and kept in their places in Controls; Close alone or the pair as its boxes ask; mirrored, the
buttons at the left.

The day's scenes (brand.DAY_LOOKS): each drawn offscreen where the window places it, and the glyph's colour held to 3:1
against what the scene puts under each button (WCAG's non-text contrast) - plans/v0624-stage1-design.md 3.3, O6.

GUI test module (it compiles the window and builds windows that are never shown): run on its own, through gui_lock.sh.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest

from codex_auto_resume import brand, l10n, settings
from codex_auto_resume.brand import colour as brand_colour

import test_gui_layout
from test_gui_v0611_access import CSC, POWERSHELL, compile_window, run_probe

LOCALES = ("en", "de", "ar", "he", "ja", "vi")
SCALES = (1.0, 1.5, 2.0)
# The days whose scene puts less than 3:1 under the caption glyphs (measured 2026-11-15, 1.6 to 2.4): open point O6 of the
# design, for the main session to decide - never changed silently here.
O6_OPEN = {"chuseok", "new_year", "christmas"}
CAPTION_WORDS = ("caption", "title card", "title's strip", "title ends", "headline ends", "Start button lies")

PROBE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
[Windows.Forms.Application]::EnableVisualStyles()
[Windows.Forms.Application]::SetCompatibleTextRenderingDefault($false)
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$static = [Reflection.BindingFlags]'Static,NonPublic,Public'
$instance = [Reflection.BindingFlags]'Instance,NonPublic,Public'
function T([string]$name) { return $assembly.GetType('CodexAutoResume.' + $name, $true) }
function Bare([object[]]$items) { $bare = New-Object 'object[]' $items.Length; for ($i = 0; $i -lt $items.Length; $i++) { $one = $items[$i]; if ($one -is [Management.Automation.PSObject]) { $one = $one.PSObject.BaseObject }; $bare[$i] = $one }; return ,$bare }
function S([string]$type, [string]$name, [object[]]$arguments) {
    $m = @((T $type).GetMethods($static) | Where-Object { $_.Name -eq $name -and $_.GetParameters().Count -eq $arguments.Count })[0]
    return $m.Invoke($null, (Bare $arguments))
}
function P($target, [string]$name) { return $target.GetType().GetProperty($name, $instance).GetValue($target, $null) }
function Box($c) { return @([int]$c.Left, [int]$c.Top, [int]$c.Width, [int]$c.Height) }
$form = T 'SettingsForm'
$work = [string]$env:CAR_WORK
$utf8 = New-Object Text.UTF8Encoding $false
$schema = [IO.File]::ReadAllText((Join-Path $work 'schema.json'), $utf8)
$current = [IO.File]::ReadAllText((Join-Path $work 'settings.json'), $utf8)
$snapshot = [IO.File]::ReadAllText((Join-Path $work 'snapshot.json'), $utf8)
$out = @{ audit = @{}; dialogs = @{}; scenes = @{} }
$audit = $form.GetMethod('LayoutAudit', $static)
foreach ($locale in (ConvertFrom-Json $env:CAR_LOCALES)) {
    $catalog = [IO.File]::ReadAllText((Join-Path $work ('strings-' + $locale + '.json')), $utf8)
    $out.audit[$locale] = @{}
    foreach ($scale in (ConvertFrom-Json $env:CAR_SCALES)) {
        $key = ([double]$scale).ToString('0.00', [Globalization.CultureInfo]::InvariantCulture)
        $report = [string]$audit.Invoke($null, [object[]]@($schema, $current, $catalog, $snapshot, [double]$scale))
        $out.audit[$locale][$key] = @{ report = $report;
            caption = [int]$form.GetField('AuditedCaption', $static).GetValue($null);
            cards = [int]$form.GetField('AuditedTitleCards', $static).GetValue($null);
            geometry = [string]$form.GetField('AuditedCaptionGeometry', $static).GetValue($null) }
    }
}

# A SoftDialog on its own, never shown: asked for 600 by 400, a body docked to fill it and a row docked at its foot - at
# 100 %, whatever this machine's display is.
$null = S 'Palette' 'Adopt' @('light')
$form.GetField('dpiScale', $static).SetValue($null, [double]1.0)
function Dialog([bool]$minimize, [bool]$maximize, [bool]$mirrored) {
    (T 'Mirror').GetField('Window', $static).SetValue($null, $mirrored)
    $dialog = [Activator]::CreateInstance((T 'SoftDialog'), $true)
    $dialog.Text = 'A dialog with a title of its own'
    $dialog.BackColor = (T 'Palette').GetField('Canvas', $static).GetValue($null)
    $null = S 'Soft' 'DialogBar' @($dialog)
    $dialog.FormBorderStyle = 'FixedDialog'
    $dialog.MinimizeBox = $minimize
    $dialog.MaximizeBox = $maximize
    $dialog.ShowInTaskbar = $false
    $dialog.ClientSize = New-Object Drawing.Size 600, 400
    $body = New-Object Windows.Forms.Panel
    $body.Dock = 'Fill'
    $row = New-Object Windows.Forms.Panel
    $row.Dock = 'Bottom'
    $row.Height = 50
    $dialog.Controls.Add($body)
    $dialog.Controls.Add($row)
    $asked = @([int]$dialog.ClientSize.Width, [int]$dialog.ClientSize.Height)
    $dialog.TopLevel = $false
    $dialog.CreateControl()
    $null = $dialog.Handle
    $dialog.PerformLayout()
    [Windows.Forms.Application]::DoEvents()
    $strip = P $dialog 'TitleGround'; $card = P $dialog 'TitleCard'; $caption = P $dialog 'CaptionHost'
    $buttons = @{}
    foreach ($name in 'MinimizeButton', 'MaximizeButton', 'CloseButton') {
        $b = $caption.GetType().GetField($name, $instance).GetValue($caption)
        $buttons[$name] = @{ shown = [bool](S 'Soft' 'OwnVisible' @($b)); on = [bool]$b.Enabled; box = (Box $b); parent = [bool]($b.Parent -eq $strip);
                             name = [string]$b.AccessibleName; tab = [bool]$b.TabStop }
    }
    $said = @{ asked = $asked; client = @([int]$dialog.ClientSize.Width, [int]$dialog.ClientSize.Height);
               reserve = [int](P $dialog 'TitleReserve'); strip = (Box $strip); card = (Box $card); body = (Box $body); row = (Box $row);
               bodyIndex = [int]$dialog.Controls.GetChildIndex($body); rowIndex = [int]$dialog.Controls.GetChildIndex($row);
               stripIndex = [int]$dialog.Controls.GetChildIndex($strip); count = [int]$dialog.Controls.Count; buttons = $buttons;
               words = (Box (P $dialog 'TitleWords')); title = [string](P $dialog 'TitleWords').Text }
    $dialog.Dispose()
    (T 'Mirror').GetField('Window', $static).SetValue($null, $false)
    return $said
}
$out.dialogs.close = Dialog $false $false $false
$out.dialogs.pair = Dialog $false $true $false
$out.dialogs.mirrored = Dialog $false $true $true

# The day's scenes where the window places one (SettingsForm.PlaceDayScene: DayArt.Fit), drawn offscreen, and the glyph's
# colour against the mean of what each scene puts under each button's glyph box.
$host1 = New-Object Windows.Forms.Panel
$host1.Size = New-Object Drawing.Size 1000, 200
$host1.CreateControl()
$muted = (T 'Palette').GetField('Muted', $static).GetValue($null)
$fit = (T 'DayArt').GetMethod('Fit', $static)
foreach ($look in (ConvertFrom-Json $env:CAR_LOOKS)) {
    $scene = [Activator]::CreateInstance((T 'SoftDayScene'), $true)
    $host1.Controls.Add($scene)
    # A hero 972 by 90 at 100 %: its words end at 300, the scene to its edge less the hairline.
    $call = [object[]]@([string]$look, [int]300, [int]0, [int]972, [int]971, [int]1, [int]89, [int]0, [double]0, [int]0)
    $null = $fit.Invoke($null, $call)
    $left = [int]$call[7]; $unit = [double]$call[8]; $fade = [int]$call[9]
    $width = 971 - $left
    $scene.GetType().GetMethod('Place', $instance).Invoke($scene, (Bare @($true, [string]$look, [int]$left, [int]1, [int]$width, [int]88, [double]$unit, [int]$fade))) | Out-Null
    $bitmap = New-Object Drawing.Bitmap $scene.Width, $scene.Height
    $g = [Drawing.Graphics]::FromImage($bitmap)
    $e = New-Object Windows.Forms.PaintEventArgs $g, $scene.ClientRectangle
    $scene.GetType().GetMethod('OnPaint', $instance).Invoke($scene, (Bare @($e))) | Out-Null
    $g.Dispose()
    $ratios = @()
    # Each glyph's 10 px box, centred in its 34 by 26 button, the buttons 10 in from the hero's top and edge, 4 apart.
    foreach ($k in 0, 1, 2) {
        $buttonLeft = 972 - 10 - 34 - $k * 38
        $gx = $buttonLeft + 12 - $left; $gy = 10 + 8 - 1
        $r = 0.0; $gg = 0.0; $b = 0.0; $n = 0
        for ($y = $gy; $y -lt $gy + 10; $y++) { for ($x = $gx; $x -lt $gx + 10; $x++) {
            if ($x -lt 0 -or $x -ge $bitmap.Width -or $y -lt 0 -or $y -ge $bitmap.Height) { continue }
            $p = $bitmap.GetPixel($x, $y); $r += $p.R; $gg += $p.G; $b += $p.B; $n++
        } }
        if ($n -eq 0) { $ratios += ,@(-1, -1, -1); continue }
        $ratios += ,@([int]($r / $n), [int]($gg / $n), [int]($b / $n))
    }
    $bitmap.Dispose()
    $out.scenes[[string]$look] = @{ left = $left; under = $ratios }
    $host1.Controls.Remove($scene)
    $scene.Dispose()
}
$host1.Dispose()
$out.muted = @([int]$muted.R, [int]$muted.G, [int]$muted.B)
[IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'result.json'), ($out | ConvertTo-Json -Depth 8 -Compress))
"""


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class CaptionWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = compile_window(work)
        current = dict(settings.defaults(), continuation_style="custom", custom_message_mode="per_reason")
        (work / "schema.json").write_text(json.dumps(settings.describe(), ensure_ascii=False), encoding="utf-8")
        (work / "settings.json").write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
        (work / "snapshot.json").write_text(json.dumps(test_gui_layout.fullest_snapshot(time.time()), ensure_ascii=False),
                                            encoding="utf-8")
        for locale in LOCALES:
            reply = {"ok": True, "language": locale, "strings": l10n.catalog(locale), "endonyms": dict(l10n.ENDONYMS),
                     "preference": locale, "system_language": locale}
            (work / ("strings-%s.json" % locale)).write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        cls.answer = run_probe(PROBE, work, 300 * len(LOCALES), CAR_EXE=str(exe), CAR_LOCALES=json.dumps(list(LOCALES)),
                               CAR_SCALES=json.dumps(list(SCALES)), CAR_LOOKS=json.dumps(list(brand.DAY_LOOKS)))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def each(self):
        for locale in LOCALES:
            for scale in SCALES:
                yield locale, scale, self.answer["audit"][locale]["%.2f" % scale]

    def test_the_audit_finds_the_caption_and_every_title_card_in_place(self):
        for locale, scale, said in self.each():
            with self.subTest(locale=locale, scale=scale):
                found = [line for line in said["report"].splitlines() if any(word in line for word in CAPTION_WORDS)]
                self.assertEqual(found, [])
                self.assertEqual(said["caption"], 2, "with the Start button shown, and without")
                self.assertGreaterEqual(said["cards"], 8, "the Timeline, Log, check, report, versions, two words, own values")

    def test_the_buttons_stand_in_the_hero_s_corner_and_the_headline_ends_before_them(self):
        for locale, scale, said in self.each():
            lines = [line for line in said["geometry"].splitlines() if line]
            with self.subTest(locale=locale, scale=scale):
                self.assertEqual(len(lines), 2)
                for line in lines:
                    box, clear, inset = line.split(":", 1)[1].split(";")
                    x, y, width, height = (int(part) for part in box.split(","))
                    self.assertEqual(int(inset), round(10 * scale))
                    self.assertGreaterEqual(int(clear), round(8 * scale))
                    self.assertEqual(width, 3 * round(34 * scale) + 2 * round(4 * scale))
                    self.assertEqual(height, round(26 * scale))
                    if locale in ("ar", "he"):
                        self.assertLess(x, 200, "mirrored: at the hero's left")
                    else:
                        self.assertGreater(x, 600, "at the hero's right")

    def test_a_dialog_is_what_it_asked_plus_its_title(self):
        for kind in ("close", "pair", "mirrored"):
            said = self.answer["dialogs"][kind]
            with self.subTest(kind):
                self.assertEqual(said["asked"], [600, 400])
                self.assertGreater(said["reserve"], 26 + 20)
                self.assertEqual(said["client"], [600, 400 + said["reserve"]])
                self.assertEqual(said["strip"], [0, 0, 600, said["reserve"]])
                self.assertEqual(said["card"], [16, 16, 600 - 32, said["reserve"] - 16])
                self.assertEqual(said["body"], [0, said["reserve"], 600, 400 - 50], "its own layout below the title, as it was")
                self.assertEqual(said["row"], [0, 400 + said["reserve"] - 50, 600, 50])
                self.assertEqual((said["bodyIndex"], said["rowIndex"]), (0, 1), "its controls keep their places")
                self.assertEqual(said["stripIndex"], said["count"] - 1, "the strip is docked first")
                self.assertEqual(said["title"], "A dialog with a title of its own")

    def test_a_dialog_has_the_buttons_its_boxes_ask_for(self):
        close = self.answer["dialogs"]["close"]["buttons"]
        self.assertFalse(close["MinimizeButton"]["shown"])
        self.assertFalse(close["MaximizeButton"]["shown"])
        self.assertTrue(close["CloseButton"]["shown"])
        pair = self.answer["dialogs"]["pair"]["buttons"]
        self.assertEqual((pair["MinimizeButton"]["shown"], pair["MinimizeButton"]["on"]), (True, False), "faint, doing nothing")
        self.assertEqual((pair["MaximizeButton"]["shown"], pair["MaximizeButton"]["on"]), (True, True))
        card = self.answer["dialogs"]["pair"]["card"]
        right = card[0] + card[2]
        boxes = {name: pair[name]["box"] for name in pair}
        self.assertEqual(boxes["CloseButton"][0] + 34, right - 10, "close 10 in from the card's edge")
        self.assertLess(boxes["MinimizeButton"][0], boxes["MaximizeButton"][0])
        self.assertLess(boxes["MaximizeButton"][0], boxes["CloseButton"][0])
        self.assertEqual({pair[name]["box"][1] for name in pair}, {card[1] + 10})
        for name, button in pair.items():
            with self.subTest(name):
                self.assertTrue(button["parent"])
                self.assertFalse(button["tab"])
                self.assertTrue(button["name"])
        words = self.answer["dialogs"]["pair"]["words"]
        self.assertLessEqual(card[0] + words[0] + words[2], boxes["MinimizeButton"][0] - 8)

    def test_mirrored_the_buttons_stand_at_the_left_in_the_other_order(self):
        said = self.answer["dialogs"]["mirrored"]
        boxes = {name: said["buttons"][name]["box"] for name in said["buttons"]}
        self.assertEqual(boxes["CloseButton"][0], said["card"][0] + 10)
        self.assertLess(boxes["CloseButton"][0], boxes["MaximizeButton"][0])
        self.assertLess(boxes["MaximizeButton"][0], boxes["MinimizeButton"][0])

    def test_every_day_s_scene_leaves_the_glyphs_readable(self):
        """3:1 under every glyph, except on the days whose scene is open point O6 (O6_OPEN): measured 1.6 to 2.4 there,
        named for the main session to decide (plans/v0624-stage1-design.md 3.3, 17). Held exactly, so a decision that
        mends one - or a scene that breaks another - shows here."""
        self.assertEqual(sorted(self.answer["scenes"]), sorted(brand.DAY_LOOKS))
        muted = "#%02X%02X%02X" % tuple(self.answer["muted"])
        short = set()
        for look, said in self.answer["scenes"].items():
            for index, under in enumerate(said["under"]):
                with self.subTest(look=look, button=index):
                    self.assertGreaterEqual(min(under), 0, "the glyph's box lies on the scene")
                    ratio = brand_colour.contrast(muted, "#%02X%02X%02X" % tuple(under))
                    if ratio < 3.0:
                        short.add(look)
        self.assertEqual(short, O6_OPEN, "the days under 3:1 (WCAG non-text contrast) are the ones open as O6")


if __name__ == "__main__":
    unittest.main()
