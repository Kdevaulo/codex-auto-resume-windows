r"""v0.6.24 (stage 1, surface A): the frame of a window whose caption is its own (gui/SoftChrome.cs).

Windows works a window's client area out in WM_NCCALCSIZE. The window keeps Windows' answer for the left, right and
bottom frames and puts the top back at the window's top - no caption strip, no top frame (Chrome.ClientFor); maximised, a
window hangs its frame past the screen's edge, so its top comes down by that much, the left frame Windows worked out. And
a Form works its window's size out from its styles, which still count WS_CAPTION: with the caption gone, every
`dialog.ClientSize = ...` would open a dialog a caption taller than it asked (SoftDialog, SettingsForm and InstallerWindow
answer SizeFromClientSize with the frames alone - Chrome.Frame, WindowSize). Asked here with no window made: the compiled
window's assembly is loaded and the functions called, and a SoftDialog is given a client size before it has a window.

The buttons' names are Windows' own words for the commands, read from the window menu with their access key and
shortcut taken off (Chrome.CommandName).

Not a GUI test: nothing is shown and no window is made.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from test_gui_v0611_access import CSC, POWERSHELL, compile_window, run_probe

# (proposed, computed, maximised) -> the client, each a rectangle left, top, right, bottom.
CLIENT_FOR = {
    "restored": ([100, 100, 1100, 800], [108, 131, 1092, 792], False, [108, 100, 1092, 792]),
    "maximized_100": ([-8, -8, 1928, 1048], [0, 23, 1920, 1040], True, [0, 0, 1920, 1040]),
    "maximized_150": ([-11, -11, 1931, 1051], [0, 34, 1920, 1040], True, [0, 0, 1920, 1040]),
    "maximized_200": ([-15, -15, 1935, 1055], [0, 46, 1920, 1040], True, [0, 0, 1920, 1040]),
    "fixed_dialog": ([200, 200, 700, 600], [203, 229, 697, 597], False, [203, 200, 697, 597]),
    "borderless": ([0, 0, 640, 480], [0, 0, 640, 480], False, [0, 0, 640, 480]),
}

COMMAND_NAMES = {
    "Mi&nimize": "Minimize",
    "Ma&ximize": "Maximize",
    "&Restore": "Restore",
    "&Close\tAlt+F4": "Close",
    "최소화(&N)": "최소화",
    "닫기(&C)\tAlt+F4": "닫기",
    "最小化（&N）": "最小化",
    "Save && go": "Save & go",
    "&": "fallback",
    "": "fallback",
}

PROBE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Frames {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool AdjustWindowRectEx(ref RECT rect, int style, bool menu, int exStyle);
    public static int[] Of(int style, int exStyle) { var r = new RECT(); AdjustWindowRectEx(ref r, style, false, exStyle); return new[] { r.Left, r.Top, r.Right, r.Bottom }; }
}
'@
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$static = [Reflection.BindingFlags]'Static,NonPublic,Public'
$instance = [Reflection.BindingFlags]'Instance,NonPublic,Public'
$chrome = $assembly.GetType('CodexAutoResume.Chrome', $true)
function S([string]$name, [object[]]$arguments) {
    $m = @($chrome.GetMethods($static) | Where-Object { $_.Name -eq $name -and $_.GetParameters().Count -eq $arguments.Count })[0]
    return $m.Invoke($null, (Bare $arguments))
}
function Bare([object[]]$items) { $bare = New-Object 'object[]' $items.Length; for ($i = 0; $i -lt $items.Length; $i++) { $one = $items[$i]; if ($one -is [Management.Automation.PSObject]) { $one = $one.PSObject.BaseObject }; $bare[$i] = $one }; return ,$bare }
function LTRB($r) { return [Drawing.Rectangle]::FromLTRB([int]$r[0], [int]$r[1], [int]$r[2], [int]$r[3]) }
$cases = ConvertFrom-Json ([IO.File]::ReadAllText((Join-Path $env:CAR_WORK 'cases.json'), [Text.Encoding]::UTF8))
$out = @{ clientFor = @{}; names = @{}; frames = @{}; dialogs = @{} }
foreach ($name in $cases.clientFor.PSObject.Properties.Name) {
    $case = $cases.clientFor.$name
    $r = S 'ClientFor' @((LTRB $case[0]), (LTRB $case[1]), [bool]$case[2])
    $out.clientFor[$name] = @($r.Left, $r.Top, $r.Right, $r.Bottom)
}
$i = 0
foreach ($pair in $cases.names) {
    $out.names["$i"] = [string](S 'CommandName' @([string]$pair[0], 'fallback'))
    $i++
}
$out.nameOfNull = [string](S 'CommandName' @($null, 'fallback'))
# The frames: WS_OVERLAPPEDWINDOW and a dialog's WS_CAPTION | WS_SYSMENU with WS_EX_DLGMODALFRAME, against Windows' own.
foreach ($style in @(@('sizable', 0x00CF0000, 0), @('dialog', 0x00C80000, 0x00000001), @('popup', [int]0x80000000, 0))) {
    $frame = S 'Frame' @([int]$style[1], [int]$style[2])
    $out.frames[$style[0]] = @{ ours = @($frame.Left, $frame.Top, $frame.Right, $frame.Bottom); windows = [Frames]::Of([int]$style[1], [int]$style[2]) }
}
$frame = S 'Frame' @([int]0x00CF0000, [int]0)
$outer = S 'WindowSize' @((New-Object Drawing.Size 600, 400), $frame)
$back = S 'ClientOf' @($outer, $frame)
$out.roundTrip = @($outer.Width, $outer.Height, $back.Width, $back.Height)
# A SoftDialog given its client size before it has a window, as every dialog's Build* gives it - then its border changed,
# as most of them change it after.
$dialogType = $assembly.GetType('CodexAutoResume.SoftDialog', $true)
foreach ($border in @('Sizable', 'FixedDialog')) {
    $dialog = [Activator]::CreateInstance($dialogType, $true)
    $dialog.ClientSize = New-Object Drawing.Size 600, 400
    $first = @($dialog.ClientSize.Width, $dialog.ClientSize.Height, $dialog.Width, $dialog.Height)
    $dialog.FormBorderStyle = $border
    $dialog.ClientSize += New-Object Drawing.Size 24, 29
    $out.dialogs[$border] = @{ first = $first; after = @($dialog.ClientSize.Width, $dialog.ClientSize.Height, $dialog.Width, $dialog.Height);
                       handle = [bool]$dialog.IsHandleCreated }
    $dialog.Dispose()
}
[IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'result.json'), ($out | ConvertTo-Json -Depth 6 -Compress), [Text.Encoding]::UTF8)
"""


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class CaptionFrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = compile_window(work)
        (work / "cases.json").write_text(json.dumps({
            "clientFor": {name: [proposed, computed, maximized] for name, (proposed, computed, maximized, _) in CLIENT_FOR.items()},
            "names": [[menu, wanted] for menu, wanted in COMMAND_NAMES.items()]}, ensure_ascii=False), encoding="utf-8")
        cls.answer = run_probe(PROBE, work, 300, CAR_EXE=str(exe))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_the_client_starts_at_the_window_s_top_and_maximised_below_the_overhang(self):
        for name, (_proposed, _computed, _maximized, wanted) in CLIENT_FOR.items():
            with self.subTest(name):
                self.assertEqual(self.answer["clientFor"][name], wanted)

    def test_the_frame_is_windows_left_right_and_bottom_and_nothing_at_the_top(self):
        for style in ("sizable", "dialog"):
            with self.subTest(style):
                ours, windows = self.answer["frames"][style]["ours"], self.answer["frames"][style]["windows"]
                self.assertEqual(ours, [-windows[0], 0, windows[2], windows[3]])
                self.assertGreater(windows[2], 0, "a window with a frame")
                self.assertLess(windows[1], -windows[3], "Windows' own frame counts a caption at the top")
        self.assertEqual(self.answer["frames"]["popup"]["ours"], [0, 0, 0, 0], "a window with no frame has none")

    def test_window_size_and_client_size_undo_each_other(self):
        width, height, back_width, back_height = self.answer["roundTrip"]
        self.assertEqual((back_width, back_height), (600, 400))
        left, _top, right, bottom = self.answer["frames"]["sizable"]["ours"]
        self.assertEqual((width, height), (600 + left + right, 400 + bottom))

    def test_a_dialog_s_client_size_means_what_it_says_before_it_has_a_window(self):
        for border in ("Sizable", "FixedDialog"):
            with self.subTest(border):
                given = self.answer["dialogs"][border]
                self.assertFalse(given["handle"], "no window was made")
                width, height, outer_width, outer_height = given["first"]
                self.assertEqual((width, height), (600, 400))
                side = (outer_width - width) / 2
                self.assertGreater(side, 0)
                self.assertEqual(outer_height - height, side, "the frames at the sides and the bottom only, no caption")
                width, height, outer_width, outer_height = given["after"]
                self.assertEqual((width, height), (624, 429), "a growth added to it lands as it was asked")
                self.assertEqual(outer_height - height, (outer_width - width) / 2)

    def test_the_commands_are_named_in_windows_own_words(self):
        for index, (menu, wanted) in enumerate(COMMAND_NAMES.items()):
            with self.subTest(menu=menu):
                self.assertEqual(self.answer["names"][str(index)], wanted)
        self.assertEqual(self.answer["nameOfNull"], "fallback")


if __name__ == "__main__":
    unittest.main()
