// Codex Auto Resume - the version's easter eggs (v0.6.24-beta.2, the owner, 2026-11-16): the run of presses that plays a
// special one at the sixth (PressRun), which of the three (EggPick), and the confetti - its pieces (ConfettiBurst) and the
// layered window they fall in, over the Dashboard and never outside it (ConfettiLayer). One press is the light's sweep and
// the sentence (SettingsForm.VersionPressed); the light's colours are its own (HaloDot.RunColours).

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace CodexAutoResume
{
    /// v0.6.24-beta.2 (the owner, 2026-11-16, "여러번 누를때의 이스터에그도 별도로 만들자", "6번"): presses on the version one
    /// after another - six, each within 1.8 s of the last - say so once, and it starts again. One press is the easter egg as
    /// it always is (SettingsForm.VersionPressed); the sixth plays one of the special ones instead (EggPick).
    internal sealed class PressRun
    {
        internal const int Wanted = 6;
        internal const double Gap = 1800.0;

        private double last = double.NegativeInfinity;
        private int count;

        /// Whether the press just counted began a run (the one-press egg plays at it, and at no other press of the run).
        internal bool First { get; private set; }

        internal bool Press(double milliseconds)
        {
            count = milliseconds - last <= Gap ? count + 1 : 1;
            last = milliseconds;
            First = count == 1;
            if (count < Wanted) return false;
            count = 0;
            return true;
        }
    }

    /// Which special egg the sixth press plays (the owner, 2026-11-16, "3개 중 하나가 랜덤으로 뜨게 하자" - one of the three
    /// at random): the light through all its colours, the count of what it has picked up, or confetti - never the same one
    /// twice in a row. `Next(n)` is the random source, a number from 0 to n - 1; the tests give their own.
    internal sealed class EggPick
    {
        internal const int Colours = 0, Count = 1, Confetti = 2, Kinds = 3;
        private int last = -1;
        internal Func<int, int> Next = new Random().Next;

        internal int Pick()
        {
            int chosen = last < 0 ? Next(Kinds) : (last + 1 + Next(Kinds - 1)) % Kinds;
            last = chosen;
            return chosen;
        }
    }

    /// The confetti egg's pieces (v0.6.24-beta.2): a small burst from a point - the version's pill - that rises, spins and falls,
    /// and fades in its last part, all within LengthMs. Pure, so the tests can ask where each piece is at any moment; drawn by
    /// ConfettiLayer.
    internal sealed class ConfettiBurst : IEggPainting
    {
        internal const int Pieces = 36, LengthMs = 1200;
        private const double FadeFrom = 0.7;
        private readonly double[] x0, y0, vx, vy, spin, turn, width, height;
        private readonly Color[] colour;
        private readonly double gravity;

        internal ConfettiBurst(Random random, PointF from, float unit, Color[] colours)
        {
            x0 = new double[Pieces]; y0 = new double[Pieces]; vx = new double[Pieces]; vy = new double[Pieces];
            spin = new double[Pieces]; turn = new double[Pieces]; width = new double[Pieces]; height = new double[Pieces];
            colour = new Color[Pieces];
            gravity = 0.0009 * unit;
            for (int i = 0; i < Pieces; i++)
            {
                x0[i] = from.X;
                y0[i] = from.Y;
                vx[i] = (random.NextDouble() * 2.0 - 1.0) * 0.2 * unit;
                vy[i] = -(0.15 + random.NextDouble() * 0.3) * unit;
                spin[i] = random.NextDouble() * 180.0;
                turn[i] = (random.NextDouble() * 2.0 - 1.0) * 0.6;
                width[i] = (4.0 + random.NextDouble() * 3.0) * unit;
                height[i] = (2.5 + random.NextDouble() * 1.5) * unit;
                colour[i] = colours[i % colours.Length];
            }
        }

        /// The brand's colours, in the theme in effect: the light's cyan, amber and red, and the mark's head.
        internal static Color[] Colours()
        {
            return new[] { HaloDot.DotColour("monitoring", false), HaloDot.DotColour("attention", false),
                           HaloDot.DotColour("failed", false), Brand.IconHead() };
        }

        /// Where piece `i` is `ms` after the burst, and how opaque.
        internal PointF At(int i, double ms, out double opacity)
        {
            double t = Math.Max(0.0, ms) / LengthMs;
            opacity = t >= 1.0 ? 0.0 : t <= FadeFrom ? 1.0 : 1.0 - (t - FadeFrom) / (1.0 - FadeFrom);
            return new PointF((float)(x0[i] + vx[i] * ms), (float)(y0[i] + vy[i] * ms + 0.5 * gravity * ms * ms));
        }

        internal Color ColourOf(int i) { return colour[i]; }

        int IEggPainting.Length { get { return LengthMs; } }
        void IEggPainting.Paint(Graphics g, double ms) { Paint(g, ms); }

        internal void Paint(Graphics g, double ms)
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            for (int i = 0; i < Pieces; i++)
            {
                double opacity;
                PointF at = At(i, ms, out opacity);
                if (opacity <= 0.0) continue;
                GraphicsState saved = g.Save();
                g.TranslateTransform(at.X, at.Y);
                g.RotateTransform((float)(spin[i] + turn[i] * ms));
                using (var brush = new SolidBrush(Soft.WithAlpha(colour[i], opacity)))
                    g.FillRectangle(brush, (float)(-width[i] / 2), (float)(-height[i] / 2), (float)width[i], (float)height[i]);
                g.Restore(saved);
            }
        }
    }

    /// What a layered egg draws (v0.6.24): its picture `ms` in, on a clear ground, for Length milliseconds - the confetti
    /// (ConfettiBurst) or a special day's own egg (DayEgg). Pure: the same picture at the same moment.
    internal interface IEggPainting
    {
        int Length { get; }
        void Paint(Graphics g, double ms);
    }

    /// The confetti on the screen: a layered window of its own over a part of the Dashboard's client area, owned by it, that
    /// takes no input (clicks and the pointer go through to the window under it) and is never activated, never on top of
    /// another program's window and never outside the Dashboard's client area - it follows the window if it moves. Gone when
    /// the burst ends, when the window goes, or when another burst replaces it (Dispose).
    internal sealed class ConfettiLayer : NativeWindow, IDisposable
    {
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern bool ShowWindow(IntPtr window, int command);

        private const int WS_POPUP = unchecked((int)0x80000000);
        // Layered, transparent to the pointer, a tool window, never activated - and not topmost.
        internal const int ExStyle = 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000;
        private const int SW_SHOWNOACTIVATE = 4;

        private readonly Form owner;
        private readonly Point offset;
        private readonly Size size;
        private readonly IEggPainting burst;
        private readonly Timer timer = new Timer();
        private readonly Stopwatch clock = new Stopwatch();
        private IntPtr dib, memory, previous;

        /// `area` in the owner's client coordinates, within its client area.
        internal ConfettiLayer(Form owner, Rectangle area, IEggPainting burst)
        {
            this.owner = owner;
            offset = area.Location;
            size = area.Size;
            this.burst = burst;
            timer.Interval = Motion.Interval;
            timer.Tick += delegate { Frame(); };
        }

        internal bool Running { get { return timer.Enabled; } }

        internal void Start()
        {
            var cp = new CreateParams();
            cp.Caption = "";
            Point at = owner.PointToScreen(offset);
            cp.X = at.X;
            cp.Y = at.Y;
            cp.Width = size.Width;
            cp.Height = size.Height;
            cp.Style = WS_POPUP;
            cp.ExStyle = ExStyle;
            cp.Parent = owner.Handle;
            CreateHandle(cp);
            clock.Start();
            Frame();
            if (Handle == IntPtr.Zero) return;
            ShowWindow(Handle, SW_SHOWNOACTIVATE);
            timer.Start();
        }

        private void Frame()
        {
            double ms = clock.Elapsed.TotalMilliseconds;
            if (ms >= burst.Length || owner.IsDisposed || !owner.Visible || owner.WindowState == FormWindowState.Minimized)
            {
                Dispose();
                return;
            }
            using (var image = new Bitmap(size.Width, size.Height, System.Drawing.Imaging.PixelFormat.Format32bppPArgb))
            {
                using (Graphics g = Graphics.FromImage(image))
                {
                    // Nothing but the pieces: every other pixel of the layer clear, so the window under it shows. A layered
                    // window's own picture, not a control's background, so nothing here is see-through (test_gui_layout).
                    g.Clear(Color.Transparent);
                    burst.Paint(g, ms);
                }
                IntPtr oldMemory = memory, oldDib = dib, oldPrevious = previous;
                LayerBits.Upload(image, out dib, out memory, out previous);
                Point at = owner.PointToScreen(offset);
                if (Handle != IntPtr.Zero && memory != IntPtr.Zero) LayerBits.Lay(Handle, memory, at.X, at.Y, size.Width, size.Height, 255);
                LayerBits.Release(oldMemory, oldDib, oldPrevious);
            }
        }

        public void Dispose()
        {
            timer.Stop();
            timer.Dispose();
            if (Handle != IntPtr.Zero) DestroyHandle();
            LayerBits.Release(memory, dib, previous);
            memory = dib = previous = IntPtr.Zero;
        }
    }

    /// v0.6.24 (the owner, 2026-11-17/18, the Special board): a special day's own egg at the sixth press, in place of the three
    /// ordinary ones - from the version's pill, about 2.6 s, in the day's colours (Brand.DayEggColour), its parts fading out
    /// in the last 0.4 s:
    ///   new year - fireworks rise from the pill and burst, then stars twinkle;
    ///   seollal - the lucky pouch swings and coins drop, then the stripes ripple;
    ///   birthday - a candle grows on the cake, is blown out with a wisp of smoke, and confetti bursts;
    ///   chuseok - the full moon rises and glows, a rabbit's shadow on it, songpyeon below;
    ///   christmas - heavy snow, the tree's lights red and green, the snow piling at its foot.
    /// Pure: where every part is at any moment is a function of the moment, the pill's centre `from` in the layer, the unit
    /// (a pixel at 100 %) and which way the window lies from the pill (`inward`: -1 when the pill is at the window's right
    /// end, 1 mirrored). Drawn by ConfettiLayer, which takes no input and stays inside the window.
    internal sealed class DayEgg : IEggPainting
    {
        internal const int LengthMs = 2700, FadeMs = 400;
        private readonly string look;
        private readonly PointF from;
        private readonly float unit;
        private readonly int inward;
        private readonly ConfettiBurst cake;
        private readonly double[] flakes;

        internal DayEgg(string look, PointF from, float unit, int inward)
        {
            this.look = look;
            this.from = from;
            this.unit = unit;
            this.inward = inward < 0 ? -1 : 1;
            if (look == "birthday")
            {
                var colours = new Color[5];
                for (int i = 0; i < 5; i++) colours[i] = Brand.DayEggColour(look, "confetti" + i);
                cake = new ConfettiBurst(new Random(906), Candle(), unit * 0.75f, colours);
            }
            if (look == "christmas")
            {
                // 70 flakes: across, how far above the top, speed, size and the phase of their sway - the same every time.
                var random = new Random(1225);
                flakes = new double[70 * 5];
                for (int i = 0; i < flakes.Length; i++) flakes[i] = random.NextDouble();
            }
        }

        internal string Look { get { return look; } }
        int IEggPainting.Length { get { return LengthMs; } }

        private static double Clamp(double t) { return t < 0 ? 0 : t > 1 ? 1 : t; }
        private static double Ease(double t) { return Motion.Ease(Clamp(t)); }

        /// How much of the egg shows at `ms`: whole until the last FadeMs, gone at LengthMs.
        internal static double Shown(double ms)
        {
            if (ms < 0 || ms >= LengthMs) return 0.0;
            return ms <= LengthMs - FadeMs ? 1.0 : 1.0 - (ms - (LengthMs - FadeMs)) / FadeMs;
        }

        private PointF At(double dx, double dy) { return new PointF((float)(from.X + inward * dx * unit), (float)(from.Y + dy * unit)); }
        private float U(double size) { return (float)(size * unit); }

        private Color C(string part, double opacity) { return Soft.WithAlpha(Brand.DayEggColour(look, part), opacity); }

        private void Dot(Graphics g, PointF at, double radius, Color colour)
        {
            float r = U(radius);
            using (var brush = new SolidBrush(colour)) g.FillEllipse(brush, at.X - r, at.Y - r, 2 * r, 2 * r);
        }

        private static void Star(Graphics g, PointF at, float size, Color colour)
        {
            float w = size * 0.24f;
            var points = new[] { new PointF(at.X, at.Y - size), new PointF(at.X + w, at.Y - w), new PointF(at.X + size, at.Y),
                                 new PointF(at.X + w, at.Y + w), new PointF(at.X, at.Y + size), new PointF(at.X - w, at.Y + w),
                                 new PointF(at.X - size, at.Y), new PointF(at.X - w, at.Y - w) };
            using (var brush = new SolidBrush(colour)) g.FillPolygon(brush, points);
        }

        public void Paint(Graphics g, double ms)
        {
            double shown = Shown(ms);
            if (shown <= 0) return;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            if (look == "new_year") NewYear(g, ms, shown);
            else if (look == "seollal") Seollal(g, ms, shown);
            else if (look == "birthday") Birthday(g, ms, shown);
            else if (look == "chuseok") Chuseok(g, ms, shown);
            else if (look == "christmas") Christmas(g, ms, shown);
        }

        // ---------------------------------------------------------------- new year
        // The three rockets' bursts and starts, as comparisons rather than arrays: the in-box compiler keeps a constant
        // array's values in a class it names with a fresh random GUID, which build/normalize_pe.py refuses (the setup
        // program compiles this file too).
        private static double RocketX(int k) { return k == 0 ? 64 : k == 1 ? 138 : 208; }
        private static double RocketY(int k) { return k == 0 ? -62 : k == 1 ? -82 : -54; }
        private static double RocketAt(int k) { return k * 160; }
        private const double RiseMs = 620, BurstMs = 900;

        private void NewYear(Graphics g, double ms, double shown)
        {
            for (int k = 0; k < 3; k++)
            {
                double since = ms - RocketAt(k);
                if (since < 0) continue;
                if (since < RiseMs)
                {
                    // Rising from the pill, a short trail behind its head.
                    for (int trail = 4; trail >= 0; trail--)
                    {
                        double p = Ease((since - trail * 30) / RiseMs);
                        if (since - trail * 30 < 0) continue;
                        Dot(g, At(RocketX(k) * p, RocketY(k) * p), 2.2 - trail * 0.35, C("trail", shown * (1.0 - trail * 0.18)));
                    }
                    continue;
                }
                double burst = (since - RiseMs) / BurstMs;
                if (burst >= 1) continue;
                double spread = 1.0 - Math.Pow(1.0 - burst, 3), sag = 12 * burst * burst;
                for (int i = 0; i < 14; i++)
                {
                    double angle = 2 * Math.PI * i / 14 + k * 0.4;
                    var at = At(RocketX(k) + 40 * spread * Math.Cos(angle), RocketY(k) + 40 * spread * Math.Sin(angle) + sag);
                    Dot(g, at, 2.3 - 1.4 * burst, C("spark" + ((i + k) % 4), shown * (1.0 - burst)));
                }
            }
            // Then the stars, twinkling where the bursts were.
            for (int i = 0; i < 9; i++)
            {
                double since = ms - 1150 - i * 70;
                if (since < 0) continue;
                double level = (1 - Math.Cos(2 * Math.PI * since / 620.0 + i)) / 2;
                double x = 40 + (i * 37) % 200, y = -40 - (i * 29) % 78;
                Star(g, At(x, y), U(3.2 + 1.6 * level), C("star", shown * Clamp(since / 200) * (0.35 + 0.65 * level)));
            }
        }

        // ---------------------------------------------------------------- seollal
        private void Seollal(Graphics g, double ms, double shown)
        {
            PointF knot = At(92, 22);
            // The pouch swings about its knot, wide at first and settling.
            double swing = 16 * Math.Sin(2 * Math.PI * ms / 720.0) * Math.Exp(-ms / 1500.0);
            GraphicsState saved = g.Save();
            g.TranslateTransform(knot.X, knot.Y);
            g.RotateTransform((float)swing);
            using (var body = new GraphicsPath())
            {
                body.AddBezier(U(-8), U(4), U(-26), U(14), U(-24), U(40), U(0), U(40));
                body.AddBezier(U(0), U(40), U(24), U(40), U(26), U(14), U(8), U(4));
                body.CloseFigure();
                using (var brush = new SolidBrush(C("pouch", shown))) g.FillPath(brush, body);
            }
            using (var brush = new SolidBrush(C("mouth", shown))) g.FillEllipse(brush, U(-11), U(-2), U(22), U(9));
            using (var brush = new SolidBrush(C("band", shown))) g.FillRectangle(brush, U(-10), U(3), U(20), U(3.4));
            using (var brush = new SolidBrush(C("knot", shown))) g.FillEllipse(brush, U(-3.4), U(-3.4), U(6.8), U(6.8));
            g.Restore(saved);
            // Coins from its mouth, one after another, spinning as they fall.
            for (int i = 0; i < 7; i++)
            {
                double since = ms - 380 - i * 120;
                if (since < 0 || since > 1300) continue;
                double side = (i % 2 == 0 ? 1 : -1) * (6 + 4 * i);
                double x = 92 + side * since / 1300.0, y = 30 - 0.05 * since + 0.00022 * since * since;
                PointF at = At(x, y);
                float r = U(5.2), squeeze = (float)Math.Abs(Math.Cos(since / 160.0 + i));
                using (var coin = new GraphicsPath(FillMode.Alternate))
                {
                    coin.AddEllipse(at.X - r * squeeze, at.Y - r, 2 * r * squeeze, 2 * r);
                    float hole = r * 0.36f;
                    coin.AddRectangle(new RectangleF(at.X - hole * squeeze, at.Y - hole, 2 * hole * squeeze, 2 * hole));
                    using (var brush = new SolidBrush(C("coin", shown * (1 - Clamp((since - 1000) / 300))))) g.FillPath(brush, coin);
                }
            }
            // Then the stripes, rippling under it.
            double ripple = Clamp((ms - 1100) / 300);
            if (ripple <= 0) return;
            for (int band = 0; band < 5; band++)
            {
                var points = new List<PointF>();
                for (double x = 20; x <= 250; x += 6)
                    points.Add(At(x, 74 + band * 4.2 + 3.5 * Math.Sin(2 * Math.PI * (x / 64.0 - (ms - 1100) / 640.0))));
                for (double x = 250; x >= 20; x -= 6)
                    points.Add(At(x, 78.2 + band * 4.2 + 3.5 * Math.Sin(2 * Math.PI * (x / 64.0 - (ms - 1100) / 640.0))));
                using (var brush = new SolidBrush(C("stripe" + band, shown * ripple))) g.FillPolygon(brush, points.ToArray());
            }
        }

        // ---------------------------------------------------------------- birthday
        private PointF Candle() { return At(64, 38); }

        private void Birthday(Graphics g, double ms, double shown)
        {
            PointF cakeTop = At(64, 46);
            float width = U(56), height = U(26);
            var body = new RectangleF(cakeTop.X - width / 2, cakeTop.Y, width, height);
            using (GraphicsPath shape = Soft.Rounded(Rectangle.Round(body), U(5)))
            {
                using (var brush = new SolidBrush(C("cake", shown))) g.FillPath(brush, shape);
                using (var pen = new Pen(C("edge", shown), U(1.2))) g.DrawPath(pen, shape);
            }
            using (var frosting = new GraphicsPath())
            {
                frosting.AddLine(body.Left, body.Top + U(3), body.Left, body.Top + U(7));
                for (int i = 0; i < 4; i++)
                    frosting.AddBezier(body.Left + i * width / 4, body.Top + U(7), body.Left + (i + 0.25f) * width / 4, body.Top + U(12),
                                       body.Left + (i + 0.75f) * width / 4, body.Top + U(12), body.Left + (i + 1) * width / 4, body.Top + U(7));
                frosting.AddLine(body.Right, body.Top + U(7), body.Right, body.Top + U(3));
                frosting.AddLine(body.Right, body.Top + U(3), body.Left, body.Top + U(3));
                using (var brush = new SolidBrush(C("frosting", shown))) g.FillPath(brush, frosting);
            }
            // The candle grows, and its flame flickers until it is blown out at 1.3 s.
            double tall = 18 * Ease(ms / 600.0);
            PointF wick = new PointF(cakeTop.X, cakeTop.Y + U(3) - U(tall));
            using (var brush = new SolidBrush(C("candle", shown))) g.FillRectangle(brush, wick.X - U(2), wick.Y, U(4), U(tall));
            double flame = ms < 300 ? 0 : ms < 1300 ? Clamp((ms - 300) / 200) * (1 + 0.15 * Math.Sin(ms / 45.0)) : 1 - Clamp((ms - 1300) / 160);
            if (flame > 0)
            {
                float lean = ms > 1300 ? (float)(-inward * U(4) * Clamp((ms - 1300) / 160)) : 0f;
                float fw = U(3.2 * flame), fh = U(6 * flame);
                using (var brush = new SolidBrush(C("flame", shown))) g.FillEllipse(brush, wick.X - fw / 2 + lean, wick.Y - fh - U(1), fw, fh);
            }
            // A wisp of smoke where it was.
            for (int i = 0; i < 4; i++)
            {
                double since = ms - 1330 - i * 110;
                if (since < 0 || since > 800) continue;
                double rise = since / 800.0;
                var at = new PointF(wick.X + U(3 * Math.Sin(since / 120.0 + i)), wick.Y - U(4 + 26 * rise));
                float r = U(2 + 3 * rise);
                using (var brush = new SolidBrush(C("smoke", shown * 0.6 * (1 - rise)))) g.FillEllipse(brush, at.X - r, at.Y - r, 2 * r, 2 * r);
            }
            // Then the confetti, from the candle.
            if (cake != null && ms >= 1450) cake.Paint(g, ms - 1450);
        }

        // ---------------------------------------------------------------- chuseok
        private void Chuseok(Graphics g, double ms, double shown)
        {
            double rise = Ease(ms / 1000.0);
            PointF moon = At(124, 70 - 128 * rise);
            float r = U(26);
            // Its glow, coming in as it stands and breathing.
            double glow = Clamp((ms - 700) / 500) * (0.75 + 0.25 * Math.Sin(ms / 260.0));
            if (glow > 0)
                using (var halo = new GraphicsPath())
                {
                    float reach = r * 1.9f;
                    halo.AddEllipse(moon.X - reach, moon.Y - reach, 2 * reach, 2 * reach);
                    using (var brush = new PathGradientBrush(halo))
                    {
                        brush.CenterColor = C("glow", shown * 0.8 * glow);
                        brush.SurroundColors = new[] { C("glow", 0) };
                        g.FillPath(brush, halo);
                    }
                }
            using (var brush = new SolidBrush(C("moon", shown))) g.FillEllipse(brush, moon.X - r, moon.Y - r, 2 * r, 2 * r);
            // The rabbit's shadow on it.
            double rabbit = Clamp((ms - 1150) / 400) * 0.6;
            if (rabbit > 0)
                using (var brush = new SolidBrush(C("rabbit", shown * rabbit)))
                {
                    g.FillEllipse(brush, moon.X - U(9), moon.Y - U(1), U(16), U(13));
                    g.FillEllipse(brush, moon.X + U(2), moon.Y - U(9), U(9), U(9));
                    g.FillEllipse(brush, moon.X + U(3), moon.Y - U(21), U(3.2), U(13));
                    g.FillEllipse(brush, moon.X + U(7), moon.Y - U(20), U(3.2), U(12));
                }
            // Songpyeon under it, one after another.
            for (int i = 0; i < 4; i++)
            {
                double since = ms - 1500 - i * 150;
                if (since < 0) continue;
                double pop = Clamp(since / 220);
                float size = (float)(pop + 0.15 * Math.Sin(Math.PI * pop));
                PointF at = At(124 + (i - 1.5) * 20, -58 + 44);
                float w = U(15) * size, h = U(11) * size;
                if (w < 1f || h < 1f) continue;
                using (var brush = new SolidBrush(C("cake" + i, shown)))
                    g.FillPie(brush, at.X - w / 2, at.Y - h / 2, w, h, 180, 180);
            }
        }

        // ---------------------------------------------------------------- christmas
        private void Christmas(Graphics g, double ms, double shown)
        {
            PointF foot = At(126, 108);
            float h = U(74), w = U(54);
            using (var brush = new SolidBrush(C("trunk", shown))) g.FillRectangle(brush, foot.X - U(4), foot.Y - U(8), U(8), U(8));
            using (var brush = new SolidBrush(C("tree", shown)))
                for (int tier = 0; tier < 3; tier++)
                {
                    float top = foot.Y - U(8) - h + tier * h * 0.26f, bottom = foot.Y - U(8) - h * (0.52f - tier * 0.26f);
                    float half = w * (0.32f + tier * 0.18f);
                    g.FillPolygon(brush, new[] { new PointF(foot.X, top), new PointF(foot.X + half, bottom), new PointF(foot.X - half, bottom) });
                }
            Star(g, new PointF(foot.X, foot.Y - U(8) - h), U(5), C("star", shown));
            // The lights: red and green by turns.
            double lit = Clamp((ms - 300) / 200);
            for (int i = 0; i < 9; i++)
            {
                double row = 0.25 + 0.22 * (i / 3), across = (i % 3 - 1) * (0.22 + 0.16 * (i / 3));
                var at = new PointF(foot.X + (float)(across * w), foot.Y - U(8) - h + (float)(row * h) + U(6));
                bool red = (i + (int)(ms / 300)) % 2 == 0;
                Dot(g, at, 2.3, C(red ? "red" : "green", shown * (0.35 + 0.65 * lit)));
            }
            // The snow piling at its foot.
            double pile = Ease((ms - 500) / 1900.0);
            if (U(20 * pile) >= 1f)
                using (var brush = new SolidBrush(C("pile", shown)))
                using (var pen = new Pen(C("snowEdge", shown), U(1)))
                {
                    var mound = new RectangleF(foot.X - U(96), foot.Y - U(10 * pile), U(192), U(20 * pile));
                    g.FillPie(brush, mound.X, mound.Y, mound.Width, mound.Height, 180, 180);
                    g.DrawArc(pen, mound.X, mound.Y, mound.Width, mound.Height, 180, 180);
                }
            // And heavy snow over all of it.
            for (int i = 0; i < 70; i++)
            {
                double x = -20 + 260 * flakes[5 * i], start = -130 - 120 * flakes[5 * i + 1], speed = 0.09 + 0.07 * flakes[5 * i + 2];
                double y = start + speed * ms;
                if (y > 110 || y < -124) continue;
                x += 6 * Math.Sin(ms / 400.0 + 6.28 * flakes[5 * i + 4]);
                double radius = 1.2 + 1.4 * flakes[5 * i + 3];
                PointF at = At(x, y);
                Dot(g, new PointF(at.X + U(0.6), at.Y + U(0.6)), radius, C("snowEdge", shown));
                Dot(g, at, radius, C("snow", shown));
            }
        }
    }

    /// v0.6.24 (the owner, 2026-11-18, the Hint board's H2 and H3): on a special day the version's pill says it can be
    /// pressed - it nudges up about 3 px now and then (every 7 s, as the board's car-nudge) and its ring glows slowly in
    /// the day's colour (Brand.DayRing, over 4 s, as car-ring). Neither on an ordinary day, in High Contrast, with motion
    /// reduced or Windows' animations off (Soft.ReduceMotion - the ring is left out then, not held still), in a picture or a
    /// probe without a probe date (DayArt.On), or while the pill is not on the screen. Under battery saver or a locked
    /// session (Motion.Ambient) it holds still - the pill at rest, the ring where it was - and asks once a second whether
    /// that is over, as the day's scene does (SoftDayScene). A timer only while it can be seen moving.
    /// v0.6.26 (audit D11): the nudge moves smoothly - not in whole pixels (four places, 90 ms apart, at 100 %): the pill
    /// is placed in whole pixels (Nudge, the lift rounded up) and draws itself the rest of a pixel lower (Offset), so it
    /// stands exactly Lift up at every frame; and battery saver starting in the middle of a nudge lets that nudge ease to
    /// rest before the pill holds, never a drop of up to 3 px in one frame.
    internal sealed class PillHint : IDisposable
    {
        internal const int NudgeMs = 7000, RingMs = 4000;
        internal const double NudgePx = 3.0, RingOpacity = 0.55, RingPx = 2.0;
        private const int FrameBeat = 33, StillBeat = 1000;
        private readonly Control pill;
        private readonly Timer timer = new Timer();
        private readonly Stopwatch clock = new Stopwatch();
        private string look;
        private double lift;
        private double ring;

        /// Told each time the nudge or the ring changes - whether the nudge did, so the pill is placed again - to repaint it.
        internal Action<bool> Changed;

        internal PillHint(Control pill)
        {
            this.pill = pill;
            timer.Interval = FrameBeat;
            timer.Tick += delegate { Beat(); };
        }

        /// The day it hints for, or null (an ordinary day).
        internal string Look { get { return look; } }

        /// How far up the pill stands now, in device pixels: in whole pixels (Nudge, where it is placed: the lift rounded up),
        /// and exactly (Lift), the rest of a pixel drawn inside it (Offset, 0 to below 1, down); how strong its ring is, 0 to
        /// 1; whether it moves; whether it is held.
        internal int Nudge { get { return RiseOf(lift); } }
        internal double Lift { get { return lift; } }
        internal float Offset { get { return OffsetOf(lift); } }
        internal double Ring { get { return ring; } }
        internal bool Moving { get { return timer.Enabled; } }
        internal bool Held { get { return timer.Enabled && timer.Interval == StillBeat; } }

        /// The whole pixels a pill `lift` up is placed up by, and how far below that it draws itself: Rise - Offset = lift.
        internal static int RiseOf(double lift)
        {
            return lift <= 0.001 ? 0 : (int)Math.Ceiling(lift - 0.001);
        }

        internal static float OffsetOf(double lift)
        {
            return (float)Math.Max(0.0, RiseOf(lift) - lift);
        }

        /// The board's car-nudge at `ms`, in pixels at 100 %: at rest for 86 % of the 7 s, then up 3, down, up 1 and down.
        internal static double NudgeAt(double ms)
        {
            double p = (ms % NudgeMs + NudgeMs) % NudgeMs / NudgeMs;
            if (p < 0.86) return 0.0;
            if (p < 0.90) return NudgePx * Motion.Ease((p - 0.86) / 0.04);
            if (p < 0.94) return NudgePx * (1.0 - Motion.Ease((p - 0.90) / 0.04));
            if (p < 0.97) return NudgePx / 3.0 * Motion.Ease((p - 0.94) / 0.03);
            return NudgePx / 3.0 * (1.0 - Motion.Ease((p - 0.97) / 0.03));
        }

        /// The board's car-ring at `ms`: 0 to 1 and back over 4 s.
        internal static double RingAt(double ms)
        {
            return (1.0 - Math.Cos(2.0 * Math.PI * ms / RingMs)) / 2.0;
        }

        /// Whether a hint may show at all for `day`: a special day, motion allowed (not reduced, not High Contrast,
        /// Windows' animations on) and the pill on the screen.
        internal bool Wanted(string day)
        {
            return !string.IsNullOrEmpty(day) && !Palette.Contrast && !Soft.ReduceMotion && Motion.Allowed(pill);
        }

        /// The hint for `day` (null for none), started or stopped as what it may show says; again on every second of the
        /// window's clock, and whenever the pill shows or goes.
        internal void Follow(string day)
        {
            look = string.IsNullOrEmpty(day) ? null : day;
            bool wanted = Wanted(day);
            if (wanted && !timer.Enabled)
            {
                clock.Start();
                timer.Interval = FrameBeat;
                timer.Start();
                Beat();
            }
            else if (!wanted && (timer.Enabled || lift != 0 || ring != 0))
            {
                timer.Stop();
                clock.Reset();
                Set(0.0, 0.0);
            }
        }

        private void Beat()
        {
            if (!Wanted(look))
            {
                Follow(look);
                return;
            }
            // Battery saver or a locked session: held - but a nudge under way first eases to rest (Settling), the ring held
            // where it was meanwhile.
            bool settling = Settling(Motion.Ambient, lift);
            bool still = Motion.Ambient && !settling;
            if (still != (timer.Interval == StillBeat))
            {
                timer.Interval = still ? StillBeat : FrameBeat;
                if (still) clock.Stop();
                else clock.Start();
            }
            double ms = clock.Elapsed.TotalMilliseconds;
            Set(still ? 0.0 : NudgeAt(ms) * Soft.PxF(1), still || settling ? ring : RingAt(ms));
        }

        /// Whether a pill `lift` up when motion is to hold (`ambient`) is still on its way to rest: it holds once there.
        internal static bool Settling(bool ambient, double lift)
        {
            return ambient && lift > 0.001;
        }

        private void Set(double up, double level)
        {
            if (Math.Abs(up - lift) < 0.01 && Math.Abs(level - ring) < 0.01) return;
            bool moved = RiseOf(up) != RiseOf(lift);
            lift = up;
            ring = level;
            if (Changed != null) Changed(moved);
        }

        /// Its ring, drawn just inside the pill's edge (`bounds`, its body, `radius` its corners) in the day's colour.
        internal void PaintRing(Graphics g, Rectangle bounds, float radius)
        {
            if (look == null || ring <= 0.01 || !timer.Enabled) return;
            Color colour = Brand.DayRing(look);
            if (colour.IsEmpty) return;
            float width = Soft.PxF((float)RingPx);
            var edge = new RectangleF(bounds.X + width / 2f, bounds.Y + width / 2f, bounds.Width - width, bounds.Height - width);
            SmoothingMode before = g.SmoothingMode;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            using (GraphicsPath path = Soft.Rounded(Rectangle.Round(edge), Math.Max(0f, radius - width / 2f)))
            using (var pen = new Pen(Soft.WithAlpha(colour, RingOpacity * ring), width))
                g.DrawPath(pen, path);
            g.SmoothingMode = before;
        }

        public void Dispose()
        {
            timer.Stop();
            timer.Dispose();
        }
    }
}
