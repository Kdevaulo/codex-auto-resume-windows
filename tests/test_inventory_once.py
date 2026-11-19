"""One process list serves a whole status read, and it is read without PowerShell (v0.6.24 final).

The owner's live acceptance of v0.6.24 found a status read taking 90-105 s on an advanced installation: each capability's
view binds the compatibility report to the engine the app serves (compat/views.py _binding_holds -> compat/probes.py
_served_engines -> codex/pairing.py app_engines -> inventory), so one read listed the processes nine times, and each list
was a PowerShell CIM query of about 10 s on that PC. Now one list answers every caller for pairing.INVENTORY_SECONDS, is
read afresh where a caller acts on who runs, and is one Toolhelp snapshot - the same rows as the CIM query gave.

No test here reads a Codex home or the product's installation: the homes are temporary, and LOCALAPPDATA points into one.
"""
from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import patch

from codex_auto_resume import compat, compatio, config
from codex_auto_resume import windows as w
from codex_auto_resume.codex import pairing
from codex_auto_resume.domain.errors import AdapterError

try:
    import no_real_codex                    # tests/sitecustomize.py and scripts/test_parts.py install it
except ImportError:                         # pragma: no cover - a run without tests/ on its path
    no_real_codex = None

# How many times the owner's read bound the report to the app's engines (8 through the arming views, 1 more beside).
READS = 9


class Listed:
    """A stand-in for the Toolhelp read under the inventory: counts its calls, and can take `seconds` each."""

    def __init__(self, rows=(), seconds=0.0):
        self.rows, self.seconds, self.names = list(rows), seconds, []

    def __call__(self, names):
        self.names.append(tuple(names))
        if self.seconds:
            time.sleep(self.seconds)
        return [dict(row) for row in self.rows]

    @property
    def calls(self):
        return len(self.names)


class Case(unittest.TestCase):
    def setUp(self):
        pairing.forget_inventory()
        self.addCleanup(pairing.forget_inventory)

    def listed(self, *rows, seconds=0.0):
        stub = Listed(rows, seconds)
        patcher = patch.object(pairing, "processes_named", stub)
        patcher.start()
        self.addCleanup(patcher.stop)
        return stub

    def clock(self, start=1000.0):
        """pairing's monotonic clock, set by the test: its `now` is moved by hand."""
        self.now = start
        patcher = patch.object(pairing, "time", types.SimpleNamespace(monotonic=lambda: self.now))
        patcher.start()
        self.addCleanup(patcher.stop)


class ReadTests(Case):
    """A status read binds the report to the app's engines many times; the processes are listed once."""

    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        environment = patch.dict(os.environ, {"LOCALAPPDATA": str(root / "local"), "CODEX_HOME": str(root / "codex")})
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop(config.ENV_CODEX_EXE, None)
        self.paths = config.Paths(root / "home")
        self.now = time.time()
        checks = {name: compat.PASS for name in compat.CHECKS}
        # An engine no candidate in bin is - the app's own, as on the owner's PC - so every read asks the app.
        report = compat.build_report(
            checked_at=self.now, product="0.6.24",
            engine={"found": True, "version": "codex-cli 0.155.0", "signature": [10, 20], "path_digest": "ab" * 32,
                    "candidates": 1},
            data={"bundled": "ok", "bundled_sequence": 1, "cache": "absent", "cache_sequence": None,
                  "cache_origin": None, "fetched_at": None, "source": "bundled", "expired": False},
            checks=checks, capabilities=compat.evaluate(checks, version="codex-cli 0.155.0", sources=[]),
            acting="structurally_compatible")
        self.paths.compat_report_file.parent.mkdir(parents=True, exist_ok=True)
        self.paths.compat_report_file.write_text(json.dumps(report), encoding="utf-8")

    def read(self):
        """The view each advanced capability's reading takes (arming._view_of: compatio.reader_view), READS times."""
        return [compatio.reader_view(self.paths, now=self.now, settings={}) for _ in range(READS)]

    def test_one_status_read_lists_the_processes_once(self):
        listed = self.listed()
        found = self.read()
        self.assertEqual(listed.calls, 1, "each binding of the report started a process list of its own")
        self.assertEqual(listed.names, [pairing.INVENTORY_NAMES])
        self.assertTrue(all(view == found[0] for view in found), "the reads answered differently")
        self.assertEqual(found[0]["status"], "engine_changed", "the report's engine is none of these processes")

    def test_a_slow_list_costs_a_read_one_list_not_nine(self):
        self.listed(seconds=2.0)
        started = time.monotonic()
        self.read()
        took = time.monotonic() - started
        self.assertLess(took, 2.0 * 2, "a read of %d bindings took %.1f s over a 2 s list" % (READS, took))


