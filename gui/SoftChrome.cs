// Codex Auto Resume - the window's own caption: no title bar from Windows (v0.6.24, stage 1 surface A).
//
// The owner, 2026-11-13: no Windows title bar on any window or dialog of ours; the minimise, maximise and close buttons
// stand in the window's first card instead - the Dashboard's hero, the setup window's header card - and, on a dialog,
// a title row on its own ground (Soft.DialogBar; the owner's choice B, 2026-11-16) - drawn in the house's material, close red under the pointer (board TitleB,
// option B, 2026-11-15).
//
// Every window style Windows has today is kept - WS_CAPTION, WS_SYSMENU, WS_THICKFRAME for a sizable window, the boxes
// the form's properties ask for - and only the caption strip and the top frame are taken out of the client calculation
// (WM_NCCALCSIZE). Keeping the styles keeps what Windows does for a window that we do not do again: the Alt+Space window
// menu, Alt+F4, Win+arrow snap, Aero snap by dragging, the minimise and maximise animations, the taskbar button, and the
// desktop window manager's own border, shadow and rounding (plans/v0624-stage1-design.md, 3.1).
//
// Where the pointer is decides the rest (WM_NCHITTEST): the top resize band, the maximise button as HTMAXBUTTON - which is
// what gives Windows 11 its snap layouts on hover - the card and the empty ground as HTCAPTION, from which Windows' own
// move loop drags, snaps, double-click maximises and right-click opens the window menu, and everything else the client's.
// A control in the drag area lets the question through to the window (HTTRANSPARENT, DragThrough); a control a person
// acts on never does. Every button acts through WM_SYSCOMMAND, so what heard Windows' own caption buttons hears ours.
//
// The screen reader hears Windows' own words for the commands, read from the window menu; the buttons are never in the
// Tab order, as Windows' are not. Nothing here asks Windows anything per mouse move but where the pointer is: the
// rectangles a hit test reads are kept until the window's layout changes (ChromeHost.Layout).

using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows.Forms;

namespace CodexAutoResume
{
    /// What a window's hit test reads (Chrome.Hit), in its client coordinates: worked out once per layout, never per move.
    internal struct ChromeLayout
    {
        internal Size Client;
        /// A window that can be resized by its edges, and is: not maximised.
        internal bool Sizable, Maximized, Mirrored;
        /// v0.6.24 W5: the window's whole rectangle is its client area (its own outer corner, gui/SoftWindowShape.cs), so
        /// the left, right and bottom resize bands are answered here too, as the top one is.
        internal bool Edges;
        /// The top resize band, in device px: the frame Windows had at the top, now inside the client area.
        internal int Band;
        /// v0.6.24: how far along each edge from the window's corner its own cut-away corner reaches (WindowCorner.Span),
        /// in device px; 0 with Windows' corner.
        internal int CornerSpan;
        /// The three buttons, Empty where the window has none.
        internal Rectangle Minimize, Maximize, Close;
        internal bool MinimizeOn, MaximizeOn;
        /// What a person acts on inside the drag area (a button in the hero, the tabs, a card on the ground): the client's.
        internal Rectangle[] Solid;
        internal int SolidCount;
    }

    /// The pieces of the window's own caption that need no window: the hit test, the client calculation and the frame,
    /// pure, so the tests ask them a table (tests/test_gui_chrome_hit.py, test_gui_chrome_frame.py).
    internal static class Chrome
    {
        internal const int HTTRANSPARENT = -1, HTNOWHERE = 0, HTCLIENT = 1, HTCAPTION = 2, HTMINBUTTON = 8, HTMAXBUTTON = 9,
                           HTLEFT = 10, HTRIGHT = 11, HTTOP = 12, HTTOPLEFT = 13, HTTOPRIGHT = 14, HTBOTTOM = 15,
                           HTBOTTOMLEFT = 16, HTBOTTOMRIGHT = 17, HTCLOSE = 20;
        internal const int WM_NCCALCSIZE = 0x0083, WM_NCHITTEST = 0x0084, WM_NCMOUSEMOVE = 0x00A0, WM_NCLBUTTONDOWN = 0x00A1,
                           WM_NCLBUTTONUP = 0x00A2, WM_NCLBUTTONDBLCLK = 0x00A3, WM_NCMOUSELEAVE = 0x02A2, WM_SYSCOMMAND = 0x0112;
        internal const int SC_MINIMIZE = 0xF020, SC_MAXIMIZE = 0xF030, SC_RESTORE = 0xF120, SC_CLOSE = 0xF060;

        /// Windows' words where its window menu has none for a command (GetMenuString found nothing).
        internal const string MinimizeWord = "Minimize", MaximizeWord = "Maximize", RestoreWord = "Restore", CloseWord = "Close";

        [StructLayout(LayoutKind.Sequential)]
        internal struct RECT { public int Left, Top, Right, Bottom; }

        [DllImport("user32.dll")]
        private static extern bool AdjustWindowRectEx(ref RECT rect, int style, bool menu, int exStyle);

        /// What the pointer at `p` is over, as WM_NCHITTEST answers it - asked only where Windows' own answer was the client
        /// (DefWindowProc keeps the left, right and bottom frames). In order: the top resize band of a sizable window that
        /// is not maximised; the maximise button, HTMAXBUTTON while it does something (Windows 11's snap layouts open on
        /// it); minimise and close, which are the client's - they are controls of their own; maximised, the strip above
        /// each button to the window's top and the room past close to the screen's edge, as a maximised window's buttons
        /// are hit by flinging the pointer into the corner; what a person acts on; and the rest, the card and the ground, to
        /// drag by.
        internal static int Hit(Point p, ChromeLayout l)
        {
            if (p.X < 0 || p.Y < 0 || p.X >= l.Client.Width || p.Y >= l.Client.Height) return HTNOWHERE;
            // The length along each edge that resizes from the corner: twice the band, as Windows' own; with the window's own
            // corner, from the corner to a band past where its cut-away curve ends (CornerSpan) - re-check 5 found the
            // diagonal target only ~3 px at 150 %, the cut corner itself taking nothing (its clicks go to the window behind).
            int reach = Math.Max(2 * l.Band, l.Edges ? l.CornerSpan + l.Band : 0);
            if (l.Edges && l.Sizable && !l.Maximized)
            {
                // No frame round the window (its own outer corner): its bottom, left and right bands as its top one.
                int corner = reach;
                if (p.Y >= l.Client.Height - l.Band)
                {
                    if (p.X < corner) return HTBOTTOMLEFT;
                    if (p.X >= l.Client.Width - corner) return HTBOTTOMRIGHT;
                    return HTBOTTOM;
                }
                if (p.Y >= l.Band && p.X < l.Band) return p.Y >= l.Client.Height - corner ? HTBOTTOMLEFT : HTLEFT;
                if (p.Y >= l.Band && p.X >= l.Client.Width - l.Band) return p.Y >= l.Client.Height - corner ? HTBOTTOMRIGHT : HTRIGHT;
            }
            if (l.Sizable && !l.Maximized && p.Y < l.Band)
            {
                int corner = reach;
                if (p.X < corner) return HTTOPLEFT;
                if (p.X >= l.Client.Width - corner) return HTTOPRIGHT;
                return HTTOP;
            }
            if (l.Maximize.Contains(p)) return l.MaximizeOn ? HTMAXBUTTON : HTCLIENT;
            if (l.Minimize.Contains(p) || l.Close.Contains(p)) return HTCLIENT;
            if (l.Maximized)
            {
                if (Above(p, l.Close)) return HTCLOSE;
                if (Above(p, l.Maximize)) return l.MaximizeOn ? HTMAXBUTTON : HTCLIENT;
                if (Above(p, l.Minimize)) return l.MinimizeOn ? HTMINBUTTON : HTCLIENT;
                if (!l.Close.IsEmpty && p.Y < l.Close.Bottom && (l.Mirrored ? p.X < l.Close.Left : p.X >= l.Close.Right))
                    return HTCLOSE;
            }
            for (int i = 0; i < l.SolidCount; i++)
                if (l.Solid[i].Contains(p)) return HTCLIENT;
            return HTCAPTION;
        }

        private static bool Above(Point p, Rectangle button)
        {
            return !button.IsEmpty && p.X >= button.Left && p.X < button.Right && p.Y < button.Top;
        }

        /// WM_NCCALCSIZE's answer: the client Windows worked out inside `proposed` (`computed`: inside the frames and the
        /// caption), with its top at the window's top - no caption and no top frame - and, maximised, as far below it as the
        /// frame Windows hangs past the screen's edge: the left frame it worked out is that thickness.
        internal static Rectangle ClientFor(Rectangle proposed, Rectangle computed, bool maximized)
        {
            int top = proposed.Top + (maximized ? Math.Max(0, computed.Left - proposed.Left) : 0);
            return Rectangle.FromLTRB(computed.Left, top, computed.Right, Math.Max(top, computed.Bottom));
        }

        /// The frame a window of `style` has round its client area once its caption is ours: the left, right and bottom
        /// frames Windows gives that style, and nothing at the top.
        internal static Padding Frame(int style, int exStyle)
        {
            Padding captioned = CaptionedFrame(style, exStyle);
            return new Padding(captioned.Left, 0, captioned.Right, captioned.Bottom);
        }

        /// The frame Windows gives a window of `style` with its own caption: what WinForms still counts where it works a
        /// window's size out with no way for us to answer (Uncaptioned).
        internal static Padding CaptionedFrame(int style, int exStyle)
        {
            var rect = new RECT();
            try
            {
                if (!AdjustWindowRectEx(ref rect, style, false, exStyle)) return Padding.Empty;
            }
            catch (Exception) { return Padding.Empty; }
            return new Padding(Math.Max(0, -rect.Left), Math.Max(0, -rect.Top), Math.Max(0, rect.Right), Math.Max(0, rect.Bottom));
        }

        /// A window size WinForms worked out from `client` with Windows' caption counted (`captioned`) - as the window is
        /// made (Form.FillInCreateParamsStartPosition) and as it comes back from maximised or minimised
        /// (Form.RestoreWindowBoundsIfNecessary), each through Control's own SizeFromClientSize(int, int), which no form can
        /// answer - is that client's window inside `frame`, with no caption. Any other size is kept as it was asked.
        internal static Size Uncaptioned(Size asked, Size client, Padding frame, Padding captioned)
        {
            if (client.IsEmpty || frame == captioned || asked != WindowSize(client, captioned)) return asked;
            return WindowSize(client, frame);
        }

