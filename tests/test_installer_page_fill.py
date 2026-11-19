"""The setup window's 600 x 600 room, filled (v0.6.24-beta.3, the owner's option A of 2026-11-17: "설치앱은 세로가
늘어난게 빈공간으로만 늘어났네"). The window keeps its size and its header; only the content card of three pages gains
what a person installing it wants to know:

* the Welcome page - three numbered points under the guide's link and before the language picker: it notices a
  conversation that stopped, it carries on once it can, and the words it sends are the person's to choose;
* the Ready page of a first installation - after what it showed before, what is installed (the watcher, the
  Dashboard and the Codex plugin, and the advanced edition's own features in that edition), one hairline row each with
  what it is beside its name, and that no administrator rights are needed. An update and a change of edition keep the
  room for what they keep, change and bring;
* the Installing page - also updating, repairing, removing and installing another version - under the bar, the steps
  this run goes through, from the installer's own sequence for its way (InstallerProgress.Listed): done (a filled disc
  with a check), under way (a ring with a dot, its name in bold) and still to come (an empty ring), moved only by the
  lines the installer prints, never by time; a step the run passes without taking it leaves the list. The bar stays;
  v0.6.24 final (the owner, 2026-11-19): the log is under the steps, shown from the start, with its toggle (Hide the
  log) above it; it takes the card's room down to the buttons, never less than four lines, and hiding it moves nothing
  above it - nor is that remembered for another run.

What is held here, on the window built and never shown (the probe pattern of tests/test_installer_window.py and
tests/test_gui_v0624_setup_600.py, the scaling and text size stood in as InstallerAudit stands them in), in every
language at Windows' usual text size and in a few at other scalings and text sizes: each page's rows are there, in
their order, in the catalog's words; each mark stands at the card's leading edge beside its row - on the right where
the language is written right to left; nothing is cut, overlaps or leaves the card; and at text size 1 the window is
still 600 x 600 (scaled) in every language.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

import guiscan
from codex_auto_resume import l10n
from test_installer_window import CSC, POWERSHELL, _build, _powershell

ROOT = Path(__file__).resolve().parents[1]
RIGHT_TO_LEFT = ("ar", "he", "fa")

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
$FormType = T 'SettingsForm'
$GetState = [System.Windows.Forms.Control].GetMethod('GetState', [Reflection.BindingFlags]'NonPublic,Instance')
function Own($control) { [bool]$GetState.Invoke($control, [object[]]@(2)) }
function Of($object, $name) { $object.GetType().GetProperty($name, $any).GetValue($object, $null) }
function CallOn($object, $name, $arguments) { $object.GetType().GetMethod($name, $any).Invoke($object, [object[]]$arguments) }
function Box($c) { @($c.Left, $c.Top, $c.Width, $c.Height) }
$parse = $FlowType.GetMethod('ParseObject', $any)
function WordsOf($locale) {
    $path = Join-Path $env:CAR_LOCALES ($locale + '.json')
    $WordsType.GetConstructors($any)[0].Invoke([object[]]@($parse.Invoke($null, [object[]]@([IO.File]::ReadAllText($path, [Text.Encoding]::UTF8))), $locale))
}
function NewFlow($mode, $edition, $installed, $from) {
    $flow = $FlowType.GetConstructors($any)[0].Invoke([object[]]@([string]$mode, 'C:\Users\ExampleUser\.codex-auto-resume',
                                                               [string]$edition, $installed, '9.9.9'))
    $FlowType.GetField('From', $any).SetValue($flow, [string]$from)
    $flow
}
function Font($c) { $c.Font.Name + '|' + [int]$c.Font.Style + '|' + $c.Font.SizeInPoints }
function Snapshot($window, $name) {
    $window.PerformLayout()
    $sheet = Of $window 'Body'
    $card = $sheet.Parent
    $width = $card.Width - $card.Padding.Horizontal
    $height = $card.Height - $card.Padding.Vertical
    $used = [int](CallOn $window 'Arrange' @($width))
    $rows = @()
    foreach ($c in @(CallOn $window 'ShownRows' @())) {
        $wanted = $c.GetPreferredSize((New-Object System.Drawing.Size($c.Width, 0)))
        $rows += ,@{ type = $c.GetType().Name; text = [string]$c.Text; box = (Box $c); font = (Font $c);
                     want = @($wanted.Width, $wanted.Height); state = [string]$c.AccessibleDescription;
                     least = [int](CallOn $window 'Least' @($c, [int]$wanted.Height)) }
    }
    $marks = @()
    foreach ($c in $sheet.Controls) {
        if ($c.GetType().Name -ceq 'StepMark' -and (Own $c)) { $marks += ,@{ kind = [string](Of $c 'Kind'); box = (Box $c); name = [string]$c.AccessibleName } }
    }
    $shown = @()
    foreach ($c in $sheet.Controls) { if (Own $c) { $shown += ,@{ type = $c.GetType().Name; box = (Box $c) } } }
    # The keyboard's order among the sheet's own controls (their tab indexes), and where the log's caret stands.
    $tabs = @()
    foreach ($c in @($sheet.Controls | Where-Object { (Own $_) -and ($_.GetType().Name -ceq 'SoftLink' -or $_.GetType().Name -ceq 'SoftTextArea') } | Sort-Object { $_.TabIndex })) { $tabs += [string]$c.GetType().Name }
    $area = $window.GetType().GetField('logArea', $any).GetValue($window)
    $box = $area.GetType().GetField('Box', $any).GetValue($area)
    @{ page = $name; client = @($window.ClientSize.Width, $window.ClientSize.Height); width = $width; height = $height;
       used = $used; rows = $rows; marks = $marks; shown = $shown; tabs = $tabs;
       caret = @($box.SelectionStart, $box.TextLength); logText = [string]$box.Text }
}
$notes = "v9.9.9 - something new`n`n**Both editions.** A line of what is new, long enough to take a second line in a window of this width.`n- A line.`n"
$out = @{}
foreach ($case in (ConvertFrom-Json $env:CAR_CASES)) {
    $locale = [string]$case[0]; $display = [double]$case[1]; $text = [double]$case[2]
    $FormType.GetMethod('StandIn', $any).Invoke($null, [object[]]@($display, $text)) | Out-Null
    $WindowType.GetField('WorkHeightStandIn', $any).SetValue($null, 5000)
    $box = [System.Drawing.SystemFonts]::MessageBoxFont
    $system = [double]$FormType.GetField('SystemScale', $any).GetValue($null)
    $font = New-Object System.Drawing.Font($box.FontFamily, [single]($box.SizeInPoints * $text * $display / $system), $box.Style, [System.Drawing.GraphicsUnit]::Point)
    $words = WordsOf $locale
    $ways = [ordered]@{
        first = (NewFlow 'install' 'standard' $null '')
        advanced = (NewFlow 'install' 'advanced' $null '')
        update = (NewFlow 'install' 'standard' 'standard' '9.9.8')
        change = (NewFlow 'install' 'advanced' 'standard' '9.9.8')
        dashboard = (NewFlow 'update' 'standard' 'standard' '9.9.8')
        uninstall = (NewFlow 'uninstall' 'standard' 'standard' '')
    }
    $ways.update.GetType().GetField('NotesText', $any).SetValue($ways.update, $notes)
    $ways.dashboard.GetType().GetField('NotesText', $any).SetValue($ways.dashboard, $notes)
    # A setup program's window speaks every language (its picker on the Welcome page); the Dashboard's and the uninstall's
    # one. Never called here: nothing picks another language.
    $script:spoken = $words
    $speaker = [System.Management.Automation.LanguagePrimitives]::ConvertTo([scriptblock]{ param($language) $script:spoken }, (T 'InstallerWindow+Speaker'))
    $snaps = @()
    foreach ($way in $ways.Keys) {
        $says = if ([string]$FlowType.GetField('Mode', $any).GetValue($ways[$way]) -ceq 'install') { $speaker } else { $null }
        $window = $WindowType.GetConstructors($any)[0].Invoke([object[]]@($ways[$way], $words, $says, $null, $null, $font.PSObject.BaseObject))
        foreach ($page in @(CallOn $ways[$way] 'Pages' @())) {
            CallOn $window 'ShowPage' @([string]$page) | Out-Null
            $snaps += ,(Snapshot $window ($way + '/' + $page))
        }
        $window.Dispose()
    }
    # Each run's Progress page, told the installer's lines one at a time, as the window hears them (Heard), and a setup
    # program's unpacking (Unpacking): the step list after each, and the whole page at its start, at its end, and with the
    # log shown and hidden again.
    $runs = @{}
    foreach ($run in (ConvertFrom-Json $env:CAR_RUNS)) {
        $flow = NewFlow ([string]$run.mode) ([string]$run.edition) $(if ($run.installed) { [string]$run.installed } else { $null }) ([string]$run.from)
        $FlowType.GetField('Unpacks', $any).SetValue($flow, [bool]$run.unpacks)
        $window = $WindowType.GetConstructors($any)[0].Invoke([object[]]@($flow, $words, $null, $null, $null, $font.PSObject.BaseObject))
        CallOn $window 'ShowPage' @('progress') | Out-Null
        $seen = @()
        $events = @(,@('start', '')) + @($run.events)
        foreach ($event in $events) {
            if ($event[0] -ceq 'line') { CallOn $window 'Heard' @([string]$event[1]) | Out-Null }
            elseif ($event[0] -ceq 'unpack') { CallOn $window 'Unpacking' @([double]$event[1]) | Out-Null }
            $snap = Snapshot $window ('run:' + $run.name)
            if ($event[0] -ceq 'start') { $first = $snap }
            $steps = @($snap.rows | Where-Object { $_.state -and $_.type -ceq 'WrapLabel' })
            $seen += ,@{ label = [string](@($snap.rows)[1].text); steps = @($steps | ForEach-Object { , @($_.text, $_.state, $_.font) });
                         marks = @(@($snap.marks | Sort-Object { $_.box[1] }) | ForEach-Object { [string]$_.kind }) }
        }
        $default = Snapshot $window ('run:' + $run.name + '/end')
        $snaps += ,$default
        # The toggle hides the log and shows it again, the installer saying one more line while it is folded away.
        $toggle = @(@(CallOn $window 'ShownRows' @()) | Where-Object { $_.GetType().Name -ceq 'SoftLink' })[0]
        CallOn $toggle 'OnClick' @([EventArgs]::Empty) | Out-Null
        $hidden = Snapshot $window ('run:' + $run.name + '/log hidden')
        CallOn $window 'Heard' @('a line said while the log is folded away') | Out-Null
        CallOn $toggle 'OnClick' @([EventArgs]::Empty) | Out-Null
        $shown = Snapshot $window ('run:' + $run.name + '/log shown')
        $snaps += ,$shown
        $runs[[string]$run.name] = @{ seen = $seen; start = $first; default = $default; hidden = $hidden; shown = $shown }
        $window.Dispose()
    }
    $snaps += ,@{ page = 'runs'; runs = $runs }
    $out[('{0}/{1:F2}/{2:F2}' -f $locale, $display, $text)] = $snaps
}
$FormType.GetMethod('StandIn', $any).Invoke($null, [object[]]@([double]$FormType.GetField('SystemScale', $any).GetValue($null), 1.0)) | Out-Null
$WindowType.GetField('WorkHeightStandIn', $any).SetValue($null, 0)
[IO.File]::WriteAllText($env:CAR_RESULT, ($out | ConvertTo-Json -Depth 12 -Compress), (New-Object Text.UTF8Encoding $false))
"""

