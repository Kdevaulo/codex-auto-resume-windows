"""Seollal (lunar 1/1) and Chuseok (lunar 8/15) as solar dates, for brand.days.LUNAR_DAYS.

The Korean lunar calendar is astronomical: a month begins on the day, in Korea Standard Time (UTC+9), of a new moon, and is
numbered by the principal solar term (zhongqi, the sun's apparent longitude a multiple of 30 degrees) whose day falls in it -
month 11 holds the winter solstice (270), month 1 holds 330, month 8 holds the autumn equinox (180). Between two month 11s
there are 12 months, or 13 with a leap month: the first of them that holds no principal term. This is the rule KASI (Korea
Astronomy and Space Science Institute, astro.kasi.re.kr) computes its official calendar by, and the table it publishes for
2026-2040 is what this reproduces exactly (tests/test_day_lunar_table.py). KASI publishes no table past 2050.

The moments are Jean Meeus, Astronomical Algorithms (2nd ed., 1998): the new moon with its periodic and planetary terms
(chapter 49, a few seconds), the sun's apparent longitude (chapter 25, 0.01 degree - about 15 minutes of time), and
Delta T (TT - UT) by Espenak and Meeus' polynomials (NASA, Five Millennium Canon). A date is only uncertain where a new moon
or a principal term falls within minutes of midnight; `close_calls` names every one, so a table it writes can say which
dates rest on a margin and how wide it is.

The same calculation in China Standard Time (UTC+8) is the Chinese calendar, which the Hong Kong Observatory publishes for
1901-2100: the second, independent source the tests check later years against.

    python build/lunar_days.py 2026 2100        # the LUNAR_DAYS table, and the close calls
"""
from __future__ import annotations

import math
import sys

KST = 9.0          # Korea Standard Time, UTC+9 (since 1961)
SEOLLAL, CHUSEOK = "seollal", "chuseok"


def _sin(degrees):
    return math.sin(math.radians(degrees))


def delta_t(year):
    """TT - UT in seconds: Espenak and Meeus (NASA, Five Millennium Canon of Solar Eclipses), 2005 to 2150."""
    if year < 2050:
        t = year - 2000.0
        return 62.92 + 0.32217 * t + 0.005589 * t * t
    return -20.0 + 32.0 * ((year - 1820.0) / 100.0) ** 2 - 0.5628 * (2150.0 - year)


_NEW_MOON_TERMS = (  # (coefficient, power of E, multiples of M, M', F, Omega) - Meeus table 49.A, new moon
    (-0.40720, 0, 0, 1, 0, 0), (0.17241, 1, 1, 0, 0, 0), (0.01608, 0, 0, 2, 0, 0), (0.01039, 0, 0, 0, 2, 0),
    (0.00739, 1, -1, 1, 0, 0), (-0.00514, 1, 1, 1, 0, 0), (0.00208, 2, 2, 0, 0, 0), (-0.00111, 0, 0, 1, -2, 0),
    (-0.00057, 0, 0, 1, 2, 0), (0.00056, 1, 1, 2, 0, 0), (-0.00042, 0, 0, 3, 0, 0), (0.00042, 1, 1, 0, 2, 0),
    (0.00038, 1, 1, 0, -2, 0), (-0.00024, 1, -1, 2, 0, 0), (-0.00017, 0, 0, 0, 0, 1), (-0.00007, 0, 2, 1, 0, 0),
    (0.00004, 0, 0, 2, -2, 0), (0.00004, 0, 3, 0, 0, 0), (0.00003, 0, 1, 1, -2, 0), (0.00003, 0, 0, 2, 2, 0),
    (-0.00003, 0, 1, 1, 2, 0), (0.00003, 0, -1, 1, 2, 0), (-0.00002, 0, -1, 1, -2, 0), (-0.00002, 0, 1, 3, 0, 0),
    (0.00002, 0, 0, 4, 0, 0))
