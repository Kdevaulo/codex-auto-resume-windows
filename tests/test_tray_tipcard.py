"""The icon's own tooltip card (v0.6.24, surface D, the owner's option 2): what it says, where it goes, how it is drawn.

Hovering over the icon shows a card in the product's design instead of Windows' tooltip: the popup header's light, the
product's name and in the advanced edition its edition's chip, the state line with its countdown in the accent, and in
the advanced edition a row per usage window - the same facts the tooltip has always said, no new ones
(words.tooltip_parts, which tooltip() joins). Its plan is pure (tipplan.py); its picture is the popup's renderer drawing
into memory (tipcard.TipRenderer, draw_offscreen) - nothing here shows a window or captures one.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import statistics
import sys
import time
import unittest

_HERE = str(Path(__file__).resolve().parent)
for entry in (str(Path(_HERE).parent / "src"), _HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from codex_auto_resume import brand, interface, l10n  # noqa: E402
from codex_auto_resume.ui import popup  # noqa: E402
from codex_auto_resume.ui.tray import tipplan, words  # noqa: E402

NOW = 1_800_000_000.0
EN = interface.STRINGS["en"]
METER = {"windows": [{"window_minutes": 300, "used_percent": 87.6}, {"window_minutes": 10080, "used_percent": 3},
                     {"window_minutes": 60, "used_percent": 130.0}, {"used_percent": 0}]}
# The icon's snapshots, as the watcher's tick makes them (model.snapshot_from) and the icon marks them (_shown).
FIXTURES = {
    "idle": {"enabled": True, "waiting": 0, "running": 0},
    "waiting": {"enabled": True, "waiting": 2, "running": 1, "next_at": NOW + 200},
    "due": {"enabled": True, "waiting": 1, "next_at": NOW - 1},
    "held": {"enabled": True, "waiting": 1, "held": 1, "next_at": NOW + 75},
    "paused": {"enabled": False, "waiting": 3},
    "failed": {"enabled": True, "waiting": 1, "failed": True},
    "unconfirmed": {"enabled": True, "unconfirmed": True},
    "metered": {"enabled": True, "waiting": 1, "next_at": NOW + 3725, "advanced": {"meter": METER}},
    "empty": {},
}


def measure(role, text, width, wrap):
    """A stand-in for GDI: 7 px a character, 16 px a line, wrapped at `width` when asked."""
    wide = 7 * len(text or " ")
    if not wrap or wide <= width:
        return min(wide, width) if wrap else wide, 16
    return width, 16 * -(-wide // max(1, int(width)))


def plan_for(name, edition=None, strings=EN, scale=1.0, light="monitoring"):
    parts = words.tooltip_parts(FIXTURES[name], strings, NOW, edition)
    return parts, tipplan.tip_layout(parts, light, scale, measure)


def texts(plan, role=None):
    return [item for item in plan["items"] if item["kind"] == "text" and (role is None or item["role"] == role)]


class PartsTests(unittest.TestCase):
    def test_the_parts_joined_are_the_tooltip_in_every_language_and_edition(self):
        """Fails if the card said a fact the tooltip does not, or left one out."""
        for locale, strings in interface.STRINGS.items():
            for name in FIXTURES:
                for edition in (None, "standard", "advanced"):
                    with self.subTest(locale=locale, fixture=name, edition=edition):
                        parts = words.tooltip_parts(FIXTURES[name], strings, NOW, edition)
                        joined = words.tooltip_joined(parts)
                        tip = words.tooltip(FIXTURES[name], strings, NOW, edition)
                        self.assertEqual(joined[:words.TIP_CHARS - 1] if parts["line"] else joined, tip)

    def test_the_card_is_never_cut_short_where_sztip_is(self):
        long = dict(FIXTURES["metered"], advanced={"meter": {"windows": [{"window_minutes": 300, "used_percent": 10}] * 12}})
        parts = words.tooltip_parts(long, EN, NOW, "advanced")
        self.assertEqual(len(words.tooltip(long, EN, NOW, "advanced")), words.TIP_CHARS - 1)
        self.assertGreater(len(words.tooltip_joined(parts)), words.TIP_CHARS)
        self.assertEqual(len(parts["meter"]), 12)

    def test_only_the_countdown_is_marked(self):
        parts = words.tooltip_parts(FIXTURES["waiting"], EN, NOW)
        self.assertEqual([text for text, counts in parts["line"] if counts], ["next check in 3:20"])
        for name in ("idle", "paused", "failed", "unconfirmed"):
            with self.subTest(name):
                self.assertFalse(any(counts for _, counts in words.tooltip_parts(FIXTURES[name], EN, NOW)["line"]))

    def test_the_meter_rows_say_what_the_meter_line_says(self):
        rows = words.tooltip_parts(FIXTURES["metered"], EN, NOW, "advanced")["meter"]
        self.assertEqual([(row["label"], row["percent"]) for row in rows],
                         [("5-hour", "13% left"), ("weekly", "97% left"), ("1-hour", "0% left"), ("limit", "100% left")])
        # v0.6.24 final: each bar is as full as the window has LEFT, and little left is the warning.
        for row, left, low in zip(rows, (0.124, 0.97, 0.0, 1.0), (False, False, True, False)):
            self.assertAlmostEqual(row["fraction"], left)
            self.assertIs(row["low"], low)
        self.assertEqual(" · ".join(row["text"] for row in rows), words.meter_line(FIXTURES["metered"], EN))
        # The share in each catalog's own words, the window's name taken out of its sentence.
        for locale, expected in (("de", "13 % übrig"), ("tr", "%13 kaldı"), ("ar", "المتبقي 13%"),
                                 ("ko", "13% 남음")):
            with self.subTest(locale):
                strings = interface.STRINGS[locale]
                percent = words.tooltip_parts(FIXTURES["metered"], strings, NOW)["meter"][0]["percent"]
                self.assertEqual(percent.replace(" ", " "), expected)

    def test_the_standard_edition_has_no_meter_rows(self):
        for name in FIXTURES:
            with self.subTest(name):
                if name != "metered":
                    self.assertEqual(words.tooltip_parts(FIXTURES[name], EN, NOW, "advanced")["meter"], [])


class PlanTests(unittest.TestCase):
    def test_the_edition_chip_is_there_only_in_the_advanced_edition(self):
        for edition, chips in ((None, 0), ("standard", 0), ("advanced", 1)):
            with self.subTest(edition):
                _, plan = plan_for("waiting", edition)
                self.assertEqual(sum(item["kind"] == "chip" for item in plan["items"]), chips)
                self.assertEqual([item["text"] for item in texts(plan, "chip")], ["Advanced"] * chips)

    def test_the_accent_is_exactly_the_countdown(self):
        _, plan = plan_for("waiting")
        self.assertEqual([item["text"] for item in texts(plan, "body") if item["colour"] == "accent"],
                         ["next check in 3:20"])
        for name in ("idle", "paused", "failed", "unconfirmed", "empty"):
            with self.subTest(name):
                _, plan = plan_for(name)
                self.assertEqual([item for item in texts(plan, "body") if item["colour"] == "accent"], [])
        _, plan = plan_for("held")
        self.assertEqual([item["text"] for item in texts(plan, "body") if item["colour"] == "accent"],
                         ["next check in 1:15"])

    def test_meter_rows_only_with_a_meter_and_each_bar_as_full_as_left(self):
        """v0.6.24 final (the owner, 2026-11-18): a bar is as full as its window has left - full is plenty left, and it
        empties as the window is used - and the share beside it is what is left."""
        for name in FIXTURES:
            with self.subTest(name):
                _, plan = plan_for(name, "advanced")
                bars = [item for item in plan["items"] if item["kind"] == "meter"]
                self.assertEqual([round(bar["fraction"], 6) for bar in bars], [0.124, 0.97, 0.0, 1.0] if name == "metered" else [])
        _, plan = plan_for("metered", "advanced")
        bars = [item for item in plan["items"] if item["kind"] == "meter"]
        self.assertEqual({bar["rect"][3] - bar["rect"][1] for bar in bars}, {tipplan.TIP_BAR})
        self.assertEqual(len({(bar["rect"][0], bar["rect"][2]) for bar in bars}), 1, "the bars line up")
        shares = [item for item in texts(plan, "small") if item["align"] == "right"]
        self.assertEqual([item["text"] for item in shares], ["13% left", "97% left", "0% left", "100% left"])
        # Little left (words.LOW_LEFT or less) is the warning, the share and its bar alike; the rest in ink and the accent.
        self.assertEqual([item["colour"] for item in shares], ["ink", "ink", "warning", "ink"])
        self.assertEqual([bar["low"] for bar in bars], [False, False, True, False])

    def test_the_warning_starts_where_little_is_left_the_used_90_mirrored(self):
        def row(used):
            snapshot = dict(FIXTURES["idle"], advanced={"meter": {"windows": [{"window_minutes": 300, "used_percent": used}]}})
            return words.tooltip_parts(snapshot, EN, NOW, "advanced")["meter"][0]
        self.assertEqual(words.LOW_LEFT, 10)
        for used, low in ((0, False), (89.9, False), (90, True), (99.6, True), (100, True), (250, True)):
            with self.subTest(used=used):
                self.assertIs(row(used)["low"], low)
        self.assertEqual([row(used)["percent"] for used in (0, 89.9, 90, 99.6, 100, 250)],
                         ["100% left", "11% left", "10% left", "1% left", "0% left", "0% left"])
        # Unknown usage is no row at all, as before.
        for used in (None, "87", True):
            snapshot = dict(FIXTURES["idle"], advanced={"meter": {"windows": [{"window_minutes": 300, "used_percent": used}]}})
            self.assertEqual(words.tooltip_parts(snapshot, EN, NOW, "advanced")["meter"], [])

    def test_every_word_of_the_parts_is_on_the_card_in_order(self):
        for name in FIXTURES:
            with self.subTest(name):
                parts, plan = plan_for(name, "advanced")
                said = [parts["title"], parts["edition"]] + [text for text, _ in parts["line"]]
                for row in parts["meter"]:
                    said += [row["label"], row["percent"]]
                drawn = [item["text"] for item in texts(plan) if item["text"] != tipplan.TIP_JOIN]
                self.assertEqual(drawn, said)

    def test_the_light_is_the_popup_headers_and_stands_inside_the_card(self):
        for scale in (1.0, 1.5, 2.0):
            with self.subTest(scale=scale):
                _, plan = plan_for("waiting", light="waiting", scale=scale)
                halo = next(item for item in plan["items"] if item["kind"] == "halo")
                self.assertEqual(halo["state"], "waiting")
                self.assertAlmostEqual(halo["radius"], brand.glow_extent(brand.STATUS_DOT["popup"]) * scale)
                card = plan["card"]
                self.assertGreaterEqual(min(halo["cx"] - card[0], halo["cy"] - card[1]), halo["radius"])

    def test_the_card_is_at_most_360_wide_and_a_long_line_wraps(self):
        for scale in (1.0, 1.25, 1.5, 2.0):
            for locale, strings in interface.STRINGS.items():
                with self.subTest(scale=scale, locale=locale):
                    _, plan = plan_for("metered", "advanced", strings, scale)
                    width = plan["size"][0]
                    self.assertLessEqual(width, int(round(360 * scale)))
                    for item in plan["items"]:
                        if "rect" in item and item["kind"] != "card":
                            self.assertLessEqual(item["rect"][2], width - int(round(tipplan.TIP_PAD_X * scale)))
        long = dict(EN, **{"tray.waiting": "{n} " + "waiting " * 30})
        _, plan = plan_for("waiting", strings=long)
        self.assertEqual(plan["size"][0], 360)
        self.assertTrue(any(item["wrap"] for item in texts(plan, "body")))

    def test_no_row_leaves_the_right_side_emptier_than_the_left(self):
        # The owner, 2026-11-16, of the card with no usage rows: "우측이 빈공간이 큰게 아쉬워" - the 280 least width it
        # had left the right side wider than the left. The card is as wide as its widest row: that row ends one side
        # padding from the right edge, in every state, edition, language and scale.
        for name in FIXTURES:
            for edition in (None, "advanced"):
                for scale in (1.0, 1.5, 2.0):
                    for locale, strings in interface.STRINGS.items():
                        with self.subTest(name=name, edition=edition, scale=scale, locale=locale):
                            _, plan = plan_for(name, edition, strings, scale)
                            rights = [item["rect"][2] for item in plan["items"]
                                      if "rect" in item and item["kind"] != "card"]
                            pad = int(round(tipplan.TIP_PAD_X * scale))
                            self.assertEqual(max(rights), plan["size"][0] - pad)

    def test_a_line_broken_in_two_takes_its_widest_line_not_the_whole_width(self):
        # Broken where the widest card breaks it, then the card shrinks to the widest line it broke into (the stand-in
        # measure breaks the English waiting line in two at 100 %).
        _, plan = plan_for("waiting")
        lines = sorted({item["rect"][1] for item in texts(plan, "body")})
        self.assertEqual(len(lines), 2)
        self.assertLess(plan["size"][0], 360)
        widest = max(item["rect"][2] for item in texts(plan, "body"))
        self.assertEqual(widest, plan["size"][0] - tipplan.TIP_PAD_X)

    def test_mirrored_the_light_is_at_the_right_and_every_line_aligned_right(self):
        parts, plan = plan_for("metered", "advanced")
        mirrored = popup.mirror(plan)
        width = plan["size"][0]
        self.assertTrue(mirrored["rtl"])
        light = next(item for item in mirrored["items"] if item["kind"] == "halo")
        self.assertGreater(light["cx"], width / 2)
        title = texts(mirrored, "name")[0]
        self.assertLess(title["rect"][2], light["cx"])
        self.assertTrue(all(item["mirrored"] for item in mirrored["items"]))
        shares = [item for item in texts(mirrored, "small") if item["text"] in [row["percent"] for row in parts["meter"]]]
        self.assertTrue(all(item["align"] == "left" and item["rect"][0] < width / 2 for item in shares))


class PlaceTests(unittest.TestCase):
    """The popup's own placement: TIP_GAP from the taskbar, beside the icon, inside the work area, on each edge."""

    PLAN = {"card": (0, 0, 300, 80), "size": (300, 80), "scale": 1.0}

    def place(self, work, monitor, box, plan=None):
        from codex_auto_resume.ui.tray import tipcard
        return tipcard.tip_place(plan or self.PLAN, work, monitor, box)

    def test_on_every_edge_the_card_is_eight_pixels_off_the_taskbar(self):
        monitor = (0, 0, 1920, 1080)
        cases = {"bottom": ((0, 0, 1920, 1032), (1700, 1040, 1724, 1064)),
                 "top": ((0, 48, 1920, 1080), (1700, 12, 1724, 36)),
                 "left": ((48, 0, 1920, 1080), (12, 900, 36, 924)),
                 "right": ((0, 0, 1872, 1080), (1884, 900, 1908, 924))}
        for edge, (work, icon) in cases.items():
            with self.subTest(edge):
                x, y = self.place(work, monitor, icon)
                if edge == "bottom":
                    self.assertEqual(y + 80, work[3] - tipplan.TIP_GAP)
                    self.assertEqual(x + 150, (icon[0] + icon[2]) // 2)
                elif edge == "top":
                    self.assertEqual(y, work[1] + tipplan.TIP_GAP)
                elif edge == "left":
                    self.assertEqual(x, work[0] + tipplan.TIP_GAP)
                    self.assertEqual(y + 40, (icon[1] + icon[3]) // 2)
                else:
                    self.assertEqual(x + 300, work[2] - tipplan.TIP_GAP)
                self.assertTrue(work[0] <= x and x + 300 <= work[2] and work[1] <= y and y + 80 <= work[3])

    def test_on_a_monitor_left_of_the_primary_one_and_at_one_and_a_half(self):
        monitor, work = (-2880, -200, 0, 1420), (-2880, -200, 0, 1348)
        plan = {"card": (0, 0, 450, 120), "size": (450, 120), "scale": 1.5}
        x, y = self.place(work, monitor, (-60, 1360, -24, 1396), plan)
        self.assertEqual(y + 120, 1348 - 12)
        self.assertEqual(x + 450, 0 - 12, "kept inside the work area, 12 px (8 at 150 %) from its edge")

    def test_the_anchor_is_the_icon_where_the_pointer_is_on_it_else_the_point(self):
        icon = (100, 200, 124, 224)
        self.assertEqual(tipplan.tip_anchor(icon, None, (110, 210)), icon)
        self.assertEqual(tipplan.tip_anchor(icon, (105, 205), (5, 5)), icon)
        # The hidden-icons flyout: Windows 11 gives the flyout button's rectangle; the anchor point is the icon's.
        self.assertEqual(tipplan.tip_anchor(icon, (300, 150), (301, 151)), (300, 150, 301, 151))
        self.assertEqual(tipplan.tip_anchor(None, None, (-40, 7)), (-40, 7, -39, 8))
        self.assertEqual(tipplan.tip_anchor(icon), icon)
        self.assertIsNone(tipplan.tip_anchor())


@unittest.skipUnless(os.name == "nt", "the card is drawn by GDI and GDI+")
class DrawTests(unittest.TestCase):
    """Drawn into memory by the popup's renderer, as the popup's and the menu's look tests draw: nothing is shown."""

    def setUp(self):
        from codex_auto_resume.ui.tray import tipcard
        self.tipcard = tipcard

    def draw(self, name="metered", light="monitoring", locale="en", **look):
        parts = words.tooltip_parts(FIXTURES[name], interface.STRINGS[locale], NOW, "advanced")
        return self.tipcard.draw_offscreen(parts, light, locale=locale, **look)

    @staticmethod
    def pixel(plan, pixels, x, y):
        index = (int(y) * plan["size"][0] + int(x)) * 4
        blue, green, red, alpha = pixels[index:index + 4]
        return (red, green, blue), alpha

    def test_the_card_has_no_lift_no_drop_shadow_and_no_lit_edge(self):
        """Decided for the card as for the icon's menu (the owner, 2026-11-01 and 11-02, test_tray_menu_no_glow): a lift's
        shadow and highlight shone as a halo round a floating surface on a dark taskbar. Fails if one comes back: the
        renderer is asked for no lift and no inset light, the card fills its window, and in dark the row inside its top
        hairline is the card's own ground."""
        from unittest import mock
        renderer = self.tipcard.TipRenderer()
        self.addCleanup(renderer.close)
        parts = words.tooltip_parts(FIXTURES["metered"], EN, NOW, "advanced")
        for theme in ("light", "dark"):
            for design in brand.DESIGNS:
                with self.subTest(theme=theme, design=design):
                    renderer.theme, renderer.design, renderer.contrast = theme, design, False
                    plan = renderer.tip_layout(parts, "monitoring", 1.5, "en")
                    self.assertEqual(plan["card"], (0, 0) + tuple(plan["size"]), "no room is kept round it for a shadow")
                    with mock.patch.object(renderer, "_lift", wraps=renderer._lift) as lift,                             mock.patch.object(renderer, "_inner", wraps=renderer._inner) as inner:
                        pixels = bytes(renderer.draw_tip(plan, None).pixels())
                    self.assertFalse(any(call.args[0] == "card" for call in lift.call_args_list), "a lift")
                    self.assertFalse(any(call.args[0] == "card" for call in inner.call_args_list), "an inset light")
                    width = plan["size"][0]
                    border = int(max(1.0, round(1.5)))
                    ground = brand.rgb(brand.card_ground(theme, design))
                    for x in (width // 2 - 30, width // 2 + 30):
                        self.assertEqual(self.pixel(plan, pixels, x, border), (ground, 255))

    def test_round_the_card_nothing_is_drawn_and_on_it_everything_is_opaque(self):
        for theme in ("light", "dark"):
            with self.subTest(theme):
                plan, pixels = self.draw(theme=theme, scale=1.5)
                width, height = plan["size"]
                self.assertEqual(self.pixel(plan, pixels, 0, 0)[1], 0, "the corner outside the round card")
                self.assertEqual(self.pixel(plan, pixels, width - 1, height - 1)[1], 0)
                for item in texts(plan):
                    left, top, right, bottom = item["rect"]
                    self.assertEqual(self.pixel(plan, pixels, (left + right) // 2, (top + bottom) // 2)[1], 255,
                                     item["text"])
                ground = brand.rgb(brand.card_ground(theme, "soft"))
                self.assertEqual(self.pixel(plan, pixels, width // 2, height - 4), (ground, 255))

    def test_the_light_is_drawn_in_its_state_colour(self):
        for light in ("monitoring", "attention", "failed", "paused"):
            with self.subTest(light):
                plan, pixels = self.draw(light=light)
                halo = next(item for item in plan["items"] if item["kind"] == "halo")
                colour, alpha = self.pixel(plan, pixels, halo["cx"], halo["cy"])
                self.assertEqual((colour, alpha), (brand.rgb(brand.status_colour(light, "light")), 255))

    def test_a_bar_is_the_accent_as_far_as_left_and_the_well_beyond(self):
        """v0.6.24 final: 87.6% used leaves 12.4%, so the accent reaches past a twentieth of the bar and not a quarter."""
        for locale in ("en", "ar"):
            with self.subTest(locale):
                plan, pixels = self.draw(locale=locale, scale=2.0)
                bar = next(item for item in plan["items"] if item["kind"] == "meter")      # 87.6 % used, 12.4 % left
                left, top, right, bottom = bar["rect"]
                middle = (top + bottom) // 2
                kept = right - (right - left) // 20 if locale == "ar" else left + (right - left) // 20
                gone = right - (right - left) // 4 if locale == "ar" else left + (right - left) // 4
                tokens = brand.palette("light", "soft")
                self.assertEqual(self.pixel(plan, pixels, kept, middle)[0], brand.rgb(tokens["accent"]))
                self.assertNotEqual(self.pixel(plan, pixels, gone, middle)[0], brand.rgb(tokens["accent"]))

    def test_in_high_contrast_it_is_the_systems_colours(self):
        plan, pixels = self.draw(contrast=True)
        width, height = plan["size"]
        self.assertEqual(self.pixel(plan, pixels, width // 2, height - 4)[0],
                         popup.system_rgb(popup.contrast_colour("surface")))
        halo = next(item for item in plan["items"] if item["kind"] == "halo")
        self.assertEqual(self.pixel(plan, pixels, halo["cx"], halo["cy"])[0],
                         popup.system_rgb(brand.status_system("monitoring")))
        bar = next(item for item in plan["items"] if item["kind"] == "meter")
        self.assertEqual(self.pixel(plan, pixels, bar["rect"][0] + 3, (bar["rect"][1] + bar["rect"][3]) // 2)[0],
                         popup.system_rgb(popup.contrast_colour("accent")))

    def test_a_frame_of_the_light_redraws_only_its_band(self):
        renderer = self.tipcard.TipRenderer()
        self.addCleanup(renderer.close)
        parts = words.tooltip_parts(FIXTURES["metered"], EN, NOW, "advanced")
        plan = renderer.tip_layout(parts, "monitoring", 1.5, "en")
        whole = bytes(renderer.draw_tip(plan, popup.halo("monitoring", 0, 0)).pixels())
        renderer.draw_tip_light(plan, popup.halo("monitoring", 1500, 1500))
        breathed = bytes(renderer.canvas.pixels())
        first, last = renderer.halo_rows
        row = plan["size"][0] * 4
        self.assertEqual(whole[:first * row], breathed[:first * row])
        self.assertEqual(whole[last * row:], breathed[last * row:])
        self.assertNotEqual(whole, breathed, "the light breathes")

    def test_plan_and_draw_take_at_most_30_ms_at_150_percent(self):
        """The speed proof (design 12, W4): the card is kept between hovers, so a hover and each second of the
        countdown cost one plan and one draw on a renderer whose fonts are made."""
        renderer = self.tipcard.TipRenderer()
        self.addCleanup(renderer.close)
        parts = words.tooltip_parts(FIXTURES["metered"], EN, NOW, "advanced")
        renderer.draw_tip(renderer.tip_layout(parts, "monitoring", 1.5, "en"), None)
        took = []
        for _ in range(15):
            started = time.perf_counter()
            renderer.draw_tip(renderer.tip_layout(parts, "monitoring", 1.5, "en"), popup.halo("monitoring", 0, 0))
            took.append((time.perf_counter() - started) * 1000.0)
        self.assertLessEqual(statistics.median(took), 30.0, took)

    def test_the_popups_renderer_draws_a_meter_in_its_ground_and_a_new_fraction_is_a_new_ground(self):
        """The one item kind the card adds to the popup's renderer: a surface that caches its ground (Renderer.draw)
        draws the bar again when only how far it is filled changed."""
        renderer = popup.Renderer()
        self.addCleanup(renderer.close)
        renderer.use("en", 1.0)

        def drawn(fraction):
            plan = {"size": (200, 40), "scale": 1.0, "items": [
                {"kind": "card", "rect": (0, 0, 200, 40), "radius": 16, "corner": "card"},
                {"kind": "meter", "rect": (20, 17, 180, 23), "fraction": fraction}], "targets": []}
            return bytes(renderer.draw({}, plan).pixels())
        quarter, most = drawn(0.25), drawn(0.9)
        self.assertNotEqual(quarter, most)
        accent = brand.rgb(brand.palette("light", "soft")["accent"])
        at = (20 * 200 + 140) * 4
        self.assertEqual(tuple(most[at:at + 3][::-1]), accent)
        self.assertNotEqual(tuple(quarter[at:at + 3][::-1]), accent)

    def test_little_left_is_the_warning_and_an_empty_bar_still_says_so(self):
        """v0.6.24 final: a window with little left fills in the warning colour, not the accent, and its well takes a
        warning edge - so a bar with nothing left in it does not read as nothing to worry about."""
        renderer = popup.Renderer()
        self.addCleanup(renderer.close)
        renderer.use("en", 1.0)

        def drawn(fraction, low):
            plan = {"size": (200, 40), "scale": 1.0, "items": [
                {"kind": "card", "rect": (0, 0, 200, 40), "radius": 16, "corner": "card"},
                {"kind": "meter", "rect": (20, 17, 180, 23), "fraction": fraction, "low": low}], "targets": []}
            return bytes(renderer.draw({}, plan).pixels())
        warning = brand.rgb(brand.palette("light", "soft")["warning"])
        at = (20 * 200 + 22) * 4                                  # inside the bar, near its start
        self.assertEqual(tuple(drawn(0.08, True)[at:at + 3][::-1]), warning)
        self.assertNotEqual(tuple(drawn(0.08, False)[at:at + 3][::-1]), warning)
        empty, calm = drawn(0.0, True), drawn(0.0, False)
        self.assertNotEqual(empty, calm, "an empty bar with nothing left looks unlike an empty calm one")
        edge = (17 * 200 + 100) * 4                               # the well's top edge, mid-way
        self.assertLess(sum(abs(a - b) for a, b in zip(empty[edge:edge + 3][::-1], warning)),
                        sum(abs(a - b) for a, b in zip(calm[edge:edge + 3][::-1], warning)))

    def test_every_language_draws(self):
        for locale in interface.STRINGS:
            with self.subTest(locale):
                plan, pixels = self.draw(locale=locale)
                self.assertEqual(bool(plan.get("rtl")), l10n.right_to_left(locale))
                self.assertEqual(len(pixels), plan["size"][0] * plan["size"][1] * 4)


@unittest.skipUnless(os.name == "nt", "MSAA is Windows'")
class AccessibleTests(unittest.TestCase):
    """What a screen reader is handed when it asks the card (WM_GETOBJECT): a tooltip named with the tooltip's whole
    text. Asked through the object's own table, in this process, with no window."""

    class Card:
        hwnd = None
        visible = True
        text = "Codex Auto Resume · Advanced\n2 waiting · next check in 3:20\n5-hour 87%"

    @staticmethod
    def call(pointer, slot, *types):
        table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *types)(table[slot])

    def test_it_is_a_read_only_tooltip_named_with_the_whole_text_and_no_children(self):
        from codex_auto_resume.ui.popup import access
        from codex_auto_resume.ui.tray import tipcard
        made = tipcard.TipAccessible(self.Card())
        pointer = made.pointer
        variant = access.VARIANT()
        variant.vt, variant.value.lVal = access.VT_I4, 0
        out = ctypes.c_void_p()
        self.assertEqual(self.call(pointer, 10, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            pointer, ctypes.addressof(variant), ctypes.byref(out)), 0)
        self.assertEqual(ctypes.wstring_at(out.value), self.Card.text)
        ctypes.WinDLL("oleaut32").SysFreeString(out)
        for slot, expected in ((13, tipcard.ROLE_SYSTEM_TOOLTIP), (14, tipcard.STATE_SYSTEM_READONLY)):
            answer = access.VARIANT()
            self.assertEqual(self.call(pointer, slot, ctypes.c_void_p, ctypes.POINTER(access.VARIANT))(
                pointer, ctypes.addressof(variant), ctypes.byref(answer)), 0)
            self.assertEqual(answer.value.lVal, expected)
        count = ctypes.c_long(-1)
        self.assertEqual(self.call(pointer, 8, ctypes.POINTER(ctypes.c_long))(pointer, ctypes.byref(count)), 0)
        self.assertEqual(count.value, 0)


class _User32:
    """user32 as the card's window calls it, for a card with no window: every call kept, each answered yes."""

    def __init__(self):
        self.calls = []

    def __call__(self, name):
        return self

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def call(*arguments):
            self.calls.append((name, arguments))
            return 1
        return call


class CardStateTests(unittest.TestCase):
    """The card's own decisions - hiding, fading, its backstop - with Windows stood in for: nothing is made or shown."""

    def setUp(self):
        from unittest import mock
        from codex_auto_resume.ui.tray import tipcard
        self.tipcard, self.user32 = tipcard, _User32()
        for target, name, value in ((popup, "_dll", self.user32), (tipcard.access, "tell", lambda *unused: None)):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.card = tipcard.TipCard(content=lambda: None)
        self.card.hwnd, self.card.visible = 0x99, True
        self.card._moves = lambda: True

    def hidden(self):
        return [arguments for name, arguments in self.user32.calls if name == "ShowWindow" and arguments[1] == popup.SW_HIDE]

    def test_a_hide_at_once_ends_a_fade_out_on_its_way(self):
        """Review M1: a click, the popup or the menu while the card fades - it kept fading beside them."""
        self.card.hide(at_once=False)
        self.assertEqual(self.card._fade[0], "out")
        self.assertEqual(self.hidden(), [])
        self.card.hide(at_once=True)
        self.assertIsNone(self.card._fade)
        self.assertEqual(len(self.hidden()), 1)
        self.card.hide(at_once=True)
        self.assertEqual(len(self.hidden()), 1, "hidden already: nothing")


    def backstop(self, pointer, steps):
        """The card shown by the icon at ICON with its card above it; the backstop looks at `steps` seconds with the pointer
        at `pointer`. Returns whether it is still shown after each look."""
        from unittest import mock
        card = self.card
        card._moves = lambda: False
        card._plan, card._screen, card._origin = {"scale": 1.0, "size": (300, 80)}, {"box": (1700, 1040, 1724, 1064)}, (1562, 952)
        clock = [0.0]
        seen = []
        with mock.patch.object(self.tipcard, "tip_pointer", lambda: pointer), \
                mock.patch.object(self.tipcard, "time", type("Clock", (), {"monotonic": staticmethod(lambda: clock[0])})):
            for at in steps:
                clock[0] = at
                card._wndproc(card.hwnd, popup.WM_TIMER, self.tipcard.TIP_WATCH, 0)
                seen.append(card.visible)
        return seen

    def test_the_backstop_hides_it_a_second_after_the_pointer_went_elsewhere(self):
        """Review R3: with NIN_POPUPCLOSE missed (the flyout closed, Explorer gone, a sleep with no lock) it stayed up."""
        self.assertEqual(self.backstop((100, 100), (0.0, 0.25, 0.5, 0.75, 1.0)), [True, True, True, True, False])
        self.assertEqual(len(self.hidden()), 1)

    def test_the_backstop_keeps_it_while_the_pointer_is_on_the_icon_near_it_or_on_the_card(self):
        for pointer in ((1710, 1050), (1690, 1050), (1600, 980)):
            with self.subTest(pointer=pointer):
                self.card.visible = True
                self.assertEqual(self.backstop(pointer, (0.0, 1.0, 2.0, 5.0)), [True] * 4)

    def test_a_suspend_or_a_resume_hides_it(self):
        tipcard = self.tipcard
        for event in (tipcard.PBT_APMSUSPEND, tipcard.PBT_APMRESUMESUSPEND, tipcard.PBT_APMRESUMEAUTOMATIC):
            with self.subTest(event=event):
                self.card.visible, self.card._fade = True, None
                self.card._moves = lambda: False
                self.card._wndproc(self.card.hwnd, tipcard.WM_POWERBROADCAST, event, 0)
                self.assertFalse(self.card.visible)


if __name__ == "__main__":
    unittest.main()
