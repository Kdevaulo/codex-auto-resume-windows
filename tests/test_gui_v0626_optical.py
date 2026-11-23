r"""The window's optical alignment, as the third round's audit proposed it (v0.6.26, plans/v0626-audit/audit-design-motion.md;
the owner, 2026-11-22: "제안대로 모두 고침" - every place fixed as the report proposes, its first choice where it names two).

D7. The chart in "How recoveries ended" kept the unscaled default 3 px Margin that Facts was cured of: it stood 2-3 px in
from its card's heading. Now it has none, and starts in the heading's column.

D8. The Overview's two stacked fact tables (Right now, Last 7 days) put their values at different x - 9 px apart in
English, 55 in German. Now they keep one value column, the wider (SettingsForm.OneLabelColumn).

Of the places the audit named, the owner kept these two from real renders before and after (2026-11-23); the others keep
v0.6.25's looks, and their tests went with them.

The window is compiled from the shipped sources and laid out by its own layout audit (SettingsForm.LayoutAudit), never
shown; what is held is where the audit wrote everything down (AuditedGeometry). GUI test module: run on its own, through
gui_lock.sh.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import time
import unittest

from codex_auto_resume import l10n, settings

import guiscan
import test_gui_layout
from test_gui_v0611_access import CSC, POWERSHELL, compile_window, run_probe

LOCALES = ("en", "de")
SCALES = (1.0, 1.5)

PROBE = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::SetUnhandledExceptionMode('ThrowException')
[Windows.Forms.Application]::EnableVisualStyles()
[Windows.Forms.Application]::SetCompatibleTextRenderingDefault($false)
$assembly = [Reflection.Assembly]::LoadFile($env:CAR_EXE)
$static = [Reflection.BindingFlags]'Static,NonPublic,Public'
function T([string]$name) { return $assembly.GetType('CodexAutoResume.' + $name, $true) }
$form = T 'SettingsForm'
$work = [string]$env:CAR_WORK
$utf8 = New-Object Text.UTF8Encoding $false
$schema = [IO.File]::ReadAllText((Join-Path $work 'schema.json'), $utf8)
$current = [IO.File]::ReadAllText((Join-Path $work 'settings.json'), $utf8)
$snapshot = [IO.File]::ReadAllText((Join-Path $work 'snapshot.json'), $utf8)
$out = @{ audit = @{} }
$audit = $form.GetMethod('LayoutAudit', $static)
foreach ($locale in (ConvertFrom-Json $env:CAR_LOCALES)) {
    $catalog = [IO.File]::ReadAllText((Join-Path $work ('strings-' + $locale + '.json')), $utf8)
    $out.audit[$locale] = @{}
    foreach ($scale in (ConvertFrom-Json $env:CAR_SCALES)) {
        $key = ([double]$scale).ToString('0.00', [Globalization.CultureInfo]::InvariantCulture)
        $report = [string]$audit.Invoke($null, [object[]]@($schema, $current, $catalog, $snapshot, [double]$scale))
        $out.audit[$locale][$key] = @{ report = $report; geometry = [string]$form.GetField('AuditedGeometry', $static).GetValue($null) }
    }
}
[IO.File]::WriteAllText((Join-Path $work 'result.json'), ($out | ConvertTo-Json -Depth 8 -Compress), $utf8)
"""

LINE = re.compile(r"^(?P<path>\S+) (?P<x>-?\d+),(?P<y>-?\d+),(?P<w>\d+),(?P<h>\d+) m(?P<m>[\d,-]+) p(?P<p>[\d,-]+)$")


def pages(geometry: str) -> dict:
    """Each page or section the audit laid out: its lines as (path, bounds, margin, padding), in order."""
    found, now = {}, None
    for line in geometry.splitlines():
        if line.startswith("== "):
            now = found.setdefault(line[3:].strip(), [])
            continue
        match = LINE.match(line)
        if match and now is not None:
            now.append((match["path"], tuple(int(match[k]) for k in "xywh"),
                        tuple(int(v) for v in match["m"].split(",")), tuple(int(v) for v in match["p"].split(","))))
    return found


class SourceTests(unittest.TestCase):
    def test_the_chart_has_no_margin_of_its_own(self):
        self.assertIn("chart.Margin = new Padding(0);", guiscan.member_body("SettingsForm", "BuildStatistics"))


@unittest.skipUnless(CSC.is_file() and POWERSHELL.is_file(), "needs the in-box compiler and PowerShell")
class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        exe = compile_window(work)
        (work / "schema.json").write_text(json.dumps(settings.describe(), ensure_ascii=False), encoding="utf-8")
        (work / "settings.json").write_text(json.dumps(settings.defaults(), ensure_ascii=False), encoding="utf-8")
        (work / "snapshot.json").write_text(json.dumps(test_gui_layout.fullest_snapshot(time.time()), ensure_ascii=False),
                                            encoding="utf-8")
        for locale in LOCALES:
            reply = {"ok": True, "language": locale, "strings": l10n.catalog(locale), "endonyms": dict(l10n.ENDONYMS),
                     "preference": locale, "system_language": locale}
            (work / ("strings-%s.json" % locale)).write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        cls.answer = run_probe(PROBE, work, 300 * len(LOCALES), CAR_EXE=str(exe), CAR_LOCALES=json.dumps(list(LOCALES)),
                               CAR_SCALES=json.dumps(list(SCALES)))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def each(self):
        for locale in LOCALES:
            for scale in SCALES:
                yield locale, scale, pages(self.answer["audit"][locale]["%.2f" % scale]["geometry"])

    def test_the_outcome_chart_starts_in_its_card_heading_s_column(self):
        for locale, scale, laid in self.each():
            with self.subTest(locale=locale, scale=scale):
                lines = [line for page in laid.values() for line in page]
                charts = [line for line in lines if line[0].endswith(":OutcomeChart")]
                self.assertTrue(charts, "the audit laid the chart out")
                for path, bounds, margin, _padding in charts:
                    self.assertEqual(margin, (0, 0, 0, 0))
                    card = path.rsplit("/", 1)[0]
                    heading = [line for line in lines if line[0].startswith(card + "/") and line[0].count("/") == path.count("/")
                               and line[0] != path]
                    self.assertTrue(heading, "the chart's card has its heading beside it")
                    self.assertEqual(bounds[0], min(line[1][0] for line in heading), heading)

    def test_the_overview_s_left_column_keeps_one_value_column(self):
        for locale, scale, laid in self.each():
            with self.subTest(locale=locale, scale=scale):
                page = laid["overview"]
                values = {}
                for path, (x, _y, _w, _h), _margin, _padding in page:
                    match = re.search(r"/(\d+):SoftCard/1:SoftStack/(\d+):\w+$", path)
                    if match and int(match[2]) % 2 == 1:
                        values.setdefault(int(match[1]), set()).add(x)
                self.assertIn(0, values, "Right now's facts")
                self.assertIn(2, values, "Last 7 days' facts")
                self.assertEqual(len(values[0]), 1)
                self.assertEqual(values[0], values[2], "one value column for the two tables")


if __name__ == "__main__":
    unittest.main()
