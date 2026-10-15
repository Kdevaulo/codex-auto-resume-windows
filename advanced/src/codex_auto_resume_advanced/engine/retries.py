# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""Codex's own retry settings, written and put back (v0.6.16-beta.4, P8, and the product leaving).

How many times Codex itself retries a request and a stream that failed is two settings of its built-in provider -
`model_providers.openai.request_max_retries` and `stream_max_retries`, 4 and 5 by its documentation. The standard
edition never changes Codex's configuration (B3). With this on, the P8 errand sets both to the person's Attempts (6,
8, 10 or 12; 8 by default, Q14) through Codex's own app server - config/value/write with an `expectedVersion`, so a
change made meanwhile refuses the write: Codex writes its own config.toml, and this product never opens it (B2).

Each prior value - or that there was none - is kept in the state's `codex_config` (version 5, state/runs.py) before
anything is written, and read back after. Turned off, read down by a policy, or when the product leaves (core's
Plug.leaving: uninstall, an edition change, an older version), each key whose value is still ours is put back - its
prior value written, or the key removed where there was none - and one the person changed since is left theirs
(left_theirs). A version conflict is read again and tried once. Codex reads the file when it starts, so the change
takes effect at its next start; whether it honours the keys for its built-in provider is not something this product
can see, and MB proves only the write, its read back and its removal.

Every write is made inside core's errand guard, a guard for each, so a Pause or Observe only that committed first
refuses it; nothing is written while recovery is paused (K5), so a turn-off during a Pause puts the values back
when recovery resumes - which its statement says.
"""
from __future__ import annotations

from codex_auto_resume.domain.plug import DEFER

from ..codex import inuse
from ..codex.protocol import Session
from ..state.schema import CONFIG_KEYS
from ..vocabulary import ConfigOutcome, OptionKey

CAPABILITY = "codex_retry_settings"
ATTEMPTS = (6, 8, 10, 12)
DEFAULT_ATTEMPTS = 8
READ, WRITE = "config/read", "config/value/write"


def _value(read, key):
    """`key`'s value in what config/read answered (the configuration in force), or None."""
    value = read.get("config") if isinstance(read, dict) else None
    for part in key.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value if type(value) is int and 0 <= value <= 1000 else (None if value is None else "other")


def _version(read):
    found = read.get("version") if isinstance(read, dict) else None
    return found if isinstance(found, (str, int)) and not isinstance(found, bool) else None


def _refused(exc) -> bool:
    return getattr(exc, "method", None) == WRITE


class Writer:
    """Writes the two keys, and puts them back, over one session of the capability's methods - each write inside a
    guard of its own, where one is given (`guard()` makes one; None, in the product leaving, none is needed: the
    watcher is stopped)."""

    def __init__(self, state, session, guard=None):
        self.state, self.session, self.guard = state, session, guard

    def _write(self, key, value, read):
        params = {"keyPath": key, "value": value, "mergeStrategy": "upsert" if value is not None else "replace",
                  "expectedVersion": _version(read)}
        if self.guard is None:
            return self.session.call(WRITE, params)
        with self.guard() as permitted:
            if permitted is not True:
                return None
            sequence = self.session.submit(WRITE, params)
        return self.session.receive(WRITE, sequence, params)

    def apply(self, wanted) -> dict:
        """Both keys at `wanted`: {key: outcome}. A prior is kept before its key is written; a key already ours
        and at `wanted` is left alone."""
        done = {}
        rows = self.state.config_rows()
        read = self.session.call(READ, {"includeLayers": True})
        for key in CONFIG_KEYS:
            current = _value(read, key)
            row = rows.get(key)
            if row is not None and row["outcome"] == ConfigOutcome.APPLIED and current == wanted:
                continue
            if current == "other":
                done[key] = ConfigOutcome.REFUSED      # a value of no shape this knows: never written over
                continue
            if row is None or row["outcome"] != ConfigOutcome.APPLIED:
                self.state.config_written(key, prior_present=current is not None, prior_value=current,
                                          written_value=wanted)
            try:
                if self._write(key, wanted, read) is None:
                    continue                           # the guard refused: the next tick tries again
            except Exception as exc:
                if _refused(exc):
                    self.state.config_ended(key, ConfigOutcome.REFUSED)
                    done[key] = ConfigOutcome.REFUSED
                continue
            read = self.session.call(READ, {"includeLayers": True})
            done[key] = ConfigOutcome.APPLIED if _value(read, key) == wanted else ConfigOutcome.REFUSED
            if done[key] == ConfigOutcome.REFUSED:
                self.state.config_ended(key, ConfigOutcome.REFUSED)
        return done

    def restore(self) -> dict:
        """Every key still ours put back: {key: outcome} - restored, left_theirs, or refused."""
        done = {}
        for key, row in self.state.config_rows().items():
            if row["outcome"] != ConfigOutcome.APPLIED:
                continue
            for attempt in (1, 2):
                read = self.session.call(READ, {"includeLayers": True})
                if _value(read, key) != row["written_value"]:
                    done[key] = ConfigOutcome.LEFT_THEIRS
                    break
                prior = row["prior_value"] if row["prior_present"] else None
                try:
                    answered = self._write(key, prior, read)
                except Exception as exc:
                    if _refused(exc) and attempt == 1:
                        continue                       # a change meanwhile (R10): read again, once
                    done[key] = ConfigOutcome.REFUSED
                    break
                if answered is None:
                    break                              # the guard refused: the next tick tries again
                done[key] = ConfigOutcome.RESTORED
                break
            if key in done:
                self.state.config_ended(key, done[key])
        return done


