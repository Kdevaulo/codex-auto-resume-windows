// Codex Auto Resume - the days with a look of their own, as this window draws them: brand's one list of shapes (Brand.DayScene).

using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.Windows.Forms;

namespace CodexAutoResume
{
    /// One shape of brand's list: brand.days.element_at, read here.
    internal sealed class DayElement
    {
        internal string Kind, Motion;
        internal double[] Numbers, Values;
        internal Color Colour;
        internal double Opacity;
    }

    /// Reading and drawing brand's list. It is the list's reader and nothing else: every scene is in brand/days.py.
    internal static class DayArt
    {
        private static readonly Dictionary<string, DayElement[]> read = new Dictionary<string, DayElement[]>();

        /// Whether this window may look at the date at all: only a window a person opened (Main), never a picture or a probe.
        internal static bool On;

        /// The date it looks at: now. A probe's own, to see a window across midnight.
        internal static Func<DateTime> Clock = delegate { return DateTime.Now; };

        /// The look of today, or null: an ordinary day, High Contrast, or a window that is no person's.
        internal static string Today()
        {
            string look, top, bottom;
            if (!On || Palette.Contrast) return null;
            DateTime now = Clock();
            return Brand.DayLook(now.Year, now.Month, now.Day, out look, out top, out bottom) ? look : null;
        }

        internal static DayElement[] Parse(string text)
        {
            DayElement[] found;
            if (read.TryGetValue(text, out found)) return found;
            string[] lines = text.Split('\n');
            found = new DayElement[lines.Length];
            for (int index = 0; index < lines.Length; index++)
            {
                string[] parts = lines[index].Split(';');
                found[index] = new DayElement
                {
                    Kind = parts[0], Numbers = Numbers(parts[1]), Colour = ColorTranslator.FromHtml(parts[2]),
                    Opacity = double.Parse(parts[3], CultureInfo.InvariantCulture), Motion = parts[4], Values = Numbers(parts[5])
                };
            }
            read[text] = found;
            return found;
        }

        private static double[] Numbers(string text)
        {
            if (text.Length == 0) return new double[0];
            string[] parts = text.Split(' ');
            var values = new double[parts.Length];
            for (int index = 0; index < parts.Length; index++) values[index] = double.Parse(parts[index], CultureInfo.InvariantCulture);
            return values;
        }

        private static double Wave(double seconds, double duration, double delay)
        {
            double phase = (seconds - delay) / duration;
            phase -= Math.Floor(phase);
            return (1.0 - Math.Cos(2.0 * Math.PI * phase)) / 2.0;
        }

        private delegate void Move(ref double x, ref double y);

        private static void Centre(DayElement e, out double x, out double y)
        {
            if (e.Kind != "poly")
            {
                x = e.Numbers[0];
                y = e.Numbers[1];
                return;
            }
            double left = double.MaxValue, right = double.MinValue, top = double.MaxValue, bottom = double.MinValue;
            for (int at = 0; at < e.Numbers.Length; at += 2)
            {
                left = Math.Min(left, e.Numbers[at]);
                right = Math.Max(right, e.Numbers[at]);
                top = Math.Min(top, e.Numbers[at + 1]);
                bottom = Math.Max(bottom, e.Numbers[at + 1]);
            }
            x = (left + right) / 2.0;
            y = (top + bottom) / 2.0;
        }

        private static double[] Placed(DayElement e, Move move)
        {
            var numbers = (double[])e.Numbers.Clone();
            if (e.Kind == "poly" || e.Kind == "stroke")
                for (int at = e.Kind == "stroke" ? 1 : 0; at + 1 < numbers.Length; at += 2) move(ref numbers[at], ref numbers[at + 1]);
            else move(ref numbers[0], ref numbers[1]);
            return numbers;
        }

