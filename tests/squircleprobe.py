"""The window's squircle, asked from Python: the window's sources compiled with one console probe beside them.

tests/test_squircle_parity.py and tests/test_squircle_shadows.py hold the C# half of the corner (gui/SoftShape.cs,
Soft.Rounded, Elevation's coverage and stamps) to brand/shape.py's. The probe shows no window: it builds paths and
bitmaps in memory, adopts a design and a theme in the window's Palette, and prints what it found as JSON. It is a
console program, started without a console window of its own. One compile per test process, kept here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

import guiscan

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
CREATE_NO_WINDOW = 0x08000000

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;

namespace CodexAutoResume
{
    internal static class ShapeProbe
    {
        static readonly CultureInfo C = CultureInfo.InvariantCulture;

        static string N(double value) { return value.ToString("R", C); }

        static string List(IEnumerable<double> values)
        {
            var parts = new List<string>();
            foreach (double value in values) parts.Add(N(value));
            return "[" + string.Join(",", parts.ToArray()) + "]";
        }

        static double D(string text) { return double.Parse(text, C); }

        static bool Same(GraphicsPath one, GraphicsPath two)
        {
            PointF[] a = one.PathPoints, b = two.PathPoints;
            byte[] x = one.PathTypes, y = two.PathTypes;
            if (a.Length != b.Length) return false;
            for (int i = 0; i < a.Length; i++)
                if (a[i] != b[i] || x[i] != y[i]) return false;
            return true;
        }

        static GraphicsPath Arcs(RectangleF bounds, float radius)
        {
            var path = new GraphicsPath();
            float diameter = Math.Min(radius * 2, Math.Min(bounds.Width, bounds.Height));
            path.AddArc(bounds.X, bounds.Y, diameter, diameter, 180, 90);
            path.AddArc(bounds.Right - diameter, bounds.Y, diameter, diameter, 270, 90);
            path.AddArc(bounds.Right - diameter, bounds.Bottom - diameter, diameter, diameter, 0, 90);
            path.AddArc(bounds.X, bounds.Bottom - diameter, diameter, diameter, 90, 90);
            path.CloseFigure();
            return path;
        }

        static int Main(string[] args)
        {
            var output = new List<string>();
            BindingFlags hidden = BindingFlags.NonPublic | BindingFlags.Static;
            foreach (string line in File.ReadAllLines(args[0]))
            {
                string[] w = line.Split(' ');
                if (w[0] == "outline")
                {
                    var segments = new List<string>();
                    foreach (double[] segment in Shape.Outline(D(w[1]), D(w[2]), D(w[3]), D(w[4]), D(w[5]), D(w[6]),
                                                                (Shape.Corners)int.Parse(w[7], C)))
                        segments.Add(List(segment));
                    output.Add("[" + string.Join(",", segments.ToArray()) + "]");
                }
                else if (w[0] == "rounded")
                {
                    // rounded <theme> <design> l t w h r: the smoothing, and which path Soft.Rounded drew.
                    Palette.AdoptDesign(w[2]);
                    Palette.Adopt(w[1]);
                    var bounds = new RectangleF((float)D(w[3]), (float)D(w[4]), (float)D(w[5]), (float)D(w[6]));
                    float radius = (float)D(w[7]);
                    using (GraphicsPath drawn = Soft.Rounded(bounds, radius))
                    using (GraphicsPath squircle = Shape.Squircle(bounds, radius, Brand.CornerSmoothing))
                    using (GraphicsPath arcs = Arcs(bounds, radius))
                        output.Add("{\"smoothing\":" + N(Shape.Smoothing) + ",\"squircle\":" + (Same(drawn, squircle) ? "true" : "false")
                                   + ",\"arcs\":" + (Same(drawn, arcs) ? "true" : "false") + ",\"points\":" + drawn.PointCount + "}");
                }
                else if (w[0] == "profile")
                {
                    Shape.Profile made = Shape.ProfileOf(D(w[1]), D(w[2]), D(w[3]));
                    output.Add("{\"p\":" + N(made.P) + ",\"rho\":" + List(made.Rho) + ",\"lean\":" + List(made.Lean) + "}");
                }
                else if (w[0] == "cover")
                {
                    // cover across down left top width height radius smoothing: Elevation's coverage grid.
                    int across = int.Parse(w[1], C), down = int.Parse(w[2], C);
                    var grid = new double[across * down];
                    typeof(Elevation).GetMethod("Cover", hidden).Invoke(null, new object[] {
                        grid, across, down, D(w[3]), D(w[4]), D(w[5]), D(w[6]), D(w[7]), D(w[8]) });
                    output.Add(List(grid));
                }
                else if (w[0] == "stamp")
                {
                    // stamp theme design recipe index scale margin width height radius: one shadow stamped round a
                    // body at (margin, margin), as the window stamps it; the bitmap's alpha, row by row.
                    Palette.AdoptDesign(w[2]);
                    Palette.Adopt(w[1]);
                    int margin = int.Parse(w[6], C), width = int.Parse(w[7], C), height = int.Parse(w[8], C);
                    var body = new Rectangle(margin, margin, width, height);
                    int across = width + 2 * margin, down = height + 2 * margin;
                    var alpha = new List<double>();
                    using (var bitmap = new Bitmap(across, down, PixelFormat.Format32bppPArgb))
                    {
                        using (Graphics g = Graphics.FromImage(bitmap))
                        {
                            g.Clear(Color.Transparent);
                            typeof(Elevation).GetMethod("StampOne", hidden).Invoke(null, new object[] {
                                g, w[3], int.Parse(w[4], C), D(w[5]), body, (float)D(w[9]), new Rectangle(0, 0, across, down) });
                        }
                        for (int y = 0; y < down; y++)
                            for (int x = 0; x < across; x++)
                                alpha.Add(bitmap.GetPixel(x, y).A);
                    }
                    output.Add(List(alpha));
                }
            }
            Console.Out.Write("[" + string.Join(",\n", output.ToArray()) + "]");
            return 0;
        }
    }
}
"""

_BUILT = {}


def available() -> bool:
    return CSC.is_file()


def _build() -> Path:
    if "exe" not in _BUILT:
        folder = tempfile.TemporaryDirectory()
        work = Path(folder.name)
        probe = work / "ShapeProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "ShapeProbe.exe"
        subprocess.run([str(CSC), "/nologo", "/target:exe", "/platform:x64", "/out:" + str(exe),
                        "/main:CodexAutoResume.ShapeProbe",
                        "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                        *[str(path) for path in guiscan.sources()], str(probe)],
                       check=True, capture_output=True, timeout=300, creationflags=CREATE_NO_WINDOW)
        _BUILT["folder"], _BUILT["exe"] = folder, exe
    return _BUILT["exe"]


def ask(lines) -> list:
    """Each line's answer from the window's own code, in order (see PROBE for the lines it reads)."""
    exe = _build()
    cases = exe.parent / "cases.txt"
    cases.write_text("\n".join(lines), encoding="utf-8")
    result = subprocess.run([str(exe), str(cases)], capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=600, creationflags=CREATE_NO_WINDOW)
    if result.returncode != 0:
        raise AssertionError("the probe failed: " + (result.stderr or result.stdout)[-2000:])
    return json.loads(result.stdout)
