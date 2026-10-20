"""Who Windows lets open the state folder (v0.6.11, Diagnostics).

One documented Win32 question, asked only when Diagnostics is shown: the folder's access list
(GetNamedSecurityInfoW, the DACL only), read and never written. Each entry that lets someone in is
compared with the few that are expected there - this account, Windows itself (SYSTEM), the
computer's administrators and CREATOR OWNER, which Windows turns into the account that made a file -
and an app's own sandbox (S-1-15-...), which runs as this account and is no other person. Anyone
else - another account, Users, Everyone, Authenticated Users - means other accounts on this PC can
open the folder where the settings, the pending tasks and the logs are kept.

One more is told apart (v0.6.17): Codex's Windows sandbox adds an explicit entry for its local group
CodexSandboxUsers that lets it read and list a user's folders (`(OI)(CI)(RX)`), the state folder among
them. A sandboxed command can then read the folder and change nothing in it: CODEX_SANDBOX, said as what
it is, not as other accounts. The group is matched by its name and kind on this machine - a local group
(an alias) of this computer named CodexSandboxUsers, whatever the computer is called - and only while
every entry for it only reads; one that may write, or any other account beside it, is SHARED as before.

Only the verdict leaves this module (`verdict`): no security identifier, no account name and no
path is kept or returned - the sandbox group's name is looked up to be compared, and dropped. The account's own identifier is read from this process's own token
(TokenUser) to be compared, and dropped. Nothing here raises: what cannot be read is UNKNOWN.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os

from ..domain.vocabulary import StateAccess
from .dll import library

SE_FILE_OBJECT = 1
DACL_SECURITY_INFORMATION = 0x4
TOKEN_USER = 1
ACL_SIZE_INFORMATION = 2
ACCESS_ALLOWED_ACE_TYPE = 0x0
ACCESS_DENIED_ACE_TYPE = 0x1
# GetCurrentProcessToken(): a pseudo-handle that needs no opening or closing, and can only be asked.
_CURRENT_PROCESS_TOKEN = -4
# Windows itself, the administrators, and CREATOR OWNER - the three expected beside this account -
# and the prefix of an app sandbox's package and capability identifiers, which are not accounts.
EXPECTED = frozenset({"S-1-5-18", "S-1-5-32-544", "S-1-3-0"})
# The answers, in the order Diagnostics has words for them.
STATE_ACCESS = tuple(StateAccess)
SANDBOX = "S-1-15-"
# Codex's Windows sandbox's local group, and the rights an entry may give it and still only read: the
# folder's contents listed, its files read and run, their attributes and its security read, and the
# generic read and execute rights that map onto those. Any other bit - writing, appending, deleting,
# changing the security or the owner, everything (GENERIC_ALL), MAXIMUM_ALLOWED - is more than reading.
CODEX_SANDBOX_GROUP = "codexsandboxusers"
READ_ONLY = 0x001200A9 | 0x80000000 | 0x20000000
# Every right, for an entry handed in as an identifier alone.
EVERYTHING = 0xFFFFFFFF
SID_TYPE_ALIAS = 4

_dll = library()


class _AceHeader(C.Structure):
    _fields_ = [("AceType", C.c_ubyte), ("AceFlags", C.c_ubyte), ("AceSize", W.WORD)]


class _AllowedAce(C.Structure):
    """ACCESS_ALLOWED_ACE: its header, its mask, and the SID that starts at SidStart."""
    _fields_ = [("Header", _AceHeader), ("Mask", W.DWORD), ("SidStart", W.DWORD)]


class _AclSize(C.Structure):
    _fields_ = [("AceCount", W.DWORD), ("AclBytesInUse", W.DWORD), ("AclBytesFree", W.DWORD)]


def _call(dll, name, result, *arguments):
    function = getattr(_dll(dll), name)
    function.restype = result
    function.argtypes = list(arguments)
    return function


def _sid_text(sid) -> str | None:
    text = W.LPWSTR()
    if not _call("advapi32", "ConvertSidToStringSidW", W.BOOL, C.c_void_p, C.POINTER(W.LPWSTR))(sid, C.byref(text)):
        return None
    try:
        return text.value
    finally:
        _call("kernel32", "LocalFree", C.c_void_p, C.c_void_p)(text)


def _own_sid() -> str | None:
    """This account's security identifier, as text, from this process's own token."""
    needed = W.DWORD(0)
    asked = _call("advapi32", "GetTokenInformation", W.BOOL, W.HANDLE, C.c_int, C.c_void_p, W.DWORD,
                  C.POINTER(W.DWORD))
    asked(W.HANDLE(_CURRENT_PROCESS_TOKEN), TOKEN_USER, None, 0, C.byref(needed))
    if not needed.value or needed.value > 4096:
        return None
    buffer = C.create_string_buffer(needed.value)
    if not asked(W.HANDLE(_CURRENT_PROCESS_TOKEN), TOKEN_USER, buffer, needed, C.byref(needed)):
        return None
    # TOKEN_USER begins with SID_AND_ATTRIBUTES, whose first field is the SID's address.
    return _sid_text(C.c_void_p.from_buffer(buffer).value)


def _dacl_entries(dacl) -> list | None:
    """(identifier as text, access mask) for each entry of a DACL that lets someone in - or None when
    one cannot be read. A missing DACL (NULL) lets everyone in everything: Everyone's, every right."""
    if not dacl:
        return [("S-1-1-0", EVERYTHING)]
    size = _AclSize()
    if not _call("advapi32", "GetAclInformation", W.BOOL, C.c_void_p, C.c_void_p, W.DWORD, C.c_int)(
            dacl, C.byref(size), C.sizeof(size), ACL_SIZE_INFORMATION):
        return None
    get_ace = _call("advapi32", "GetAce", W.BOOL, C.c_void_p, W.DWORD, C.POINTER(C.c_void_p))
    found = []
    for index in range(min(size.AceCount, 1024)):
        ace = C.c_void_p()
        if not get_ace(dacl, index, C.byref(ace)):
            return None
        header = _AceHeader.from_address(ace.value)
        if header.AceType == ACCESS_DENIED_ACE_TYPE:
            continue                        # a refusal lets no one in
        if header.AceType != ACCESS_ALLOWED_ACE_TYPE:
            return None                     # a kind this does not read: unknown, never "only you"
        allowed = _AllowedAce.from_address(ace.value)
        if not allowed.Mask:
            continue
        text = _sid_text(ace.value + _AllowedAce.SidStart.offset)
        if text is None:
            return None
        found.append((text, int(allowed.Mask)))
    return found


