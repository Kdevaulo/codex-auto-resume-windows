"""Every constant script reaches Windows PowerShell whole, as the one plain argument after -Command.

Issue #65: Avast's Behavior Shield blocked powershell.exe (IDP.HELU.PSE96) on the shape the product used to start it
with - the script as base64 after the encoded-command switch. From v0.6.24 pwsh.run hands the constant over as it is,
quoted by subprocess's list2cmdline (pwsh.command_line). That is only safe if the real interpreter receives exactly the
text written, so these tests ask it: each script starts with a line that compares the text PowerShell itself parsed
($MyInvocation.MyCommand.Definition) with the whole script, passed beside it as a value, parses it once more with
PowerShell's own parser, and exits 41 only when both hold - 42, writing down what it received, otherwise. Nothing after
that first line ever runs: no toast is raised, no shortcut written, no process created.

The awkward script carries every character a constant has or could have: double quotes (shortcut._MAKER has ten),
backslashes, backslashes right before a double quote and at the very end of the argument, every single quote PowerShell
knows, `$`, backtick, `%`, `^`, `&`, `|`, `<`, `>`, `;`, newlines, here-strings of both kinds, non-ASCII. A control run
asks for one character more and must get 42, so the check cannot pass by accident.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from codex_auto_resume import notify, pwsh, shortcut  # noqa: E402

ADVANCED = ROOT / "advanced" / "src" / "codex_auto_resume_advanced"

# The first line of every probe: what PowerShell received, compared with what was sent, and parsed again.
CHECK = ("$received = $MyInvocation.MyCommand.Definition; $tokens = $null; $errors = $null; "
         "$null = [System.Management.Automation.Language.Parser]::ParseInput($received, [ref]$tokens, [ref]$errors); "
         "if ($errors.Count -eq 0 -and $received -ceq $env:CODEX_AUTO_RESUME_ARG_EXPECT) { exit 41 }; "
         "[System.IO.File]::WriteAllText($env:CODEX_AUTO_RESUME_ARG_OUT, $received, "
         "(New-Object System.Text.UTF8Encoding $false)); exit 42\n")

AWKWARD = (
    '<# a block comment: "double" \\back\\slash\\ \\"quoted\\" \\\\"two\\\\" \' \u2018 \u2019 \u201a \u201b $notvar '
    '`backtick % ^ & | < > ; ( ) { } [ ] @ ! ~ * ? \u00e9 \ud55c\uad6d\uc5b4 \U0001f9e9 "" \'\' trailing\\\\ #>\n'
    "$text = @'\n"
    'a line with "double quotes" and \\" and \\\\" and \\\\\\" and a trailing backslash\\\n'
    "'single' \u2018one\u2019 \u201atwo\u201b $(Write-Output never) `n %PATH% ^caret &amp | pipe <in >out ;semi\n"
    "@\" not the end \"@ and @' inside '@ mid-line\n"
    "'@\n"
    '$expand = @"\n'
    '"inner" `$escaped ${braced} \\"q\\" \\\\\n'
    '"@\n'
    '$path = "C:\\Program Files\\x\\" + \'\\"\' + "`"" + "\\\\server\\share\\"\n'
    "$tab = \"a\tb\"\n"
    "# backslashes at the very end of the argument, where the closing quote follows them: \\\\\\")


def advanced_constant(relative: str, name: str) -> str:
    """A module-level string constant of the advanced package, read from its source: the standard lane keeps that
    package off the path, and the constant is the same text either way."""
    tree = ast.parse((ADVANCED / relative).read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name
                                                 for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("%s has no constant %s" % (relative, name))


@unittest.skipUnless(pwsh.executable(), "Windows PowerShell is not available")
class ReceivedWholeTests(unittest.TestCase):
    def received(self, script: str, expect: str | None = None):
        """pwsh.run's exit code for `script`, and the text PowerShell received when it was not what was sent."""
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "received.txt"
            code = pwsh.run(script, {"EXPECT": script if expect is None else expect, "OUT": out}, timeout=120)
            return code, out.read_text(encoding="utf-8") if out.is_file() else None

    def test_the_awkward_script_arrives_whole(self):
        script = CHECK + AWKWARD
        for character in ('"', "\\", '\\"', "'", "\u2018", "\u2019", "\u201a", "\u201b", "$", "`", "%", "^", "&",
                          "|", "<", ">", ";", "\n", "@'", "'@", '@"', '"@'):
            self.assertIn(character, AWKWARD)
        self.assertTrue(AWKWARD.endswith("\\\\\\"), "the argument ends in backslashes")
        self.assertEqual(self.received(script), (41, None))

    def test_the_check_fails_when_the_text_differs(self):
        """The control: the same script, asked to be one character longer than it is, is told apart - so 41 is
        earned, and what PowerShell received is the script exactly."""
        script = CHECK + AWKWARD
        code, got = self.received(script, expect=script + "x")
        self.assertEqual(code, 42)
        self.assertEqual(got, script)

    def test_every_constant_script_arrives_whole_and_parses(self):
        # The toast script with the one word tests/no_real_toast.py refuses a command for, its last letter in upper
        # case: the same method to PowerShell, which ignores case in member names, and every character the quoting
        # carries unchanged - while the guard, which looks for the word exactly, still stands. Nothing after the first
        # line runs anyway.
        import no_real_toast
        toast = notify._SCRIPT.replace(no_real_toast.TOAST_MARK, no_real_toast.TOAST_MARK[:-1] + "R")
        self.assertNotEqual(toast, notify._SCRIPT)
        self.assertEqual(toast.lower(), notify._SCRIPT.lower())
        constants = {
            "notify._SCRIPT": toast,
            "shortcut._MAKER": shortcut._MAKER,
            "shortcut._READER": shortcut._READER,
            "codexstart._WMI_CREATE": advanced_constant("control/codexstart.py", "_WMI_CREATE"),
            "wmi_escape._WMI_SCRIPT": advanced_constant("codex/wmi_escape.py", "_WMI_SCRIPT"),
        }
        self.assertEqual(shortcut._MAKER.count('"'), 10, "the maker's double quotes are what this proves")
        for name, constant in constants.items():
            with self.subTest(name):
                self.assertEqual(self.received(CHECK + constant), (41, None))


class ArgvShapeTests(unittest.TestCase):
    def test_the_script_is_one_plain_argument_after_command(self):
        argv = pwsh.command_line("powershell.exe", AWKWARD)
        self.assertEqual(argv, ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", AWKWARD])
        self.assertFalse(any(part.lower().startswith("-e") for part in argv), "no encoded-command switch")


if __name__ == "__main__":
    unittest.main()
