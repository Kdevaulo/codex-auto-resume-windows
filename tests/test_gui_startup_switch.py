r"""v0.6.16-beta.3, issue #31: Settings' "Run at Windows sign-in" shows what Windows holds.

The switch was set from the page's own status read alone (RefreshStatusAsync), built off and left off
until that read came back - so it showed off while the read was on its way, and for good after one that
failed, though the Run value was there and the status said startup_enabled true. Save then wrote what it
showed, whatever was saved: a switch never read removed the entry the person had kept, and one read before
the entry was removed elsewhere put it back.

Now any status read that says it sets the switch - the Dashboard's snapshot too - though a snapshot only
while the switch still shows what was read last, so a person's unsaved change is not taken back by the next
refresh; and Save writes the sign-in entry only where the person moved the switch from what a read said.

The source half reads the window with guiscan; the built half compiles the real window, never shown and
asking no bridge (it is audited), and drives the switch through status answers.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import guiscan
from codex_auto_resume import settings
from test_gui_v0611_access import CSC, POWERSHELL, compile_window, reply, run_probe


def body(member: str) -> str:
    return guiscan.member_body("SettingsForm", member)


class SourceTests(unittest.TestCase):
    def test_save_writes_the_entry_only_where_the_person_moved_the_switch_from_what_was_read(self):
        save = body("Save")
        self.assertIn("bool writeStartup = startup != null && startupKnown && startAtSignIn != startupBaseline;", save)
        self.assertIn("if (writeStartup)", save)
        self.assertIn("else registeredThen(null);", save)

    def test_a_build_forgets_what_was_read(self):
        self.assertIn("startupKnown = false;", body("BuildEditors"))

    def test_the_snapshot_s_status_reaches_the_switch(self):
        """The Dashboard's snapshot hands ApplyStatus no switch; ApplyStatus finds it itself."""
        apply = body("ApplyStatus")
        self.assertIn('editors.ContainsKey("__startup")', apply)
        self.assertIn("startup.Checked == startupBaseline", apply)


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box C# compiler and Windows PowerShell")
class BuiltSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = compile_window(work)
        (work / "schema.json").write_text(json.dumps(settings.describe(), ensure_ascii=False), encoding="utf-8")
        (work / "settings.json").write_text(json.dumps(settings.defaults(), ensure_ascii=False), encoding="utf-8")
        (work / "strings-en.json").write_text(json.dumps(reply("en"), ensure_ascii=False), encoding="utf-8")
        cls.answer = run_probe(PROBE, work, 600, CAR_EXE=str(exe))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_before_any_read_nothing_is_known(self):
        self.assertEqual(self.answer["unread"], {"on": False, "known": False})

    def test_a_snapshot_that_says_it_is_registered_turns_it_on(self):
        self.assertEqual(self.answer["snapshot"], {"on": True, "known": True})

    def test_a_snapshot_never_takes_back_a_change_not_yet_saved(self):
        self.assertEqual(self.answer["edited"], {"on": False, "known": True})

    def test_the_page_s_own_read_says_what_windows_holds(self):
        self.assertEqual(self.answer["own"], {"on": True, "known": True})

    def test_a_status_without_the_answer_changes_nothing(self):
        self.assertEqual(self.answer["silent"], {"on": False, "known": False})


PROBE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$flags = [Reflection.BindingFlags]'Instance,Static,NonPublic,Public'
$F = $assembly.GetType('CodexAutoResume.SettingsForm', $true)
$PB = $assembly.GetType('CodexAutoResume.PersistentBridge', $true)
$BT = $assembly.GetType('CodexAutoResume.Bridge', $true)
$J = $assembly.GetType('CodexAutoResume.Json', $true)
$utf8 = New-Object Text.UTF8Encoding $false
function Read($name) { return [IO.File]::ReadAllText((Join-Path $env:CAR_WORK $name), $utf8) }
function Parse([string]$text) { return ,$J.GetMethod('Parse', $flags).Invoke($null, [object[]]@($text)) }
function Call($name, $arguments) {
  $given = New-Object 'object[]' $arguments.Count
  for ($i = 0; $i -lt $arguments.Count; $i++) {
    $value = $arguments[$i]
    if ($null -ne $value -and $value -is [psobject]) { $value = $value.PSObject.BaseObject }
    $given[$i] = $value
  }
  return $F.GetMethod($name, $flags).Invoke($form, $given)
}
function Field($name) { return $F.GetField($name, $flags).GetValue($form) }
[string]$nowhere = Join-Path $env:CAR_WORK 'nowhere'
$make = $F.GetConstructor($flags, $null, [type[]]@($PB, [Collections.Generic.Dictionary[string,object]], [Drawing.Font]), $null)
function NewWindow() {
  $bridge = $BT.GetConstructor($flags, $null, [type[]]@([string]), $null).Invoke([object[]]@($nowhere))
  $persistent = $PB.GetConstructor($flags, $null, [type[]]@([string], $BT), $null).Invoke([object[]]@($nowhere, $bridge))
  $window = $make.Invoke([object[]]@($persistent.PSObject.BaseObject, (Parse (Read 'strings-en.json')), [Drawing.SystemFonts]::MessageBoxFont))
  $F.GetField('auditing', $flags).SetValue($window, $true)
  return $window
}
function Switch() { return (Field 'editors')['__startup'] }
function Now() { return @{ on = [bool](Switch).Checked; known = [bool](Field 'startupKnown') } }
$registered = '{"watcher_running": false, "startup_enabled": true}'
$out = @{}

$form = NewWindow
$form.TopLevel = $false
$form.ClientSize = New-Object Drawing.Size 1000, 664
Call 'BuildEditors' @((Parse (Read 'schema.json')), (Parse (Read 'settings.json'))) | Out-Null
$out.unread = Now
# A status that does not say it (an older bridge's) leaves the switch as it was.
Call 'ApplyStatus' @((Parse '{"watcher_running": false}'), $null) | Out-Null
$out.silent = Now
# The Dashboard's snapshot: ApplyStatus is handed no switch.
Call 'ApplyStatus' @((Parse $registered), $null) | Out-Null
$out.snapshot = Now
# The person turns it off and has not saved: the next snapshot leaves that alone ...
(Switch).Checked = $false
Call 'ApplyStatus' @((Parse $registered), $null) | Out-Null
$out.edited = Now
# ... and the page's own read, after a save or a start, says what Windows holds, as it always did.
Call 'ApplyStatus' @((Parse $registered), (Switch)) | Out-Null
$out.own = Now
$form.Dispose()
[IO.File]::WriteAllText((Join-Path $env:CAR_WORK 'result.json'), ($out | ConvertTo-Json -Depth 6 -Compress), $utf8)
"""


if __name__ == "__main__":
    unittest.main()
