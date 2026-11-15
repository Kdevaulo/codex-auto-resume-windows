r"""v0.6.24: a text box's right-click menu is ours, with Windows' six edit commands in Windows' own words.

Every editable box of both editions is a SoftTextArea's Box or a SoftNumber's edit part, and both hand it to
EditMenu.Attach (gui/SoftEdit.cs): the box's WM_CONTEXTMENU opens a SoftMenu and never reaches Windows' menu. Its six
items - Undo | Cut, Copy, Paste, Delete | Select all - carry user32's own words for the six commands, read on the first
right-click and taken by command, never by position, with the English words when they cannot be read; each item is
usable when Windows' is.

Held through the source (SourceTests) and the compiled window (WindowTests), in a form that is never shown: no menu
window is opened, the clipboard is only asked whether it holds text, and the probe's own hook under ours swallows a
WM_CONTEXTMENU that got through, so Windows' menu cannot open either.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import guiscan

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
POWERSHELL = (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
              / "WindowsPowerShell" / "v1.0" / "powershell.exe")
ADVANCED_GUI = guiscan.ROOT / "advanced" / "gui"

ENGLISH = ["&Undo", "Cu&t", "&Copy", "&Paste", "&Delete", "Select &All"]


def code_only(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


def every_source() -> dict[str, str]:
    """Every hand-written window source of both editions."""
    found = {name: guiscan.read(name) for name in guiscan.handwritten()}
    for path in sorted(ADVANCED_GUI.glob("*.cs")):
        found["advanced/gui/" + path.name] = path.read_text(encoding="utf-8")
    return found


class SourceTests(unittest.TestCase):
    def test_the_menu_is_compiled_with_the_controls(self):
        self.assertIn("gui/SoftEdit.cs", guiscan.group("controls"))
        self.assertLess(guiscan.group("controls").index("gui/SoftMenu.cs"),
                        guiscan.group("controls").index("gui/SoftEdit.cs"))

    def test_every_editable_box_is_made_in_one_of_the_two_places(self):
        """A text box, a number box, a rich or masked box: made only as SoftTextArea's Box and SoftNumber's Spin, and
        nothing derives from them; every drop-down is a list, with no edit part."""
        made = []
        for name, text in every_source().items():
            code = code_only(text)
            for kind in re.findall(r"new\s+(TextBox|RichTextBox|MaskedTextBox|NumericUpDown|DomainUpDown|ComboBox)\s*\(",
                                   code):
                made.append((name, kind))
            with self.subTest(name):
                self.assertIsNone(re.search(r"class\s+\w+\s*:\s*(TextBoxBase|TextBox|RichTextBox|MaskedTextBox|"
                                            r"UpDownBase|NumericUpDown|DomainUpDown)\b", code))
                for style in re.findall(r"DropDownStyle\s*=\s*([\w.]+)", code):
                    self.assertEqual(style, "ComboBoxStyle.DropDownList")
        self.assertEqual(sorted(made), [("gui/SoftFields.cs", "NumericUpDown"), ("gui/SoftFields.cs", "TextBox")])
        self.assertIn("internal readonly TextBox Box = new TextBox();", guiscan.type_body("SoftTextArea"))
        self.assertIn("internal readonly NumericUpDown Spin = new NumericUpDown();", guiscan.type_body("SoftNumber"))

    def test_both_places_attach_our_menu(self):
        self.assertIn("EditMenu.Attach(Box);", guiscan.member_body("SoftTextArea", "SoftTextArea"))
        hook = guiscan.member_body("SoftNumber", "Hook")
        self.assertRegex(hook, r"if \(child is TextBox\) \{ EditMenu\.Attach\(\(TextBox\)child\); continue; \}")

    def test_the_hook_keeps_the_message_from_windows_menu(self):
        """WM_CONTEXTMENU opens ours and returns before the base; only if ours throws does Windows' own open."""
        body = code_only(guiscan.type_body("Hook", "gui/SoftEdit.cs"))
        self.assertIn(": NativeWindow", body)
        proc = re.search(r"protected override void WndProc\(ref Message m\)\s*\{(.*)\}\s*\}\s*$", body, re.S).group(1)
        taken = re.search(r"if \(m\.Msg == WM_CONTEXTMENU\)\s*\{\s*try\s*\{(.*?)\}\s*catch", proc, re.S)
        self.assertIsNotNone(taken)
        self.assertRegex(taken.group(1), r"Opening\(box, At\(box, m\.LParam\)\);\s*m\.Result = IntPtr\.Zero;\s*return;")
        self.assertNotIn("base.WndProc", taken.group(1))
        self.assertIn("AssignHandle(box.Handle)", body)
        self.assertIn("box.HandleDestroyed += delegate { ReleaseHandle(); };", body)

    def test_six_commands_in_windows_order_with_two_lines(self):
        menu = guiscan.type_body("EditMenu")
        self.assertIn("Commands = { EM_UNDO, WM_CUT, WM_COPY, WM_PASTE, WM_CLEAR, EM_SETSEL };", menu)
        self.assertIn("RuleBefore = { 1, 5 };", menu)
        self.assertIn('Fallback = { "&Undo", "Cu&t", "&Copy", "&Paste", "&Delete", "Select &All" };', menu)
        for name, value in (("EM_UNDO", "0x00C7"), ("WM_UNDO", "0x0304"), ("WM_CUT", "0x0300"), ("WM_COPY", "0x0301"),
                            ("WM_PASTE", "0x0302"), ("WM_CLEAR", "0x0303"), ("EM_SETSEL", "0x00B1"),
                            ("WM_CONTEXTMENU", "0x007B")):
            self.assertRegex(menu, r"\b%s = %s\b" % (name, value))
        self.assertIn("new SoftMenu()", guiscan.member_body("EditMenu", "Open"))

    def test_the_words_are_taken_by_command_and_read_only_when_asked(self):
        """Nothing is read at start: no static constructor, the cache starts empty, and only the menu's own build asks
        for the words. The resource is found by its six commands, never by its number, and each word by its command."""
        menu = code_only(guiscan.type_body("EditMenu"))
        self.assertIsNone(re.search(r"static\s+EditMenu\s*\(", menu))
        self.assertRegex(menu, r"private static string\[\] words;")
        callers = [m.start() for m in re.finditer(r"\bWords\(\)", menu)]
        self.assertEqual(len(callers), 3, "declared once, asked by Build and by FromWindows")
        self.assertIn("string[] said = Words();", guiscan.member_body("EditMenu", "Build"))
        read = guiscan.member_body("EditMenu", "Read")
        self.assertIn("EnumResourceNamesExW(user32, (IntPtr)RT_MENU", read)
        self.assertIsNone(re.search(r"LoadMenuW\([^,]+,\s*\(IntPtr\)\d", menu), "no resource number is trusted")
        match = guiscan.member_body("EditMenu", "Match")
        self.assertIn("int slot = Slot((int)id);", match)
        self.assertIn("mine[slot] = text.ToString()", match)
        self.assertIn("if (string.IsNullOrEmpty(word)) return null;", match)
        attach = guiscan.member_body("EditMenu", "Attach") + guiscan.type_body("Hook", "gui/SoftEdit.cs")
        for asked in ("Words(", "Read(", "LoadMenuW", "EnumResource"):
            self.assertNotIn(asked, attach)

    def test_asking_the_clipboard_never_reads_it(self):
        menu = code_only(guiscan.type_body("EditMenu"))
        self.assertIn("IsClipboardFormatAvailable(CF_UNICODETEXT)", menu)
        for reading in ("GetClipboardData", "OpenClipboard", "Clipboard."):
            self.assertNotIn(reading, menu)


