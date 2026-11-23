"""v0.6.26 third round A4: window_anchor reads a config.toml saved with a byte-order mark as Codex's own reader would,
and says in the watcher's log when it cannot read one at all.

`declared_servers` returned () on any failure, so a config.toml saved by Notepad as "UTF-8 with BOM" - or any file
Python's tomllib refuses - named no server off, and the person's MCP servers started for the request with nothing said.

Every request is a stub process and every home a temporary folder: no test starts codex.exe or reads a real Codex home.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_window_anchor_config_read
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume.codex.transport import Backend  # noqa: E402
from codex_auto_resume_advanced.engine import anchor  # noqa: E402
from test_advanced_window_anchor_quiet import QUIET, REST, TWO_SERVERS, FallbackCase  # noqa: E402

EXE = Path("C:/fake/codex.exe")
BOM = b"\xef\xbb\xbf"
OFF = 'mcp_servers={"docs.example"={enabled=false},"say\\"hi"={enabled=false}}'


class ReadTests(unittest.TestCase):
    def setUp(self):
        made = tempfile.TemporaryDirectory(prefix="car-anchor-config-")
        self.addCleanup(made.cleanup)
        self.home = Path(made.name)

    def write(self, data: bytes):
        (self.home / "config.toml").write_bytes(data)

    def test_a_byte_order_mark_is_read_past(self):
        """Fails with the plain tomllib.load: a BOM is no TOML, so () and no server named off."""
        self.write(BOM + TWO_SERVERS.encode("utf-8"))
        self.assertEqual(anchor.declared_servers(self.home), ("docs.example", 'say"hi'))
        self.assertFalse(anchor.config_unreadable(self.home))
        argv = anchor.argv_for(Backend(self.home, EXE))
        self.assertIn(OFF, argv)

    def test_without_a_mark_it_reads_as_before(self):
        self.write(TWO_SERVERS.encode("utf-8"))
        self.assertEqual(anchor.declared_servers(self.home), ("docs.example", 'say"hi'))

    def test_no_file_is_not_unreadable(self):
        self.assertEqual(anchor.declared_servers(self.home), ())
        self.assertFalse(anchor.config_unreadable(self.home))

    def test_a_file_it_cannot_parse_is_unreadable(self):
        """Fails without `config_unreadable`: nothing could tell this case from a file that declares no server."""
        self.write(b'[mcp_servers.docs]\ncommand = "npx\n')
        self.assertEqual(anchor.declared_servers(self.home), ())
        self.assertTrue(anchor.config_unreadable(self.home))


class TheLogSaysItTests(FallbackCase):
    def test_a_start_over_an_unreadable_config_toml_says_the_servers_may_run(self):
        """Fails with nothing said: the request started with the person's servers on, and no line anywhere."""
        (self.codex_home / "config.toml").write_bytes(b'[mcp_servers.docs]\ncommand = "npx\n')
        self.refusing()
        sent = self.run_once()
        self.assertEqual(sent[0], ["exec", *QUIET, *REST])
        warned = [line for line in self.lines if "config.toml could not be read" in line]
        self.assertEqual(len(warned), 1, self.lines)
        self.assertIn("may run for it", warned[0])

    def test_a_readable_one_says_nothing(self):
        self.refusing()
        sent = self.run_once()
        self.assertEqual(sent[0], ["exec", *QUIET, "-c", OFF, *REST])
        self.assertEqual([line for line in self.lines if "config.toml" in line], [])


if __name__ == "__main__":
    unittest.main()
