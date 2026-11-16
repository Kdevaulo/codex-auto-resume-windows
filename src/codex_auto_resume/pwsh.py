"""Run a fixed Windows PowerShell script, with values passed beside it rather than in it.

Two features need PowerShell because the platform offers them nowhere else from Python's
standard library: raising a toast under our own AppUserModelID, and writing a Start Menu
shortcut that carries one. Both used to build the script text with each value quoted as
a PowerShell single-quoted string, doubling any ASCII apostrophe.

That was not enough, and the failure was a code injection. PowerShell's tokenizer treats
four more characters as single quotes - U+2018, U+2019, U+201A and U+201B - so a project
folder or conversation title containing one of them ended the string early and the rest
of the value ran as PowerShell, in the watcher's context, under the user's account. A
folder called "Bob’s project" was enough to break a notification; a crafted name was
enough to run a command. Measured, not inferred: tests/test_pwsh.py raises the exact
payload through the real interpreter.

The fix is not a longer escape list. Values never become script text at all. Each one
travels as an environment variable of the child process, and the script - a constant,
reviewed in this repository - reads it with `$env:NAME`. PowerShell does not parse an
environment variable's value as code under any circumstances, so there is no character a
value could contain that changes what runs.

The script itself travels as one plain argument after -Command, quoted by subprocess's
list2cmdline - never as base64 after PowerShell's encoded-command switch, as it was until
v0.6.23 (issue #65: Avast's Behavior Shield blocked powershell.exe on that shape,
IDP.HELU.PSE96; tests/test_no_encoded_powershell.py keeps it out). Quoting is safe here
because the script is a constant: no value is ever in it, so the only text the quoting
carries is text reviewed in this repository, and tests/test_pwsh_command_line.py proves
the real interpreter receives every constant - double quotes, backslashes, here-strings
and all - exactly as written. Not stdin (`-Command -`), which Windows PowerShell 5.1 reads
line by line and so breaks a statement that spans lines.
"""
from __future__ import annotations

import os
import re
import subprocess

# Namespaced so a value can never collide with, or be mistaken for, a real setting.
PREFIX = "CODEX_AUTO_RESUME_ARG_"
_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,40}\Z")
# Windows limits an environment variable to 32,767 characters. Everything passed here is
# short; a value near the limit is a bug, and refusing it beats truncating it.
MAX_VALUE = 16000


class PowerShellError(RuntimeError):
    """A static reason only - never a transcript, never a value."""


def executable() -> str | None:
    """The in-box Windows PowerShell, by absolute path. Never whatever is on PATH."""
    root = os.environ.get("SystemRoot")
    if os.name != "nt" or not root:
        return None
    path = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return path if os.path.isfile(path) else None


def environment(values: dict) -> dict:
    """The child's environment: ours, plus one variable per value.

    Every value is checked here rather than trusted: a NUL cannot be carried in an
    environment block at all, and an oversized value means something upstream is wrong.
    """
    child = dict(os.environ)
    # Never inherit a stale argument from a parent that happened to set one.
    for key in list(child):
        if key.upper().startswith(PREFIX):
            del child[key]
    for name, value in values.items():
        if not _NAME.match(name):
            raise PowerShellError("invalid argument name")
        text = "" if value is None else str(value)
        if "\0" in text:
            raise PowerShellError("an argument contains a NUL character")
        if len(text) > MAX_VALUE:
            raise PowerShellError("an argument is too long")
        child[PREFIX + name] = text
    return child


def reference(name: str) -> str:
    """How a fixed script refers to a value: `$env:CODEX_AUTO_RESUME_ARG_NAME`."""
    if not _NAME.match(name):
        raise PowerShellError("invalid argument name")
    return "$env:" + PREFIX + name


def command_line(shell: str, script: str) -> list:
    """The argv that runs the constant `script`: the script whole, as the one argument after -Command."""
    return [shell, "-NoProfile", "-NonInteractive", "-Command", script]


def run(script: str, values: dict, *, timeout: float) -> int:
    """Run `script` with `values` available as environment variables. Returns the exit code.

    `script` must be a constant. It is the caller's code, not data; nothing derived from
    a value may be formatted into it. tests/test_pwsh.py holds every caller to that.
    """
    shell = executable()
    if shell is None:
        raise PowerShellError("PowerShell is unavailable")
    completed = subprocess.run(
        command_line(shell, script),
        env=environment(values), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        timeout=timeout, shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return completed.returncode
