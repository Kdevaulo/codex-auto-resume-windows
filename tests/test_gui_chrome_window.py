r"""v0.6.24 (stage 1, surface A): the window's own caption, built and never shown (gui/SoftChrome.cs).

The window and its dialogs as the layout audit lays them out (SettingsForm.LayoutAudit: not even top-level windows, no
input): the caption buttons in the hero's top outer corner, Brand.CaptionInsetTop below its top and CaptionInsetEnd in from
its edge - the left, mirrored - the headline ending at least 8 px before them in every language tried, at every scaling,
with the Start button shown and without (AuditCaption); every dialog's title row on its ground (v0.6.24-beta.2), 16 px in
and 8 down from its top, its buttons centred in it, and the dialog's own layout below it (AuditTitleRow).

A SoftDialog on its own: its ClientSize is what it was asked plus the title's strip, docked first, its own controls laid
out below it as they were and kept in their places in Controls; Close alone or the pair as its boxes ask; mirrored, the
buttons at the left.

The day's scenes (brand.DAY_LOOKS): each drawn offscreen where the window places it under a caption of the window's own,
and the colour each glyph takes held to 3:1 against what the scene puts under it (WCAG's non-text contrast) - O6 of
plans/v0624-stage1-design.md, decided 2026-11-15: ink or OnAccent where Muted would not stand out, Muted where it does.

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
CAPTION_WORDS = ("caption", "title row", "title's strip", "title ends", "title starts", "title is", "headline ends",
                 "Start button lies")

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
            cards = [int]$form.GetField('AuditedTitleRows', $static).GetValue($null);
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
    $strip = P $dialog 'TitleGround'; $card = P $dialog 'TitleRow'; $caption = P $dialog 'CaptionHost'
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

# The day's scenes where the window places one (SettingsForm.PlaceDayScene: DayArt.Fit), under a caption of the window's own
# (ChromeHost over a card, its Scene the day's): each button's background painted as the window paints it, the colour its
# glyph then takes at rest (CaptionButton.OverSceneInk: Empty is Palette.Muted, as on every other day), and the mean of what
# the scene put in the glyph's box of that very picture.
$muted = (T 'Palette').GetField('Muted', $static).GetValue($null)
$fit = (T 'DayArt').GetMethod('Fit', $static)
foreach ($look in (ConvertFrom-Json $env:CAR_LOOKS)) {
    $holder = New-Object Windows.Forms.Form
    $holder.TopLevel = $false
    $holder.ClientSize = New-Object Drawing.Size 1000, 200
    $card = [Activator]::CreateInstance((T 'SoftCard'), $true)
    $card.SetBounds(0, 0, 972, 90)
    $holder.Controls.Add($card)
    $caption = S 'ChromeHost' 'Install' @($holder, $card, $holder)
    $scene = [Activator]::CreateInstance((T 'SoftDayScene'), $true)
    $holder.Controls.Add($scene)
    # A hero 972 by 90 at 100 %: its words end at 300, the scene to its edge less the hairline.
    $call = [object[]]@([string]$look, [int]300, [int]0, [int]972, [int]971, [int]1, [int]89, [int]0, [double]0, [int]0)
    $null = $fit.Invoke($null, $call)
    $left = [int]$call[7]; $unit = [double]$call[8]; $fade = [int]$call[9]
    $width = 971 - $left
    $scene.GetType().GetMethod('Place', $instance).Invoke($scene, (Bare @($true, [string]$look, [int]$left, [int]1, [int]$width, [int]88, [double]$unit, [int]$fade))) | Out-Null
    $caption.GetType().GetProperty('Scene', $instance).SetValue($caption, $scene, $null)
    $said = @()
    foreach ($name in 'MinimizeButton', 'MaximizeButton', 'CloseButton') {
        $button = $caption.GetType().GetField($name, $instance).GetValue($caption)
        $bitmap = New-Object Drawing.Bitmap $button.Width, $button.Height
        $g = [Drawing.Graphics]::FromImage($bitmap)
        $e = New-Object Windows.Forms.PaintEventArgs $g, $button.ClientRectangle
        $button.GetType().GetMethod('OnPaintBackground', $instance).Invoke($button, (Bare @($e))) | Out-Null
        $g.Dispose()
        $ink = $button.GetType().GetProperty('OverSceneInk', $instance).GetValue($button, $null)
        if ($ink.IsEmpty) { $ink = $muted }
        $gx = [int](($button.Width - 10) / 2); $gy = [int](($button.Height - 10) / 2)
        $r = 0.0; $gg = 0.0; $b = 0.0; $n = 0
        for ($y = $gy; $y -lt $gy + 10; $y++) { for ($x = $gx; $x -lt $gx + 10; $x++) {
            $p = $bitmap.GetPixel($x, $y); $r += $p.R; $gg += $p.G; $b += $p.B; $n++
        } }
        $bitmap.Dispose()
        $said += ,@{ box = (Box $button); onScene = [bool]$button.Bounds.IntersectsWith($scene.Bounds);
                     under = @([int]($r / $n), [int]($gg / $n), [int]($b / $n)); ink = @([int]$ink.R, [int]$ink.G, [int]$ink.B) }
    }
    $out.scenes[[string]$look] = @{ left = $left; buttons = $said }
    $holder.Dispose()
}
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
                self.assertEqual(said["reserve"], 8 + 26 + 8, "v0.6.24-beta.2: a row on the ground, where the card took 62")
                self.assertEqual(said["client"], [600, 400 + said["reserve"]])
                self.assertEqual(said["strip"], [0, 0, 600, said["reserve"]])
                self.assertEqual(said["card"], [16, 8, 600 - 32, said["reserve"] - 16], "the title row")
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
        self.assertEqual(boxes["CloseButton"][0] + 34, right - 10, "close 10 in from the row's end")
        self.assertLess(boxes["MinimizeButton"][0], boxes["MaximizeButton"][0])
        self.assertLess(boxes["MaximizeButton"][0], boxes["CloseButton"][0])
        self.assertEqual({pair[name]["box"][1] for name in pair}, {card[1] + (card[3] - 26) // 2}, "centred in the row")
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
        """O6, decided by the main session 2026-11-15: over a day's scene each glyph at rest takes whichever of ink and
        OnAccent stands out by 3:1 (WCAG's non-text contrast) from what the scene puts under it, measured from the scene's
        own drawing where the button stands - and keeps Muted, as on every other day, wherever Muted already does."""
        self.assertEqual(sorted(self.answer["scenes"]), sorted(brand.DAY_LOOKS))
        hex_of = lambda rgb: "#%02X%02X%02X" % tuple(rgb)
        muted = hex_of(self.answer["muted"])
        on_scene = 0
        for look, said in self.answer["scenes"].items():
            for index, button in enumerate(said["buttons"]):
                with self.subTest(look=look, button=index):
                    under, ink = hex_of(button["under"]), hex_of(button["ink"])
                    on_scene += button["onScene"]
                    self.assertGreaterEqual(brand_colour.contrast(ink, under), 3.0, "the glyph stands out from the scene")
                    if brand_colour.contrast(muted, under) >= 3.0:
                        self.assertEqual(ink, muted, "no change where Muted already stands out")
        self.assertGreater(on_scene, 0, "the buttons stood over the scenes measured")

if __name__ == "__main__":
    unittest.main()