        /// brand.days.element_at: one shape `seconds` in.
        internal static void At(DayElement e, double seconds, out double[] numbers, out double opacity)
        {
            opacity = e.Opacity;
            numbers = e.Numbers;
            double[] v = e.Values;
            if (e.Motion == "fall")
            {
                double part = (seconds - v[1]) / v[0];
                part -= Math.Floor(part);
                double cx, cy;
                Centre(e, out cx, out cy);
                double dy = -14.0 + 96.0 * part, radians = v[2] * part * Math.PI / 180.0, c = Math.Cos(radians), s = Math.Sin(radians);
                numbers = Placed(e, delegate(ref double x, ref double y)
                {
                    double nx = cx + (x - cx) * c - (y - cy) * s, ny = cy + dy + (x - cx) * s + (y - cy) * c;
                    x = nx;
                    y = ny;
                });
            }
            else if (e.Motion == "twinkle")
            {
                double level = Wave(seconds, v[0], v[1]), cx, cy, size = 0.7 + 0.4 * level;
                Centre(e, out cx, out cy);
                numbers = Placed(e, delegate(ref double x, ref double y)
                {
                    x = cx + (x - cx) * size;
                    y = cy + (y - cy) * size;
                });
                opacity = 0.25 + 0.75 * level;
            }
            else if (e.Motion == "breathe") opacity = v[1] + v[2] * Wave(seconds, v[0], 0.0);
            else if (e.Motion == "drift")
            {
                double turn = seconds / v[0], part = turn - Math.Floor(turn);
                if (((long)Math.Floor(turn)) % 2 != 0) part = 1.0 - part;
                double dx = -10.0 + 24.0 * (1.0 - Math.Cos(Math.PI * part)) / 2.0;
                numbers = Placed(e, delegate(ref double x, ref double y) { x += dx; });
            }
            else if (e.Motion == "sway")
            {
                double radians = (-5.0 + 10.0 * Wave(seconds, v[0], 0.0)) * Math.PI / 180.0, c = Math.Cos(radians), s = Math.Sin(radians), px = v[1], py = v[2];
                numbers = Placed(e, delegate(ref double x, ref double y)
                {
                    double nx = px + (x - px) * c - (y - py) * s, ny = py + (x - px) * s + (y - py) * c;
                    x = nx;
                    y = ny;
                });
            }
            else if (e.Motion == "flame")
            {
                numbers = (double[])e.Numbers.Clone();
                double tall = numbers[3] * (1.0 + 0.35 * Wave(seconds, v[0], 0.0));
                numbers[1] = v[1] - tall;
                numbers[3] = tall;
            }
        }

        private static PointF[] Points(double[] n, int from, Func<double, double, PointF> at)
        {
            var points = new PointF[(n.Length - from) / 2];
            for (int index = 0; index < points.Length; index++) points[index] = at(n[from + index * 2], n[from + index * 2 + 1]);
            return points;
        }

