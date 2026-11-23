"""audit4 D3 (round 3's S3, the part left open): `http.stream`'s deadline covers the connection and the headers.

The A7 fix armed the caller's deadline (`ends`) only once the reply was back: the connection, the TLS handshake, the status
line and up to 100 header lines were each bounded by the per-read timeout alone, so a service that trickled its headers
ran the Python choice's Check or download far past its deadline (12.2 s against 2 s, shown). Now one clock starts with
the call, and every connection the courier's own opener makes is held by it from its making.

A server on this PC's loopback answers over plain HTTP - the address check let through for it, as
test_advanced_courier_http's trickle tests do - and sends a header line every 0.1 s, inside each read's 1 s timeout. The
courier's own opener is used (no opener given), so its held connection is what is tested. Nothing reaches the network.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests" python -m unittest test_advanced_courier_stream_headers
"""
from __future__ import annotations

from pathlib import Path
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase  # noqa: E402,F401
from codex_auto_resume_advanced.courier import http  # noqa: E402

TRICKLE_FOR = 8.0


class SlowHeaders:
    """Every request answered with a status line and then a header line every 0.1 s for TRICKLE_FOR seconds."""

    def __init__(self, slow=True):
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

    def _answer(self, client):
        try:
            client.recv(65536)
            client.sendall(b"HTTP/1.1 200 OK\r\n")
            ends = time.monotonic() + TRICKLE_FOR
            while self.slow and time.monotonic() < ends and not self.stopped.is_set():
                client.sendall(b"X-Still: coming\r\n")
                time.sleep(0.1)
            client.sendall(b"Content-Length: 2\r\n\r\nok")
            self.stopped.wait(2)
        except OSError:
            pass
        finally:
            client.close()

    def stop(self):
        self.stopped.set()
        self.server.close()


class StreamHeadersTests(unittest.TestCase):
    def serve(self, slow=True):
        self.mail = SlowHeaders(slow)
        self.addCleanup(self.mail.stop)
        patched = patch.object(http, "checked_url", lambda url: url)
        patched.start()
        self.addCleanup(patched.stop)
        return "http://127.0.0.1:%d/x" % self.mail.port

    def test_headers_that_trickle_are_cut_at_the_deadline(self):
        """Fails with the deadline armed after the headers: the 100 header lines take 10 s, past the 1 s deadline."""
        url = self.serve()
        started = time.monotonic()
        with self.assertRaises(http.Failed) as raised:
            http.stream(url, lambda piece: None, timeout=1, ends=time.monotonic() + 1.0)
        self.assertEqual(raised.exception.word, "timeout")
        self.assertLess(time.monotonic() - started, 3.0)

    def test_a_tls_handshake_that_never_answers_is_cut_at_the_deadline(self):
        """The HTTPS connection, held before its handshake: a service that takes the connection and never answers the
        TLS hello. Fails with the deadline armed after the reply: the handshake waits out its whole 5 s timeout."""
        self.serve(slow=True)
        silent = socket.create_server(("127.0.0.1", 0))
        self.addCleanup(silent.close)
        taken = []
        threading.Thread(target=lambda: taken.append(silent.accept()), daemon=True).start()
        started = time.monotonic()
        with self.assertRaises(http.Failed) as raised:
            http.stream("https://127.0.0.1:%d/x" % silent.getsockname()[1], lambda piece: None, timeout=5,
                        ends=time.monotonic() + 1.0)
        self.assertEqual(raised.exception.word, "timeout")
        self.assertLess(time.monotonic() - started, 3.0)
        for peer, _address in taken:
            peer.close()

    def test_an_answer_in_time_is_read_whole(self):
        url = self.serve(slow=False)
        pieces = []
        http.stream(url, pieces.append, timeout=1, ends=time.monotonic() + 5.0)
        self.assertEqual(b"".join(pieces), b"ok")


if __name__ == "__main__":
    unittest.main()