_PLANETARY = (  # (coefficient, constant, per lunation, per T squared) - Meeus chapter 49, the additional corrections
    (0.000325, 299.77, 0.107408, -0.009173), (0.000165, 251.88, 0.016321, 0.0), (0.000164, 251.83, 26.651886, 0.0),
    (0.000126, 349.42, 36.412478, 0.0), (0.000110, 84.66, 18.206239, 0.0), (0.000062, 141.74, 53.303771, 0.0),
    (0.000060, 207.14, 2.453732, 0.0), (0.000056, 154.84, 7.306860, 0.0), (0.000047, 34.52, 27.261239, 0.0),
    (0.000042, 207.19, 0.121824, 0.0), (0.000040, 291.34, 1.844379, 0.0), (0.000037, 161.72, 24.198154, 0.0),
    (0.000035, 239.56, 25.513099, 0.0), (0.000023, 331.55, 3.592518, 0.0))


def new_moon(k):
    """The new moon of lunation `k` (0 is 2000-01-06), as a Julian Ephemeris Day (TT)."""
    t = k / 1236.85
    jde = 2451550.09766 + 29.530588861 * k + 0.00015437 * t ** 2 - 0.000000150 * t ** 3 + 0.00000000073 * t ** 4
    e = 1.0 - 0.002516 * t - 0.0000074 * t ** 2
    m = 2.5534 + 29.10535670 * k - 0.0000014 * t ** 2 - 0.00000011 * t ** 3
    mp = 201.5643 + 385.81693528 * k + 0.0107582 * t ** 2 + 0.00001238 * t ** 3 - 0.000000058 * t ** 4
    f = 160.7108 + 390.67050284 * k - 0.0016118 * t ** 2 - 0.00000227 * t ** 3 + 0.000000011 * t ** 4
    omega = 124.7746 - 1.56375588 * k + 0.0020672 * t ** 2 + 0.00000215 * t ** 3
    for coefficient, power, a, b, c, d in _NEW_MOON_TERMS:
        jde += coefficient * e ** power * _sin(a * m + b * mp + c * f + d * omega)
    for coefficient, constant, per_k, per_t2 in _PLANETARY:
        jde += coefficient * _sin(constant + per_k * k + per_t2 * t * t)
    return jde


def sun_longitude(jde):
    """The sun's apparent geocentric longitude in degrees at `jde` (Meeus chapter 25, 0.01 degree)."""
    t = (jde - 2451545.0) / 36525.0
    l0 = 280.46646 + 36000.76983 * t + 0.0003032 * t * t
    m = 357.52911 + 35999.05029 * t - 0.0001537 * t * t
    c = ((1.914602 - 0.004817 * t - 0.000014 * t * t) * _sin(m) + (0.019993 - 0.000101 * t) * _sin(2 * m)
         + 0.000289 * _sin(3 * m))
    omega = 125.04 - 1934.136 * t
    return (l0 + c - 0.00569 - 0.00478 * _sin(omega)) % 360.0


def solar_term(year, longitude):
    """The moment (JDE) in `year` when the sun's apparent longitude is `longitude`."""
    # The sun is at 0 degrees about 20 March; a first guess, then Newton's steps of the mean daily motion.
    jde = 2451545.0 + 365.2422 * (year - 2000) + 79.0 + ((longitude - 0.0) % 360.0) * 365.2422 / 360.0 - 0.5
    for _ in range(50):
        step = 58.0 * _sin(longitude - sun_longitude(jde))
        jde += step
        if abs(step) < 1e-7:
            break
    return jde


def _year_of(jde):
    return 2000.0 + (jde - 2451545.0) / 365.25


def _local(jde, zone):
    """(day number, fraction of the local day) of a TT moment, in UTC+`zone`: the day number is a Julian Day Number."""
    ut = jde - delta_t(_year_of(jde)) / 86400.0
    local = ut + zone / 24.0 + 0.5
    day = math.floor(local)
    return day, local - day


def _civil(day):
    """A Julian Day Number as (year, month, day), Gregorian."""
    a = day + 32044
    b = (4 * a + 3) // 146097
    c = a - 146097 * b // 4
    d = (4 * c + 3) // 1461
    e = c - 1461 * d // 4
    m = (5 * e + 2) // 153
    return 100 * b + d - 4800 + m // 10, m + 3 - 12 * (m // 10), e - (153 * m + 2) // 5 + 1


