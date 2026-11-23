r"""The v0.6.26 "Codex changed" words are laid out by the layout audits (fourth round, plans/v0626-audit4/audit-design.md,
the open lead).

The watcher's own judge (domain/public.py self_check) puts words in three places: the Right now line
(overlay.codex_changed, the longest of its words in most languages - de 76 characters, vi 64, fr 60), the Pending rows'
overlay, and Diagnostics' callout of up to four lines (CodexNote). No reply the layout audits laid out carried a
self_check, so none of them was ever measured. Now SettingsForm.LayoutAudit lays out the Overview, Pending and
Diagnostics again from a reply whose judge says the most it says (WithCodexChanged; AuditedCodexChanged counts the
pages), and tests/test_gui_layout.py's overview_states holds the Overview to neither scrolling nor moving as a watcher
comes to say it (codex_changed) - in every language at five scalings in the four audit modules. This module holds that
the audit looks, with canaries no page could hold, and audits it here in the languages whose words are longest and in
the three right-to-left ones, at 100, 150 and 200 % (SettingsForm.CodexChangedAudit: those pages alone). Two of the
words a page's walk cannot judge are measured there too: the header's facts end in an ellipsis by design, and these
must be said whole; and the callout, a label held to a width, would clip a word longer than it.

The window is compiled from the shipped sources and laid out without being shown: it is not even a top-level window.
GUI test module: run on its own, through gui_lock.sh.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

import guiscan
from codex_auto_resume import l10n
from test_gui_layout import codex_changed, fullest_snapshot, overview_states
from test_gui_v0611_access import CSC, POWERSHELL, compile_window

# The longest words of Right now's state (de, vi, fr), two languages written without spaces between words (ja, th),
# and the three written right to left (ar, he, fa).
LOCALES = ("en", "de", "vi", "fr", "ja", "th", "ar", "he", "fa")
SCALES = (1.0, 1.5, 2.0)

PROBE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
[Windows.Forms.Application]::EnableVisualStyles()
[Windows.Forms.Application]::SetCompatibleTextRenderingDefault($false)
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$static = [Reflection.BindingFlags]'Static,NonPublic,Public'
$form = $assembly.GetType('CodexAutoResume.SettingsForm', $true)
$audit = $form.GetMethod('CodexChangedAudit', $static)
$statesAudit = $form.GetMethod('OverviewStatesAudit', $static)
$looked = $form.GetField('AuditedCodexChanged', $static)
$work = [string]$env:CAR_WORK
$utf8 = New-Object Text.UTF8Encoding $false
function Read([string]$name) { return [IO.File]::ReadAllText((Join-Path $work $name), $utf8) }
$snapshot = Read 'snapshot.json'
$states = Read 'states.json'
$out = @{ audit = @{}; states = @{}; looked = @{} }
foreach ($locale in (ConvertFrom-Json $env:CAR_LOCALES)) {
    $catalog = Read ('strings-' + $locale + '.json')
    $out.audit[$locale] = @{}; $out.states[$locale] = @{}; $out.looked[$locale] = @{}
    foreach ($scale in (ConvertFrom-Json $env:CAR_SCALES)) {
        $key = ([double]$scale).ToString('0.00', [Globalization.CultureInfo]::InvariantCulture)
        $out.audit[$locale][$key] = [string]$audit.Invoke($null, [object[]]@($catalog, $snapshot, [double]$scale))
        $out.looked[$locale][$key] = if ($null -eq $looked) { -1 } else { [int]$looked.GetValue($null) }
        $out.states[$locale][$key] = [string]$statesAudit.Invoke($null, [object[]]@($catalog, $states, [double]$scale))
    }
}
# Words no page could hold, so a quiet report on them is the audit measuring them.
$canary = Read 'strings-canary.json'
$out.canary = [string]$audit.Invoke($null, [object[]]@($canary, $snapshot, [double]1.0))
[IO.File]::WriteAllText((Join-Path $work 'result.json'), ($out | ConvertTo-Json -Depth 6 -Compress), $utf8)
"""


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class CodexChangedLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = compile_window(work)
        def reply(locale, catalog):
            return {"ok": True, "language": locale, "strings": catalog, "endonyms": dict(l10n.ENDONYMS),
                    "preference": locale, "system_language": locale}

        for locale in LOCALES:
            (work / ("strings-%s.json" % locale)).write_text(json.dumps(reply(locale, l10n.catalog(locale)),
                                                                        ensure_ascii=False), encoding="utf-8")
        canary = dict(l10n.catalog("en"), **{"overlay.codex_changed": "Y" * 400, "selfcheck.held_elsewhere": "Z" * 400})
        (work / "strings-canary.json").write_text(json.dumps(reply("en", canary)), encoding="utf-8")
        now = time.time()
        fullest = fullest_snapshot(now)
        (work / "snapshot.json").write_text(json.dumps(fullest, ensure_ascii=False), encoding="utf-8")
        states = [["the fullest", fullest], ["Codex changed, recovery cannot work here", codex_changed(fullest)]]
        (work / "states.json").write_text(json.dumps(states, ensure_ascii=False), encoding="utf-8")
        probe = work / "probe.ps1"
        probe.write_text(PROBE, encoding="utf-8")
        said, errors = work / "probe.out", work / "probe.err"
        with open(said, "wb") as out, open(errors, "wb") as err:
            done = subprocess.run([str(POWERSHELL), "-STA", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                   "-File", str(probe)], stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                  timeout=120 * len(LOCALES) * len(SCALES), creationflags=0x08000000,
                                  env=dict(os.environ, CAR_EXE=str(exe), CAR_WORK=str(work),
                                           CAR_LOCALES=json.dumps(list(LOCALES)), CAR_SCALES=json.dumps(SCALES)))
        answer = work / "result.json"
        cls.failed = errors.read_text(encoding="utf-8", errors="replace")[-3000:]
        cls.answer = (json.loads(answer.read_text(encoding="utf-8-sig"))
                      if done.returncode == 0 and answer.is_file() else {})

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if not self.answer:
            self.fail("the probe did not run: " + self.failed)

    def test_the_audit_lays_out_the_three_pages_with_codex_changed(self):
        for locale in LOCALES:
            for scale in SCALES:
                with self.subTest(locale=locale, scale=scale):
                    self.assertEqual(self.answer["looked"][locale]["%.2f" % scale], 3, "the Overview, Pending, Diagnostics")

    def test_nothing_of_codex_changed_is_cut_off_in_the_longest_languages_and_right_to_left(self):
        for locale in LOCALES:
            for scale in SCALES:
                report = self.answer["audit"][locale]["%.2f" % scale]
                with self.subTest(locale=locale, scale=scale):
                    self.assertEqual(report, "", "\n" + "\n".join(report.splitlines()[:40]))

    def test_the_overview_neither_scrolls_nor_moves_as_the_watcher_comes_to_say_it(self):
        for locale in LOCALES:
            for scale in SCALES:
                report = self.answer["states"][locale]["%.2f" % scale]
                with self.subTest(locale=locale, scale=scale):
                    self.assertEqual(report, "", "\n" + "\n".join(report.splitlines()[:40]))

    def test_the_audit_finds_codex_changed_words_no_page_could_hold(self):
        canary = self.answer["canary"]
        self.assertRegex(canary, r"overview with Codex changed/header :: its facts end in an ellipsis",
                         "the header's facts, 400 characters wide, went unreported, so a quiet report on them proves nothing")
        self.assertRegex(canary, r"diagnostics with Codex changed/.* :: a word needs ",
                         "the callout's 400-character word went unreported, so a quiet report on it proves nothing")

    def test_the_states_the_four_audit_modules_lay_out_include_it(self):
        names = [name for name, _reply in overview_states(0)]
        self.assertIn("Codex changed, recovery cannot work here", names)
        changed = dict(overview_states(0))["Codex changed, recovery cannot work here"]
        self.assertTrue(changed["status"]["watcher"]["self_check"]["blocked"].startswith("recovery_blocked:"))
        # And LayoutAudit, which the four audit modules run in every language at five scalings, lays them out too.
        self.assertIn("form.AuditCodexChanged(snapshot, findings);", guiscan.member_body("SettingsForm", "LayoutAuditAt"))


if __name__ == "__main__":
    unittest.main()
