// Codex Auto Resume - the corner every rounded thing is drawn with: Figma's corner smoothing (v0.6.24).
//
// The window's half of src/codex_auto_resume/brand/shape.py, number for number: the outline a path is made of,
// and what the shadows ask of it. tests/test_squircle_parity.py holds the two languages to one outline.
//
// A circular corner meets its sides with a jump in curvature, from none to 1/R at once. Figma's construction runs a
// circular arc in the middle of the corner and joins it to each side with one cubic Bezier whose curvature is zero
// at the side, so the corner eases in, and starts (1 + smoothing) * R from its vertex instead of R. Where a side is
// too short for the whole ease the smoothing backs off until the corner fits, so a pill - a radius of half its side -
// is a plain semicircle. Soft smooths by Brand.CornerSmoothing; Classic and Plain keep circular corners
// (Brand.DesignSmoothing), and a corner the budget left circular is drawn as one arc, exactly as before.

using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;

namespace CodexAutoResume
{
    internal static class Shape
    {
        /// The corners a path rounds; the others are their vertex.
        [Flags]
        internal enum Corners { TopLeft = 1, TopRight = 2, BottomRight = 4, BottomLeft = 8, All = 15 }

        /// One corner as drawn: the radius and smoothing after the budget, its length P along each side, the
        /// Bezier's spacings A B C D and the arc's run along each axis (figma-squircle's names).
        internal struct Corner
        {
            internal double Radius, Smoothing, P, A, B, C, D, Chord;

            /// Whether it is drawn smoothed; a corner the budget took the smoothing from is the circle.
            internal bool Smoothed
            {
                get { return Smoothing > 1e-9; }
            }
        }

        /// The smoothing the window's corners are drawn with: the design's (Brand.DesignSmoothing), and Soft's in
        /// High Contrast, as the radii are (Palette.Adopt). Paint only.
        internal static double Smoothing
        {
            get { return Brand.DesignSmoothing(Design.Drawn(Palette.Theme, Palette.Design)); }
        }

        /// One corner of `radius` smoothed by `smoothing`, in a box whose shorter side is 2 * budget.
        internal static Corner Of(double radius, double smoothing, double budget)
        {
            var corner = new Corner();
            budget = Math.Max(0.0, budget);
            radius = Math.Max(0.0, Math.Min(radius, budget));
            if (radius <= 0.0) return corner;
            smoothing = Math.Max(0.0, Math.Min(smoothing, budget / radius - 1.0));
            double p = Math.Min((1.0 + smoothing) * radius, budget);
            double arc = 90.0 * (1.0 - smoothing);
            double chord = Math.Sin(Radians(arc / 2.0)) * radius * Math.Sqrt(2.0);
            double alpha = (90.0 - arc) / 2.0;
            double p3ToP4 = radius * Math.Tan(Radians(alpha / 2.0));
            double beta = 45.0 * smoothing;
            double c = p3ToP4 * Math.Cos(Radians(beta));
            double d = c * Math.Tan(Radians(beta));
            double b = (p - chord - c - d) / 3.0;
            corner.Radius = radius;
            corner.Smoothing = smoothing;
            corner.P = p;
            corner.A = 2.0 * b;
            corner.B = b;
            corner.C = c;
            corner.D = d;
            corner.Chord = chord;
            return corner;
        }

        private static double Radians(double degrees)
        {
            return degrees * Math.PI / 180.0;
        }

        // ------------------------------------------------------------------ the outline
        // The corners in drawing order - top left, top right, bottom right, bottom left - each the top-right corner
        // (vertex at the origin, the shape down and to the left) turned a quarter clockwise per step. No arrays of constants:
        // the in-box compiler would put them in a class named by a fresh GUID, and the build would not be reproducible.
        private static Corners InOrder(int step)
        {
            if (step == 0) return Corners.TopLeft;
            if (step == 1) return Corners.TopRight;
            if (step == 2) return Corners.BottomRight;
            return Corners.BottomLeft;
        }

