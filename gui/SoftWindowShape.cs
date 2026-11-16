// Codex Auto Resume - the Dashboard window's own outer corner: the card's corner, tried (v0.6.24, stage 1 surface E).
//
// Windows rounds a window's corners itself (DWMWCP_ROUND, about 8 px) and offers no radius of our choosing; a window it
// does not round - one with a region, or with a window of its own for its shadow - it does not round at all. So the
// window's own corner is two pieces (plans/v0624-stage1-design.md, section 5):
//
// - a window region: the pixels the card's corner (Palette.RadiusCard at the window's scale, smoothed as the cards are -
//   Figma's 60 % for Soft, circular arcs for Classic and Plain) covers fully, less the hairline round its edge. Hard-edged,
//   as a region is: "The system does not display any portion of a window that lies outside of the window region";
// - a companion: one layered popup owned by the window - above it, hidden while it is minimised, gone with it - that lets
//   the mouse through (WS_EX_TRANSPARENT) and paints everything round the region: the hairline and the anti-aliased edge,
//   every pixel the corner covers partly at its coverage, and the window's shadow (the one a still draws round a dialog:
//   14 px, 6 px lower, about 0.17 of the light) onto the desktop. Nothing it paints lies inside the region.
//
// The window's whole rectangle is its client area then (WM_NCCALCSIZE answered with the window itself), so no invisible
// frame is cut off by the region; the resize bands lie inside the visible edge (Chrome.Hit, ChromeLayout.Edges).
//
// The companion follows the window in the very message that moves it (WM_WINDOWPOSCHANGED): UpdateLayeredWindow, its
// picture made again only when the size, the scale or the colours change - the corner pieces kept per scale, the
// straight edges repeated (WindowShape.Compose).
//
// Windows' round corner is kept - the region removed, the companion hidden, DWMWCP_ROUND - while the window is maximised
// or arranged (snapped), in High Contrast, in a remote session, without desktop composition, on Windows 10 (square), and
// whenever the switch is off: Brand.WindowSquircle, on from v0.6.24-beta at the owner's word (M-CORNER still runs on real
// screens before the final). With it
// off, nothing here is made at all (ChromeHost.OwnCorner) and the window is exactly what it was.

