"""v0.6.15-beta.2: words for this time, as the engine adds them - once, to one interruption, and never on their own.

A person may add words for one waiting recovery in the Dashboard (oncewords.py). The engine reads them when it
builds that recovery's next continuation, before the claim (A26), and puts them after the continuation it would
send anyway, one blank line between; the one continuation that carries them is the one handed to Codex, and the
words are deleted as it is (whatever delivery then proves) - or put back when the queue process never started,
for the next one. They are deleted too when the interruption ends without a send. They never go to another
interruption, and adding them starts, speeds or skips nothing.

Against the real Store, Codex home and LocalSource (test_engine.Harness), with the real side file.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from codexsim import BASE, RESET  # noqa: E402
from codex_auto_resume import continuation, oncewords  # noqa: E402
from test_engine import T1, T2, TURN_A, TURN_B, EngineCase  # noqa: E402

WORDS = "Then run the tests, please."


class OnceWordsEngineCase(EngineCase):
    def fresh(self, **kwargs):
        harness = super().fresh(**kwargs)
        harness.engine.once_words = oncewords.OnceWords(harness.root / oncewords.FILE_NAME)
        return harness

    def words_file(self, h=None):
        return (h or self.h).engine.once_words

    def waiting(self, h=None, thread_id=T1, turn_id=TURN_A):
        """A usage limit registered and waiting for its reset; its record."""
        h = h or self.h
        h.home.fail_usage(thread_id, turn_id)
        h.backend.loaded_map[thread_id] = "loaded"
        h.tick()
        return h.record(thread_id)

    def add(self, row, text=WORDS, h=None):
        self.words_file(h).put(row["interruption_id"], text, now=BASE)

    def plain_prompt(self, row):
        """The continuation this record sends without words, and its marker."""
        values = self.h.engine.policy_values
        text = continuation.for_settings(row["category"], values, row=row, limits=self.h.engine.limits())
        return text + "\n\n" + row["marker"]


class AttachOnceTests(OnceWordsEngineCase):
    def test_the_words_go_after_the_continuation_once_and_are_deleted_as_it_is_sent(self):
        row = self.waiting()
        self.add(row)
        self.h.now = RESET + 61
        self.h.tick()
        self.assertEqual(len(self.h.backend.send_calls), 1)
        prompt = self.h.backend.send_calls[0][1]
        plain = self.plain_prompt(self.h.record())
        body, marker = plain.rsplit("\n\n", 1)
        self.assertEqual(prompt, body + "\n\n" + WORDS + "\n\n" + marker)
        self.assertIsNone(self.words_file().words(row["interruption_id"]))
        self.assertFalse(self.words_file().path.exists(), "the file goes when it holds nothing")
        self.assertIn("once_words_sent", self.h.codes())

    def test_placeholders_in_them_are_filled_as_a_custom_messages_are(self):
        row = self.waiting()
        self.add(row, "Kind: {category}.")
        self.h.now = RESET + 61
        self.h.tick()
        self.assertIn("\n\nKind: usage_limit.\n\n", self.h.backend.send_calls[0][1])

    def test_a_send_whose_outcome_is_unknown_spent_them_and_nothing_is_sent_again(self):
        row = self.waiting()
        self.add(row)
        self.h.backend.default_outcome = "unknown"
        self.h.now = RESET + 61
        self.h.tick()
        self.assertEqual(self.h.record()["state"], "submission_unknown")
        self.assertIsNone(self.words_file().words(row["interruption_id"]))
        for _ in range(4):
            self.h.tick(advance=1800)
        self.assertEqual(len(self.h.backend.send_calls), 1)

    def test_a_queue_process_that_never_started_keeps_them_for_the_next_continuation_only(self):
        self.h.engine.options["thread_cooldown_seconds"] = 0
        row = self.waiting()
        self.add(row)
        self.h.backend.default_outcome = "not_started"
        self.h.now = RESET + 61
        self.h.tick()
        self.assertEqual(self.h.record()["state"], "waiting_retry")
        self.assertEqual(self.words_file().words(row["interruption_id"]), WORDS, "never handed over: kept")
        self.h.backend.default_outcome = "accepted"
        self.h.tick(advance=31)
        self.assertEqual(len(self.h.backend.send_calls), 2)
        self.assertTrue(all(WORDS in prompt for _, prompt in self.h.backend.send_calls))
        self.assertIsNone(self.words_file().words(row["interruption_id"]))
        self.follow()
        self.h.tick(advance=3600)
        self.assertEqual(len(self.h.backend.send_calls), 2)

    def test_words_that_could_not_be_taken_off_are_not_sent(self):
        row = self.waiting()
        self.add(row)
        self.h.now = RESET + 61
        with patch.object(oncewords.OnceWords, "remove", return_value=False):
            self.h.tick()
        self.assertEqual(self.h.backend.send_calls[0][1], self.plain_prompt(self.h.record()))
        self.assertIn("once_words_kept", self.h.codes())
        # Kept in the file, and deleted at the next look: the record is no longer waiting.
        self.h.tick(advance=1)
        self.assertIsNone(self.words_file().words(row["interruption_id"]))

    def test_words_that_fail_the_check_when_read_are_not_set(self):
        row = self.waiting()
        path = self.words_file().path
        path.write_text(json.dumps({row["interruption_id"]: {"text": "Read {prompt}", "written_at": BASE}}),
                        encoding="utf-8")
        self.h.now = RESET + 61
        self.h.tick()
        self.assertEqual(self.h.backend.send_calls[0][1], self.plain_prompt(self.h.record()))


class OnlyThisInterruptionTests(OnceWordsEngineCase):
    def test_they_never_go_to_another_conversation(self):
        first = self.waiting(thread_id=T1, turn_id=TURN_A)
        self.waiting(thread_id=T2, turn_id=TURN_B)
        self.add(first)
        self.h.now = RESET + 61
        self.h.tick()
        prompts = {thread: prompt for thread, prompt in self.h.backend.send_calls}
        self.assertEqual(set(prompts), {T1, T2})
        self.assertIn(WORDS, prompts[T1])
        self.assertNotIn(WORDS, prompts[T2])

    def test_words_kept_for_an_id_no_record_has_are_never_sent_and_are_deleted(self):
        self.waiting()
        self.words_file().put("e" * 64, WORDS, now=BASE)
        self.h.now = RESET + 61
        self.h.tick()
        self.assertNotIn(WORDS, self.h.backend.send_calls[0][1])
        self.assertEqual(self.words_file().held(), {})


class EndsWithoutASendTests(OnceWordsEngineCase):
    def test_a_cancel_deletes_them(self):
        row = self.waiting()
        self.add(row)
        self.h.store.cancel_thread(T1, self.h.now)
        self.h.tick()
        self.assertEqual(self.h.record()["state"], "cancelled")
        self.h.tick(advance=1)
        self.assertEqual(self.words_file().held(), {})
        self.assertFalse(self.words_file().path.exists())

    def test_a_person_who_continued_the_conversation_themselves_deletes_them(self):
        row = self.waiting()
        self.add(row)
        self.h.home.add_turn(T1, TURN_B, "completed", completed=BASE + 100)
        self.h.now = RESET + 61
        self.h.tick()
        self.assert_no_send()
        self.assertEqual(self.h.record()["state"], "superseded_by_user")
        self.h.tick(advance=1)
        self.assertEqual(self.words_file().held(), {})

    def test_while_it_waits_they_are_kept(self):
        row = self.waiting()
        self.add(row)
        for _ in range(3):
            self.h.tick(advance=60)
        self.assertEqual(self.words_file().words(row["interruption_id"]), WORDS)


class NothingSentByAddingTests(OnceWordsEngineCase):
    def test_words_start_nothing_before_the_reset(self):
        row = self.waiting()
        self.add(row)
        for _ in range(5):
            self.h.tick(advance=60)
        self.assert_no_send()
        self.assertEqual(self.h.record()["state"], row["state"])

    def test_the_gates_and_the_moment_of_the_send_are_the_same_with_or_without_them(self):
        plain = self.fresh()
        plain.engine.once_words = None
        worded = self.fresh()
        for harness in (plain, worded):
            harness.home.fail_usage(T1, TURN_A)
            harness.backend.loaded_map[T1] = "loaded"
            harness.tick()
        self.add(worded.record(), h=worded)
        for step in (0, 30, 31, 60):
            for harness in (plain, worded):
                harness.now = RESET + step
                harness.tick()
            with self.subTest(step=step):
                self.assertEqual(len(plain.backend.send_calls), len(worded.backend.send_calls))
                self.assertEqual(plain.record()["state"], worded.record()["state"])
                self.assertEqual(plain.record()["gate_eval"], worded.record()["gate_eval"])
        self.assertEqual(len(worded.backend.send_calls), 1)

    def test_an_engine_given_none_adds_none(self):
        self.h.engine.once_words = None
        row = self.waiting()
        oncewords.OnceWords(self.h.root / oncewords.FILE_NAME).put(row["interruption_id"], WORDS, now=BASE)
        self.h.now = RESET + 61
        self.h.tick()
        self.assertNotIn(WORDS, self.h.backend.send_calls[0][1])


class WiredTests(unittest.TestCase):
    def test_the_watchers_engines_are_given_the_state_folders_file(self):
        import inspect
        from codex_auto_resume.runtime import app
        source = inspect.getsource(app.App.engine) + inspect.getsource(app.App.home_engine)
        self.assertEqual(source.count("oncewords.OnceWords.of(self.paths)"), 2)


if __name__ == "__main__":
    unittest.main()
