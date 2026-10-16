# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""What each measurement found, as this build ships it: its verdict and the Codex it was made on.

The owner measures on a real machine (measure.py), and each run writes one content-free record
to the source tree's docs/evidence/live/ (evidence.py). An installed copy has no such directory,
so what a release knows of the measurements is this table, and
advanced/tests/test_advanced_measured.py keeps it equal to the records beside it: a record
re-measured without this table following fails the tests.

A measurement is here only when it settled - a pass or a fail, the person's completion counting
for a blocked probe (evidence.outcome). One that is not here was never measured, as far as this
build knows. A capability whose route rests on a measurement that failed, or that has no pass
for the Codex in force, says so as a warning in its statement (arming.warnings_for); it is
never withheld for it (the owner's rule of 2026-09-26, which replaced decision C7).

Pure: a table, and nothing read.
"""
from __future__ import annotations

from .vocabulary import Measurement, Verdict

# The Codex the 2026-10-10 measurements were made on, as `codex --version` names it - the same
# words the Compatibility Registry's view carries as the engine version. Every earlier reading
# (codex-cli 0.158.0-alpha.2.1, 2026-09-26 and 09-28) was made again on it.
CLI_0162_ALPHA_17_2 = "codex-cli 0.162.0-alpha.17.2"

MEASURED = {
    Measurement.M1: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.M2: (Verdict.FAIL, CLI_0162_ALPHA_17_2),
    Measurement.M2B: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.M3: (Verdict.FAIL, CLI_0162_ALPHA_17_2),
    Measurement.M4: (Verdict.FAIL, CLI_0162_ALPHA_17_2),
    Measurement.M5: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.M6: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.M7: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.MW: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.MA: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.MH: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.MP1: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.MP2: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.MP3: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    # 2026-10-11, at the owner's word that one reset credit may be spent.
    Measurement.MR: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    # 2026-10-11, once that credit was spent and the account had none left.
    Measurement.MN: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    # 2026-10-13, after a 5-hour reset that passed with no Codex use.
    Measurement.MU: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    # 2026-10-16 (records 22f19fb7, da367839, f0f1f1fd): the Desktop's IPC pipe starts, adds to and interrupts a turn of
    # a conversation the app holds; Codex documents no supported shared app-server the app uses; `codex cloud` reads a
    # cloud task's state but nothing continues one - partial, which is not a pass.
    Measurement.MIPC: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.MAWS: (Verdict.FAIL, CLI_0162_ALPHA_17_2),
    Measurement.MCLOUD: (Verdict.FAIL, CLI_0162_ALPHA_17_2),
    # 2026-10-15 and 16, stage 4's nine (v0.6.16-beta.4), Codex closed or open as each needs.
    Measurement.MC1: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.MXA: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.MX: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    Measurement.MF: (Verdict.PASS, CLI_0162_ALPHA_17_2),
    # A fail narrows a route or is its capability's warning, never its end (the owner's rule).
    Measurement.MB: (Verdict.FAIL, CLI_0162_ALPHA_17_2),
    Measurement.MO: (Verdict.FAIL, CLI_0162_ALPHA_17_2),
    Measurement.MC2: (Verdict.FAIL, CLI_0162_ALPHA_17_2),
    Measurement.M3B: (Verdict.FAIL, CLI_0162_ALPHA_17_2),
    Measurement.M6B: (Verdict.FAIL, CLI_0162_ALPHA_17_2),
}
