"""v0.6.24 final: the health check agrees with the watcher about an app serving from another official engine.

The owner's re-check 2 (live acceptance): every install and repair ended "[!] The health check reported a problem",
the doctor's line "running, but its Codex server could not be matched". The Codex app ran its server from its own
package (signed by OpenAI, #58) while discovery had found the build in bin first; the watcher looks for its engine
again in that case (App.engine_moved) and pairs with the app's, but the doctor judged the first pairing alone.

Here the doctor, the status, the App, discovery and the pairing are real, in a scratch home; the process list, the
identities the pairing confirms, Windows' signature answer and the engines' own answers are stubs
(tests/test_signed_engine.py's SignedEngineCase), and nothing of this machine's registrations is read.
"""
from __future__ import annotations

import contextlib
import io
import logging
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from test_engine_moved import key  # noqa: E402
from test_signed_engine import SignedEngineCase  # noqa: E402
from codex_auto_resume import cli, startup  # noqa: E402

PROBLEM = "The health check reported a problem"
UNMATCHED = "running, but its Codex server could not be matched"
# What both commands add for it (commands/status.py ELSEWHERE_SHORT), spelt out so a guard here holds without it.
ELSEWHERE = "its server runs from another official Codex engine, which the watcher takes up"
# Windows PowerShell runs the installer's block; every other process this module would start is the stub engines'.
REAL_RUN = subprocess.run


class DoctorCase(SignedEngineCase):
    def setUp(self):
        super().setUp()
        for stub in (patch.object(startup, "current_value", return_value=None),
                     patch.object(startup, "protocol_value", return_value=None)):
            stub.start()
            self.addCleanup(stub.stop)
        self.addCleanup(self._reset_logging)

    @staticmethod
    def _reset_logging():
        logger = logging.getLogger("codex_auto_resume")
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    def cli(self, command, *more):
        """The command as setup runs it: a process of its own, which has found nothing yet."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--home", str(self.fixture.paths.home), "--quiet",
                             "--codex-home", str(self.fixture.home.root), *more, command])
        return code, out.getvalue()

    @staticmethod
    def app_line(out):
        lines = out.splitlines()
        first = next(n for n, text in enumerate(lines) if text.startswith("ChatGPT app"))
        return "\n".join(lines[first:first + 2])


class AnotherOfficialEngineTests(DoctorCase):
    def test_the_app_serving_from_its_signed_package_is_no_problem(self):
        """The reverse-applied doctor says "could not be matched" here and exits 1."""
        self.serve(self.package)
        code, out = self.cli("doctor")
        said = self.app_line(out)
        self.assertNotIn(UNMATCHED, out)
        self.assertIn("ChatGPT app      : main pid 10, codex app-server pid 20", said)
        self.assertIn(ELSEWHERE, said)
        self.assertIn(str(self.package), said, "the engine the watcher takes up is named")
        self.assertIn("codex.exe        : %s" % self.first.codex_exe, out, "the engine found first is still said first")
        self.assertEqual(code, 0, out)

    def test_another_official_build_in_bin_is_found_by_discovery_itself(self):
        """Two builds in bin that pass: discovery already drives the one the app runs, so there is nothing to note."""
        other = self.other_build()
        self.serve(other)
        code, out = self.cli("doctor")
        self.assertIn("codex.exe        : %s" % other, out)
        self.assertIn("ChatGPT app      : main pid 10, codex app-server pid 20\n", out)
        self.assertNotIn(ELSEWHERE, out)
        self.assertEqual(code, 0, out)

    def test_status_says_the_same(self):
        self.serve(self.package)
        _code, out = self.cli("status")
        line = self.app_line(out).splitlines()[0]
        self.assertIn("running (pid 10, codex server pid 20; %s)" % ELSEWHERE, line)

    def test_an_app_serving_from_the_engine_found_says_what_it_always_said(self):
        self.serve(self.first.codex_exe)
        code, out = self.cli("doctor")
        self.assertIn("ChatGPT app      : main pid 10, codex app-server pid 20\n", out)
        self.assertNotIn(ELSEWHERE, out)
        self.assertEqual(code, 0, out)

    def other_build(self):
        other = self.fixture.exe.parent.parent / "fedcba9876543210" / "codex.exe"
        other.parent.mkdir()
        other.write_bytes(b"MZ-second-build")
        return other.resolve()


class StillAProblemTests(DoctorCase):
    def test_a_server_not_signed_by_openai_is_still_reported(self):
        for refusal in ("unsigned", "signature_invalid", "signature_unreadable", "engine_unreadable"):
            self.refused[key(self.package)] = refusal
            self.signed.clear()
            with self.subTest(refusal):
                from codex_auto_resume.codex import pairing
                pairing._OFFICIAL.clear()
                self.serve(self.package)
                code, out = self.cli("doctor")
                self.assertIn("ChatGPT app      : " + UNMATCHED, out)
                self.assertNotIn(ELSEWHERE, out)
                self.assertEqual(code, 1, out)

    def test_a_signed_server_that_fails_its_engine_checks_is_still_reported(self):
        self.codex.failing.add(key(self.package))
        self.serve(self.package)
        code, out = self.cli("doctor")
        self.assertIn("ChatGPT app      : " + UNMATCHED, out)
        self.assertEqual(code, 1, out)

    def test_a_named_engine_is_never_second_guessed(self):
        self.serve(self.package)
        code, out = self.cli("doctor", "--codex-exe", str(self.first.codex_exe))
        self.assertIn("ChatGPT app      : " + UNMATCHED, out)
        self.assertNotIn(ELSEWHERE, out)
        self.assertEqual(code, 1, out)


class SetupsLastWordTests(DoctorCase):
    """install.ps1's closing block, lifted from the health check to the last word, with its setup answering the
    doctor's exit code from the doctor just run here."""

    def last_words(self):
        from test_installer import VOICE, block
        from test_setup_words import INSTALL, RepairIsToldFromUpdateTests, run_powershell
        code, out = self.cli("doctor")
        stubs = ("function Invoke-Setup { param([string[]]$Arguments)\n"
                 "    $code = if ($Arguments[0] -eq 'doctor') { %d } else { 0 }\n"
                 "    $global:LASTEXITCODE = $code; return $code }\n" % code
                 + "function Open-ClosedDashboard { param([switch]$Updated) }\n")
        script = ("$script:Failed = $false\n$upgrade = $true\n$repair = $true\n$watcherUnconfirmed = $false\n"
                  "$previousWatcherStillRunning = $false\n"
                  + block(INSTALL.read_text(encoding="utf-8"), RepairIsToldFromUpdateTests.START,
                          RepairIsToldFromUpdateTests.END))
        with patch.object(subprocess, "run", REAL_RUN):
            return run_powershell(VOICE + stubs + script), out

    def test_the_app_s_own_official_engine_ends_on_the_ok_line(self):
        """The reverse-applied doctor puts the warning above the last word here."""
        self.serve(self.package)
        said, out = self.last_words()
        self.assertNotIn(PROBLEM, said, out)
        lines = [line for line in said.splitlines() if line.strip()]
        self.assertEqual(lines[1:3], ["Repaired. Your settings and pending recoveries were kept.",
                                      "Recommended settings are already on. Nothing else to do."], said)

    def test_an_unofficial_one_still_warns(self):
        self.refused[key(self.package)] = "unsigned"
        self.signed.clear()
        self.serve(self.package)
        said, _out = self.last_words()
        self.assertIn("[!]  " + PROBLEM, said)


if __name__ == "__main__":
    unittest.main()
