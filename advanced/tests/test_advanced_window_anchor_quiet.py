"""The window anchor's request starts none of the person's own programs (v0.6.24, the owner's choice of 2026-11-15): right
after `exec`, `-c notify=[] --disable hooks --disable plugins --disable apps` and - where the Codex home's config.toml
declares MCP servers - ONE `-c mcp_servers={"<name>"={enabled=false},...}`, as MANCHOR measured it again on codex-cli
0.167.0-alpha.4.1 (plans/v0624-measure-2-result.md, T1-T3). Where Codex refuses that switch before any thread starts, the
request is sent once more as before, and the watcher's log says the person's programs ran for it.

Every request is a stub process and every home a temporary folder: no test starts codex.exe or reads a real Codex home.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;tests" python -m unittest test_advanced_window_anchor_quiet
"""
from __future__ import annotations

import logging
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_advanced_window_anchor import PRINTED, AnchorCase  # noqa: E402
from codex_auto_resume.codex.transport import Backend  # noqa: E402
from codex_auto_resume.logbook import LOGGER_NAME  # noqa: E402
from codex_auto_resume_advanced.engine import anchor  # noqa: E402

EXE = Path("C:/fake/codex.exe")
QUIET = ["-c", "notify=[]", "--disable", "hooks", "--disable", "plugins", "--disable", "apps"]
REST = ["--skip-git-repo-check", "--ephemeral", "--json", "-s", "read-only", "-c", 'model_reasoning_effort="low"',
        "Reply with OK"]
TWO_SERVERS = '''model = "gpt-example"
notify = ["notifier.exe", "turn-ended"]

[mcp_servers."docs.example"]
command = "node"
args = ["server.js"]

[mcp_servers.'say"hi']
url = "https://mcp.example.invalid/sse"
'''
INVALID_TRANSPORT = b"Error loading config.toml: invalid transport in `mcp_servers.example`\n"
UNKNOWN_FEATURE = b"Error: Unknown feature flag: hooks\n"


class ArgvTests(unittest.TestCase):
    """The exact list for each kind of config.toml, read from the Codex home the request uses (Backend._environment)."""

    def setUp(self):
        made = tempfile.TemporaryDirectory(prefix="car-anchor-quiet-")
        self.addCleanup(made.cleanup)
        self.home = Path(made.name) / "codex"
        self.home.mkdir()
        self.backend = Backend(self.home, EXE)

    def config(self, text):
        (self.home / "config.toml").write_text(text, encoding="utf-8")

    def after_prefix(self, plain=False):
        argv = anchor.argv_for(self.backend, plain)
        self.assertEqual(argv[:len(self.backend._argv())], self.backend._argv(), "the C10 prefix first, as before")
        return argv[len(self.backend._argv()):]

    def test_a_no_config_toml_gives_the_switch_and_no_servers_argument(self):
        """Fails with QUIET_ARGUMENTS left out of argv_for."""
        self.assertEqual(self.after_prefix(), ["exec", *QUIET, *REST])

    def test_b_two_servers_one_with_a_dot_one_with_a_quote_are_one_inline_table(self):
        """Fails with servers_off left out, or with the dotted-path form (a name with a dot is then two keys)."""
        self.config(TWO_SERVERS)
        expected = ["exec", *QUIET, "-c", 'mcp_servers={"docs.example"={enabled=false},"say\\"hi"={enabled=false}}',
                    *REST]
        self.assertEqual(self.after_prefix(), expected)
        self.assertEqual(tomllib.loads(expected[len(QUIET) + 2]),
                         {"mcp_servers": {"docs.example": {"enabled": False}, 'say"hi': {"enabled": False}}})

    def test_b_every_name_parses_back_to_itself(self):
        """json.dumps quotes a name as a TOML basic string; DEL, which JSON leaves bare, is escaped too."""
        names = ("plain", "a.b.c", 'q"uote', "back\\slash", "tab\there", "del\x7fhere", "\uc11c\ubc84", "emoji\U0001f600",
                 "")
        value = anchor.servers_off(names)
        self.assertEqual(tomllib.loads(value), {"mcp_servers": {name: {"enabled": False} for name in names}})
        self.assertIsNone(anchor.servers_off(()))

    def test_c_a_table_under_mcp_servers_with_no_command_or_url_is_left_out(self):
        self.config('[mcp_servers.real]\ncommand = "node"\n\n[mcp_servers.settings_only]\nstartup_timeout_sec = 5\n'
                    '[mcp_servers.nested.inner]\ncommand = "x"\n')
        self.assertEqual(self.after_prefix(), ["exec", *QUIET, "-c", 'mcp_servers={"real"={enabled=false}}', *REST])
        self.config("[mcp_servers.settings_only]\nenabled = true\n")
        self.assertEqual(self.after_prefix(), ["exec", *QUIET, *REST], "no server declared: no mcp_servers argument")
        self.config("mcp_servers = 3\n")
        self.assertEqual(self.after_prefix(), ["exec", *QUIET, *REST])

    def test_d_an_unparseable_config_toml_gives_no_servers_argument(self):
        self.config('[mcp_servers.real]\ncommand = "node"\nthis is not toml = = =\n')
        self.assertEqual(self.after_prefix(), ["exec", *QUIET, *REST])
        (self.home / "config.toml").write_bytes(b"\xff\xfe\x00[mcp_servers.x]")
        self.assertEqual(self.after_prefix(), ["exec", *QUIET, *REST])

    def test_plain_is_the_argv_before_the_switch(self):
        self.config(TWO_SERVERS)
        self.assertEqual(self.after_prefix(plain=True), ["exec", *REST])
        self.assertEqual(list(anchor.EXEC_ARGUMENTS), ["exec", *REST])

    def test_the_home_is_the_one_backend_environment_gives(self):
        """The names come from the CODEX_HOME the request runs with, never another home."""
        other = self.home.parent / "other"
        other.mkdir()
        (other / "config.toml").write_text(TWO_SERVERS, encoding="utf-8")
        self.assertEqual(self.after_prefix(), ["exec", *QUIET, *REST])
        self.assertEqual(Path(self.backend._environment()["CODEX_HOME"]), self.home.resolve())


