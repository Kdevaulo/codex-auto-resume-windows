"""The setup window's Finish page tells the person when an update STARTED the watcher again (v0.6.24).

install.ps1's last word already said it: a watcher that had ended unexpectedly before an update or a repair (a crash, in
this sign-in - not a stop, a restart, a shutdown or a sign-out) is started again by setup, which then exits with
EXIT_STARTED_AGAIN (5) for a caller that asks, and the last word says why a watcher that was not running runs now
(test_update_ended_by_itself). The Finish page told a watcher that was LEFT stopped in a box of its own
(InstallerFlow.LeftStoppedLine, installer.done.left_stopped) and said nothing of this, though the person reads the
page rather than the log.

Held here:

* SourceTests - InstallerFlow.StartedAgainLine is the start of the line install.ps1 prints, for an update and for a
  repair, and of no other line of its last word; it is not the left-stopped line's start, and neither starts with the
  other, so the two boxes never read each other's line. The window shows the one box when the other is not, and its
  words are the catalog key installer.done.started_again, with the English beside it.
* CatalogTests - the key is in every catalog, said in that catalog's own words for the watcher, and sits after
  installer.done.left_stopped (build/l10n.py import sorts a catalog: it must not be used to add it).
* FinishPageTests - the Finish page, built and never shown (the compiled setup program called through reflection),
  over install.ps1's own last word run with setup stubbed: the started-again line gives the started-again box, in every
  catalog, for an update and a repair and the Dashboard's update, with the light of a watcher that runs; the
  left-stopped line gives the left-stopped box and not this one; a plain update gives neither; the two lines
  together give the left-stopped box alone.
* LayoutTests - the setup window's layout audit (build/setup/SetupWindow.cs InstallerAudit) lays the started-again
  Finish page out in a finish of its own beside the left-stopped one; here in English at the smallest and the largest
  scaling, and in every language at every scaling by test_installer_window.LayoutAuditTests.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from test_installer import block
import test_installer_left_stopped as left_stopped  # the module, not its TestCase: a TestCase named here is
from test_installer_left_stopped import INSTALL, left_stopped_line  # discovered again under this module's name
from test_installer_window import CSC, PAIRS, POWERSHELL, _build, _powershell

from codex_auto_resume import l10n

ROOT = Path(__file__).resolve().parents[1]
FLOW = (ROOT / "gui" / "InstallerFlow.cs").read_text(encoding="utf-8")
WINDOW = (ROOT / "gui" / "InstallerWindow.cs").read_text(encoding="utf-8")
SETUP_WINDOW = (ROOT / "build" / "setup" / "SetupWindow.cs").read_text(encoding="utf-8")
LOCALES = ROOT / "src" / "codex_auto_resume" / "locales"
KEY = "installer.done.started_again"
LEFT_KEY = "installer.done.left_stopped"


def started_again_line() -> str:
    """InstallerFlow.StartedAgainLine, read from the window's source."""
    marker = 'internal const string StartedAgainLine = "'
    start = FLOW.index(marker) + len(marker)
    return FLOW[start:FLOW.index('";', start)]


def catalog(locale: str) -> dict:
    return json.loads((LOCALES / ("%s.json" % locale)).read_text(encoding="utf-8"))


class LastWords:
    """install.ps1's last word as it prints, for a watcher in each state. A plain class borrowing LastWordTests' script
    runner: none of its tests run again here."""

    run_script = left_stopped.LastWordTests.run_script
    WORD = left_stopped.LastWordTests.WORD

    def last_word(self, *, again=False, left=False, repair=False):
        text = INSTALL.read_text(encoding="utf-8")
        stubs = ("function Invoke-Setup { param([string[]]$Arguments)\n"
                 "    $global:LASTEXITCODE = 0; return 0 }\n"
                 "function Open-ClosedDashboard { param([switch]$Updated) }\n")
        flag = lambda value: "$true" if value else "$false"   # noqa: E731
        script = ("$script:Failed = $false\n$upgrade = $true\n$repair = %s\n$watcherUnconfirmed = $false\n"
                  "$previousWatcherStillRunning = $false\n$watcherLeftStopped = %s\n$watcherStartedAgain = %s\n"
                  % (flag(repair), flag(left), flag(again)) + stubs + block(text, *self.WORD))
        done = self.run_script(script)
        if done.returncode != 0:
            raise AssertionError(done.stdout + done.stderr)
        return done.stdout