# Every language at Windows' usual text size and scaling, and a few at other scalings and text sizes - a language
# written right to left among them.
CASES = ([[locale, 1.0, 1.0] for locale in l10n.LOCALES] +
         [["ko", 1.5, 1.0], ["de", 1.25, 1.0], ["ar", 1.75, 1.0], ["ja", 2.0, 1.0], ["en", 1.0, 1.5], ["ru", 1.0, 2.25],
          ["he", 1.0, 1.5], ["en", 1.5, 1.0], ["en", 2.0, 1.0], ["ko", 2.0, 1.0]])


def _words(locale):
    return l10n.catalog(locale)


def _lines(*lines):
    return [["line", line] for line in lines]


UNPACKING = [["unpack", 0.4], ["unpack", 1.0]]
# install.ps1's lines as a first installation prints them (tests/test_installer_window.py's INSTALLING, without a
# watcher to stop or a Dashboard to close: there is none yet), and one of the window's own progress lines among them.
FIRST = UNPACKING + _lines("Codex Auto Resume", "edition: standard", "  [ok] Found Codex", "  Installing program files",
                           "  Copying the program files into place", "progress: files 3/10",
                           "  [ok] Bundled Python 3.13 (no system Python needed)", "  Registering the Codex plugin",
                           "  Setting up the watcher", "    (the setup step's words, in any language)",
                           "  Checking the installation")