class RefusedTests(unittest.TestCase):
    """What finish_request answers of stderr: whether the switch was refused before `thread.started` - nothing of it kept."""

    def answered(self, code, printed, errors):
        class Process:
            returncode = code

            def communicate(self, timeout=None):
                return printed, errors
        return anchor.finish_request(Process())

    def test_each_refusal_before_thread_started_is_refused(self):
        for errors in (INVALID_TRANSPORT, UNKNOWN_FEATURE):
            with self.subTest(errors=errors):
                answered = self.answered(1, b"", errors)
                self.assertIs(answered["refused"], True)
                self.assertEqual(set(answered), {"end", "code", "input", "cached", "output", "refused"})

    def test_after_thread_started_on_another_error_or_exit_zero_it_is_not(self):
        self.assertIs(self.answered(1, b'{"type":"thread.started","thread_id":"x"}\n', INVALID_TRANSPORT)["refused"], False)
        self.assertIs(self.answered(1, b"", b"Error: something else\n")["refused"], False)
        self.assertIs(self.answered(1, b"", None)["refused"], False)
        self.assertIs(self.answered(0, PRINTED, UNKNOWN_FEATURE)["refused"], False)


class Refusing:
    """The World's processes, each answering the next of `outcomes`: (exit code, what it printed, its stderr)."""

    def __init__(self, world, outcomes):
        self.world, self.outcomes = world, list(outcomes)

    def __call__(self, argv, **options):
        world, outcome = self.world, self.outcomes.pop(0) if self.outcomes else (0, PRINTED, b"")

        class Process:
            returncode = None
            killed = False

            def communicate(self, timeout=None):
                code, printed, errors = outcome
                if code == 0:
                    world.running_until = world.now() + anchor.WINDOW_SECONDS
                self.returncode = code
                return printed, errors

            def kill(self):
                self.killed = True
        made = Process()
        world.started.append((argv, options, made))
        return made


class FallbackCase(AnchorCase):
    """A Codex home whose config.toml declares two servers, and processes that answer what each test says."""

    def setUp(self):
        super().setUp()
        self.codex_home = self.home / "codex"
        self.codex_home.mkdir(parents=True, exist_ok=True)
        (self.codex_home / "config.toml").write_text(TWO_SERVERS, encoding="utf-8")

    def refusing(self, *outcomes):
        from unittest.mock import patch
        refusing = Refusing(self.world, outcomes)
        patched = patch.object(subprocess, "Popen", refusing)
        patched.start()
        self.addCleanup(patched.stop)

    def run_once(self):
        """One occasion run through; what each request was sent with after the C10 prefix."""
        self.on(anchor_at_1=anchor.encode_time(7, 0), anchor_after_reset=2)
        self.run_through(10)
        return [argv[len(Backend(self.codex_home, EXE)._argv()):] for argv, _options, _process in self.world.started]


