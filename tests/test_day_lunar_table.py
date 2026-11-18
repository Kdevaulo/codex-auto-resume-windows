r"""v0.6.24: seollal and chuseok from 2026 to 2100 (the owner, 2026-11-18: the table went to 2040).

brand.days.LUNAR_DAYS is what build/lunar_days.py computes: the Korean lunar calendar's rule (KASI's, the Korea Astronomy
and Space Science Institute) in Korea Standard Time, with Meeus' new moons and solar terms. The proof:

- 2026-2040: the dates KASI's calendar converter (astro.kasi.re.kr) gives, read by hand into this file (and into
  test_gui_v0623_days), equal what it computes - exactly, among them 2027 and 2028, where Korea's new year is a day after
  China's because the new moon falls between midnight in Beijing and midnight in Seoul.
- Later years: the same calculation in China Standard Time (UTC+8) equals the Hong Kong Observatory's Gregorian-Lunar
  calendar conversion table (www.hko.gov.hk, gts/time/calendar/text/files/T<year>e.txt, 1901-2100), a second source
  computed by others, read by hand on 2026-11-18 for the years below. The Korean dates differ from those only where the
  new moon falls in that hour, as 2061, 2089, 2092 and 2096 show.
- No date moves if every moment is two minutes earlier or later (Delta T's uncertainty and the formulas' error).

Pure Python, no window: nothing here reads today's date.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "build"))

import lunar_days  # noqa: E402
from codex_auto_resume import brand  # noqa: E402

# KASI's calendar converter, lunar 1/1 and 8/15 (as test_gui_v0623_days.KASI).
KASI = {2026: ("0217", "0925"), 2027: ("0207", "0915"), 2028: ("0127", "1003"), 2029: ("0213", "0922"), 2030: ("0203", "0912"),
        2031: ("0123", "1001"), 2032: ("0211", "0919"), 2033: ("0131", "0908"), 2034: ("0219", "0927"), 2035: ("0208", "0916"),
        2036: ("0128", "1004"), 2037: ("0215", "0924"), 2038: ("0204", "0913"), 2039: ("0124", "1002"), 2040: ("0212", "0921")}

# The Hong Kong Observatory's table (China Standard Time): the 1st lunar month's first day, and day 15 of the 8th.
HKO = {2045: ("0217", "0925"), 2061: ("0121", "0928"), 2073: ("0207", "0916"), 2089: ("0210", "0918"),
       2092: ("0207", "0916"), 2096: ("0125", "0930"), 2100: ("0209", "0918")}
# Where Korea is a day later: the new moon after 15:00 UTC and before 16:00.
KOREA_LATER = {(2061, "seollal"): (1, 22), (2089, "seollal"): (2, 11), (2089, "chuseok"): (9, 19),
               (2092, "seollal"): (2, 8), (2096, "chuseok"): (10, 1)}


def _dates(table):
    return {key: {date[0]: date[1:] for date in dates} for key, dates in table}


class LunarTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.korea = _dates(lunar_days.lunar_days(2026, 2100))
        cls.china = _dates(lunar_days.lunar_days(2026, 2100, 8.0))

    def test_the_table_is_what_the_calculation_gives_to_2100(self):
        self.assertEqual(brand.LUNAR_DAYS, lunar_days.lunar_days(2026, 2100))
        for key, dates in brand.LUNAR_DAYS:
            self.assertEqual([date[0] for date in dates], list(range(2026, 2101)), key)

    def test_kasis_own_years_exactly(self):
        for year, (seollal, chuseok) in KASI.items():
            self.assertEqual(self.korea["seollal"][year], (int(seollal[:2]), int(seollal[2:])), year)
            self.assertEqual(self.korea["chuseok"][year], (int(chuseok[:2]), int(chuseok[2:])), year)

    def test_in_china_standard_time_it_is_the_hong_kong_observatorys_calendar(self):
        for year, (spring, autumn) in HKO.items():
            self.assertEqual(self.china["seollal"][year], (int(spring[:2]), int(spring[2:])), year)
            self.assertEqual(self.china["chuseok"][year], (int(autumn[:2]), int(autumn[2:])), year)
        # 2027 and 2028: China's new year is the day before Korea's, as both offices publish.
        self.assertEqual(self.china["seollal"][2027], (2, 6))
        self.assertEqual(self.china["seollal"][2028], (1, 26))

    def test_korea_differs_from_china_only_by_the_hour_between_them(self):
        for year in HKO:
            for key in ("seollal", "chuseok"):
                expected = KOREA_LATER.get((year, key), self.china[key][year])
                self.assertEqual(self.korea[key][year], expected, (year, key))

    def test_no_date_rests_on_two_minutes(self):
        self.assertEqual(lunar_days.unsteady(2026, 2100, 2.0), [])

    def test_every_table_date_is_a_day_with_its_look(self):
        for key, dates in brand.LUNAR_DAYS:
            for year, month, day in dates:
                self.assertEqual(brand.day_look(year, month, day), key, (year, month, day))
        self.assertIsNone(brand.day_look(2101, 1, 29))


if __name__ == "__main__":
    unittest.main()