def allowed_entries(path) -> list | None:
    """(identifier, access mask) for each entry of the folder's access list that lets someone in - or
    None when the list cannot be read. An empty list is a folder nobody may open."""
    descriptor, dacl = C.c_void_p(), C.c_void_p()
    asked = _call("advapi32", "GetNamedSecurityInfoW", W.DWORD, W.LPCWSTR, C.c_int, W.DWORD, C.c_void_p,
                  C.c_void_p, C.POINTER(C.c_void_p), C.c_void_p, C.POINTER(C.c_void_p))
    if asked(str(path), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, None, None, C.byref(dacl), None,
             C.byref(descriptor)) != 0:
        return None
    try:
        return _dacl_entries(dacl.value)
    finally:
        _call("kernel32", "LocalFree", C.c_void_p, C.c_void_p)(descriptor)


def described_entries(sddl: str) -> list | None:
    """allowed_entries for a security descriptor written as SDDL rather than read from a folder: the
    same reading of the same structures, over a descriptor that exists only in this process - which is
    how the tests hold it without changing any folder's access list."""
    descriptor = C.c_void_p()
    if not _call("advapi32", "ConvertStringSecurityDescriptorToSecurityDescriptorW", W.BOOL, W.LPCWSTR,
                 W.DWORD, C.POINTER(C.c_void_p), C.c_void_p)(sddl, 1, C.byref(descriptor), None):
        return None
    try:
        present, dacl, defaulted = W.BOOL(), C.c_void_p(), W.BOOL()
        if not _call("advapi32", "GetSecurityDescriptorDacl", W.BOOL, C.c_void_p, C.POINTER(W.BOOL),
                     C.POINTER(C.c_void_p), C.POINTER(W.BOOL))(descriptor, C.byref(present), C.byref(dacl),
                                                              C.byref(defaulted)):
            return None
        return _dacl_entries(dacl.value if present.value else None)
    finally:
        _call("kernel32", "LocalFree", C.c_void_p, C.c_void_p)(descriptor)


