// Codex Auto Resume - the version's easter eggs (v0.6.24-beta.2, the owner, 2026-11-16): the run of presses that plays a
// special one at the sixth (PressRun), which of the three (EggPick), and the confetti - its pieces (ConfettiBurst) and the
// layered window they fall in, over the Dashboard and never outside it (ConfettiLayer). One press is the light's sweep and
// the sentence (SettingsForm.VersionPressed); the light's colours are its own (HaloDot.RunColours).

using System;
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
    internal sealed class ConfettiBurst
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
        private readonly ConfettiBurst burst;
        private readonly Timer timer = new Timer();
        private readonly Stopwatch clock = new Stopwatch();
        private IntPtr dib, memory, previous;

        /// `area` in the owner's client coordinates, within its client area.
        internal ConfettiLayer(Form owner, Rectangle area, ConfettiBurst burst)
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
            if (ms >= ConfettiBurst.LengthMs || owner.IsDisposed || !owner.Visible || owner.WindowState == FormWindowState.Minimized)
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
}
