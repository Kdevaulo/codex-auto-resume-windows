"""v0.6.26 (review of the third round, K2): one refused usage read no longer turns off what stands on usage_probe.

Since the protocol checks read what Codex's helper last met, protocol_usage_method failed on any error answer to the
usage read - a signed-out account, the very moment sign_in_retry exists for, or Codex's backend failing. usage_probe
then read Failed here, a tripping warning, and every capability standing on it that was on and not kept on was turned
off and stored off; a later good read did not turn it on again. Now a refusal of a method Codex knows passes the check,
and only Codex saying it does not know the method fails it - a failed local check still wins over the data.

The path is the real one from the helper on: the transport's usage read over a stand-in app server, the protocol
check, the registry's resolution and the arming's standing. Nothing reaches the real machine.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase as ac  # noqa: E402
from codex_auto_resume import compat  # noqa: E402
from codex_auto_resume.codex import appserver, transport  # noqa: E402
from codex_auto_resume.compat import probes, standing as compat_standing  # noqa: E402
from codex_auto_resume_advanced import policy, registry  # noqa: E402
from codex_auto_resume_advanced.arming import standing, warnings_for  # noqa: E402
from codex_auto_resume_advanced.vocabulary import ArmingState, OffReason  # noqa: E402
from test_usage_refusal import NOT_FOUND, SIGNED_OUT, read  # noqa: E402

STANDING_ON_USAGE = (registry.SIGN_IN_RETRY, registry.RESET_CREDIT, registry.USAGE_METER)


def view_of(checks):
    """The view the arming reads, for usage_probe resolved from `checks` on a build the data verifies."""
    local = compat_standing.combine(checks.get(name, compat.UNAVAILABLE)
                                    for name in compat.CAPABILITIES["usage_probe"][0])
    state, reason = compat_standing.resolve(local, compat.VERIFIED)
    return ac.view(state, capability="usage_probe", reason=reason)


class RefusalTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="car-adv-usage-refusal-")).resolve()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.backend = transport.Backend(self.home, self.home / "codex.exe")
        for stub in (patch.object(self.backend, "_compatible", return_value=None),
                     patch.object(self.backend, "_argv", return_value=["codex"]),
                     patch.dict(appserver.RESULTS, clear=True)):
            stub.start()
            self.addCleanup(stub.stop)

    def after(self, error):
        """Each capability's standing, armed and confirmed on a good read, after one read Codex answered `error`."""
        good = view_of({"version_runs": compat.PASS, "protocol_usage_method": read(self.backend, self.home, None)[2]})
        self.assertEqual(good["capabilities"]["usage_probe"]["state"], compat.VERIFIED)
        now = view_of({"version_runs": compat.PASS,
                       "protocol_usage_method": read(self.backend, self.home, error)[2]})
        found = {}
        for definition in STANDING_ON_USAGE:
            row = {"state": ArmingState.ARMED, "statement_revision": definition.revision,
                   "engine_version": ac.ENGINE, "warnings": list(warnings_for(definition, good, {}, parts=False))}
            found[definition.id] = standing(definition, row, policy.NONE, now, {})
        return found

    def test_a_signed_out_account_leaves_them_on(self):
        for capability, result in self.after(SIGNED_OUT).items():
            with self.subTest(capability=capability):
                self.assertEqual(result, (ArmingState.ARMED, None, None, None))

    def test_codex_saying_it_does_not_know_the_method_still_turns_them_off(self):
        for capability, result in self.after(NOT_FOUND).items():
            with self.subTest(capability=capability):
                self.assertEqual(result, (ArmingState.OFF, OffReason.FAILED_HERE, None, None))


if __name__ == "__main__":
    unittest.main()