# An update over a watcher that was not running: install.ps1 never says it stops one, and closes the open Dashboard.
OVER = UNPACKING + _lines("edition: standard", "  [ok] Found Codex", "  Updating program files",
                          "  Closing the Dashboard so it opens again on the new version", "  [ok] The Dashboard closed",
                          "  Copying the program files into place", "  Registering the Codex plugin",
                          "  Setting up the watcher", "  Checking the installation")
# The Dashboard's update: the bootstrap's lines, then install.ps1's, a running watcher stopped.
UPDATING = _lines("Codex Auto Resume - setting up", "edition: standard",
                  "  Asking github.com which release is newest. Nothing is uploaded, and no page is read.",
                  "  Downloading v9.9.9 from github.com over HTTPS.",
                  "  [ok] SHA-256 matches the digest pinned in this plugin",
                  "  [ok] Archive contents verified as Codex Auto Resume v9.9.9", "  Installing", "edition: standard",
                  "  [ok] Found Codex", "  Updating program files",
                  "  Stopping the running watcher so the new version takes over",
                  "  Closing the Dashboard so it opens again on the new version",
                  "  Copying the program files into place", "  [ok] Bundled Python 3.13 (no system Python needed)",
                  "  Registering the Codex plugin", "  Setting up the watcher", "  Checking the installation")
REMOVING = _lines("Codex Auto Resume", "  Closing the Dashboard so its files can be removed", "  [ok] The Dashboard closed",
                  "  Removing the watcher, autostart, notification identity and Start Menu entry",
                  "  Removing the Codex plugin", "  Removing the marketplace this installation registered",
                  "  Removing program files", "Removed. Settings and pending recoveries were kept.")