        /// Every shape of `elements`, `seconds` in, each point of its 190 by 66 (or a mark's 32 by 32) put where `at` says, `unit` to the pixel.
        /// A shape wholly outside what `g` may draw on (its clip) is not filled at all (W2: the day's specks laid band after
        /// band, and the caption buttons that paint the day under them, each its own small clip, so a frame costs no more
        /// than the scene alone did).
        internal static void Draw(Graphics g, DayElement[] elements, double seconds, double unit, Func<double, double, PointF> at)
        {
            GraphicsState state = g.Save();
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.PixelOffsetMode = PixelOffsetMode.Half;
            float u = (float)unit;
            RectangleF sight = g.VisibleClipBounds;
            sight.Inflate(2f, 2f);                       // antialiasing reaches a pixel past a shape's outline
            foreach (DayElement e in elements)
            {
                double[] n;
                double opacity;
                At(e, seconds, out n, out opacity);
                Color colour = Soft.WithAlpha(e.Colour, opacity);
                if (e.Kind == "poly")
                {
                    PointF[] points = Points(n, 0, at);
                    if (!InSight(points, sight)) continue;
                    Filled++;
                    using (var brush = new SolidBrush(colour)) g.FillPolygon(brush, points);
                }
                else if (e.Kind == "circle" || e.Kind == "ellipse")
                {
                    PointF c = at(n[0], n[1]);
                    float rx = (float)n[2] * u, ry = (e.Kind == "circle" ? (float)n[2] : (float)n[3]) * u;
                    if (!sight.IntersectsWith(new RectangleF(c.X - rx, c.Y - ry, rx * 2, ry * 2))) continue;
                    Filled++;
                    using (var brush = new SolidBrush(colour)) g.FillEllipse(brush, c.X - rx, c.Y - ry, rx * 2, ry * 2);
                }
                else if (e.Kind == "round")
                {
                    PointF one = at(n[0], n[1]), other = at(n[0] + n[2], n[1]);
                    var body = new RectangleF(Math.Min(one.X, other.X), one.Y, (float)n[2] * u, (float)n[3] * u);
                    if (!sight.IntersectsWith(body)) continue;
                    Filled++;
                    using (GraphicsPath path = Soft.Rounded(body, (float)n[4] * u))
                    using (var brush = new SolidBrush(colour)) g.FillPath(brush, path);
                }
                else if (e.Kind == "ring")
                {
                    PointF c = at(n[0], n[1]);
                    float r = (float)n[2] * u;
                    using (var pen = new Pen(colour, (float)n[3] * u)) g.DrawEllipse(pen, c.X - r, c.Y - r, r * 2, r * 2);
                }
                else if (e.Kind == "stroke")
                    using (var pen = new Pen(colour, (float)n[0] * u))
                    {
                        pen.StartCap = LineCap.Round;
                        pen.EndCap = LineCap.Round;
                        pen.LineJoin = LineJoin.Round;
                        g.DrawLines(pen, Points(n, 1, at));
                    }
                else if (e.Kind == "glow") Light(g, at(n[0], n[1]), (float)n[2] * u, (float)n[3], e.Colour, opacity);
            }
            g.Restore(state);
        }

        /// How many circles, ellipses, polygons and rounds Draw has filled (for the tests: what a clip saves).
        internal static long Filled;

        // Whether any of a polygon's outline lies in `sight`.
        private static bool InSight(PointF[] points, RectangleF sight)
        {
            if (points.Length == 0) return false;
            float left = points[0].X, right = left, top = points[0].Y, bottom = top;
            foreach (PointF p in points)
            {
                if (p.X < left) left = p.X;
                if (p.X > right) right = p.X;
                if (p.Y < top) top = p.Y;
                if (p.Y > bottom) bottom = p.Y;
            }
            return sight.IntersectsWith(RectangleF.FromLTRB(left, top, right, bottom));
        }

        private static void Light(Graphics g, PointF c, float radius, float whole, Color colour, double opacity)
        {
            using (var path = new GraphicsPath())
            {
                path.AddEllipse(c.X - radius, c.Y - radius, radius * 2, radius * 2);
                using (var brush = new PathGradientBrush(path))
                {
                    brush.CenterPoint = c;
                    brush.CenterColor = Soft.WithAlpha(colour, opacity);
                    brush.SurroundColors = new[] { Soft.WithAlpha(colour, 0) };
                    var blend = new ColorBlend(5);
                    blend.Positions[0] = 0f;
                    blend.Colors[0] = Soft.WithAlpha(colour, 0);
                    blend.Positions[1] = 1f - (whole + (1f - whole) * 0.65f);
                    blend.Colors[1] = Soft.WithAlpha(colour, opacity * 0.16);
                    blend.Positions[2] = 1f - (whole + (1f - whole) * 0.3f);
                    blend.Colors[2] = Soft.WithAlpha(colour, opacity * 0.55);
                    blend.Positions[3] = 1f - whole;
                    blend.Colors[3] = Soft.WithAlpha(colour, opacity);
                    blend.Positions[4] = 1f;
                    blend.Colors[4] = Soft.WithAlpha(colour, opacity);
                    brush.InterpolationColors = blend;
                    g.FillPath(brush, path);
                }
            }
        }