        private const int WS_MAXIMIZE = 0x01000000, WS_MINIMIZE = 0x20000000;

        /// The window `created` makes, from the client `client`, with no caption: for a form's CreateParams, so a top-level
        /// window is made at the size its ClientSize says and not one Windows caption taller.
        internal static void Uncaption(CreateParams created, Size client)
        {
            Uncaption(created, client, false);
        }

        /// v0.6.24-beta.2: and, `frameless` (ChromeHost.Frameless: the window's outer corner is its own), with no frame at
        /// all - the window is that client, as its SizeFromClientSize says - or it is made a frame bigger than its ClientSize
        /// and the whole of it becomes its client (the setup window opened 906 x 903 for its 900 x 900 at 150 %).
        internal static void Uncaption(CreateParams created, Size client, bool frameless)
        {
            int style = created.Style & ~(WS_MAXIMIZE | WS_MINIMIZE);
            Size outer = Uncaptioned(new Size(created.Width, created.Height), client,
                                     frameless ? Padding.Empty : Frame(style, created.ExStyle), CaptionedFrame(style, created.ExStyle));
            created.Width = outer.Width;
            created.Height = outer.Height;
        }

        // ------------------------------------------------------------------ an auto-hide taskbar (or other appbar)

        [StructLayout(LayoutKind.Sequential)]
        private struct APPBARDATA
        {
            public int Size;
            public IntPtr Window;
            public int CallbackMessage;
            public int Edge;
            public RECT Rect;
            public IntPtr Param;
        }

        [DllImport("shell32.dll")]
        private static extern IntPtr SHAppBarMessage(int message, ref APPBARDATA data);

        private const int ABM_GETSTATE = 0x4, ABM_GETAUTOHIDEBAREX = 0xB, ABS_AUTOHIDE = 0x1;

        /// How much of the monitor a maximised window leaves at an edge where an auto-hide bar waits: the pointer reaches
        /// the bar there, and the bar can slide out over the window. Two pixels, as other windows with a caption of their
        /// own leave (one is lost to rounding at some scalings).
        internal const int AutoHideRoom = 2;

        /// The edges of `monitor` with an auto-hide appbar on them - the taskbar set to hide itself - each a bit, 1 << ABE_
        /// (left 1, top 2, right 4, bottom 8): asked of Windows (SHAppBarMessage) only while a window is maximised, and
        /// what the tests stub.
        internal static Func<Rectangle, int> AppBarEdges = AutoHideEdges;

        private static int AutoHideEdges(Rectangle monitor)
        {
            try
            {
                var state = new APPBARDATA();
                state.Size = Marshal.SizeOf(typeof(APPBARDATA));
                if ((SHAppBarMessage(ABM_GETSTATE, ref state).ToInt64() & ABS_AUTOHIDE) == 0) return 0;
                int edges = 0;
                for (int edge = 0; edge < 4; edge++)
                {
                    var bar = new APPBARDATA();
                    bar.Size = Marshal.SizeOf(typeof(APPBARDATA));
                    bar.Edge = edge;
                    bar.Rect = new RECT { Left = monitor.Left, Top = monitor.Top, Right = monitor.Right, Bottom = monitor.Bottom };
                    if (SHAppBarMessage(ABM_GETAUTOHIDEBAREX, ref bar) != IntPtr.Zero) edges |= 1 << edge;
                }
                return edges;
            }
            catch (Exception) { return 0; }
        }

        /// The client of a maximised window, `client`, short by AutoHideRoom at each edge of `monitor` in `edges`
        /// (AppBarEdges) that it reaches; where it stops short of that edge already (the work area), as it was.
        internal static Rectangle LeaveForAppBars(Rectangle client, Rectangle monitor, int edges)
        {
            int left = client.Left, top = client.Top, right = client.Right, bottom = client.Bottom;
            if ((edges & 1) != 0 && left <= monitor.Left) left = monitor.Left + AutoHideRoom;
            if ((edges & 2) != 0 && top <= monitor.Top) top = monitor.Top + AutoHideRoom;
            if ((edges & 4) != 0 && right >= monitor.Right) right = monitor.Right - AutoHideRoom;
            if ((edges & 8) != 0 && bottom >= monitor.Bottom) bottom = monitor.Bottom - AutoHideRoom;
            return Rectangle.FromLTRB(left, top, Math.Max(left, right), Math.Max(top, bottom));
        }

        /// Where a window whose visible box is `window` big goes over a window whose visible box is `owner`: centred on it,
        /// and held inside `work` (the work area of the monitor the owner is on) against the edge it would cross - its top
        /// left kept inside where it is larger than the work area. An empty `work` holds it nowhere.
        internal static Point CentreOn(Rectangle owner, Size window, Rectangle work)
        {
            int x = owner.X + (owner.Width - window.Width) / 2, y = owner.Y + (owner.Height - window.Height) / 2;
            if (work.IsEmpty) return new Point(x, y);
            x = Math.Max(work.Left, Math.Min(x, work.Right - window.Width));
            y = Math.Max(work.Top, Math.Min(y, work.Bottom - window.Height));
            return new Point(x, y);
        }

        /// The window `client` needs inside `frame` (Frame): what Form.SizeFromClientSize answers once the caption is ours, so
        /// a form's ClientSize means what it says.
        internal static Size WindowSize(Size client, Padding frame)
        {
            return new Size(client.Width + frame.Horizontal, client.Height + frame.Vertical);
        }

        /// The client area of a window `outer` big inside `frame`.
        internal static Size ClientOf(Size outer, Padding frame)
        {
            return new Size(Math.Max(0, outer.Width - frame.Horizontal), Math.Max(0, outer.Height - frame.Vertical));
        }

        /// Whether a window has the minimise and maximise pair, as Windows draws it from its properties: with either box on,
        /// both - the one that is off drawn faint and doing nothing - and with both off, Close alone.
        internal static bool Pair(bool minimizeBox, bool maximizeBox)
        {
            return minimizeBox || maximizeBox;
        }

        private static readonly Regex KeyInBrackets = new Regex(@"\s*[\(（]&[^\)）][\)）]");

        /// A window menu item's words as a screen reader hears a caption button: its access key and its shortcut taken
        /// off - "Mi&nimize" is "Minimize", "&Close\tAlt+F4" is "Close", "최소화(&N)" is "최소화" - or `fallback`.
        internal static string CommandName(string menu, string fallback)
        {
            if (string.IsNullOrEmpty(menu)) return fallback;
            int tab = menu.IndexOf('\t');
            if (tab >= 0) menu = menu.Substring(0, tab);
            menu = KeyInBrackets.Replace(menu, "");
            menu = menu.Replace("&&", "\u0001").Replace("&", "").Replace("\u0001", "&").Trim();
            return menu.Length == 0 ? fallback : menu;
        }

        /// WCAG's relative luminance of `colour` (its alpha ignored).
        internal static double Luminance(Color colour)
        {
            Func<int, double> channel = delegate(int value)
            {
                double c = value / 255.0;
                return c <= 0.03928 ? c / 12.92 : Math.Pow((c + 0.055) / 1.055, 2.4);
            };
            return 0.2126 * channel(colour.R) + 0.7152 * channel(colour.G) + 0.0722 * channel(colour.B);
        }

        /// WCAG's contrast ratio of two colours, 1 to 21.
        internal static double Contrast(Color one, Color other)
        {
            double first = Luminance(one), second = Luminance(other);
            return (Math.Max(first, second) + 0.05) / (Math.Min(first, second) + 0.05);
        }

        /// A caption glyph's colour at rest over a day's scene (O6, the main session 2026-11-15): `muted` as on every other
        /// day where it stands out from what the scene puts under the glyph (`under`) by WCAG's 3:1 for what is not text;
        /// otherwise whichever of `ink` and `light` (OnAccent) stands out the more. Empty: keep `muted`.
        internal static Color OverScene(Color under, Color muted, Color ink, Color light)
        {
            if (Contrast(muted, under) >= 3.0) return Color.Empty;
            return Contrast(ink, under) >= Contrast(light, under) ? ink : light;
        }

        /// Whether this Windows has snap layouts on the maximise button (Windows 11, build 22000 on): where it does, the
        /// button shows them on hover and no tooltip of ours.
        internal static bool SnapLayouts
        {
            get { return Environment.OSVersion.Version.Major >= 10 && Environment.OSVersion.Version.Build >= 22000; }
        }
    }

    /// One window's caption: its three buttons in its first card, the controls it may be dragged by, and what it does with
    /// the messages Windows sends a window about its frame. The form's own WndProc hands each message here first
    /// (Intercept), with a way to hand it on to its base - no second window procedure.
    internal sealed class ChromeHost : IDisposable
    {
        internal delegate void Pass(ref Message m);

        [DllImport("user32.dll")]
        private static extern bool IsZoomed(IntPtr window);
        [DllImport("user32.dll")]
        private static extern bool PostMessage(IntPtr window, int message, IntPtr wParam, IntPtr lParam);
        [DllImport("user32.dll")]
        private static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int width, int height, uint flags);
        [DllImport("user32.dll")]
        private static extern IntPtr GetSystemMenu(IntPtr window, bool revert);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetMenuString(IntPtr menu, int item, StringBuilder text, int most, int flags);
        [DllImport("user32.dll")]
        private static extern bool TrackMouseEvent(ref TRACKMOUSEEVENT track);
        [DllImport("user32.dll")]
        private static extern int GetDpiForWindow(IntPtr window);
        [DllImport("user32.dll")]
        private static extern int GetSystemMetricsForDpi(int index, int dpi);
        [DllImport("user32.dll")]
        private static extern int GetSystemMetrics(int index);

        [StructLayout(LayoutKind.Sequential)]
        private struct TRACKMOUSEEVENT { public int Size; public int Flags; public IntPtr Window; public int HoverTime; }