        private static int Turns(Corners corner)
        {
            if (corner == Corners.TopRight) return 0;
            if (corner == Corners.BottomRight) return 1;
            if (corner == Corners.BottomLeft) return 2;
            return 3;
        }

        /// Writes the point (x, y) of the top-right corner's frame, turned onto corner `turns` at (vx, vy), at `at`.
        private static void Turn(int turns, double x, double y, double vx, double vy, double[] into, int at)
        {
            if (turns == 1) { double t = x; x = -y; y = t; }
            else if (turns == 2) { x = -x; y = -y; }
            else if (turns == 3) { double t = x; x = y; y = -t; }
            into[at] = vx + x;
            into[at + 1] = vy + y;
        }

        /// The outline of the box, as shape.outline gives it: per corner [0, x0, y0 .. x3, y3] for a Bezier and
        /// [1, cx, cy, r, start, sweep] for an arc in GDI+'s degrees, or [2, x, y] for a corner not rounded. Empty for
        /// a box too small to round (under a pixel across). Every paint asks for it, so it allocates only its arrays.
        internal static List<double[]> Outline(double left, double top, double right, double bottom, double radius,
                                               double smoothing, Corners corners)
        {
            var segments = new List<double[]>(12);
            Corner corner = Of(radius, smoothing, Math.Min(right - left, bottom - top) / 2.0);
            if (corner.Radius * 2.0 <= 1.0) return segments;
            double r = corner.Radius, p = corner.P, a = corner.A, b = corner.B, c = corner.C, d = corner.D;
            double beta = 45.0 * corner.Smoothing;
            for (int step = 0; step < 4; step++)
            {
                Corners name = InOrder(step);
                double vx = name == Corners.TopLeft || name == Corners.BottomLeft ? left : right;
                double vy = name == Corners.TopLeft || name == Corners.TopRight ? top : bottom;
                if ((corners & name) == 0)
                {
                    var point = new double[3];
                    point[0] = 2.0;
                    point[1] = vx;
                    point[2] = vy;
                    segments.Add(point);
                    continue;
                }
                int turns = Turns(name);
                double start = (270.0 + 90.0 * turns) % 360.0;
                var arc = new double[6];
                arc[0] = 1.0;
                Turn(turns, -r, r, vx, vy, arc, 1);
                arc[3] = r;
                if (!corner.Smoothed)
                {
                    arc[4] = start;
                    arc[5] = 90.0;
                    segments.Add(arc);
                    continue;
                }
                arc[4] = start + beta;
                arc[5] = 90.0 - 2.0 * beta;
                var first = new double[9];
                Turn(turns, -p, 0.0, vx, vy, first, 1);
                Turn(turns, -p + a, 0.0, vx, vy, first, 3);
                Turn(turns, -p + a + b, 0.0, vx, vy, first, 5);
                Turn(turns, -p + a + b + c, d, vx, vy, first, 7);
                var second = new double[9];
                Turn(turns, -d, p - a - b - c, vx, vy, second, 1);
                Turn(turns, 0.0, p - a - b, vx, vy, second, 3);
                Turn(turns, 0.0, p - a, vx, vy, second, 5);
                Turn(turns, 0.0, p, vx, vy, second, 7);
                segments.Add(first);
                segments.Add(arc);
                segments.Add(second);
            }
            return segments;
        }

        /// `bounds` with every corner rounded by `radius` and `smoothing`: what Soft.Rounded draws.
        internal static GraphicsPath Squircle(RectangleF bounds, float radius, double smoothing)
        {
            return Squircle(bounds, radius, smoothing, Corners.All);
        }

