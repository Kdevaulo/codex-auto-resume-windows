# ADVANCED-EDITION-CODE: in the advanced edition's archive, never the standard one's.
"""The Codex Desktop app's own IPC pipe, \\\\.\\pipe\\codex-ipc - for the forced stop near a usage limit alone
(v0.6.16-beta.4, usage_pause; measurement MIPC passed on codex-cli 0.162.0-alpha.17.2 with app 26.1007.9446.0).

What it does, and nothing else: open the pipe, `initialize`, ask `thread-owner-discovery` which client of the app
holds the conversation, and ask that client `thread-follower-interrupt-turn` (mode "system") for it - the stop a
person makes with the app's own Stop button. Then (off until a measurement says how) put the conversation's queue
back to running, which the app pauses after a stop - a pause that survives the app's restart. And, after the window
resets, `thread-follower-start-turn` - a turn started with the product's own continuation, which goes past that paused
queue - for a conversation it stopped (start_turn). Every frame is 4 bytes of little-endian length and UTF-8 JSON.
Each read waits at most READ_SECONDS (an overlapped read, cancelled and waited out, then the pipe closed - as the
MIPC look does); nothing here waits for good.

The app checks each request's version exactly, and a new app build may move one: the versions are pinned in
REQUESTS, every request's shape is there too, and a version mismatch is an answer like any other failure - the
caller falls back (holds this product's continuations until the reset, and tells the person the turn could not be
stopped). Every outcome is one closed word (Stop). Never a conversation's words, never an id in a log: the caller
journals the word alone.
"""
from __future__ import annotations

import json
import struct
import uuid
from enum import StrEnum

PIPE = r"\\.\pipe\codex-ipc"
# Each read of a frame waits at most this long; a whole stop, a few reads.
READ_SECONDS = 5.0
# The longest frame taken: the app's broadcasts can be long, a reply to these never is.
FRAME_LIMIT = 8 * 1024 * 1024
# The request shapes and the versions the app checks exactly (the MIPC record, 2026-10-16; app 26.1007). Filled with
# {thread}, {client}; the queue's (QUEUE_RESUME) is not measured yet and is None: no request is made for it.
CLIENT_TYPE = "codex-auto-resume"
REQUESTS = {
    "initialize": (0, {"clientType": CLIENT_TYPE}),
    "thread-owner-discovery": (1, {"hostId": "local", "conversationId": "{thread}"}),
    "thread-follower-interrupt-turn": (3, {"conversationId": "{thread}", "mode": "system"}),
    "thread-follower-start-turn": (2, {"conversationId": "{thread}", "turnStart": {
        "request": {"threadId": "{thread}", "clientUserMessageId": "{message}",
                    "input": [{"type": "text", "text": "{text}", "text_elements": []}]},
        "context": {"inheritThreadSettings": True}}}),
}
# v4 of the stop names the running turn it expects to stop, so a turn begun in between is never stopped.
INTERRUPT_EXPECTING = (4, {"conversationId": "{thread}", "mode": "system", "expectedTurnId": "{turn}"})
# Putting the queue back to running after a stop (thread-follower-set-queued-follow-ups-state v1, which REPLACES the
# queued list): not measured yet - None until it is, and then the stop's caller tells the person to press Resume.
QUEUE_RESUME = None


class Stop(StrEnum):
    """What came of one forced stop - the closed words the journal keeps."""
    STOPPED = "stopped"                      # the app stopped the turn
    NO_CLIENT = "no_client"                  # the app does not hold the conversation (not open, or not running)
    VERSION_MISMATCH = "version_mismatch"    # the app's build checks another version of a request
    NO_PIPE = "no_pipe"                      # the pipe is not there: the app is not running
    NO_ANSWER = "no_answer"                  # it did not answer in time
    REFUSED = "refused"                      # any other answer than success
    BROKEN = "broken"                        # a frame that is not one, or the pipe failing under us


class Resume(StrEnum):
    """What came of putting the queue back to running after a stop."""
    RESUMED = "resumed"
    UNPROVEN = "unproven"                    # not measured, or not answered success: the person presses Resume


class Start(StrEnum):
    """What came of one turn started - the closed words the journal keeps (and Stop's for every failure)."""
    STARTED = "started"


class _Failed(Exception):
    def __init__(self, word):
        super().__init__(word)
        self.word = word


