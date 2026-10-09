"""One folder is one Codex home however it is spelled, and what a home to watch must be (v0.6.14-beta.2).

A watcher's lock on a Codex home has been a file named by the SHA-256 of the home's resolved path since
v0.6.0 (win/homelock.py). Path.resolve() follows a junction or a symbolic link, but a folder has spellings
it does not canonicalise - a subst drive, a share of the same disk - so from v0.6.14-beta.2 the lock is
two files: the path's, then one named by the folder's identity (win/folderid.py: the volume's serial number
and the folder's index, which no spelling changes). Either busy is busy. A folder whose identity cannot be
read - the default home before Codex made it - is locked by its path alone, as before; a home a person
added is not watched until it can be (runtime/homes.py).

Scratch folders only: every lock file is under a temporary folder, never %LOCALAPPDATA%.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import homes  # noqa: E402
from codex_auto_resume.domain.errors import AdapterError  # noqa: E402
from codex_auto_resume.win import folderid  # noqa: E402
from codex_auto_resume.win.homelock import HomeLock  # noqa: E402

WINDOWS = os.name == "nt"


def junction(target: Path, link: Path) -> bool:
    try:
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
        return True
    except (ImportError, OSError):
        return False


class Case(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.locks = self.root / "locks"
        self.home = self.root / "home"
        self.home.mkdir()
        (self.home / "state_5.sqlite").write_bytes(b"")

    def held(self, lock):
        entered = lock.__enter__()
        self.addCleanup(lock.__exit__, None, None, None)
        return entered

    def entry(self, path, alias="work"):
        return {"path": str(path), "alias": alias}

    def codex_home(self, name):
        folder = self.root / name
        folder.mkdir()
        (folder / "state_5.sqlite").write_bytes(b"")
        return folder


@unittest.skipUnless(WINDOWS, "folder identities and file locks are Windows'")
class FolderLockTests(Case):
    def test_a_folders_identity_does_not_change_with_its_spelling(self):
        link = self.root / "through"
        if not junction(self.home, link):
            self.skipTest("no junction could be made here")
        self.assertIsNotNone(folderid.identity(self.home))
        self.assertEqual(folderid.identity(link), folderid.identity(self.home))
        self.assertIsNone(folderid.identity(self.root / "nothing"))
        self.assertIsNone(folderid.identity(self.home / "state_5.sqlite"), "a file is not a folder")

    def test_a_spelling_the_path_does_not_canonicalise_is_still_one_home(self):
        """A second lock on the same folder under another path name - a subst drive's, a share's, which
        Path.resolve() leaves as they are - is busy through the folder's identity. Without the second
        lock file it would have been taken."""
        self.held(HomeLock(self.home, self.locks))
        other = HomeLock(self.home, self.locks)
        other.path = self.locks / ("0" * 64 + ".lock")        # the name another spelling's path gives
        with self.assertRaises(AdapterError) as refused:
            other.__enter__()
        self.assertEqual(str(refused.exception), "home_lock_busy")
        self.assertFalse(other.held)
        # It took nothing on the way: the path lock it got first was let go again.
        third = HomeLock(self.root / "not-yet", self.locks)
        third.path = other.path
        self.assertTrue(self.held(third).held)

    def test_a_junction_to_a_home_is_that_home(self):
        link = self.root / "through"
        if not junction(self.home, link):
            self.skipTest("no junction could be made here")
        self.held(HomeLock(self.home, self.locks))
        with self.assertRaises(AdapterError):
            HomeLock(link, self.locks).__enter__()

    def test_the_path_lock_alone_still_excludes_the_same_spelling(self):
        """A v0.6.14-beta watcher takes the path lock only: it and this one still exclude each other."""
        with patch.object(folderid, "identity", return_value=None):
            self.held(HomeLock(self.home, self.locks))
        with self.assertRaises(AdapterError):
            HomeLock(self.home, self.locks).__enter__()

    def test_the_default_home_before_codex_made_it_is_locked_by_its_path_as_before(self):
        lock = self.held(HomeLock(self.root / "not-yet", self.locks))
        self.assertTrue(lock.held)
        self.assertEqual([path.name for path in self.locks.iterdir()], [lock.path.name])

    def test_a_home_that_needs_its_identity_is_not_locked_without_it(self):
        lock = HomeLock(self.root / "not-yet", self.locks, require_identity=True)
        with self.assertRaises(AdapterError) as refused:
            lock.__enter__()
        self.assertEqual(str(refused.exception), "home_unavailable")
        self.assertFalse(lock.held)
        # Nothing was left held: the same path can be locked at once.
        self.held(HomeLock(self.root / "not-yet", self.locks))

    def test_the_path_lock_keeps_the_name_it_has_had_since_v0_6_0(self):
        expected = hashlib.sha256(os.path.normcase(str(self.home.resolve())).encode("utf-8")).hexdigest()
        self.assertEqual(HomeLock(self.home, self.locks).path.name, expected + ".lock")
        self.assertEqual(homes.key(self.home), expected)


class WhatAHomeMustBeTests(Case):
    def test_well_formed(self):
        good = [self.entry("C:\\Codex\\work"), self.entry("D:\\other", "Other one")]
        self.assertTrue(homes.well_formed(good))
        self.assertEqual(homes.coerce(good, []), good)
        for bad in ([self.entry("C:\\a%d" % n, str(n)) for n in range(4)],    # four more
                    [self.entry("\\\\server\\share\\codex")],                   # UNC
                    [self.entry("relative\\codex")],
                    [self.entry("C:\\a", "")], [self.entry("C:\\a", "x" * 33)], [self.entry("C:\\a", " pad")],
                    [self.entry("C:\\a", "two\nlines")],
                    [self.entry("C:\\a"), self.entry("c:\\A\\", "other")],       # one path twice
                    [self.entry("C:\\a", "Work"), self.entry("C:\\b", "work")],   # one alias twice
                    [dict(self.entry("C:\\a"), extra=1)], "C:\\a", None):
            with self.subTest(bad):
                self.assertFalse(homes.well_formed(bad))
                self.assertEqual(homes.coerce(bad, []), [])

    def test_a_folder_to_watch(self):
        self.assertIsNone(homes.problem(self.home))
        self.assertEqual(homes.problem("\\\\server\\share\\codex"), homes.UNC)
        self.assertEqual(homes.problem(self.root / "nothing"), homes.MISSING)
        empty = self.root / "empty"
        empty.mkdir()
        self.assertEqual(homes.problem(empty), homes.NO_STATE)
        link = self.root / "through"
        if junction(self.home, link):
            self.assertEqual(homes.problem(link), homes.LINK, "a junction itself is named by what it points to")

    @unittest.skipUnless(WINDOWS, "folder identities are Windows'")
    def test_the_strict_write_refuses_one_folder_twice(self):
        default, other = self.codex_home("default"), self.codex_home("other")
        homes.strict([self.entry(self.home), self.entry(other, "again")], default, folderid.identity)
        with self.assertRaisesRegex(ValueError, "same folder as the default Codex home"):
            homes.strict([self.entry(default)], default, folderid.identity)
        # One folder under two names: refused by its identity, where the paths are not alike.
        spelled = {str(self.home): "id-1", str(other): "id-1"}
        with self.assertRaisesRegex(ValueError, "that is the same folder as work"):
            homes.strict([self.entry(self.home), self.entry(other, "again")], None,
                         lambda path: spelled.get(str(path)))
        empty = self.root / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, "no Codex state"):
            homes.strict([self.entry(empty)], default, folderid.identity)
        link = self.root / "through"
        if junction(self.home, link):
            with self.assertRaisesRegex(ValueError, "link or a junction"):
                homes.strict([self.entry(link)], default, folderid.identity)


if __name__ == "__main__":
    unittest.main()
