"""Each setup motion is framed by, and held to, the still of its own language (v0.6.26, audit-apng M9).

The plans named `assets/screenshot-setup.png`, a still that never existed; the generator never read the key and framed
both pictures with the first still it found, the Korean one, so the English window was never held to any still before
its picture was made. Now a plan's `window.still` is its own language's still among FIDELITY, the generator frames it
with that one, and `--still` draws every language's. Pure Python: nothing is drawn."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "build"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import make_install_motion as motion  # noqa: E402


class OwnStillTests(unittest.TestCase):
    def test_each_plan_is_framed_by_the_still_of_its_own_language(self):
        for name in motion.PLAN_NAMES + ("update-preview-ko",):
            with self.subTest(name):
                plan = motion.load(name)
                locale, path = motion.plan_still(plan, Path("X"))
                self.assertEqual(locale, plan["locale"])
                self.assertEqual(path, Path("X") / dict(motion.FIDELITY)[plan["locale"]])
        self.assertEqual(motion.plan_still(motion.load("install-en"))[1].name, "screenshot-setup.png")
        self.assertEqual(motion.plan_still(motion.load("install-ko"))[1].name, "screenshot-setup-ko.png")

    def test_a_plan_naming_another_languages_still_is_refused(self):
        plan = motion.load("install-en")
        plan["window"] = {"still": dict(motion.FIDELITY)["ko"]}
        with self.assertRaises(motion.PlanError):
            motion.plan_still(plan)
        plan["locale"] = "xx"
        with self.assertRaises(motion.PlanError):
            motion.plan_still(plan)

    def test_drawing_the_stills_draws_every_languages(self):
        self.assertEqual(sorted(locale for locale, _path in motion.stills_to_draw()),
                         sorted({motion.load(name)["locale"] for name in motion.PLAN_NAMES}))


if __name__ == "__main__":
    unittest.main()