def _filled(shape, fields):
    if isinstance(shape, dict):
        return {key: _filled(value, fields) for key, value in shape.items()}
    if isinstance(shape, list):
        return [_filled(value, fields) for value in shape]
    if isinstance(shape, str) and shape.startswith("{") and shape.endswith("}") and shape[1:-1] in fields:
        return fields[shape[1:-1]]
    return shape


_OVERLAPPED = []


def _overlapped():
    """Windows' OVERLAPPED, made once, when a channel first needs it (ctypes only where it is used)."""
    if not _OVERLAPPED:
        import ctypes

        class OVERLAPPED(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p), ("Offset", ctypes.c_uint32),
                        ("OffsetHigh", ctypes.c_uint32), ("hEvent", ctypes.c_void_p)]
        _OVERLAPPED.append(OVERLAPPED)
    return _OVERLAPPED[0]


class Channel:
    """One connection to the pipe, opened read-write, overlapped, closed by `close`. `opener` is a seam a test fills
    with a scratch pipe of its own name - never the real one."""

    def __init__(self, name=None):
        import ctypes
        from ctypes import wintypes
        self._ctypes, self._wintypes = ctypes, wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateFileW.restype = wintypes.HANDLE
        k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        k32.CreateEventW.restype = wintypes.HANDLE
        k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        for name_ in ("ReadFile", "WriteFile"):
            getattr(k32, name_).argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
                                           ctypes.c_void_p]
        k32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD),
                                            wintypes.BOOL]
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.WaitForSingleObject.restype = wintypes.DWORD
        k32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.ResetEvent.argtypes = [wintypes.HANDLE]
        self._k32 = k32
        self._pipe = None
        self._event = None
        generic_read_write, open_existing, overlapped = 0xC0000000, 3, 0x40000000
        pipe = k32.CreateFileW(PIPE if name is None else name, generic_read_write, 0, None, open_existing, overlapped,
                               None)
        if pipe in (None, wintypes.HANDLE(-1).value):
            raise _Failed(Stop.NO_PIPE)
        self._pipe = pipe
        self._event = k32.CreateEventW(None, True, False, None)
        if not self._event:
            self.close()
            raise _Failed(Stop.BROKEN)

    def _io(self, call, buffer, size, seconds):
        ctypes, k32 = self._ctypes, self._k32
        k32.ResetEvent(self._event)
        overlapped = _overlapped()(hEvent=self._event)
        count = self._wintypes.DWORD(0)
        started = call(self._pipe, buffer, size, None, ctypes.byref(overlapped))
        if not started and ctypes.get_last_error() != 997:            # ERROR_IO_PENDING
            raise _Failed(Stop.BROKEN)
        if k32.WaitForSingleObject(self._event, int(seconds * 1000)) != 0:
            k32.CancelIoEx(self._pipe, ctypes.byref(overlapped))
            k32.GetOverlappedResult(self._pipe, ctypes.byref(overlapped), ctypes.byref(count), True)
            raise _Failed(Stop.NO_ANSWER)
        if not k32.GetOverlappedResult(self._pipe, ctypes.byref(overlapped), ctypes.byref(count), False):
            raise _Failed(Stop.BROKEN)
        return count.value

    def _exactly(self, size, seconds):
        found = b""
        while len(found) < size:
            buffer = self._ctypes.create_string_buffer(size - len(found))
            got = self._io(self._k32.ReadFile, buffer, size - len(found), seconds)
            if got <= 0:
                raise _Failed(Stop.BROKEN)
            found += buffer.raw[:got]
        return found

    def write(self, message) -> None:
        data = json.dumps(message).encode("utf-8")
        frame = struct.pack("<I", len(data)) + data
        buffer = self._ctypes.create_string_buffer(frame, len(frame))
        if self._io(self._k32.WriteFile, buffer, len(frame), READ_SECONDS) != len(frame):
            raise _Failed(Stop.BROKEN)

    def read(self, seconds=READ_SECONDS):
        size = struct.unpack("<I", self._exactly(4, seconds))[0]
        if not 0 < size <= FRAME_LIMIT:
            raise _Failed(Stop.BROKEN)
        try:
            found = json.loads(self._exactly(size, seconds).decode("utf-8"))
        except ValueError:
            raise _Failed(Stop.BROKEN) from None
        if not isinstance(found, dict):
            raise _Failed(Stop.BROKEN)
        return found

    def close(self) -> None:
        if self._event:
            self._k32.CloseHandle(self._event)
            self._event = None
        if self._pipe is not None:
            self._k32.CloseHandle(self._pipe)
            self._pipe = None


