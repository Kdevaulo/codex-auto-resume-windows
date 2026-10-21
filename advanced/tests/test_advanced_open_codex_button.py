"""Open Codex on a notice (v0.6.18): while the capability is on and Windows has a handler for `codex:`, a notice about
one conversation offers Open Codex beside Open Dashboard, and a click hands exactly that conversation's Codex link to
the opener; off, or with no handler, or for a notice about no conversation, every notice is exactly the standard
edition's.

Held against the shipped definition and statement, the edition's own surface, core's notifier and the watcher's
handling of what the surface says. The registry is never read: every test gives the handler check its own reader.

    PYTHONPATH=src python -m unittest discover -s advanced/tests
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import advancedcase as ac  # noqa: E402
from codex_auto_resume import notifier, notify  # noqa: E402
from codex_auto_resume.domain.plug import DEFER, Surface  # noqa: E402
from codex_auto_resume.runtime.app import App  # noqa: E402
from codex_auto_resume_advanced import registry, statement, surfaces  # noqa: E402
from codex_auto_resume_advanced.control import opencodex  # noqa: E402
from codex_auto_resume_advanced.registry import OPEN_CODEX_BUTTON  # noqa: E402
from codex_auto_resume_advanced.vocabulary import Actor, CapabilityKind  # noqa: E402

CAP = "open_codex_button"
THREAD = ac.THREAD
LINK = notify.codex_thread_uri(THREAD)


def reader(*registered):
    """A registry reader that finds the `codex:` scheme under the roots named, and raises for any other read."""
    asked = []

    def read(root, path, value):
        asked.append((root, path, value))
        if root in registered and path == opencodex.PROTOCOL_KEY and value == opencodex.PROTOCOL_VALUE:
            return True
        raise FileNotFoundError(path)
    read.asked = asked
    return read


def interruption():
    return notifier.build("interruption", {"thread_id": THREAD, "interruption_id": ac.KEY, "reset_at": None,
                                           "category": "usage_limit"})


class DefinitionTests(unittest.TestCase):
    def test_it_is_an_action_departing_from_a28_b16_and_f6_shown_right_after_send_now(self):
        self.assertEqual((OPEN_CODEX_BUTTON.kind, OPEN_CODEX_BUTTON.points, OPEN_CODEX_BUTTON.compat,
                          OPEN_CODEX_BUTTON.ceilings), (CapabilityKind.ACTION, frozenset(), None, None))
        self.assertEqual(OPEN_CODEX_BUTTON.departs_from, ("A28", "B16", "F6"))
        self.assertIn(CAP, registry.REGISTRY.ids)
        order = registry.SHOWN_ORDER
        self.assertEqual(order[order.index("send_now") + 1], CAP)
        self.assertEqual(statement.CATALOGS.missing(OPEN_CODEX_BUTTON), [])


class HandlerTests(unittest.TestCase):
    def test_the_scheme_is_read_under_the_user_then_the_machine_and_never_written(self):
        self.assertTrue(opencodex.handler_registered(reader("HKEY_CURRENT_USER")))
        machine = reader("HKEY_LOCAL_MACHINE")
        self.assertTrue(opencodex.handler_registered(machine))
        self.assertEqual([root for root, _path, _value in machine.asked], ["HKEY_CURRENT_USER", "HKEY_LOCAL_MACHINE"])
        self.assertFalse(opencodex.handler_registered(reader()))
        self.assertFalse(opencodex.handler_registered(lambda *_: "yes"), "only a read that found the value counts")

    def test_an_answer_is_reused_for_a_minute(self):
        now = [0.0]
        read = reader("HKEY_CURRENT_USER")
        code = opencodex.OpenCodexButton(None, read=read, clock=lambda: now[0])
        self.assertTrue(code.available())
        self.assertTrue(code.available())
        self.assertEqual(len(read.asked), 1)
        now[0] += opencodex.REUSE
        self.assertTrue(code.available())
        self.assertEqual(len(read.asked), 2)

    def test_the_default_reader_opens_for_reading_alone(self):
        source = Path(opencodex.__file__).read_text(encoding="utf-8")
        self.assertIn("winreg.KEY_READ", source)
        for write in ("SetValue", "CreateKey", "DeleteKey", "DeleteValue", "KEY_WRITE", "KEY_SET_VALUE",
                      "KEY_ALL_ACCESS"):
            self.assertNotIn(write, source)


class SurfaceTests(ac.AdvancedCase):
    def setUp(self):
        super().setUp()
        self.catalogs = statement.CATALOGS

    def plugged(self, registered):
        plug = self.plug(OPEN_CODEX_BUTTON)
        code = plug.runtime.action(OPEN_CODEX_BUTTON)
        code._read = reader(*registered)
        return plug

    def test_off_the_icon_s_surface_carries_nothing_of_it(self):
        plug = self.plugged(["HKEY_CURRENT_USER"])
        self.assertNotIn("notice", plug.surface(Surface.TRAY, {}))

    def test_on_with_a_handler_the_surface_asks_for_the_button(self):
        plug = self.plugged(["HKEY_CURRENT_USER"])
        self.arm(plug.runtime, CAP)
        plug.runtime.states(fresh=True)
        self.assertEqual(plug.surface(Surface.TRAY, {})["notice"], {"open_codex": True})
        self.assertEqual(surfaces.notice_view(plug.runtime), {"notice": {"open_codex": True}})

    def test_on_with_no_handler_the_button_is_not_offered(self):
        plug = self.plugged([])
        self.arm(plug.runtime, CAP)
        plug.runtime.states(fresh=True)
        self.assertNotIn("notice", plug.surface(Surface.TRAY, {}))

    def test_turned_off_again_the_surface_says_nothing_of_it(self):
        plug = self.plugged(["HKEY_CURRENT_USER"])
        self.arm(plug.runtime, CAP)
        plug.runtime.arming.disarm(CAP, actor=Actor.DASHBOARD)
        plug.runtime.states(fresh=True)
        self.assertEqual(surfaces.notice_view(plug.runtime), {})


class NoticeTests(unittest.TestCase):
    def test_on_a_notice_about_one_conversation_offers_its_codex_link_after_open_dashboard(self):
        plain = interruption()
        shown = notifier.with_open_codex(plain, True)
        self.assertEqual(len(shown.actions), len(plain.actions) + 1)
        self.assertIn(LINK, [uri for _label, uri in shown.actions])
        uris = [uri for _label, uri in shown.actions]
        self.assertEqual(uris.index(LINK), [notify.parse_open_uri(uri) is not None for uri in uris].index(True) + 1)
        label = dict((uri, label) for label, uri in shown.actions)[LINK]
        self.assertEqual(label, notify.l10n.message("toast_button_open_codex"))
        # The toast carries the same button the card draws.
        self.assertIn((label, LINK), [tuple(pair) for pair in shown.toast_content()["more"]])
        self.assertEqual(notifier.with_open_codex(shown, True), shown, "never twice")

    def test_off_every_notice_is_exactly_the_standard_edition_s(self):
        plain = interruption()
        for off in (False, None, "yes", 1):
            with self.subTest(off=off):
                self.assertIs(notifier.with_open_codex(plain, off), plain)

    def test_a_notice_about_no_conversation_never_gains_it(self):
        for event, detail in (("after_sleep", {"slept": 7200, "count": 2}),
                              ("near_limit", {"minutes": 300, "percent": 90, "reset_at": None}),
                              ("memory_warning", {"used": 300, "limit": 200})):
            with self.subTest(event=event):
                plain = notifier.build(event, detail)
                self.assertIsNone(plain.key)
                self.assertIs(notifier.with_open_codex(plain, True), plain)
        odd = replace(interruption(), key="not-a-uuid")
        self.assertIs(notifier.with_open_codex(odd, True), odd)

    def test_a_click_on_it_hands_exactly_that_link_to_the_opener(self):
        opened = []
        said = notifier.activate(LINK, open_link=lambda link: opened.append(link) or True)
        self.assertEqual((said, opened), ("opened", [LINK]))


class WatcherTests(unittest.TestCase):
    """What the edition's surface says, taken up by the watcher: the flag follows the surface tick by tick."""

    class Watcher:
        def __init__(self):
            self.shown = []

        def _near_limit(self, added):
            self.shown.append(added)

        def _update_offered(self, added):
            self.shown.append(added)

    def test_the_flag_is_on_only_while_the_surface_asks_for_it(self):
        watcher = self.Watcher()
        App._edition_notices(watcher, {"notice": {"open_codex": True}})
        self.assertTrue(watcher._open_codex)
        for said in ({}, {"notice": {"open_codex": "yes"}}, {"notice": True}, DEFER, None):
            with self.subTest(said=said):
                App._edition_notices(watcher, {"notice": {"open_codex": True}})
                App._edition_notices(watcher, said)
                self.assertFalse(watcher._open_codex)

    def test_a_notice_the_watcher_announces_carries_the_button_while_the_flag_is_on(self):
        built = []

        class Settings(dict):
            pass

        for flag in (True, False):
            with self.subTest(flag=flag):
                app = App.__new__(App)
                app.settings = Settings(notifications=True)
                app._open_codex = flag
                app._inbox = None
                source = type("Source", (), {"identity": lambda _self, _thread: None})()
                with patch.object(notifier, "deliver", lambda notice, **_kw: built.append(notice) or ("toast", True)):
                    App._notifier(app, source)("interruption", {"thread_id": THREAD, "interruption_id": ac.KEY,
                                                                "reset_at": None, "category": "usage_limit"})
                self.assertEqual(LINK in [uri for _label, uri in built[-1].actions], flag)


if __name__ == "__main__":
    unittest.main()