# Each run, the steps it lists before it starts, and the steps that leave the list as the run passes them untaken.
RUNS = [
    {"name": "first", "mode": "install", "edition": "standard", "installed": None, "from": "", "unpacks": True,
     "events": FIRST, "listed": ["unpack", "codex", "prepare", "files", "plugin", "setup", "check"]},
    {"name": "over", "mode": "install", "edition": "standard", "installed": "standard", "from": "9.9.8", "unpacks": True,
     "events": OVER, "listed": ["unpack", "codex", "prepare", "watcher", "dashboard", "files", "plugin", "setup", "check"],
     "leaves": {"watcher": "  Closing the Dashboard so it opens again on the new version"}},
    {"name": "dashboard", "mode": "update", "edition": "standard", "installed": "standard", "from": "9.9.8",
     "unpacks": False, "events": UPDATING,
     "listed": ["ask", "download", "verify", "prepare", "watcher", "dashboard", "files", "plugin", "setup", "check"]},
    {"name": "uninstall", "mode": "uninstall", "edition": "standard", "installed": "standard", "from": "",
     "unpacks": False, "events": REMOVING,
     "listed": ["dashboard", "unregister", "remove_plugin", "remove_files", "finishing"]},
    # Settings > Apps with no Dashboard open: the uninstall never says it closes one.
    {"name": "uninstall_closed", "mode": "uninstall", "edition": "standard", "installed": "standard", "from": "",
     "unpacks": False, "events": [REMOVING[0]] + REMOVING[3:],
     "listed": ["dashboard", "unregister", "remove_plugin", "remove_files", "finishing"],
     "leaves": {"dashboard": "  Removing the watcher, autostart, notification identity and Start Menu entry"}},
    # A setup program started with -Uninstall unpacks its archive first.
    {"name": "setup_uninstall", "mode": "uninstall", "edition": "standard", "installed": "standard", "from": "",
     "unpacks": True, "events": UNPACKING + REMOVING,
     "listed": ["unpack", "dashboard", "unregister", "remove_plugin", "remove_files", "finishing"]},
]
STATE = {"done": "installer.progress.done", "now": "installer.progress.now", "todo": "installer.progress.todo"}
MARK = {"done": "Done", "now": "Now", "todo": "Todo"}


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class PageFillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="setup-fill-"))
        exe = _build(cls.work)
        result = cls.work / "result.json"
        cls.probe = _powershell(PROBE, cls.work, 1500, CAR_EXE=str(exe), CAR_CASES=json.dumps(CASES), CAR_RUNS=json.dumps(RUNS),
                                CAR_LOCALES=str(l10n.DIRECTORY), CAR_RESULT=str(result))
        cls.answer = (json.loads(result.read_text(encoding="utf-8-sig"))
                      if cls.probe.returncode == 0 and result.is_file() else {})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def setUp(self):
        if not self.answer:
            self.fail("the probe did not run: " + (self.probe.stderr or self.probe.stdout)[-3000:])

    def snaps(self, locale, display=1.0, text=1.0):
        return [snap for snap in self.answer["%s/%.2f/%.2f" % (locale, display, text)] if snap["page"] != "runs"]

    def runs(self, locale, display=1.0, text=1.0):
        return [snap for snap in self.answer["%s/%.2f/%.2f" % (locale, display, text)] if snap["page"] == "runs"][0]["runs"]

    def page(self, locale, name, display=1.0, text=1.0):
        found = [snap for snap in self.snaps(locale, display, text) if snap["page"] == name]
        self.assertEqual(len(found), 1, name)
        return found[0]

    def every(self):
        for case in CASES:
            for snap in self.snaps(*case):
                yield case, snap

    def assertBeside(self, snap, mark, row, mirrored):
        """The mark at the card's leading edge, the row in its column past it, the mark centred on the row's first line."""
        width = snap["width"]
        x, y, w, h = mark["box"]
        rx, ry, rw, rh = row["box"]
        if mirrored:
            self.assertEqual(x + w, width, "the mark stands at the card's right edge")
            self.assertLess(rx + rw, x, "the row stands left of its mark")
            self.assertEqual(rx, 0)
        else:
            self.assertEqual(x, 0, "the mark stands at the card's left edge")
            self.assertGreater(rx, x + w, "the row stands right of its mark")
            self.assertEqual(rx + rw, width)
        self.assertLess(abs((y + h / 2) - (ry + min(rh, h) / 2)), max(h, rh), "the mark is beside its row")

    # ------------------------------------------------------------------ the Welcome page

    def test_the_welcome_page_has_three_numbered_points_between_the_guide_and_the_language(self):
        for case in CASES:
            locale = case[0]
            words = _words(locale)
            with self.subTest(case=case):
                snap = self.page(locale, "first/welcome", case[1], case[2])
                texts = [row["text"] for row in snap["rows"]]
                guide = texts.index(words["installer.welcome.guide"])
                language = texts.index(words["installer.language"])
                self.assertEqual(texts[guide + 1:language],
                                 [words["installer.welcome.notices"], words["installer.welcome.notices_help"],
                                  words["installer.welcome.resumes"], words["installer.welcome.resumes_help"],
                                  words["installer.welcome.message"], words["installer.welcome.message_help"]])
                rows = snap["rows"][guide + 1:language]
                self.assertEqual({row["type"] for row in rows}, {"WrapLabel"})
                # The titles in the name's weight, the lines under them in the body's; each title above its line.
                titles, helps = rows[0::2], rows[1::2]
                self.assertEqual(len({row["font"] for row in titles}), 1)
                self.assertNotEqual(titles[0]["font"], helps[0]["font"])
                for title, help_ in zip(titles, helps):
                    self.assertLessEqual(title["box"][1] + title["box"][3], help_["box"][1])
                    self.assertEqual(title["box"][0], help_["box"][0], "a title and its line share the column")
                numbers = sorted((mark for mark in snap["marks"] if mark["kind"] == "Number"), key=lambda mark: mark["box"][1])
                self.assertEqual(len(numbers), 3, "a numbered disc beside each point")
                for mark, title in zip(numbers, titles):
                    self.assertBeside(snap, mark, title, locale in RIGHT_TO_LEFT)
                # Below the guide's link, above the language's label.
                guide_box, language_box = snap["rows"][guide]["box"], snap["rows"][language]["box"]
                self.assertGreater(numbers[0]["box"][1], guide_box[1] + guide_box[3])
                self.assertLess(numbers[-1]["box"][1] + numbers[-1]["box"][3], language_box[1])

    def test_the_dashboards_and_the_uninstalls_pages_have_no_welcome_points(self):
        for snap in self.snaps("en"):
            if snap["page"].startswith(("dashboard/", "uninstall/")):
                with self.subTest(snap["page"]):
                    self.assertNotIn("It notices when one stops", [row["text"] for row in snap["rows"]])
                    self.assertFalse([mark for mark in snap["marks"] if mark["kind"] == "Number"])

    # ------------------------------------------------------------------ the Ready page

    INSTALLED = [("installer.options.watcher", "installer.options.watcher_help"),
                 ("installer.options.dashboard", "installer.options.dashboard_help"),
                 ("installer.options.plugin_name", "installer.options.plugin_help")]
    ADVANCED = ("installer.options.advanced", "installer.options.advanced_help")

    def test_a_first_installation_says_what_is_installed_and_that_no_administrator_rights_are_needed(self):
        for case in CASES:
            locale = case[0]
            words = _words(locale)
            for way, items in (("first", self.INSTALLED), ("advanced", self.INSTALLED + [self.ADVANCED])):
                with self.subTest(case=case, way=way):
                    snap = self.page(locale, way + "/options", case[1], case[2])
                    rows = snap["rows"]
                    texts = [row["text"] for row in rows]
                    # After what the page showed before - the plugin's line - and in this order: the heading, a name, what
                    # it is and a hairline for each, and the line about administrator rights last.
                    start = texts.index(words["installer.options.installed"])
                    self.assertEqual(texts[start - 1], words["installer.options.plugin"])
                    listed = rows[start + 1:start + 1 + 3 * len(items)]
                    self.assertEqual([row["text"] for row in listed],
                                     [text for name, what in items for text in (words[name], words[what], "")])
                    self.assertEqual([row["type"] for row in listed[2::3]], ["InstallerRule"] * len(items))
                    self.assertEqual(texts[start + 1 + 3 * len(items)], words["installer.options.no_admin"])
                    self.assertEqual(texts[-1], words["installer.options.no_admin"])
                    width = snap["width"]
                    for name, what, rule in zip(listed[0::3], listed[1::3], listed[2::3]):
                        self.assertNotEqual(name["font"], what["font"], "the name in the name's weight")
                        # Beside each other on one line: the name at the leading edge, what it is at the other end - or,
                        # where the two do not fit on one line, what it is under the name.
                        beside = name["box"][1] == what["box"][1]
                        mirrored = locale in RIGHT_TO_LEFT
                        if beside:
                            self.assertEqual(name["box"][0] + name["box"][2] if mirrored else name["box"][0],
                                             width if mirrored else 0)
                            self.assertEqual(what["box"][0] if mirrored else what["box"][0] + what["box"][2],
                                             0 if mirrored else width)
                        else:
                            self.assertGreaterEqual(what["box"][1], name["box"][1] + name["box"][3])
                        self.assertGreater(rule["box"][1], max(name["box"][1] + name["box"][3], what["box"][1] + what["box"][3]))
                        self.assertEqual([rule["box"][0], rule["box"][2]], [0, width], "the hairline runs across the card")
                    if case == ["en", 1.0, 1.0]:
                        self.assertTrue(all(name["box"][1] == what["box"][1] for name, what in zip(listed[0::3], listed[1::3])),
                                        "in English each fits beside its name")

    def test_an_update_and_a_change_of_edition_say_what_they_keep_instead(self):
        for case in CASES:
            words = _words(case[0])
            for way in ("update", "change"):
                with self.subTest(case=case, way=way):
                    texts = [row["text"] for row in self.page(case[0], way + "/options", case[1], case[2])["rows"]]
                    self.assertNotIn(words["installer.options.installed"], texts)
                    self.assertNotIn(words["installer.options.no_admin"], texts)

    # ------------------------------------------------------------------ the Installing page

    def test_the_list_is_the_steps_this_run_takes_in_the_installers_order(self):
        for case in CASES:
            words = _words(case[0])
            runs = self.runs(*case)
            for run in RUNS:
                with self.subTest(case=case, run=run["name"]):
                    start = runs[run["name"]]["seen"][0]
                    self.assertEqual([step[0] for step in start["steps"]],
                                     [words["installer.steps." + key] for key in run["listed"]])
                    self.assertEqual({step[1] for step in start["steps"]}, {words[STATE["todo"]]},
                                     "before the installer has said anything, nothing is done or under way")
                    self.assertEqual(start["marks"], [MARK["todo"]] * len(run["listed"]))

    def test_each_line_marks_the_steps_done_under_way_and_still_to_come_as_the_step_advances(self):
        for case in CASES:
            words = _words(case[0])
            runs = self.runs(*case)
            for run in RUNS:
                seen = runs[run["name"]]["seen"]
                self.assertEqual(len(seen), len(run["events"]) + 1)
                keys = list(run["listed"])
                name_of = {words["installer.steps." + key]: key for key in keys}
                under = []
                for event, now in zip(run["events"], seen[1:]):
                    with self.subTest(case=case, run=run["name"], event=event):
                        texts = [step[0] for step in now["steps"]]
                        states = [step[1] for step in now["steps"]]
                        going = [i for i, state in enumerate(states) if state == words[STATE["now"]]]
                        if not under and not going:
                            continue
                        self.assertEqual(len(going), 1, "one step is under way once the installer has begun one")
                        at = going[0]
                        step = name_of[texts[at]]
                        if step not in under:
                            under.append(step)
                        # The step above the bar is the one under way in the list.
                        self.assertEqual(now["label"], words["installer.step." + step])
                        self.assertEqual(states[:at], [words[STATE["done"]]] * at, "every step before it is done")
                        self.assertEqual(states[at + 1:], [words[STATE["todo"]]] * (len(states) - at - 1),
                                         "every step after it is still to come")
                        # Only a step that was under way is done; one passed untaken has left the list.
                        self.assertEqual([name_of[text] for text in texts[:at]], [key for key in under if key != step])
                        self.assertEqual(now["marks"], [MARK["done"]] * at + [MARK["now"]] + [MARK["todo"]] * (len(states) - at - 1))
                        fonts = [found[2] for found in now["steps"]]
                        others = fonts[:at] + fonts[at + 1:]
                        self.assertLessEqual(len(set(others)), 1)
                        self.assertNotIn(fonts[at], others, "the step under way stands in bold")
                with self.subTest(case=case, run=run["name"]):
                    # Run to its last line: every step it took is done but the last, which is under way.
                    self.assertEqual(seen[-1]["steps"][-1][1], words[STATE["now"]])
                    self.assertEqual(under[-1], keys[-1])

    def test_a_progress_line_or_a_line_of_no_step_moves_nothing_in_the_list(self):
        seen = self.runs("en")["first"]["seen"]
        for index, event in enumerate(FIRST):
            said = str(event[1]).strip()
            if said.startswith("progress: ") or said.startswith("(the setup step's") or said == "Codex Auto Resume":
                with self.subTest(event=event):
                    self.assertEqual(seen[index + 1]["steps"], seen[index]["steps"])

    def test_a_step_the_run_passes_without_taking_it_leaves_the_list(self):
        words = _words("en")
        runs = self.runs("en")
        for run in RUNS:
            for key, line in run.get("leaves", {}).items():
                with self.subTest(run=run["name"], step=key):
                    seen = runs[run["name"]]["seen"]
                    at = [event[1] for event in run["events"]].index(line) + 1
                    name = words["installer.steps." + key]
                    self.assertIn(name, [step[0] for step in seen[at - 1]["steps"]], "listed until it is passed")
                    for later in seen[at:]:
                        self.assertNotIn(name, [step[0] for step in later["steps"]], "never marked done: it was not done")
        # A step the run did take stays, done, to the end.
        last = runs["dashboard"]["seen"][-1]["steps"]
        self.assertIn([words["installer.steps.watcher"], words[STATE["done"]]], [step[:2] for step in last])

    @staticmethod
    def _steps(snap):
        return [row for row in snap["rows"] if row["state"] and row["type"] == "WrapLabel"]

    @staticmethod
    def _logs(snap):
        return [row for row in snap["rows"] if row["type"] == "SoftTextArea"]

    @staticmethod
    def _toggles(snap):
        return [row for row in snap["rows"] if row["type"] == "SoftLink"]

    def test_the_progress_page_shows_the_steps_and_the_log_at_once_by_default(self):
        """v0.6.24 final (the owner, 2026-11-19: the log was in the steps' place; it is to be under them, and shown)."""
        for case in CASES:
            words = _words(case[0])
            for run in RUNS:
                with self.subTest(case=case, run=run["name"]):
                    snap = self.runs(*case)[run["name"]]["default"]
                    steps, logs, toggles = self._steps(snap), self._logs(snap), self._toggles(snap)
                    self.assertEqual([row["text"] for row in steps],
                                     [step[0] for step in self.runs(*case)[run["name"]]["seen"][-1]["steps"]],
                                     "the list the run's last line left, on the page with the log")
                    self.assertEqual(len(snap["marks"]), len(steps), "each with its mark")
                    self.assertEqual(len(logs), 1, "the log is shown, without a press")
                    self.assertEqual([row["text"] for row in toggles], [words["installer.log.hide"]],
                                     "its button offers to hide it")
                    log, last = logs[0]["box"], steps[-1]["box"]
                    self.assertGreaterEqual(log[1], last[1] + last[3], "the log is under the steps")
                    self.assertEqual([log[0], log[2]], [0, snap["width"]], "as wide as the card")
                    self.assertLessEqual(log[1] + log[3], snap["height"], "inside the card")
                    # Under them, down to the bottom bar: where the page needs less than the card holds, the log takes the rest.
                    if snap["used"] < snap["height"]:
                        self.assertEqual(log[1] + log[3], snap["height"], "down to the bottom bar")
                    line = min(row["box"][3] for row in steps)
                    self.assertGreaterEqual(log[3], 3 * line, "never less than about four lines (a line is a step row less its air)")

    def test_the_toggle_hides_and_shows_only_the_log_and_the_steps_never_move(self):
        for case in CASES:
            words = _words(case[0])
            for run in RUNS:
                with self.subTest(case=case, run=run["name"]):
                    found = self.runs(*case)[run["name"]]
                    default, hidden, shown = found["default"], found["hidden"], found["shown"]
                    self.assertEqual(self._logs(hidden), [], "hidden, the log is not there")
                    self.assertEqual([row["text"] for row in self._toggles(hidden)], [words["installer.log.show"]])
                    self.assertEqual([row["text"] for row in self._toggles(shown)], [words["installer.log.hide"]],
                                     "and the button offers to hide it again")
                    for other in (hidden, shown):
                        self.assertEqual(self._steps(other), self._steps(default), "the steps stay as they were")
                        self.assertEqual(other["marks"], default["marks"])
                        self.assertEqual([row["box"] for row in self._toggles(other)],
                                         [row["box"] for row in self._toggles(default)], "the toggle stays where it is")
                        self.assertEqual([(row["text"], row["box"]) for row in other["rows"] if row["type"] not in ("SoftTextArea", "SoftLink")],
                                         [(row["text"], row["box"]) for row in default["rows"] if row["type"] not in ("SoftTextArea", "SoftLink")],
                                         "nothing but the log comes and goes")
                    self.assertEqual(self._logs(shown), self._logs(default), "shown again, the log stands where it stood")
                    self.assertEqual(hidden["used"], default["used"], "the page needs as much with the log as without it")

    def test_the_keyboard_goes_steps_then_the_log_then_the_buttons(self):
        """The steps are words; the toggle stands above the log, as on the Finish page, so Tab reaches it and then the log;
        the page's card comes before the window's buttons (tests/test_gui_v0624_focus_visible.py)."""
        for case in CASES:
            for run in RUNS:
                with self.subTest(case=case, run=run["name"]):
                    snap = self.runs(*case)[run["name"]]["default"]
                    self.assertEqual(snap["tabs"], ["SoftLink", "SoftTextArea"])
                    rows = [row["type"] for row in snap["rows"] if row["type"] in ("SoftLink", "SoftTextArea")]
                    self.assertEqual(rows, ["SoftLink", "SoftTextArea"])

    def test_the_log_follows_its_newest_line(self):
        for case in CASES[:len(l10n.LOCALES)]:
            for run in RUNS:
                with self.subTest(case=case, run=run["name"]):
                    found = self.runs(*case)[run["name"]]
                    default = found["default"]
                    self.assertEqual(run["events"][-1][0], "line")
                    self.assertTrue(default["logText"].rstrip().endswith(run["events"][-1][1].strip()), "the newest line is last")
                    self.assertEqual(default["caret"][0], default["caret"][1], "the caret, which scrolls the log, is at the end")
                    shown = found["shown"]
                    self.assertTrue(shown["logText"].rstrip().endswith("a line said while the log is folded away"))
                    self.assertEqual(shown["caret"][0], shown["caret"][1], "a line said while it was folded away is the newest")
        self.assertIn("logArea.Box.ScrollToCaret();", guiscan.member_body("InstallerWindow", "LogToggle"))
        self.assertIn("logArea.Box.AppendText(", guiscan.member_body("InstallerWindow", "Heard"))

    def test_what_a_person_hid_is_not_remembered_between_runs(self):
        window = (ROOT / "gui" / "InstallerWindow.cs").read_text(encoding="utf-8")
        self.assertIn("private bool logShown = true;", window)
        for forbidden in ("Settings", "Registry", "File.", "Properties."):
            self.assertNotIn(forbidden, guiscan.member_body("InstallerWindow", "LogToggle"))

    def test_the_finished_page_keeps_the_log_as_the_run_left_it(self):
        ended = guiscan.member_body("InstallerWindow", "Ended")
        self.assertIn("if (ended != 0) logShown = true;", ended)
        self.assertNotIn("logShown = ended != 0", ended)

    def test_the_list_is_made_only_by_the_installers_own_lines(self):
        """Real progress only (the owner, 2026-10-21): the list moves with `step`, which only a line the installer
        prints (Heard, InstallerProgress.Advance) or the archive's own unpacking (Unpacking) moves - never a timer."""
        listing = guiscan.member_body("InstallerWindow", "ListSteps")
        self.assertNotIn("Timer", listing)
        self.assertIn("InstallerProgress.Listed(flow.Mode, flow.Upgrade, flow.Unpacks, step, under)", listing)
        window = (ROOT / "gui" / "InstallerWindow.cs").read_text(encoding="utf-8")
        self.assertEqual(window.count("ListSteps(true)"), 1)
        self.assertIn("ListSteps(true)", guiscan.member_body("InstallerWindow", "ShowStep"))
        self.assertEqual(sorted(name for name in ("Heard", "Unpacking", "Ended", "Start", "Fit", "ShowPage")
                                if "ShowStep()" in guiscan.member_body("InstallerWindow", name)), ["Heard", "Unpacking"])
        listed = guiscan.member_body("InstallerProgress", "Listed")
        for clock in ("DateTime", "Stopwatch", "Timer", "Environment.TickCount"):
            self.assertNotIn(clock, listed)

    def test_every_listed_step_has_its_words_in_every_catalog(self):
        table = guiscan.type_body("InstallerWords", (ROOT / "gui" / "InstallerFlow.cs").read_text(encoding="utf-8"))
        table = table[table.index("StepNames ="):]
        pairs = re.findall(r'"([a-z_]+)", "([^"]+)"', table[:table.index("};")])
        self.assertEqual({key for run in RUNS for key in run["listed"]}, {key for key, _ in pairs})
        english = l10n.catalog("en")
        for key, text in pairs:
            self.assertEqual(english["installer.steps." + key], text)
        for locale in l10n.LOCALES:
            own = json.loads((l10n.DIRECTORY / ("%s.json" % locale)).read_text(encoding="utf-8"))
            with self.subTest(locale=locale):
                self.assertEqual([key for key, _ in pairs if "installer.steps." + key not in own], [])
                self.assertEqual([key for key in STATE.values() if key not in own], [])

    # ------------------------------------------------------------------ every page

    def test_nothing_is_cut_overlaps_or_leaves_the_card(self):
        for case, snap in self.every():
            with self.subTest(case=case, page=snap["page"]):
                width = snap["width"]
                self.assertLessEqual(snap["used"], snap["height"], "the page's rows end inside the card")
                boxes = []
                for row in snap["rows"]:
                    x, y, w, h = row["box"]
                    self.assertGreaterEqual(x, 0, row["text"][:40])
                    self.assertLessEqual(x + w, width, row["text"][:40])
                    self.assertLessEqual(y + h, snap["height"], row["text"][:40])
                    if row["type"] in ("WrapLabel", "SoftCheck", "SoftCallout"):
                        self.assertLessEqual(row["want"][0], w, row["text"][:40] + ": as wide as its words need")
                        self.assertLessEqual(row["least"], h, row["text"][:40] + ": as tall as its lines need")
                    boxes.append((row["text"][:40], row["box"]))
                for mark in snap["marks"]:
                    x, y, w, h = mark["box"]
                    self.assertGreaterEqual(x, 0)
                    self.assertLessEqual(x + w, width)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(y + h, snap["height"])
                    boxes.append(("a %s mark" % mark["kind"], mark["box"]))
                for i, (one, a) in enumerate(boxes):
                    for other, b in boxes[i + 1:]:
                        overlap = a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
                        self.assertFalse(overlap, "%r %s overlaps %r %s" % (one, a, other, b))

    def test_the_progress_page_with_its_log_cuts_nothing_overlaps_nothing_and_leaves_no_card(self):
        for case in CASES:
            for run in RUNS:
                found = self.runs(*case)[run["name"]]
                for name in ("default", "hidden", "shown"):
                    snap = found[name]
                    with self.subTest(case=case, run=run["name"], snap=name):
                        width = snap["width"]
                        self.assertLessEqual(snap["used"], snap["height"], "the page's rows end inside the card")
                        boxes = []
                        for row in snap["rows"]:
                            x, y, w, h = row["box"]
                            self.assertGreaterEqual(x, 0, row["text"][:40])
                            self.assertLessEqual(x + w, width, row["text"][:40])
                            self.assertLessEqual(y + h, snap["height"], row["text"][:40])
                            if row["type"] in ("WrapLabel", "SoftCheck", "SoftCallout"):
                                self.assertLessEqual(row["want"][0], w, row["text"][:40])
                                self.assertLessEqual(row["least"], h, row["text"][:40])
                            boxes.append((row["text"][:40], row["box"]))
                        for mark in snap["marks"]:
                            boxes.append(("a %s mark" % mark["kind"], mark["box"]))
                        for i, (one, a) in enumerate(boxes):
                            for other, b in boxes[i + 1:]:
                                overlap = a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
                                self.assertFalse(overlap, "%r %s overlaps %r %s" % (one, a, other, b))

    # Option B (the owner's second choice, 2026-11-19): the window stays 600 high for every way, the update's nine steps and
    # the Dashboard's ten included - the step list's rows and the gaps beside it give the room (Arrange). English and Korean
    # are held to it at 100, 150 and 200 %; a language or text size that does not fit after the floors makes the window as tall
    # as its tallest page needs (Fit) and no taller.
    HELD = ("en", "ko")

    def test_at_windows_usual_text_size_the_window_stays_600_by_600_in_every_way_in_english_and_korean_at_every_scaling(self):
        held = [case for case in CASES if case[0] in self.HELD and case[2] == 1.0]
        self.assertEqual(sorted({case[1] for case in held if case[0] == "en"}), [1.0, 1.5, 2.0])
        self.assertEqual(sorted({case[1] for case in held if case[0] == "ko"}), [1.0, 1.5, 2.0])
        for case in held:
            size = int(round(600 * case[1]))
            for snap in self.snaps(*case):
                with self.subTest(case=case, page=snap["page"]):
                    self.assertEqual(snap["client"], [size, size])
            for run in RUNS:
                with self.subTest(case=case, run=run["name"]):
                    self.assertEqual(self.runs(*case)[run["name"]]["default"]["client"], [size, size])

    def test_where_it_does_not_fit_the_window_is_as_tall_as_its_tallest_page_needs_and_never_shorter_than_600(self):
        for case, snap in self.every():
            if case[2] != 1.0:
                continue
            size = int(round(600 * case[1]))
            way = snap["page"].split("/")[0]
            if way.startswith("run:"):
                continue
            with self.subTest(case=case, page=snap["page"]):
                self.assertEqual(snap["client"][0], size)
                self.assertGreaterEqual(snap["client"][1], size)
                if snap["client"][1] != size:
                    needs = [other["used"] for other in self.snaps(*case) if other["page"].split("/")[0] == way]
                    self.assertEqual(max(needs), snap["height"], "as tall as its tallest page needs")

    def test_the_step_list_gives_the_room_evenly_as_little_as_needed_and_never_below_its_floor(self):
        source = (ROOT / "gui" / "InstallerWindow.cs").read_text(encoding="utf-8")
        floor = int(re.search(r"private const int StepRowFloor = (\d+);", source).group(1))
        gap = int(re.search(r"private const int StepGapFloor = (\d+);", source).group(1))
        self.assertEqual([floor, gap], [17, 6])
        for case in CASES:
            scale = case[1]
            pitches = {}
            for run in RUNS:
                with self.subTest(case=case, run=run["name"]):
                    # As the run starts: the whole list (steps the run then passes untaken leave it).
                    snap = self.runs(*case)[run["name"]]["start"]
                    steps = self._steps(snap)
                    tops = [row["box"][1] for row in steps]
                    heights = [row["box"][3] for row in steps]
                    # Rows of one line (the usual) stand at one pitch, whatever the run: the same in each, evenly.
                    single = [i for i, row in enumerate(steps) if row["box"][3] == min(heights)]
                    steps_apart = {tops[i + 1] - tops[i] for i in single if i + 1 in single}
                    self.assertLessEqual(len(steps_apart), 1, "the same pitch in every row")
                    if steps_apart:
                        pitches[run["name"]] = steps_apart.pop()
                        self.assertGreaterEqual(pitches[run["name"]], int(round((floor + 2) * scale)) - 1, "never below the floor")
                    for row in steps:
                        self.assertGreaterEqual(row["box"][3], row["least"])
            # Tightened only where the page needs the room: a run with few steps keeps the pitch it has always had, and the
            # one with the most is the tightest.
            if case[0] == "en" and case[2] == 1.0 and case[1] == 1.0:
                self.assertEqual(pitches["first"], pitches["uninstall"], "the same where nothing needs tightening")
                self.assertLess(pitches["dashboard"], pitches["over"])
                self.assertLess(pitches["over"], pitches["first"])
                self.assertEqual(pitches["first"], 23)
                self.assertEqual(pitches["over"], 21)
                self.assertEqual(pitches["dashboard"], 19)


if __name__ == "__main__":
    unittest.main()
