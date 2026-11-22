"""v0.6.26 third round N2: the courier's e-mail channel has one time in all, as its HTTP channels do.

smtplib's timeout is for each socket operation, and a reply of many lines is read a line at a time with no bound on how
many: a mail server that answered a line inside each timeout held the courier's drain pass for as long as it went on.
Now the connection's socket is closed at MAIL_SECONDS and the send ends as "timeout".

The mail server is one on this PC's loopback whose banner never ends (a "220-" line every 0.1 s, for 6 s); smtplib's
connection is pointed at it. Nothing reaches the network.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests" python -m unittest test_advanced_courier_mail_time
"""
from __future__ import annotations

from pathlib import Path
import smtplib
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase  # noqa: E402,F401
from codex_auto_resume_advanced.courier import channels, http  # noqa: E402

SETTINGS = {"host": "mail.example.invalid", "port": 587, "user": "example", "password": "example-password",
            "from": "example@example.invalid", "to": "example@example.invalid"}
TRICKLE_FOR = 6.0


class EndlessBanner:
    def __init__(self):
        self.stopped = threading.Event()
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        self.server.settimeout(0.2)
        while not self.stopped.is_set():
            try:
                client, _address = self.server.accept()
            except OSError:
                continue
            threading.Thread(target=self._answer, args=(client,), daemon=True).start()

    def _answer(self, client):
        ends = time.monotonic() + TRICKLE_FOR
        try:
            while time.monotonic() < ends and not self.stopped.is_set():
                client.sendall(b"220-still saying hello\r\n")
                time.sleep(0.1)
            client.sendall(b"220 hello\r\n")
            self.stopped.wait(15)
        except OSError:
            pass
        finally:
            client.close()

    def stop(self):
        self.stopped.set()
        self.server.close()


class MailTimeTests(unittest.TestCase):
    def setUp(self):
        self.mail = EndlessBanner()
        self.addCleanup(self.mail.stop)
        real = socket.create_connection
        port = self.mail.port

        def to_loopback(address, timeout=None, source_address=None, **keywords):
            return real(("127.0.0.1", port), timeout)
        patched = patch.object(smtplib.socket, "create_connection", to_loopback)
        patched.start()
        self.addCleanup(patched.stop)

    def test_a_banner_that_never_ends_is_cut_at_the_time_in_all(self):
        """Fails without the clock: every line comes inside smtplib's 10 s, so it runs the whole 6 s banner and then
        waits out EHLO's 10 s."""
        started = time.monotonic()
        with patch.object(channels, "MAIL_SECONDS", 1.0, create=True), self.assertRaises(http.Failed) as raised:
            channels.mail(SETTINGS, "test", "words")
        self.assertEqual(raised.exception.word, "timeout")
        self.assertLess(time.monotonic() - started, 3.0)

    def test_the_time_in_all_is_four_timeouts(self):
        self.assertEqual(channels.MAIL_SECONDS, 4 * http.TIMEOUT)


if __name__ == "__main__":
    unittest.main()
