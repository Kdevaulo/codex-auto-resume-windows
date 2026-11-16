r"""v0.6.24 (stage 1, surface E): the Dashboard window's own outer corner, asked with no window (gui/SoftWindowShape.cs).

The corner is two pieces - a hard-edged window region and a layered companion that paints the anti-aliased edge, the
hairline and the shadow round it - and the screen shows them composited. Here both are made by the window's own code in
a console probe (no window, nothing on the screen) and composited over white, black, grey and a checkerboard, at 100 to
300 % for Soft and at 100/150/200 % for Classic and Plain, then held to the ideal worked out here from brand/shape.py -
the corner sampled 16 x 16 per pixel, the same hairline, the same shadow (plans/v0624-stage1-design.md 5.3):

* every channel within 2 levels of the ideal;
* no double cover - no pixel inside the region the companion also paints;
* no gap - no pixel the corner covers by more than 1/255 that neither paints;
* the region GDI makes from the rectangles is exactly the window's own pixels;
* the fast composition (corner blocks, straight edges repeated) is the per-pixel one, pixel for pixel.

And the switch (5.4): Brand.WindowSquircle is brand.WINDOW_SQUIRCLE, on from v0.6.24-beta (the owner, 2026-11-16), and
every hook into the window's caption is behind the corner it makes; the decision table of 5.2 item 6; and the cost of making
the companion's picture at 1500 x 1000 device px at 150 %, printed (the budget is 4 ms on the owner's PC).

The live half - the companion following the window in the very message that moves it - is
tests/test_gui_window_corner_sync.py (a window off every screen, under the GUI lock).
"""
from __future__ import annotations

import base64
import itertools
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

import guiscan
from codex_auto_resume import brand
from codex_auto_resume.brand import shape

ROOT = Path(__file__).resolve().parent.parent
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
CREATE_NO_WINDOW = 0x08000000