        /// `bounds` with `corners` rounded. A box under a pixel across is its rectangle; a corner the budget left
        /// circular is the arc v0.6.23 drew, and with every corner so, the very path it drew.
        internal static GraphicsPath Squircle(RectangleF bounds, float radius, double smoothing, Corners corners)
        {
            var path = new GraphicsPath();
            float diameter = Math.Min(radius * 2, Math.Min(bounds.Width, bounds.Height));
            if (diameter <= 1f)
            {
                path.AddRectangle(bounds);
                return path;
            }
            if (corners == Corners.All && !Of(radius, smoothing, Math.Min(bounds.Width, bounds.Height) / 2.0).Smoothed)
            {
                path.AddArc(bounds.X, bounds.Y, diameter, diameter, 180, 90);
                path.AddArc(bounds.Right - diameter, bounds.Y, diameter, diameter, 270, 90);
                path.AddArc(bounds.Right - diameter, bounds.Bottom - diameter, diameter, diameter, 0, 90);
                path.AddArc(bounds.X, bounds.Bottom - diameter, diameter, diameter, 90, 90);
                path.CloseFigure();
                return path;
            }
            foreach (double[] segment in Outline(bounds.Left, bounds.Top, bounds.Right, bounds.Bottom, radius, smoothing, corners))
            {
                if (segment[0] == 0.0)
                    path.AddBezier((float)segment[1], (float)segment[2], (float)segment[3], (float)segment[4],
                                   (float)segment[5], (float)segment[6], (float)segment[7], (float)segment[8]);
                else if (segment[0] == 1.0)
                    path.AddArc((float)(segment[1] - segment[3]), (float)(segment[2] - segment[3]),
                                (float)(2 * segment[3]), (float)(2 * segment[3]), (float)segment[4], (float)segment[5]);
                else
                    path.AddLine((float)segment[1], (float)segment[2], (float)segment[1], (float)segment[2]);
            }
            path.CloseFigure();
            return path;
        }

        // ------------------------------------------------------------------ what a shadow asks of a corner
        // As shape.profile: the distance from the corner's centre (P, P) to the outline by the direction
        // t = qy / (qx + qy) of a point out from it, and the lean - the cosine between that ray and the outline's
        // normal where they meet - at RhoSteps steps of t, made once for a corner of radius 1 at each smoothing and
        // scaled, since every number of a corner is a length times its radius.
        internal const int RhoSteps = 512;
        private const int HalfSteps = 64;

        internal sealed class Profile
        {
            internal Corner Corner;
            internal double P;
            internal double[] Rho, Lean;
        }

        private static readonly Dictionary<long, Profile> units = new Dictionary<long, Profile>();
        private static readonly Dictionary<long, Profile> profiles = new Dictionary<long, Profile>();

        /// The corner's tables for a box whose shorter side is 2 * budget, kept per corner as drawn.
        internal static Profile ProfileOf(double radius, double smoothing, double budget)
        {
            Corner corner = Of(radius, smoothing, budget);
            long key = (long)Math.Round(corner.Radius * 4096) * 1048576 + (long)Math.Round(corner.Smoothing * 1000000);
            Profile known;
            if (profiles.TryGetValue(key, out known)) return known;
            Profile unit = Unit(corner.Smoothing);
            var made = new Profile();
            made.Corner = corner;
            made.P = corner.P;
            made.Lean = unit.Lean;
            made.Rho = new double[RhoSteps + 1];
            for (int k = 0; k <= RhoSteps; k++) made.Rho[k] = unit.Rho[k] * corner.Radius;
            if (profiles.Count >= 64) profiles.Clear();
            profiles[key] = made;
            return made;
        }

