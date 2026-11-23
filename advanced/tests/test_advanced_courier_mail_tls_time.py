"""audit4 J2: the courier's e-mail time in all holds after STARTTLS and at QUIT.

N2's clock held the socket smtplib made at the connection. STARTTLS wraps that socket in a new one and detaches the first,
so on port 587 - the STARTTLS path, most providers' - the clock closed a detached socket and nothing after STARTTLS was
bounded but by 10 s a line; and `mail` stopped the clock before QUIT. Now the wrapped socket is held, and QUIT runs
inside the time in all.

The mail server is one on this PC's loopback that answers each command at once but trickles one reply - the second EHLO
(after STARTTLS) or QUIT - a line every 0.1 s for 6 s. STARTTLS is taken by a stand-in context whose wrap does what a real
one does to the socket (detaches it into a new object) without TLS, as no certificate is made here. Nothing reaches the
network.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests" python -m unittest test_advanced_courier_mail_tls_time
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


class SlowReplyServer:
    """A loopback SMTP server: every reply at once but `slow` ("ehlo_after_tls" or "quit"), trickled."""

    def __init__(self, slow):
        self.slow = slow
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

    def _trickle(self, client, code):
        ends = time.monotonic() + TRICKLE_FOR
        while time.monotonic() < ends and not self.stopped.is_set():
            client.sendall(b"%d-still answering\r\n" % code)
            time.sleep(0.1)

    def _answer(self, client):
        tls = False
        try:
            reader = client.makefile("rb")
            client.sendall(b"220 hello\r\n")
            while not self.stopped.is_set():
                line = reader.readline()
                if not line:
                    return
                verb = line.split(b" ", 1)[0].strip().upper()
                if verb in (b"EHLO", b"HELO"):
                    if tls and self.slow == "ehlo_after_tls":
                        self._trickle(client, 250)
                    client.sendall(b"250-hello\r\n250 AUTH PLAIN\r\n" if tls else b"250-hello\r\n250 STARTTLS\r\n")
                elif verb == b"STARTTLS":
                    client.sendall(b"220 go ahead\r\n")
                    tls = True
                elif verb == b"AUTH":
                    client.sendall(b"235 accepted\r\n")
                elif verb in (b"MAIL", b"RCPT"):
                    client.sendall(b"250 ok\r\n")
                elif verb == b"DATA":
                    client.sendall(b"354 go on\r\n")
                    while reader.readline() not in (b".\r\n", b""):
                        pass
                    client.sendall(b"250 queued\r\n")
                elif verb == b"QUIT":
                    if self.slow == "quit":
                        self._trickle(client, 221)
                    client.sendall(b"221 bye\r\n")
                    return
                else:
                    client.sendall(b"250 ok\r\n")
        except OSError:
            pass
        finally:
            client.close()

    def stop(self):
        self.stopped.set()
        self.server.close()


class _Context:
    """STARTTLS's wrap as a real context does it to the socket - a new object, the first detached - without TLS."""

    def wrap_socket(self, sock, server_hostname=None, **keywords):
        timeout = sock.gettimeout()
        wrapped = socket.socket(fileno=sock.detach())
        wrapped.settimeout(timeout)                 # as an SSLSocket keeps it: the handle is non-blocking under a timeout
        return wrapped


class MailTlsTimeTests(unittest.TestCase):
    def serve(self, slow):
        self.mail = SlowReplyServer(slow)
        self.addCleanup(self.mail.stop)
        real, port = socket.create_connection, self.mail.port

        def to_loopback(address, timeout=None, source_address=None, **keywords):
            return real(("127.0.0.1", port), timeout)
        for patched in (patch.object(smtplib.socket, "create_connection", to_loopback),
                        patch.object(http, "context", lambda: _Context()),
                        patch.object(channels, "MAIL_SECONDS", 1.0)):
            patched.start()
            self.addCleanup(patched.stop)

    def test_a_reply_that_never_ends_after_starttls_is_cut_at_the_time_in_all(self):
        """Fails with the plain socket held: the clock closes a detached socket, and the second EHLO runs its whole 6 s."""
        self.serve("ehlo_after_tls")
        started = time.monotonic()
        with self.assertRaises(http.Failed) as raised:
            channels.mail(SETTINGS, "test", "words")
        self.assertEqual(raised.exception.word, "timeout")
        self.assertLess(time.monotonic() - started, 3.0)

    def test_a_quit_that_never_ends_is_cut_at_the_time_in_all(self):
        """Fails with the clock stopped before QUIT: the message is sent, then QUIT's reply holds the drain for 6 s."""
        self.serve("quit")
        started = time.monotonic()
        self.assertEqual(channels.mail(SETTINGS, "test", "words"), "2xx")
        self.assertLess(time.monotonic() - started, 3.0)


if __name__ == "__main__":
    unittest.main()
