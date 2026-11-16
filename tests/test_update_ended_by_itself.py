"""An update starts again a watcher that ended unexpectedly in this sign-in, and keeps every other stopped (v0.6.24).

The v0.6.16 rule left every watcher that was not running before an update stopped (setup --watcher-was-stopped). The
owner (2026-11-14) wants "stopped by the person" told apart from "ended by itself", and an end with a restart, a
shutdown or a sign-out is expected, not a fault: it keeps the v0.6.16 rule. The heartbeat tells them apart (store
watcher_status): every tick writes RUNNING, with the sign-in and the start of Windows it runs in; a watcher whose stop
event is signalled - Stop watcher on the Dashboard or in the Codex panel, the tray's Stop, `codex-auto-resume stop` -
writes CLEAN as it exits, and the memory guard writes MEMORY_GUARD. A watcher ended from outside writes nothing:
measured on this product's PC (2026-11-12/13), a fast-startup shutdown logged the session off and ended the watcher
with no stop line. control/watcher.how_it_ended reads RUNNING left in this sign-in and start as UNEXPECTED, and one
from an earlier sign-in or start as nothing - one rule for the Dashboard and for setup.

Held here:

* EndedByItselfTests - plugin_setup.ended_by_itself over a real store in a scratch home, this sign-in and start of
  Windows given: RUNNING and MEMORY_GUARD left in them are ends by itself; the same from an earlier start of Windows
  or another sign-in (a restart, a shutdown, a sign-out), CLEAN, no heartbeat and no state are not.
* SetupStartsAgainTests - setup --keep-state --watcher-was-stopped (test_plugin.BridgeTests' guards: no registry,
  no Start menu, no watcher): a watcher that ended by itself is started and said to be started again, with
  EXIT_STARTED_AGAIN for a caller that asks and EXIT_OK for every other; one that was stopped is left stopped.
* InstallerWordTests - install.ps1's setup call and last word, lifted verbatim, setup stubbed: 5 is a success, the
  variable is set for that one call alone, and the last word says the watcher had ended by itself and was started
  again - never with the line the Finish page's left-stopped box looks for.
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_plugin
from test_installer import block
import test_installer_left_stopped as left_stopped  # the module, not its TestCase: a TestCase named here is
from test_installer_left_stopped import INSTALL, left_stopped_line  # discovered again under this module's name
from test_installer_window import POWERSHELL

from codex_auto_resume import config, l10n
from codex_auto_resume.domain.vocabulary import WatcherEnd
from codex_auto_resume.store import Store
from codex_auto_resume.win import ownprocess

NOW = 1_794_600_000.0
MONTH = 30 * 86400.0
# This sign-in and this start of Windows, as ownprocess reads them, given to every test.
SIGN_IN = "00000000000a1b2c"
BOOTED = NOW - 7200.0


def this_session(case: unittest.TestCase) -> None:
    for name, value in (("sign_in", SIGN_IN), ("booted_at", BOOTED)):
        guard = patch.object(ownprocess, name, return_value=value)
        guard.start()
        case.addCleanup(guard.stop)


def beat(home: Path, end=None, *, at=NOW, sign_in=SIGN_IN, booted_at=BOOTED) -> None:
    """A heartbeat in `home`'s state, as a watcher's tick writes it - in this sign-in and start of Windows unless said
    otherwise - and how it ended where `end` says."""
    store = Store(config.Paths(home).state_dir)
    try:
        store.heartbeat(at, pid=1, session_id="s", started_at=at - 60, ok=True, engine_state="verified",
                        code_version="0.6.23", sign_in=sign_in, booted_at=booted_at)
        if end is not None:
            assert store.watcher_ended(at + 1, end)
    finally:
        store.close()


class EndedByItselfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.bridge = test_plugin._load("plugin_setup_under_test", test_plugin.ROOT / "scripts" / "plugin_setup.py")
        this_session(self)

    def test_no_state_is_no_end_by_itself(self):
        self.assertFalse(self.bridge.ended_by_itself(self.home))

    def test_a_state_with_no_heartbeat_is_none(self):
        Store(config.Paths(self.home).state_dir).close()
        self.assertFalse(self.bridge.ended_by_itself(self.home))

    def test_a_heartbeat_left_saying_running_in_this_sign_in_is_an_end_by_itself(self):
        beat(self.home)
        self.assertTrue(self.bridge.ended_by_itself(self.home), "a crash, an end from outside: no word written")

    def test_the_memory_guards_end_in_this_sign_in_is_an_end_by_itself(self):
        beat(self.home, WatcherEnd.MEMORY_GUARD)
        self.assertTrue(self.bridge.ended_by_itself(self.home))

    def test_an_end_with_a_restart_a_shutdown_or_a_sign_out_is_not(self):
        """The owner, 2026-11-14: a restart is meant to end it. Its heartbeat is from an earlier start of Windows (a
        restart, a shutdown, fast startup's too) or another sign-in (a sign-out)."""
        for end in (None, WatcherEnd.MEMORY_GUARD):
            for case in (dict(at=NOW - MONTH, booted_at=NOW - MONTH - 3600), dict(booted_at=BOOTED - 86400),
                         dict(sign_in="00000000000f0f0f"), dict(sign_in=None), dict(booted_at=None)):
                with self.subTest(end=end, case=case):
                    beat(self.home, end, **case)
                    self.assertFalse(self.bridge.ended_by_itself(self.home))

    def test_a_stop_is_not(self):
        beat(self.home, WatcherEnd.CLEAN)
        self.assertFalse(self.bridge.ended_by_itself(self.home), "Stop watcher, the tray's Stop, the command line")

    def test_a_state_that_cannot_be_read_is_none(self):
        state = config.Paths(self.home).state_dir
        Path(state).mkdir(parents=True)
        (Path(state) / "state.sqlite").write_bytes(b"not a database" * 100)
        self.assertFalse(self.bridge.ended_by_itself(self.home))


class SetupStartsAgainTests(unittest.TestCase):
    """plugin_setup.py's update over a watcher that was not running, by how it ended and who asks."""

    setUp = test_plugin.BridgeTests.setUp
    _close_log_handlers = staticmethod(test_plugin.BridgeTests._close_log_handlers)
    pretend_installed = test_plugin.BridgeTests.pretend_installed
    started_after_update = test_plugin.BridgeTests.started_after_update

    ARGV = ["setup", "--keep-state", "--watcher-was-stopped"]

    def run_setup(self, end, asked, **heartbeat):
        this_session(self)
        self.pretend_installed()
        if end != "none":
            beat(self.home, end, **heartbeat)
        names = (self.bridge.ENV_SAYS_STARTED_AGAIN, self.bridge.ENV_SAYS_LEFT_STOPPED)
        with patch.dict(os.environ, {name: "1" for name in names} if asked else {}):
            if not asked:
                for name in names:
                    os.environ.pop(name, None)
            with patch.object(l10n, "current", return_value="en"):
                return self.started_after_update(self.ARGV, None)

    def test_a_watcher_that_ended_by_itself_is_started_again_and_said_so(self):
        for end in (None, WatcherEnd.MEMORY_GUARD):
            with self.subTest(end=end):
                code, started, text = self.run_setup(end, asked=True)
                self.assertTrue(started)
                self.assertEqual(code, self.bridge.EXIT_STARTED_AGAIN)
                self.assertIn(l10n.message("setup_started_again"), text)
                self.assertNotIn(l10n.message("setup_left_stopped"), text)

    def test_a_caller_that_does_not_ask_hears_success_as_before(self):
        code, started, _text = self.run_setup(None, asked=False)
        self.assertTrue(started)
        self.assertEqual(code, self.bridge.EXIT_OK, "an older install.ps1 and the bootstrap read 0 and 2 only")

    def test_a_watcher_that_ended_with_an_earlier_start_of_windows_stays_stopped(self):
        """The review's case: last month's heartbeat, from an earlier boot, the sign-in start off."""
        code, started, text = self.run_setup(None, asked=True, at=NOW - MONTH, booted_at=NOW - MONTH - 3600)
        self.assertFalse(started)
        self.assertEqual(code, self.bridge.EXIT_LEFT_STOPPED)
        self.assertIn(l10n.message("setup_left_stopped"), text)
        self.assertNotIn(l10n.message("setup_started_again"), text)

    def test_a_watcher_the_person_stopped_stays_stopped(self):
        for end in (WatcherEnd.CLEAN, "none"):
            with self.subTest(end=end):
                code, started, text = self.run_setup(end, asked=True)
                self.assertFalse(started)
                self.assertEqual(code, self.bridge.EXIT_LEFT_STOPPED)
                self.assertIn(l10n.message("setup_left_stopped"), text)

    def test_one_meaning_per_code(self):
        codes = (self.bridge.EXIT_OK, self.bridge.EXIT_ERROR, self.bridge.EXIT_UNCONFIRMED,
                 self.bridge.EXIT_DESKTOP_TAKEN, self.bridge.EXIT_LEFT_STOPPED, self.bridge.EXIT_STARTED_AGAIN)
        self.assertEqual(len(set(codes)), len(codes))

    def test_a_watcher_started_again_but_not_seen_is_not_confirmed(self):
        this_session(self)
        self.pretend_installed()
        beat(self.home)
        with patch.dict(os.environ, {self.bridge.ENV_SAYS_STARTED_AGAIN: "1"}), \
                patch.object(self.bridge, "looked_again", return_value="not-confirmed"):
            code, started, _text = self.started_after_update(self.ARGV, None)
        self.assertTrue(started)
        self.assertEqual(code, self.bridge.EXIT_UNCONFIRMED)


@unittest.skipUnless(POWERSHELL.is_file(), "Windows PowerShell")
class InstallerWordTests(unittest.TestCase):
    run_script = left_stopped.LastWordTests.run_script
    CALL = left_stopped.LastWordTests.CALL
    WORD = left_stopped.LastWordTests.WORD

    def call(self, setup_code):
        text = INSTALL.read_text(encoding="utf-8")
        stubs = ("function Invoke-Setup { param([string[]]$Arguments)\n"
                 "    $script:heard = [string]$env:CODEX_AUTO_RESUME_SETUP_SAYS_STARTED_AGAIN\n"
                 "    $global:LASTEXITCODE = %d; return %d }\n" % (setup_code, setup_code))
        script = ("$setupArgs = @('setup', '--keep-state', '--watcher-was-stopped')\n$watcherWasRunning = $false\n"
                  + stubs + block(text, *self.CALL)
                  + "Write-Host ('AGAIN ' + $watcherStartedAgain + ' LEFT ' + $watcherLeftStopped + ' CODE ' + $code)\n"
                  + "Write-Host ('HEARD ' + $script:heard + ' AFTER '"
                    " + [string]$env:CODEX_AUTO_RESUME_SETUP_SAYS_STARTED_AGAIN + '.')\n")
        return self.run_script(script)

    def test_the_call_asks_for_the_answer_and_reads_it_as_a_success(self):
        done = self.call(5)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("Setup did not complete", done.stdout)
        self.assertIn("AGAIN True LEFT False CODE 0", done.stdout)
        self.assertIn("HEARD 1 AFTER .", done.stdout, "set for setup's one call, and only for it")

    def last_word(self, again, left=False, repair=False):
        text = INSTALL.read_text(encoding="utf-8")
        stubs = ("function Invoke-Setup { param([string[]]$Arguments)\n"
                 "    $global:LASTEXITCODE = 0; return 0 }\n"
                 "function Open-ClosedDashboard { param([switch]$Updated) }\n")
        flag = lambda value: "$true" if value else "$false"   # noqa: E731
        script = ("$script:Failed = $false\n$upgrade = $true\n$repair = %s\n$watcherUnconfirmed = $false\n"
                  "$previousWatcherStillRunning = $false\n$watcherLeftStopped = %s\n$watcherStartedAgain = %s\n"
                  % (flag(repair), flag(left), flag(again)) + stubs + block(text, *self.WORD))
        done = self.run_script(script)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return done.stdout

    def test_a_watcher_started_again_is_the_last_word(self):
        said = self.last_word(True)
        self.assertIn("Updated. Your settings and pending recoveries were kept.", said)
        self.assertIn("The watcher had ended unexpectedly before this update (in this sign-in, not by a stop or a "
                      "restart), so it was started again and is running.", said)
        self.assertNotIn(left_stopped_line(), said, "not the Finish page's left-stopped box")
        self.assertIn("this repair", self.last_word(True, repair=True))

    def test_a_watcher_left_stopped_says_why(self):
        said = self.last_word(False, left=True)
        self.assertIn("The watcher was not running before this update, so it was left stopped", said)
        self.assertIn("It had been stopped, or had ended with a restart, a shutdown or a sign-out, or had never "
                      "started.", said)
        self.assertNotIn("started again", said)

    def test_a_watcher_that_ran_before_ends_as_before(self):
        said = self.last_word(False)
        self.assertIn("Recommended settings are already on. Nothing else to do.", said)
        self.assertNotIn("ended unexpectedly", said)


if __name__ == "__main__":
    unittest.main()
