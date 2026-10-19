"""The watcher takes its single-instance mutex before any slow step of its start.

scripts/plugin_setup.py start_watcher waits for this mutex, and no longer than WATCHER_START_TIMEOUT, to say whether the
watcher it started runs. The v0.6.17 live acceptance saw that wait run out on a busy PC; measured, nothing had crept in
front of the mutex. This module holds that start order. It is its own module because tests/test_engine.py is one of the
scenario modules test_released_calls holds byte for byte to the file v0.6.10 had (tests/neutral.py MODULES).

Temporary homes only, and no console window for the child.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SRC = str(Path(__file__).resolve().parents[1] / "src")


class SingleInstanceStartTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows named objects")
    def test_the_mutex_is_taken_before_the_state_the_plug_or_the_engine(self):
        """The start order the setup's confirmation rests on (scripts/plugin_setup.py start_watcher waits for this
        mutex, and no longer than WATCHER_START_TIMEOUT): `cli run` takes the single-instance mutex once its imports
        are done and before any slow step - opening the state, loading the edition's plug (the advanced runtime's
        checks at load), finding the Codex engine, the icon. The v0.6.17 live acceptance suspected v0.6.17's advanced
        work had crept in front of it; measured, none had. This holds it so, read from what a fresh interpreter has
        done at the moment the mutex is taken - not from a clock, which on a CI runner would measure the runner.

        A scratch home: its mutex is named after that state path, never the real watcher's, and the child ends at the
        mutex, before anything that could start a watcher's work."""
        code = (
            "import json, os, sys\n"
            f"sys.path.insert(0, {SRC!r})\n"
            "from codex_auto_resume import cli, edition, store\n"
            "from codex_auto_resume.runtime import app as runtime\n"
            "made = []\n"
            "for kind in (store.Store, store.LegacyStore):\n"
            "    def record(self, *args, _real=kind.__init__, _name=kind.__name__, **kwargs):\n"
            "        made.append(_name)\n"
            "        return _real(self, *args, **kwargs)\n"
            "    kind.__init__ = record\n"
            "real = runtime.App.mutex\n"
            "def mutex(self, timeout=None):\n"
            "    held = real(self, timeout=timeout)\n"
            "    enter = held.__enter__\n"
            "    def taken():\n"
            "        enter()\n"
            "        advanced = sorted(m for m in sys.modules if m.startswith('codex_auto_resume_advanced'))\n"
            "        print(json.dumps({'stores': made, 'plugs': len(edition._plugs), 'plug': self._plug is not None,\n"
            "                          'backend': self._backend is not None, 'tray': self._tray is not None,\n"
            "                          'advanced': advanced}), flush=True)\n"
            "        os._exit(0)\n"
            "    held.__enter__ = taken\n"
            "    return held\n"
            "runtime.App.mutex = mutex\n"
            "cli.main(['--home', sys.argv[1], '--quiet', '--codex-home', sys.argv[2], 'run'])\n"
            "print(json.dumps({'mutex': 'never taken'}), flush=True)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            home, codex = Path(temp) / "home", Path(temp) / "codex"
            codex.mkdir()
            done = subprocess.run([sys.executable, "-c", code, str(home), str(codex)], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=120,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            seen = json.loads(done.stdout.strip().splitlines()[-1])
            self.assertEqual(seen, {"stores": [], "plugs": 0, "plug": False, "backend": False, "tray": False,
                                    "advanced": []})
            self.assertEqual(sorted(path.name for path in (home / "config").glob("*.sqlite*")), [],
                             "nothing opened the state before the mutex")


if __name__ == "__main__":
    unittest.main()
