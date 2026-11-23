r"""A special-day pill nudge under way comes to rest under battery saver (v0.6.26, plans/v0626-audit4/audit-gui.md C1).

Battery saver or a locked session (Motion.Ambient) holds the pill still, but a nudge under way first eases to rest
(PillHint.Settling: the lift kept is over a thousandth of a pixel). The nudge's eased tail often lands between a
thousandth and a hundredth of a pixel up the frame before rest, and a change under a hundredth was never kept: that
lift stayed, the pill went on settling, the 33 ms beat and the clock ran on, and whole further nudges played under
battery saver - in the audit's line-for-line copy, 207 of 400 starting phases at 100 %. Now the pill's coming to rest is
always kept, exactly (PillHint.Changes, Set).

The window is compiled from the shipped sources and the probe drives PillHint's own Set and Settling, beat by beat as
Beat does under battery saver, on a control that is never shown: no window is made. GUI test module (it compiles the
window): run on its own, through gui_lock.sh.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from test_gui_v0611_access import CSC, POWERSHELL, compile_window, run_probe

PROBE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$static = [Reflection.BindingFlags]'Static,NonPublic,Public'
$instance = [Reflection.BindingFlags]'Instance,NonPublic,Public'
$type = $assembly.GetType('CodexAutoResume.PillHint', $true)
$nudgeAt = $type.GetMethod('NudgeAt', $static)
$settling = $type.GetMethod('Settling', $static)
$set = $type.GetMethod('Set', $instance)
$liftOf = $type.GetProperty('Lift', $instance)
$made = $type.GetConstructor($instance, $null, [Type[]]@([Windows.Forms.Control]), $null)
$beat = 33
$out = @{ scales = @() }
foreach ($scale in 1.0, 1.5, 2.0) {
    $unsettled = 0
    $latest = 0
    $phases = 200
    for ($i = 0; $i -lt $phases; $i++) {
        $pill = New-Object Windows.Forms.Panel
        $hint = $made.Invoke([object[]]@([Windows.Forms.Control]$pill))
        # A beat with motion allowed, somewhere in the nudge (6020 to 7000 ms of its 7 s); then battery saver.
        $start = 6020.0 + 980.0 * $i / $phases
        $null = $set.Invoke($hint, [object[]]@([double]([double]$nudgeAt.Invoke($null, [object[]]@($start)) * $scale), [double]0))
        $t = $start
        while ([bool]$settling.Invoke($null, [object[]]@($true, [double]$liftOf.GetValue($hint, $null))) -and ($t - $start) -lt 1500) {
            $t += $beat
            $null = $set.Invoke($hint, [object[]]@([double]([double]$nudgeAt.Invoke($null, [object[]]@($t)) * $scale), [double]0))
        }
        $lift = [double]$liftOf.GetValue($hint, $null)
        if ($t -gt 7000.0 + $beat -or [bool]$settling.Invoke($null, [object[]]@($true, $lift))) { $unsettled++ }
        if ($t - $start -gt $latest) { $latest = $t - $start }
        $hint.Dispose()
        $pill.Dispose()
    }
    $out.scales += ,@{ scale = $scale; phases = $phases; unsettled = $unsettled; latest = $latest }
}
[IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'result.json'), ($out | ConvertTo-Json -Depth 6 -Compress))
"""


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class PillSettlesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = compile_window(work)
        cls.answer = run_probe(PROBE, work, 300, CAR_EXE=str(exe))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_a_nudge_under_way_rests_by_its_own_end_at_every_scale(self):
        scales = self.answer["scales"]
        self.assertEqual([round(entry["scale"], 1) for entry in scales], [1.0, 1.5, 2.0])
        for entry in scales:
            with self.subTest(scale=entry["scale"]):
                self.assertEqual(entry["phases"], 200)
                self.assertEqual(entry["unsettled"], 0, "phases that held only a nudge later, or never")
                # From the earliest phase the nudge has 980 ms to go, and a beat more to be seen at rest.
                self.assertLessEqual(entry["latest"], 980 + 33)


if __name__ == "__main__":
    unittest.main()
