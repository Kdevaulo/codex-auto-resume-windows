"""The captured window pictures show the usage reading the envelope says they show.

The Dashboard's Waiting card ends in "Codex usage, read 2m ago: ..." when the watcher's heartbeat carries a usage
reading. The envelope's installation (make_screenshots.pinned_installation) has one - write_heartbeat hands the
heartbeat sample_usage - but until v0.6.16 the capture's (render_window) had none: its mutex holder beats every
second with no reading, and nothing wrote one first, so every captured page lacked the line the envelope promised and
the README motion (which is answered from the envelope's installation) had to strip it to agree. These hold the
capture to writing the envelope's heartbeat before its holder starts, and the store to keeping that reading through
the holder's beats. Nothing is captured: the second test writes a scratch store only.
"""
from __future__ import annotations

import inspect
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import make_screenshots  # noqa: E402


class CaptureHeartbeatTests(unittest.TestCase):
    def test_the_capture_writes_the_envelope_s_heartbeat_before_its_holder_beats(self):
        source = inspect.getsource(make_screenshots.render_window)
        self.assertIn("write_heartbeat(config.Paths(home), now, word)", source,
                      "the capture's installation has no usage reading, so its pictures lack the usage line")
        self.assertLess(source.index("write_heartbeat("), source.index("HOLD_MUTEX"))
        self.assertLess(source.index("seed_compatibility("), source.index("write_heartbeat("),
                        "the heartbeat carries the word the compatibility check gave")

    def test_the_holder_s_beats_keep_the_sample_reading(self):
        from codex_auto_resume import config
        from codex_auto_resume.store import Store
        now = 1_800_000_000.0
        with tempfile.TemporaryDirectory() as name:
            paths = config.Paths(Path(name) / "home")
            paths.state_dir.mkdir(parents=True, exist_ok=True)
            make_screenshots.write_heartbeat(paths, now, "verified")
            with Store(paths.state_dir) as store:
                # As HOLD_MUTEX beats: its own pid and moment, and no reading.
                store.heartbeat(now + 5, pid=1, session_id="screenshot", started_at=now - 5400, ok=True,
                                engine_state="verified", code_version=config.version())
                status = store.watcher_status()
        read_at, windows = make_screenshots.sample_usage(now)
        self.assertEqual(status.get("usage"), {"read_at": read_at, "windows": windows},
                         "the holder's beat dropped the reading the pictures show")


if __name__ == "__main__":
    unittest.main()