        private const uint SWP_NOSIZE = 0x0001, SWP_NOMOVE = 0x0002, SWP_NOZORDER = 0x0004, SWP_NOACTIVATE = 0x0010,
                           SWP_FRAMECHANGED = 0x0020;
        private const int TME_LEAVE = 0x00000002, TME_NONCLIENT = 0x00000010;
        private const int SM_CYSIZEFRAME = 33, SM_CXPADDEDBORDER = 92;
        private const int MF_BYCOMMAND = 0;
        // How long the pointer rests on a button before its tooltip, as a tooltip of Windows' waits (ToolTip.InitialDelay).
        private const int TipDelay = 500;

        private readonly Form form;
        private readonly Control card, holder;
        internal readonly CaptionButton MinimizeButton, MaximizeButton, CloseButton;
        private readonly List<Control> drag = new List<Control>();
        private readonly List<DragThrough> hooks = new List<DragThrough>();
        private ChromeLayout layout;
        private bool dirty = true, tracking;
        private int ncHover, ncPressed;
        private SoftDayScene scene;
        private readonly Timer sceneBeat = new Timer();
        private readonly Timer tipWait = new Timer();
        private CaptionButton tipFor;
        private SoftTipWindow tip;
        private readonly LayoutEventHandler dirtied;
        // v0.6.24 W5: the window's own outer corner (gui/SoftWindowShape.cs), only where it asked for one and the switch is on.
        private WindowCorner corner;
        // v0.6.24-beta.2: the buttons stand in a row on the window's own ground (a dialog's title), not in a card's corner.
        private bool ground;

        private ChromeHost(Form form, Control card, Control holder)
        {
            this.form = form;
            this.card = card;
            this.holder = holder;
            MinimizeButton = new CaptionButton(this, Chrome.SC_MINIMIZE);
            MaximizeButton = new CaptionButton(this, Chrome.SC_MAXIMIZE);
            CloseButton = new CaptionButton(this, Chrome.SC_CLOSE);
            dirtied = delegate { dirty = true; };
            sceneBeat.Tick += delegate { SceneBeat(); };
            tipWait.Interval = TipDelay;
            tipWait.Tick += delegate { tipWait.Stop(); ShowTip(); };
        }

        /// The caption of `form`, its buttons standing in `card` at the card's top outer corner (Brand.CaptionInsetTop,
        /// CaptionInsetEnd), over everything in it. They are children of `holder` - the card itself, or a control the card is
        /// in, which lays out nothing it holds of its own accord (a Panel, a Form: never a table, never a SoftPage, which
        /// moves what it holds to its right when mirrored) - so they stand over what is laid on the card too (the day's scene).
        internal static ChromeHost Install(Form form, Control card, Control holder)
        {
            var host = new ChromeHost(form, card, holder);
            foreach (CaptionButton button in host.Buttons()) holder.Controls.Add(button);
            host.Raise();
            EventHandler place = delegate { host.Place(); };
            card.SizeChanged += place;
            card.LocationChanged += place;
            form.RightToLeftChanged += place;
            form.Resize += delegate { host.Maximized(); host.dirty = true; };
            form.Layout += delegate { host.dirty = true; };
            holder.Layout += delegate { host.dirty = true; };
            form.HandleCreated += delegate { host.Created(); };
            form.Disposed += delegate { host.Dispose(); };
            if (holder != form) host.Drag(holder);
            if (card != form) host.Drag(card);
            host.Place();
            if (form.IsHandleCreated) host.Created();
            return host;
        }

        /// v0.6.24 W5: the window's own outer corner - the card's, smoothed as the cards are - in place of Windows' round
        /// one, for the window that asks (the Dashboard): only with Brand.WindowSquircle on, on Windows 11, outside High
        /// Contrast and a remote session (WindowShape.Wanted). Off, nothing is made and the window is as it was.
        internal void OwnCorner()
        {
            if (corner != null || !form.TopLevel || !WindowShape.Wanted()) return;
            corner = WindowCorner.Attach(form);
            corner.Changed += delegate { dirty = true; Grip(); };
            form.Layout += delegate { Grip(); };
            if (form.IsHandleCreated) Created();
            Grip();
        }

        // ------------------------------------------------------------------ the grip band, given by what lies in it

        // The controls that reach into the grip band (GripThrough), and the containers looked into for them.
        private readonly Dictionary<Control, GripThrough> grips = new Dictionary<Control, GripThrough>();
        private readonly HashSet<Control> watched = new HashSet<Control>();
        private bool gripping;

        /// v0.6.24 W5: with its own corner the window resizes from a band inside its edge (Chrome.Hit, ChromeLayout.Edges),
        /// but Windows asks the control under the pointer first, and a control that reaches into the band - the page
        /// under the tabs, the full width of the window (M-CORNER 2026-11-16, item 3: the left and right edges did not
        /// resize along the pages) - answered for it. Every control that reaches into the band, at any depth, gives the
        /// band to the window (HTTRANSPARENT there); the rest of it stays its own. Looked at again as anything that holds
        /// one is laid out, so a page built later, a control added and the mirrored window all give it too. Only controls
        /// that reach the band are looked into: nothing inside one that does not can reach it.
        private void Grip()
        {
            if (corner == null || gripping || form.IsDisposed) return;
            gripping = true;
            try { GripIn(form, Math.Max(1, TopBand())); }
            finally { gripping = false; }
        }

        private void GripIn(Control parent, int band)
        {
            Size client = form.ClientSize;
            foreach (Control child in parent.Controls)
            {
                if (child is CaptionButton || child.IsDisposed) continue;
                Rectangle at = InForm(child);
                bool reaches = at.Left < band || at.Top < band || at.Right > client.Width - band || at.Bottom > client.Height - band;
                if (!reaches) continue;
                if (!drag.Contains(child) && !grips.ContainsKey(child)) grips[child] = new GripThrough(child, this);
                if (watched.Add(child))
                {
                    child.Layout += delegate { Grip(); };
                    child.Disposed += delegate { Forget(child); };
                }
                if (child.Controls.Count > 0) GripIn(child, band);
            }
        }

        private void Forget(Control child)
        {
            GripThrough hook;
            if (grips.TryGetValue(child, out hook)) hook.Let();
            grips.Remove(child);
            watched.Remove(child);
        }

        /// Whether the pointer at `screen` is in the band the window is resized from (Chrome.Hit's edges), the window's own
        /// corner on.
        internal bool InGrip(Point screen)
        {
            if (corner == null || !form.IsHandleCreated || !form.TopLevel) return false;
            ChromeLayout l = Layout();
            if (!l.Edges || !l.Sizable || l.Maximized) return false;
            int hit = Chrome.Hit(form.PointToClient(screen), l);
            return hit >= Chrome.HTLEFT && hit <= Chrome.HTBOTTOMRIGHT;
        }

        /// The controls that give the grip band to the window now, for the tests.
        internal int Gripping
        {
            get { return grips.Count; }
        }

        /// The window's outer corner now: its own, or Windows' - round on Windows 11, square before.
        internal WindowShape.Corner OuterCorner
        {
            get
            {
                if (corner != null) return corner.Now;
                return WindowShape.Windows11 ? WindowShape.Corner.Round : WindowShape.Corner.Square;
            }
        }

        /// Whether the window has no frame at all (its own outer corner): its ClientSize is its size.
        internal bool Frameless
        {
            get { return corner != null && corner.Shaped; }
        }

        /// The window's own corner, for the tests; null where it has none.
        internal WindowCorner Corner
        {
            get { return corner; }
        }

        private IEnumerable<CaptionButton> Buttons()
        {
            yield return MinimizeButton;
            yield return MaximizeButton;
            yield return CloseButton;
        }

        /// The buttons in reading order: minimise, maximise, close from the left - mirrored, close, maximise, minimise, as a
        /// right-to-left Windows title bar has them.
        private CaptionButton[] Shown()
        {
            bool pair = Soft.OwnVisible(MinimizeButton);
            if (!Soft.OwnVisible(CloseButton)) return new CaptionButton[0];
            if (!pair) return new[] { CloseButton };
            return Mirror.Of(form) ? new[] { CloseButton, MaximizeButton, MinimizeButton }
                                   : new[] { MinimizeButton, MaximizeButton, CloseButton };
        }

        /// How wide the group of buttons is, for a card that keeps its words clear of it.
        internal int GroupWidth
        {
            get
            {
                int count = Shown().Length;
                return count == 0 ? 0 : count * Soft.Px(Brand.CaptionButtonW) + (count - 1) * Soft.Px(Brand.CaptionGap);
            }
        }

        /// Where the card is, in the coordinates of what holds the buttons.
        private Rectangle CardFace
        {
            get { return InHolder(card); }
        }

        /// Where `control` is in the coordinates of what holds the buttons: its client area when it is the holder.
        internal Rectangle InHolder(Control control)
        {
            if (control == holder) return holder.ClientRectangle;
            int x = 0, y = 0;
            for (Control c = control; c != null && c != holder; c = c.Parent)
            {
                x += c.Left;
                y += c.Top;
            }
            return new Rectangle(x, y, control.Width, control.Height);
        }

        /// The buttons as the form's properties say (Chrome.Pair) and where they go in the card.
        internal void Place()
        {
            bool pair = form.ControlBox && Chrome.Pair(form.MinimizeBox, form.MaximizeBox);
            MinimizeButton.Visible = pair;
            MaximizeButton.Visible = pair;
            CloseButton.Visible = form.ControlBox;
            MinimizeButton.Enabled = form.MinimizeBox;
            MaximizeButton.Enabled = form.MaximizeBox;
            Rectangle face = CardFace;
            bool mirrored = Mirror.Of(form);
            int width = Soft.Px(Brand.CaptionButtonW), height = Soft.Px(Brand.CaptionButtonH), gap = Soft.Px(Brand.CaptionGap);
            int x = mirrored ? face.Left + Soft.Px(Brand.CaptionInsetEnd) : face.Right - Soft.Px(Brand.CaptionInsetEnd) - GroupWidth;
            // In a card, CaptionInsetTop below its top; in a row on the ground (OnGround), centred in the row.
            int y = ground ? face.Top + (face.Height - height) / 2 : face.Top + Soft.Px(Brand.CaptionInsetTop);
            foreach (CaptionButton button in Shown())
            {
                button.SetBounds(x, y, width, height);
                x += width + gap;
            }
            dirty = true;
        }