class CacheTests(Case):
    APP = {"pid": 10, "parent": 1, "path": "C:\\Apps\\ChatGPT.exe"}

    def test_the_list_answers_for_its_window_then_is_read_again(self):
        self.clock()
        listed = self.listed(self.APP)
        self.assertEqual(pairing.inventory(), [self.APP])
        self.now += pairing.INVENTORY_SECONDS
        self.assertEqual(pairing.inventory(), [self.APP])
        self.assertEqual(listed.calls, 1)
        self.now += 0.01
        pairing.inventory()
        self.assertEqual(listed.calls, 2, "a list older than INVENTORY_SECONDS was still answered")

    def test_a_clock_that_went_back_reads_again(self):
        self.clock()
        listed = self.listed(self.APP)
        pairing.inventory()
        self.now -= 1.0
        pairing.inventory()
        self.assertEqual(listed.calls, 2)

    def test_forget_inventory_makes_the_next_read_fresh(self):
        listed = self.listed(self.APP)
        pairing.inventory()
        pairing.forget_inventory()
        pairing.inventory()
        self.assertEqual(listed.calls, 2)

    def test_starting_or_shutting_an_app_server_of_our_own_forgets_the_list(self):
        listed = self.listed(self.APP)
        with patch.object(pairing, "process_identity", return_value={"pid": 77, "path": "x", "created": 5}):
            pairing.inventory()
            mark = pairing.own_server(77)
            pairing.inventory()
            self.assertEqual(listed.calls, 2, "a server we started was not looked for afresh")
            pairing.own_server_gone(mark)
            pairing.inventory()
            self.assertEqual(listed.calls, 3, "a server we shut was not looked for afresh")

    def test_the_queue_route_asks_a_fresh_list_before_a_send(self):
        listed = self.listed(self.APP)
        backend = w.Backend(Path("state"), Path("codex.exe"))
        backend.queue_remote_supported = True
        pairing.inventory()
        self.assertFalse(backend._queue_daemon_remote())
        self.assertEqual(listed.calls, 2, "the send's route was decided on a list a read left")

    def test_a_list_read_while_it_was_forgotten_is_not_kept(self):
        """A read begun before a caller started or stopped a process may not have seen it: it answers its own caller,
        and the next read looks again."""
        rows = [[self.APP], [self.APP, {"pid": 11, "parent": 10, "path": "C:\\Apps\\codex.exe"}]]

        def read(names):
            if len(rows) == 2:
                pairing.forget_inventory()          # another thread started a server while this list was read
            return rows.pop(0)

        with patch.object(pairing, "processes_named", side_effect=read):
            self.assertEqual(pairing.inventory(), [self.APP])
            self.assertEqual(len(pairing.inventory()), 2, "a list begun before the forget was kept")

    def test_each_caller_gets_its_own_copy(self):
        self.listed(self.APP)
        first = pairing.inventory()
        first[0]["path"] = None
        first.append({"pid": 99})
        self.assertEqual(pairing.inventory(), [self.APP])

    def test_a_list_that_cannot_be_read_is_refused_and_not_kept(self):
        with patch.object(pairing, "processes_named", side_effect=AdapterError("windows_required")):
            with self.assertRaisesRegex(AdapterError, "process_inventory_unavailable"):
                pairing.inventory()
        listed = self.listed(self.APP)
        self.assertEqual(pairing.inventory(), [self.APP])
        self.assertEqual(listed.calls, 1)


