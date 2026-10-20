"""v0.6.17: a WrapLabel remembers Label's measurement of text without Korean for the whole window (gui/SoftList.cs).

Label keeps what it measured only for itself, and the Advanced page builds its cards anew each time a capability is
opened or a read comes back: one layout audit asked Label about 235,000 times for some 3,000 different answers, and in
Chinese and Japanese each answer is a wrapped GDI measurement 10 to 45 ms long - about 2 s a click on an English
Windows. WrapLabel now answers a question it has been asked before, by any label, from what Label said then
(WrapLabel.Remembered). What is drawn must not change, so:

* RememberedAnswerTests - the remembered answer is the one a fresh Label gives, for catalog texts in English, Japanese,
  Chinese and Korean (the Korean catalog's texts without Hangul: text with Korean takes WrapLabel's own path, which this
  does not touch), at widths from none to unbounded, and for every property Label's measurement reads changed one at a
  time - each after the plain label has been measured at the same width, so a key that left that property out would
  hand back the plain label's answer and be caught. A label asked twice answers alike.
* AskedOnceTests - the same question from a second label does not reach Label again (WrapLabel.LabelMeasures), a
  different one does, and the remembered answers stay within WrapLabel.RememberedMost.

The window is compiled from gui/window.sources and its WrapLabel made through reflection in a PowerShell; no window is
created or shown, and nothing is read from or written to this machine's installation.

GUI test module: compiles the window with the in-box C# compiler (csc.exe), so it runs on its own.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codex_auto_resume import l10n  # noqa: E402

import guiscan  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
POWERSHELL = (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
              / "WindowsPowerShell" / "v1.0" / "powershell.exe")
LANGUAGES = ("en", "ja", "zh-CN", "ko")
HANGUL = re.compile("[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f\ua960-\ua97f\ud7b0-\ud7ff]")
# The widths asked: none (0 and 1, as a table asks), a narrow and a wide line, and unbounded.
WIDTHS = (0, 1, 180, 420, 100000)
# Each property Label.GetPreferredSize reads, changed from the plain label (the first, "plain").
VARIANTS = ("plain", "padding", "maximum", "minimum", "border", "centred", "ellipsis", "mnemonic", "reading", "font",
            "system", "fixed")


def texts(locale: str, count: int = 14) -> list:
    """The catalog's longest texts without Korean - those wrap - and a few of its shortest, which do not."""
    found = sorted({value for value in l10n.catalog(locale).values()
                    if isinstance(value, str) and value.strip() and not HANGUL.search(value)}, key=lambda t: (len(t), t))
    if len(found) <= count:
        return found
    return found[:4] + found[-(count - 4):]