def allowed_sids(path) -> list | None:
    """The identifiers allowed_entries names, as text, or None."""
    entries = allowed_entries(path)
    return None if entries is None else [sid for sid, _mask in entries]


def is_sandbox_group(name, domain, kind, computer) -> bool:
    """Whether an account Windows names (`name`, `domain`, SID_NAME_USE `kind`) is Codex's sandbox group on
    this computer: a local group (an alias) of this computer - its domain is the computer's name - called
    CodexSandboxUsers, in any case. Pure."""
    return (isinstance(name, str) and name.casefold() == CODEX_SANDBOX_GROUP and kind == SID_TYPE_ALIAS
            and isinstance(domain, str) and isinstance(computer, str) and bool(computer)
            and domain.casefold() == computer.casefold())


def _account(sid_text):
    """(name, domain, kind) Windows gives for an identifier on this machine, or None."""
    sid = C.c_void_p()
    if not _call("advapi32", "ConvertStringSidToSidW", W.BOOL, W.LPCWSTR, C.POINTER(C.c_void_p))(
            sid_text, C.byref(sid)):
        return None
    try:
        name, domain = C.create_unicode_buffer(256), C.create_unicode_buffer(256)
        name_size, domain_size, kind = W.DWORD(256), W.DWORD(256), C.c_int()
        if not _call("advapi32", "LookupAccountSidW", W.BOOL, W.LPCWSTR, C.c_void_p, W.LPWSTR,
                     C.POINTER(W.DWORD), W.LPWSTR, C.POINTER(W.DWORD), C.POINTER(C.c_int))(
                None, sid, name, C.byref(name_size), domain, C.byref(domain_size), C.byref(kind)):
            return None
        return name.value, domain.value, kind.value
    finally:
        _call("kernel32", "LocalFree", C.c_void_p, C.c_void_p)(sid)


def _computer() -> str | None:
    """This computer's NetBIOS name, which LookupAccountSidW gives as a local account's domain."""
    buffer, size = C.create_unicode_buffer(256), W.DWORD(256)
    if not _call("kernel32", "GetComputerNameW", W.BOOL, W.LPWSTR, C.POINTER(W.DWORD))(buffer, C.byref(size)):
        return None
    return buffer.value


def sandbox_sids(entries, account=None, computer=None) -> frozenset:
    """The identifiers among `entries` that name Codex's sandbox group on this computer. Only a machine's
    own identifiers (S-1-5-21-...) are looked up; `account` and `computer` stand in for Windows' answers."""
    account = account or _account
    if computer is None:
        computer = _computer()
    found = set()
    for sid in {sid for sid, _mask in entries or ()}:
        if not sid.startswith("S-1-5-21-"):
            continue
        named = account(sid)
        if named is not None and is_sandbox_group(*named, computer):
            found.add(sid)
    return frozenset(found)


def verdict(allowed, own, sandbox=frozenset()) -> str:
    """OWNER_ONLY, CODEX_SANDBOX, SHARED or UNKNOWN for what an access list lets in and this account's
    identifier. `allowed` holds (identifier, mask) pairs - or bare identifiers, each then given every
    right - and `sandbox` the identifiers that name Codex's sandbox group here (sandbox_sids). Pure: the
    rule, apart from the asking."""
    if allowed is None or not own:
        return StateAccess.UNKNOWN.value
    entries = [(entry, EVERYTHING) if isinstance(entry, str) else entry for entry in allowed]
    others = [(sid, mask) for sid, mask in entries
              if sid != own and sid not in EXPECTED and not sid.startswith(SANDBOX)]
    if not others:
        return StateAccess.OWNER_ONLY.value
    if all(sid in sandbox and not mask & ~READ_ONLY for sid, mask in others):
        return StateAccess.CODEX_SANDBOX.value
    return StateAccess.SHARED.value


def state_access(path) -> str:
    """Who may open the folder at `path`: OWNER_ONLY, CODEX_SANDBOX, SHARED or UNKNOWN. Never raises."""
    if os.name != "nt":
        return StateAccess.UNKNOWN.value
    try:
        entries = allowed_entries(path)
        return verdict(entries, _own_sid(), sandbox_sids(entries))
    except Exception:
        return StateAccess.UNKNOWN.value
