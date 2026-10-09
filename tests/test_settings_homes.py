"""Settings name up to three more Codex homes with an alias, and only the Dashboard writes them (v0.6.14-beta.2).

`codex_homes` is a list of {"path", "alias"}: none by default, which is the default home alone, as before. A
hand-edited file in any other shape reads as none (settings.coerce); the Dashboard's write is strict - the
shape, and then each folder against this PC (homes.strict through Control.update_settings): it can be watched,
and it is neither the default home nor another home under a second name. No generated editor draws the field
(settings.describe leaves it out), MCP's schema never offers it, and MCP's update_settings refuses it by name
even where a schema would - which is what the last test reverts to prove. Restore defaults keeps the homes.

Scratch folders only: CODEX_HOME points at a temporary folder for every test that asks the default home.
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
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import config, control, homes, settings  # noqa: E402
from codex_auto_resume.control import ControlError  # noqa: E402


class Case(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.default = self.codex_home("default")
        environment = patch.dict(os.environ, {"CODEX_HOME": str(self.default)})
        environment.start()
        self.addCleanup(environment.stop)
        self.paths = config.Paths(self.root / "product")
        self.paths.ensure()
        self.control = control.Control(self.paths)
        for name, value in (("watcher_running", True), ("startup_enabled", False)):
            patcher = patch.object(control.Control, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def codex_home(self, name):
        folder = self.root / name
        folder.mkdir()
        (folder / "state_5.sqlite").write_bytes(b"")
        return folder

    @staticmethod
    def entry(path, alias="work"):
        return {"path": str(path), "alias": alias}


class FieldTests(Case):
    def test_none_by_default_and_never_drawn_by_a_generated_editor(self):
        self.assertEqual(settings.defaults()[homes.FIELD], [])
        self.assertEqual(settings.field_type(homes.FIELD), "array")
        self.assertNotIn(homes.FIELD, {entry["name"] for entry in settings.describe()})
        self.assertIn(homes.FIELD, settings.DASHBOARD_ONLY)

    def test_a_hand_edited_file_in_another_shape_reads_as_none(self):
        for stored in ("C:\\work", [{"path": "C:\\work"}], [self.entry("C:\\a", "%d" % n) for n in range(4)]):
            with self.subTest(stored):
                self.paths.settings_file.write_text(json.dumps({"config_version": 2, homes.FIELD: stored}),
                                                    encoding="utf-8")
                self.assertEqual(settings.load(self.paths.settings_file)[homes.FIELD], [])

    def test_the_dashboards_write_keeps_what_can_be_watched(self):
        work, other = self.codex_home("work"), self.codex_home("other")
        written = [self.entry(work), self.entry(other, "Other")]
        self.assertEqual(self.control.update_settings({homes.FIELD: written})[homes.FIELD], written)
        self.assertEqual(settings.load(self.paths.settings_file)[homes.FIELD], written)

    def test_the_dashboards_write_refuses_in_words_a_person_can_act_on(self):
        work = self.codex_home("work")
        empty = self.root / "empty"
        empty.mkdir()
        cases = {
            "four more": ([self.entry(self.codex_home("h%d" % n), "h%d" % n) for n in range(4)], "at most 3"),
            "a bad alias": ([self.entry(work, "x" * 33)], "alias"),
            "one alias twice": ([self.entry(work, "A"), self.entry(self.codex_home("b"), "a")], "no two alike"),
            "the default home": ([self.entry(self.default, "again")], "same folder as the default Codex home"),
            "no state there": ([self.entry(empty)], "no Codex state"),
            "no such folder": ([self.entry(self.root / "nowhere")], "no such folder"),
        }
        for name, (value, words) in cases.items():
            with self.subTest(name):
                with self.assertRaises(ControlError) as refused:
                    self.control.update_settings({homes.FIELD: value})
                self.assertIn(words, str(refused.exception))
                self.assertEqual(settings.load(self.paths.settings_file)[homes.FIELD], [])

    def test_restore_defaults_keeps_the_homes(self):
        written = [self.entry(self.codex_home("work"))]
        self.control.update_settings({homes.FIELD: written, "max_no_progress": 5})
        restored = self.control.restore_defaults()
        self.assertEqual(restored[homes.FIELD], written)
        self.assertEqual(restored["max_no_progress"], settings.DEFAULTS["max_no_progress"])


class SurfaceTests(Case):
    """Pending, History and the status say which home a record is of, only while there is more than one."""

    def record(self, home_key):
        from codex_auto_resume.store import Store
        from codex_auto_resume.domain import ids
        thread, turn = "0a1b2c3d-0001-7000-8000-000000000001", "0a1b2c3d-0002-7000-8000-000000000002"
        key = ids.interruption_id(thread, turn, 110.0, 2, home_key=home_key)
        with Store(self.paths.state_dir) as store:
            store.register({"thread_id": thread, "turn_id": turn, "completed_at": 110.0, "started_at": 105.0,
                            "ordinal": 2, "interruption_id": key, "reset_at": None, "limit_type": "x",
                            "uncertain": False, "category": "server_5xx"}, 120.0, home_key=home_key)
        return key

    def test_a_record_of_another_home_carries_its_alias_and_none_with_one_home(self):
        work = self.codex_home("work")
        default_key, other_key = self.record(""), self.record(homes.key(work))
        rows = {row["interruption_id"]: row for row in self.control.list_pending()}
        self.assertEqual({key: row["home"] for key, row in rows.items()}, {default_key: None, other_key: None})
        self.assertEqual(self.control.get_status()["codex_homes"],
                         {"homes": [{"key": "", "alias": None, "path": None, "state": "watched"}], "unmeasured": False})
        self.control.update_settings({homes.FIELD: [self.entry(work, "Work")]})
        rows = {row["interruption_id"]: row for row in self.control.list_pending()}
        self.assertEqual({key: row["home"] for key, row in rows.items()}, {default_key: None, other_key: "Work"})
        view = self.control.get_status()["codex_homes"]
        self.assertEqual([(home["alias"], home["path"]) for home in view["homes"]], [(None, None), ("Work", str(work))])

    def test_unproven_on_a_codex_newer_than_the_one_measured(self):
        self.assertFalse(homes.unmeasured("0.158.0-alpha.2.1"))
        self.assertTrue(homes.unmeasured("0.159.0"))
        self.assertTrue(homes.unmeasured("1.0.0"))
        self.assertTrue(homes.unmeasured(None))


class McpRefusalTests(Case):
    def call(self, arguments):
        from codex_auto_resume.mcp import server
        return server.Server(self.control)._tool_update_settings(arguments)

    def test_refused_by_name_even_where_a_schema_would_offer_it(self):
        """A schema that offered codex_homes - a group moved, a schema ignored - still does not let Codex write
        where the watcher looks: the refusal by name comes first. Reverting it makes this test fail."""
        from codex_auto_resume.mcp import server
        offering = {"type": "object", "properties": {homes.FIELD: {"type": "array"}}}
        with patch.object(server, "settings_schema", return_value=offering), \
                patch.object(self.control, "update_settings") as update:
            with self.assertRaises(ControlError) as refused:
                self.call({homes.FIELD: [self.entry(self.codex_home("work"))]})
        self.assertIn("not changeable from Codex: codex_homes", str(refused.exception))
        update.assert_not_called()

    def test_no_reply_to_codex_carries_a_homes_folder(self):
        """The folders are paths, which may hold the Windows user name; MCP's replies go on to OpenAI."""
        from codex_auto_resume.mcp import server
        work = self.codex_home("work")
        self.control.update_settings({homes.FIELD: [self.entry(work)]})
        handler = server.Server(self.control)
        for name in ("get_status", "open_settings", "restore_default_settings"):
            with self.subTest(name):
                reply = getattr(handler, "_tool_" + name)({})
                text = json.dumps(reply)
                self.assertNotIn(homes.FIELD, text)
                self.assertNotIn(str(work).replace("\\", "\\\\"), text)

    def test_the_schema_never_offers_it(self):
        from codex_auto_resume.mcp import tools
        self.assertNotIn(homes.FIELD, tools.settings_schema()["properties"])


if __name__ == "__main__":
    unittest.main()
