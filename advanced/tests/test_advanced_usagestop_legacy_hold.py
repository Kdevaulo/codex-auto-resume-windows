"""review6 A1: the stop kept with Continue after the reset off is a row no version starts the product's continuation from -
this one, or any older one a person goes back to with Install another version.

review4 V4 kept that stop as a waiting continuation WITH the catalog's words, for the carry of a reset message. Every
usage_pause from v0.6.16-beta.4 to v0.6.26-beta starts any waiting AFTER_RESET row that has words, and never reads the
choice: after a downgrade to v0.6.25 or v0.6.26-beta the continuation the person turned off went at the first look after
the reset. The hold is now kept with no words (state.add_held_continuation); the message's words come from its rule.

The older code is read from the tags, out of git and nothing else, as tests/test_legacy_bootstraps.py reads old trees:
v0.6.25's and v0.6.26-beta's whole UsageStop is run on the state this version writes, and every tagged usage_pause's
`_waiting` is asked what it would start. Where the tags are not in the checkout, CI fails and a local checkout skips.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests;tests" python -m unittest test_advanced_usagestop_legacy_hold
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from codex_auto_resume_advanced.engine import usagestop  # noqa: E402
from codex_auto_resume_advanced.engine.usagestop import UsageStop  # noqa: E402
from test_advanced_usagestop_carry import DAY  # noqa: E402
from test_advanced_usagestop_continue_off import ContinueOffCase  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "advanced/src/codex_auto_resume_advanced/engine/usagestop.py"
RUN = ("v0.6.25", "v0.6.26-beta")


def _git(*arguments) -> bytes | None:
    done = subprocess.run(["git", "-C", str(ROOT), *arguments], capture_output=True, timeout=120,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return done.stdout if done.returncode == 0 else None


def tags() -> list:
    """Every tag whose tree has usage_pause's stop (engine/usagestop.py), oldest first by git's version order."""
    listed = (_git("tag", "--list", "v*", "--sort=version:refname") or b"").decode("utf-8").split()
    return [tag for tag in listed if _git("cat-file", "-e", "%s:%s" % (tag, SOURCE)) is not None]


def legacy(tag) -> types.ModuleType:
    """The tag's engine/usagestop.py, loaded as a module of this package (its relative imports resolve here)."""
    name = "codex_auto_resume_advanced.engine._legacy_usagestop_" + tag.replace(".", "_").replace("-", "_")
    # The spec's parent, taken from the name, is the package its relative imports resolve in (module_from_spec sets it).
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    exec(compile(_git("show", "%s:%s" % (tag, SOURCE)).decode("utf-8"), "%s:%s" % (tag, SOURCE), "exec"),
         module.__dict__)
    return module


def _need_tags(case):
    if _git("rev-parse", "--verify", "--quiet", RUN[0]) is None:
        if os.environ.get("CI"):
            case.fail("the tags are not in the checkout (fetch-depth: 0)")
        case.skipTest("the tags are not in this checkout")


class LegacyHold(ContinueOffCase):
    def held(self):
        plug, turn = self.stopped_off()
        (row,) = plug.runtime.state.continuations(capability=self.cap, pending=None)
        self.assertEqual(row["kind"], "after_reset")
        return plug, turn, row

    def test_the_hold_has_no_words(self):
        """Fails with V4's row: the catalog's continuation words were kept on it."""
        _plug, _turn, row = self.held()
        self.assertIsNone(row["words"])

    def test_v0_6_25_and_v0_6_26_beta_start_nothing_from_it(self):
        """Fails with V4's row: each older UsageStop starts the product's continuation at its first look after the
        reset."""
        _need_tags(self)
        for tag in RUN:
            with self.subTest(tag):
                self.starts.clear()
                plug, turn, _row = self.held()
                old = legacy(tag)
                methods = {name: value for name, value in vars(old.UsageStop).items()
                           if callable(value) and not name.startswith("__")}
                with patch.multiple(UsageStop, **methods):
                    self.after_reset(plug, turn)
                    for _ in range(4):
                        self.h.tick(advance=DAY / 4)
                self.assertEqual(self.starts, [], "%s started the continuation the person turned off" % tag)
                self.tearDown()
                self.setUp()

    def test_no_tagged_usage_pause_would_start_it(self):
        """Every tagged usage_pause's own `_waiting` - what its after_reset starts - leaves the hold out."""
        _need_tags(self)
        plug, _turn, _row = self.held()
        code = self.code(plug)
        found = tags()
        self.assertGreaterEqual(len(found), 20)
        for tag in found:
            with self.subTest(tag):
                self.assertEqual(legacy(tag).UsageStop._waiting(code), [])
        self.assertIsNotNone(usagestop)


if __name__ == "__main__":
    unittest.main()
