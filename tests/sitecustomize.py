"""Loaded by Python itself in every interpreter that has tests/ on its path (PYTHONPATH="src;tests", as
every local run of the suite is started): the guard that fails a test which reaches the real Windows toast
(tests/no_real_toast.py), and the one that keeps this PC's Codex processes out of every test
(tests/no_real_codex.py). It never raises: an interpreter must start whatever happens here.

Not a test module (no `test_` prefix), so discovery does not collect it."""
try:
    import no_real_toast as _no_real_toast

    _no_real_toast.install()
except Exception:   # pragma: no cover - a guard that cannot load must not stop the interpreter
    pass
try:
    import no_real_codex as _no_real_codex

    _no_real_codex.install()
except Exception:   # pragma: no cover - the same: never in the way of the interpreter
    pass
