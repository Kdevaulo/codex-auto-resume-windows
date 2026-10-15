"""v0.6.16-beta.3: words for this time - where they are kept, what they may say, and who may write them.

A person may add words for one waiting recovery on the Dashboard's Pending page; the watcher sends them once, after
that recovery's next continuation (tests/test_once_words_engine.py). They are kept in config/once-words.json beside
the state - no state schema change and no settings key, so a beta's stored formats stay final and an older version
never reads them - written whole under the file's one lock, and read back through the Custom message's own check
every time (A27): an entry that fails is not set, and a file that cannot be believed holds nothing. Diagnostics say
how many there are and never what they say. They are written only in the Dashboard, through the bridge: MCP's
update_settings refuses them, no tool reads or writes them, the preview tool takes no text, and the panel never
shows them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codex_auto_resume import (config, continuation, controlcli, diagnostics, l10n, mcpserver,  # noqa: E402
                               oncewords, settings)
from codex_auto_resume.control import ControlError  # noqa: E402
from codex_auto_resume.store import Store  # noqa: E402
from test_control import KEY, OTHER_KEY, THREAD, ControlTestCase, detection  # noqa: E402
from test_mcp import McpTestCase  # noqa: E402

OTHER_THREAD = "0a1b2c3d-0001-7000-8000-000000000009"
WORDS = "Then run the tests, please."
ROW = {"category": "usage_limit", "recovery_attempts": 0, "reset_at": None, "thread_id": THREAD}


def english(**extra):
    return dict(settings.defaults(), continuation_language="en", **extra)


class StorageCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.held = oncewords.OnceWords(self.folder / oncewords.FILE_NAME)

    def document(self):
        return json.loads(self.held.path.read_text(encoding="utf-8"))


class StorageTests(StorageCase):
    def test_words_are_written_read_and_taken_away_for_one_interruption(self):
        self.held.put(KEY, WORDS, now=100.0)
        self.held.put(OTHER_KEY, "Other words", now=101.0)
        self.assertEqual(self.document(), {KEY: {"text": WORDS, "written_at": 100.0},
                                           OTHER_KEY: {"text": "Other words", "written_at": 101.0}})
        self.assertEqual((self.held.words(KEY), self.held.words(OTHER_KEY), self.held.count()), (WORDS, "Other words", 2))
        self.assertTrue(self.held.remove(KEY))
        self.assertIsNone(self.held.words(KEY))
        self.assertTrue(self.held.remove(KEY), "nothing to take away is not a failure")
        self.assertTrue(self.held.remove(OTHER_KEY))
        self.assertFalse(self.held.path.exists(), "the file goes when it holds nothing")

    def test_a_write_is_whole_or_nothing(self):
        self.held.put(KEY, WORDS, now=100.0)
        before = self.held.path.read_bytes()
        with patch.object(oncewords.os, "replace", side_effect=OSError("refused")):
            with self.assertRaises(oncewords.OnceWordsError) as caught:
                self.held.put(OTHER_KEY, "more", now=101.0)
        self.assertEqual(caught.exception.code, "state_busy")
        self.assertEqual(self.held.path.read_bytes(), before)
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), [oncewords.FILE_NAME],
                         "no temporary file is left behind")

    def test_nothing_is_written_without_the_lock(self):
        with patch.object(oncewords, "Mutex", side_effect=RuntimeError("busy")):
            with self.assertRaises(oncewords.OnceWordsError):
                self.held.put(KEY, WORDS)
            self.assertFalse(self.held.remove(KEY))
        self.assertFalse(self.held.path.exists())

    def test_a_bad_file_is_read_as_nothing(self):
        for text in ("not json", "[]", json.dumps({"words": {}}), "￾", json.dumps({KEY: "bare"}),
                     json.dumps({KEY: {"text": WORDS}}), json.dumps({KEY: {"text": WORDS, "written_at": True}}),
                     json.dumps({KEY.upper(): {"text": WORDS, "written_at": 1}}),
                     json.dumps({"latest": {"text": WORDS, "written_at": 1}})):
            with self.subTest(text=text[:40]):
                self.held.path.write_text(text, encoding="utf-8")
                self.assertEqual(self.held.held(), {})
                self.assertIsNone(self.held.words(KEY))
        self.held.path.write_bytes(b"x" * (oncewords.FILE_LIMIT + 1))
        self.assertEqual(oncewords.read_file(self.held.path)[0], oncewords.READ_INVALID)

    def test_a_bad_entry_is_left_out_and_the_rest_are_kept(self):
        self.held.path.write_text(json.dumps({KEY: {"text": WORDS, "written_at": 1.0},
                                              OTHER_KEY: {"text": "{prompt}", "written_at": 1.0}}), encoding="utf-8")
        self.assertEqual(self.held.held(), {KEY: {"text": WORDS, "written_at": 1.0}})

    def test_at_most_fifty_and_then_a_refusal(self):
        for index in range(oncewords.MAX_ENTRIES):
            self.held.put("%064x" % (index + 1), "go", now=1.0)
        with self.assertRaises(oncewords.OnceWordsError) as caught:
            self.held.put(KEY, "one more")
        self.assertEqual(caught.exception.code, "too_many_messages")
        self.held.put("%064x" % 1, "changed", now=2.0)
        self.assertEqual(self.held.words("%064x" % 1), "changed")
        many = {"%064x" % (index + 1): {"text": "go", "written_at": 1.0} for index in range(oncewords.MAX_ENTRIES + 1)}
        self.held.path.write_text(json.dumps(many), encoding="utf-8")
        self.assertEqual(self.held.held(), {}, "a file of more than fifty is not believed")

    def test_restore_puts_back_only_where_none_were_written_since(self):
        self.assertTrue(self.held.restore(KEY, WORDS, now=1.0))
        self.assertFalse(self.held.restore(KEY, "older words", now=2.0))
        self.assertEqual(self.held.words(KEY), WORDS)
        self.assertFalse(self.held.restore(OTHER_KEY, "{prompt}"))

    def test_prune_takes_what_is_not_kept_and_a_bad_file_with_it(self):
        self.held.put(KEY, WORDS, now=1.0)
        self.held.put(OTHER_KEY, "other", now=1.0)
        self.assertEqual(self.held.prune(lambda key: key == KEY), 1)
        self.assertEqual(set(self.held.held()), {KEY})
        self.assertEqual(self.held.prune(lambda key: True), 0)
        self.held.path.write_text("not json", encoding="utf-8")
        self.held.prune(lambda key: True)
        self.assertFalse(self.held.path.exists())

    def test_it_is_owned_state_a_purge_takes(self):
        paths = config.Paths(self.folder / "home")
        paths.ensure()
        self.assertEqual(paths.once_words_file, paths.state_dir / oncewords.FILE_NAME)
        oncewords.OnceWords.of(paths).put(KEY, WORDS)
        (paths.state_dir / "once-words.1234.tmp").write_text("{}", encoding="utf-8")
        owned = paths.owned_state_files()
        self.assertIn(paths.once_words_file, owned)
        self.assertIn(paths.state_dir / "once-words.1234.tmp", owned)


class ValidationTests(unittest.TestCase):
    def test_they_are_checked_as_a_custom_message_is(self):
        self.assertEqual(oncewords.validate("x" * continuation.MAX_CUSTOM_LENGTH), "x" * 2000)
        self.assertEqual(oncewords.validate("  as typed\n\n"), "  as typed\n\n")
        for text, code in (("x" * 2001, "too_long"), ("{prompt}", "forbidden_placeholder"),
                           ("{username}", "forbidden_placeholder"), ("{nope}", "unknown_placeholder"),
                           ("   ", "empty"), (5, "not_text")):
            with self.subTest(code=code), self.assertRaises(continuation.CustomMessageError) as caught:
                oncewords.validate(text)
            self.assertEqual(caught.exception.code, code)

    def test_they_go_after_the_continuation_one_blank_line_between_and_filled_in(self):
        joined = continuation.with_once_words("Continue.", "Kind {category}; {reason}.", "usage_limit", english(),
                                              row=ROW)
        self.assertEqual(joined, "Continue.\n\nKind usage_limit; %s." % l10n.text("reason.usage_limit", "en"))
        self.assertEqual(continuation.with_once_words("Continue.", "  as typed  ", "usage_limit", english(), row=ROW),
                         "Continue.\n\n  as typed  ")

    def test_they_are_never_added_where_they_may_not_be(self):
        for words in (None, "{prompt}", "x" * 2001, "{reset_time}"):
            with self.subTest(words=str(words)[:12]):
                self.assertEqual(continuation.with_once_words("Continue.", words, "usage_limit", english(), row=ROW),
                                 "Continue.")
        self.assertEqual(continuation.with_once_words("Continue.", WORDS, "unclassified", english()), "Continue.")


class ControlTests(ControlTestCase):
    def setUp(self):
        super().setUp()
        self.register()

    def state(self, value, **extra):
        """The record claimed (submitting), and then moved on to `value`."""
        with Store(self.paths.state_dir) as store:
            if store.get(KEY)["state"] != "submitting":
                store.set_enabled(True, 100.0)
                self.assertTrue(store.reserve(KEY, 1000.0))
            if value != "submitting":
                store.update(KEY, at=1001.0, state=value, **extra)

    def test_set_read_and_taken_away_for_one_waiting_recovery(self):
        self.assertEqual(self.control.once_words(KEY), {"interruption_id": KEY, "set": False, "text": None})
        self.assertEqual(self.control.set_once_words(KEY, THREAD, WORDS),
                         {"interruption_id": KEY, "thread_id": THREAD, "set": True})
        self.assertEqual(self.control.once_words(KEY)["text"], WORDS)
        self.assertEqual(self.control.set_once_words(KEY, THREAD, "  ")["set"], False)
        self.assertIsNone(self.control.once_words(KEY)["text"])
        self.control.set_once_words(KEY, THREAD, WORDS)
        self.assertEqual(self.control.set_once_words(KEY, THREAD, None)["set"], False)

    def test_refused_as_a_custom_message_would_be_and_for_a_recovery_that_no_longer_waits(self):
        for text in ("{prompt}", "x" * 2001, 5):
            with self.subTest(text=str(text)[:12]), self.assertRaises(ControlError):
                self.control.set_once_words(KEY, THREAD, text)
        for key, thread, code in ((KEY, OTHER_THREAD, "thread_mismatch"), (OTHER_KEY, THREAD, "no_such_interruption"),
                                  ("latest", THREAD, "invalid_id"), (KEY, "latest", "invalid_thread_id")):
            with self.subTest(code=code), self.assertRaises(ControlError) as caught:
                self.control.set_once_words(key, thread, WORDS)
            self.assertEqual(caught.exception.code, code)
        queue = "0a1b2c3d-0003-7000-8000-000000000003"
        for state, code, extra in (("submitting", "being_sent", {}),
                                   ("queued", "in_flight", {"queue_id": queue})):
            with self.subTest(state=state):
                self.state(state, **extra)
                with self.assertRaises(ControlError) as caught:
                    self.control.set_once_words(KEY, THREAD, WORDS)
                self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.control.once_words(KEY)["set"], False, "nothing was written")
        # Taking them away is always allowed: it only reduces.
        self.assertEqual(self.control.set_once_words(KEY, THREAD, None)["set"], False)

    def test_a_cancelled_recovery_takes_none(self):
        self.control.cancel_interruption(KEY)
        with self.assertRaises(ControlError) as caught:
            self.control.set_once_words(KEY, THREAD, WORDS)
        self.assertIn(caught.exception.code, ("cancel_requested", "already_finished"))
        self.assertFalse(self.paths.once_words_file.exists())

    def test_adding_words_wakes_and_sends_nothing(self):
        with patch("codex_auto_resume.control.actions.WakeEvent") as woken:
            self.control.set_once_words(KEY, THREAD, WORDS)
        woken.assert_not_called()
        with Store(self.paths.state_dir) as store:
            row = store.get(KEY)
        self.assertEqual((row["state"], row["next_retry_at"], row["attempt_count"]),
                         ("waiting_reset", row["next_retry_at"], 0))

    def test_a_pending_row_says_whether_and_never_what(self):
        self.assertIs(self.control.list_pending()[0]["once_words"], False)
        self.control.set_once_words(KEY, THREAD, "private words")
        rows = self.control.list_pending()
        self.assertIs(rows[0]["once_words"], True)
        self.assertNotIn("private words", json.dumps(rows))
        self.assertNotIn("private words", json.dumps(self.control.get_status()))

    def test_the_bridge_reads_sets_and_takes_them_away(self):
        reply = controlcli.dispatch(self.control, "once-words", {"interruption_id": KEY})
        self.assertEqual(reply, {"ok": True, "result": {"interruption_id": KEY, "set": False, "text": None}})
        self.assertTrue(controlcli.dispatch(self.control, "once-words",
                                            {"interruption_id": KEY, "thread_id": THREAD, "text": WORDS})["ok"])
        self.assertEqual(controlcli.dispatch(self.control, "once-words", {"interruption_id": KEY})["result"]["text"],
                         WORDS)
        refused = controlcli.dispatch(self.control, "once-words",
                                      {"interruption_id": KEY, "thread_id": THREAD, "text": "{prompt}"})
        self.assertIs(refused["ok"], False)
        self.assertTrue(controlcli.dispatch(self.control, "once-words",
                                            {"interruption_id": KEY, "thread_id": THREAD, "text": None})["ok"])
        self.assertFalse(self.paths.once_words_file.exists())

    def test_the_preview_shows_them_after_the_continuation_and_reports_a_refusal(self):
        plain = self.control.preview_continuation("usage_limit")["text"]
        shown = self.control.preview_continuation("usage_limit", once_words=WORDS)
        self.assertEqual(shown["text"], plain + "\n\n" + WORDS)
        refused = self.control.preview_continuation("usage_limit", once_words="{prompt}")
        self.assertEqual((refused["text"], refused["refusal_code"]), (plain, "forbidden_placeholder"))
        via = controlcli.dispatch(self.control, "preview-continuation", {"category": "usage_limit", "once_words": WORDS})
        self.assertEqual(via["result"]["text"], plain + "\n\n" + WORDS)

    def test_diagnostics_count_them_and_never_carry_the_text(self):
        self.control.set_once_words(KEY, THREAD, "private words")
        target = self.home / "diagnostics.json"
        diagnostics.write(self.control, target)
        written = target.read_text(encoding="utf-8")
        self.assertNotIn("private words", written)
        self.assertEqual(json.loads(written)["once_words"], {"count": 1})


class NeverFromAModelTests(McpTestCase):
    def setUp(self):
        super().setUp()
        self.register()

    def test_update_settings_refuses_them_and_no_setting_holds_them(self):
        self.assertNotIn("once_words", settings.FIELDS)
        reply = self.call("update_settings", {"once_words": {KEY: "Injected words"}})
        self.assertTrue(reply.get("error") or reply.get("result", {}).get("isError"))
        self.assertFalse(self.paths.once_words_file.exists())

    def test_the_preview_tool_takes_no_text(self):
        from codex_auto_resume.mcp.tools import TOOLS
        tool = next(tool for tool in TOOLS if tool["name"] == "preview_recovery_message")
        self.assertNotIn("once_words", json.dumps(tool["inputSchema"]))
        reply = self.call("preview_recovery_message", {"category": "usage_limit", "once_words": "Injected words"})
        self.assertNotIn("Injected words", json.dumps(reply))

    def test_no_tool_and_no_panel_reads_or_writes_them(self):
        source = Path(mcpserver.__file__).parent / "mcp"
        files = list(source.glob("*.py")) + sorted((source / "assets").glob("*"))
        for path in files:
            if path.is_file():
                with self.subTest(path.name):
                    text = path.read_text(encoding="utf-8", errors="replace")
                    for name in ("set_once_words", "once-words", "oncewords", "once_words("):
                        self.assertNotIn(name, text)

    def test_what_mcp_lists_never_carries_the_text(self):
        self.control.set_once_words(KEY, THREAD, "private words")
        for name in ("list_pending", "get_status", "open_settings"):
            with self.subTest(name):
                self.assertNotIn("private words", json.dumps(self.call(name, {})))


if __name__ == "__main__":
    unittest.main()
