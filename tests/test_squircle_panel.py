"""v0.6.24 (owner, O11): the Codex panel's corners as a superellipse where its engine has `corner-shape`.

A progressive enhancement: under `@supports (corner-shape: ...)` Soft's roles take the superellipse and the radius
that come nearest the window's squircle (brand/shape.py's CSS_CORNER), and everywhere else the panel is exactly what
it was. Held here: the fit itself, the properties brand writes, the designs that keep circular corners, and that
every rule rounded by a role takes the corner shape while no pill does.
"""
from __future__ import annotations

import math
import re
import unittest

from codex_auto_resume import brand
from codex_auto_resume.brand import css, shape
from codex_auto_resume.mcp import panel


def _superellipse(reach, k, steps=240) -> list:
    n = 2.0 ** k
    return [(reach * (1 - math.cos(t) ** (2 / n)), reach * (1 - math.sin(t) ** (2 / n)))
            for t in (i / steps * math.pi / 2 for i in range(steps + 1))]


def _apart(one, two) -> float:
    def near(point, points):
        return min(math.hypot(point[0] - q[0], point[1] - q[1]) for q in points)
    return max(max(near(point, two) for point in one), max(near(point, one) for point in two))


def _rules(sheet):
    sheet = re.sub(r"/\*.*?\*/", "", sheet, flags=re.S)
    return [(" ".join(selector.split()), body) for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", sheet)]


class FitTests(unittest.TestCase):
    def figma(self):
        half = shape._half_points(shape.corner(1.0, shape.design_smoothing("soft"), 1e9), 120)
        return half + [(v, u) for u, v in half]

    def test_the_superellipse_is_within_three_hundredths_of_a_radius_of_the_squircle(self):
        fitted = _superellipse(shape.CSS_CORNER["reach"], shape.CSS_CORNER["superellipse"])
        self.assertLess(_apart(self.figma(), fitted), 0.032)

    def test_the_circle_and_css_squircle_are_further_off(self):
        """What the fit is for: neither CSS's own `squircle` nor a round corner at the radius is the shape."""
        self.assertGreater(_apart(self.figma(), _superellipse(1.0, 1.0)), 0.1)
        self.assertGreater(_apart(self.figma(), _superellipse(1.0, 2.0)), 0.1)


class PropertyTests(unittest.TestCase):
    def test_brand_writes_the_corner_and_each_roles_radius(self):
        scale = brand.css_scale()
        self.assertIn("--corner-shape: superellipse(%s);" % css._number(shape.CSS_CORNER["superellipse"]), scale)
        for role in css.CORNER_ROLES:
            with self.subTest(role=role):
                self.assertIn("--squircle-%s: %spx;" % (role, css._number(brand.RADII[role] * shape.CSS_CORNER["reach"])),
                              scale)

    def test_classic_and_plain_say_round_in_every_one_of_their_blocks(self):
        blocks = brand.css_design_blocks()
        for design in ("classic", "plain"):
            found = re.findall(r':root\[data-design="%s"\][^{]*\{([^{}]*)\}' % design, blocks)
            with self.subTest(design=design):
                self.assertEqual(len(found), 4)
                self.assertTrue(all("--corner-shape: round;" in body for body in found))


class StylesheetTests(unittest.TestCase):
    def setUp(self):
        self.sheet = panel._STYLE
        block = re.search(r"@supports \(corner-shape: superellipse\(2\)\) \{(.*?)\n\}", self.sheet, re.S)
        self.assertIsNotNone(block, "the panel's stylesheet has the progressive block")
        self.block, self.whole = block.group(1), block.group(0)

    def test_only_inside_the_supports_block(self):
        outside = re.sub(r"/\*.*?\*/", "", self.sheet.replace(self.whole, ""), flags=re.S)
        self.assertIsNone(re.search(r"(?<![-\w])corner-shape\s*:", outside),
                          "an engine without corner-shape draws the panel as it was")

    def test_every_rule_rounded_by_a_role_takes_the_shape_and_no_pill_does(self):
        shaped = None
        for selector, body in _rules(self.block):
            if "corner-shape: var(--corner-shape)" in body:
                shaped = {part.strip() for part in selector.split(",")}
        self.assertIsNotNone(shaped)
        outside = self.sheet.replace(self.block, "")
        rounded, pills = set(), set()
        for selector, body in _rules(outside):
            selector = selector.split("@")[-1].split(" ", 1)[-1] if selector.startswith("@") else selector
            names = {part.strip() for part in selector.split(",")}
            if re.search(r"var\(--radius-(card|control|small|check)\)", body):
                rounded |= names
            elif re.search(r"border-radius:\s*(999px|50%)", body):
                pills |= names
        self.assertEqual(rounded - shaped, set(), "a rule rounded by a role without the shape would grow round")
        self.assertEqual(shaped & (pills - rounded), set(), "a pill stays a pill")

    def test_the_roles_radii_point_at_the_squircles(self):
        for role in css.CORNER_ROLES:
            self.assertIn("--radius-%s: var(--squircle-%s);" % (role, role), self.block)


if __name__ == "__main__":
    unittest.main()
