"""v0.6.26 (fourth round, audit-standards E2 and audit-security D1): no content of codex-layout.json or selfcheck.json
ends the watcher.

`WatchLoop._layout_said` compared the kept counts of config/codex-layout.json with numbers outside every `try` of the
tick, and `layout.read` checked only the format: a count that is text, a list or an object raised TypeError, a deeply
nested file RecursionError, and the watcher's run ended - again at each start, since nothing rewrote the file while no
look paired. The bridge's read of selfcheck.json let RecursionError through too (Python 3.13, within its 4096 bytes).
Now `layout.read` takes at most READ_MOST bytes, keeps only the closed shape, and refuses anything else; the
self-check's look at it costs the look alone; and the self-check reader refuses what cannot be parsed.

A scratch folder only; the process list the self-check asks is a stub.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume.codex import layout  # noqa: E402
from codex_auto_resume.control import watcher as control_watcher  # noqa: E402
from codex_auto_resume.runtime import loop  # noqa: E402
from test_recovery_blocked import Store, Watcher  # noqa: E402

GOOD = {"format": 1, "app_version": "26.1117.0", "catalogued": False,
        "layout": {"mains": 1, "helpers": 0, "engines_under_main": 0, "engines_under_helper": 0,
                   "engines_elsewhere": 0, "shape": None}}
NESTED = '{"format": 1, "layout": ' + "[" * 7000 + "]" * 7000 + "}"
BAD = {
    "a count that is text": json.dumps(dict(GOOD, layout={"mains": "1"})),
    "a count that is a list": json.dumps(dict(GOOD, layout={"mains": [1], "helpers": {"a": 1}})),
    "a layout that is a list": json.dumps(dict(GOOD, layout=[1, 2])),
    "versions that are not text": json.dumps(dict(GOOD, app_version=[1], engine_version={"a": 1}, updated_from=7,
                                                  unpaired_after_update="yes", code_version=None)),
    "a last good look of another shape": json.dumps(dict(GOOD, last_good={"layout": {"mains": "x"}, "app_version": 3})),
    "deeply nested": NESTED,
    "very large": json.dumps(dict(GOOD, padding="x" * 100000)),
    "a format that is true": json.dumps(dict(GOOD, format=True)),
    "not an object": "[1, 2, 3]",
    "not json": "{\"format\": 1, ",
    "not utf-8": b"\xff\xfe{}",
}


class LayoutFileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.watcher = Watcher(Path(temp.name) / "product")
        self.path = self.watcher.paths.codex_layout_file
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stub = patch.object(loop, "app_running_now", return_value=False)
        stub.start()
        self.addCleanup(stub.stop)

    def put(self, content):
        if isinstance(content, bytes):
            self.path.write_bytes(content)
        else:
            self.path.write_text(content, encoding="utf-8")

    def test_no_content_ends_the_self_check(self):
        """Fails with the fix reverted: TypeError (or RecursionError) out of _self_check, which ends the tick loop."""
        for name, content in BAD.items():
            with self.subTest(file=name):
                self.put(content)
                self.watcher._self_check(Store([]), None, 500.0)
                said = self.watcher._layout_said()
                self.assertTrue(all(each is None or isinstance(each, str) for each in said))
                self.assertTrue(self.watcher.paths.self_check_file.is_file())
                kept = layout.read(self.path)
                if kept is not None:
                    self.assertTrue(all(type(kept["layout"][count]) is int for count in layout._COUNTS))
                    self.assertTrue(all(each is None or isinstance(each, str) for each in
                                        (kept["app_version"], kept["engine_version"], kept["updated_from"])))
                watch = layout.Watch(self.path, "0.6.26")
                self.assertIsNotNone(watch.look(layout.snapshot([])))

    def test_a_good_file_is_still_read(self):
        self.put(json.dumps(GOOD))
        self.assertEqual(self.watcher._layout_said(), ("26.1117.0", None))
        self.assertEqual(layout.read(self.path)["layout"]["mains"], 1)

    def test_what_the_watch_writes_reads_back_the_same(self):
        watch = layout.Watch(self.path, "0.6.26")
        kept = watch.look(layout.snapshot([]), stamp=(1, 2), engine_version="codex-cli 0.170.0")
        self.assertEqual(layout.read(self.path), kept)

    def test_a_failure_inside_costs_the_look_alone(self):
        self.put(json.dumps(GOOD))
        with patch.object(Watcher, "_layout_said", side_effect=RecursionError):
            self.watcher._self_check(Store([]), None, 500.0)
        self.assertIn("the self-check", self.watcher.failures)


class SelfCheckFileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.paths = Watcher(Path(temp.name) / "product").paths

    def test_a_nested_selfcheck_file_is_no_self_check(self):
        """Fails with the fix reverted where the parser raises RecursionError, as Python 3.13's does on these 4096
        bytes - and with the parser made to raise it on any."""
        self.paths.self_check_file.write_text("[" * 4096, encoding="utf-8")
        self.assertIsNone(control_watcher.read_self_check(self.paths, {"started_at": 500.0}))
        self.paths.self_check_file.write_text("{}", encoding="utf-8")
        with patch.object(control_watcher.json, "loads", side_effect=RecursionError):
            self.assertIsNone(control_watcher.read_self_check(self.paths, {"started_at": 500.0}))


if __name__ == "__main__":
    unittest.main()
