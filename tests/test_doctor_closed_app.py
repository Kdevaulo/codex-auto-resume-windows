"""v0.6.26 (update resilience, proposal 8): the health check tells a closed ChatGPT app from a broken one.

The installer runs the health check last. It failed whenever the Codex app was simply closed - "not running or not
paired", and "codex.exe : FAIL" where the engine sits only in the app's package - so a real failure hid among those,
and the last word said "Nothing else to do." either way. Now a closed app is said to be no problem, a Run value whose
interpreter or launcher is gone is a failure, and the check's last line names the first failure, which install.ps1
puts in its last word.

Nothing real is asked: the backend, the watcher probe, the source, both registrations and the process list are stubs.
"""
from __future__ import annotations

import contextlib
import io
import logging
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import cli, config, startup  # noqa: E402
from codex_auto_resume.commands import status  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _reset_logging():
    for handler in list(logging.getLogger().handlers) + list(logging.getLogger("codex_auto_resume").handlers):
        handler.close()


class DoctorCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.addCleanup(_reset_logging)
        self.home = Path(temp.name)
        scratch = patch.dict(os.environ, {"LOCALAPPDATA": str(self.home / "no-codex"),
                                          "CODEX_HOME": str(self.home / "codex")})
        scratch.start()
        self.addCleanup(scratch.stop)
        self.launcher = self.home / "watcher-launcher.py"
        self.launcher.write_text("# launcher\n", encoding="utf-8")
        self.interpreter = self.home / "pythonw.exe"
        self.interpreter.write_bytes(b"")

    def doctor(self, *, look="closed", identity=None, backend_error=None, app_runs=False, run_value=None):
        args = cli.build_parser().parse_args(["--home", str(self.home), "--quiet", "doctor"])
        backend = MagicMock()
        backend.codex_exe = "codex.exe"
        backend.engine_version = "0.0.0"
        backend.app_identity.return_value = identity
        backend.app_look = look
        made = {"side_effect": backend_error} if backend_error else {"return_value": backend}
        out = io.StringIO()
        with patch.object(cli.App, "backend", **made), \
             patch.object(cli.App, "engine_moved", return_value=False), \
             patch.object(cli.App, "watcher_running", return_value=False), \
             patch.object(cli.App, "source", return_value=MagicMock()), \
             patch.object(status.compatio, "live_view", return_value=None), \
             patch.object(status, "app_running_now", return_value=app_runs), \
             patch.object(startup, "protocol_value", return_value=None), \
             patch.object(startup, "current_value", return_value=run_value), \
             contextlib.redirect_stdout(out):
            code = cli.cmd_doctor(args)
        return code, out.getvalue()


class ClosedAppTests(DoctorCase):
    def test_a_closed_app_is_no_problem(self):
        code, said = self.doctor(look="closed")
        self.assertEqual(code, status.EXIT_OK, said)
        self.assertIn("ChatGPT app      : " + status.CLOSED_APP, said)
        self.assertNotIn(status.PROBLEM, said)

    def test_an_app_whose_server_is_not_matched_is_the_problem_named_last(self):
        code, said = self.doctor(look="unmatched")
        self.assertEqual(code, status.EXIT_ERROR)
        self.assertEqual(said.splitlines()[-1], status.PROBLEM + "ChatGPT app : " + status.UNMATCHED_APP)

    def test_no_engine_with_the_app_closed_is_no_problem_and_the_other_checks_still_run(self):
        code, said = self.doctor(backend_error=config.ConfigError("no official Codex engine"), app_runs=False)
        self.assertEqual(code, status.EXIT_OK, said)
        self.assertIn("codex.exe        : " + status.CLOSED_ENGINE, said)
        self.assertIn("local history    : readable", said)

    def test_no_engine_with_the_app_running_fails_as_it_did_and_names_it(self):
        code, said = self.doctor(backend_error=config.ConfigError("no official Codex engine"), app_runs=True)
        self.assertEqual(code, status.EXIT_ERROR)
        self.assertIn("codex.exe        : FAIL (no official Codex engine)", said)
        self.assertEqual(said.splitlines()[-1], status.PROBLEM + "codex.exe : FAIL (no official Codex engine)")


class AutostartTests(DoctorCase):
    def value(self, interpreter, launcher):
        return startup.quote_argument(str(interpreter)) + " " + startup.quote_argument(str(launcher)) + " --home x"

    def test_a_run_value_whose_launcher_is_gone_fails(self):
        code, said = self.doctor(run_value=self.value(self.interpreter, self.home / "gone" / "watcher-launcher.py"))
        self.assertEqual(code, status.EXIT_ERROR)
        self.assertIn("autostart        : registered, but its launcher is missing", said)

    def test_a_run_value_whose_interpreter_is_gone_fails(self):
        code, said = self.doctor(run_value=self.value(self.home / "gone" / "pythonw.exe", self.launcher))
        self.assertIn("its interpreter is missing", said)
        self.assertEqual(code, status.EXIT_ERROR)

    def test_a_run_value_that_starts_something_and_none_at_all_are_both_fine(self):
        self.assertEqual(self.doctor(run_value=self.value(self.interpreter, self.launcher))[0], status.EXIT_OK)
        code, said = self.doctor(run_value=None)
        self.assertEqual(code, status.EXIT_OK)
        self.assertIn("autostart        : not registered", said)


class InstallerTests(unittest.TestCase):
    def test_the_last_word_repeats_the_health_checks_problem_line(self):
        script = (ROOT / "build" / "install" / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("'%s*'" % status.PROBLEM, script)
        self.assertIn("'%s'.Length" % status.PROBLEM, script)
        self.assertIn("The health check found a problem: ' + $doctorProblem", script)
        # Both successes that said "Nothing else to do." now say what the check found, where it found something.
        self.assertEqual(script.count("Write-Host $nothingElse"), 2)
        self.assertEqual(script.count("Nothing else to do.'"), 1)


if __name__ == "__main__":
    unittest.main()