        /// The buttons over the card and over anything laid on it (the day's scene): just above what of the holder's the card
        /// is in, so the rest of the holder's order - its docking - is as it was.
        internal void Raise()
        {
            if (holder.IsDisposed || holder == card) return;
            Control under = card;
            while (under != null && under.Parent != holder) under = under.Parent;
            int top = under == null ? 0 : holder.Controls.GetChildIndex(under);
            foreach (CaptionButton button in Buttons())
                if (button.Parent == holder) holder.Controls.SetChildIndex(button, top);
        }

        /// The day's scene the buttons stand over (SoftDays): painted under each, and again as it moves.
        internal SoftDayScene Scene
        {
            get { return scene; }
            set
            {
                if (scene == value) return;
                scene = value;
                if (scene == null) return;
                scene.VisibleChanged += delegate { SceneBeat(); };
                scene.LocationChanged += delegate { InvalidateOverScene(); };
                scene.SizeChanged += delegate { InvalidateOverScene(); };
                Drag(scene);
                SceneBeat();
            }
        }

        // A frame of the scene under the buttons while it moves (SoftDayScene's own beat), a second's wait while it is held
        // still (battery saver, a locked session), and nothing once it is gone.
        private void SceneBeat()
        {
            bool shown = scene != null && !scene.IsDisposed && scene.Visible && scene.Look != null;
            if (!shown)
            {
                sceneBeat.Stop();
                return;
            }
            sceneBeat.Interval = scene.Moving && !scene.Stilled ? 33 : 1000;
            if (!sceneBeat.Enabled) sceneBeat.Start();
            if (scene.Moving && !scene.Stilled) InvalidateOverScene();
        }

        private void InvalidateOverScene()
        {
            if (scene == null) return;
            Rectangle under = InHolder(scene);
            foreach (CaptionButton button in Buttons())
                if (button.Visible && button.Bounds.IntersectsWith(under)) button.Invalidate();
        }

        /// The card's own colour, which a button shows at rest - in High Contrast the person's Window colour, a card's; on
        /// the ground (OnGround) the ground's own colour in both, the system colour the ground is drawn in there.
        internal Color Face
        {
            get
            {
                if (Palette.Contrast && !ground) return SystemColors.Window;
                return card.BackColor.A == 255 ? card.BackColor : Palette.Card;
            }
        }

        /// v0.6.24-beta.2 (the owner's choice B, 2026-11-16): `card` is no card but a row on the window's own ground - a
        /// dialog's title - and the buttons stand at its end, centred in its height, CaptionInsetEnd in from its edge.
        internal bool OnGround
        {
            get { return ground; }
            set
            {
                if (ground == value) return;
                ground = value;
                Place();
            }
        }

        /// `control` (and what Windows asks about the points over it) is one the window may be dragged by: the card, its words
        /// and light, the empty ground. Never a control a person acts on.
        internal void Drag(Control control)
        {
            if (control == null || control == form || drag.Contains(control)) return;
            drag.Add(control);
            hooks.Add(new DragThrough(control));
            control.Layout += dirtied;
            dirty = true;
        }

        internal bool Zoomed
        {
            get { return form.IsHandleCreated && form.TopLevel && IsZoomed(form.Handle); }
        }

        private void Maximized()
        {
            bool zoomed = Zoomed;
            if (zoomed == MaximizeButton.Restores) return;
            MaximizeButton.Restores = zoomed;
            Names();
        }

        // The window is made: its frame worked out again with no caption (SWP_FRAMECHANGED, before it is first shown), and
        // the buttons named as Windows names the commands.
        private void Created()
        {
            if (form.IsHandleCreated)
            {
                try
                {
                    SetWindowPos(form.Handle, IntPtr.Zero, 0, 0, 0, 0,
                                 SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED);
                }
                catch (Exception) { }
            }
            Place();
            MaximizeButton.Restores = Zoomed;
            Names();
        }

        /// Each button's name for a screen reader and its tooltip: Windows' own word for the command, from the window menu
        /// (GetSystemMenu, GetMenuString), in Windows' language - or Chrome's fallback where the menu has none.
        internal void Names()
        {
            IntPtr menu = IntPtr.Zero;
            try { if (form.IsHandleCreated && form.TopLevel) menu = GetSystemMenu(form.Handle, false); }
            catch (Exception) { menu = IntPtr.Zero; }
            MinimizeButton.AccessibleName = Word(menu, Chrome.SC_MINIMIZE, Chrome.MinimizeWord);
            MaximizeButton.AccessibleName = MaximizeButton.Restores ? Word(menu, Chrome.SC_RESTORE, Chrome.RestoreWord)
                                                                    : Word(menu, Chrome.SC_MAXIMIZE, Chrome.MaximizeWord);
            CloseButton.AccessibleName = Word(menu, Chrome.SC_CLOSE, Chrome.CloseWord);
        }

        private static string Word(IntPtr menu, int command, string fallback)
        {
            if (menu == IntPtr.Zero) return fallback;
            try
            {
                var text = new StringBuilder(128);
                int length = GetMenuString(menu, command, text, text.Capacity, MF_BYCOMMAND);
                return Chrome.CommandName(length > 0 ? text.ToString() : null, fallback);
            }
            catch (Exception) { return fallback; }
        }

        // ------------------------------------------------------------------ what the pointer does

        /// The rectangles a hit test reads, worked out again only once the window's layout has changed since.
        internal ChromeLayout Layout()
        {
            if (!dirty) return layout;
            dirty = false;
            layout.Client = form.ClientSize;
            FormBorderStyle border = form.FormBorderStyle;
            layout.Sizable = border == FormBorderStyle.Sizable || border == FormBorderStyle.SizableToolWindow;
            layout.Maximized = Zoomed;
            layout.Mirrored = Mirror.Of(form);
            layout.Edges = Frameless;
            layout.CornerSpan = Frameless ? corner.Span : 0;
            layout.Band = layout.Sizable ? TopBand() : 0;
            layout.Minimize = Showing(MinimizeButton) ? InForm(MinimizeButton) : Rectangle.Empty;
            layout.Maximize = Showing(MaximizeButton) ? InForm(MaximizeButton) : Rectangle.Empty;
            layout.Close = Showing(CloseButton) ? InForm(CloseButton) : Rectangle.Empty;
            layout.MinimizeOn = MinimizeButton.Enabled;
            layout.MaximizeOn = MaximizeButton.Enabled;
            var solid = new List<Rectangle>();
            AddSolid(form, solid);
            foreach (Control container in drag) AddSolid(container, solid);
            layout.Solid = solid.ToArray();
            layout.SolidCount = layout.Solid.Length;
            return layout;
        }

        private static bool Showing(Control control)
        {
            return Soft.OwnVisible(control) && !control.IsDisposed;
        }

        private void AddSolid(Control container, List<Rectangle> solid)
        {
            foreach (Control child in container.Controls)
            {
                if (child is CaptionButton || drag.Contains(child) || !Soft.OwnVisible(child)) continue;
                solid.Add(InForm(child));
            }
        }

        private Rectangle InForm(Control control)
        {
            int x = 0, y = 0;
            for (Control c = control; c != null && c != form; c = c.Parent)
            {
                x += c.Left;
                y += c.Top;
            }
            return new Rectangle(x, y, control.Width, control.Height);
        }

        // The frame Windows had at the top - its sizing frame and padding at the window's DPI - kept as a band inside the
        // client area that resizes the window from its top edge.
        private int TopBand()
        {
            int dpi = 0;
            try { if (form.IsHandleCreated) dpi = GetDpiForWindow(form.Handle); }
            catch (Exception) { dpi = 0; }
            if (dpi <= 0) dpi = (int)Math.Round(96 * SettingsForm.DpiScale);
            try { return GetSystemMetricsForDpi(SM_CYSIZEFRAME, dpi) + GetSystemMetricsForDpi(SM_CXPADDEDBORDER, dpi); }
            catch (Exception)
            {
                try { return (int)Math.Round((GetSystemMetrics(SM_CYSIZEFRAME) + GetSystemMetrics(SM_CXPADDEDBORDER)) * dpi / 96.0); }
                catch (Exception) { return Soft.Px(8); }
            }
        }

        /// Handles `m` before the form does: true when it is answered here and the form must not see it again.
        internal bool Intercept(ref Message m, Pass pass)
        {
            // v0.6.24: a window held off the screen until it has painted (WindowCorner.Cloak) comes on after its first paint.
            if (corner != null && m.Msg == WM_PAINT && corner.Cloaked)
            {
                try { pass(ref m); }
                finally { corner.Painted(); }
                return true;
            }
            // v0.6.24 W5: the window's own corner first - its frame while it is cut, its region and companion as it moves.
            if (corner != null && corner.Intercept(ref m)) return true;
            if (corner != null && corner.Shaped && (m.Msg == WM_SETTEXT || m.Msg == WM_SETICON) && form.IsHandleCreated)
            {
                Unframed(ref m, pass);
                return true;
            }
            switch (m.Msg)
            {
                case Chrome.WM_NCCALCSIZE:
                    return CalcSize(ref m, pass);
                case WM_WINDOWPOSCHANGED:
                    return PositionChanged(ref m, pass);
                case Chrome.WM_NCHITTEST:
                    if (!form.TopLevel) return false;
                    pass(ref m);
                    if (m.Result.ToInt64() == Chrome.HTCLIENT)
                    {
                        long at = m.LParam.ToInt64();
                        var screen = new Point((short)(at & 0xFFFF), (short)((at >> 16) & 0xFFFF));
                        m.Result = (IntPtr)Chrome.Hit(form.PointToClient(screen), Layout());
                    }
                    return true;
                case Chrome.WM_NCMOUSEMOVE:
                {
                    int code = m.WParam.ToInt32();
                    NcHover(code);
                    // Windows 11 opens its snap layouts from the maximise button's hover: Windows' own handling of the move.
                    // Where there are none (Windows 10) the move goes no further, as over the other two.
                    if (code == Chrome.HTMAXBUTTON && Chrome.SnapLayouts) return false;
                    if (IsButton(code))
                    {
                        m.Result = IntPtr.Zero;
                        return true;
                    }
                    return false;
                }
                case Chrome.WM_NCMOUSELEAVE:
                    tracking = false;
                    NcHover(0);
                    NcPress(0);
                    return false;
                case Chrome.WM_NCLBUTTONDOWN:
                case Chrome.WM_NCLBUTTONDBLCLK:
                {
                    // Never handed on over a button: Windows would track and paint a button of its own there.
                    int code = m.WParam.ToInt32();
                    if (!IsButton(code)) return false;
                    NcPress(code);
                    m.Result = IntPtr.Zero;
                    return true;
                }
                case Chrome.WM_NCLBUTTONUP:
                {
                    int code = m.WParam.ToInt32();
                    if (!IsButton(code)) return false;
                    bool act = ncPressed == code;
                    NcPress(0);
                    if (act) Act(ButtonFor(code));
                    m.Result = IntPtr.Zero;
                    return true;
                }
            }
            return false;
        }