SOFT_SCALES = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
OTHER_SCALES = (1.0, 1.5, 2.0)
# The window drawn here, in px at 100 %: big enough for four corners that do not meet at 300 %.
LOGICAL = (96, 84)
GROUND, LINE = (0xF2, 0xF4, 0xF7), (0xC9, 0xCF, 0xD8)
BACKGROUNDS = ("white", "black", "grey", "checker")

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace CodexAutoResume
{
    internal static class CornerProbe
    {
        static readonly CultureInfo C = CultureInfo.InvariantCulture;
        static double D(string text) { return double.Parse(text, C); }
        static int I(string text) { return int.Parse(text, C); }

        [DllImport("gdi32.dll")] static extern int GetRegionData(IntPtr region, int size, byte[] data);
        [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr item);

        static string Pixels(int[] values)
        {
            var bytes = new byte[values.Length * 4];
            Buffer.BlockCopy(values, 0, bytes, 0, bytes.Length);
            return "\"" + Convert.ToBase64String(bytes) + "\"";
        }

        static string Rects(List<Rectangle> rects)
        {
            var parts = new List<string>();
            foreach (Rectangle r in rects) parts.Add("[" + r.Left + "," + r.Top + "," + r.Right + "," + r.Bottom + "]");
            return "[" + string.Join(",", parts.ToArray()) + "]";
        }

        static List<Rectangle> FromGdi(IntPtr region)
        {
            var rects = new List<Rectangle>();
            int size = GetRegionData(region, 0, null);
            var data = new byte[size];
            GetRegionData(region, size, data);
            int count = BitConverter.ToInt32(data, 8);
            for (int i = 0; i < count; i++)
            {
                int at = 32 + 16 * i;
                rects.Add(Rectangle.FromLTRB(BitConverter.ToInt32(data, at), BitConverter.ToInt32(data, at + 4),
                                             BitConverter.ToInt32(data, at + 8), BitConverter.ToInt32(data, at + 12)));
            }
            return rects;
        }

        static int Main(string[] args)
        {
            var output = new List<string>();
            foreach (string entry in File.ReadAllLines(args[0]))
            {
                string[] w = entry.Split(' ');
                if (w[0] == "compose")
                {
                    // compose width height radius smoothing scale ground line: the companion (fast and pixel by pixel),
                    // the region's rectangles and what GDI makes of them.
                    int width = I(w[1]), height = I(w[2]);
                    Color ground = ColorTranslator.FromHtml(w[6]), line = ColorTranslator.FromHtml(w[7]);
                    var edge = new WindowShape.Edge(width, height, D(w[3]), D(w[4]), D(w[5]));
                    Size size = WindowShape.CompanionSize(edge);
                    var fast = new WindowShape.ArraySink(size.Width, size.Height);
                    WindowShape.Compose(edge, ground, line, Color.Black, fast);
                    bool same = true;
                    for (int y = 0; y < size.Height && same; y++)
                        for (int x = 0; x < size.Width; x++)
                            if (fast.Pixels[y * size.Width + x] != edge.Pixel(x - edge.Margin, y - edge.Margin, ground, line, Color.Black))
                            {
                                same = false;
                                break;
                            }
                    IntPtr region = WindowShape.Region(edge);
                    List<Rectangle> gdi = FromGdi(region);
                    DeleteObject(region);
                    output.Add("{\"margin\":" + edge.Margin + ",\"reach\":" + edge.Reach + ",\"drop\":" + edge.Drop +
                               ",\"hair\":" + edge.Hair + ",\"tile\":" + edge.Tile + ",\"fits\":" + (edge.Fits ? "true" : "false") +
                               ",\"width\":" + size.Width + ",\"height\":" + size.Height + ",\"same\":" + (same ? "true" : "false") +
                               ",\"rects\":" + Rects(WindowShape.RegionRects(edge)) + ",\"gdi\":" + Rects(gdi) +
                               ",\"pixels\":" + Pixels(fast.Pixels) + "}");
                }
                else if (w[0] == "still")
                {
                    // still width height radius smoothing scale ground line: a picture all `ground` cut as a still is.
                    int width = I(w[1]), height = I(w[2]);
                    Color ground = ColorTranslator.FromHtml(w[6]), line = ColorTranslator.FromHtml(w[7]);
                    var edge = new WindowShape.Edge(width, height, D(w[3]), D(w[4]), D(w[5]));
                    var pixels = new int[width * height];
                    for (int i = 0; i < pixels.Length; i++) pixels[i] = ground.ToArgb();
                    WindowShape.CutStill(pixels, edge, line);
                    output.Add("{\"hair\":" + edge.Hair + ",\"pixels\":" + Pixels(pixels) + "}");
                }
                else if (w[0] == "decide")
                {
                    var rows = new List<string>();
                    for (int bits = 0; bits < 128; bits++)
                    {
                        WindowShape.Corner corner = WindowShape.Decide((bits & 1) != 0, (bits & 2) != 0, (bits & 4) != 0,
                            (bits & 8) != 0, (bits & 16) != 0, (bits & 32) != 0, (bits & 64) != 0);
                        rows.Add("\"" + corner + "\"");
                    }
                    output.Add("[" + string.Join(",", rows.ToArray()) + "]");
                }
                else if (w[0] == "switch")
                {
                    output.Add("{\"brand\":" + (Brand.WindowSquircle ? "true" : "false") + ",\"switch\":" +
                               (WindowShape.Switch ? "true" : "false") + ",\"wanted\":" + (WindowShape.Wanted() ? "true" : "false") + "}");
                }
                else if (w[0] == "bench")
                {
                    // bench width height scale runs: the companion's picture into clear memory, as into a new DIB section -
                    // the first time (corner pieces made) and then each time again.
                    int width = I(w[1]), height = I(w[2]), runs = I(w[4]);
                    double scale = D(w[3]);
                    Color ground = ColorTranslator.FromHtml("#F2F4F7"), line = ColorTranslator.FromHtml("#C9CFD8");
                    var times = new List<double>();
                    double region = 0;
                    for (int run = 0; run <= runs; run++)
                    {
                        var clock = Stopwatch.StartNew();
                        var edge = new WindowShape.Edge(width, height, 16, 0.6, scale);
                        Size size = WindowShape.CompanionSize(edge);
                        int stride = 4 * size.Width;
                        IntPtr bits = Marshal.AllocHGlobal(new IntPtr((long)stride * size.Height));
                        try
                        {
                            var zero = new byte[stride];
                            for (int y = 0; y < size.Height; y++) Marshal.Copy(zero, 0, new IntPtr(bits.ToInt64() + (long)y * stride), stride);
                            clock.Restart();
                            WindowShape.Compose(edge, ground, line, Color.Black, new WindowShape.MemorySink(bits, stride));
                            times.Add(clock.Elapsed.TotalMilliseconds);
                        }
                        finally { Marshal.FreeHGlobal(bits); }
                        var shapeClock = Stopwatch.StartNew();
                        IntPtr made = WindowShape.Region(edge);
                        region = shapeClock.Elapsed.TotalMilliseconds;
                        DeleteObject(made);
                    }
                    double first = times[0];
                    times.RemoveAt(0);
                    times.Sort();
                    output.Add("{\"first\":" + first.ToString("R", C) + ",\"median\":" + times[times.Count / 2].ToString("R", C) +
                               ",\"region\":" + region.ToString("R", C) + "}");
                }
            }
            Console.Out.Write("[" + string.Join(",\n", output.ToArray()) + "]");
            return 0;
        }
    }
}
"""

_BUILT = {}


def _build() -> Path:
    if "exe" not in _BUILT:
        folder = tempfile.TemporaryDirectory(prefix="car-corner-")
        work = Path(folder.name)
        probe = work / "CornerProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "CornerProbe.exe"
        done = subprocess.run([str(CSC), "/nologo", "/target:exe", "/platform:x64", "/optimize+", "/out:" + str(exe),
                               "/main:CodexAutoResume.CornerProbe",
                               "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                               *[str(path) for path in guiscan.sources()], str(probe)],
                              capture_output=True, timeout=300, creationflags=CREATE_NO_WINDOW)
        if done.returncode:
            raise AssertionError("the probe did not compile: " + done.stdout.decode("utf-8", "replace")[-3000:])
        _BUILT["folder"], _BUILT["exe"] = folder, exe
    return _BUILT["exe"]


def ask(lines) -> list:
    exe = _build()
    cases = exe.parent / "cases.txt"
    cases.write_text("\n".join(lines), encoding="utf-8")
    result = subprocess.run([str(exe), str(cases)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=900, creationflags=CREATE_NO_WINDOW)
    if result.returncode != 0:
        raise AssertionError("the probe failed: " + (result.stderr or result.stdout)[-2000:])
    return json.loads(result.stdout)


def _hex(rgb) -> str:
    return "#%02X%02X%02X" % rgb


def _background(name, x, y):
    if name == "white":
        return (255, 255, 255)
    if name == "black":
        return (0, 0, 0)
    if name == "grey":
        return (128, 128, 128)
    return (255, 255, 255) if ((x // 8) + (y // 8)) % 2 == 0 else (0, 0, 0)


class _Ideal:
    """The corner as it should look, worked out from brand/shape.py alone: each pixel's coverage by the window's outline
    and by the one a hairline inside it, 16 x 16 samples where the outline passes, and the shadow's light."""

    def __init__(self, width, height, radius, smoothing, hair, reach, drop):
        self.width, self.height, self.radius, self.smoothing = width, height, radius, smoothing
        self.hair, self.reach, self.drop = hair, reach, drop
        self.outer_rect = (0.0, 0.0, float(width), float(height))
        self.inner_rect = (float(hair), float(hair), float(width - hair), float(height - hair))
        self.corner = shape.corner(radius, smoothing, min(width, height) / 2.0).p + hair + 2
        self.cache = {}

    def _cover(self, x, y, rect, radius):
        left, top, right, bottom = rect
        half_w, half_h = (right - left) / 2.0, (bottom - top) / 2.0
        d = shape.distance(x + 0.5 - (left + right) / 2.0, y + 0.5 - (top + bottom) / 2.0, half_w, half_h, radius, self.smoothing)
        if d <= -1.5:
            return 1.0
        if d >= 1.5:
            return 0.0
        inside = sum(1 for j in range(16) for i in range(16)
                     if shape.inside(x + (i + 0.5) / 16.0, y + (j + 0.5) / 16.0, rect, radius, self.smoothing))
        return inside / 256.0

    def covers(self, x, y):
        """(outer, inner) coverage of the window's pixel (x, y); (0, 0) outside the window."""
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return 0.0, 0.0
        xx, yy = min(x, self.width - 1 - x), min(y, self.height - 1 - y)
        if xx >= self.corner or yy >= self.corner:
            return 1.0, 1.0 if (xx >= self.hair and yy >= self.hair) else 0.0
        key = (xx, yy)
        if key not in self.cache:
            self.cache[key] = (self._cover(xx, yy, self.outer_rect, self.radius),
                               self._cover(xx, yy, self.inner_rect, max(0.0, self.radius - self.hair)))
        return self.cache[key]

    def shadow(self, x, y):
        d = shape.distance(x + 0.5 - self.width / 2.0, y + 0.5 - self.drop - self.height / 2.0, self.width / 2.0,
                           self.height / 2.0, self.radius, self.smoothing)
        layers = max(0.0, min(self.reach, self.reach - d))
        return 1.0 - (1.0 - 0.17 / self.reach) ** layers


