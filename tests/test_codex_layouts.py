"""Every Codex layout this product has met, run through the pairing, discovery and the other-session test (v0.6.26).

Update resilience #6 and #11 (the owner's approval of 2026-11-22). Each Codex update that left recovery waiting moved
the app's processes, and each fix was tested on its own layout alone. `LAYOUTS` holds every known one as the inventory
lists it - since v0.6.26 with each process's creation time and package family - with the Restart Manager's holders of
Codex's newest databases, and what this version must make of it: the server it pairs (or the refusal), the engines the
app is seen serving, the engine discovery drives, the conversations it calls another session's, and the shape the
watcher's look names (codex/layout.py). A rule reverted fails the layout it was made for: the walk through a helper
fails 26.1117, the holder fails 26.930, the creation time fails the reused pid, the package family a renamed main.

The watcher's side - the look said in the log when the engine's file or the app's version changes, and the last good
pairing kept across this product's own update - is `WatchTests`. Fixture rows and a scratch LOCALAPPDATA only: no
process is read and none is started.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from codex_auto_resume import config, windows as w
from codex_auto_resume.codex import layout, pairing
from codex_auto_resume.domain.ids import CODEX_APP_FAMILY

NATIVE = r"C:\Program Files"
PROFILE = r"C:\Users\ExampleUser"


def folder(version):
    return NATIVE + r"\WindowsApps\OpenAI.Codex_%s_x64__2p2nqsd0c76g0" % version


def app(version):
    return folder(version) + r"\app\ChatGPT.exe"


EXTENSION = PROFILE + r"\.vscode\extensions\openai.chatgpt-26.1.0-win32-x64\bin\windows-x86_64\codex.exe"
SHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def p(pid, parent, path, created, family=None):
    return {"pid": pid, "parent": parent, "path": path, "created": created, "family": family}


def main(version, pid=10, created=100):
    return p(pid, 1, app(version), created, CODEX_APP_FAMILY)


# Each layout: its rows (engine paths as keys: "a" and "b" are bin\<hex>\codex.exe folders, "package" the app's own
# engine), which bin folders exist, the configured engine, the holders of Codex's newest databases (pids), and what
# this version makes of it. `pair` is the server's pid or the refusal; `served` the engines the app runs; `found` the
# engine discovery drives (None: it refuses); `sessions` the holders `session_kind` calls another session's (True) or
# not (False); `shape` the watcher's word.
LAYOUTS = (
    {"name": "26.915: the app server, the main's one child",
     "rows": lambda: [main("26.915.1.0"), p(20, 10, "a", 200)], "bin": ("a",), "engine": "a", "holders": (20,),
     "pair": 20, "served": {"a"}, "found": "a", "sessions": {20: False}, "shape": "single_child"},
    {"name": "26.930: the app server and the exec-server, both the main's children",
     "rows": lambda: [main("26.930.2377.0"), p(20, 10, "a", 200), p(21, 10, "a", 210)], "bin": ("a",),
     "engine": "a", "holders": (20,), "pair": 20, "served": {"a"}, "found": "a", "sessions": {20: False, 21: False},
     "shape": "two_children"},
    # No process shape was recorded for 26.1007; it came between 26.930 and 26.1111, both of whose shapes it shares.
    {"name": "26.1007: as 26.930",
     "rows": lambda: [main("26.1007.9446.0"), p(20, 10, "a", 200), p(21, 10, "a", 210)], "bin": ("a",),
     "engine": "a", "holders": (20,), "pair": 20, "served": {"a"}, "found": "a", "sessions": {20: False},
     "shape": "two_children"},
    {"name": "26.930.7945: rebuilt into a new bin folder, the old one left (2026-10-07)",
     "rows": lambda: [main("26.930.7945.0"), p(20, 10, "b", 200)], "bin": ("a", "b"), "engine": "a",
     "holders": (20,), "pair": "desktop_server_missing_or_ambiguous", "served": {"b"}, "found": "b",
     "sessions": {20: False}, "shape": "single_child"},
    {"name": "26.1111 (#58): the engine in the app's own package, none in bin",
     "rows": lambda: [main("26.1111.1.0"), p(20, 10, "package", 200)], "bin": (), "engine": "package",
     "holders": (20,), "pair": 20, "served": {"package"}, "found": "package", "sessions": {20: False},
     "shape": "single_child"},
    {"name": "26.1117 (#67): the app server under the package's utility process, the exec-server under the main",
     "rows": lambda: [main("26.1117.4957.0"), p(11, 10, app("26.1117.4957.0"), 110, CODEX_APP_FAMILY),
                      p(12, 10, app("26.1117.4957.0"), 120, CODEX_APP_FAMILY), p(20, 11, "a", 200),
                      p(21, 10, "a", 210)], "bin": ("a",), "engine": "a", "holders": (20,), "pair": 20,
     "served": {"a"}, "found": "a", "sessions": {20: False, 21: False}, "shape": "helper_parented"},
    {"name": "the managed app-server daemon: a server no app process runs",
     "rows": lambda: [main("26.1117.4957.0"), p(20, 5, "daemon", 200)], "bin": ("a",), "engine": "a",
     "holders": (20,), "pair": "desktop_server_missing_or_ambiguous", "served": set(), "found": "a",
     "sessions": {20: False}, "shape": "starting"},
    {"name": "a TUI started in the app's own terminal, beside the app's server",
     "rows": lambda: [main("26.1117.4957.0"), p(11, 10, app("26.1117.4957.0"), 110, CODEX_APP_FAMILY),
                      p(20, 11, "a", 200), p(30, 11, SHELL, 300, CODEX_APP_FAMILY), p(31, 30, "a", 310)],
     "bin": ("a",), "engine": "a", "holders": (20, 31), "pair": 20, "served": {"a"}, "found": "a",
     "sessions": {31: True, 20: False}, "shape": "helper_parented"},
    {"name": "VS Code's own engine beside the app",
     "rows": lambda: [main("26.1117.4957.0"), p(20, 10, "a", 200), p(40, 6, EXTENSION, 400)], "bin": ("a",),
     "engine": "a", "holders": (20, 40), "pair": 20, "served": {"a"}, "found": "a",
     "sessions": {40: True, 20: False}, "shape": "single_child"},
    {"name": "a reused pid: a TUI whose ended shell's id a helper of the app was given (audit-core C1)",
     "rows": lambda: [main("26.1117.4957.0"), p(999, 10, app("26.1117.4957.0"), 900, CODEX_APP_FAMILY),
                      p(40, 999, "a", 400)], "bin": ("a",), "engine": "a", "holders": (40,),
     "pair": "desktop_server_missing_or_ambiguous", "served": set(), "found": "a", "sessions": {40: True},
     "shape": "starting"},
    {"name": "a renamed main (update resilience #5)",
     "rows": lambda: [p(10, 1, folder("26.1200.1.0") + r"\OpenAI Codex.exe", 100, CODEX_APP_FAMILY),
                      p(20, 10, "a", 200)], "bin": ("a",), "engine": "a", "holders": (20,), "pair": 20,
     "served": {"a"}, "found": "a", "sessions": {20: False}, "shape": "single_child"},
    {"name": "the app closed: a TUI alone",
     "rows": lambda: [p(30, 5, "a", 300)], "bin": ("a",), "engine": "a", "holders": (30,),
     "pair": "desktop_main_missing_or_ambiguous", "served": None, "found": "a", "sessions": {30: True},
     "shape": "closed"},
)


class Case(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.local = self.root / "local"
        self.home = self.root / "codex-home"
        self.home.mkdir()
        for name in ("state_5.sqlite", "queue_1.sqlite"):
            (self.home / name).write_bytes(b"")
        self.engines = {"a": self.local / "OpenAI/Codex/bin/aaaa/codex.exe",
                        "b": self.local / "OpenAI/Codex/bin/bbbb/codex.exe",
                        "package": Path(folder("26.1111.1.0") + r"\app\resources\codex.exe"),
                        "daemon": self.home / "packages/app-server-daemon/releases/1.0/bin/codex.exe"}
        for stub in (patch.dict(os.environ, {"ProgramW6432": NATIVE, "LOCALAPPDATA": str(self.local),
                                             "USERPROFILE": PROFILE}),
                     patch.object(pairing, "process_identity", side_effect=self.identity)):
            stub.start()
            self.addCleanup(stub.stop)
        self.rows = []

    def identity(self, pid):
        for each in self.rows:
            if each["pid"] == pid:
                return {"pid": pid, "created": each["created"], "path": each["path"].lower()}
        raise w.AdapterError("process_exited")

    def path(self, key):
        return str(self.engines[key]) if key in self.engines else key

    def made(self, case):
        """The layout's rows with its engines' paths, and its bin folders made."""
        for key in case["bin"]:
            self.engines[key].parent.mkdir(parents=True, exist_ok=True)
            self.engines[key].write_bytes(b"")
        self.rows = [dict(each, path=self.path(each["path"])) for each in case["rows"]()]
        return self.rows

    def holders(self, case):
        return [{"pid": each["pid"], "created": each["created"]} for each in self.rows if each["pid"] in case["holders"]]


class LayoutTests(Case):
    def test_every_layout(self):
        for case in LAYOUTS:
            with self.subTest(case["name"]):
                self.check(case)
                for key in case["bin"]:
                    self.engines[key].unlink()

    def check(self, case):
        rows = self.made(case)
        engine = self.path(case["engine"])
        seen = {}
        with patch.object(pairing, "resource_users", return_value=self.holders(case)):
            try:
                found = w.desktop_pair(rows, engine, self.home, seen=seen)["server"]["pid"]
            except w.AdapterError as error:
                found = str(error)
        self.assertEqual(found, case["pair"], "the pairing")
        if case["served"] is None:
            with self.assertRaises(w.AdapterError):
                pairing.server_engines(rows)
        else:
            self.assertEqual(pairing.server_engines(rows), frozenset(self.path(key) for key in case["served"]),
                             "the engines the app is seen serving")
        for pid, other in case["sessions"].items():
            held = {"pid": pid, "created": next(each["created"] for each in rows if each["pid"] == pid)}
            self.assertEqual(pairing.session_kind(rows, held, engine), other, "session_kind of %d" % pid)
        self.assertEqual(self.discovered(rows), self.path(case["found"]) if case["found"] else None, "discovery")
        self.assertEqual(layout.snapshot(rows, engine, seen)["shape"], case["shape"], "the watcher's shape")

    @staticmethod
    def discovered(rows):
        """The engine the watcher's discovery drives (config.discover_codex_exe, as App.backend asks it), every
        candidate passing its checks, or None where it refuses."""
        try:
            return str(config.discover_codex_exe(None, lambda path: None, running=lambda: pairing.server_engines(rows),
                                                 ask_app=False, ask_app_if_none=True))
        except config.ConfigError:
            return None

    def test_every_shape_the_look_names_is_a_catalogued_layout(self):
        named = {case["shape"] for case in LAYOUTS}
        self.assertEqual(named, set(layout.SHAPES.values()))
        self.assertTrue(layout.catalogued(layout.snapshot([], None)), "nothing running is the closed shape")
        engine = self.path("a")
        three = [main("26.1300.1.0"), p(20, 10, engine, 200), p(21, 10, engine, 210), p(22, 10, engine, 220)]
        self.assertFalse(layout.catalogued(layout.snapshot(three, engine)), "three children is no shape tested on")

    def test_the_snapshot_keeps_no_path(self):
        case = LAYOUTS[5]
        found = layout.snapshot(self.made(case), self.path("a"), {"server_holds": True})
        self.assertEqual(found["app_version"], "26.1117.4957.0")
        self.assertEqual((found["mains"], found["helpers"], found["engines_under_main"], found["engines_under_helper"]),
                         (1, 2, 1, 1))
        text = repr(found).lower()
        for part in ("windowsapps", "codex.exe", "chatgpt.exe", "\\"):
            self.assertNotIn(part, text)


class WatchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.file = Path(temp.name) / "config" / "codex-layout.json"
        self.lines = []
        self.paired = dict(layout.snapshot([], None), mains=1, engines_under_main=1, app_version="26.1117.4957.0",
                           paired=True, shape="single_child")
        self.unpaired = dict(self.paired, paired=False, engines_under_main=0, engines_elsewhere=1, shape="starting")

    def watch(self, version):
        return layout.Watch(self.file, version, self.lines.append)

    def test_the_layout_is_said_once_per_engine_file_and_app_version(self):
        watch = self.watch("0.6.26")
        watch.look(self.paired, stamp=(1, 1), engine_version="codex-cli 0.160.0")
        watch.look(self.paired, stamp=(1, 1), engine_version="codex-cli 0.160.0")
        self.assertEqual(len(self.lines), 1)
        watch.look(self.paired, stamp=(2, 2), engine_version="codex-cli 0.161.0")
        watch.look(dict(self.paired, app_version="26.1200.1.0"), stamp=(2, 2), engine_version="codex-cli 0.161.0")
        self.assertEqual(len(self.lines), 3)
        self.assertTrue(all(line.startswith("Codex layout: ") for line in self.lines))

    def test_a_layout_not_tested_on_is_said(self):
        watch = self.watch("0.6.26")
        kept = watch.look(dict(self.paired, engines_under_main=3, shape=None), stamp=(1, 1))
        self.assertIn("Codex 26.1117.4957.0 runs in a layout this version has not been tested on", self.lines)
        self.assertFalse(kept["catalogued"])
        self.assertFalse(layout.read(self.file)["catalogued"])

    def test_the_last_good_pairing_is_kept_across_this_products_update(self):
        """Update resilience #11: fails with the rule reverted - nothing said where the new version pairs nothing."""
        self.watch("0.6.25").look(self.paired, stamp=(1, 1), engine_version="codex-cli 0.160.0")
        kept = layout.read(self.file)
        self.assertEqual(kept["last_good"]["code_version"], "0.6.25")
        self.assertFalse(kept["unpaired_after_update"])
        watch = self.watch("0.6.26")
        self.assertEqual(watch.updated_from, "0.6.25")
        watch.look(self.unpaired, stamp=(1, 1), engine_version="codex-cli 0.160.0")
        kept = layout.read(self.file)
        self.assertTrue(kept["unpaired_after_update"])
        self.assertEqual(kept["updated_from"], "0.6.25")
        self.assertEqual(kept["last_good"]["code_version"], "0.6.25", "the last good pairing is the old version's")
        self.assertIn("the first looks since this product was updated from 0.6.25 pair no Codex server, where that "
                      "version paired one", self.lines)
        watch.look(self.paired, stamp=(1, 1), engine_version="codex-cli 0.160.0")
        kept = layout.read(self.file)
        self.assertFalse(kept["unpaired_after_update"])
        self.assertIsNone(kept["updated_from"])
        self.assertEqual(kept["last_good"]["code_version"], "0.6.26")

    def test_no_word_where_the_version_is_the_same_or_the_app_is_closed(self):
        self.watch("0.6.25").look(self.paired, stamp=(1, 1))
        self.assertFalse(self.watch("0.6.25").look(self.unpaired, stamp=(1, 1))["unpaired_after_update"])
        closed = layout.snapshot([], None)
        self.assertFalse(self.watch("0.6.26").look(closed, stamp=(1, 1))["unpaired_after_update"])
        # A watcher started again before any look paired still knows what it was updated from.
        watch = self.watch("0.6.26")
        self.assertEqual(watch.updated_from, "0.6.25")
        self.assertTrue(watch.look(self.unpaired, stamp=(1, 1))["unpaired_after_update"])

    def test_the_watcher_looks_at_each_tick_and_names_a_named_engine(self):
        """runtime/app.py: the backend's snapshot goes to the look, and a named engine is told to the backend (#9)."""
        from codex_auto_resume.runtime.app import App
        paths = config.Paths(self.file.parent.parent)
        paths.ensure()
        watcher = App.__new__(App)
        watcher.paths, watcher.logger = paths, logging.getLogger("test_codex_layouts")
        watcher._backend = types.SimpleNamespace(layout=self.paired, engine_version="codex-cli 0.160.0")
        watcher._backend_stamp = (1, 1)
        watcher._layout_look()
        self.assertEqual(layout.read(paths.codex_layout_file)["layout"]["shape"], "single_child")
        self.assertIn(paths.codex_layout_file, paths.owned_state_files())


if __name__ == "__main__":
    unittest.main()
