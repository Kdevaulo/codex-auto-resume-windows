"""v0.6.26 (review of the fourth round's fixes, C3): K8's count of "starting" looks runs only while the looks run on.

After I1 a snapshot seen before no longer moves the count, but `_starting_since` kept the first look's time across any
stretch with no new look - and looks are made only while a record waits. So one "starting" look, hours with no record,
then one new "starting" look (the app starting, or its server restarting, as a new record is checked) was at once past
STARTING_SECONDS: "runs in a layout this version has not been tested on" in the log and in Diagnostics. Now a fresh look
that comes longer after the one before than two of the watcher's ticks (at least LOOK_GAP_SECONDS; before a tick is
measured, twice STARTING_SECONDS) begins the count again.

Synthetic rows and a scratch folder only (test_pairing_roles' Case for the package folder).
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume.codex import layout  # noqa: E402
import test_pairing_roles as roles  # noqa: E402  (a module, so its cases are not bound here)

STARTING = [roles.MAIN, roles.RENDERER]
PAIRED = [roles.MAIN, roles.RENDERER, roles.row(20, 10, roles.ENGINE, 200)]
HOURS = 3 * 3600.0
RECORD_POLL = 60.0          # engine/options.py state_poll_seconds: a record waiting on the app is looked at again


class GapTests(roles.Case):
    def setUp(self):
        super().setUp()
        self.now, self.lines = 0.0, []
        clock = patch("time.monotonic", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.watch = layout.Watch(self.home / "codex-layout.json", "0.6.26", self.lines.append)

    def look(self, found, at):
        self.now = at
        return self.watch.look(found, stamp=(1, 2), engine_version="0.170.0")["catalogued"]

    def untested(self):
        return [line for line in self.lines if "has not been tested on" in line]

    def test_the_reviews_repro_a_new_starting_look_hours_later_is_tested(self):
        """Fails with the fix reverted: catalogued False at 3 h, and the log said "not tested on"."""
        self.assertIs(self.look(layout.snapshot(STARTING), 0.0), True)
        self.assertIs(self.look(layout.snapshot(STARTING), HOURS), True)
        self.assertIs(self.look(layout.snapshot(PAIRED), HOURS + 5), True)
        self.assertEqual(self.untested(), [])

    def test_hours_of_ticks_on_the_old_look_then_a_new_one(self):
        """The watcher's own pace: every tick hands the same snapshot until a record makes a new one. Fails with the
        fix reverted."""
        old = layout.snapshot(STARTING)
        at = 0.0
        while at < HOURS:
            self.assertIs(self.look(old, at), True, "I1 holds: a snapshot seen before is judged as at its first look")
            at += 60.0
        self.assertIs(self.look(layout.snapshot(STARTING), HOURS), True)
        self.assertIs(self.look(layout.snapshot(STARTING), HOURS + 60), True)
        self.assertEqual(self.untested(), [])

    def test_looks_that_run_on_still_turn_after_ten_minutes(self):
        """K8 holds: a new starting look at every tick."""
        for tick in range(10):
            self.assertIs(self.look(layout.snapshot(STARTING), tick * 60.0), True)
        self.assertIs(self.look(layout.snapshot(STARTING), 600.0), False)
        self.assertEqual(len(self.untested()), 1)

    def test_a_slow_poll_still_counts(self):
        """Ticks fifteen minutes apart (poll_seconds 900), each with a new starting look: one stretch."""
        self.assertIs(self.look(layout.snapshot(STARTING), 0.0), True)
        self.assertIs(self.look(layout.snapshot(STARTING), 900.0), False)
        self.assertIs(self.look(layout.snapshot(STARTING), 1800.0), False)

    def drive(self, tick, until, wake_after=()):
        """The real loop: `look` at every watcher tick with the backend's last snapshot, a fresh one only at the first
        tick after the waiting record is due - every RECORD_POLL seconds (engine/options.py state_poll_seconds, the
        poll of a record waiting on the app) - and, after each tick in `wake_after`, a Retry now wake a second later.
        Returns {time: catalogued}."""
        seen, snapshot, due, at = {}, None, 0.0, 0.0
        while at <= until:
            for when in (at, at + 1.0) if at in wake_after else (at,):
                if when >= due:
                    snapshot, due = layout.snapshot(STARTING), when + RECORD_POLL
                seen[when] = self.look(snapshot, when)
            at += tick
        return seen

    def test_one_record_waiting_on_a_starting_app_turns_at_every_tick_length(self):
        """K8's own case (an app that stays "starting") with one record waiting at its real poll, the watcher ticking at
        every pace its setting allows: it turns once ten minutes of looks have run, as before C3."""
        for tick in (5.0, 30.0, 59.0, 61.0, 100.0, 300.0, 900.0, 3600.0):
            with self.subTest(tick=tick):
                self.setUp()
                seen = self.drive(tick, 4 * 3600.0)
                self.assertTrue(all(seen[when] for when in seen if when < 600.0))
                self.assertFalse(seen[max(seen)], "never turned to not tested on")

    def test_a_retry_now_wake_does_not_break_the_run(self):
        """Fails with c24b93ea7's rule (two of the last tick): a wake a second after each tick made the last tick one
        second, and each next fresh look, a 300-second tick later, began the count again - K8 never fired."""
        seen = self.drive(300.0, 3600.0, wake_after=tuple(300.0 * n for n in range(13)))
        self.assertFalse(seen[max(seen)])

    def test_a_gap_after_ticks_were_measured_begins_again(self):
        for tick in range(5):
            self.look(layout.snapshot(STARTING), tick * 5.0)
        self.assertIs(self.look(layout.snapshot(STARTING), 20.0 + layout.LOOK_GAP_SECONDS + 1), True)
        self.assertIs(self.look(layout.snapshot(STARTING), 20.0 + layout.LOOK_GAP_SECONDS + 1 + 599), True)


if __name__ == "__main__":
    unittest.main()