class Calendar:
    """The lunar months around one year, in one time zone, and what lies close to a midnight."""

    def __init__(self, zone=KST):
        self.zone = zone
        self.close = []          # (what, local date, minutes from midnight)

    def _day(self, jde, what):
        day, part = _local(jde, self.zone)
        minutes = min(part, 1.0 - part) * 1440.0
        self.close.append((what, _civil(day), minutes))
        return day

    def months(self, year):
        """The months from the one holding the winter solstice of `year - 1` to the one holding that of `year`, as
        [(first day, number, leap)], the next month 11's first day last."""
        first = self._day(solar_term(year - 1, 270.0), "winter solstice")
        last = self._day(solar_term(year, 270.0), "winter solstice")
        k = math.floor((year - 1 - 2000) * 12.3685) - 2
        starts = []
        while True:
            start = self._day(new_moon(k), "new moon")
            if start > last:
                break
            starts.append(start)
            k += 1
        terms = []
        for y in (year - 1, year):
            for longitude in range(0, 360, 30):
                terms.append(self._day(solar_term(y, float(longitude)), "principal term %d" % longitude))
        # From the month that holds the first solstice to the one that holds the second.
        begin = max(day for day in starts if day <= first)
        end = max(day for day in starts if day <= last)
        span = [day for day in starts if begin <= day <= end]
        count = len(span) - 1
        leap_found = count == 12
        months, number = [], 11
        for index in range(count):
            holds = any(span[index] <= term < span[index + 1] for term in terms)
            leap = not leap_found and not holds and index > 0
            if leap:
                leap_found = True
                months.append((span[index], number, True))
                continue
            if index > 0:
                number = number % 12 + 1
            months.append((span[index], number, False))
        months.append((span[-1], 11, False))
        return months

    def days(self, year):
        """(seollal, chuseok) of `year`, each (year, month, day)."""
        months = self.months(year)
        seollal = next(day for day, number, leap in months if number == 1 and not leap)
        chuseok = next(day for day, number, leap in months if number == 8 and not leap) + 14
        return _civil(seollal), _civil(chuseok)


def lunar_days(first, last, zone=KST):
    """LUNAR_DAYS for the years `first` to `last`: ((seollal, (dates)), (chuseok, (dates)))."""
    calendar = Calendar(zone)
    found = [calendar.days(year) for year in range(first, last + 1)]
    return ((SEOLLAL, tuple(pair[0] for pair in found)), (CHUSEOK, tuple(pair[1] for pair in found)))


def close_calls(first, last, zone=KST, minutes=30.0):
    """Every new moon, solstice or principal term from `first - 1` to `last` within `minutes` of a local midnight."""
    calendar = Calendar(zone)
    for year in range(first, last + 1):
        calendar.days(year)
    seen, close = set(), []
    for what, date, off in calendar.close:
        if off < minutes and (what, date) not in seen:
            seen.add((what, date))
            close.append((what, date, round(off, 1)))
    return close


def unsteady(first, last, minutes):
    """The dates that change when every moment moves `minutes` earlier or later (Delta T's and the formulas' error, and
    more): [(key, date, date it becomes)]. None within two minutes from 2026 to 2100; 2092's seollal within five (its new
    moon at 00:02.6 KST, 8 February; only a Delta T past 340 s - about twice the forecast - would make it the 7th)."""
    base, moved = lunar_days(first, last), set()
    for shift in (-minutes, minutes):
        for (key, dates), (_, others) in zip(base, lunar_days(first, last, KST + shift / 60.0)):
            moved.update((key, date, other) for date, other in zip(dates, others) if date != other)
    return sorted(moved)


def main(argv):
    first, last = (int(argv[0]), int(argv[1])) if len(argv) >= 2 else (2026, 2100)
    for key, dates in lunar_days(first, last):
        print(key, dates)
    for minutes in (2, 5, 15):
        print("moves within %d min:" % minutes, unsteady(first, last, minutes))
    for what, date, off in close_calls(first, last):
        print("close: %s on %04d-%02d-%02d, %.1f min from midnight" % ((what,) + date + (off,)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