PROBE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[Windows.Forms.Application]::SetCompatibleTextRenderingDefault($false)
$utf8 = New-Object Text.UTF8Encoding $false
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$static = [Reflection.BindingFlags]'Static,NonPublic,Public'
$wrapType = $assembly.GetType('CodexAutoResume.WrapLabel', $true)
$measures = $wrapType.GetField('LabelMeasures', $static)
$count = $wrapType.GetProperty('RememberedCount', $static)
$most = $wrapType.GetField('RememberedMost', $static)
if (-not $measures -or -not $count -or -not $most) { throw 'WrapLabel remembers nothing: no LabelMeasures, RememberedCount or RememberedMost' }
$given = ConvertFrom-Json ([IO.File]::ReadAllText($env:CAR_INPUT, $utf8))
$base = [Drawing.SystemFonts]::MessageBoxFont
$larger = New-Object Drawing.Font $base.FontFamily, ([float]($base.SizeInPoints * 1.5)), $base.Style, ([Drawing.GraphicsUnit]::Point)
function Dress($label, [string]$variant, [string]$text) {
    $label.AutoSize = $true
    $label.Font = $base
    switch ($variant) {
        'padding'  { $label.Padding = New-Object Windows.Forms.Padding 6, 2, 9, 8 }
        'maximum'  { $label.MaximumSize = New-Object Drawing.Size 260, 0 }
        'minimum'  { $label.MinimumSize = New-Object Drawing.Size 300, 60 }
        'border'   { $label.BorderStyle = [Windows.Forms.BorderStyle]::Fixed3D }
        'centred'  { $label.TextAlign = [Drawing.ContentAlignment]::MiddleCenter }
        'ellipsis' { $label.AutoEllipsis = $true }
        'mnemonic' { $label.UseMnemonic = $false }
        'reading'  { $label.RightToLeft = [Windows.Forms.RightToLeft]::Yes }
        'font'     { $label.Font = $larger }
        'system'   { $label.FlatStyle = [Windows.Forms.FlatStyle]::System }
        'fixed'    { $label.AutoSize = $false; $label.Size = New-Object Drawing.Size 140, 30 }
    }
    $label.Text = $text
}
$out = @{ cases = 0; repeats = 0; wrong = @(); asked = @{}; bounded = @{} }
foreach ($language in $given.languages) {
    foreach ($text in $language.texts) {
        foreach ($width in $given.widths) {
            $asked = New-Object Drawing.Size ([int]$width), 0
            foreach ($variant in $given.variants) {
                $wrap = [Activator]::CreateInstance($wrapType, $true)
                Dress $wrap $variant $text
                $first = $wrap.GetPreferredSize($asked)
                $again = $wrap.GetPreferredSize($asked)
                $plain = New-Object Windows.Forms.Label
                Dress $plain $variant $text
                $fresh = $plain.GetPreferredSize($asked)
                $out.cases++
                if ($first -ne $again) { $out.repeats++ }
                if ($first -ne $fresh -and $out.wrong.Count -lt 20) {
                    $out.wrong += ,@{ language = [string]$language.locale; variant = $variant; width = [int]$width
                                     text = [string]$text; remembered = [string]$first; label = [string]$fresh }
                }
                $wrap.Dispose(); $plain.Dispose()
            }
        }
    }
}
# The same question from a second label; then a different one.
$unique = 'Asked once ' + [Guid]::NewGuid().ToString('N') + ' and then remembered for the rest of this window.'
$width = New-Object Drawing.Size 200, 0
$start = [long]$measures.GetValue($null)
$one = [Activator]::CreateInstance($wrapType, $true); Dress $one 'plain' $unique; $null = $one.GetPreferredSize($width)
$afterOne = [long]$measures.GetValue($null)
$two = [Activator]::CreateInstance($wrapType, $true); Dress $two 'plain' $unique; $null = $two.GetPreferredSize($width)
$null = $two.GetPreferredSize($width)
$afterTwo = [long]$measures.GetValue($null)
$two.Padding = New-Object Windows.Forms.Padding 3
$null = $two.GetPreferredSize($width)
$afterPadding = [long]$measures.GetValue($null)
$null = $two.GetPreferredSize((New-Object Drawing.Size 333, 0))
$afterWidth = [long]$measures.GetValue($null)
$out.asked = @{ first = $afterOne - $start; second = $afterTwo - $afterOne; padding = $afterPadding - $afterTwo; width = $afterWidth - $afterPadding }
# More different questions than are ever remembered.
$many = [Activator]::CreateInstance($wrapType, $true); Dress $many 'plain' 'x'
$limit = [int]$most.GetValue($null)
$highest = 0
for ($i = 0; $i -lt $limit + 500; $i++) {
    $many.Text = 'n' + $i
    $null = $many.GetPreferredSize($width)
    $highest = [Math]::Max($highest, [int]$count.GetValue($null, $null))
}
$out.bounded = @{ most = $limit; highest = $highest }
[IO.File]::WriteAllText($env:CAR_RESULT, (ConvertTo-Json $out -Depth 6 -Compress), $utf8)
"""


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class WrapMeasureCase(unittest.TestCase):
    """The window compiled once, and the probe run once, for both classes' tests."""

    answer: dict = {}
    run_ = None

    @classmethod
    def setUpClass(cls):
        if WrapMeasureCase.answer or WrapMeasureCase.run_ is not None:
            return
        folder = tempfile.TemporaryDirectory()
        WrapMeasureCase.folder = folder
        work = Path(folder.name)
        exe = work / "CodexAutoResumeSettings.exe"
        subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                        "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                        *[str(path) for path in guiscan.sources()]],
                       check=True, capture_output=True, timeout=300,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        data = work / "input.json"
        data.write_text(json.dumps({"languages": [{"locale": locale, "texts": texts(locale)} for locale in LANGUAGES],
                                    "widths": list(WIDTHS), "variants": list(VARIANTS)}, ensure_ascii=False),
                        encoding="utf-8")
        probe = work / "probe.ps1"
        probe.write_text(PROBE, encoding="utf-8-sig")
        result = work / "result.json"
        WrapMeasureCase.run_ = subprocess.run(
            [str(POWERSHELL), "-STA", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(probe)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=dict(os.environ, CAR_EXE=str(exe), CAR_INPUT=str(data), CAR_RESULT=str(result)))
        if WrapMeasureCase.run_.returncode == 0 and result.is_file():
            WrapMeasureCase.answer = json.loads(result.read_text(encoding="utf-8-sig"))

    @classmethod
    def tearDownModule_(cls):
        folder = getattr(WrapMeasureCase, "folder", None)
        if folder is not None:
            folder.cleanup()

    def setUp(self):
        if not self.answer:
            self.fail("the probe did not run: " + (self.run_.stderr or self.run_.stdout)[-3000:])


def tearDownModule():
    WrapMeasureCase.tearDownModule_()


class RememberedAnswerTests(WrapMeasureCase):
    def test_every_language_has_texts_that_wrap(self):
        for locale in LANGUAGES:
            with self.subTest(locale=locale):
                self.assertGreaterEqual(len(texts(locale)), 10 if locale != "ko" else 5)

    def test_every_case_was_asked(self):
        expected = sum(len(texts(locale)) for locale in LANGUAGES) * len(WIDTHS) * len(VARIANTS)
        self.assertEqual(self.answer["cases"], expected)

    def test_the_remembered_answer_is_the_one_a_fresh_label_gives(self):
        self.assertEqual(self.answer["wrong"], [], "a remembered answer differs from Label's own")

    def test_a_label_asked_twice_answers_alike(self):
        self.assertEqual(self.answer["repeats"], 0)


class AskedOnceTests(WrapMeasureCase):
    def test_the_first_question_reaches_label(self):
        self.assertEqual(self.answer["asked"]["first"], 1)

    def test_the_same_question_from_another_label_does_not(self):
        self.assertEqual(self.answer["asked"]["second"], 0, "asked again: nothing was remembered")

    def test_a_different_padding_or_width_is_a_different_question(self):
        self.assertEqual(self.answer["asked"]["padding"], 1)
        self.assertEqual(self.answer["asked"]["width"], 1)

    def test_the_remembered_answers_are_bounded(self):
        bounded = self.answer["bounded"]
        self.assertGreater(bounded["most"], 1000)
        self.assertLessEqual(bounded["highest"], bounded["most"])


if __name__ == "__main__":
    unittest.main()
