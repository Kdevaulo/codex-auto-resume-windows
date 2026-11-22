"""v0.6.26 (update resilience, proposal 7): a usage read that broke says which way it broke.

Every way Codex's usage helper could fail - another home in its answer, another system, a refused request, an answer
this version cannot read - was one word, "Usage could not be read", and a record waited under it for ever. Now the
helper's last real answer is kept by method (codex/appserver.py), the record's reason names it (usage_probe_broken_*),
the watcher's judge counts it toward "recovery cannot work here" (engine/impossible.py, rule d), and the compatibility
report's two protocol checks say what the helper last met instead of whether this product's own list names a method.

No real Codex runs: `codex app-server --stdio` is played in this process over two pipes.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import compat  # noqa: E402
from codex_auto_resume.codex import appserver, transport  # noqa: E402
from codex_auto_resume.compat import probes  # noqa: E402
from codex_auto_resume.engine import impossible  # noqa: E402
from codexsim import RESET  # noqa: E402
from test_engine import EngineCase, T1  # noqa: E402

USAGE = {"rateLimits": {"primary": {"usedPercent": 12, "windowDurationMins": 300, "resetsAt": 1900000000}}}


class Helper:
    """The helper, as one Popen: initialize is answered with `start` (None: the home and system this product asked
    for), account/rateLimits/read with `usage` - a result, or "refuse" for an error."""

    pid = None

    def __init__(self, home, start, usage):
        self.home, self.start, self.usage = home, start, usage
        to_server, from_client = os.pipe()
        to_client, from_server = os.pipe()
        self.stdin = io.open(from_client, "w", encoding="utf-8", newline="")
        self._incoming = io.open(to_server, "r", encoding="utf-8")
        self.stdout = io.open(to_client, "r", encoding="utf-8", errors="replace")
        self._outgoing = io.open(from_server, "w", encoding="utf-8", newline="")
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _say(self, value):
        self._outgoing.write(json.dumps(value) + "\n")
        self._outgoing.flush()

    def _serve(self):
        try:
            for line in self._incoming:
                message = json.loads(line)
                method, ident = message.get("method"), message.get("id")
                if method is None or ident is None:
                    continue
                if method == "initialize":
                    self._say({"id": ident, "result": self.start if self.start is not None else
                               {"codexHome": str(self.home), "platformOs": "windows"}})
                elif self.usage == "refuse":
                    self._say({"id": ident, "error": {"code": -32601, "message": "unknown method"}})
                else:
                    self._say({"id": ident, "result": self.usage})
        except (OSError, ValueError):
            pass
        finally:
            for stream in (self._outgoing, self._incoming):
                try:
                    stream.close()
                except OSError:
                    pass

    def wait(self, timeout=None):
        self.thread.join(timeout)
        return 0

    def terminate(self):
        pass


class HelperTests(unittest.TestCase):
    """The real transport's usage(), over the stand-in: what it answers, and what the helper last met."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="car-usage-broken-")).resolve()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.backend = transport.Backend(self.home, self.home / "codex.exe")
        for stub in (patch.object(self.backend, "_compatible", return_value=None),
                     patch.object(self.backend, "_argv", return_value=["codex"])):
            stub.start()
            self.addCleanup(stub.stop)
        self.results = patch.dict(appserver.RESULTS, clear=True)
        self.results.start()
        self.addCleanup(self.results.stop)

    def read(self, start=None, usage=USAGE):
        with patch.object(appserver.S, "Popen", lambda *a, **k: Helper(self.home, start, usage)):
            limits = self.backend.usage()
        return limits, impossible.usage_reason(limits, getattr(self.backend, "protocol_results", None))

    def test_an_answer_without_codex_home_names_the_answer(self):
        limits, reason = self.read(start={"platformOs": "windows"})
        self.assertIsNone(limits["available"])
        self.assertEqual(reason, "usage_probe_broken_answer")
        self.assertEqual(probes.protocol_check("account/rateLimits/read"), compat.FAIL)

    def test_a_refused_request_names_the_request(self):
        self.assertEqual(self.read(usage="refuse")[1], "usage_probe_broken_request")
        self.assertEqual(probes.protocol_check("account/rateLimits/read"), compat.FAIL)

    def test_an_answer_this_version_cannot_read_names_the_answer(self):
        self.assertEqual(self.read(usage={"somethingNew": {}})[1], "usage_probe_broken_answer")
        self.assertEqual(probes.protocol_check("account/rateLimits/read"), compat.FAIL)

    def test_a_good_read_passes_and_says_nothing_broke(self):
        limits, _ = self.read()
        self.assertIs(limits["available"], True)
        self.assertEqual(probes.protocol_check("account/rateLimits/read"), compat.PASS)
        # The delete was never asked here: not checked, rather than vouched for by a list of names.
        self.assertEqual(probes.protocol_check("thread/queue/delete"), compat.UNAVAILABLE)
        # And a broken start after it is what the helper last met.
        self.read(start={"codexHome": str(self.home), "platformOs": "linux"})
        self.assertEqual(probes.protocol_check("account/rateLimits/read"), compat.FAIL)

    def test_a_helper_that_cannot_start_stays_usage_unknown(self):
        def refuse(*unused, **ignored):
            raise OSError("cannot start")
        with patch.object(appserver.S, "Popen", refuse):
            limits = self.backend.usage()
        self.assertEqual(impossible.usage_reason(limits, getattr(self.backend, "protocol_results", None)),
                         "usage_unknown")


class RecordTests(EngineCase):
    """The record waits under the reason that names it, where it waited under usage_unknown."""

    def wait_on(self, results):
        self.h.home.fail_usage(T1)
        self.h.backend.loaded_map[T1] = "loaded"
        self.h.tick()
        self.h.now = RESET + 61
        self.h.engine._usage_cache = None
        self.h.backend.usage_result = {"available": None, "reset_at": None, "limit_type": "unknown",
                                       "reason": "usage_probe_unavailable"}
        self.h.backend.protocol_results = results
        self.h.tick(advance=1900)
        return self.h.record()

    def test_a_record_waits_under_the_broken_answer(self):
        row = self.wait_on({"initialize": ("protocol_home_mismatch", 3)})
        self.assertEqual((row["state"], row["last_error"]), ("waiting_for_usage", "usage_probe_broken_answer"))
        self.assertEqual(self.h.backend.send_calls, [])

    def test_with_nothing_said_by_the_helper_it_is_usage_unknown_as_before(self):
        row = self.wait_on(None)
        self.assertEqual(row["last_error"], "usage_unknown")


if __name__ == "__main__":
    unittest.main()