        private const int WM_SETTEXT = 0x000C, WM_SETICON = 0x0080, WM_PAINT = 0x000F, GWL_STYLE = -16, WS_VISIBLE = 0x10000000;

        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")]
        private static extern IntPtr GetWindowLongPtr(IntPtr window, int index);
        [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")]
        private static extern IntPtr SetWindowLongPtr(IntPtr window, int index, IntPtr value);

        // v0.6.24 W5: a new title or icon, taken by Windows' own handling with the window marked hidden for that moment.
        // Windows paints the caption it keeps for those straight onto the window, and while the window's corner is its own
        // that caption is the classic one (WindowCorner.Intercept); marked hidden, it paints nothing. Nothing is shown or
        // hidden: the style bit alone, put back at once.
        private void Unframed(ref Message m, Pass pass)
        {
            IntPtr handle = form.Handle;
            long style = GetWindowLongPtr(handle, GWL_STYLE).ToInt64();
            bool visible = (style & WS_VISIBLE) != 0;
            if (visible) SetWindowLongPtr(handle, GWL_STYLE, new IntPtr(style & ~(long)WS_VISIBLE));
            try { pass(ref m); }
            finally
            {
                if (visible)
                {
                    long now = GetWindowLongPtr(handle, GWL_STYLE).ToInt64();
                    SetWindowLongPtr(handle, GWL_STYLE, new IntPtr(now | WS_VISIBLE));
                }
            }
        }

        private static bool IsButton(int code)
        {
            return code == Chrome.HTMINBUTTON || code == Chrome.HTMAXBUTTON || code == Chrome.HTCLOSE;
        }

        private CaptionButton ButtonFor(int code)
        {
            return code == Chrome.HTMINBUTTON ? MinimizeButton : code == Chrome.HTMAXBUTTON ? MaximizeButton
                 : code == Chrome.HTCLOSE ? CloseButton : null;
        }

        // Windows' own calculation, then its top put back at the window's top (Chrome.ClientFor).
        private bool CalcSize(ref Message m, Pass pass)
        {
            if (m.LParam == IntPtr.Zero) return false;
            var proposed = (Chrome.RECT)Marshal.PtrToStructure(m.LParam, typeof(Chrome.RECT));
            pass(ref m);
            var computed = (Chrome.RECT)Marshal.PtrToStructure(m.LParam, typeof(Chrome.RECT));
            bool maximized = form.IsHandleCreated && form.TopLevel && IsZoomed(form.Handle);
            Rectangle client = Chrome.ClientFor(Rectangle.FromLTRB(proposed.Left, proposed.Top, proposed.Right, proposed.Bottom),
                                                Rectangle.FromLTRB(computed.Left, computed.Top, computed.Right, computed.Bottom),
                                                maximized);
            // Maximised over an auto-hide taskbar: a little of that edge left, or the bar could never be brought out.
            if (maximized)
            {
                try
                {
                    Rectangle monitor = Screen.FromRectangle(Rectangle.FromLTRB(proposed.Left, proposed.Top, proposed.Right, proposed.Bottom)).Bounds;
                    int edges = Chrome.AppBarEdges(monitor);
                    if (edges != 0) client = Chrome.LeaveForAppBars(client, monitor, edges);
                }
                catch (Exception) { /* the whole monitor, as before */ }
            }
            var answer = new Chrome.RECT { Left = client.Left, Top = client.Top, Right = client.Right, Bottom = client.Bottom };
            Marshal.StructureToPtr(answer, m.LParam, false);
            dirty = true;
            return true;
        }

        private const int WM_WINDOWPOSCHANGED = 0x0047;
        // The client the window had as it left its normal state, kept until it is back in it (Restoring).
        private Size restoreClient = Size.Empty;
        private bool restoring;

        // The window moved or changed state. WinForms keeps the client size a window had as it is maximised or minimised
        // (Form.UpdateWindowState) and gives it back on the way to normal (RestoreWindowBoundsIfNecessary) - as a window size
        // worked out with Windows' caption, which this window does not have. The same client is kept here, for Restoring.
        private bool PositionChanged(ref Message m, Pass pass)
        {
            if (!form.TopLevel) return false;
            FormWindowState before = form.WindowState;
            Size client = form.ClientSize;
            // v0.6.24 W5: kept through a message sent inside this one - the window's own corner cut again as it comes back
            // (SetWindowRgn), or the restored size itself - where WinForms gives the remembered size back a second time.
            bool outer = restoring;
            restoring = outer || before != FormWindowState.Normal;
            // Before WinForms handles the message - the one place it gives a kept size back (ForgetRestoredSize).
            ForgetRestoredSize();
            try { pass(ref m); }
            finally { restoring = outer; }
            FormWindowState after = form.WindowState;
            if (before == FormWindowState.Normal && after != FormWindowState.Normal)
            {
                restoreClient = client;
                ForgetRestoredSize();
            }
            else if (after == FormWindowState.Normal) restoreClient = Size.Empty;
            return true;
        }

        private static readonly System.Reflection.FieldInfo RestoredSpecified = typeof(Form).GetField("restoredWindowBoundsSpecified",
            System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);

        /// v0.6.24 W5: WinForms keeps the client size a window had as it leaves its normal state, and gives it back on the
        /// way to normal (Form.UpdateWindowState, RestoreWindowBoundsIfNecessary) - as a window size worked out with
        /// Windows' caption, which Restoring takes back off only where it can tell that is what it is. On the real 150 %
        /// monitor it could not (M-CORNER 2026-11-16: every restore grew the window by Windows' frame and caption at the
        /// system's scale; an unsnap, which WinForms remembers nothing for, did not). Forgotten as the window leaves its
        /// normal state was not enough: WinForms kept it again while the window was maximised (dev CI read All there, on a
        /// 1024 by 768 screen) and, from maximised, gave it back a moment after the restore (M-CORNER re-check: exact, then
        /// 0.1 to 0.35 s later 22 x 56 px bigger, again on every round). So it is forgotten before every
        /// WM_WINDOWPOSCHANGED WinForms handles - the one message it gives it back in - and the window comes back where
        /// Windows keeps it, its normal position, exactly as it left, as every other window does. A size set while the
        /// window is maximised is not given back either: Windows' normal position is the one restored.
        private void ForgetRestoredSize()
        {
            if (RestoredSpecified == null) return;
            try { RestoredSpecified.SetValue(form, BoundsSpecified.None); }
            catch (Exception) { /* Restoring answers what WinForms asks, as before */ }
        }

        /// The size the form's SetBoundsCore is asked for (`created` its CreateParams): on the way back from maximised or
        /// minimised, the window of the client it had then with no caption (Chrome.Uncaptioned) - exactly the size it had -
        /// where WinForms asks for that client's window with Windows' caption counted. Any other size, as asked. A window
        /// whose outer corner is its own again once it is back (Frameless: its corner is decided before this, in the same
        /// message) has no frame at all - its window is that client - or it would come back a frame bigger every time.
        internal void Restoring(ref int width, ref int height, BoundsSpecified specified, CreateParams created)
        {
            if (!restoring || restoreClient.IsEmpty || form.WindowState != FormWindowState.Normal) return;
            if ((specified & BoundsSpecified.Size) == 0) return;
            const int MaximizeOrMinimize = 0x01000000 | 0x20000000;
            int style = created.Style & ~MaximizeOrMinimize;
            Padding frame = Frameless ? Padding.Empty : Chrome.Frame(style, created.ExStyle);
            Size outer = Chrome.Uncaptioned(new Size(width, height), restoreClient, frame,
                                            Chrome.CaptionedFrame(style, created.ExStyle));
            width = outer.Width;
            height = outer.Height;
        }

        private void NcHover(int code)
        {
            if (code == ncHover) return;
            ncHover = code;
            CaptionButton over = IsButton(code) ? ButtonFor(code) : null;
            foreach (CaptionButton button in Buttons()) button.NcHover = button == over;
            if (over != null && !tracking && form.IsHandleCreated)
            {
                var track = new TRACKMOUSEEVENT();
                track.Size = Marshal.SizeOf(typeof(TRACKMOUSEEVENT));
                track.Flags = TME_LEAVE | TME_NONCLIENT;
                track.Window = form.Handle;
                try { tracking = TrackMouseEvent(ref track); }
                catch (Exception) { tracking = false; }
            }
        }

        private void NcPress(int code)
        {
            ncPressed = code;
            CaptionButton down = IsButton(code) ? ButtonFor(code) : null;
            foreach (CaptionButton button in Buttons()) button.NcPressed = button == down;
        }

        /// What a button does, through WM_SYSCOMMAND as Windows' own caption buttons do it - so the minimise animation, the
        /// window's FormClosing and a dialog's DialogResult are what they always were. Posted: a close the button's own click
        /// asks for comes after the click has finished.
        internal void Act(CaptionButton button)
        {
            if (button == null || !button.Enabled || !form.IsHandleCreated || !form.TopLevel) return;
            CloseTip();
            int command = button.Command == Chrome.SC_MAXIMIZE && Zoomed ? Chrome.SC_RESTORE : button.Command;
            PostMessage(form.Handle, Chrome.WM_SYSCOMMAND, (IntPtr)command, IntPtr.Zero);
        }

        // ------------------------------------------------------------------ tooltips (Windows shows one on its buttons)

        /// The pointer came onto `button` or left it: its tooltip after the time Windows waits, or none. The maximise
        /// button shows Windows 11's snap layouts instead.
        internal void Hovered(CaptionButton button, bool on)
        {
            if (on)
            {
                if (button == tipFor && (tip != null || tipWait.Enabled)) return;
                CloseTip();
                if (button == MaximizeButton && Chrome.SnapLayouts) return;
                tipFor = button;
                tipWait.Start();
                return;
            }
            if (button == tipFor) CloseTip();
        }

        private void ShowTip()
        {
            CaptionButton button = tipFor;
            if (button == null || button.IsDisposed || !button.Hot || !form.Visible) return;
            string text = button.AccessibleName ?? "";
            if (text.Length == 0) return;
            const TextFormatFlags flags = TextFormatFlags.SingleLine | TextFormatFlags.NoPrefix | TextFormatFlags.Left | TextFormatFlags.Top;
            Size words = TextRenderer.MeasureText(text, Soft.BaseFont, new Size(int.MaxValue, int.MaxValue), flags);
            bool mirrored = Mirror.Of(form);
            tip = new SoftTipWindow(text, words, Soft.Px(8), Mirror.Words(mirrored, flags));
            Point at = Cursor.Position;
            tip.Show(mirrored ? at.X - tip.CardWidth : at.X, at.Y + Soft.Px(20), Screen.FromPoint(at).WorkingArea, Motion.Allowed(button));
        }

        internal void CloseTip()
        {
            tipWait.Stop();
            tipFor = null;
            if (tip != null) tip.Close(false);
            tip = null;
        }

        public void Dispose()
        {
            if (corner != null) corner.Dispose();
            corner = null;
            CloseTip();
            sceneBeat.Stop();
            sceneBeat.Dispose();
            tipWait.Dispose();
            foreach (DragThrough hook in hooks) hook.Let();
            hooks.Clear();
            foreach (GripThrough grip in grips.Values) grip.Let();
            grips.Clear();
        }
    }