def _session(paths, backend=None):
    return Session(backend if backend is not None else inuse.backend(paths), capability=CAPABILITY)


class _Errand:
    __slots__ = ("code", "restore")

    def __init__(self, code, restore):
        self.code, self.restore = code, restore

    def run(self, guard):
        return self.code.run(guard, restore=self.restore)


class RetrySettings:
    """The capability's code: its hook at P8. Its seams are the tests': `session` opens the app-server session (None:
    a live one against the Codex the watcher drives), `state` is the edition's state (the runtime's, given at bind)."""
    __slots__ = ("paths", "_scoped", "_open", "state")

    def __init__(self, paths, *, session=None, state=None):
        self.paths, self._scoped, self._open, self.state = paths, None, session, state

    def bind(self, scoped):
        self._scoped = scoped
        if self.state is None:
            self.state = getattr(scoped, "config", None)

    def _wanted(self) -> int:
        try:
            chosen = self._scoped.options().get(OptionKey.ATTEMPTS, DEFAULT_ATTEMPTS)
        except Exception:
            chosen = DEFAULT_ATTEMPTS
        return chosen if chosen in ATTEMPTS else DEFAULT_ATTEMPTS

    def tick(self, view):
        """P8: an errand that sets the two keys, while they are not at the person's choice."""
        if self._scoped is None or self.state is None:
            return DEFER
        try:
            rows = self.state.config_rows()
        except Exception:
            return DEFER
        wanted = self._wanted()
        settled = all(rows.get(key, {}).get("outcome") == ConfigOutcome.APPLIED
                      and rows[key].get("written_value") == wanted for key in CONFIG_KEYS)
        return DEFER if settled else _Errand(self, restore=False)

    def run(self, guard, *, restore):
        session = self._open() if self._open is not None else _session(self.paths)
        with session:
            writer = Writer(self.state, session, guard)
            done = writer.restore() if restore else writer.apply(self._wanted())
        for outcome in done.values():
            if self._scoped is not None:
                self._scoped.count(str(outcome))
        return None


def pending(state) -> bool:
    """Whether a key the edition wrote is still ours: what turning it off, or the product leaving, puts back."""
    try:
        return any(row["outcome"] == ConfigOutcome.APPLIED for row in state.config_rows().values())
    except Exception:
        return False


def restore_errand(runtime, definition):
    """The errand that puts the keys back while the capability stands off (runtime.tick), or None."""
    if not pending(runtime.state):
        return None
    code = runtime._code_of(definition)
    return _Errand(code, restore=True)


def leave(state, backend) -> dict:
    """The product leaving (core's prepare-leave, Plug.leaving): every key still ours put back, with the watcher
    stopped - {key: outcome}. Raises where no session can be opened; the caller prints the keys then."""
    if not pending(state):
        return {}
    with _session(None, backend) as session:
        return Writer(state, session).restore()


def make(paths) -> RetrySettings:
    """The capability's factory (registry.CapabilityDef.make): its code for one installation."""
    return RetrySettings(paths)
