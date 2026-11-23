"""v0.6.26 (fourth round, audit-core A2): a usage answer whose every window is null is a known answer, not "Codex
changed".

Proposal 7 noted any usage answer `parse_usage` could not read as `protocol_reply_unknown`, so the compatibility
report's protocol_usage_method check failed, the record waited usage_probe_broken_answer and the self-check's rule (d)
said Codex changed. That took in an answer whose buckets all name both windows as null - the very form the measured
answer's `premium` bucket has (codex/payload.py; tests/fixtures/usage-limit.json) - which says nothing of the method.
Now such an answer waits usage_unknown, as before v0.6.26, and the check passes; an answer whose buckets do not name
the windows at all, or name none, is still one this version cannot read.

No real Codex runs: `codex app-server --stdio` is played in this process over two pipes (test_usage_probe_broken).
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import compat  # noqa: E402
from codex_auto_resume.codex.usage import parse_usage  # noqa: E402
from codex_auto_resume.compat import probes  # noqa: E402
from codex_auto_resume.engine import impossible  # noqa: E402
import test_usage_probe_broken as broken  # noqa: E402  (a module, so its cases are not bound here)

NULL = {"primary": None, "secondary": None}
NO_WINDOWS = {"rateLimitsByLimitId": {"codex": dict(NULL, rateLimitReachedType=None), "premium": dict(NULL)}}
METHOD = "account/rateLimits/read"


class NoWindowTests(unittest.TestCase):
    # The real transport's usage() over the stand-in helper, set up as test_usage_probe_broken's HelperTests are.
    setUp, read = broken.HelperTests.setUp, broken.HelperTests.read

    def test_every_window_null_is_a_known_answer(self):
        """Fails with the fix reverted: usage_probe_broken_answer, and the method's check FAIL."""
        limits, reason = self.read(usage=NO_WINDOWS)
        self.assertIsNone(limits["available"])
        self.assertEqual(reason, "usage_unknown")
        self.assertNotIn(reason, impossible.USAGE_BROKEN_REASONS)
        self.assertEqual(probes.protocol_check(METHOD), compat.PASS)

    def test_the_legacy_form_with_both_windows_null_too(self):
        self.assertEqual(self.read(usage={"rateLimits": dict(NULL)})[1], "usage_unknown")
        self.assertEqual(probes.protocol_check(METHOD), compat.PASS)

    def test_windows_not_named_or_no_bucket_is_still_unread(self):
        for usage in ({"rateLimitsByLimitId": {"codex": {"first": None, "second": None}}},
                      {"rateLimitsByLimitId": {"codex": {"primary": None}}},
                      {"rateLimitsByLimitId": {}}, {"rateLimitsByLimitId": {"codex": dict(NULL, primary=7)}}):
            with self.subTest(usage=usage):
                self.assertEqual(self.read(usage=usage)[1], "usage_probe_broken_answer")
                self.assertEqual(probes.protocol_check(METHOD), compat.FAIL)

    def test_the_measured_answer_with_one_null_bucket_reads_as_it_did(self):
        reply = {"rateLimitsByLimitId": {
            "codex": {"primary": {"usedPercent": 98, "windowDurationMins": 300, "resetsAt": 1788645827},
                      "secondary": {"usedPercent": 34, "windowDurationMins": 10080, "resetsAt": 1789108889}},
            "premium": dict(NULL)}}
        parsed = parse_usage(reply)
        self.assertIs(parsed["available"], True)
        self.assertEqual(len(parsed["windows"]), 2)


if __name__ == "__main__":
    unittest.main()