def _region_mask(rects, width, height):
    own = bytearray(width * height)
    for left, top, right, bottom in rects:
        for y in range(max(0, top), min(height, bottom)):
            for x in range(max(0, left), min(width, right)):
                own[y * width + x] += 1
    return own


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class CompositeTests(unittest.TestCase):
    """The region and the companion together, over four backgrounds, against the ideal."""

    @classmethod
    def setUpClass(cls):
        cls.cases = []
        for design in ("soft", "classic", "plain"):
            for scale in (SOFT_SCALES if design == "soft" else OTHER_SCALES):
                cls.cases.append((design, scale))
        lines = []
        for design, scale in cls.cases:
            width, height = (int(round(side * scale)) for side in LOGICAL)
            radius = brand.design_radii(design)["card"]
            lines.append("compose %d %d %r %r %r %s %s" % (width, height, float(radius), shape.design_smoothing(design),
                                                           scale, _hex(GROUND), _hex(LINE)))
        cls.answers = ask(lines)

    def each(self):
        for (design, scale), answer in zip(self.cases, self.answers):
            width, height = (int(round(side * scale)) for side in LOGICAL)
            yield design, scale, width, height, answer

    def test_the_fast_picture_is_the_pixel_by_pixel_one(self):
        for design, scale, width, height, answer in self.each():
            with self.subTest(design=design, scale=scale):
                self.assertTrue(answer["fits"])
                self.assertTrue(answer["same"])

    def test_the_numbers_are_the_window_shadow_s_and_the_card_s_hairline(self):
        for design, scale, width, height, answer in self.each():
            with self.subTest(design=design, scale=scale):
                self.assertEqual(answer["reach"], int(round(14 * scale)))
                self.assertEqual(answer["drop"], int(round(6 * scale)))
                self.assertEqual(answer["margin"], answer["reach"] + answer["drop"])
                self.assertEqual(answer["hair"], max(1, int(scale + 1e-6)))
                self.assertEqual((answer["width"], answer["height"]),
                                 (width + 2 * answer["margin"], height + 2 * answer["margin"]))

    def test_gdi_makes_the_region_of_exactly_the_window_s_own_pixels(self):
        for design, scale, width, height, answer in self.each():
            with self.subTest(design=design, scale=scale):
                ours = _region_mask(answer["rects"], width, height)
                gdis = _region_mask(answer["gdi"], width, height)
                self.assertEqual(ours, gdis)
                self.assertLessEqual(max(ours), 1, "the rectangles overlap")

    def test_composited_over_every_ground_it_is_the_ideal_corner(self):
        for design, scale, width, height, answer in self.each():
            with self.subTest(design=design, scale=scale):
                self._composite(design, scale, width, height, answer)

    def _composite(self, design, scale, width, height, answer):
        margin, across, down = answer["margin"], answer["width"], answer["height"]
        pixels = struct.unpack("<%dI" % (across * down), base64.b64decode(answer["pixels"]))
        own = _region_mask(answer["rects"], width, height)
        radius = brand.design_radii(design)["card"] * scale
        ideal = _Ideal(width, height, radius, shape.design_smoothing(design), answer["hair"], answer["reach"], answer["drop"])
        worst, double, gaps = 0.0, [], []
        for cy in range(down):
            for cx in range(across):
                x, y = cx - margin, cy - margin
                value = pixels[cy * across + cx]
                alpha = value >> 24
                mine = 0 <= x < width and 0 <= y < height and own[y * width + x]
                if mine and value:
                    double.append((x, y))
                outer, inner = ideal.covers(x, y)
                if outer > 1 / 255.0 and not mine and alpha == 0:
                    gaps.append((x, y))
                shadow = 0.0 if outer >= 1.0 else ideal.shadow(x, y)
                painted = (value >> 16 & 255, value >> 8 & 255, value & 255)
                for name in BACKGROUNDS:
                    under = _background(name, cx, cy)
                    for c in range(3):
                        want = GROUND[c] * inner + LINE[c] * (outer - inner) + (1.0 - outer) * under[c] * (1.0 - shadow)
                        got = GROUND[c] if mine else painted[c] + under[c] * (255 - alpha) / 255.0
                        worst = max(worst, abs(round(got) - want))
        self.assertEqual(double[:5], [], "the companion paints inside the region")
        self.assertEqual(gaps[:5], [], "a pixel the corner covers that neither paints")
        self.assertLessEqual(worst, 2.0, "a channel further than 2 levels from the ideal")


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class StillTests(unittest.TestCase):
    """5.6: a still's corner is cut by the same decision - the window's own corner at the still's scale while the switch
    is on, Windows' 8 px circle as today while it is off."""

    def test_the_still_job_names_the_corner_only_while_the_switch_is_on(self):
        import sys
        from unittest import mock
        sys.path.insert(0, str(ROOT / "build"))
        try:
            import make_screenshots as shots
        finally:
            sys.path.remove(str(ROOT / "build"))
        self.assertEqual(shots.still_job(shots.PINNED_DPI), {"radius": 12, "dpi": shots.PINNED_DPI, "corner": "squircle"})
        with mock.patch.object(brand, "WINDOW_SQUIRCLE", False):
            self.assertEqual(shots.still_job(shots.PINNED_DPI), {"radius": 12, "dpi": shots.PINNED_DPI})

    def test_the_render_and_the_capture_cut_by_the_same_decision(self):
        frames = guiscan.member_body("SettingsForm", "RenderFrames")
        self.assertIn('StillSquircle() ? SquircleStill(picture, StillNumber(renderStill, "dpi"))', frames)
        self.assertIn("Bitmap cut = CornerStill(square, dpi);", guiscan.member_body("SettingsForm", "SquircleStill"))
        # FramedStill is the setup window's too (build/motion/InstallerRender.cs keeps it word for word): unchanged.
        self.assertNotIn("Squircle", guiscan.member_body("SettingsForm", "FramedStill"))
        self.assertIn('renderStill.TryGetValue("corner", out value) && value as string == "squircle"',
                      guiscan.member_body("SettingsForm", "StillSquircle"))
        still = guiscan.member_body("SettingsForm", "CornerStill")
        self.assertIn("new WindowShape.Edge(width, height, Palette.RadiusCard, Shape.Smoothing,", still)
        self.assertIn("WindowShape.CutStill(pixels, edge, Palette.Line);", still)
        script = (ROOT / "build" / "capture_window.ps1").read_text(encoding="utf-8")
        for step in ("GetWindowRgn($handle, $own) -gt 1", "[System.Drawing.Region]::FromHrgn($own)",
                     "$shaped.Translate(-$cropLeft, 0)", "$paint.FillRegion($brush, $shaped)", "$radius = 0"):
            self.assertIn(step, script)
        # The region's cut comes before Windows' circle, which it turns off.
        self.assertLess(script.index("GetWindowRgn($handle"), script.index("$path.AddArc(0, 0, $d, $d, 180, 90)"))

    def test_a_still_s_corner_is_the_ideal_edge_without_the_shadow(self):
        for design, scale in (("soft", 1.5), ("soft", 2.0), ("classic", 1.5)):
            width, height = (int(round(side * scale)) for side in LOGICAL)
            radius = brand.design_radii(design)["card"]
            smoothing = shape.design_smoothing(design)
            answer = ask(["still %d %d %r %r %r %s %s" % (width, height, float(radius), smoothing, scale, _hex(GROUND),
                                                          _hex(LINE))])[0]
            pixels = struct.unpack("<%dI" % (width * height), base64.b64decode(answer["pixels"]))
            ideal = _Ideal(width, height, radius * scale, smoothing, answer["hair"], 1, 0)
            worst = 0.0
            for y in range(height):
                for x in range(width):
                    value = pixels[y * width + x]
                    alpha = (value >> 24) / 255.0
                    outer, inner = ideal.covers(x, y)
                    for c, shift in enumerate((16, 8, 0)):
                        for under in (0, 255):
                            want = GROUND[c] * inner + LINE[c] * (outer - inner) + (1.0 - outer) * under
                            got = ((value >> shift) & 255) * alpha + under * (1.0 - alpha)
                            worst = max(worst, abs(got - want))
            with self.subTest(design=design, scale=scale):
                self.assertLessEqual(worst, 2.0)


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class SwitchTests(unittest.TestCase):
    """5.4: the switch, on from v0.6.24-beta (the owner, 2026-11-16), and the decision of 5.2 item 6."""

    def test_the_switch_is_brand_s_and_on(self):
        self.assertIs(brand.WINDOW_SQUIRCLE, True, "the owner turned the window's own corner on for v0.6.24-beta")
        self.assertIn("internal const bool WindowSquircle = true;", guiscan.read("gui/Brand.cs"))
        answer = ask(["switch"])[0]
        # `wanted` is the switch and this machine (Windows 11, composition, no remote session, no High Contrast): the
        # decision table below holds it; here only that the switch reaches the window's code.
        self.assertEqual((answer["brand"], answer["switch"]), (True, True))
        self.assertIsInstance(answer["wanted"], bool)

    def test_windows_round_corner_unless_every_condition_holds(self):
        rows = ask(["decide"])[0]
        for bits, got in enumerate(rows):
            on, windows11, composition, remote, contrast, zoomed, arranged = ((bits >> i) & 1 == 1 for i in range(7))
            if not windows11:
                want = "Square"
            elif on and composition and not (remote or contrast or zoomed or arranged):
                want = "Squircle"
            else:
                want = "Round"
            with self.subTest(on=on, windows11=windows11, composition=composition, remote=remote, contrast=contrast,
                              zoomed=zoomed, arranged=arranged):
                self.assertEqual(got, want)

    def test_every_hook_is_behind_the_corner_the_switch_makes(self):
        chrome = guiscan.read("gui/SoftChrome.cs")
        own = guiscan.member_body("ChromeHost", "OwnCorner")
        self.assertIn("!WindowShape.Wanted()) return;", own)
        self.assertIn("corner = WindowCorner.Attach(form);", own)
        self.assertEqual(chrome.count("WindowCorner.Attach("), 1)
        self.assertIn("if (corner != null && corner.Intercept(ref m)) return true;", guiscan.member_body("ChromeHost", "Intercept"))
        self.assertIn("get { return corner != null && corner.Shaped; }", guiscan.type_body("ChromeHost"))
        self.assertIn("layout.Edges = Frameless;", guiscan.member_body("ChromeHost", "Layout"))
        wanted = guiscan.member_body("WindowShape", "Wanted")
        self.assertIn("Switch && Windows11", wanted)
        self.assertIn("internal static readonly bool Switch = Brand.WindowSquircle;", guiscan.read("gui/SoftWindowShape.cs"))
        # Only the Dashboard asks, and only after its caption is installed.
        askers = [path.name for path in (ROOT / "gui").glob("*.cs") if ".OwnCorner()" in path.read_text(encoding="utf-8")]
        self.assertEqual(askers, ["SettingsApp.cs"])
        self.assertIn("chrome.OwnCorner();", guiscan.read("gui/SettingsApp.cs"))
        self.assertIn("if (chrome != null && chrome.Frameless) return Padding.Empty;",
                      guiscan.member_body("SettingsForm", "OwnFrame"))

    def test_it_is_compiled_with_the_controls(self):
        controls = guiscan.groups()["controls"]
        self.assertIn("gui/SoftWindowShape.cs", controls)


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class CostTests(unittest.TestCase):
    """5.3: making the companion's picture for a 1500 x 1000 px window at 150 % - each resize does it once."""

    def test_composing_at_1500_by_1000_at_150_percent(self):
        answer = ask(["bench 1500 1000 1.5 40"])[0]
        print("\n[window corner] compose 1500x1000 at 150 %%: first %.3f ms (corner pieces made), then median %.3f ms;"
              " region %.3f ms (budget: 4 ms on the owner's PC)" % (answer["first"], answer["median"], answer["region"]))
        # A tenfold regression guard only: the 4 ms budget is measured on the owner's PC, never judged on a busy runner.
        self.assertLess(answer["median"], 40.0)


if __name__ == "__main__":
    unittest.main()
