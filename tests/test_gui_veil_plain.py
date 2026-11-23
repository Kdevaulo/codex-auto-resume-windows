r"""The veil over a dialog's owner makes no picture of the owner's whole size where it is plain (v0.6.26,
plans/v0626-audit4/audit-gui.md C3).

D10 drew the veil pixel by pixel (UpdateLayeredWindow) at the owner's edge coverage, and made that picture on every
dialog's opening - a DIB of the owner's size, a managed copy of it filled pixel by pixel and the coverage array - even
where no pixel of it is part-covered: a maximised Dashboard on a 4K screen took 44 ms on the UI thread and about 61 MB
before the dialog's first frame. Now where every pixel is wholly the owner's (maximised, Windows 10, a region of the
owner's own) the veil is its ink at Windows' constant alpha, as before D10, and makes no picture; under a corner with an
anti-aliased edge it is the picture still (D10 kept), and in both it follows the dialog's fade step for step (D9 kept).

The window is compiled from the shipped sources. The probe shows a stand-in owner with a region of its own and a dialog
over it, both far off the screen and never activated, then a soft owner with a corner of its own and a dialog over that.
GUI test module: run on its own, through gui_lock.sh.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import guiscan
from test_gui_v0611_access import CSC, POWERSHELL, compile_window, run_probe

PROBE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode([System.Windows.Forms.UnhandledExceptionMode]::ThrowException)
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class CarPlainVeil {
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern bool GetLayeredWindowAttributes(IntPtr h, out uint key, out byte alpha, out uint flags);
    public static int[] Layered(IntPtr h) {
        uint key, flags; byte alpha;
        bool ok = GetLayeredWindowAttributes(h, out key, out alpha, out flags);
        return new int[] { ok ? 1 : 0, alpha, (int)flags };
    }
}
'@
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$static = [Reflection.BindingFlags]'Static,NonPublic,Public'
$instance = [Reflection.BindingFlags]'Instance,NonPublic,Public'
function T([string]$name) { return $assembly.GetType('CodexAutoResume.' + $name, $true) }
function P($target, [string]$name) { return $target.GetType().GetProperty($name, $instance).GetValue($target, $null) }
function Pump([int]$ms) { $until = [DateTime]::Now.AddMilliseconds($ms); while ([DateTime]::Now -lt $until) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 3 } }
$null = (T 'Palette').GetMethod('Adopt', $static, $null, [Type[]]@([string]), $null).Invoke($null, [object[]]@('light'))
(T 'SettingsForm').GetField('dpiScale', $static).SetValue($null, [double]1.0)
(T 'Soft').GetField('ReduceMotionSetting', $static).SetValue($null, $false)
(T 'Soft').GetField('WindowsAnimates', $static).SetValue($null, [Func[bool]]{ $true })
function Dialog([string]$title, [int]$x) {
    $dialog = [Activator]::CreateInstance((T 'SoftDialog'), $true)
    $dialog.Text = $title
    $dialog.BackColor = (T 'Palette').GetField('Canvas', $static).GetValue($null)
    $null = (T 'Soft').GetMethod('DialogBar', $static).Invoke($null, [object[]]@($dialog))
    $dialog.FormBorderStyle = 'FixedDialog'; $dialog.MinimizeBox = $false; $dialog.MaximizeBox = $false
    $dialog.ShowInTaskbar = $false
    $dialog.StartPosition = 'Manual'; $dialog.Location = New-Object System.Drawing.Point($x, -30000)
    $dialog.ClientSize = New-Object System.Drawing.Size 640, 420
    return $dialog
}
function Veiled($owner, [int]$x) {
    $seen = @{}
    $dialog = Dialog 'A dialog over it' $x
    $dialog.Owner = $owner
    $null = $dialog.Handle
    [void][CarPlainVeil]::ShowWindow($dialog.Handle, 4)
    $veil = P $dialog 'Veil'
    $seen.veiled = $null -ne $veil
    $seen.steps = @()
    $seen.layered = @()
    if ($veil) {
        $seen.plain = [bool](P $veil 'Plain')
        $seen.pictured = [bool](P $veil 'Pictured')
        $seen.full = [int](P $veil 'Full')
        $clock = [Diagnostics.Stopwatch]::StartNew()
        while ($clock.ElapsedMilliseconds -lt 900) {
            [Windows.Forms.Application]::DoEvents()
            $seen.steps += ,@([int](P $dialog 'FadeAlpha'), [int](P $veil 'Alpha'))
            if ($seen.plain) { $seen.layered += ,([int[]][CarPlainVeil]::Layered($veil.Handle)) }
            Start-Sleep -Milliseconds 3
        }
        $coverage = $veil.GetType().GetMethod('Coverage', $instance)
        $seen.corner = [int]$coverage.Invoke($veil, [object[]]@(0, 0))
        $seen.middle = [int]$coverage.Invoke($veil, [object[]]@(20, 20))
        $seen.outside = [int]$coverage.Invoke($veil, [object[]]@(-1, 0))
    }
    $dialog.Close(); Pump 50
    $seen.gone = $null -eq (P $dialog 'Veil')
    $dialog.Dispose()
    return $seen
}
$out = @{}
# An owner with a region of its own: no pixel of the veil is part-covered.
$plainOwner = New-Object Windows.Forms.Form
$plainOwner.FormBorderStyle = 'None'; $plainOwner.ShowInTaskbar = $false
$plainOwner.StartPosition = 'Manual'; $plainOwner.Location = New-Object System.Drawing.Point(-30000, -30000)
$plainOwner.Size = New-Object System.Drawing.Size 700, 480
$plainOwner.Region = New-Object Drawing.Region (New-Object Drawing.Rectangle 0, 0, 700, 480)
$null = $plainOwner.Handle
[void][CarPlainVeil]::ShowWindow($plainOwner.Handle, 4)
Pump 300
$out.plain = Veiled $plainOwner -29000
$plainOwner.Close(); $plainOwner.Dispose()
# A soft owner, with a corner of its own where this machine gives it one: its anti-aliased edge kept (D10).
$softOwner = Dialog 'The window under it' -30000
$null = $softOwner.Handle
[void][CarPlainVeil]::ShowWindow($softOwner.Handle, 4)
Pump 900
$corner = (T 'WindowCorner').GetMethod('Of', $static).Invoke($null, [object[]]@($softOwner))
$out.owner_shaped = ($null -ne $corner) -and [bool](P $corner 'Shaped')
$out.soft = Veiled $softOwner -29000
$softOwner.Close(); $softOwner.Dispose()
[IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'result.json'), ($out | ConvertTo-Json -Depth 6 -Compress), (New-Object Text.UTF8Encoding $false))
"""