        /// The day spread wide over a card (W2, the owner's pick of 2026-11-17; popup/layout.py's day_band, in the window's
        /// pixels): the day begins brand's gap past the last word (`left`), as tall as the card from `top` to `bottom` (`unit`,
        /// the scene's to the pixel), the card's colour fading into it over at most brand's fade (`fade`). True when the scene's
        /// main piece is whole between there and `right`, where the scene's outer end stands (the caption buttons' inner edge
        /// in the Dashboard's header); false when it is not drawn - never half a scene. Whether there is a day at all is Band's.
        internal static bool Fit(string look, int wordsEnd, int cardLeft, int cardWidth, int right, int top, int bottom,
                                 out int left, out double unit, out int fade)
        {
            left = Math.Max(cardLeft, wordsEnd + Soft.Px(Brand.DayWideGap));
            unit = (bottom - top) / Brand.DaySceneHeight;
            double focal = Brand.DaySceneWidth - Brand.DayFocus(look);
            int room = (int)(right - left - Soft.Px(2) - focal * unit);
            bool scene = room >= Soft.Px(28);
            fade = Math.Max(Soft.Px(2), Math.Min(Soft.Px(Brand.DayWideFade), scene ? room : right - left - Soft.Px(2) - Soft.Px(24)));
            return scene;
        }

        /// Whether the words leave the day any room at all between `left` (Fit's) and the card's outer side `outer`: the fade's
        /// first half and a little of the day past it. popup/layout.py's day_band.
        internal static bool Band(int left, int outer)
        {
            return outer - left >= Soft.Px(Brand.DayWideFade) / 2 + Soft.Px(24);
        }
    }

    /// The day on the Dashboard's status card: its own control over the card, in what the words leave at its outer side - since
    /// v0.6.24-beta.3 (W2) all of it from past the words to the card's edge, the day's ground and specks across it and its scene
    /// as tall as the card left of the caption buttons, the card's colour fading into it past the words.
    /// A timer only while it can be seen and motion is allowed; a frame repaints this control and nothing is laid out. While
    /// battery saver or a locked session holds what moves by itself (Motion.Ambient, standard H13) it stands where it was and
    /// asks once a second whether that is over, as the status light does (HaloDot.Beat).
    internal sealed class SoftDayScene : Control
    {
        // A frame of the scene, and how often it asks while it is held still.
        private const int FrameBeat = 33, StillBeat = 1000;
        private readonly Timer timer = new Timer();
        private readonly System.Diagnostics.Stopwatch clock = System.Diagnostics.Stopwatch.StartNew();
        private string look;
        private double unit;
        private int fade;
        private int clear;                       // the room at its outer side the scene keeps clear (Keep)
        private bool scene = true;               // whether the scene is drawn, or the day's ground and specks alone (Keep)
        private DateTime day;                    // the date its look was last chosen for (Follow)

        internal SoftDayScene()
        {
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.ResizeRedraw, true);
            TabStop = false;
            timer.Interval = FrameBeat;
            timer.Tick += delegate { Beat(); };
            Visible = false;
        }

        internal string Look { get { return look; } }
        internal bool Moving { get { return timer.Enabled; } }
        internal double Unit { get { return unit; } }

        /// Whether it is held still for battery saver or a locked session: a beat a second, its clock stopped, nothing painted (for the tests).
        internal bool Stilled { get { return timer.Enabled && timer.Interval == StillBeat; } }

        private void Beat()
        {
            if (!Motion.Allowed(this))
            {
                timer.Stop();
                clockAtRest();
                Invalidate();
                return;
            }
            bool still = Motion.Ambient;
            if (still != (timer.Interval == StillBeat)) Hold(still);
            else if (!still) Invalidate();
        }

        // Held still (Motion.Ambient) or let go: the clock stops where the scene stands and goes on from there, so nothing jumps.
        private void Hold(bool still)
        {
            timer.Interval = still ? StillBeat : FrameBeat;
            if (still) clock.Stop();
            else clock.Start();
            Invalidate();
        }

        /// Asked every second by the window's clock: the look of the date, chosen again once the date has changed since it
        /// was last asked (a window left open past midnight). True when it is another look than `current`, which it then is.
        internal bool Follow(ref string current)
        {
            DateTime today = DayArt.Clock().Date;
            if (today == day) return false;
            day = today;
            string now = Palette.AccentBar ? null : DayArt.Today();
            if (now == current) return false;
            current = now;
            return true;
        }

        private void clockAtRest() { clock.Reset(); }