using System;
using System.Collections.Generic;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace CodexAutoResume
{
    /// The window's own corner with no window: the decision and the pictures, pure, so the tests ask them a table
    /// (tests/test_gui_window_corner.py).
    internal static class WindowShape
    {
        /// Which corner a window has: Windows 10's square one, Windows 11's round one (DWM's), or our own.
        internal enum Corner { Square, Round, Squircle }

        /// The window's shadow, in px at 96 DPI: as far as it reaches past the edge, how much lower than the window it lies,
        /// and the light it takes at its darkest - the shadow WindowRender's PaintDialog draws round a dialog in a still.
        internal const int ShadowReach = 14, ShadowDrop = 6;
        internal const double ShadowPeak = 0.17;

        /// Sub-samples across one pixel's side where the edge passes through it.
        internal const int Samples = 16;

        [DllImport("dwmapi.dll")]
        private static extern int DwmIsCompositionEnabled(out bool enabled);
        [DllImport("user32.dll")]
        private static extern int GetSystemMetrics(int index);

        private const int SM_REMOTESESSION = 0x1000;

        /// Windows 11 (build 22000 on): where DWM rounds windows and where a corner of our own replaces that.
        internal static bool Windows11
        {
            get { return Environment.OSVersion.Version.Major >= 10 && Environment.OSVersion.Version.Build >= 22000; }
        }

        /// The switch, Brand.WindowSquircle (brand.WINDOW_SQUIRCLE): read as a value, so the compiler, which builds the setup
        /// programs with every warning an error, finds no code it could never reach while it is off.
        internal static readonly bool Switch = Brand.WindowSquircle;

        /// Whether a window may have a corner of its own at all - asked once, as it is built: the switch, Windows 11,
        /// composition, not a remote session, not High Contrast. Off, nothing of this file is made for it.
        internal static bool Wanted()
        {
            return Switch && Windows11 && Composition() && !RemoteSession() && !Palette.Contrast;
        }

        internal static bool Composition()
        {
            try
            {
                bool on;
                return DwmIsCompositionEnabled(out on) != 0 || on;
            }
            catch (Exception) { return false; }
        }

        internal static bool RemoteSession()
        {
            try { return GetSystemMetrics(SM_REMOTESESSION) != 0; }
            catch (Exception) { return true; }
        }

        /// The corner a window has now (5.2 item 6): ours only with the switch on, on Windows 11 with composition, outside a
        /// remote session and High Contrast, and neither maximised nor arranged - "You should treat arranged as a window
        /// state similar to maximized"; Windows' round one otherwise, and Windows 10's square one there.
        internal static Corner Decide(bool on, bool windows11, bool composition, bool remote, bool contrast, bool zoomed,
                                      bool arranged)
        {
            if (!windows11) return Corner.Square;
            if (!on || !composition || remote || contrast || zoomed || arranged) return Corner.Round;
            return Corner.Squircle;
        }

        internal static int Px(double logical, double scale)
        {
            return (int)Math.Round(logical * scale);
        }

        /// The hairline round the window at `scale`, as Soft.Hairline draws a card's: a whole device pixel, one per 100 %.
        internal static int Hairline(double scale)
        {
            return Math.Max(1, (int)Math.Floor(scale + 1e-6));
        }

        /// How far the companion reaches past the window on every side at `scale`: the shadow's reach and its drop.
        internal static int Margin(double scale)
        {
            return Px(ShadowReach, scale) + Px(ShadowDrop, scale);
        }

        // ------------------------------------------------------------------ one window's edge at one size

        /// The window's edge at one size and scale: the corner's coverage of each pixel - the outer outline and the one a
        /// hairline inside it - and the shadow's light. Device pixels; the window's pixel (x, y) spans x to x + 1.
        internal sealed class Edge
        {
            internal readonly int Width, Height, Hair, Reach, Drop, Margin, Tile;
            internal readonly double Scale;
            internal readonly Shape.Profile Outer, Inner;
            /// The top-left corner's coverage, Tile by Tile pixels, outer and inner; the other three are its mirror images.
            internal readonly double[] OuterTile, InnerTile;
            /// Whether the window is big enough for four corners that do not meet: smaller, no corner of its own is cut.
            internal readonly bool Fits;

            internal Edge(int width, int height, double radius, double smoothing, double scale)
            {
                Width = width;
                Height = height;
                Scale = scale;
                Hair = Hairline(scale);
                Reach = Math.Max(1, Px(ShadowReach, scale));
                Drop = Px(ShadowDrop, scale);
                Margin = Reach + Drop;
                double r = radius * scale;
                double budget = Math.Min(width, height) / 2.0;
                Outer = Shape.ProfileOf(r, smoothing, budget);
                Inner = Shape.ProfileOf(Math.Max(0.0, r - Hair), smoothing, budget - Hair);
                Tile = (int)Math.Ceiling(Outer.P) + Hair + 1;
                Fits = width >= 2 * (Tile + Drop) + 2 && height >= 2 * (Tile + Drop) + 2 && Outer.P > 0;
                Tiles tiles = TilesOf(Outer, Inner, Hair, Tile);
                OuterTile = tiles.Outer;
                InnerTile = tiles.Inner;
            }

            /// How much of the window's pixel (x, y) the outer outline covers, 0 to 1; 0 outside the window.
            internal double CoverOuter(int x, int y)
            {
                if (x < 0 || y < 0 || x >= Width || y >= Height) return 0.0;
                int xx = Math.Min(x, Width - 1 - x), yy = Math.Min(y, Height - 1 - y);
                if (xx < Tile && yy < Tile) return OuterTile[yy * Tile + xx];
                return 1.0;
            }

            /// How much of it the outline a hairline inside covers: the window's own pixels where this is 1.
            internal double CoverInner(int x, int y)
            {
                if (x < 0 || y < 0 || x >= Width || y >= Height) return 0.0;
                int xx = Math.Min(x, Width - 1 - x), yy = Math.Min(y, Height - 1 - y);
                if (xx < Tile && yy < Tile) return InnerTile[yy * Tile + xx];
                return xx >= Hair && yy >= Hair ? 1.0 : 0.0;
            }

            /// Whether the pixel is the window's own - inside its region.
            internal bool Own(int x, int y)
            {
                return CoverInner(x, y) >= 1.0;
            }

            /// The shadow's light at the window's pixel (x, y): the stacked layers of PaintDialog's shadow - each
            /// ShadowPeak / Reach - over the outline moved down by Drop, as many as reach the pixel's centre.
            internal double Shadow(int x, int y)
            {
                double d = Shape.Distance(Outer, x + 0.5 - Width / 2.0, y + 0.5 - Drop - Height / 2.0, Width / 2.0, Height / 2.0);
                double layers = Math.Max(0.0, Math.Min(Reach, Reach - d));
                return 1.0 - Math.Pow(1.0 - ShadowPeak / Reach, layers);
            }

            /// The companion's premultiplied ARGB at the window's pixel (x, y), which may lie outside the window: clear where
            /// the window is its own; else the ground and the hairline at their coverage, over the shadow where the outline
            /// leaves room for it.
            internal int Pixel(int x, int y, Color ground, Color line, Color shade)
            {
                double outer = CoverOuter(x, y), inner = CoverInner(x, y);
                if (inner >= 1.0) return 0;
                double shadow = outer >= 1.0 ? 0.0 : Shadow(x, y) * (1.0 - outer);
                double alpha = outer + shadow;
                if (alpha <= 0.0) return 0;
                double edge = outer - inner;
                int a = Byte(alpha * 255.0);
                int red = Math.Min(a, Byte(ground.R * inner + line.R * edge + shade.R * shadow));
                int green = Math.Min(a, Byte(ground.G * inner + line.G * edge + shade.G * shadow));
                int blue = Math.Min(a, Byte(ground.B * inner + line.B * edge + shade.B * shadow));
                return unchecked((int)((uint)a << 24 | (uint)red << 16 | (uint)green << 8 | (uint)blue));
            }
        }

        private static int Byte(double value)
        {
            int rounded = (int)Math.Round(value);
            return rounded < 0 ? 0 : rounded > 255 ? 255 : rounded;
        }

        private sealed class Tiles
        {
            internal double[] Outer, Inner;
        }

        private static readonly Dictionary<string, Tiles> tiles = new Dictionary<string, Tiles>();

        // The top-left corner's coverage, kept per corner as drawn and hairline: the same at every size of the window.
        private static Tiles TilesOf(Shape.Profile outer, Shape.Profile inner, int hair, int tile)
        {
            string key = string.Join("|", new[] { Key(outer), Key(inner), hair.ToString(), tile.ToString() });
            Tiles known;
            if (tiles.TryGetValue(key, out known)) return known;
            var made = new Tiles();
            made.Outer = new double[tile * tile];
            made.Inner = new double[tile * tile];
            for (int y = 0; y < tile; y++)
                for (int x = 0; x < tile; x++)
                {
                    made.Outer[y * tile + x] = Cover(outer, x, y);
                    made.Inner[y * tile + x] = Cover(inner, x - hair, y - hair);
                }
            if (tiles.Count >= 16) tiles.Clear();
            tiles[key] = made;
            return made;
        }

        private static string Key(Shape.Profile shape)
        {
            return shape.Corner.Radius.ToString("R") + "/" + shape.Corner.Smoothing.ToString("R");
        }

        /// How much of the pixel whose top-left lies at (u, v) from a corner's vertex - the shape down and to the right -
        /// the corner covers: whole or none where the outline is further than a pixel and a half from its centre
        /// (Shape.Distance, which is within a third of a pixel), else Samples x Samples points counted inside it (Edge).
        internal static double Cover(Shape.Profile shape, double u, double v)
        {
            if (shape.P <= 0) return u >= 0 && v >= 0 ? 1.0 : 0.0;
            // A box so big that only this corner is near: its far sides never fold back onto the pixel.
            const double half = 4096.0;
            double d = Shape.Distance(shape, u + 0.5 - half, v + 0.5 - half, half, half);
            if (d <= -1.5) return 1.0;
            if (d >= 1.5) return 0.0;
            Outline line = OutlineOf(shape.Corner);
            int count = 0;
            for (int sy = 0; sy < Samples; sy++)
            {
                double py = v + (sy + 0.5) / Samples;
                for (int sx = 0; sx < Samples; sx++)
                    if (line.Inside(u + (sx + 0.5) / Samples, py)) count++;
            }
            return count / (double)(Samples * Samples);
        }

        /// One corner's outline as a curve over its side - the window's edge needs it closer than a shadow does: within a
        /// thousandth of a pixel, where Shape.Inside's table of distances by direction is a tenth off along a flat stretch.
        /// In the corner's frame (vertex at the origin, the shape at u, v >= 0), the half nearer the top side is
        /// v = Edge(u) from the middle of the arc to P: the arc of radius R about (R, R), then Figma's Bezier from its end
        /// (P - a - b - c, d) to (P, 0) - the outline Shape.Outline draws. The other half is its mirror across u = v.
        internal sealed class Outline
        {
            internal readonly Shape.Corner Corner;
            internal readonly double Middle, Joint;
            private readonly double[] table;
            private const int PerPixel = 64;

            internal Outline(Shape.Corner corner)
            {
                Corner = corner;
                double r = corner.Radius;
                Middle = r * (1.0 - Math.Sqrt(0.5));
                Joint = corner.Smoothed ? corner.P - corner.A - corner.B - corner.C : r;
                int steps = Math.Max(1, (int)Math.Ceiling((corner.P - Joint) * PerPixel));
                table = new double[steps + 1];
                for (int k = 0; k <= steps; k++) table[k] = Bezier(Joint + (corner.P - Joint) * k / steps);
            }

            // The Bezier's v where its u is `u`: its u falls from P to Joint as t goes from 0 to 1, found by halving.
            private double Bezier(double u)
            {
                Shape.Corner c = Corner;
                if (!c.Smoothed) return 0.0;
                double p = c.P, a = c.A, b = c.B, cc = c.C, low = 0.0, high = 1.0;
                for (int i = 0; i < 48; i++)
                {
                    double t = (low + high) / 2, s = 1 - t;
                    double at = s * s * s * p + 3 * s * s * t * (p - a) + 3 * s * t * t * (p - a - b) + t * t * t * (p - a - b - cc);
                    if (at > u) low = t;
                    else high = t;
                }
                double found = (low + high) / 2;
                return found * found * found * c.D;
            }

            /// The outline's v at `u`, from the middle of the arc to P.
            internal double Edge(double u)
            {
                double r = Corner.Radius;
                if (u >= Corner.P) return 0.0;
                if (u <= Joint)
                {
                    double du = Math.Min(u, r) - r;
                    return r - Math.Sqrt(Math.Max(0.0, r * r - du * du));
                }
                double at = (u - Joint) / (Corner.P - Joint) * (table.Length - 1);
                int k = Math.Min(table.Length - 2, (int)at);
                return table[k] + (table[k + 1] - table[k]) * (at - k);
            }

            /// Whether the point (u, v) of the corner's frame is inside the outline.
            internal bool Inside(double u, double v)
            {
                if (u < 0.0 || v < 0.0) return false;
                if (u >= Corner.P || v >= Corner.P) return true;
                if (v > u)
                {
                    double swap = u;
                    u = v;
                    v = swap;
                }
                if (u < Middle) return false;
                return v >= Edge(u);
            }
        }

        private static readonly Dictionary<string, Outline> outlines = new Dictionary<string, Outline>();

        private static Outline OutlineOf(Shape.Corner corner)
        {
            string key = corner.Radius.ToString("R") + "/" + corner.Smoothing.ToString("R");
            Outline known;
            if (outlines.TryGetValue(key, out known)) return known;
            var made = new Outline(corner);
            if (outlines.Count >= 16) outlines.Clear();
            outlines[key] = made;
            return made;
        }

        // ------------------------------------------------------------------ the region

        /// The window's region as rectangles, in its own coordinates: for each run of rows the span of pixels it owns
        /// (Edge.Own) - one span a row, the shape being convex - rows with the same span merged.
        internal static List<Rectangle> RegionRects(Edge edge)
        {
            var rects = new List<Rectangle>();
            int runTop = -1, runLeft = -1;
            for (int y = 0; y <= edge.Height; y++)
            {
                int left = y < edge.Height ? FirstOwn(edge, y) : -1;
                if (left == runLeft) continue;
                if (runLeft >= 0) rects.Add(Rectangle.FromLTRB(runLeft, runTop, edge.Width - runLeft, y));
                runTop = y;
                runLeft = left;
            }
            return rects;
        }

        // The first pixel of row y the window owns, or -1.
        private static int FirstOwn(Edge edge, int y)
        {
            int yy = Math.Min(y, edge.Height - 1 - y);
            if (yy < edge.Hair) return -1;
            if (yy >= edge.Tile) return edge.Hair;
            for (int x = 0; x < edge.Tile; x++)
                if (edge.InnerTile[yy * edge.Tile + x] >= 1.0) return x;
            return edge.Tile;
        }

        [DllImport("gdi32.dll")]
        private static extern IntPtr ExtCreateRegion(IntPtr transform, int count, byte[] data);

        /// The region's GDI handle, made from RegionRects; IntPtr.Zero if GDI makes none.
        internal static IntPtr Region(Edge edge)
        {
            List<Rectangle> rects = RegionRects(edge);
            const int header = 32;
            var data = new byte[header + 16 * rects.Count];
            Action<int, int> put = delegate(int at, int value) { BitConverter.GetBytes(value).CopyTo(data, at); };
            put(0, header);                       // dwSize
            put(4, 1);                            // iType: RDH_RECTANGLES
            put(8, rects.Count);                  // nCount
            put(12, 16 * rects.Count);            // nRgnSize
            put(16, 0); put(20, 0); put(24, edge.Width); put(28, edge.Height);   // rcBound
            for (int i = 0; i < rects.Count; i++)
            {
                int at = header + 16 * i;
                put(at, rects[i].Left);
                put(at + 4, rects[i].Top);
                put(at + 8, rects[i].Right);
                put(at + 12, rects[i].Bottom);
            }
            return ExtCreateRegion(IntPtr.Zero, data.Length, data);
        }

        // ------------------------------------------------------------------ a still's corner (5.6)

        /// A still's corner as the screen shows the window's own: its pixels opaque where the window owns them, and round
        /// them the edge its companion paints - the picture and the hairline at their coverage, the outline's coverage its
        /// alpha - with no shadow, as a capture's corners are clear. `pixels` is a Format32bppArgb bitmap's, not
        /// premultiplied, `edge.Width` by `edge.Height`, changed in place.
        internal static void CutStill(int[] pixels, Edge edge, Color line)
        {
            for (int y = 0; y < edge.Height; y++)
                for (int x = 0; x < edge.Width; x++)
                {
                    int at = y * edge.Width + x;
                    double outer = edge.CoverOuter(x, y), inner = edge.CoverInner(x, y);
                    int pixel = pixels[at];
                    if (inner >= 1.0)
                    {
                        pixels[at] = unchecked((int)0xFF000000) | (pixel & 0xFFFFFF);
                        continue;
                    }
                    if (outer <= 0.0)
                    {
                        pixels[at] = 0;
                        continue;
                    }
                    double edgeShare = outer - inner;
                    int red = Byte((((pixel >> 16) & 255) * inner + line.R * edgeShare) / outer);
                    int green = Byte((((pixel >> 8) & 255) * inner + line.G * edgeShare) / outer);
                    int blue = Byte(((pixel & 255) * inner + line.B * edgeShare) / outer);
                    pixels[at] = unchecked((int)((uint)Byte(outer * 255.0) << 24 | (uint)red << 16 | (uint)green << 8 | (uint)blue));
                }
        }

        // ------------------------------------------------------------------ the companion's picture

        /// Where the companion's picture goes, row by row: an array (the tests) or the memory of a DIB section (the window).
        internal interface Sink
        {
            void Put(int y, int x, int[] values, int start, int count);
        }

        internal sealed class ArraySink : Sink
        {
            internal readonly int[] Pixels;
            internal readonly int Width;

            internal ArraySink(int width, int height)
            {
                Width = width;
                Pixels = new int[width * height];
            }

            public void Put(int y, int x, int[] values, int start, int count)
            {
                Array.Copy(values, start, Pixels, y * Width + x, count);
            }
        }

        /// Rows written into memory that starts clear (a new DIB section's): only what is not clear is written.
        internal sealed class MemorySink : Sink
        {
            private readonly IntPtr bits;
            private readonly int stride;

            internal MemorySink(IntPtr bits, int stride)
            {
                this.bits = bits;
                this.stride = stride;
            }

            public void Put(int y, int x, int[] values, int start, int count)
            {
                Marshal.Copy(values, start, new IntPtr(bits.ToInt64() + (long)y * stride + 4L * x), count);
            }
        }

        /// The companion's size for `edge`: the window's, and Margin more on every side.
        internal static Size CompanionSize(Edge edge)
        {
            return new Size(edge.Width + 2 * edge.Margin, edge.Height + 2 * edge.Margin);
        }

        private sealed class Blocks
        {
            internal int Zone, Band;
            internal int[] TopLeft, TopRight, BottomLeft, BottomRight, Left, Right;
        }

        private static readonly Dictionary<string, Blocks> blocks = new Dictionary<string, Blocks>();

        /// The companion's picture for `edge`, into `sink`, which starts clear: the four corner blocks (each Margin + Tile +
        /// Drop square - the shadow's corner lies Drop lower than the window's - kept per scale and colours: the same at
        /// every size), the straight edges repeated row by row, the
        /// window's own pixels never written. A window too small for its corners (Edge.Fits) is drawn pixel by pixel.
        internal static void Compose(Edge edge, Color ground, Color line, Color shade, Sink sink)
        {
            Size size = CompanionSize(edge);
            int m = edge.Margin;
            if (!edge.Fits)
            {
                var row = new int[size.Width];
                for (int y = 0; y < size.Height; y++)
                {
                    for (int x = 0; x < size.Width; x++) row[x] = edge.Pixel(x - m, y - m, ground, line, shade);
                    sink.Put(y, 0, row, 0, size.Width);
                }
                return;
            }
            Blocks b = BlocksOf(edge, ground, line, shade);
            int zone = b.Zone, middle = size.Width - 2 * zone;
            var straight = new int[Math.Max(1, middle)];
            for (int r = 0; r < zone; r++)
            {
                // The top rows, then the bottom ones: the corners from their blocks, between them one value a row.
                for (int pass = 0; pass < 2; pass++)
                {
                    int y = pass == 0 ? r : size.Height - zone + r;
                    int[] left = pass == 0 ? b.TopLeft : b.BottomLeft, right = pass == 0 ? b.TopRight : b.BottomRight;
                    sink.Put(y, 0, left, r * zone, zone);
                    int value = edge.Pixel(zone - m, y - m, ground, line, shade);
                    if (value != 0 && middle > 0)
                    {
                        for (int i = 0; i < middle; i++) straight[i] = value;
                        sink.Put(y, zone, straight, 0, middle);
                    }
                    sink.Put(y, size.Width - zone, right, r * zone, zone);
                }
            }
            for (int y = zone; y < size.Height - zone; y++)
            {
                sink.Put(y, 0, b.Left, 0, b.Band);
                sink.Put(y, size.Width - b.Band, b.Right, 0, b.Band);
            }
        }

        private static Blocks BlocksOf(Edge edge, Color ground, Color line, Color shade)
        {
            string key = string.Join("|", new[] { Key(edge.Outer), Key(edge.Inner), edge.Hair.ToString(), edge.Tile.ToString(),
                                                  edge.Reach.ToString(), edge.Drop.ToString(), ground.ToArgb().ToString(),
                                                  line.ToArgb().ToString(), shade.ToArgb().ToString() });
            Blocks known;
            if (blocks.TryGetValue(key, out known)) return known;
            int m = edge.Margin, zone = m + edge.Tile + edge.Drop, band = m + edge.Hair;
            var made = new Blocks();
            made.Zone = zone;
            made.Band = band;
            made.TopLeft = new int[zone * zone];
            made.TopRight = new int[zone * zone];
            made.BottomLeft = new int[zone * zone];
            made.BottomRight = new int[zone * zone];
            for (int r = 0; r < zone; r++)
                for (int c = 0; c < zone; c++)
                {
                    int top = edge.Pixel(c - m, r - m, ground, line, shade);
                    int bottom = edge.Pixel(c - m, edge.Height + m - zone + r, ground, line, shade);
                    made.TopLeft[r * zone + c] = made.TopRight[r * zone + zone - 1 - c] = top;
                    made.BottomLeft[r * zone + c] = made.BottomRight[r * zone + zone - 1 - c] = bottom;
                }
            // A row between the corners: the shadow, the hairline, then the window's own pixels. The same in every such row:
            // the window's corner is above it and the shadow's corner, Drop lower, too.
            int across = edge.Height / 2;
            made.Left = new int[band];
            made.Right = new int[band];
            for (int c = 0; c < band; c++)
                made.Left[c] = made.Right[band - 1 - c] = edge.Pixel(c - m, across, ground, line, shade);
            if (blocks.Count >= 16) blocks.Clear();
            blocks[key] = made;
            return made;
        }
    }

    /// The window's own corner on a window (ChromeHost.OwnCorner): its region, its companion, and which corner it has as
    /// it moves, resizes, is maximised, snapped and restored.
    internal sealed class WindowCorner : IDisposable
    {
        [StructLayout(LayoutKind.Sequential)]
        private struct POINT { public int X, Y; }
        [StructLayout(LayoutKind.Sequential)]
        private struct SIZE { public int Width, Height; }
        [StructLayout(LayoutKind.Sequential)]
        private struct BLENDFUNCTION { public byte Op, Flags, Alpha, Format; }
        [StructLayout(LayoutKind.Sequential)]
        private struct BITMAPINFOHEADER
        {
            public int Size, Width, Height;
            public short Planes, BitCount;
            public int Compression, SizeImage, XPelsPerMeter, YPelsPerMeter, ClrUsed, ClrImportant;
        }

        private delegate bool ArrangedCall(IntPtr window);

        [DllImport("user32.dll")]
        private static extern bool IsZoomed(IntPtr window);
        [DllImport("user32.dll")]
        private static extern bool IsIconic(IntPtr window);
        [DllImport("user32.dll")]
        private static extern bool IsWindowVisible(IntPtr window);
        [DllImport("user32.dll")]
        private static extern bool GetWindowRect(IntPtr window, out Chrome.RECT rect);
        [DllImport("user32.dll")]
        private static extern int SetWindowRgn(IntPtr window, IntPtr region, bool redraw);
        [DllImport("user32.dll")]
        private static extern bool ShowWindow(IntPtr window, int command);
        [DllImport("user32.dll")]
        private static extern int GetDpiForWindow(IntPtr window);
        [DllImport("user32.dll")]
        private static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int width, int height, uint flags);
        [DllImport("user32.dll")]
        private static extern IntPtr GetDC(IntPtr window);
        [DllImport("user32.dll")]
        private static extern int ReleaseDC(IntPtr window, IntPtr dc);
        [DllImport("user32.dll")]
        private static extern bool UpdateLayeredWindow(IntPtr window, IntPtr screen, ref POINT at, ref SIZE size, IntPtr source,
                                                       ref POINT from, int key, ref BLENDFUNCTION blend, int flags);
        [DllImport("user32.dll", EntryPoint = "UpdateLayeredWindow")]
        private static extern bool MoveLayeredWindow(IntPtr window, IntPtr screen, ref POINT at, IntPtr size, IntPtr source,
                                                     IntPtr from, int key, IntPtr blend, int flags);
        [DllImport("gdi32.dll")]
        private static extern IntPtr CreateCompatibleDC(IntPtr dc);
        [DllImport("gdi32.dll")]
        private static extern bool DeleteDC(IntPtr dc);
        [DllImport("gdi32.dll")]
        private static extern IntPtr SelectObject(IntPtr dc, IntPtr item);
        [DllImport("gdi32.dll")]
        private static extern bool DeleteObject(IntPtr item);
        [DllImport("gdi32.dll")]
        private static extern IntPtr CreateDIBSection(IntPtr dc, ref BITMAPINFOHEADER info, int usage, out IntPtr bits,
                                                      IntPtr section, int offset);
        [DllImport("dwmapi.dll")]
        private static extern int DwmSetWindowAttribute(IntPtr window, int attribute, ref int value, int size);
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr GetModuleHandle(string name);
        [DllImport("kernel32.dll", CharSet = CharSet.Ansi)]
        private static extern IntPtr GetProcAddress(IntPtr module, string name);

        internal const int WM_WINDOWPOSCHANGED = 0x0047;
        private const int SW_HIDE = 0, SW_SHOWNOACTIVATE = 4;
        private const int ULW_ALPHA = 2;
        private const uint SWP_NOSIZE = 0x0001, SWP_NOMOVE = 0x0002, SWP_NOZORDER = 0x0004, SWP_NOACTIVATE = 0x0010,
                           SWP_FRAMECHANGED = 0x0020;
        // DWMWA_WINDOW_CORNER_PREFERENCE: DWMWCP_DONOTROUND under a corner of our own, DWMWCP_ROUND under Windows' (Soft.TitleBar).
        private const int DoNotRound = 1;

        private static ArrangedCall arranged;
        private static bool arrangedLooked;

        private readonly Form form;
        private CornerLayer layer;
        private WindowShape.Corner now;
        private bool busy, again, preferred, failed;
        private Size shapedSize;
        private int shapedDpi;
        private Color shapedGround, shapedLine;
        private IntPtr memory, bitmap, kept;
        private Size bitmapSize;

        /// Told when the window's corner changes (the hit test's edges follow it).
        internal event EventHandler Changed;

        private WindowCorner(Form form)
        {
            this.form = form;
            now = Want();
        }

        /// The corner of `form`, a top-level window that asked for its own (WindowShape.Wanted).
        internal static WindowCorner Attach(Form form)
        {
            var corner = new WindowCorner(form);
            form.BackColorChanged += delegate { corner.Refresh(); };
            return corner;
        }

        /// The corner the window has now.
        internal WindowShape.Corner Now { get { return now; } }

        /// Whether it is ours now: the window's whole rectangle its client area, its region cut.
        internal bool Shaped { get { return now == WindowShape.Corner.Squircle; } }

        /// The companion, for the tests; IntPtr.Zero before it is made.
        internal IntPtr Companion { get { return layer == null ? IntPtr.Zero : layer.Handle; } }

        /// How far the companion reaches past the window on every side now.
        internal int Margin { get { return WindowShape.Margin(Scale()); } }

        /// The corner the window should have in the state it is in (WindowShape.Decide).
        internal WindowShape.Corner Want()
        {
            IntPtr handle = form.IsHandleCreated ? form.Handle : IntPtr.Zero;
            bool zoomed = handle != IntPtr.Zero && IsZoomed(handle);
            return WindowShape.Decide(!failed, WindowShape.Windows11, WindowShape.Composition(), WindowShape.RemoteSession(),
                                      Palette.Contrast, zoomed, Arranged(handle));
        }

        // IsWindowArranged (Windows 10 1903 on), found at run time: snapped is "a window state similar to maximized".
        private static bool Arranged(IntPtr handle)
        {
            if (handle == IntPtr.Zero) return false;
            if (!arrangedLooked)
            {
                arrangedLooked = true;
                try
                {
                    IntPtr call = GetProcAddress(GetModuleHandle("user32.dll"), "IsWindowArranged");
                    if (call != IntPtr.Zero) arranged = (ArrangedCall)Marshal.GetDelegateForFunctionPointer(call, typeof(ArrangedCall));
                }
                catch (Exception) { arranged = null; }
            }
            try { return arranged != null && arranged(handle); }
            catch (Exception) { return false; }
        }

        private double Scale()
        {
            int dpi = 0;
            try { if (form.IsHandleCreated) dpi = GetDpiForWindow(form.Handle); }
            catch (Exception) { dpi = 0; }
            return dpi > 0 ? dpi / 96.0 : SettingsForm.DpiScale;
        }

        /// Handles `m` before the window's caption does: true when it is answered here. WM_NCCALCSIZE while the corner is
        /// ours: the whole window is the client (nothing of the rectangle given is taken off). WM_WINDOWPOSCHANGED: the
        /// region and the companion follow the window at once, and the message goes on to the window.
        internal bool Intercept(ref Message m)
        {
            if (m.Msg == Chrome.WM_NCCALCSIZE)
            {
                if (m.LParam == IntPtr.Zero || Want() != WindowShape.Corner.Squircle) return false;
                m.Result = IntPtr.Zero;
                return true;
            }
            if (m.Msg == WM_WINDOWPOSCHANGED) Sync();
            return false;
        }

        /// The region and the companion as the window is now - in the message that moved it, so the companion is never a
        /// message behind.
        internal void Sync()
        {
            if (!form.IsHandleCreated) return;
            if (busy)
            {
                // A change inside our own (the region's, or the window's own handling of it - a form put back to its
                // restored bounds): looked at again once this one is done, still in this message.
                again = true;
                return;
            }
            busy = true;
            try
            {
                int rounds = 0;
                do
                {
                    again = false;
                    SyncOnce();
                }
                while (again && ++rounds < 4);
            }
            finally { busy = false; }
        }

        private void SyncOnce()
        {
            try
            {
                WindowShape.Corner want = Want();
                if (want != now)
                {
                    now = want;
                    if (now != WindowShape.Corner.Squircle) Unshape();
                    Prefer();
                    LaterFrame();
                    EventHandler changed = Changed;
                    if (changed != null) changed(this, EventArgs.Empty);
                }
                else if (!preferred) Prefer();
                if (now != WindowShape.Corner.Squircle) return;
                IntPtr handle = form.Handle;
                Chrome.RECT rect;
                if (!GetWindowRect(handle, out rect)) return;
                var size = new Size(rect.Right - rect.Left, rect.Bottom - rect.Top);
                int dpi = (int)Math.Round(Scale() * 96);
                double scale = dpi / 96.0;
                int margin = WindowShape.Margin(scale);
                var at = new POINT { X = rect.Left - margin, Y = rect.Top - margin };
                if (size != shapedSize || dpi != shapedDpi || Ground() != shapedGround || Palette.Line != shapedLine)
                    Reshape(size, dpi, at);
                else if (layer != null)
                    MoveLayeredWindow(layer.Handle, IntPtr.Zero, ref at, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 0, IntPtr.Zero, 0);
                bool visible = IsWindowVisible(handle) && !IsIconic(handle);
                if (layer != null) ShowWindow(layer.Handle, visible && bitmap != IntPtr.Zero ? SW_SHOWNOACTIVATE : SW_HIDE);
            }
            catch (Exception)
            {
                // A corner that cannot be made is Windows' round one, for the rest of the window's life.
                failed = true;
                now = WindowShape.Corner.Round;
                try { Unshape(); Prefer(); LaterFrame(); }
                catch (Exception) { }
                EventHandler changed = Changed;
                if (changed != null) changed(this, EventArgs.Empty);
            }
        }

        // The shadow's colour: the ink PaintDialog shades a still's dialog with in light (5.2 item 2, O12), and in dark the
        // theme's own shadow, all but black - a light ink would be a glow round the window, never a shadow.
        private static Color Shade()
        {
            return Palette.Dark ? Tokens.ShadowDark : Palette.Ink;
        }

        private Color Ground()
        {
            return form.BackColor.A == 255 ? form.BackColor : Palette.Canvas;
        }

        // The theme's colours changed: the companion's picture is made again.
        private void Refresh()
        {
            shapedSize = Size.Empty;
            Sync();
        }

        // The region and the companion's picture for a window `size` big at `dpi`, the companion at `at`.
        private void Reshape(Size size, int dpi, POINT at)
        {
            double scale = dpi / 96.0;
            Color ground = Ground(), line = Palette.Line;
            var edge = new WindowShape.Edge(size.Width, size.Height, Palette.RadiusCard, Shape.Smoothing, scale);
            shapedSize = size;
            shapedDpi = dpi;
            shapedGround = ground;
            shapedLine = line;
            if (!edge.Fits)
            {
                SetWindowRgn(form.Handle, IntPtr.Zero, true);
                FreeBitmap();
                return;
            }
            IntPtr region = WindowShape.Region(edge);
            if (region == IntPtr.Zero) throw new InvalidOperationException("no region");
            if (SetWindowRgn(form.Handle, region, true) == 0)
            {
                DeleteObject(region);
                throw new InvalidOperationException("the region was not taken");
            }
            if (layer == null) layer = new CornerLayer(form.Handle);
            Size whole = WindowShape.CompanionSize(edge);
            FreeBitmap();
            var info = new BITMAPINFOHEADER();
            info.Size = Marshal.SizeOf(typeof(BITMAPINFOHEADER));
            info.Width = whole.Width;
            info.Height = -whole.Height;
            info.Planes = 1;
            info.BitCount = 32;
            IntPtr screen = GetDC(IntPtr.Zero);
            try
            {
                memory = CreateCompatibleDC(screen);
                IntPtr bits;
                bitmap = CreateDIBSection(screen, ref info, 0, out bits, IntPtr.Zero, 0);
                if (memory == IntPtr.Zero || bitmap == IntPtr.Zero || bits == IntPtr.Zero)
                    throw new InvalidOperationException("no bitmap for the companion");
                kept = SelectObject(memory, bitmap);
                bitmapSize = whole;
                WindowShape.Compose(edge, ground, line, Shade(), new WindowShape.MemorySink(bits, 4 * whole.Width));
                var dimensions = new SIZE { Width = whole.Width, Height = whole.Height };
                var from = new POINT();
                var blend = new BLENDFUNCTION { Op = 0, Flags = 0, Alpha = 255, Format = 1 };
                if (!UpdateLayeredWindow(layer.Handle, screen, ref at, ref dimensions, memory, ref from, 0, ref blend, ULW_ALPHA))
                    throw new InvalidOperationException("the companion was not updated");
            }
            finally { ReleaseDC(IntPtr.Zero, screen); }
        }

        // Windows' own corner again: no region, the companion hidden.
        private void Unshape()
        {
            shapedSize = Size.Empty;
            if (form.IsHandleCreated) SetWindowRgn(form.Handle, IntPtr.Zero, true);
            if (layer != null) ShowWindow(layer.Handle, SW_HIDE);
        }

        // Asks DWM for no corner of its own under ours, and for its round one otherwise (as Soft.TitleBar does).
        private void Prefer()
        {
            if (!form.IsHandleCreated) return;
            preferred = true;
            int corner = now == WindowShape.Corner.Squircle ? DoNotRound : Soft.CornerRound;
            try { DwmSetWindowAttribute(form.Handle, Soft.CornerPreferenceAttribute, ref corner, 4); }
            catch (Exception) { }
        }

        // The client area worked out again for the corner it has now - after this message, never inside it.
        private void LaterFrame()
        {
            if (!form.IsHandleCreated) return;
            IntPtr handle = form.Handle;
            form.BeginInvoke(new MethodInvoker(delegate
            {
                try { SetWindowPos(handle, IntPtr.Zero, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED); }
                catch (Exception) { }
            }));
        }

        private void FreeBitmap()
        {
            if (memory != IntPtr.Zero && kept != IntPtr.Zero) SelectObject(memory, kept);
            if (bitmap != IntPtr.Zero) DeleteObject(bitmap);
            if (memory != IntPtr.Zero) DeleteDC(memory);
            memory = bitmap = kept = IntPtr.Zero;
            bitmapSize = Size.Empty;
        }

        public void Dispose()
        {
            FreeBitmap();
            if (layer != null) layer.DestroyHandle();
            layer = null;
        }

        /// The companion's window: layered, owned by the window, never active, the mouse passing through it.
        private sealed class CornerLayer : NativeWindow
        {
            private const int WS_POPUP = unchecked((int)0x80000000);
            private const int WS_EX_LAYERED = 0x00080000, WS_EX_TRANSPARENT = 0x00000020, WS_EX_TOOLWINDOW = 0x00000080,
                              WS_EX_NOACTIVATE = 0x08000000;
            private const int WM_NCHITTEST = 0x0084, WM_MOUSEACTIVATE = 0x0021, MA_NOACTIVATE = 3;

            internal CornerLayer(IntPtr owner)
            {
                var made = new CreateParams();
                made.Caption = "";
                made.Style = WS_POPUP;
                made.ExStyle = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE;
                made.Parent = owner;
                CreateHandle(made);
            }

            protected override void WndProc(ref Message m)
            {
                if (m.Msg == WM_NCHITTEST)
                {
                    m.Result = (IntPtr)Chrome.HTTRANSPARENT;
                    return;
                }
                if (m.Msg == WM_MOUSEACTIVATE)
                {
                    m.Result = (IntPtr)MA_NOACTIVATE;
                    return;
                }
                base.WndProc(ref m);
            }
        }
    }
}
