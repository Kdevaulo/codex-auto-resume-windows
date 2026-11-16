r"""v0.6.24 (stage 1, surface A): what the pointer is over in a window whose caption is its own (gui/SoftChrome.cs, Chrome.Hit).

No window of ours has Windows' title bar any more: the minimise, maximise and close buttons stand in the window's first
card, and Windows still asks the window what each point is (WM_NCHITTEST) - which is what gives it its own move loop,
Aero snap, double-click to maximise, the window menu on a right click, the top edge that resizes, and on Windows 11 the
snap layouts on the maximise button (HTMAXBUTTON). Chrome.Hit is the answer, a pure function of the window's layout, so it
is asked here a table with no window at all: the compiled window's assembly is loaded and the function called.

* the top resize band (HTTOP and its corners) only on a sizable window that is not maximised;
* the maximise button HTMAXBUTTON only while it does something, and the client's when it is faint;
* minimise and close the client's: they are controls of their own;
* the card and the ground HTCAPTION; a control inside them (the Start button) the client's;
* mirrored, the buttons at the left - and maximised, the strip above each button and the room past close are the
  buttons', as a maximised window's caption is hit by flinging the pointer into the screen's corner;
* a dialog with Close alone has no HTMAXBUTTON anywhere.

Not a GUI test: nothing is shown and no window is made.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from test_gui_v0611_access import CSC, POWERSHELL, compile_window, run_probe

HTCLIENT, HTCAPTION, HTMINBUTTON, HTMAXBUTTON, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTCLOSE = 1, 2, 8, 9, 12, 13, 14, 20
HTLEFT, HTRIGHT, HTBOTTOM, HTBOTTOMLEFT = 10, 11, 15, 16

# A window 1000 by 700 at 100 %, its top band 8 px, the buttons 34 by 26, 4 apart, 10 in from the hero's corner -
# the hero 14 in from the window's sides and 12 down.
CLIENT = [1000, 700]
MINIMIZE, MAXIMIZE, CLOSE = [838, 22, 34, 26], [876, 22, 34, 26], [914, 22, 34, 26]
START = [800, 60, 120, 34]
# Mirrored: close, maximise, minimise from the left.
M_CLOSE, M_MAXIMIZE, M_MINIMIZE = [24, 22, 34, 26], [62, 22, 34, 26], [100, 22, 34, 26]


def layout(**given):
    base = {"Client": CLIENT, "Sizable": True, "Maximized": False, "Mirrored": False, "Band": 8,
            "Minimize": MINIMIZE, "Maximize": MAXIMIZE, "Close": CLOSE, "MinimizeOn": True, "MaximizeOn": True,
            "Solid": [START]}
    base.update(given)
    return base


CENTRE = lambda r: [r[0] + r[2] // 2, r[1] + r[3] // 2]

CASES = {
    "band": ([500, 3], layout(), HTTOP),
    "band_left": ([5, 3], layout(), HTTOPLEFT),
    "band_right": ([995, 3], layout(), HTTOPRIGHT),
    "band_fixed": ([500, 3], layout(Sizable=False), HTCAPTION),
    "band_maximized": ([500, 3], layout(Maximized=True), HTCAPTION),
    "below_band": ([500, 8], layout(), HTCAPTION),
    "maximize": (CENTRE(MAXIMIZE), layout(), HTMAXBUTTON),
    "maximize_faint": (CENTRE(MAXIMIZE), layout(MaximizeOn=False), HTCLIENT),
    "minimize": (CENTRE(MINIMIZE), layout(), HTCLIENT),
    "close": (CENTRE(CLOSE), layout(), HTCLIENT),
    "gap_between_buttons": ([874, 30], layout(), HTCAPTION),
    "drag_area": ([500, 40], layout(), HTCAPTION),
    "control_in_the_hero": (CENTRE(START), layout(), HTCLIENT),
    "restored_past_close": ([990, 30], layout(), HTCAPTION),
    "restored_above_close": ([930, 12], layout(), HTCAPTION),
    "maximized_above_close": ([930, 2], layout(Maximized=True), HTCLOSE),
    "maximized_above_maximize": ([890, 2], layout(Maximized=True), HTMAXBUTTON),
    "maximized_above_faint_maximize": ([890, 2], layout(Maximized=True, MaximizeOn=False), HTCLIENT),
    "maximized_above_minimize": ([850, 2], layout(Maximized=True), HTMINBUTTON),
    "maximized_past_close": ([999, 30], layout(Maximized=True), HTCLOSE),
    "maximized_corner": ([999, 0], layout(Maximized=True), HTCLOSE),
    "maximized_below_buttons": ([999, 60], layout(Maximized=True), HTCAPTION),
    "mirrored_maximize": (CENTRE(M_MAXIMIZE), layout(Mirrored=True, Minimize=M_MINIMIZE, Maximize=M_MAXIMIZE, Close=M_CLOSE),
                          HTMAXBUTTON),
    "mirrored_right_is_ground": ([900, 30], layout(Mirrored=True, Minimize=M_MINIMIZE, Maximize=M_MAXIMIZE, Close=M_CLOSE),
                                 HTCAPTION),
    "mirrored_maximized_past_close": ([0, 30], layout(Mirrored=True, Maximized=True, Minimize=M_MINIMIZE,
                                                      Maximize=M_MAXIMIZE, Close=M_CLOSE), HTCLOSE),
    "mirrored_maximized_right_corner": ([999, 0], layout(Mirrored=True, Maximized=True, Minimize=M_MINIMIZE,
                                                         Maximize=M_MAXIMIZE, Close=M_CLOSE), HTCAPTION),
    # v0.6.24: the window's own corner, cut away 24 px along each edge - its corner target runs a band past that
    # (re-check 5: only the ~3 px diagonal between the cut and the page resized from the corner at 150 %).
    "own_corner_bottom_edge": ([30, 699], layout(Edges=True, CornerSpan=24), HTBOTTOMLEFT),
    "own_corner_left_edge": ([3, 669], layout(Edges=True, CornerSpan=24), HTBOTTOMLEFT),
    "own_corner_top_edge": ([969, 3], layout(Edges=True, CornerSpan=24), HTTOPRIGHT),
    "own_corner_past_its_reach": ([33, 699], layout(Edges=True, CornerSpan=24), HTBOTTOM),
    "own_corner_side_past_its_reach": ([3, 667], layout(Edges=True, CornerSpan=24), HTLEFT),
    "windows_corner_keeps_twice_the_band": ([969, 3], layout(CornerSpan=24), HTTOP),
    # Re-check 6: the top corners as the bottom ones - down each side too, not only along the top.
    "own_corner_left_side_from_the_top": ([3, 25], layout(Edges=True, CornerSpan=24), HTTOPLEFT),
    "own_corner_right_side_from_the_top": ([996, 31], layout(Edges=True, CornerSpan=24), HTTOPRIGHT),
    "own_corner_left_side_past_its_reach": ([3, 32], layout(Edges=True, CornerSpan=24), HTLEFT),
    "own_corner_right_side_past_its_reach": ([996, 40], layout(Edges=True, CornerSpan=24), HTRIGHT),
}

# A dialog with Close alone, fixed: every point of a grid over it.
DIALOG = layout(Sizable=False, Minimize=[0, 0, 0, 0], Maximize=[0, 0, 0, 0], Close=[914, 22, 34, 26], Solid=[])

PROBE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$static = [Reflection.BindingFlags]'Static,NonPublic,Public'
$instance = [Reflection.BindingFlags]'Instance,NonPublic,Public'
$chrome = $assembly.GetType('CodexAutoResume.Chrome', $true)
$type = $assembly.GetType('CodexAutoResume.ChromeLayout', $true)
$hit = $chrome.GetMethod('Hit', $static)
function Bare([object[]]$items) { $bare = New-Object 'object[]' $items.Length; for ($i = 0; $i -lt $items.Length; $i++) { $one = $items[$i]; if ($one -is [Management.Automation.PSObject]) { $one = $one.PSObject.BaseObject }; $bare[$i] = $one }; return ,$bare }
function Rect($r) { return New-Object Drawing.Rectangle ([int]$r[0]), ([int]$r[1]), ([int]$r[2]), ([int]$r[3]) }
function Layout($given) {
    $box = [Activator]::CreateInstance($type)
    $type.GetField('Client', $instance).SetValue($box, (New-Object Drawing.Size ([int]$given.Client[0]), ([int]$given.Client[1])))
    foreach ($flag in 'Sizable', 'Maximized', 'Mirrored', 'MinimizeOn', 'MaximizeOn', 'Edges') { $type.GetField($flag, $instance).SetValue($box, [bool]$given.$flag) }
    $type.GetField('Band', $instance).SetValue($box, [int]$given.Band)
    $type.GetField('CornerSpan', $instance).SetValue($box, [int]$given.CornerSpan)
    foreach ($part in 'Minimize', 'Maximize', 'Close') { $type.GetField($part, $instance).SetValue($box, (Rect $given.$part)) }
    $solid = New-Object 'Drawing.Rectangle[]' (@($given.Solid).Count)
    for ($i = 0; $i -lt $solid.Length; $i++) { $solid[$i] = Rect @($given.Solid)[$i] }
    $type.GetField('Solid', $instance).SetValue($box, $solid)
    $type.GetField('SolidCount', $instance).SetValue($box, [int]$solid.Length)
    return ,$box
}
$cases = ConvertFrom-Json ([IO.File]::ReadAllText((Join-Path $env:CAR_WORK 'cases.json')))
$out = @{ cases = @{}; grid = @() }
foreach ($name in $cases.cases.PSObject.Properties.Name) {
    $case = $cases.cases.$name
    $box = Layout $case.layout
    $point = New-Object Drawing.Point ([int]$case.point[0]), ([int]$case.point[1])
    $out.cases[$name] = [int]$hit.Invoke($null, (Bare @($point, $box)))
}
$dialog = Layout $cases.dialog
for ($y = 0; $y -lt 700; $y += 3) { for ($x = 0; $x -lt 1000; $x += 3) {
    $code = [int]$hit.Invoke($null, (Bare @((New-Object Drawing.Point $x, $y), $dialog)))
    if ($out.grid -notcontains $code) { $out.grid += $code }
} }
# The layout read back, so a box that did not take its fields cannot pass for an answer.
$box = Layout $cases.cases.band.layout
$out.readBack = [int]$type.GetField('Band', $instance).GetValue($box)
[IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'result.json'), ($out | ConvertTo-Json -Depth 6 -Compress))
"""


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class CaptionHitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = compile_window(work)
        (work / "cases.json").write_text(json.dumps({
            "cases": {name: {"point": point, "layout": given} for name, (point, given, _) in CASES.items()},
            "dialog": DIALOG}), encoding="utf-8")
        cls.answer = run_probe(PROBE, work, 300, CAR_EXE=str(exe))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_the_layout_reaches_the_function(self):
        self.assertEqual(self.answer["readBack"], 8)

    def test_every_point_of_the_table(self):
        for name, (_point, _given, wanted) in CASES.items():
            with self.subTest(name):
                self.assertEqual(self.answer["cases"][name], wanted)

    def test_a_dialog_with_close_alone_has_no_maximise_and_no_top_band(self):
        grid = set(self.answer["grid"])
        self.assertNotIn(HTMAXBUTTON, grid)
        self.assertNotIn(HTTOP, grid)
        self.assertNotIn(HTMINBUTTON, grid)
        self.assertEqual(grid, {HTCAPTION, HTCLIENT}, "the ground to drag by, and Close")


if __name__ == "__main__":
    unittest.main()