        /// W2: the room at its outer side the scene keeps clear (the caption buttons' in the Dashboard's header, which stand
        /// over the day's ground and specks), and whether the scene is drawn at all (DayArt.Fit) - before Place.
        internal void Keep(int room, bool drawn)
        {
            if (room == clear && drawn == scene) return;
            clear = room;
            scene = drawn;
            Invalidate();
        }

        /// Whether the scene itself is drawn, past the day's ground and specks (for the tests).
        internal bool SceneDrawn { get { return scene; } }

        /// Stands it where `left` to `right` of its parent says, or hides it (`on` false).
        internal void Place(bool on, string day, int left, int top, int width, int height, double size, int faded)
        {
            look = on ? day : null;
            if (!on)
            {
                if (Visible) Visible = false;
                Sync();
                return;
            }
            var bounds = new Rectangle(left, top, width, height);
            if (Bounds != bounds || size != unit || faded != fade)
            {
                unit = size;
                fade = faded;
                Bounds = bounds;
                Rounding();
                Invalidate();
            }
            if (!Visible) Visible = true;
            Sync();
        }

        private void Rounding()
        {
            int radius = 2 * Math.Max(1, Soft.Px(Palette.RadiusCard) - Soft.Hairline);
            bool mirrored = Mirror.Of(this);
            // v0.6.24: the card's outer two corners as the card draws them - the squircle (Shape) where the design
            // smooths its corners, still a Region; the arcs below where it does not.
            double smoothing = Shape.Smoothing;
            if (Shape.Of(radius / 2.0, smoothing, Math.Min(Width, Height) / 2.0).Smoothed)
            {
                Shape.Corners outer = mirrored ? Shape.Corners.TopLeft | Shape.Corners.BottomLeft
                                               : Shape.Corners.TopRight | Shape.Corners.BottomRight;
                using (GraphicsPath squircle = Shape.Squircle(new RectangleF(0, 0, Width, Height), radius / 2f, smoothing, outer))
                    Region = new Region(squircle);
                return;
            }
            using (var path = new GraphicsPath())
            {
                int w = Width, h = Height;
                if (mirrored)
                {
                    path.AddArc(0, 0, radius, radius, 180, 90);
                    path.AddLine(radius / 2, 0, w, 0);
                    path.AddLine(w, 0, w, h);
                    path.AddLine(w, h, radius / 2, h);
                    path.AddArc(0, h - radius, radius, radius, 90, 90);
                }
                else
                {
                    path.AddLine(0, 0, w - radius / 2, 0);
                    path.AddArc(w - radius, 0, radius, radius, 270, 90);
                    path.AddArc(w - radius, h - radius, radius, radius, 0, 90);
                    path.AddLine(w - radius / 2, h, 0, h);
                }
                path.CloseFigure();
                Region = new Region(path);
            }
        }

        /// Timer on only while there is something to see move.
        internal void Sync()
        {
            bool wanted = look != null && Motion.Allowed(this);
            if (wanted && !timer.Enabled)
            {
                bool still = Motion.Ambient;
                timer.Interval = still ? StillBeat : FrameBeat;
                if (still) clock.Stop();
                else clock.Start();
                timer.Start();
            }
            else if (!wanted && timer.Enabled) timer.Stop();
        }

        protected override void OnVisibleChanged(EventArgs e) { base.OnVisibleChanged(e); Sync(); }
        protected override void OnHandleCreated(EventArgs e) { base.OnHandleCreated(e); Sync(); }

