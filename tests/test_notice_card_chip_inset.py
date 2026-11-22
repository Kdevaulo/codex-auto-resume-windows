"""The notification card's reason chip ends inside the notice tile's edge (v0.6.26, audit D3).

plans/v0626-audit/audit-design-motion.md D3 (the owner, 2026-11-22, "제안대로 모두 고침"): the chip's last pixel stood
exactly on the hairline of the notice tile under it - a rounded pill whose end lies on a straight edge looks as if it sticks
out past it, the version pill's case. Now it ends brand.LAYOUT["pill_inset"] inside the card's content edge, which the
tile spans to, and the product's name keeps its gap before it. The plan is laid out with a measure of its own (no font).
"""
from __future__ import annotations

import unittest

from codex_auto_resume import brand, l10n, notice_card

from test_notice_card import EVENTS, build, fake_measure, in_locale


class ChipInsetTests(unittest.TestCase):
    def test_the_chip_ends_pill_inset_inside_the_tile_s_edge(self):
        for locale in ("en", "de", "ar"):
            with in_locale(locale):
                notices = [build(event, detail) for event, detail, _identity in EVENTS]
            for notice in notices:
                vm = notice_card.view(notice)
                if not vm["chip"]:
                    continue
                for scale in (1.0, 1.5, 2.0):
                    with self.subTest(locale=locale, kind=notice.kind, scale=scale):
                        plan = notice_card.layout(vm, scale, fake_measure(scale))
                        px = lambda value: int(round(value * scale))
                        left, right = px(brand.SPACING["l"]), plan["size"][0] - px(brand.SPACING["l"])
                        chip = next(item["rect"] for item in plan["items"] if item["kind"] == "chip")
                        panel = next(item["rect"] for item in plan["items"] if item["kind"] == "panel")
                        product = next(item["rect"] for item in plan["items"]
                                       if item["kind"] == "text" and item["text"] == vm["product"])
                        inset = px(brand.LAYOUT["pill_inset"])
                        if l10n.right_to_left(vm["locale"]):
                            # Mirrored: at the card's left, inside the tile's left edge.
                            self.assertEqual(panel[0], left, "the tile spans to the content edge")
                            self.assertEqual(chip[0], left + inset, "pill_inset inside it")
                            self.assertGreaterEqual(product[0], chip[2] + px(brand.SPACING["s"]), "the name keeps its gap")
                        else:
                            self.assertEqual(panel[2], right, "the tile spans to the content edge")
                            self.assertEqual(chip[2], right - inset, "pill_inset inside it")
                            self.assertLessEqual(product[2], chip[0] - px(brand.SPACING["s"]), "the name keeps its gap")


if __name__ == "__main__":
    unittest.main()