# The query the inventory made until v0.6.24 final, kept here as the reference the Toolhelp read is held to.
CIM = r"""
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
@(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'ChatGPT.exe' OR Name = 'codex.exe'" |
 ForEach-Object { [pscustomobject]@{
 pid=[int]$_.ProcessId; parent=[int]$_.ParentProcessId; path=$_.ExecutablePath; name=$_.Name
 } }) | ConvertTo-Json -Compress
"""


@unittest.skipUnless(os.name == "nt", "Windows only")
class SameAsCimTests(Case):
    """The Toolhelp read lists what the CIM query listed for this PC's processes: the same pids, parents and paths."""

    def cim(self):
        powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        if not powershell.is_file():
            self.skipTest("no Windows PowerShell to compare with")
        done = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", CIM],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
                              creationflags=w.NO_WINDOW, check=True, shell=False)
        rows = json.loads(done.stdout) if done.stdout.strip() else []
        return {row["pid"]: row for row in (rows if isinstance(rows, list) else [rows])}

    @staticmethod
    def this_pc():
        """This PC's own Codex processes listed too, past the guard every test run has (tests/no_real_codex.py)."""
        return no_real_codex.real() if no_real_codex is not None else contextlib.nullcontext()

    def test_the_toolhelp_read_matches_the_cim_query(self):
        names = ("python.exe",) + pairing.INVENTORY_NAMES
        with self.this_pc():
            before = {row["pid"]: row for row in pairing.processes_named(names)}
            cim = self.cim()
            after = {row["pid"]: row for row in pairing.processes_named(names)}
        own = os.getpid()
        for found in (before, after):
            self.assertIn(own, found, "the test's own python.exe was not listed")
        self.assertIn(own, cim)
        self.assertEqual(os.path.normcase(before[own]["path"]), os.path.normcase(cim[own]["path"]))
        self.assertTrue(Path(before[own]["path"]).is_file())
        # Processes come and go between the reads: every one listed by all three reads must agree in each field.
        steady = set(before) & set(cim) & set(after)
        self.assertIn(own, steady)
        for pid in steady:
            with self.subTest(pid=pid):
                self.assertEqual(before[pid], after[pid])
                self.assertEqual(before[pid]["parent"], cim[pid]["parent"])
                self.assertEqual(before[pid]["path"], cim[pid]["path"])

    def test_the_inventory_lists_only_the_app_and_the_engines(self):
        with self.this_pc():
            rows = pairing.inventory()
        self.assertTrue(all(set(row) == {"pid", "parent", "path"} for row in rows))
        self.assertTrue(all(row["path"] is None or Path(row["path"]).name.lower() in ("chatgpt.exe", "codex.exe")
                            for row in rows))
        self.assertNotIn(os.getpid(), {row["pid"] for row in rows})


class GuardTests(Case):
    """Every test run keeps this PC's Codex out of what a test sees (tests/no_real_codex.py), as CI's runner has none."""

    def setUp(self):
        super().setUp()
        if no_real_codex is None or not no_real_codex.active():
            self.skipTest("the guard is not installed in this run")

    def test_a_test_sees_no_codex_app_and_no_engine(self):
        self.assertEqual(pairing.inventory(), [])
        rows = pairing.processes_named(("python.exe",) + pairing.INVENTORY_NAMES)
        self.assertIn(os.getpid(), {row["pid"] for row in rows})
        self.assertTrue(all(Path(row["path"]).name.lower() == "python.exe" for row in rows if row["path"]))


if __name__ == "__main__":
    unittest.main()