class FallbackTests(FallbackCase):
    """The switch refused before any thread started: the request sent once more as before - once, and only then."""

    def resent(self, errors):
        """Fails with `_again` taken out: the refused request ends as failed and the window is not started."""
        self.refusing((1, b"", errors), (0, PRINTED, b""))
        sent = self.run_once()
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0], ["exec", *QUIET, "-c",
                                   'mcp_servers={"docs.example"={enabled=false},"say\\"hi"={enabled=false}}', *REST])
        self.assertEqual(sent[1], ["exec", *REST])
        self.assertEqual(self.codes(), ["anchor.started", "anchor.fixed"])
        warned = [line for line in self.lines if "warning" in line]
        self.assertEqual(len(warned), 1)
        self.assertIn("MCP servers, hooks, plugins, apps and notify", warned[0])
        self.assertIn("they ran for this request", warned[0])

    def test_an_invalid_transport_sends_it_once_more_plain_and_the_log_says_the_programs_ran(self):
        self.resent(INVALID_TRANSPORT)

    def test_an_unknown_feature_flag_sends_it_once_more_plain_and_the_log_says_the_programs_ran(self):
        self.resent(UNKNOWN_FEATURE)

    def test_a_plain_request_refused_too_is_never_sent_a_third_time(self):
        self.refusing((1, b"", INVALID_TRANSPORT), (1, b"", INVALID_TRANSPORT), (0, PRINTED, b""))
        sent = self.run_once()
        self.assertEqual(len(sent), 2, "never a third request")
        self.assertEqual(self.codes(), ["anchor.started", "anchor.failed"])

    def not_resent(self, outcome):
        self.refusing(outcome, (0, PRINTED, b""))
        self.assertEqual(len(self.run_once()), 1)
        self.assertEqual(self.codes(), ["anchor.started", "anchor.failed"])
        self.assertFalse([line for line in self.lines if "warning" in line])

    def test_no_fallback_after_thread_started(self):
        self.not_resent((1, b'{"type":"thread.started","thread_id":"00000000-0000-7000-8000-00000000abcd"}\n',
                         INVALID_TRANSPORT))

    def test_no_fallback_on_another_error(self):
        self.not_resent((1, b"", b"Error: the network is down\n"))

    def test_no_fallback_on_an_exit_with_nothing_said(self):
        self.not_resent((1, b"", b""))

    def test_paused_at_the_second_send_sends_nothing_more(self):
        """The second send is inside core's errand guard: refused there, the occasion ends as the refused request did."""
        self.refusing((1, b"", UNKNOWN_FEATURE), (0, PRINTED, b""))
        self.on(anchor_at_1=anchor.encode_time(7, 0), anchor_after_reset=2)
        for _look in range(10):
            if len(self.world.started) == 1:
                self.permitted = False
            self.look(anchor.STEADY_GAP)
        self.assertEqual(len(self.world.started), 1)
        self.assertEqual(self.codes(), ["anchor.started", "anchor.failed"])


class NamesStayInMemoryTests(FallbackCase):
    """No name of a server reaches the watcher's log, its own lines, or any file it writes."""

    def test_nothing_of_the_names_reaches_any_log_or_file(self):
        """Fails with a name put in a log line (proved by adding one to argv_for)."""
        records = []

        class Keep(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())
        # On the watcher's own logger, whatever an earlier test left: logbook.setup_logging sets propagate False, so a
        # handler on the root alone hears nothing after a module that set the logbook up has run.
        handler, root = Keep(level=logging.DEBUG), logging.getLogger()
        logger = logging.getLogger(LOGGER_NAME)
        before = (root.level, logger.level, logger.disabled, logging.root.manager.disable)
        for target in (logger, root):
            target.addHandler(handler)
            self.addCleanup(target.removeHandler, handler)
        root.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logger.disabled = False
        logging.disable(logging.NOTSET)
        self.addCleanup(root.setLevel, before[0])
        self.addCleanup(logger.setLevel, before[1])
        self.addCleanup(setattr, logger, "disabled", before[2])
        self.addCleanup(logging.disable, before[3])
        self.code._log = anchor._log_line
        self.refusing((1, b"", INVALID_TRANSPORT), (0, PRINTED, b""))
        sent = self.run_once()
        self.assertEqual(len(sent), 2)
        self.assertTrue(any("warning" in line for line in records), "the watcher's log heard the warning")
        for name in ("docs.example", 'say"hi', 'say\\"hi'):
            self.assertFalse([line for line in records if name in line], name)
        found = [path for path in self.home.rglob("*") if path.is_file() and path.name != "config.toml"
                 and (b"docs.example" in path.read_bytes() or b'say"hi' in path.read_bytes())]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
