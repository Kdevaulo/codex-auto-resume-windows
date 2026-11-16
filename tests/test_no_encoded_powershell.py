"""No code we ship hands PowerShell a script encoded on its command line.

Issue #65 (v0.6.22 advanced): Avast Free's Behavior Shield blocked powershell.exe again and again with the command-line
heuristic IDP.HELU.PSE96 - after a usage-limit stop, at a power action's countdown, around a resume, as the watcher
started and while installing - because every fixed script went to it as base64 after the encoded-command switch, and
the installers had WMI start a hidden PowerShell that way. From v0.6.24 pwsh.run passes the constant script plain after
-Command (tests/test_pwsh_command_line.py proves it arrives whole) and the installers' Invoke-Outside writes it to a
file it starts with -File (tests/test_outside_constant_script.py). This holds every tree that ships - src/,
advanced/src/, scripts/, build/install/ and the window's gui/ (not build/stage/, which is generated) - to it, three ways:

* the switch itself, in any spelling PowerShell accepts for it (any prefix from -en up to -EncodedCommand, and -ec);
* `-e` followed by a run of base64, the shortest spelling;
* the encoding step: base64 of UTF-16LE text, which is what that switch takes and nothing else of ours needs -
  Python's b64encode of something encoded "utf-16", PowerShell's or C#'s ToBase64String of Encoding.Unicode bytes.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
TREES = ("src", "advanced/src", "scripts", "build/install", "gui")
SUFFIXES = {".py", ".ps1", ".psm1", ".psd1", ".cmd", ".bat", ".cs", ".js", ".vbs"}

SWITCH = re.compile(r"(?i)(?<![\w-])-(?:en(?:c(?:o(?:d(?:e(?:d(?:c(?:o(?:m(?:m(?:a(?:n(?:d)?)?)?)?)?)?)?)?)?)?)?)?|ec)(?![\w-])")
SHORT = re.compile(r"(?<![\w-])-[eE]\s+[A-Za-z0-9+/]{16,}={0,2}")
ENCODING = re.compile(r"b64encode\([^\n]*utf-?16|ToBase64String\([^\n]*Encoding\]?::Unicode|"
                      r"ToBase64String\([^\n]*Encoding\.Unicode", re.IGNORECASE)
CHECKS = (("the encoded-command switch", SWITCH), ("-e and base64", SHORT), ("base64 of UTF-16LE text", ENCODING))


def shipped_files():
    for tree in TREES:
        base = ROOT / tree
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix.lower() in SUFFIXES and "__pycache__" not in path.parts:
                yield path


def findings(text: str) -> list:
    return [(what, match.group(0)) for what, pattern in CHECKS for match in pattern.finditer(text)]


class NoEncodedPowerShellTests(unittest.TestCase):
    def test_no_shipped_file_encodes_a_powershell_command(self):
        found = []
        files = 0
        for path in shipped_files():
            files += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), 1):
                for what, matched in findings(line):
                    found.append("%s:%d %s: %s" % (path.relative_to(ROOT).as_posix(), number, what, matched))
        self.assertGreater(files, 100, "the trees were read")
        self.assertEqual(found, [], "issue #65: pass the constant script plain after -Command (pwsh.run) or as a "
                                    "file with -File, never encoded on the command line")

    def test_the_checks_see_what_they_forbid(self):
        """Each spelling the old code used, or PowerShell would take, is seen; ordinary text is not."""
        seen = [
            '[shell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]',
            "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand ' + $encoded",
            "powershell -enc SQBuAHYAbwBrAGUA",
            "powershell -ec SQBuAHYAbwBrAGUA",
            "powershell -EncodedComm SQBuAHYAbwBrAGUA",
            "powershell -e SQBuAHYAbwBrAGUALQBFAHgA",
            'encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")',
            "$encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($Source))",
            "Convert.ToBase64String(Encoding.Unicode.GetBytes(script))",
        ]
        for text in seen:
            with self.subTest(text):
                self.assertTrue(findings(text))
        unseen = [
            '[shell, "-NoProfile", "-NonInteractive", "-Command", script]',
            "-ExecutionPolicy Bypass -File \"' + $sourceFile + '\"",
            "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false",
            "Get-Content -Raw -Encoding UTF8",
            'base64.b64encode(raw).decode("ascii")',
            "[Convert]::ToBase64String($utf8.GetBytes([string]$given[$key]))",
            "Convert.ToBase64String(sha.ComputeHash(File.ReadAllBytes(path)))",
            "git grep -e pattern",
            "some-encoded-name -end",
        ]
        for text in unseen:
            with self.subTest(text):
                self.assertEqual(findings(text), [])


if __name__ == "__main__":
    unittest.main()
