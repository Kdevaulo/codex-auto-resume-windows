"""v0.6.26 (review of the third round, K2): Codex refusing a usage read is not the usage method gone.

The compatibility report's protocol_usage_method check failed as soon as Codex's helper last met any error answer to
account/rateLimits/read. A signed-out account or Codex's backend failing is such an answer, so one refused read failed
the check - and with it, in the edition that reads it, everything standing on the usage read, until a person turned it
on again. Now only an error answer saying the method is not one Codex knows fails it; any other refusal is a PASS, and
its record waits usage_unknown, as it did before v0.6.26, rather than counting toward "Codex changed" (rule d).

No real Codex runs: `codex app-server --stdio` is played in this process over two pipes (test_usage_probe_broken's).
"""
from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
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
from test_usage_probe_broken import USAGE, Helper  # noqa: E402

METHOD = "account/rateLimits/read"
SIGNED_OUT = {"code": -32600, "message": "codex account authentication required to read rate limits"}
BACKEND = {"code": -32603, "message": "failed to fetch codex rate limits: 502 Bad Gateway"}
NOT_FOUND = {"code": -32601, "message": "Method not found"}
NO_VARIANT = {"code": -32600, "message": "Invalid request: unknown variant `%s`, expected one of `initialize`" % METHOD}
OTHER_VARIANT = {"code": -32600, "message": "Invalid request: unknown variant `thread/queue/add`, expected `x`"}


class Answering(Helper):
    """The helper, answering the usage read with the error `error`."""

    def __init__(self, home, error):
        self.error = error
        super().__init__(home, None, "refuse")

    def _say(self, value):
        if "error" in value:
            value = dict(value, error=self.error)
        super()._say(value)


def read(backend, home, error):
    """One usage read over the stand-in; (the answer, the record's reason, the protocol check)."""
    if error is None:
        maker = lambda *a, **k: Helper(home, None, USAGE)  # noqa: E731
    else:
        maker = lambda *a, **k: Answering(home, error)  # noqa: E731
    with patch.object(appserver.S, "Popen", maker):
        limits = backend.usage()
    return (limits, impossible.usage_reason(limits, getattr(backend, "protocol_results", None)),
            probes.protocol_check(METHOD))


class RefusalTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="car-usage-refusal-")).resolve()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.backend = transport.Backend(self.home, self.home / "codex.exe")
        for stub in (patch.object(self.backend, "_compatible", return_value=None),
                     patch.object(self.backend, "_argv", return_value=["codex"]),
                     patch.dict(appserver.RESULTS, clear=True)):
            stub.start()
            self.addCleanup(stub.stop)

    def test_a_signed_out_or_failing_account_passes_the_check_and_waits_usage_unknown(self):
        for error in (SIGNED_OUT, BACKEND, OTHER_VARIANT, {"code": "-32601"}, {}):
            with self.subTest(error=error):
                limits, reason, check = read(self.backend, self.home, error)
                self.assertIsNone(limits["available"])
                self.assertEqual(appserver.last_result(METHOD), appserver.REFUSED)
                self.assertEqual(check, compat.PASS)
                self.assertEqual(reason, "usage_unknown")
                self.assertNotIn(reason, impossible.USAGE_BROKEN_REASONS)

    def test_codex_saying_it_does_not_know_the_method_still_fails_it(self):
        for error in (NOT_FOUND, NO_VARIANT):
            with self.subTest(error=error):
                limits, reason, check = read(self.backend, self.home, error)
                self.assertIsNone(limits["available"])
                self.assertEqual(appserver.last_result(METHOD), appserver.METHOD_UNKNOWN)
                self.assertEqual(check, compat.FAIL)
                self.assertEqual(reason, "usage_probe_broken_request")

    def test_a_refusal_after_a_method_gone_is_what_the_helper_last_met(self):
        self.assertEqual(read(self.backend, self.home, NOT_FOUND)[2], compat.FAIL)
        self.assertEqual(read(self.backend, self.home, SIGNED_OUT)[2], compat.PASS)
        self.assertEqual(read(self.backend, self.home, None)[2], compat.PASS)

    def test_the_caller_still_meets_codexs_no(self):
        for error in (SIGNED_OUT, NOT_FOUND):
            with self.subTest(error=error), patch.object(appserver.S, "Popen",
                                                         lambda *a, **k: Answering(self.home, error)):
                with appserver.Protocol(self.backend) as protocol:
                    with self.assertRaises(transport.AdapterError) as raised:
                        protocol.call(METHOD)
                self.assertEqual(str(raised.exception), "protocol_request_failed")


if __name__ == "__main__":
    unittest.main()