def _request(channel, client, method, shape, fields, target=None, reads=20):
    version, params = shape
    key = str(uuid.uuid4())
    message = {"type": "request", "requestId": key, "sourceClientId": client, "version": version,
               "method": method, "params": _filled(params, fields)}
    if target is not None:
        message["targetClientId"] = target
    channel.write(message)
    for _ in range(reads):
        found = channel.read()
        if found.get("type") == "client-discovery-request":
            channel.write({"type": "client-discovery-response", "requestId": found.get("requestId"),
                           "response": {"canHandle": False}})
            continue
        if found.get("type") != "response" or found.get("requestId") != key:
            continue                                       # a broadcast, or another client's
        if found.get("resultType") == "success":
            return found
        error = found.get("error")
        if error == "no-client-found":
            raise _Failed(Stop.NO_CLIENT)
        if error == "request-version-mismatch":
            raise _Failed(Stop.VERSION_MISMATCH)
        raise _Failed(Stop.REFUSED)
    raise _Failed(Stop.NO_ANSWER)


def stop_turn(thread_id, turn_id=None, *, channel=None) -> tuple:
    """Stop the running turn of `thread_id` the app holds: (Stop word, Resume word or None). `turn_id`, where known,
    makes it the v4 stop that names it. `channel` is a seam (a Channel of a test's own pipe)."""
    try:
        opened = channel if channel is not None else Channel()
    except _Failed as failed:
        return failed.word, None
    except Exception:
        return Stop.BROKEN, None
    try:
        hello = _request(opened, "initializing-client", "initialize", REQUESTS["initialize"], {})
        client = (hello.get("result") or {}).get("clientId")
        if not isinstance(client, str) or not client:
            return Stop.REFUSED, None
        owner = _request(opened, client, "thread-owner-discovery", REQUESTS["thread-owner-discovery"],
                         {"thread": thread_id}).get("handledByClientId")
        if not isinstance(owner, str) or not owner:
            return Stop.NO_CLIENT, None
        shape = INTERRUPT_EXPECTING if turn_id else REQUESTS["thread-follower-interrupt-turn"]
        _request(opened, client, "thread-follower-interrupt-turn", shape, {"thread": thread_id, "turn": turn_id},
                 target=owner)
        return Stop.STOPPED, _resume(opened, client, owner, thread_id)
    except _Failed as failed:
        return failed.word, None
    except Exception:
        return Stop.BROKEN, None
    finally:
        opened.close()


def start_turn(thread_id, text, *, channel=None):
    """Start a turn of `thread_id` the app holds with `text` - the product's continuation after a window reset, for a
    conversation the forced stop stopped (its queue may be paused): Start.STARTED, or the Stop word of what failed -
    NO_CLIENT above all, the app not holding the conversation. `channel` is a seam (a Channel of a test's own pipe)."""
    try:
        opened = channel if channel is not None else Channel()
    except _Failed as failed:
        return failed.word
    except Exception:
        return Stop.BROKEN
    try:
        hello = _request(opened, "initializing-client", "initialize", REQUESTS["initialize"], {})
        client = (hello.get("result") or {}).get("clientId")
        if not isinstance(client, str) or not client:
            return Stop.REFUSED
        owner = _request(opened, client, "thread-owner-discovery", REQUESTS["thread-owner-discovery"],
                         {"thread": thread_id}).get("handledByClientId")
        if not isinstance(owner, str) or not owner:
            return Stop.NO_CLIENT
        _request(opened, client, "thread-follower-start-turn", REQUESTS["thread-follower-start-turn"],
                 {"thread": thread_id, "message": str(uuid.uuid4()), "text": text}, target=owner)
        return Start.STARTED
    except _Failed as failed:
        return failed.word
    except Exception:
        return Stop.BROKEN
    finally:
        opened.close()


def _resume(channel, client, owner, thread_id):
    """The queue put back to running after the stop - only once QUEUE_RESUME is measured; until then UNPROVEN."""
    if QUEUE_RESUME is None:
        return Resume.UNPROVEN
    try:
        _request(channel, client, "thread-follower-set-queued-follow-ups-state", QUEUE_RESUME,
                 {"thread": thread_id}, target=owner)
    except Exception:
        return Resume.UNPROVEN
    return Resume.RESUMED