LWA_ALPHA = 2


class SourceTests(unittest.TestCase):
    def test_a_plain_veil_builds_no_picture_of_the_owner_s_size(self):
        veil = guiscan.type_body("DialogVeil")
        made = veil[veil.index("private DialogVeil(IntPtr owner, IntPtr dialog, int alpha)"):]
        self.assertIn("if (cover != null) Picture();", made)
        shape = veil[veil.index("private static byte[] Shape("):veil.index("private static byte[] Whole(")]
        # Maximised and Windows 10, and a region of the owner's own: null, before any array of the owner's size.
        zoomed = shape.index("if (!WindowShape.Windows11 || IsZoomed(owner)) return null;")
        self.assertLess(zoomed, shape.rindex("Whole(bounds.Size)"))
        self.assertIn("region = own;\n                return null;", shape.replace("\r\n", "\n"))
        # A corner of its own whose edge has no part-covered pixel is plain too.
        self.assertLess(shape.index("if (!partial) return null;"), shape.index("var covered = Whole(bounds.Size);"))


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = compile_window(work)
        cls.answer = run_probe(PROBE, work, 180, CAR_EXE=str(exe))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def follows_the_fade(self, seen):
        steps = seen["steps"]
        self.assertTrue(steps)
        full = seen["full"]
        self.assertTrue(any(0 < alpha < 255 for alpha, _veil in steps), "the dialog faded in: %r" % steps)
        for alpha, veil in steps:
            self.assertEqual(veil, round(full * alpha / 255.0), "the veil at the dialog's alpha of its fullest")
        self.assertEqual(steps[-1], [255, full], "at its fullest once the dialog is opaque")
        self.assertTrue(seen["gone"])

    def test_over_a_plain_owner_the_veil_is_one_ink_at_windows_constant_alpha(self):
        seen = self.answer["plain"]
        self.assertTrue(seen["veiled"])
        self.assertTrue(seen["plain"], "no pixel part-covered")
        self.assertFalse(seen["pictured"], "no picture of the owner's size made")
        self.assertEqual([seen["corner"], seen["middle"], seen["outside"]], [255, 255, -1])
        self.follows_the_fade(seen)
        # What Windows lays it at is the alpha it follows, step for step (D9 kept).
        for (alpha, veil), (ok, laid, flags) in zip(seen["steps"], seen["layered"]):
            self.assertEqual(ok, 1)
            self.assertEqual(flags & LWA_ALPHA, LWA_ALPHA)
            self.assertEqual(laid, veil)

    def test_over_an_owner_with_an_anti_aliased_corner_the_picture_stays(self):
        if not self.answer["owner_shaped"]:
            self.skipTest("this machine gives the window Windows' corner (no corner of its own to dim)")
        seen = self.answer["soft"]
        self.assertTrue(seen["veiled"])
        self.assertFalse(seen["plain"], "its edge is part-covered (D10)")
        self.assertTrue(seen["pictured"])
        self.assertLess(seen["corner"], 255)
        self.assertEqual(seen["middle"], 255)
        self.follows_the_fade(seen)


if __name__ == "__main__":
    unittest.main()