        protected override void OnPaint(PaintEventArgs e)
        {
            if (look == null) return;
            Graphics g = e.Graphics;
            string name, top, bottom;
            Brand.DayGround(look, out name, out top, out bottom);
            g.Clear(ColorTranslator.FromHtml(name));
            bool mirrored = Mirror.Of(this);
            double seconds = timer.Enabled ? clock.Elapsed.TotalSeconds : 0.0;
            double u = unit, width = Width, origin = Brand.DayFromTop(look) ? 0.0 : Height - Brand.DaySceneHeight * u;
            // W2: the day's specks across all of it, band after band from its outer side (brand.speck_elements), under
            // the caption buttons too; then the scene, its outer end where the buttons' room ends (Keep).
            DayElement[] specks = DayArt.Parse(Brand.DaySpecks(look));
            double band = Brand.DaySpeckBand * u;
            for (double offset = 0; offset < width && band > 0; offset += band)
            {
                double at = offset;
                DayArt.Draw(g, specks, seconds, u, delegate(double x, double y)
                {
                    return new PointF((float)(mirrored ? at + (Brand.DaySpeckBand - x) * u : width - at - (Brand.DaySpeckBand - x) * u), (float)(y * u));
                });
            }
            double end = clear;
            if (scene)
                DayArt.Draw(g, DayArt.Parse(Brand.DayScene(look)), seconds, u, delegate(double x, double y)
                {
                    return new PointF((float)(mirrored ? end + (Brand.DaySceneWidth - x) * u : width - end - (Brand.DaySceneWidth - x) * u), (float)(origin + y * u));
                });
            Color card = Parent != null ? Palette.Card : Palette.Card;
            int solid = Soft.Px(2);
            int from = mirrored ? Width - solid : solid, to = mirrored ? Width - solid - fade : solid + fade;
            g.FillRectangle(Soft.Fill(card), mirrored ? Width - solid : 0, 0, solid, Height);
            using (var brush = new LinearGradientBrush(new Point(from, 0), new Point(to, 0), card, Color.FromArgb(0, card)))
            {
                brush.WrapMode = WrapMode.TileFlipXY;
                g.FillRectangle(brush, Math.Min(from, to), 0, fade, Height);
            }
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) timer.Dispose();
            base.Dispose(disposing);
        }
    }

    /// The Dashboard's ground on a special day (W2, the owner's pick of 2026-11-17): the window's canvas takes brand's tint of the
    /// day's ground (Palette.Canvas, before anything is made in it), and every ground of that window shows the day's specks
    /// where they fall in the window, faint and still, behind the cards - painted with the ground (Ground.Paint), so they
    /// cost nothing a frame. The cards keep their own colour, so the pages read as always. Never in a picture, a probe or an
    /// audit without its own date (DayArt.Today), nor in High Contrast or Classic.
    internal static class DayGround
    {
        // How much of each speck's own opacity a speck on the ground keeps: it lies behind the words of the tabs and pages.
        private const double FaintShare = 0.45;
        private static readonly Dictionary<string, DayElement[]> faint = new Dictionary<string, DayElement[]>();
        private static WeakReference owner;

        /// The day the window's ground is in, or null.
        internal static string Look;

        /// The specks' unit, the scene's to the pixel: as on the header card, so a speck is the same size on both.
        internal static double Unit = 1.0;

        /// The window's ground in `look`'s tint, or as the palette has it on any other day; `window` the one window whose
        /// grounds show its specks.
        internal static void Adopt(string look, Form window)
        {
            Look = look;
            owner = look == null ? null : new WeakReference(window);
            Palette.Canvas = look == null ? Untinted : Tinted(Untinted, look);
            Unit = Soft.PxF(Brand.DaySceneHeight) / Brand.DaySceneHeight * 1.2;
        }

        /// The window's ground on any other day: the palette's canvas.
        internal static Color Untinted { get { return Palette.Contrast ? SystemColors.Control : Tokens.Canvas; } }

        /// `canvas` with brand's tint of `look`'s ground in it - or less of it, as much as leaves the words on the ground (the
        /// palette's ink, its secondary words and its accent) at WCAG's 4.5:1, or where one was below that on any other day,
        /// no lower than it was. A dark day's ground took a light window's secondary words to 4.3:1 at the whole tint.
        internal static Color Tinted(Color canvas, string look)
        {
            string ground, top, bottom;
            Brand.DayGround(look, out ground, out top, out bottom);
            if (ground == null) return canvas;
            Color day = ColorTranslator.FromHtml(ground);
            for (double share = Brand.DayGroundTint; share > 0.0; share -= 0.005)
            {
                Color tinted = Soft.Mix(canvas, day, share);
                if (Readable(Palette.Ink, canvas, tinted) && Readable(Palette.Muted, canvas, tinted) && Readable(Palette.Accent, canvas, tinted))
                    return tinted;
            }
            return canvas;
        }

        // Whether words in `words` stand out from `tinted` as WCAG asks (4.5:1), or as much as they did from `canvas`.
        private static bool Readable(Color words, Color canvas, Color tinted)
        {
            return Chrome.Contrast(words, tinted) >= Math.Min(4.5, Chrome.Contrast(words, canvas));
        }

        /// Every control of `window` in the ground's old colour `from` takes the new `to` (a window left open past midnight).
        internal static void Repaint(Control window, Color from, Color to)
        {
            var walk = new Stack<Control>();
            walk.Push(window);
            while (walk.Count > 0)
            {
                Control control = walk.Pop();
                if (control.BackColor.ToArgb() == from.ToArgb()) control.BackColor = to;
                foreach (Control child in control.Controls) walk.Push(child);
            }
            window.Invalidate(true);
        }

        private static DayElement[] Faint(string look)
        {
            DayElement[] found;
            if (faint.TryGetValue(look, out found)) return found;
            // The moving ones alone: what stands still in the band (seollal's stripes) belongs to a card's header, not to a ground.
            var moving = new List<DayElement>();
            foreach (DayElement one in DayArt.Parse(Brand.DaySpecks(look)))
                if (!string.IsNullOrEmpty(one.Motion))
                    moving.Add(new DayElement { Kind = one.Kind, Numbers = one.Numbers, Colour = one.Colour,
                                                Opacity = one.Opacity * FaintShare, Motion = one.Motion, Values = one.Values });
            found = moving.ToArray();
            faint[look] = found;
            return found;
        }

        /// The day's specks on `ground`'s background where they fall in its window, within `clip`: only on the window's own
        /// ground (the tinted canvas), never on a card.
        internal static void Paint(Control ground, Graphics g, Rectangle clip)
        {
            if (Look == null || owner == null || Palette.Contrast) return;
            if (Ground.Colour(ground).ToArgb() != Palette.Canvas.ToArgb()) return;
            Point at = Point.Empty;
            Control c = ground;
            for (; c != null && !(c is Form); c = c.Parent) at.Offset(c.Left, c.Top);
            if (c == null || !ReferenceEquals(c, owner.Target)) return;
            double u = Unit, wide = Brand.DaySpeckBand * u, tall = Brand.DaySceneHeight * u;
            if (wide <= 0 || tall <= 0) return;
            DayElement[] specks = Faint(Look);
            Rectangle shown = new Rectangle(clip.X + at.X, clip.Y + at.Y, clip.Width, clip.Height);
            int firstColumn = (int)Math.Floor((shown.Left - 8 * u) / wide), lastColumn = (int)Math.Floor((shown.Right + 8 * u) / wide);
            int firstRow = (int)Math.Floor((shown.Top - 8 * u) / tall), lastRow = (int)Math.Floor((shown.Bottom + 8 * u) / tall);
            GraphicsState state = g.Save();
            g.SetClip(clip, CombineMode.Intersect);
            for (int row = Math.Max(0, firstRow); row <= lastRow; row++)
                for (int column = Math.Max(0, firstColumn); column <= lastColumn; column++)
                {
                    double x0 = column * wide - at.X, y0 = row * tall - at.Y;
                    // Each row a half band along from the one above, so the specks do not stand in columns.
                    if (row % 2 == 1) x0 -= wide / 2;
                    DayArt.Draw(g, specks, 0.0, u, delegate(double x, double y) { return new PointF((float)(x0 + x * u), (float)(y0 + y * u)); });
                    if (row % 2 == 1 && column == lastColumn)
                        DayArt.Draw(g, specks, 0.0, u, delegate(double x, double y) { return new PointF((float)(x0 + wide + x * u), (float)(y0 + y * u)); });
                }
            g.Restore(state);
        }
    }

    /// The Dashboard's icon on a special day: the day's body under the mark's ring, the head left as it is, the small mark from 24 px up.
    internal static class DayIcon
    {
        private static double Part(int y, int size) { return (y + 0.5) / size; }

        private static int Mix(int from, int to, double part) { return (int)Math.Round(from + (to - from) * part); }

        /// The pixel (r, g, b), part of the plain badge at height `y`, as it is on the day's body: how much of it is ring is
        /// read off the channel where ring and body differ most. False for what is neither ring nor body (the head).
        internal static bool Turn(int size, int y, Color top, Color bottom, ref int r, ref int g, ref int b)
        {
            double part = Part(y, size);
            Color plainTop = Brand.IconTopColour(), plainBottom = Brand.IconBottomColour(), mark = Brand.IconMarkColour();
            int br = Mix(plainTop.R, plainBottom.R, part), bg = Mix(plainTop.G, plainBottom.G, part), bb = Mix(plainTop.B, plainBottom.B, part);
            double k = Math.Max(0.0, Math.Min(1.0, (r - br) / (double)(mark.R - br)));
            if (Math.Abs(g - (bg + (mark.G - bg) * k)) + Math.Abs(b - (bb + (mark.B - bb) * k)) > 28) return false;
            r = Mix(Mix(top.R, bottom.R, part), mark.R, k);
            g = Mix(Mix(top.G, bottom.G, part), mark.G, k);
            b = Mix(Mix(top.B, bottom.B, part), mark.B, k);
            return true;
        }

        /// The day's mark as this many pixels (top-down BGRA over nothing), or null below the size it shows from.
        internal static byte[] Mark(string look, int size)
        {
            if (size < Brand.DayMarkLeast) return null;
            using (var bitmap = new Bitmap(size, size, System.Drawing.Imaging.PixelFormat.Format32bppArgb))
            {
                using (Graphics g = Graphics.FromImage(bitmap))
                {
                    g.Clear(Color.Transparent);
                    double unit = size / 32.0;
                    DayArt.Draw(g, DayArt.Parse(Brand.DayMark(look)), 0.0, unit, delegate(double x, double y) { return new PointF((float)(x * unit), (float)(y * unit)); });
                }
                var pixels = new byte[size * size * 4];
                for (int y = 0; y < size; y++)
                    for (int x = 0; x < size; x++)
                    {
                        Color c = bitmap.GetPixel(x, y);
                        int at = (y * size + x) * 4;
                        pixels[at] = c.B;
                        pixels[at + 1] = c.G;
                        pixels[at + 2] = c.R;
                        pixels[at + 3] = c.A;
                    }
                return pixels;
            }
        }

        /// `mark` over the frame's pixel `at`, where the frame has one.
        internal static void Lay(byte[] frame, int at, byte[] mark)
        {
            if (mark == null || frame[at + 3] == 0 || mark[at + 3] == 0) return;
            int a = mark[at + 3];
            for (int channel = 0; channel < 3; channel++) frame[at + channel] = (byte)((frame[at + channel] * (255 - a) + mark[at + channel] * a) / 255);
        }

        /// The window's icon of `size` as the day's: its pixels turned, the head left, the mark on.
        internal static IntPtr From(Icon icon, int size, string look)
        {
            string name, top, bottom;
            Brand.DayGround(look, out name, out top, out bottom);
            Color from = ColorTranslator.FromHtml(top), to = ColorTranslator.FromHtml(bottom);
            byte[] mark = Mark(look, size);
            using (var sized = new Icon(icon, size, size))
            using (Bitmap bitmap = sized.ToBitmap())
            {
                int side = Math.Min(size, Math.Min(bitmap.Width, bitmap.Height));
                var pixels = new byte[size * size * 4];
                for (int y = 0; y < side; y++)
                    for (int x = 0; x < side; x++)
                    {
                        Color c = bitmap.GetPixel(x, y);
                        int r = c.R, g = c.G, b = c.B, at = (y * size + x) * 4;
                        bool body = c.A != 0 && Turn(size, y, from, to, ref r, ref g, ref b);
                        pixels[at] = (byte)b;
                        pixels[at + 1] = (byte)g;
                        pixels[at + 2] = (byte)r;
                        pixels[at + 3] = c.A;
                        if (body) Lay(pixels, at, mark);
                    }
                return MarkFrames.IconFrom(pixels, size);
            }
        }
    }
}
