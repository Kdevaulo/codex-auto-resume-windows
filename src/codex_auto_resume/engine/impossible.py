"""Whether recovery cannot work here (v0.6.26, the update-resilience proposals 1 and 3): a judge of the watcher's own looks.

An update - mostly Codex's - can leave every waiting recovery waiting for ever under a word that is not true: "open in
another Codex session" (#67), "not open in the Codex app", "usage could not be read". Each look of the watcher is put
here as a handful of facts it already has, and when one of the contradictions below has held long enough, one word says
so to a person. It never sends, never holds anything back and never decides that a conversation is open: the loaded
state is still the Restart Manager's alone (B12), and every gate runs as it did.

The recovery rules, each judged only while a process of the Codex app runs and a record waits for it:

    held_elsewhere   (a) a record waits `held_by_other_session` or `loaded_state_unknown`, its writer lock's holder
                     holds the newest queue or state database, and the paired server holds neither - #67's signature
    locks_unread     (b) a record waits `notLoaded` or `loaded_state_unknown`, the paired server holds the newest
                     databases, and the thread-writer-locks folder is not there - since update resilience #4 a home
                     without that folder answers "unknown" (codex/transport.py loaded), so its records wait
                     `loaded_state_unknown` and never `notLoaded`
    stale_database   (c) a newer database generation is held by nobody while the paired server holds an older one
    usage_protocol   (d) a record has waited 30 minutes on a usage read Codex answered in a way this version does not
                     know (engine/outcome.py, the usage_probe_broken_* reasons)

and the detection rules, judged while a process of the Codex app runs, whether or not anything waits:

    engine_missing       no Codex engine could be found or checked, 3 ticks running
    history_unreadable   Codex's history could not be read for detection, 3 ticks running

What keeps it from crying wolf: nothing is judged while no process of the app runs; a real terminal or VS Code session
leaves the paired server holding the databases, so (a) does not hold; a recovery rule holds only over HOLD_SECONDS of
looks at most GAP_SECONDS apart, at least LOOKS of them; and a rule is cleared by the first look that does not find it.

Pure: the facts are handed in (runtime/loop.py gathers them), and the clock is the caller's.
"""
from __future__ import annotations

# The words themselves, and what the watcher writes of them beside its heartbeat, are domain/public.py's: a surface
# reads them there without importing the engine.
from ..domain.public import DETECTION_RULES, RECOVERY_RULES, WORDS  # noqa: F401

# How long a recovery rule holds before it is said, and (d)'s, which waits on usage reads a usage limit spaces out.
HOLD_SECONDS = 600.0
USAGE_HOLD_SECONDS = 1800.0
# Looks further apart than this - a PC that slept, a watcher that was busy - start the count again.
GAP_SECONDS = 300.0
# The fewest looks a recovery rule must hold on; and the ticks running a detection rule must.
LOOKS = 5
TICKS = 3
# How often the watcher looks for the recovery rules: each look asks the Restart Manager a few files.
LOOK_EVERY_SECONDS = 60.0

# The reasons each recovery rule reads on a waiting record.
ELSEWHERE_REASONS = frozenset({"held_by_other_session", "loaded_state_unknown"})
NOT_LOADED_REASONS = frozenset({"notLoaded"})
# Rule (b): what a record of a home without its lock folder waits under - "unknown" since #4, "notLoaded" before it (a
# record that waited then, or a folder that is there and empty).
LOCKS_UNREAD_REASONS = NOT_LOADED_REASONS | frozenset({"loaded_state_unknown"})
USAGE_BROKEN_REASONS = frozenset({"usage_probe_broken_answer", "usage_probe_broken_request",
                                  "usage_probe_broken_start"})


# v0.6.26 (proposal 7): which way a usage read broke, by what the helper last met (codex/appserver.py RESULTS): Codex
# answered for another home or system, or with a usage answer this version does not read; refused the request; or did
# not answer at all.
_USAGE_BROKEN = {"protocol_home_mismatch": "usage_probe_broken_answer",
                 "protocol_platform_mismatch": "usage_probe_broken_answer",
                 "protocol_reply_unknown": "usage_probe_broken_answer",
                 "protocol_request_failed": "usage_probe_broken_request",
                 "protocol_unavailable": "usage_probe_broken_start",
                 "protocol_timeout": "usage_probe_broken_start"}