        private static Profile Unit(double smoothing)
        {
            long key = (long)Math.Round(smoothing * 1000000000);
            Profile known;
            if (units.TryGetValue(key, out known)) return known;
            Corner corner = Of(1.0, smoothing, 1e9);
            double p = corner.P, r = corner.Radius;
            // The outline's half nearer the horizontal side, in the corner's frame (vertex at the origin, the shape
            // in u >= 0, v >= 0), from (p, 0) to the middle of the arc.
            var us = new List<double>();
            var vs = new List<double>();
            double from = 270.0;
            if (corner.Smoothed)
            {
                double a = corner.A, b = corner.B, c = corner.C, d = corner.D;
                for (int k = 0; k < HalfSteps; k++)
                {
                    double t = k / (double)HalfSteps, s = 1 - t;
                    us.Add(s * s * s * p + 3 * s * s * t * (p - a) + 3 * s * t * t * (p - a - b) + t * t * t * (p - a - b - c));
                    vs.Add(t * t * t * d);
                }
                from = 270.0 - 45.0 * corner.Smoothing;
            }
            for (int k = 0; k <= HalfSteps; k++)
            {
                double angle = Radians(from + (225.0 - from) * k / HalfSteps);
                us.Add(r + r * Math.Cos(angle));
                vs.Add(r + r * Math.Sin(angle));
            }
            var ts = new List<double>();
            var rs = new List<double>();
            var leans = new List<double>();
            int last = us.Count - 1;
            for (int k = last; k >= 0; k--)
            {
                double qx = p - us[k], qy = p - vs[k];
                if (qx + qy <= 0.0) continue;
                int before = Math.Max(0, k - 1), after = Math.Min(last, k + 1);
                double du = us[after] - us[before], dv = vs[after] - vs[before];
                double tangent = Math.Sqrt(du * du + dv * dv), reach = Math.Sqrt(qx * qx + qy * qy);
                ts.Add(qy / (qx + qy));
                rs.Add(reach);
                leans.Add(tangent > 0.0 && reach > 0.0 ? Math.Abs(qx * dv - qy * du) / (reach * tangent) : 1.0);
            }
            var unit = new Profile();
            unit.Corner = corner;
            unit.P = p;
            unit.Rho = new double[RhoSteps + 1];
            unit.Lean = new double[RhoSteps + 1];
            for (int k = RhoSteps / 2; k <= RhoSteps; k++)
            {
                double t = k / (double)RhoSteps;
                int i = ts.BinarySearch(t);
                if (i < 0) i = ~i;
                i = Math.Min(Math.Max(1, i), ts.Count - 1);
                double t0 = ts[i - 1], t1 = ts[i];
                double share = t1 > t0 ? Math.Min(1.0, Math.Max(0.0, (t - t0) / (t1 - t0))) : 0.0;
                unit.Rho[k] = unit.Rho[RhoSteps - k] = rs[i - 1] + (rs[i] - rs[i - 1]) * share;
                unit.Lean[k] = unit.Lean[RhoSteps - k] = leans[i - 1] + (leans[i] - leans[i - 1]) * share;
            }
            if (units.Count >= 64) units.Clear();
            units[key] = unit;
            return unit;
        }

        /// Signed distance from (px, py) to the rounded box of half sizes halfWidth x halfHeight centred on the
        /// origin; inside is negative. Along the ray from the corner's centre, leant onto the outline's normal, in a
        /// corner; across a side elsewhere. The circle's distance exactly when the corner is not smoothed.
        internal static double Distance(Profile shape, double px, double py, double halfWidth, double halfHeight)
        {
            double qx = Math.Abs(px) - (halfWidth - shape.P), qy = Math.Abs(py) - (halfHeight - shape.P);
            if (qx > 0 && qy > 0)
            {
                double reach = Math.Sqrt(qx * qx + qy * qy);
                if (!shape.Corner.Smoothed) return reach - shape.P;
                int k = (int)(qy / (qx + qy) * RhoSteps + 0.5);
                return (reach - shape.Rho[k]) * shape.Lean[k];
            }
            return Math.Max(qx, qy) - shape.P;
        }

        /// Whether (px, py) is inside that box: the outline is convex and seen whole from each corner's centre, so
        /// a point is inside exactly when it is no further out along its ray than the outline is.
        internal static bool Inside(Profile shape, double px, double py, double halfWidth, double halfHeight)
        {
            return Distance(shape, px, py, halfWidth, halfHeight) <= 0;
        }
    }
}