    /// A control that reaches into the window's grip band, giving that band to the window (ChromeHost.Grip): its answer
    /// to what the pointer is over is the window's there (HTTRANSPARENT), its own everywhere else.
    internal sealed class GripThrough : NativeWindow
    {
        private readonly Control control;
        private readonly ChromeHost host;
        private bool let;

        internal GripThrough(Control control, ChromeHost host)
        {
            this.control = control;
            this.host = host;
            control.HandleCreated += delegate { Take(); };
            control.HandleDestroyed += delegate { if (Handle != IntPtr.Zero) ReleaseHandle(); };
            Take();
        }

        private void Take()
        {
            if (let || !control.IsHandleCreated || Handle == control.Handle) return;
            if (Handle != IntPtr.Zero) ReleaseHandle();
            AssignHandle(control.Handle);
        }

        internal void Let()
        {
            let = true;
            if (Handle != IntPtr.Zero) ReleaseHandle();
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == Chrome.WM_NCHITTEST && !let)
            {
                long at = m.LParam.ToInt64();
                if (host.InGrip(new Point((short)(at & 0xFFFF), (short)((at >> 16) & 0xFFFF))))
                {
                    m.Result = (IntPtr)Chrome.HTTRANSPARENT;
                    return;
                }
            }
            base.WndProc(ref m);
        }
    }

    /// A control the window may be dragged by: it hands Windows' question of what the pointer is over on to the window
    /// beneath it (HTTRANSPARENT), which answers it (Chrome.Hit). A line cut short with an ellipsis keeps the question, and
    /// so its tooltip of the whole line.
    internal sealed class DragThrough : NativeWindow
    {
        private readonly Control control;
        private bool let;

        internal DragThrough(Control control)
        {
            this.control = control;
            control.HandleCreated += delegate { Take(); };
            control.HandleDestroyed += delegate { if (Handle != IntPtr.Zero) ReleaseHandle(); };
            Take();
        }

        private void Take()
        {
            if (let || !control.IsHandleCreated || Handle == control.Handle) return;
            if (Handle != IntPtr.Zero) ReleaseHandle();
            AssignHandle(control.Handle);
        }

        internal void Let()
        {
            let = true;
            if (Handle != IntPtr.Zero) ReleaseHandle();
        }

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == Chrome.WM_NCHITTEST && !let && Through())
            {
                m.Result = (IntPtr)Chrome.HTTRANSPARENT;
                return;
            }
            base.WndProc(ref m);
        }

        private bool Through()
        {
            Form form = control.FindForm();
            if (form == null || !form.TopLevel) return false;
            var label = control as Label;
            if (label == null || !label.AutoEllipsis || string.IsNullOrEmpty(label.Text)) return true;
            Size words = TextRenderer.MeasureText(label.Text, label.Font, new Size(int.MaxValue, int.MaxValue),
                                                  TextFormatFlags.SingleLine | TextFormatFlags.NoPrefix);
            return words.Width <= label.ClientSize.Width - label.Padding.Horizontal;
        }
    }

    /// One of the window's caption buttons (minimise, maximise or close): its body only under the pointer - the soft well
    /// the tabs are pressed into, close filled red - gliding in the house's transition, its glyph drawn at the window's
    /// scale. Never in the Tab order and never given the keyboard, as Windows' are not; a screen reader finds it as a push
    /// button named with Windows' own word (ChromeHost.Names).
    internal sealed class CaptionButton : Control
    {
        private readonly ChromeHost host;
        internal readonly int Command;
        private readonly SoftSurfaceGlide glide;
        private bool hover, pressed, ncHover, ncPressed, restores;

        internal CaptionButton(ChromeHost host, int command)
        {
            this.host = host;
            Command = command;
            SetStyle(ControlStyles.UserPaint | ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer |
                     ControlStyles.ResizeRedraw, true);
            SetStyle(ControlStyles.Selectable, false);
            TabStop = false;
            AccessibleRole = AccessibleRole.PushButton;
            AccessibleName = command == Chrome.SC_MINIMIZE ? Chrome.MinimizeWord
                           : command == Chrome.SC_MAXIMIZE ? Chrome.MaximizeWord : Chrome.CloseWord;
            glide = new SoftSurfaceGlide(this, Wanted);
        }

        /// The maximise button of a maximised window: its glyph two squares, its command Restore.
        internal bool Restores
        {
            get { return restores; }
            set
            {
                if (restores == value) return;
                restores = value;
                Invalidate();
            }
        }

        /// Under the pointer or held down, by the client's mouse or by the window's (the maximise button and, maximised,
        /// the strips over the buttons are the window's: ChromeHost.NcHover).
        internal bool Hot { get { return hover || ncHover; } }
        internal bool Down { get { return (pressed && hover) || ncPressed; } }

        internal bool NcHover
        {
            set
            {
                if (ncHover == value) return;
                ncHover = value;
                if (!value) ncPressed = false;
                Changed(false);
                host.Hovered(this, Hot);
            }
        }

        internal bool NcPressed
        {
            set
            {
                if (ncPressed == value) return;
                ncPressed = value;
                Changed(true);
            }
        }

        private void Changed(bool press)
        {
            glide.Changed(press ? Motion.Press : Motion.Duration);
            Invalidate();
        }

        /// What its state looks like: nothing but the glyph at rest, in `muted`; under the pointer a well and the glyph in
        /// ink - close filled with Danger and its glyph on it - and held down, the well's hairline (close: Danger 15 % of
        /// the way to ink). Faint and still where the window does not offer it. High Contrast: the person's Highlight.
        private SurfaceLook Wanted()
        {
            Color muted = Palette.Contrast ? SystemColors.WindowText : !overScene.IsEmpty ? overScene : Palette.Muted;
            Color none = SurfaceLook.None(Palette.Inset);
            // High Contrast: what is not offered is in the person's GrayText, as Windows draws a command that is off.
            if (!Enabled) return new SurfaceLook(none, none, Palette.Contrast ? SystemColors.GrayText : Soft.WithAlpha(muted, 0.43));
            if (!Hot && !Down) return new SurfaceLook(none, none, muted);
            if (Palette.Contrast) return new SurfaceLook(SystemColors.Highlight, SystemColors.Highlight, SystemColors.HighlightText);
            if (Command == Chrome.SC_CLOSE)
            {
                Color red = Down ? Soft.Mix(Palette.Danger, Palette.Ink, 0.15) : Palette.Danger;
                return new SurfaceLook(red, red, Palette.OnAccent);
            }
            return Down ? new SurfaceLook(Palette.Inset, Palette.Line, Palette.Ink)
                        : new SurfaceLook(Palette.Inset, Palette.Inset, Palette.Ink);
        }

        protected override void WndProc(ref Message m)
        {
            // The maximise button is the window's (HTMAXBUTTON, Chrome.Hit): Windows 11's snap layouts are asked of it there.
            if (m.Msg == Chrome.WM_NCHITTEST && Command == Chrome.SC_MAXIMIZE && Enabled)
            {
                Form form = FindForm();
                if (form != null && form.TopLevel)
                {
                    m.Result = (IntPtr)Chrome.HTTRANSPARENT;
                    return;
                }
            }
            base.WndProc(ref m);
        }

        protected override void OnMouseEnter(EventArgs e)
        {
            hover = true;
            Changed(false);
            host.Hovered(this, true);
            base.OnMouseEnter(e);
        }

        protected override void OnMouseLeave(EventArgs e)
        {
            hover = false;
            pressed = false;
            Changed(false);
            host.Hovered(this, Hot);
            base.OnMouseLeave(e);
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left)
            {
                pressed = true;
                host.CloseTip();
                Changed(true);
            }
            base.OnMouseDown(e);
        }

        protected override void OnMouseUp(MouseEventArgs e)
        {
            bool act = pressed && e.Button == MouseButtons.Left && ClientRectangle.Contains(e.Location);
            pressed = false;
            Changed(true);
            base.OnMouseUp(e);
            if (act) host.Act(this);
        }

        protected override void OnEnabledChanged(EventArgs e)
        {
            base.OnEnabledChanged(e);
            glide.Changed();
            Invalidate();
        }

        // The glyph's colour at rest over the day's scene where the button stands (Chrome.OverScene), worked out each time the
        // scene under it is drawn; Empty on every other day, and wherever `muted` already stands out.
        private Color overScene = Color.Empty;

        /// What the glyph is drawn in at rest over the day's scene, or Empty (for the tests).
        internal Color OverSceneInk { get { return overScene; } }

        protected override void OnPaintBackground(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            SoftDayScene scene = host.Scene;
            Rectangle at = scene == null || scene.IsDisposed || !scene.Visible || scene.Look == null ? Rectangle.Empty : host.InHolder(scene);
            if (at.IsEmpty || !at.IntersectsWith(Bounds) || Width <= 0 || Height <= 0)
            {
                overScene = Color.Empty;
                g.FillRectangle(Soft.Fill(host.Face), ClientRectangle);
                return;
            }
            // The day's scene where it lies under the button, drawn by the scene itself - into a picture of the button, so
            // the glyph can be held to what is under it (O6) - then laid down.
            var under = Rectangle.Intersect(new Rectangle(Left - at.Left, Top - at.Top, Width, Height), scene.ClientRectangle);
            using (var drawn = new Bitmap(Width, Height, PixelFormat.Format32bppArgb))
            {
                using (Graphics b = Graphics.FromImage(drawn))
                {
                    b.FillRectangle(Soft.Fill(host.Face), new Rectangle(0, 0, Width, Height));
                    b.TranslateTransform(at.Left - Left, at.Top - Top);
                    b.SetClip(under, CombineMode.Intersect);
                    if (scene.Region != null) b.SetClip(scene.Region, CombineMode.Intersect);
                    using (var args = new PaintEventArgs(b, under)) InvokePaint(scene, args);
                }
                g.DrawImageUnscaled(drawn, 0, 0);
                overScene = Palette.Contrast ? Color.Empty
                          : Chrome.OverScene(UnderGlyph(drawn), Palette.Muted, Palette.Ink, Palette.OnAccent);
            }
        }

        // The mean colour of what lies in the glyph's box (Glyph) in a picture of the button.
        private Color UnderGlyph(Bitmap drawn)
        {
            int box = Math.Max(1, Soft.Px(Brand.CaptionGlyph));
            var glyph = Rectangle.Intersect(new Rectangle((Width - box) / 2, (Height - box) / 2, box, box), new Rectangle(0, 0, Width, Height));
            if (glyph.Width <= 0 || glyph.Height <= 0) return host.Face;
            BitmapData data = drawn.LockBits(glyph, ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
            long r = 0, gr = 0, bl = 0;
            try
            {
                var row = new int[glyph.Width];
                for (int y = 0; y < glyph.Height; y++)
                {
                    Marshal.Copy(new IntPtr(data.Scan0.ToInt64() + (long)y * data.Stride), row, 0, glyph.Width);
                    foreach (int pixel in row)
                    {
                        r += (pixel >> 16) & 0xFF;
                        gr += (pixel >> 8) & 0xFF;
                        bl += pixel & 0xFF;
                    }
                }
            }
            finally { drawn.UnlockBits(data); }
            int count = glyph.Width * glyph.Height;
            return Color.FromArgb(255, (int)(r / count), (int)(gr / count), (int)(bl / count));
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            Graphics g = e.Graphics;
            SurfaceLook look = glide.Now;
            Rectangle face = ClientRectangle;
            float radius = Soft.PxF(Palette.RadiusSmall);
            if (look.Fill.A > 0 || look.Edge.A > 0)
            {
                // The well's inset shadow cannot fade: it comes in past half way, as a tab's does (NavButton).
                bool well = Command != Chrome.SC_CLOSE && Palette.Depth && !Palette.Contrast && Enabled && glide.Progress >= 0.5 &&
                            (Hot || Down);
                Soft.Body(g, face, radius, look.Fill, look.Edge, well);
            }
            Glyph(g, look.Ink);
        }

        /// The glyph in a box Brand.CaptionGlyph across, centred: minimise a line, maximise a square with small round
        /// corners, restore two of them, close a cross - each in a stroke of Brand.CaptionStroke, never under a device pixel,
        /// with round ends.
        internal void Glyph(Graphics g, Color ink)
        {
            float unit = Soft.PxF(1.0), box = Soft.PxF(Brand.CaptionGlyph);
            float ox = (float)Math.Round((Width - box) / 2f), oy = (float)Math.Round((Height - box) / 2f);
            float stroke = Math.Max(1f, Soft.PxF(Brand.CaptionStroke));
            float corner = Soft.PxF(Brand.CaptionGlyphCorner);
            GraphicsState state = g.Save();
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.PixelOffsetMode = PixelOffsetMode.Half;
            using (var pen = new Pen(ink, stroke))
            {
                pen.StartCap = LineCap.Round;
                pen.EndCap = LineCap.Round;
                pen.LineJoin = LineJoin.Round;
                Func<double, float> x = delegate(double at) { return ox + (float)at * unit; };
                Func<double, float> y = delegate(double at) { return oy + (float)at * unit; };
                if (Command == Chrome.SC_MINIMIZE)
                    g.DrawLine(pen, x(0.5), y(5.5), x(9.5), y(5.5));
                else if (Command == Chrome.SC_CLOSE)
                {
                    g.DrawLine(pen, x(1), y(1), x(9), y(9));
                    g.DrawLine(pen, x(9), y(1), x(1), y(9));
                }
                else if (!restores)
                {
                    using (GraphicsPath square = Soft.Rounded(new RectangleF(x(0.65), y(0.65), 8.7f * unit, 8.7f * unit), corner))
                        g.DrawPath(pen, square);
                }
                else
                {
                    using (GraphicsPath front = Soft.Rounded(new RectangleF(x(0.65), y(2.35), 7f * unit, 7f * unit), corner))
                        g.DrawPath(pen, front);
                    // The square behind: what shows of it above and right of the front one.
                    using (var back = new GraphicsPath())
                    {
                        float left = x(2.35), top = y(0.65), right = x(9.35), bottom = y(7.65), d = 2 * corner;
                        back.AddLine(left, y(2.35), left, top + corner);
                        back.AddArc(left, top, d, d, 180, 90);
                        back.AddLine(left + corner, top, right - corner, top);
                        back.AddArc(right - d, top, d, d, 270, 90);
                        back.AddLine(right, top + corner, right, bottom - corner);
                        back.AddArc(right - d, bottom - d, d, d, 0, 90);
                        back.AddLine(right - corner, bottom, x(7.65), bottom);
                        g.DrawPath(pen, back);
                    }
                }
            }
            g.Restore(state);
        }

        protected override AccessibleObject CreateAccessibilityInstance()
        {
            return new CaptionAccessible(this);
        }

        internal void Press()
        {
            host.Act(this);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) glide.Dispose();
            base.Dispose(disposing);
        }

        private sealed class CaptionAccessible : ControlAccessibleObject
        {
            private readonly CaptionButton owner;

            internal CaptionAccessible(CaptionButton owner) : base(owner) { this.owner = owner; }

            public override AccessibleRole Role { get { return AccessibleRole.PushButton; } }

            public override string DefaultAction { get { return "Press"; } }

            public override void DoDefaultAction() { owner.Press(); }

            public override AccessibleStates State
            {
                get
                {
                    AccessibleStates state = base.State;
                    if (!owner.Enabled) state |= AccessibleStates.Unavailable;
                    if (owner.Hot) state |= AccessibleStates.HotTracked;
                    if (owner.Down) state |= AccessibleStates.Pressed;
                    return state;
                }
            }
        }
    }

    /// A dialog of the window's (v0.6.24): a Form whose caption is ours. Its ClientSize means what it says - a Form works
    /// its window out from its styles, which still count WS_CAPTION - and Soft.DialogBar gives it its title row and the
    /// caption buttons in it (BuildTitle) as its window is made, once its own code has laid it out: a strip docked at its top, the
    /// last control it holds and so the first docked (Windows' docking goes from the last-added control inward). Since
    /// v0.6.24-beta.2 (the owner's choice B, 2026-11-16) the title is no card: its words and buttons stand on the dialog's own
    /// ground, in one row 8 px below its top and 8 px above its first card, 16 px in from its edges as its body card is - 42
    /// logical px where the title card took 62. The dialog grows once by the strip; everything it laid out stands below it as
    /// it stood, and its own controls keep their places in Controls.
    internal sealed class SoftDialog : Form
    {
        private ChromeHost chrome;
        private Panel titleGround;
        private TitleRowPanel titleRow;
        private Label titleWords;
        internal bool Titled;

        /// The title row, its words, the strip it stands in and the caption it holds (null until the dialog is made): for
        /// the tests and the audit.
        internal Panel TitleRow { get { return titleRow; } }
        internal Label TitleWords { get { return titleWords; } }
        internal Panel TitleGround { get { return titleGround; } }
        internal ChromeHost CaptionHost { get { return chrome; } }

        /// The title row's measures in logical px: the ground above and below it, and how far in from the side gap its words
        /// start (the mockup the owner chose).
        internal const int TitleAbove = 8, TitleWordsInset = 6;

        /// How much of the dialog's height its title takes once it is made: 0 before.
        internal int TitleReserve { get { return titleGround == null ? 0 : titleGround.Height; } }

        /// The same of any dialog: what a dialog that fits its height to what it holds adds for its title.
        internal static int TitleRoom(Form dialog)
        {
            var soft = dialog as SoftDialog;
            return soft == null ? 0 : soft.TitleReserve;
        }

        // Made just before its window is - by ShowDialog, or by the first of its controls to need a window (the layout audit,
        // the render mode) - so its own code has laid it out, and the window is made with the title already in it.
        protected override void CreateHandle()
        {
            MakeTitle();
            base.CreateHandle();
        }

        /// Its title row now, if Soft.DialogBar asked for one and it has none yet: for what lays a dialog out without making
        /// its window (the layout audit's Materialise makes its controls' windows alone).
        internal void MakeTitle()
        {
            if (Titled && titleRow == null) BuildTitle();
        }

        // A control the dialog's code adds after the title (one that needed a window early): the strip stays the last, the
        // first docked.
        protected override void OnControlAdded(ControlEventArgs e)
        {
            base.OnControlAdded(e);
            if (titleGround != null && e.Control != titleGround && titleGround.Parent == this)
                Controls.SetChildIndex(titleGround, Controls.Count - 1);
        }

        private void BuildTitle()
        {
            int gap = Soft.Px(16), above = Soft.Px(TitleAbove);
            titleGround = new Panel();
            titleGround.BackColor = BackColor;
            titleGround.Margin = new Padding(0);
            // The row and its words take the ground's colour from what they stand in: no card of their own.
            titleRow = new TitleRowPanel();
            titleRow.Margin = new Padding(0);
            titleWords = new Label();
            titleWords.AutoSize = false;
            titleWords.Dock = DockStyle.Fill;
            titleWords.Margin = new Padding(0);
            // One step under a card's title (RoleFont "title", 1.5 pt larger): the window's font at 600, a heading's.
            titleWords.Font = Soft.RoleFont("heading");
            titleWords.ForeColor = Palette.Ink;
            titleWords.TextAlign = ContentAlignment.MiddleLeft;
            titleWords.AutoEllipsis = true;
            titleWords.UseMnemonic = false;
            titleWords.Text = Text;
            TextChanged += delegate { if (titleWords != null) titleWords.Text = Text; };
            titleRow.Controls.Add(titleWords);
            int line = Math.Max(titleWords.Font.Height,
                                TextRenderer.MeasureText("Ag", titleWords.Font, new Size(int.MaxValue, 0), TextFormatFlags.NoPrefix).Height);
            int height = Math.Max(line, Soft.Px(Brand.CaptionButtonH));
            titleGround.Height = above + height + above;
            titleGround.Width = ClientSize.Width;
            titleRow.SetBounds(gap, above, Math.Max(1, ClientSize.Width - 2 * gap), height);
            titleRow.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            titleGround.Controls.Add(titleRow);
            chrome = ChromeHost.Install(this, titleRow, titleGround);
            chrome.OnGround = true;
            chrome.Drag(titleWords);
            // The words start TitleWordsInset in from the side gap and stop short of the buttons; the row mirrors its own
            // padding (Mirror.Display).
            int end = Soft.Px(Brand.CaptionInsetEnd) + chrome.GroupWidth + Soft.Px(8);
            titleRow.Padding = new Padding(Soft.Px(TitleWordsInset), 0, end, 0);
            int grown = titleGround.Height;
            SuspendLayout();
            titleGround.Dock = DockStyle.Top;
            Controls.Add(titleGround);
            ClientSize = new Size(ClientSize.Width, ClientSize.Height + grown);
            ResumeLayout(true);
            chrome.Place();
        }

        /// The title row: a plain panel on the dialog's ground whose padding is mirrored in a mirrored dialog, as a card's is.
        internal sealed class TitleRowPanel : Panel
        {
            public override Rectangle DisplayRectangle
            {
                get { return Mirror.Display(this, base.DisplayRectangle); }
            }
        }

        protected override void WndProc(ref Message m)
        {
            if (chrome != null && chrome.Intercept(ref m, PassOn)) return;
            // Centred on the window that opened it as it is first shown (OnOwner): the caption leaves this message alone.
            if (m.Msg == WM_WINDOWPOSCHANGING && !placed) OnOwner(m.LParam);
            if (chrome == null && m.Msg == Chrome.WM_NCCALCSIZE && CalcSizeEarly(ref m)) return;
            base.WndProc(ref m);
        }

        // ------------------------------------------------------------------ centred on the window that opened it

        [StructLayout(LayoutKind.Sequential)]
        private struct WINDOWPOS { public IntPtr Window, After; public int X, Y, Width, Height; public uint Flags; }

        [DllImport("user32.dll")]
        private static extern IntPtr GetWindow(IntPtr window, int command);
        [DllImport("user32.dll")]
        private static extern bool IsIconic(IntPtr window);
        [DllImport("user32.dll")]
        private static extern bool IsWindowVisible(IntPtr window);
        [DllImport("user32.dll")]
        private static extern bool GetWindowRect(IntPtr window, out Chrome.RECT rect);
        [DllImport("dwmapi.dll")]
        private static extern int DwmGetWindowAttribute(IntPtr window, int attribute, out Chrome.RECT rect, int size);

        private const int WM_WINDOWPOSCHANGING = 0x0046, GW_OWNER = 4, DWMWA_EXTENDED_FRAME_BOUNDS = 9;
        private const uint SWP_NOSIZE = 0x0001, SWP_NOMOVE = 0x0002, SWP_SHOWWINDOW = 0x0040;
        private bool placed;

        /// The work area of the monitor the window `owner` is on, which a dialog over it is kept inside: what the tests stub.
        internal static Func<IntPtr, Rectangle> WorkAreaOf = delegate(IntPtr owner) { return Screen.FromHandle(owner).WorkingArea; };

        /// v0.6.24 (the owner, 2026-11-16: wherever the Dashboard is, its dialogs open at its middle, not the monitor's): a
        /// dialog asked to open centred on its owner (StartPosition.CenterParent) is placed as it is first shown - the last
        /// moment before it is on a screen, whatever moved it before - its visible box (DWM's frame bounds: Windows'
        /// invisible borders not counted) centred on its owner's, held inside the work area of the monitor the owner is on
        /// (Chrome.CentreOn). Only once: a dialog moved by hand stays where it is put. A dialog with no owner on the screen -
        /// none, or only WinForms' hidden taskbar owner - is left where WinForms put it (CenterScreen).
        private void OnOwner(IntPtr lParam)
        {
            if (lParam == IntPtr.Zero || !IsHandleCreated) return;
            var pos = (WINDOWPOS)Marshal.PtrToStructure(lParam, typeof(WINDOWPOS));
            if ((pos.Flags & SWP_SHOWWINDOW) == 0) return;
            placed = true;
            if (StartPosition != FormStartPosition.CenterParent || WindowState != FormWindowState.Normal || !TopLevel) return;
            try
            {
                IntPtr owner = GetWindow(Handle, GW_OWNER);
                if (owner == IntPtr.Zero || !IsWindowVisible(owner) || IsIconic(owner)) return;
                Chrome.RECT box, ownerBox;
                if (!GetWindowRect(Handle, out box) || !GetWindowRect(owner, out ownerBox)) return;
                Rectangle whole = Rectangle.FromLTRB(box.Left, box.Top, box.Right, box.Bottom);
                Rectangle seen = Seen(Handle, whole);
                var inset = new Padding(seen.Left - whole.Left, seen.Top - whole.Top, whole.Right - seen.Right, whole.Bottom - seen.Bottom);
                Size size = (pos.Flags & SWP_NOSIZE) != 0 ? whole.Size : new Size(pos.Width, pos.Height);
                var visible = new Size(Math.Max(0, size.Width - inset.Horizontal), Math.Max(0, size.Height - inset.Vertical));
                Rectangle over = Seen(owner, Rectangle.FromLTRB(ownerBox.Left, ownerBox.Top, ownerBox.Right, ownerBox.Bottom));
                Point at = Chrome.CentreOn(over, visible, WorkAreaOf(owner));
                pos.X = at.X - inset.Left;
                pos.Y = at.Y - inset.Top;
                pos.Flags &= ~SWP_NOMOVE;
                Marshal.StructureToPtr(pos, lParam, false);
            }
            catch (Exception) { /* where WinForms put it */ }
        }

        // What a person sees of `window`, whose window rectangle is `whole`: DWM's frame bounds, where DWM gives sensible
        // ones (inside `whole`, no more than 64 px in at a side); otherwise the window rectangle.
        private static Rectangle Seen(IntPtr window, Rectangle whole)
        {
            try
            {
                Chrome.RECT r;
                if (DwmGetWindowAttribute(window, DWMWA_EXTENDED_FRAME_BOUNDS, out r, Marshal.SizeOf(typeof(Chrome.RECT))) != 0)
                    return whole;
                Rectangle seen = Rectangle.FromLTRB(r.Left, r.Top, r.Right, r.Bottom);
                bool sensible = seen.Width > 0 && seen.Height > 0 && whole.Contains(seen)
                             && seen.Left - whole.Left <= 64 && seen.Top - whole.Top <= 64
                             && whole.Right - seen.Right <= 64 && whole.Bottom - seen.Bottom <= 64;
                return sensible ? seen : whole;
            }
            catch (Exception) { return whole; }
        }

        // The client calculation before the title row exists (the window is being made): the caption is ours from the
        // first one, so the window is never laid out with Windows' caption.
        private bool CalcSizeEarly(ref Message m)
        {
            if (m.LParam == IntPtr.Zero) return false;
            var proposed = (Chrome.RECT)Marshal.PtrToStructure(m.LParam, typeof(Chrome.RECT));
            base.WndProc(ref m);
            var computed = (Chrome.RECT)Marshal.PtrToStructure(m.LParam, typeof(Chrome.RECT));
            Rectangle client = Chrome.ClientFor(Rectangle.FromLTRB(proposed.Left, proposed.Top, proposed.Right, proposed.Bottom),
                                                Rectangle.FromLTRB(computed.Left, computed.Top, computed.Right, computed.Bottom),
                                                false);
            var answer = new Chrome.RECT { Left = client.Left, Top = client.Top, Right = client.Right, Bottom = client.Bottom };
            Marshal.StructureToPtr(answer, m.LParam, false);
            return true;
        }

        private void PassOn(ref Message m)
        {
            base.WndProc(ref m);
        }

        private Padding OwnFrame()
        {
            CreateParams created = CreateParams;
            return Chrome.Frame(created.Style, created.ExStyle);
        }

        protected override Size SizeFromClientSize(Size clientSize)
        {
            return Chrome.WindowSize(clientSize, OwnFrame());
        }

        // The window made at the size its ClientSize says: Form fills it in with Windows' caption counted (Chrome.Uncaption).
        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams created = base.CreateParams;
                Chrome.Uncaption(created, ClientSize);
                return created;
            }
        }

        protected override void SetClientSizeCore(int x, int y)
        {
            SuspendLayout();
            try
            {
                base.SetClientSizeCore(x, y);
                Size outer = SizeFromClientSize(new Size(x, y));
                if (Size != outer) Size = outer;
                // As Control.SetClientSizeCore keeps it: the client asked for, even where Form held the window to the
                // largest the screen allows (SystemInformation.MaxWindowTrackSize) - which a picture drawn at a pinned
                // scale then sizes itself past with SetWindowPos (WindowRender.OpenForRender).
                if (ClientSize != new Size(x, y)) UpdateBounds(Left, Top, Width, Height, x, y);
            }
            finally { ResumeLayout(true); }
        }

        protected override void SetBoundsCore(int x, int y, int width, int height, BoundsSpecified specified)
        {
            // Back from maximised or minimised at the size it had (ChromeHost.Restoring).
            if (chrome != null) chrome.Restoring(ref width, ref height, specified, CreateParams);
            base.SetBoundsCore(x, y, width, height, specified);
            if (IsHandleCreated) return;
            Size client = Chrome.ClientOf(Size, OwnFrame());
            if (client != ClientSize) UpdateBounds(Left, Top, Width, Height, client.Width, client.Height);
        }
    }
}