# Each scenario: its flow, the words it reads, and what install.ps1 said. One window each, in the catalog named.
PROBE = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$any = [Reflection.BindingFlags]'Static,Instance,NonPublic,Public'
function T($name) { $assembly.GetType('CodexAutoResume.' + $name, $true) }
$FlowType = T 'InstallerFlow'
$WindowType = T 'InstallerWindow'
$WordsType = T 'InstallerWords'
function Of($object, $name) { $object.GetType().GetProperty($name, $any).GetValue($object, $null) }
function CallOn($object, $name, $arguments) { $object.GetType().GetMethod($name, $any).Invoke($object, [object[]]$arguments) }
function NewFlow($mode, $edition, $installed, $from) {
    $flow = $FlowType.GetConstructors($any)[0].Invoke([object[]]@([string]$mode, 'C:\Users\ExampleUser\.codex-auto-resume',
                                                               [string]$edition, $installed, '9.9.9'))
    $FlowType.GetField('From', $any).SetValue($flow, [string]$from)
    $flow
}
function TextOf($control) {
    $notice = $control.GetType().GetField('notice', $any)
    if ($notice) { return [string]$notice.GetValue($control) }
    [string]$control.Text
}
function Rows($window) { @(@(CallOn $window 'ShownRows' @()) | ForEach-Object { TextOf $_ }) }
function LightOf($window) {
    $dot = $WindowType.GetField('light', $any).GetValue($window)
    [string]$dot.GetType().GetProperty('State', $any).GetValue($dot, $null)
}
$parse = $FlowType.GetMethod('ParseObject', $any)
function WordsOf($path, $language) {
    $WordsType.GetConstructors($any)[0].Invoke([object[]]@(
        $parse.Invoke($null, [object[]]@([IO.File]::ReadAllText($path, [Text.Encoding]::UTF8))), $language))
}
$font = [System.Drawing.SystemFonts]::MessageBoxFont
function Window($flow, $words) { $WindowType.GetConstructors($any)[0].Invoke([object[]]@($flow, $words, $null, $null, $null, $font)) }
function Finish($flow, $words, $said) {
    $window = Window $flow $words
    $null = CallOn $window 'Finished' @(0, [string]$said)
    @{ rows = (Rows $window); light = (LightOf $window) }
}
function Update() { NewFlow 'install' 'standard' 'standard' '9.9.8' }
function Repair() {
    $flow = NewFlow 'install' 'standard' 'standard' '9.9.9'
    $FlowType.GetField('Maintaining', $any).SetValue($flow, $true)
    $flow
}
function Dashboard() { NewFlow 'update' 'standard' 'standard' '9.9.8' }
$said = ConvertFrom-Json $env:CAR_SAID
$out = @{ locale = @{} }
$english = WordsOf $env:CAR_EN 'en'
$out.again = Finish (Update) $english $said.again
$out.again_repair = Finish (Repair) $english $said.again_repair
$out.again_dashboard = Finish (Dashboard) $english $said.again
$out.left = Finish (Update) $english $said.left
$out.left_repair = Finish (Repair) $english $said.left_repair
$out.plain = Finish (Update) $english $said.plain
$out.both = Finish (Update) $english ($said.again + "`n" + $said.left)
$out.both_reverse = Finish (Update) $english ($said.left + "`n" + $said.again)
# Every catalog, in its own language, for the one line.
foreach ($path in (Get-ChildItem $env:CAR_LOCALES -Filter *.json)) {
    $language = [IO.Path]::GetFileNameWithoutExtension($path.Name)
    $words = WordsOf $path.FullName $language
    $out.locale[$language] = @{ again = (Finish (Update) $words $said.again); left = (Finish (Update) $words $said.left);
                                plain = (Finish (Update) $words $said.plain) }
}
$out | ConvertTo-Json -Depth 8 -Compress
"""


class SourceTests(unittest.TestCase):
    def test_the_line_is_the_start_of_install_ps1s_started_again_line_and_of_no_other(self):
        line = started_again_line()
        for repair in (False, True):
            said = LastWords().last_word(again=True, repair=repair).splitlines()
            with self.subTest(repair=repair):
                self.assertEqual(len([each for each in said if each.strip().startswith(line)]), 1, said)
        for other, kwargs in (("left stopped", {"left": True}), ("running", {}), ("repair left", {"left": True, "repair": True})):
            with self.subTest(other=other):
                self.assertFalse(any(each.strip().startswith(line) for each in LastWords().last_word(**kwargs).splitlines()))

    def test_neither_line_starts_with_the_other(self):
        again, left = started_again_line(), left_stopped_line()
        self.assertFalse(again.startswith(left) or left.startswith(again))

    def test_the_line_is_the_one_install_ps1_prints_before_update_or_repair(self):
        text = INSTALL.read_text(encoding="utf-8")
        self.assertIn("Write-Host ('" + started_again_line() + "' + $what", text)

    def test_the_finish_page_shows_the_box_for_the_line_and_never_beside_the_left_stopped_one(self):
        self.assertIn('if (said.StartsWith(InstallerFlow.StartedAgainLine, StringComparison.Ordinal)) startedAgain = true;', WINDOW)
        self.assertIn("if (code == 0 && startedAgain && !leftStopped)", WINDOW)
        self.assertIn("if (code == 0 && leftStopped)", WINDOW)
        english = catalog("en")[KEY]
        self.assertIn('Say("%s", "%s")' % (KEY, english), WINDOW, "the fallback is the English catalog's")
        self.assertIn("SoftCallout(words.Say(\"%s\"" % KEY, WINDOW)

    def test_the_light_is_the_running_watchers_not_the_stopped_ones(self):
        """A watcher started again runs: only an unconfirmed or left-stopped watcher leaves the light idle."""
        self.assertIn("InstallerFlow.Light(flow.Mode, name, code, unconfirmed || leftStopped, previousRunning)", WINDOW)

    def test_the_audit_lays_the_started_again_finish_out_beside_the_left_stopped_one(self):
        self.assertIn("InstallerFlow.StartedAgainLine", SETUP_WINDOW)
        self.assertIn("InstallerFlow.LeftStoppedLine", SETUP_WINDOW)
        self.assertIn('" started again"', SETUP_WINDOW)


class CatalogTests(unittest.TestCase):
    def test_every_catalog_says_it(self):
        english = catalog("en")[KEY]
        self.assertTrue(english.startswith("The watcher had ended unexpectedly"), english)
        for locale in l10n.LOCALES:
            with self.subTest(locale=locale):
                own = catalog(locale)
                self.assertIn(KEY, own)
                self.assertTrue(own[KEY].strip())
                self.assertEqual(l10n.placeholders(own[KEY]), l10n.placeholders(english))
                if locale != "en":
                    self.assertNotEqual(own[KEY], english, "translated, not English left in")

    def test_it_is_one_sentence_beside_the_left_stopped_one_in_the_catalogs_own_word_for_the_watcher(self):
        # The word for the watcher the same catalog's left-stopped sentence uses (its first words).
        for locale in l10n.LOCALES:
            if locale == "en":
                continue
            own = catalog(locale)
            with self.subTest(locale=locale):
                self.assertLess(len(own[KEY]), len(own[LEFT_KEY]), "shorter than the left-stopped box")
                self.assertEqual(own[KEY].count("\n"), 0)

    def test_the_korean_words_use_the_products_own_watcher_word(self):
        ko = catalog("ko")[KEY]
        self.assertIn("워처", ko)
        self.assertNotIn("감시기", ko)
        self.assertNotIn("에디션", ko)

    def test_each_catalog_keeps_its_key_order_and_has_the_key_after_left_stopped(self):
        for locale in l10n.LOCALES:
            with self.subTest(locale=locale):
                keys = list(json.loads((LOCALES / ("%s.json" % locale)).read_text(encoding="utf-8")))
                self.assertEqual(keys.index(KEY), keys.index(LEFT_KEY) + 1)


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class FinishPageTests(unittest.TestCase):
    """The Finish page for each way install.ps1 can end, in every catalog."""

    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="installer-started-again-"))
        exe = _build(cls.work)
        words = LastWords()
        cls.said = {"again": words.last_word(again=True), "again_repair": words.last_word(again=True, repair=True),
                    "left": words.last_word(left=True), "left_repair": words.last_word(left=True, repair=True),
                    "plain": words.last_word()}
        cls.result = _powershell(PROBE, cls.work, 900, CAR_EXE=str(exe), CAR_SAID=json.dumps(cls.said),
                                 CAR_EN=str(LOCALES / "en.json"), CAR_LOCALES=str(LOCALES))
        cls.answer = json.loads(cls.result.stdout) if cls.result.returncode == 0 and cls.result.stdout.strip() else {}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def setUp(self):
        if not self.answer:
            self.fail("the probe did not run: " + (self.result.stderr or self.result.stdout)[-3000:])

    def test_a_watcher_started_again_is_told_on_the_finish_page(self):
        again, left = catalog("en")[KEY], catalog("en")[LEFT_KEY]
        for name in ("again", "again_repair", "again_dashboard"):
            with self.subTest(name):
                rows = self.answer[name]["rows"]
                self.assertIn(again, rows)
                self.assertNotIn(left, rows)
                self.assertLess(rows.index("Exit code: 0"), rows.index(again), "under the headline and the exit code")
                self.assertEqual(self.answer[name]["light"], "monitoring", "the watcher runs")
        self.assertEqual(self.answer["again"]["rows"][0], "Codex Auto Resume is updated.")
        self.assertEqual(self.answer["again_repair"]["rows"][0], "Codex Auto Resume is repaired.")

    def test_a_watcher_left_stopped_keeps_its_own_box_and_not_this_one(self):
        again, left = catalog("en")[KEY], catalog("en")[LEFT_KEY]
        for name in ("left", "left_repair"):
            with self.subTest(name):
                rows = self.answer[name]["rows"]
                self.assertIn(left, rows)
                self.assertNotIn(again, rows)
                self.assertEqual(self.answer[name]["light"], "idle")

    def test_a_plain_update_shows_neither(self):
        rows = self.answer["plain"]["rows"]
        self.assertNotIn(catalog("en")[KEY], rows)
        self.assertNotIn(catalog("en")[LEFT_KEY], rows)
        self.assertEqual(self.answer["plain"]["light"], "monitoring")

    def test_the_two_boxes_never_both_show(self):
        again, left = catalog("en")[KEY], catalog("en")[LEFT_KEY]
        for name in ("both", "both_reverse"):
            with self.subTest(name):
                rows = self.answer[name]["rows"]
                self.assertIn(left, rows)
                self.assertNotIn(again, rows)
        for locale, found in self.answer["locale"].items():
            with self.subTest(locale=locale):
                shown = [KEY if catalog(locale)[KEY] in found[kind]["rows"] else LEFT_KEY if catalog(locale)[LEFT_KEY] in found[kind]["rows"]
                         else None for kind in ("again", "left", "plain")]
                self.assertEqual(shown, [KEY, LEFT_KEY, None])

    def test_every_catalog_says_it_in_its_own_words(self):
        self.assertEqual(sorted(self.answer["locale"]), sorted(l10n.LOCALES))
        for locale, found in self.answer["locale"].items():
            with self.subTest(locale=locale):
                self.assertIn(catalog(locale)[KEY], found["again"]["rows"])
                self.assertNotIn(catalog(locale)[KEY], found["left"]["rows"])
                self.assertNotIn(catalog(locale)[KEY], found["plain"]["rows"])


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class LayoutTests(unittest.TestCase):
    """The audit's started-again variant, in English at the smallest and the largest scaling. Every language at every
    scaling and text size is test_installer_window's own LayoutAuditTests, which lays this Finish page out as well
    (a long sentence in a callout is wrapped, and the Finish page is measured again for what the run left it saying,
    so what the audit can find here is a word or a button the window cuts off, not a callout that is too tall)."""

    AUDIT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$audit = $assembly.GetType('CodexAutoResume.InstallerAudit', $true).GetMethod('LayoutAudit', [Reflection.BindingFlags]'Static,NonPublic')
$catalog = [IO.File]::ReadAllText($env:CAR_CATALOG, [Text.Encoding]::UTF8)
$out = @{}
foreach ($pair in (ConvertFrom-Json $env:CAR_PAIRS)) {
    $out[('{0:F2}/{1:F2}' -f [double]$pair[0], [double]$pair[1])] = [string]$audit.Invoke($null,
        [object[]]@([string]$catalog, 'en', [double]$pair[0], [double]$pair[1]))
}
[IO.File]::WriteAllText($env:CAR_RESULT, ($out | ConvertTo-Json -Depth 4 -Compress), (New-Object Text.UTF8Encoding $false))
"""

    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="installer-started-again-audit-"))
        exe = _build(cls.work)
        result = cls.work / "result.json"
        cls.result = _powershell(cls.AUDIT, cls.work, 900, CAR_EXE=str(exe), CAR_CATALOG=str(LOCALES / "en.json"),
                                 CAR_PAIRS=json.dumps([PAIRS[0], PAIRS[4]]), CAR_RESULT=str(result))
        cls.answer = (json.loads(result.read_text(encoding="utf-8-sig"))
                      if cls.result.returncode == 0 and result.is_file() else {})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def setUp(self):
        if not self.answer:
            self.fail("the audit did not run: " + (self.result.stderr or self.result.stdout)[-3000:])

    def test_nothing_is_cut_off_at_the_smallest_and_the_largest_scaling(self):
        self.assertEqual(sorted(self.answer), ["1.00/1.00", "2.00/1.00"])
        for pair, report in self.answer.items():
            with self.subTest(pair):
                self.assertEqual(report, "", "\n" + "\n".join(report.splitlines()[:30]))


if __name__ == "__main__":
    unittest.main()
