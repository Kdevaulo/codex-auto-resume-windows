"""v0.6.17: the Advanced page's layout audits dealt over the five layout modules by what each costs (pagecase.layout_deal).

Until v0.6.17 the languages were dealt round: the module that drew Japanese took 43 minutes on GitHub's runners, the one
that drew English under one, and two of Japan's five audits shared one of its four processes. Now every (language,
scaling) is one audit with a cost (pagecase.audit_cost, what it took there), the modules are filled longest first under
the time their longest audit sets, and each module's processes take its audits longest first (pagecase.deal_out). This
holds the deal to its rules without compiling anything:

* every language at every scaling is audited exactly once over the five modules, each module audits something, and each
  module runs exactly its share (LayoutTests.JOBS); the canary is in one module, the one CANARY_MODULE names;
* no module takes longer than the costliest single audit, and the modules together take less than the round deal did;
* deal_out gives the longest first to the share with the least, equal costs round as before, and probe() shares its jobs
  out that way.

Not a GUI test: it reads the deal and the five modules' classes, and runs no window (probe's processes are stood in for).
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pagecase  # noqa: E402
from codex_auto_resume import l10n  # noqa: E402


def wall(costs: list) -> float:
    """How long a module of audits of these costs takes: its slowest process's share (deal_out)."""
    shares = pagecase.deal_out(costs, pagecase.LAYOUT_WORKERS)
    return max(sum(costs[index] for index in share) for share in shares)


def module_costs(module: int) -> list:
    costs = [pagecase.audit_cost(locale) for locale, _ in pagecase.layout_jobs(module)]
    if module == pagecase.CANARY_MODULE:
        costs.append(pagecase.OTHER_AUDIT_COST)
    return costs


class DealTests(unittest.TestCase):
    def test_every_language_at_every_scaling_is_audited_exactly_once(self):
        dealt = [job for module in range(1, pagecase.LAYOUT_MODULES + 1) for job in pagecase.layout_jobs(module)]
        everything = [(str(locale), scale) for locale in l10n.LOCALES for scale in pagecase.SCALES]
        self.assertEqual(sorted(dealt), sorted(everything))
        self.assertEqual(len(dealt), len(set(dealt)))

    def test_every_module_audits_something(self):
        for module in range(1, pagecase.LAYOUT_MODULES + 1):
            with self.subTest(module=module):
                self.assertTrue(pagecase.layout_jobs(module))

    def test_each_module_runs_exactly_its_share_and_one_runs_the_canary(self):
        canaries = []
        for module in range(1, pagecase.LAYOUT_MODULES + 1):
            tests = importlib.import_module("test_advanced_page_layout_%d" % module).LayoutTests
            with self.subTest(module=module):
                self.assertEqual(tests.JOBS, pagecase.layout_jobs(module))
            if tests.CANARY:
                canaries.append(module)
        self.assertEqual(canaries, [pagecase.CANARY_MODULE])

    def test_the_deal_is_the_same_every_time(self):
        before = pagecase.layout_deal()
        pagecase.layout_deal.cache_clear()
        self.assertEqual(pagecase.layout_deal(), before)

    def test_no_module_takes_longer_than_the_costliest_audit(self):
        costliest = max(pagecase.audit_cost(locale) for locale in l10n.LOCALES)
        for module in range(1, pagecase.LAYOUT_MODULES + 1):
            with self.subTest(module=module):
                self.assertLessEqual(wall(module_costs(module)), costliest)

    def test_the_modules_together_take_less_than_the_round_deal(self):
        dealt = sum(wall(module_costs(module)) for module in range(1, pagecase.LAYOUT_MODULES + 1))
        # The deal until v0.6.17: the languages round, each at every scaling, the canary in the last; its processes
        # took their audits round too.
        locales = [str(locale) for locale in l10n.LOCALES]
        round_deal = 0.0
        for module in range(1, pagecase.LAYOUT_MODULES + 1):
            costs = [pagecase.audit_cost(locale) for locale in locales[module - 1::pagecase.LAYOUT_MODULES]
                     for _ in pagecase.SCALES]
            if module == pagecase.LAYOUT_MODULES:
                costs.append(pagecase.OTHER_AUDIT_COST)
            round_deal += max(sum(costs[index::pagecase.LAYOUT_WORKERS]) for index in range(pagecase.LAYOUT_WORKERS))
        self.assertLess(dealt, round_deal * 0.8)

    def test_japanese_is_never_two_audits_in_one_process(self):
        for module in range(1, pagecase.LAYOUT_MODULES + 1):
            costs = module_costs(module)
            for share in pagecase.deal_out(costs, pagecase.LAYOUT_WORKERS):
                with self.subTest(module=module):
                    self.assertLessEqual(sum(1 for index in share if costs[index] == pagecase.audit_cost("ja")), 1)


class DealOutTests(unittest.TestCase):
    def test_the_longest_go_first_to_the_share_with_least(self):
        self.assertEqual(pagecase.deal_out([10, 1270, 10, 1270, 420, 10], 2), [[1, 4], [0, 2, 3, 5]])

    def test_equal_costs_deal_round_as_before(self):
        self.assertEqual(pagecase.deal_out([1] * 6, 4), [[0, 4], [1, 5], [2], [3]])

    def test_the_allowance_follows_the_share_not_the_count(self):
        each = pagecase.AUDIT_SECONDS * pagecase.audited_views()
        self.assertEqual(pagecase.audit_timeout([10] * 8, 4), 2 * each)
        self.assertEqual(pagecase.audit_timeout([pagecase.audit_cost("ja")] * 4, 4),
                         max(each, 3 * pagecase.audit_cost("ja")))

    def test_probe_shares_its_jobs_out_longest_first(self):
        jobs = [{"kind": "audit", "name": name, "cost": cost}
                for name, cost in (("en", 10), ("ja", 1270), ("de", 10), ("ja2", 1270), ("zh", 320))]

        class Exited:
            def __init__(self, *args, **kwargs):
                self.returncode, self.args = 1, args

            def communicate(self, timeout=None):
                return b"", b""

        with tempfile.TemporaryDirectory() as folder, mock.patch.object(pagecase.subprocess, "Popen", Exited):
            work = Path(folder)
            pagecase.probe(work, work / "none.exe", jobs, timeout=1, workers=2)
            shares = [[job["name"] for job in json.loads((work / ("jobs-%d.json" % index)).read_text(encoding="utf-8"))]
                      for index in range(2)]
        self.assertEqual(shares, [["ja", "zh"], ["en", "de", "ja2"]])


if __name__ == "__main__":
    unittest.main()
