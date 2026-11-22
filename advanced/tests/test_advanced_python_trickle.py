"""v0.6.26 third round A7 (security S3): the Python choice's Check and download deadlines cut a read that trickles.

`http.stream` read the answer `reply.read(65536)` at a time - a buffered read, which waits for the whole piece - and the
deadline was looked at only between pieces. A service that sent a byte inside each read's timeout held one piece for
days, the card busy and Back to the bundled version refused meanwhile. Now each piece is what one read of the socket
brought, and the caller's deadline shuts the socket itself.

python.org is a server on this PC's loopback, reached through an opener of the test's own: a real socket and a real
HTTPResponse, nothing on the network. Each case takes about a second.

    CODEX_AR_EDITION=advanced PYTHONPATH="src;advanced/src;advanced/tests" python -m unittest test_advanced_python_trickle
"""
from __future__ import annotations

import http.client
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase  # noqa: E402,F401
from codex_auto_resume_advanced.courier import http as courier_http  # noqa: E402
from codex_auto_resume_advanced.courier import pythonorg  # noqa: E402

BODY = 2000


class Trickle:
    """A loopback HTTP server that answers every request with BODY bytes declared and sends them `every` seconds apart,
    `each` bytes at a time, until the client goes or it is stopped."""

    def __init__(self, every=0.05, each=1):
        self.every, self.each = every, each
        self.stopped = threading.Event()
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

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
            client.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nContent-Type: application/json\r\n\r\n" % BODY)
            sent = 0
            while sent < BODY and not self.stopped.is_set():
                client.sendall(b" " * self.each)
                sent += self.each
                time.sleep(self.every)
        except OSError:
            pass
        finally:
            client.close()

    def stop(self):
        self.stopped.set()
        self.server.close()


class Opener:
    """urllib's `open` as the courier calls it, every request made to the loopback server whatever its address says."""

    def __init__(self, port):
        self.port = port

    def open(self, request, timeout=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        connection.request("GET", "/")
        return connection.getresponse()


class Case(unittest.TestCase):
    def setUp(self):
        self.server = Trickle()
        self.addCleanup(self.server.stop)
        self.opener = Opener(self.server.port)


class StreamTests(Case):
    def test_each_piece_is_what_arrived(self):
        """Fails with `reply.read(piece)`: the first piece comes only once all 2,000 bytes have, after 100 s."""
        pieces = []

        def take(piece):
            pieces.append(piece)
            raise StopIteration
        started = time.monotonic()
        with self.assertRaises(StopIteration):
            courier_http.stream("https://www.python.org/x", take, timeout=5, opener=self.opener)
        self.assertLess(time.monotonic() - started, 3)
        self.assertLess(len(pieces[0]), BODY)

    def test_the_deadline_cuts_a_read_that_waits(self):
        """Fails without `ends`: a server that sends nothing more for longer than the deadline holds the read to its
        timeout (here 5 s) rather than the deadline (1 s)."""
        self.server.every = 3.0
        started = time.monotonic()
        with self.assertRaises(courier_http.Failed) as raised:
            courier_http.stream("https://www.python.org/x", lambda piece: None, timeout=5, opener=self.opener,
                                ends=time.monotonic() + 1.0)
        self.assertEqual(raised.exception.word, "timeout")
        self.assertLess(time.monotonic() - started, 2.5)


class PythonOrgTests(Case):
    def test_a_check_ends_at_its_deadline(self):
        """Fails with the old read: the trickle of 2,000 bytes at 20 a second runs a 1 s Check for 100 s."""
        started = time.monotonic()
        with self.assertRaises(pythonorg.Refused) as raised:
            pythonorg._answer("https://www.python.org/api/v2/downloads/release/", self.opener,
                              time.monotonic() + 1.0)
        self.assertEqual(raised.exception.step, pythonorg.LIST)
        self.assertLess(time.monotonic() - started, 2.5)

    def test_a_download_ends_at_its_deadline(self):
        made = tempfile.TemporaryDirectory(prefix="car-python-trickle-")
        self.addCleanup(made.cleanup)
        found = {"url": "https://www.python.org/ftp/python/x.zip", "sha256": "0" * 64, "size": BODY}
        started = time.monotonic()
        with patch.object(pythonorg, "DOWNLOAD_SECONDS", 1.0), self.assertRaises(pythonorg.Refused) as raised:
            pythonorg.download(found, Path(made.name) / "package.zip", opener=self.opener)
        self.assertEqual(raised.exception.step, pythonorg.DOWNLOAD)
        self.assertLess(time.monotonic() - started, 2.5)


if __name__ == "__main__":
    unittest.main()