PROBE = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding $false
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
Add-Type -ReferencedAssemblies System.Windows.Forms, System.Drawing -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;
public sealed class EditProbeCatcher : NativeWindow
{
    public int Reached;
    public EditProbeCatcher(IntPtr handle) { AssignHandle(handle); }
    protected override void WndProc(ref Message m)
    {
        if (m.Msg == 0x007B) { Reached++; m.Result = IntPtr.Zero; return; }
        base.WndProc(ref m);
    }
    [DllImport("user32.dll")]
    public static extern IntPtr SendMessage(IntPtr window, int message, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr SendMessage(IntPtr window, int message, IntPtr wParam, string lParam);
}
'@
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$flags = [Reflection.BindingFlags]'Instance,Static,NonPublic,Public'
$script:E = $assembly.GetType('CodexAutoResume.EditMenu', $true)
$A = $assembly.GetType('CodexAutoResume.SoftTextArea', $true)
$N = $assembly.GetType('CodexAutoResume.SoftNumber', $true)
function Call($name, $arguments) {
  $plain = New-Object 'object[]' (@($arguments).Count)
  for ($i = 0; $i -lt $plain.Length; $i++) {
    $value = @($arguments)[$i]
    if ($value -is [Management.Automation.PSObject]) { $value = $value.PSObject.BaseObject }
    $plain[$i] = $value
  }
  return $script:E.GetMethod($name, $flags).Invoke($null, $plain)
}
$out = @{}
$out.readBefore = ($script:E.GetField('words', $flags).GetValue($null) -eq $null)

# The rule, row by row: canUndo, readOnly, password, start, length, textLength, clipboardText.
$rows = @(
  @($false, $false, $false, 0, 0, 0, $false),
  @($true, $false, $false, 2, 3, 10, $true),
  @($true, $true, $false, 2, 3, 10, $true),
  @($true, $false, $true, 2, 3, 10, $true),
  @($false, $false, $false, 0, 10, 10, $false),
  @($false, $false, $false, 4, 0, 10, $true),
  @($true, $true, $true, 0, 0, 10, $true))
$out.states = @($rows | ForEach-Object { ,@(Call 'States' $_) })

$script:box = $null
$frame = New-Object Windows.Forms.Form
$frame.ClientSize = New-Object Drawing.Size 400, 300
$area = $A.GetConstructor($flags, $null, [type[]]@(), $null).Invoke(@())
$area.SetBounds(10, 10, 300, 100)
$frame.Controls.Add($area)
$number = $N.GetConstructor($flags, $null, [type[]]@(), $null).Invoke(@())
$number.SetBounds(10, 150, 120, 36)
$frame.Controls.Add($number)
$box = $A.GetField('Box', $flags).GetValue($area)
$null = $frame.Handle; $null = $box.Handle
$spin = $N.GetField('Spin', $flags).GetValue($number)
$null = $spin.Handle
foreach ($child in $spin.Controls) { $null = $child.Handle }
$out.attachedArea = [bool](Call 'Attached' @($box))
$out.attachedNumber = @($spin.Controls | Where-Object { $_ -is [Windows.Forms.TextBox] } | ForEach-Object { [bool](Call 'Attached' @($_)) })
$out.readAtAttach = ($script:E.GetField('words', $flags).GetValue($null) -eq $null)

function Items($b) {
  return @(Call 'Build' @($b) | ForEach-Object {
    if ($_ -is [Windows.Forms.ToolStripSeparator]) { @{ rule = $true } }
    else { @{ text = $_.Text; enabled = $_.Enabled; command = [int]$_.Tag } } })
}
$box.Text = 'hello world'
$box.Select(0, 5)
$out.selected = Items $box
$out.clipboardText = [bool]((Call 'StatesOf' @($box))[3])
$box.SelectAll()
$out.allSelected = Items $box
$null = [EditProbeCatcher]::SendMessage($box.Handle, 0x00B1, [IntPtr]11, [IntPtr]11)
$null = [EditProbeCatcher]::SendMessage($box.Handle, 0x00C2, [IntPtr]1, '!')
$out.typed = Items $box
$box.ReadOnly = $true
$box.Select(0, 5)
$out.readOnly = Items $box
$box.ReadOnly = $false
$before = $box.Handle
$box.UseSystemPasswordChar = $true
$null = $box.Handle
$out.recreated = ($box.Handle -ne $before)
$out.attachedAfterRecreate = [bool](Call 'Attached' @($box))
$box.Text = 'secret'
$box.Select(0, 3)
$out.password = Items $box
$box.UseSystemPasswordChar = $false
$null = $box.Handle

# What each item does: the box's own messages.
$script:changed = 0
$box.add_TextChanged({ try { $script:changed++ } catch { [Environment]::Exit(3) } })
$box.Text = 'one two'
$script:changed = 0
$box.Select(0, 0)
Call 'Run' @($box, 0x00B1)
$out.runSelectAll = @($box.SelectionStart, $box.SelectionLength)
$box.Select(0, 4)
Call 'Run' @($box, 0x0303)
$out.runDelete = $box.Text
$out.runDeleteChanged = $script:changed
Call 'Run' @($box, 0x00C7)
$out.runUndo = $box.Text

# The message itself: our hook above the probe's catcher; Opening records where instead of opening.
$plain = New-Object Windows.Forms.TextBox
$plain.SetBounds(150, 150, 200, 30)
$plain.Text = 'abc def'
$frame.Controls.Add($plain)
$null = $plain.Handle
$catcher = New-Object EditProbeCatcher $plain.Handle
Call 'Attach' @($plain)
$script:opened = New-Object 'System.Collections.Generic.List[object]'
$field = $script:E.GetField('Opening', $flags)
$keep = $field.GetValue($null)
$field.SetValue($null, [Action[Windows.Forms.TextBoxBase, Drawing.Point]]{
  param($b, $p)
  try { $script:opened.Add(@($p.X, $p.Y)) } catch { [Environment]::Exit(4) }
})
try {
  $null = [EditProbeCatcher]::SendMessage($plain.Handle, 0x007B, $plain.Handle, [IntPtr](200 + (300 -shl 16)))
  $plain.Select(4, 0)
  $null = [EditProbeCatcher]::SendMessage($plain.Handle, 0x007B, $plain.Handle, [IntPtr]-1)
} finally {
  $field.SetValue($null, $keep)
}
$out.opened = @($script:opened | ForEach-Object { ,@($_) })
$out.passedOn = $catcher.Reached
$r = $plain.RectangleToScreen($plain.ClientRectangle)
$out.plainScreen = @($r.Left, $r.Top, $r.Right, $r.Bottom)
$out.everShown = $frame.Visible

$out.words = @(Call 'Words' @())
$out.fromWindows = [bool]$script:E.GetProperty('FromWindows', $flags).GetValue($null, $null)
$out.ui = [Globalization.CultureInfo]::CurrentUICulture.Name
$catcher.ReleaseHandle()
$frame.Dispose()
$out | ConvertTo-Json -Depth 6 -Compress
"""


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = work / "CodexAutoResumeSettings.exe"
        subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                        "/reference:System.dll", "/reference:System.Drawing.dll",
                        "/reference:System.Windows.Forms.dll", *[str(path) for path in guiscan.sources()]],
                       check=True, capture_output=True, timeout=300,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        probe = work / "probe.ps1"
        probe.write_text(PROBE, encoding="utf-8-sig")
        result = subprocess.run(
            [str(POWERSHELL), "-STA", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=dict(os.environ, CAR_EXE=str(exe)))
        cls.result = result
        cls.answer = json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else {}

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if not self.answer:
            self.fail("the probe did not run: " + (self.result.stderr or self.result.stdout)[-2000:])

    def items(self, name):
        return self.answer[name]

    def enabled(self, name):
        return [item.get("enabled") for item in self.items(name) if not item.get("rule")]

    def test_the_rule_row_by_row(self):
        self.assertEqual(self.answer["states"], [
            [False, False, False, False, False, False],   # an empty box, nothing on the clipboard
            [True, True, True, True, True, True],         # some selected, text on the clipboard
            [False, False, True, False, False, True],     # read-only: Copy and Select all only
            [True, False, False, True, True, True],       # a password box: no Cut, no Copy
            [False, True, True, False, True, False],      # all of it selected: no Select all
            [False, False, False, True, False, True],     # only a caret
            [False, False, False, False, False, True],    # read-only password box with a caret
        ])

    def test_both_boxes_are_attached_and_nothing_is_read_at_start(self):
        self.assertTrue(self.answer["readBefore"])
        self.assertTrue(self.answer["attachedArea"])
        self.assertEqual(self.answer["attachedNumber"], [True])
        self.assertTrue(self.answer["readAtAttach"], "attaching reads no words")

    def test_the_menu_is_six_items_and_two_lines_in_windows_order(self):
        items = self.items("selected")
        self.assertEqual([bool(item.get("rule")) for item in items], [False, True, False, False, False, False, True, False])
        self.assertEqual([item["command"] for item in items if not item.get("rule")],
                         [0x00C7, 0x0300, 0x0301, 0x0302, 0x0303, 0x00B1])
        self.assertEqual([item["text"] for item in items if not item.get("rule")], self.answer["words"])

    def test_each_item_is_usable_as_windows_decides(self):
        paste = self.answer["clipboardText"]
        self.assertEqual(self.enabled("selected"), [False, True, True, paste, True, True])
        self.assertEqual(self.enabled("allSelected"), [False, True, True, paste, True, False])
        self.assertEqual(self.enabled("typed")[0], True, "typed text can be undone")
        self.assertEqual(self.enabled("readOnly"), [False, False, True, False, False, True])
        self.assertTrue(self.answer["recreated"])
        self.assertTrue(self.answer["attachedAfterRecreate"], "a box made anew keeps our menu")
        self.assertEqual(self.enabled("password"), [False, False, False, paste, True, True])

    def test_each_item_sends_the_boxs_own_message(self):
        self.assertEqual(self.answer["runSelectAll"], [0, 7])
        self.assertEqual(self.answer["runDelete"], "two")
        self.assertGreaterEqual(self.answer["runDeleteChanged"], 1, "the box says its text changed, as typing does")
        self.assertEqual(self.answer["runUndo"], "one two")

    def test_the_message_opens_ours_and_never_windows(self):
        self.assertFalse(self.answer["everShown"])
        self.assertEqual(self.answer["passedOn"], 0, "WM_CONTEXTMENU never got past our hook")
        opened = self.answer["opened"]
        self.assertEqual(len(opened), 2)
        self.assertEqual(opened[0], [200, 300], "a right-click opens where the pointer is")
        left, top, right, bottom = self.answer["plainScreen"]
        x, y = opened[1]
        self.assertTrue(left <= x < right and top <= y < bottom, "Shift+F10 opens at the caret, inside the box")

    def test_six_words_each_with_its_mnemonic(self):
        words = self.answer["words"]
        self.assertEqual(len(words), 6)
        for word in words:
            with self.subTest(word):
                self.assertTrue(word.strip())
                self.assertEqual(word.replace("&&", "").count("&"), 1)
        if self.answer["ui"] == "en-US":
            self.assertEqual(words, ENGLISH)
        if not self.answer["fromWindows"]:
            self.assertEqual(words, ENGLISH, "the stand-in words are the English ones")


if __name__ == "__main__":
    unittest.main()