USAGE_METHOD = "account/rateLimits/read"


def usage_reason(limits, results):
    """The reason a record waits on a usage read that said neither available nor not (`limits`, the backend's usage()
    answer), given what the helper last met (`results`, the backend's protocol_results): a usage_probe_broken_* reason
    where that names how it broke, else usage_unknown, as it always was."""
    reason = limits.get("reason") if isinstance(limits, dict) else None
    if reason == "usage_snapshot_unknown":
        return "usage_probe_broken_answer"
    if reason != "usage_probe_unavailable" or not isinstance(results, dict):
        return "usage_unknown"
    own, start = results.get(USAGE_METHOD), results.get("initialize")
    if start is not None and start[0] != "ok" and (own is None or start[1] > own[1]):
        own = start
    return _USAGE_BROKEN.get(own[0] if isinstance(own, tuple) else None, "usage_unknown")


def recovery_facts(*, matched, server, reasons, lock_holders, database_holders, locks_folder, older_holders):
    """{rule: True | False | None} for one look, from what was read: `matched`, whether the app's server is paired;
    `server`, its pid; `reasons`, the waiting records' reasons; `lock_holders`, the pids holding the writer lock of a
    record waiting elsewhere or unknown; `database_holders`, the pids holding the newest queue or state database (None
    where it could not be asked); `locks_folder`, whether thread-writer-locks is there; `older_holders`, for each kind
    whose newest generation nobody holds, the pids holding an older one. None is "not judged"."""
    if not matched or not isinstance(server, int) or database_holders is None:
        return dict.fromkeys(RECOVERY_RULES[:3])
    holds = server in database_holders
    elsewhere = bool(reasons & ELSEWHERE_REASONS) and not holds and any(
        pid != server and pid in database_holders for pid in lock_holders)
    unread = bool(reasons & LOCKS_UNREAD_REASONS) and holds and locks_folder is False
    stale = not holds and any(server in pids for pids in older_holders)
    return {"held_elsewhere": elsewhere, "locks_unread": unread, "stale_database": stale}


class Judge:
    """The watcher's judge of its own looks: `look` for the recovery rules, `tick` for the detection rules, and `word`,
    the one word to say now or None."""

    def __init__(self):
        self._since = {}            # rule -> (first time, looks, last time)
        self._ticks = dict.fromkeys(DETECTION_RULES, 0)

    def look(self, now, app_runs, facts):
        """One look for the recovery rules. `facts` maps a rule to True (it holds), False or None (not judged); a rule
        not named, and every rule where no process of the app runs, is not judged - and neither keeps its count."""
        for rule in RECOVERY_RULES:
            found = facts.get(rule) if app_runs is True else None
            if found is not True:
                self._since.pop(rule, None)
                continue
            first, looks, last = self._since.get(rule, (now, 0, now))
            if now - last > GAP_SECONDS or now < last:
                first, looks = now, 0
            self._since[rule] = (first, looks + 1, now)

    def tick(self, app_runs, facts):
        """One tick for the detection rules: `facts` maps engine_missing and history_unreadable to whether each was
        met this tick. Counted only while a process of the app runs; a tick that did not meet one starts it again."""
        for rule in DETECTION_RULES:
            self._ticks[rule] = self._ticks[rule] + 1 if app_runs is True and facts.get(rule) is True else 0

    def word(self, now):
        """The word to say now - "detection_blocked:<rule>" or "recovery_blocked:<rule>", the first of WORDS that
        holds - or None."""
        for rule in DETECTION_RULES:
            if self._ticks[rule] >= TICKS:
                return "detection_blocked:" + rule
        for rule in RECOVERY_RULES:
            held = self._since.get(rule)
            hold = USAGE_HOLD_SECONDS if rule == "usage_protocol" else HOLD_SECONDS
            if held is not None and held[1] >= LOOKS and now - held[0] >= hold:
                return "recovery_blocked:" + rule
        return None
