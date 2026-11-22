// Codex Auto Resume - the render mode: the window drawing frames of itself, offscreen, for the documentation's
// motion pictures (build/make_motion.py).
//
// Never a window a person opens: it runs only when build/motion_window.py names a render job in
// CODEX_AR_RENDER_PLAN beside a capture's event (Soft.StillReady), and then the window is built as LayoutAudit
// builds it - never shown, not even a top-level window - answered from the job's own canned replies instead of
// a bridge, so nothing is read from an installation, nothing is written anywhere but the job's folder, and no
// process is started. For each frame of the job it is put in a state - a page, a Settings section, a scroll
// offset, a control's hover or pressed face, a drop-down's value, its open list, a Pending row chosen and its own
// menu open (v0.6.18), an action in flight (v0.6.20: SetBusy), the answers of another state of the installation
// (paused), Why it is waiting scrolled, a dialog the window opened (Timeline) over it with the veil under it, the moment
// of its lights and of the light's sweep (v0.6.24) - waits until it holds still as a capture waits (Settled), and draws
// itself into a bitmap; only what changed since the frame before is written. v0.6.26 (audit-apng M3-M7): the row menu,
// a drop-down's list and a dialog fade in at the frame's moment of their opening, the menu and the list fade out, a
// drop-down with its list open looks open, and Retry now's answer is taken as the window takes it. v0.6.26 (audit-apng
// M6): a frame that carries its moment on the picture's clock (`moment`, build/motion_window.frame_state) is drawn with
// every glide at that moment - a control's hover and press, the current tab, the busy look, the light's colour - each
// begun by the control's own change at the frame it began at and drawn at each frame after on the picture's clock
// (Transition.RenderMs), never the wall clock's.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal sealed partial class SettingsForm
    {
        // ------------------------------------------------------------------ render mode
        [DllImport("user32.dll")]
        private static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int width, int height, uint flags);
        private const uint SwpNoMove = 0x0002, SwpNoZOrder = 0x0004, SwpNoActivate = 0x0010;

        [DllImport("user32.dll", EntryPoint = "SendMessageW")]
        private static extern IntPtr SendRenderMessage(IntPtr window, int message, IntPtr wParam, IntPtr lParam);

        private const int WM_UPDATEUISTATE = 0x0128;
        // UIS_SET with UISF_HIDEFOCUS | UISF_HIDEACCEL: a window as a person using the mouse sees it, as every capture
        // is taken (build/capture_window.ps1).
        private static readonly IntPtr HideCues = (IntPtr)0x00030001;
        // The longest a state may take to hold still, in milliseconds; a frame drawn past it says so.
        private const int RenderSettleLimit = 20000;
        // How many lines a turn of the wheel scrolls in a picture: Windows' own default, whatever this machine says.
        internal const int RenderWheelLines = 3;

        /// Set on a window the render mode builds: it never starts another window of itself (Reopen).
        private bool rendering;

        /// The render job's file, or null - which is what anybody running the product gets. Only beside a capture's
        /// event (Soft.StillReady), as every hook of the pictures is.
        internal static string RenderJob
        {
            get
            {
                if (Soft.StillReady == null) return null;
                try
                {
                    string path = Environment.GetEnvironmentVariable("CODEX_AR_RENDER_PLAN");
                    return string.IsNullOrEmpty(path) || !File.Exists(path) ? null : path;
                }
                catch (Exception) { return null; }
            }
        }

        // The replies the window being rendered is given, and every read it made that they did not answer.
        private static List<object> renderAnswers;
        private static readonly List<string> RenderMisses = new List<string>();

        /// A read answered from the job's replies: the one for exactly this argument, else the one the job gave for
        /// the command whatever its argument. Anything else - every command that changes something among them - is
        /// refused, and noted.
        private static Dictionary<string, object> RenderAnswer(string command, string argument)
        {
            Dictionary<string, object> any = null;
            string asked = Compact(argument);
            lock (RenderMisses)
            {
                foreach (object item in renderAnswers ?? new List<object>())
                {
                    var answer = item as Dictionary<string, object>;
                    if (answer == null || Str(answer, "command") != command) continue;
                    object given;
                    answer.TryGetValue("argument", out given);
                    var reply = Map(answer, "reply");
                    if (given == null) { if (any == null) any = reply; continue; }
                    if (Compact(Convert.ToString(given, CultureInfo.InvariantCulture)) == asked) return Copy(reply);
                }
                if (any != null) return Copy(any);
                RenderMisses.Add(command + (string.IsNullOrEmpty(argument) ? "" : " " + argument));
            }
            var refused = new Dictionary<string, object>();
            refused["ok"] = false;
            refused["error"] = "not answered in the render";
            return refused;
        }

        private static string Compact(string json)
        {
            if (string.IsNullOrEmpty(json)) return "";
            try { return Json.Write(Json.Parse(json)); }
            catch (Exception) { return json; }
        }

        // Each read gets a reply of its own: the window keeps and changes what it is given.
        private static Dictionary<string, object> Copy(Dictionary<string, object> reply)
        {
            return reply == null ? null : Json.Parse(Json.Write(reply)) as Dictionary<string, object>;
        }

        /// Draws the job's frames into its folder and ends: 0 when every frame was drawn, 2 when the job could not be
        /// read. What went wrong, and every read nobody answered, is in the folder's frames.json.
        internal static int RenderFrames(string jobPath)
        {
            var job = Json.Parse(File.ReadAllText(jobPath, new UTF8Encoding(false))) as Dictionary<string, object>;
            if (job == null) return 2;
            string folder = Str(job, "out");
            if (string.IsNullOrEmpty(folder)) return 2;
            Directory.CreateDirectory(folder);
            var writer = new RenderWriter(folder);
            SettingsForm form = null;
            string formLocale = null;
            try
            {
                string theme = Str(job, "theme"), design = Str(job, "design");
                if (theme == null || design == null) throw new InvalidDataException("the job names no theme or design");
                Theme.Opened = theme;
                Design.Opened = design;
                Palette.AdoptDesign(design);
                Palette.Adopt(Theme.Current(theme));
                AdoptRenderScale(job);
                Soft.StillLightMs = 0;
                PersistentBridge.Answers = RenderAnswer;
                // The colour of the border Windows draws round a dialog (RenderDialog). v0.6.24: the job's `outer` is not read -
                // no window has Windows' caption, so the window the picture frames is its client area.
                renderChrome = Map(job, "chrome");
                // v0.6.20: each frame also as the still a capture takes of the window (FramedStill), when the job asks.
                renderStill = Map(job, "still");
                // v0.6.24: each frame with the window's own outer edge - its squircle corner and hairline, cut as a still is
                // (CornerStill) - when the job asks (`edge_dpi`, motion_window.frame_edge): the motion's and the Advanced-page
                // pictures' frames are then what the stills are, edge and all.
                object edgeDpi;
                renderEdgeDpi = job.TryGetValue("edge_dpi", out edgeDpi) && edgeDpi != null
                    ? Convert.ToInt32(edgeDpi, CultureInfo.InvariantCulture) : 0;
                // The job's command line, read as the window's own is (ParseArguments), for what a page takes from it:
                // the advanced edition's `--capability=`. The standard window takes nothing here.
                var arguments = new List<string>();
                foreach (object argument in Items(job, "arguments") ?? new List<object>())
                    arguments.Add(Convert.ToString(argument, CultureInfo.InvariantCulture));
                ParseArguments(arguments.ToArray());
                var forms = Map(job, "forms") ?? new Dictionary<string, object>();
                var targets = Items(job, "targets") ?? new List<object>();
                // v0.6.26 (audit-apng M6): a job whose frames carry their moment draws every glide on the picture's clock
                // (Transition.RenderMs, set for each frame below), and as a person with Windows' animation effects on sees it
                // (the default), whatever this machine's switch says - GitHub's runner has it off (Soft.WindowsAnimates) -
                // so the picture is the same on any machine, as the light's moment is pinned (Soft.StillLightMs). The render
                // stands its own answer in that input as a probe does; a job without moments (the stills, the fidelity check)
                // is as before.
                Dictionary<string, object> before = null;
                string beforeLocale = null;
                if (Clocked(Items(job, "frames"))) Soft.WindowsAnimates = delegate { return true; };
                foreach (object item in Items(job, "frames") ?? new List<object>())
                {
                    var frame = item as Dictionary<string, object>;
                    if (frame == null) continue;
                    string locale = Str(frame, "locale") ?? "en";
                    double moment = RenderMs(frame, "moment");
                    // Another state of the installation answers its reads (a paused watcher: `variant` "paused" reads
                    // the replies the job gives for "<locale>-paused"): the window is opened again on them, as it is for
                    // another language.
                    string variant = Str(frame, "variant");
                    string answersOf = variant == null ? locale : locale + "-" + variant;
                    bool opened = form == null || formLocale != answersOf;
                    if (opened)
                    {
                        // v0.6.26 (audit-apng M6): another state of the installation in the same language is the same window on
                        // a screen, its answer just come: the window opened again on it is first put, arrived, in the state the
                        // frame before showed (an action in flight, its light the working one), and this frame's changes - the
                        // call over, the light to the paused colour - glide from there at its moment, as the window glides them.
                        // A new language is a window opened again (Reopen): arrived, as it opens.
                        Dictionary<string, object> carried = form != null && moment >= 0 && before != null && beforeLocale == locale
                            ? Carried(before) : null;
                        if (form != null) form.Dispose();
                        form = null;
                        Transition.RenderMs = Transition.Live;
                        renderAnswers = Items(Map(forms, answersOf), "answers");
                        form = OpenForRender(writer);
                        formLocale = answersOf;
                        if (carried != null)
                        {
                            Transition.RenderMs = Transition.Arrived;
                            form.RenderState(carried, writer);
                            opened = false;
                        }
                    }
                    // The frame's moment; the first frame of a window opened anew is set up as it stands.
                    Transition.RenderMs = moment < 0 ? Transition.Live : opened ? Transition.Arrived : moment;
                    form.RenderState(frame, writer);
                    before = frame;
                    beforeLocale = locale;
                    int index = Convert.ToInt32(frame["index"], CultureInfo.InvariantCulture);
                    // v0.6.26: a frame with the window's own edge is cut before what lies over the window is laid (EdgeFirst).
                    using (Bitmap picture = form.RenderPicture(frame, writer))
                    {
                        if (renderEdgeDpi > 0 && !EdgeFirst)
                            using (Bitmap edged = CornerStill(picture, renderEdgeDpi))
                                writer.Write(index, edged, form.RenderBounds(targets, frame), form.renderVeil);
                        else
                            writer.Write(index, picture, form.RenderBounds(targets, frame), form.renderVeil);
                        if (renderStill != null)
                            // v0.6.24 W5: cut by the same decision as the window - its own corner while the switch is on (the job
                            // says so, make_screenshots.still_job), else Windows' 8 px circle as a capture is cut.
                            using (Bitmap still = StillSquircle() ? SquircleStill(picture, StillNumber(renderStill, "dpi"))
                                                                  : FramedStill(picture, StillNumber(renderStill, "radius"), StillNumber(renderStill, "dpi")))
                                writer.WriteStill(index, still);
                    }
                }
            }
            catch (Exception error)
            {
                writer.Failed(error.ToString());
            }
            finally
            {
                if (form != null) form.Dispose();
                Transition.RenderMs = Transition.Live;
                PersistentBridge.Answers = null;
                lock (RenderMisses) writer.Finish(RenderMisses);
            }
            return writer.Error == null ? 0 : 2;
        }

        /// v0.6.26 (audit-apng M6): whether the job's frames carry their moment on the picture's clock (`moment`).
        private static bool Clocked(List<object> frames)
        {
            if (frames == null) return false;
            foreach (object item in frames)
            {
                var frame = item as Dictionary<string, object>;
                if (frame != null && frame.ContainsKey("moment")) return true;
            }
            return false;
        }

        /// v0.6.26 (audit-apng M6): the frame before, as a window opened again is put in it: its state without the answer it
        /// took (taken once, by the window it was taken in).
        private static Dictionary<string, object> Carried(Dictionary<string, object> before)
        {
            var carried = new Dictionary<string, object>(before);
            carried.Remove("answered");
            return carried;
        }

        /// v0.6.20: the scale the job's pictures are drawn at. A job naming `scale` (build/make_screenshots.py PINNED_SCALE,
        /// 1.5) is drawn at that scale and at Windows' plain text size, whatever display this machine has: the window drawn
        /// at another monitor's scale as it is on a monitor of that scale (AdoptDisplayScale, its fonts at FontFactor and
        /// Control.DefaultFont with them), so a picture is the same on a laptop at 200 % and on a monitor at 150 % (the owner,
        /// 2026-10-30). A job without one is drawn at this machine's scale and text size, as before.
        private static void AdoptRenderScale(Dictionary<string, object> job)
        {
            object pinned;
            double scale = job.TryGetValue("scale", out pinned) && pinned != null
                ? Convert.ToDouble(pinned, CultureInfo.InvariantCulture) : 0;
            if (scale >= 0.5)
            {
                RenderPinned = true;
                AdoptDisplayScale(scale);
                ScaleDefaultFont();
                AdoptTextSize(1.0, 1.0);
                return;
            }
            double text = TextScale.Read();
            AdoptTextSize(text, TextScale.Fitting(text, Screen.PrimaryScreen.WorkingArea.Size, DpiScale));
        }

        /// v0.6.26 (audit-apng M2): the window's font in a render whose scale the job pinned - Windows' UI font at its size
        /// and style, in the face an English Windows has (Segoe UI, Typeface.Segoe), whatever Windows this machine is: the
        /// window then sets each language in the face that language's Windows sets it in, as the product does
        /// (Typeface.ForLanguage: ko Malgun Gothic, ja Yu Gothic UI, zh-CN Microsoft YaHei UI, zh-TW Microsoft JhengHei UI,
        /// th Leelawadee UI, the rest Segoe UI). Before, the English pictures made on a Korean Windows kept its Malgun
        /// Gothic, which draws a backslash as a won sign. Null - the machine's own font, as before - in a render that pins
        /// no scale.
        private static Font RenderFont()
        {
            if (!RenderPinned) return null;
            Font box = SystemFonts.MessageBoxFont;
            Font face;
            try { face = new Font(Typeface.Segoe, box.SizeInPoints, box.Style, GraphicsUnit.Point); }
            catch (ArgumentException) { return null; }
            if (!string.Equals(face.FontFamily.Name, Typeface.Segoe, StringComparison.OrdinalIgnoreCase)) return null;
            return AtDisplayScale(TextScale.Apply(face, textRead, TextSize));
        }

        /// v0.6.20: whether this is a render whose scale the job pinned (AdoptRenderScale): the window opens at its own size
        /// on no screen (KeepOnScreen), and a list's header is laid out at that scale (SoftList.PinnedHeader). False in
        /// every window a person opens.
        internal static bool RenderPinned;

        /// The window as a capture opens it, built never shown, for the job's replies in force.
        private static SettingsForm OpenForRender(RenderWriter writer)
        {
            var strings = RenderAnswer("strings", null);
            string nowhere = Path.Combine(Path.GetTempPath(), "codex-auto-resume-render-" + Guid.NewGuid().ToString("N"));
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, RenderFont());
            form.rendering = true;
            // v0.6.20: the client area the window opened with - its opening size, as a language's face scales it (Microsoft
            // YaHei UI opens it wider and shorter) - kept when its frame is taken off; it was set back to the opening
            // size, so a picture in such a language came out the size of every other.
            Size opened = form.ClientSize;
            form.TopLevel = false;
            form.FormBorderStyle = FormBorderStyle.None;
            form.ClientSize = RenderPinned ? opened : form.OpeningClient;
            form.CreateControl();
            IntPtr made = form.Handle;
            // v0.6.20: and as large as it is. Form.SetBoundsCore holds a form to the largest window the screen allows
            // (SystemInformation.MaxWindowTrackSize) even off every screen, while ClientSize keeps what was asked: on a CI
            // runner's 1024 by 768 screen the 1500 by 996 window was drawn 1044 by 788 (dev CI 41145110604). Windows itself
            // sizes a window with no frame off the screen past that.
            if (RenderPinned)
                SetWindowPos(made, IntPtr.Zero, 0, 0, opened.Width, opened.Height, SwpNoMove | SwpNoZOrder | SwpNoActivate);
            // Shown as a child of Windows' parking window, which is never on the screen: its Load (the reads, the
            // first page, the clock) and its Shown come as they come to a window a person opens.
            form.Visible = true;
            Application.DoEvents();
            if (form.currentPage == null) form.OnLoad(EventArgs.Empty);
            if (!form.shown) form.OnShown(EventArgs.Empty);
            Materialise(form);
            SendRenderMessage(made, WM_UPDATEUISTATE, HideCues, IntPtr.Zero);
            if (!form.HoldStill(true)) writer.Note("the window did not hold still as it opened: " + form.Unsettled());
            return form;
        }

        /// Waits, pumping the window's messages, until the page in front is drawn from every answer it asked for,
        /// nothing moves, and the clock has ticked once since - as a capture waits for its event (WatchForStill).
        private bool HoldStill(bool settle)
        {
            var waited = Stopwatch.StartNew();
            int since = -1;
            var still = new Stopwatch();
            while (waited.ElapsedMilliseconds < RenderSettleLimit)
            {
                Application.DoEvents();
                // What the window's own message loop raises once its queue is empty, and DoEvents never does: the Settings
                // editors are built on it (BuildEditorsLater).
                Application.RaiseIdle(EventArgs.Empty);
                Materialise(this);
                if (!settle) return true;
                // Settled asks about the page the window opened on: the page in front is that page here.
                firstPage = currentPage ?? firstPage;
                if (!Settled()) { since = -1; }
                else if (since < 0) { since = ticks; still.Restart(); }
                else if (ticks != since && still.ElapsedMilliseconds >= 250) return true;
                System.Threading.Thread.Sleep(10);
            }
            return false;
        }

        /// What the window is still waiting for, of everything Settled asks.
        private string Unsettled()
        {
            var waiting = new List<string>();
            if (!shown) waiting.Add("shown");
            if (!settingsRead) waiting.Add("settings read");
            if (readingSettings) waiting.Add("reading settings");
            if (reopening) waiting.Add("reopening");
            if (pendingSchema != null) waiting.Add("editors to build");
            if (buildQueued) waiting.Add("build queued");
            if (busy > 0) waiting.Add("busy " + busy);
            if (refreshing) waiting.Add("refreshing");
            if (loadingStats) waiting.Add("statistics");
            if (loadingCompat) waiting.Add("compatibility");
            if (readingFailure) waiting.Add("failure");
            if (acknowledging) waiting.Add("acknowledging");
            if (bridge.InFlight > 0) waiting.Add("in flight " + bridge.InFlight);
            if (Transition.Moving > 0) waiting.Add("moving " + Transition.Moving);
            if (previewTimer != null && previewTimer.Enabled) waiting.Add("preview timer");
            if (previewToken <= 0) waiting.Add("no preview");
            if (snapshot == null) waiting.Add("no snapshot");
            if (statsToken <= 0) waiting.Add("no statistics");
            waiting.Add("ticks " + ticks);
            return string.Join(", ", waiting.ToArray());
        }

        // The face the last frame gave a control, taken off before the next frame gives one.
        private Control renderFaced;
        private int renderCombo = -1;
        private string renderComboField;

        /// v0.6.22: how far the window's clock has gone on from the moment it is told it is (Soft.StillNow), in seconds:
        /// the frame's `clock` (build/motion_window.frame_state - the last tick of the window's own one-second clock at
        /// or before the frame's moment on the picture's clock, build/motion_plan.clock_at). Every countdown and age the
        /// window works out from now (Now) is read that much later, so they move on as the picture plays; a frame without
        /// one, and every window a person opens, is at the pinned moment itself. Set only here.
        private static double renderClock;

        /// The window's clock at the frame's moment (renderClock), and every time it shows said again at it, as its own
        /// clock and refresh say them (ApplySnapshot: Right now's Last check, the waiting line's usage age, Why it is
        /// waiting's Last checked, the countdowns) - so what a frame shows is that moment's, whenever the window's own
        /// timer happened to tick while it was drawn.
        private void RenderClock(Dictionary<string, object> frame)
        {
            object given;
            double clock = frame.TryGetValue("clock", out given) && given != null
                ? Convert.ToDouble(given, CultureInfo.InvariantCulture) / 1000.0 : 0;
            if (clock == renderClock) return;
            renderClock = clock;
            if (snapshot != null) ApplySnapshot(snapshot);
        }

        /// Puts the window in a frame's state, and waits for it to hold still when that took a read or a layout.
        private void RenderState(Dictionary<string, object> frame, RenderWriter writer)
        {
            bool moved = false;
            // The clock first: a page shown below writes its countdowns at it (ShowPage).
            RenderClock(frame);
            string page = Str(frame, "page") ?? "overview";
            if (currentPage != page && Array.IndexOf(PageOrder, page) >= 0)
            {
                ShowPage(page);
                moved = true;
            }
            RenderStateNamed(frame, writer, ref moved);
            // A page this window does not have is never drawn as another: the job stops.
            if (currentPage != page) throw new InvalidDataException("no page called " + page + " is in this window");
            string section = Str(frame, "section");
            if (page == "settings" && section != null && currentSection != section)
            {
                ShowSection(section);
                moved = true;
            }
            moved |= RenderCombo(Map(frame, "combo"));
            moved |= RenderSelected(Map(frame, "selected"));
            if (moved)
            {
                Materialise(this);
                PerformLayout();
                if (!HoldStill(true)) writer.Note("frame " + frame["index"] + ": the " + page + " page did not hold still: " + Unsettled());
            }
            // The chosen row again, now that the page holds still (RenderSelected).
            RenderSelected(Map(frame, "selected"));
            RenderScroll(page, Map(frame, "scroll"));
            RenderExplain(page, Map(frame, "explain"));
            // v0.6.26 (audit-apng M5): a drop-down whose list is open looks open - its edge a step darker, its chevron turned.
            RenderComboOpen(Map(frame, "droplist"));
            RenderFace(Str(frame, "hover"), Str(frame, "pressed"), writer);
            object light;
            Soft.StillLightMs = frame.TryGetValue("light", out light) && light != null
                ? Convert.ToDouble(light, CultureInfo.InvariantCulture) : 0;
            // An action in flight, as the window counts it (SetBusy): its buttons wait their turn and the header's light
            // is the working one (BusyLight). After the moment of the lights, which the header reads as it follows.
            object working;
            RenderBusy(frame.TryGetValue("busy", out working) && Equals(working, true));
            // v0.6.26 (audit-apng M7): the answer of an action the frame says came, taken as the window takes it.
            RenderAnswered(Str(frame, "answered"), writer);
            object sweeping;
            RenderSweep(frame.TryGetValue("sweep", out sweeping) && sweeping != null
                ? Convert.ToDouble(sweeping, CultureInfo.InvariantCulture) : -1);
            HoldStill(false);
        }

        /// v0.6.24: the light's sweep `ms` into it - as the window opens and as the light turns on (SweepLight, and Shown for
        /// the opening's) - and the line under the headline coming in as it ends (AsideLabel.Arrive(AsideAfterMs)): each drawn
        /// by its own painter at that moment (HaloDot.StillSweepMs, AsideLabel.ArriveAt), for a frame `sweep` ms after the
        /// sweep began (build/motion_window.frame_state); -1 - no sweep - for every other frame. The window's own sweep never
        /// plays in a render (LightSweepsShown).
        private void RenderSweep(double ms)
        {
            if (ms >= HaloDot.SweepMs) ms = -1;
            if (stateDot.StillSweepMs != ms)
            {
                stateDot.StillSweepMs = ms;
                stateDot.Invalidate();
            }
            detail.ArriveAt(ms, AsideAfterMs);
        }

        // Whether the last frame had an action in flight (RenderBusy).
        private bool renderBusy;

        // v0.6.26 (review P2): the picture's moment the call in flight began at, while its first moments are held, or -1.
        private double renderBusyAt = -1;

        /// The window's own count of an action in flight, raised or let go as the frame says: SetBusy, which waits on
        /// nothing - what a Retry now, a Pause or a Rescan raises for as long as the bridge's call lasts.
        /// v0.6.26 (review P2): on the picture's clock its first moments are held as the product holds them (BusyHold): the
        /// buttons keep their look for BusyHold.Milliseconds from the frame the call began, then glide to it - from that
        /// moment, whichever frame comes next - and a call that ends inside the hold shows nothing. Its timer never runs
        /// here: the hold ends on the picture's clock (RenderHoldOver). Outside it (a still, a window set up as it stands) a
        /// picture of a call in flight is of one that has lasted.
        private void RenderBusy(bool on)
        {
            RenderHoldOver();
            if (on == renderBusy) return;
            renderBusy = on;
            renderBusyAt = -1;
            SetBusy(on);
            if (on) BusyHold.Lapse();       // a picture of a call in flight is of one that has lasted, not of its first 150 ms
            // Every button's look has just begun to glide: on the picture's clock (v0.6.26, audit-apng M6) drawn at each
            // frame's moment from here, nothing counted as moving; on the wall clock a picture is of where it ends.
            var waited = Stopwatch.StartNew();
            while (Transition.Moving > 0 && waited.ElapsedMilliseconds < RenderSettleLimit)
            {
                Application.DoEvents();
                System.Threading.Thread.Sleep(5);
            }
        }

        /// v0.6.26 (review P2): the call's held first moments over, at their own moment on the picture's clock, once a frame
        /// is at or past it: the buttons begin their glide to the busy look from there (BusyHold.Lapse, as its timer would).
        private void RenderHoldOver()
        {
            double moment = Transition.RenderMs;
            if (renderBusyAt < 0 || moment < 0) return;
            double over = renderBusyAt + BusyHold.Milliseconds;
            if (moment < over) return;
            renderBusyAt = -1;
            if (!BusyHold.On) return;
            try
            {
                Transition.RenderMs = over;
                BusyHold.Lapse();
            }
            finally { Transition.RenderMs = moment; }
        }

        // BusyHold's wall-clock timer stopped: on the picture's clock the hold ends at its moment, never at a real 150 ms.
        private static void StopHoldTimer()
        {
            var field = typeof(BusyHold).GetField("timer", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static);
            var timer = field == null ? null : field.GetValue(null) as Timer;
            if (timer != null) timer.Stop();
        }

        // The action whose answer the last frame took (RenderAnswered), or null.
        private string renderAnswered;

        /// v0.6.26 (audit-apng M7): an action's answer, as the window takes it - `retry-now`: the window's own Retry now
        /// (RetryNow) on the chosen Pending row, its call answered from the job's replies (the pinned installation's own
        /// answer, build/motion_window.py answers), so the note under the list says what the product says for that answer
        /// (ShowPendingNote). Once, when a frame first names it; nothing again while frames go on naming it.
        private void RenderAnswered(string command, RenderWriter writer)
        {
            if (command == renderAnswered) return;
            renderAnswered = command;
            if (command == null) return;
            if (command != "retry-now") { writer.Note("no action is called " + command); return; }
            var row = Selected(pendingList);
            if (row == null) { writer.Note("Retry now is answered with no Pending row chosen"); return; }
            // Only an answer the job gives: a refusal would have the window say so in a box of its own, never drawn here.
            if (!Ok(RenderAnswer("retry-now", IdArgument(row)))) { writer.Note("Retry now on the chosen row was not answered"); return; }
            RetryNow();
            if (!HoldStill(true)) writer.Note("Retry now's answer did not hold still: " + Unsettled());
        }

        /// A frame's moment `key` (`appear_ms`, `close_ms`) of something opening or closing, in ms, or -1 when it has none.
        private static double RenderMs(Dictionary<string, object> state, string key)
        {
            object given;
            return state != null && state.TryGetValue(key, out given) && given != null
                ? Convert.ToDouble(given, CultureInfo.InvariantCulture) : -1;
        }

        /// v0.6.26 (audit-apng M4, M5): how opaque, and how far below its place, a card that opens as the row menu and the
        /// drop-down's list open (SoftMenuLayer.Tick, SoftDropList.PaintAt) is `appear` ms into its opening: fading in and
        /// rising SpaceXs into place over Motion.Duration on Motion.Ease. Arrived for -1.
        internal static void RenderOpening(double appear, out int alpha, out int rise)
        {
            double t = appear < 0 ? 1.0 : appear / Math.Max(1, Motion.Duration);
            double eased = Motion.Ease(Math.Min(1.0, t));
            alpha = t >= 1.0 ? 255 : (int)Math.Round(255 * eased);
            rise = t >= 1.0 ? 0 : (int)Math.Round(Soft.Px(Brand.SpaceXs) * (1.0 - eased));
        }

        /// v0.6.26 (audit-apng M4, M5): how opaque the last picture of a closed menu or list is `ms` into its fade-out from
        /// `from` (SoftLayerFade.Tick, SoftDropList.FadeFrame): over Motion.Press on Motion.Ease, then gone.
        internal static int RenderClosing(double ms, int from)
        {
            double part = ms / Math.Max(1, Motion.Press);
            return part >= 1.0 ? 0 : (int)Math.Round(from * (1.0 - Motion.Ease(Math.Max(0.0, part))));
        }

        /// `image` over `picture` at `at`, `alpha` (0 to 255) as opaque as it is drawn, as a layered window of that alpha is laid.
        private static void LayFaded(Bitmap picture, Bitmap image, Point at, int alpha)
        {
            if (image == null || alpha <= 0) return;
            using (Graphics g = Graphics.FromImage(picture))
            {
                if (alpha >= 255) { g.DrawImage(image, at.X, at.Y, image.Width, image.Height); return; }
                using (var faded = new ImageAttributes())
                {
                    var matrix = new ColorMatrix();
                    matrix.Matrix33 = alpha / 255f;
                    faded.SetColorMatrix(matrix);
                    g.DrawImage(image, new Rectangle(at.X, at.Y, image.Width, image.Height), 0, 0, image.Width, image.Height,
                                GraphicsUnit.Pixel, faded);
                }
            }
        }

        // The drop-down the last frame gave its open look (RenderComboOpen), or null.
        private SoftCombo renderOpened;

        /// v0.6.26 (audit-apng M5): the drop-down whose list the frame has open (not closing) in its open look, as OpenList
        /// leaves it - its edge a step darker (FaceWanted while Open) and its chevron turned up - and the one before in its
        /// closed look again. The list itself is drawn over the picture (RenderDropList); the drop-down is only told it has
        /// one, never shown it. v0.6.26 (review P1): each by the drop-down's own change, as OpenList and CloseList make it -
        /// its face's glide told (faceGlide.Changed) and its chevron sent round (chevron.To, Motion.Allowed) - so on the
        /// picture's clock both glide over brand's transition from the frame the list opens or closes; outside it, at once.
        private void RenderComboOpen(Dictionary<string, object> listed)
        {
            SoftCombo wanted = null;
            Control editor;
            if (listed != null && RenderMs(listed, "close_ms") < 0 && editors.TryGetValue(Str(listed, "field") ?? "", out editor))
                wanted = editor as SoftCombo;
            if (wanted == renderOpened) return;
            if (renderOpened != null && !renderOpened.IsDisposed) ComboLooksOpen(renderOpened, false);
            renderOpened = wanted;
            if (wanted != null) ComboLooksOpen(wanted, true);
        }

        private static void ComboLooksOpen(SoftCombo combo, bool open)
        {
            const System.Reflection.BindingFlags own = System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;
            System.Reflection.FieldInfo drop = typeof(SoftCombo).GetField("drop", own);
            System.Reflection.FieldInfo turn = typeof(SoftCombo).GetField("chevron", own);
            if (drop == null || turn == null) return;
            var was = drop.GetValue(combo) as SoftDropList;
            if (open && was == null) drop.SetValue(combo, new SoftDropList(combo));
            else if (!open && was != null)
            {
                drop.SetValue(combo, null);
                was.Dispose();
            }
            double clock = Transition.RenderMs;
            if (clock == Transition.Live) Transition.RenderMs = Transition.Arrived;
            try
            {
                var face = typeof(SoftCombo).GetField("faceGlide", own) == null ? null
                         : typeof(SoftCombo).GetField("faceGlide", own).GetValue(combo) as SoftSurfaceGlide;
                if (face != null) face.Changed();
                var chevron = turn.GetValue(combo) as Transition;
                if (chevron != null) chevron.To(open ? 1.0 : 0.0, Motion.Allowed(combo));
            }
            finally { Transition.RenderMs = clock; }
            combo.Invalidate();
        }

        /// Why it is waiting scrolled `notches` turns of the wheel down, the last of them `glide_ms` into its glide: its
        /// checks' own soft page (the Pending page's), moved as the wheel moves any page (RenderOffset).
        private void RenderExplain(string page, Dictionary<string, object> scroll)
        {
            if (page != "pending" || explainPage == null) return;
            int notches = scroll == null ? 0 : Convert.ToInt32(scroll["notches"], CultureInfo.InvariantCulture);
            object gliding;
            int glide = scroll != null && scroll.TryGetValue("glide_ms", out gliding) && gliding != null
                ? Convert.ToInt32(gliding, CultureInfo.InvariantCulture) : -1;
            ISoftScroller scroller = explainPage;
            scroller.ScrollTo(RenderOffset(scroller.Extent, scroller.Viewport, notches, glide));
        }

        /// The control a frame's target names that the window's command line has no name for: the Pending page's own
        /// buttons and its explanation, the Overview's Pause or Resume. Null for every other name.
        private Control RenderControl(string name)
        {
            switch (name)
            {
                case "pending.retry": return retryButton;
                case "pending.timeline": return timelineButton;
                case "pending.explain": return explainPage == null ? null : explainPage.Parent;
                case "overview.toggle": return toggleButton;
            }
            return null;
        }

        /// A drop-down showing a value that is not saved, as a pick from its list leaves it; the value it was built
        /// with again when no frame names it any more. True when anything changed.
        private bool RenderCombo(Dictionary<string, object> combo)
        {
            string field = null, value = null;
            if (combo != null)
                foreach (KeyValuePair<string, object> pair in combo) { field = pair.Key; value = Convert.ToString(pair.Value, CultureInfo.InvariantCulture); }
            if (renderComboField != null && renderComboField != field)
            {
                Control was;
                if (editors.TryGetValue(renderComboField, out was) && was is ComboBox) ((ComboBox)was).SelectedIndex = renderCombo;
                renderComboField = null;
                return true;
            }
            Control editor;
            if (field == null || !editors.TryGetValue(field, out editor)) return false;
            var box = editor as ComboBox;
            if (box == null) return false;
            for (int i = 0; i < box.Items.Count; i++)
            {
                var choice = box.Items[i] as Choice;
                if (choice == null || choice.Value != value) continue;
                if (box.SelectedIndex == i) return false;
                if (renderComboField == null) { renderComboField = field; renderCombo = box.SelectedIndex; }
                box.SelectedIndex = i;
                return true;
            }
            return false;
        }

        // The Pending row the last frame chose (RenderSelected), or -1.
        private int renderSelected = -1;

        /// v0.6.18: the Pending row a right click chose - `{"pending": n}` - as the list chooses the row under the pointer
        /// (DashboardPages, MouseDown); none again once no frame names one. True when anything changed.
        private bool RenderSelected(Dictionary<string, object> selected)
        {
            object given;
            int row = selected != null && selected.TryGetValue("pending", out given) && given != null
                ? Convert.ToInt32(given, CultureInfo.InvariantCulture) : -1;
            if (pendingList == null || (row < 0 && renderSelected < 0)) return false;
            renderSelected = row;
            // Asked of every frame, not only when it changes: a read the window makes while it settles fills the list
            // again, and the row chosen with it.
            bool chosen = row >= 0 && row < pendingList.Items.Count;
            if (chosen && pendingList.SelectedIndices.Count == 1 && pendingList.Items[row].Selected) return false;
            if (!chosen && pendingList.SelectedIndices.Count == 0) return false;
            pendingList.SelectedIndices.Clear();
            if (chosen) pendingList.Items[row].Selected = true;
            pendingList.Invalidate();
            return true;
        }

        /// The page scrolled `notches` turns of the wheel down, the last of them `glide_ms` into its glide - as
        /// SoftPage glides, SoftBar.GlideAt along brand's curve over brand's transition - or at rest.
        private void RenderScroll(string page, Dictionary<string, object> scroll)
        {
            Control built;
            ISoftScroller scroller = page == "settings" ? sectionScroll
                                   : pages.TryGetValue(page, out built) ? built as ISoftScroller : null;
            if (scroller == null) return;
            int notches = scroll == null ? 0 : Convert.ToInt32(scroll["notches"], CultureInfo.InvariantCulture);
            object gliding;
            int glide = scroll != null && scroll.TryGetValue("glide_ms", out gliding) && gliding != null
                ? Convert.ToInt32(gliding, CultureInfo.InvariantCulture) : -1;
            scroller.ScrollTo(RenderOffset(scroller.Extent, scroller.Viewport, notches, glide));
        }

        /// Where a page `extent` long showing `viewport` of it stands after `notches` turns of the wheel down from its
        /// top, the last `glide` ms into its glide (-1: arrived).
        internal static int RenderOffset(int extent, int viewport, int notches, int glide)
        {
            int range = Math.Max(0, extent - viewport), offset = 0;
            for (int notch = 0; notch < notches; notch++)
            {
                int step = SoftBar.WheelStep(-120, RenderWheelLines, Soft.Px(SoftBar.Line), viewport);
                int target = Math.Max(0, Math.Min(range, offset + step));
                if (notch < notches - 1 || glide < 0) { offset = target; continue; }
                offset = SoftBar.GlideAt(offset, target, Motion.Ease(glide / (double)Math.Max(1, Motion.Duration)));
            }
            return offset;
        }

        // Whether the control the last frame gave a face has it pressed.
        private bool renderFacedPressed;

        /// The hover or pressed face of the control a frame names, as the pointer gives it: the control's own change of its
        /// `hover` flag and its own Press - nothing a control does not draw of its own - made only when the face changes, so
        /// a glide it starts goes on over the frames after (v0.6.26, audit-apng M6: it was taken off and given again every
        /// frame, and a press's glide began anew at each). A name the window has no control for is noted.
        private void RenderFace(string hover, string pressed, RenderWriter writer)
        {
            string name = pressed ?? hover;
            Control control = null;
            // A row of an open list, a Pending row or an item of the row menu: drawn by RenderPicture, not a control's face.
            if (name != null && !name.StartsWith("row.", StringComparison.Ordinal) &&
                !name.StartsWith("task.", StringComparison.Ordinal) && !name.StartsWith("menu.", StringComparison.Ordinal) &&
                !name.StartsWith("dialog.", StringComparison.Ordinal))
            {
                control = RenderControl(name) ?? FocusTarget(name);
                if (control == null) writer.Note("no control is called " + name);
            }
            bool down = control != null && pressed != null;
            if (control == renderFaced && down == renderFacedPressed) return;
            if (renderFaced != null && renderFaced != control && !renderFaced.IsDisposed) SetRenderFace(renderFaced, false, false);
            if (control != null) SetRenderFace(control, true, down);
            renderFaced = control;
            renderFacedPressed = down;
        }

        /// `control` given its hover and pressed face as the pointer gives them, by its own change: its Press (a press and
        /// its release, in brand's press time), and its `hover` flag with the glide its pointer's coming and going starts
        /// (its Hover, or its SoftSurfaceGlide's Changed in brand's transition) - entering, the hover first; leaving, the
        /// press first, as its own OnMouseEnter and OnMouseLeave take them. No event is raised: nothing but its face changes
        /// (a caption button's tip is never asked for). Outside a picture's clock, arrived at once.
        private static void SetRenderFace(Control control, bool hover, bool pressed)
        {
            double clock = Transition.RenderMs;
            if (clock == Transition.Live) Transition.RenderMs = Transition.Arrived;
            try
            {
                if (hover) { RenderHover(control, true); RenderPress(control, pressed); }
                else { RenderPress(control, false); RenderHover(control, false); }
            }
            finally { Transition.RenderMs = clock; }
            control.Invalidate();
            if (control.Parent != null) control.Parent.Invalidate(true);
        }

        private const System.Reflection.BindingFlags RenderOwn = System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;

        private static void RenderHover(Control control, bool over)
        {
            Type type = control.GetType();
            // v0.6.26 (audit-apng M5): the drop-down keeps its pointer's hover as faceHover.
            System.Reflection.FieldInfo hovered = type.GetField("hover", RenderOwn) ?? type.GetField("faceHover", RenderOwn);
            if (hovered == null || hovered.FieldType != typeof(bool) || (bool)hovered.GetValue(control) == over) return;
            System.Reflection.MethodInfo own = type.GetMethod("Hover", RenderOwn, null, new[] { typeof(bool) }, null);
            if (own != null) { own.Invoke(control, new object[] { over }); return; }
            hovered.SetValue(control, over);
            RenderGlide(control, Motion.Duration);
        }

        private static void RenderPress(Control control, bool down)
        {
            Type type = control.GetType();
            System.Reflection.MethodInfo press = type.GetMethod("Press", RenderOwn, null, new[] { typeof(bool) }, null);
            if (press != null) { press.Invoke(control, new object[] { down }); return; }
            // A control with no Press of its own (a caption button) keeps its press as `pressed`, its glide in the press time.
            System.Reflection.FieldInfo held = type.GetField("pressed", RenderOwn);
            if (held == null || held.FieldType != typeof(bool) || (bool)held.GetValue(control) == down) return;
            held.SetValue(control, down);
            RenderGlide(control, Motion.Press);
        }

        // The control's own glides told its state has changed, in `milliseconds`.
        private static void RenderGlide(Control control, int milliseconds)
        {
            foreach (System.Reflection.FieldInfo field in control.GetType().GetFields(RenderOwn))
            {
                if (field.FieldType != typeof(SoftSurfaceGlide)) continue;
                var glide = field.GetValue(control) as SoftSurfaceGlide;
                if (glide != null) glide.Changed(milliseconds);
            }
        }

        /// v0.6.24-beta.3: the day's scene under `root` (SoftDayScene, the header's child above its card) laid down over the
        /// picture of it, where it stands and in its own outline (its Region), as the screen stacks it: higher in the
        /// header's z-order than the card, so over it. DrawToBitmap prints the children from the top of the z-order down,
        /// each over the one before, and the card was printed over the scene - on a special day the header showed none of
        /// it, only the caption buttons (PaintCaptionOver, after this) drew it under them (found 2026-11-17).
        private static void PaintSceneOver(Bitmap picture, Control root)
        {
            var found = new List<SoftDayScene>();
            var walk = new Stack<Control>();
            walk.Push(root);
            while (walk.Count > 0)
            {
                Control parent = walk.Pop();
                foreach (Control child in parent.Controls)
                {
                    if (!OwnVisible(child)) continue;
                    var scene = child as SoftDayScene;
                    if (scene != null) { if (scene.Look != null) found.Add(scene); }
                    else walk.Push(child);
                }
            }
            foreach (SoftDayScene scene in found)
            {
                if (scene.Width <= 0 || scene.Height <= 0) continue;
                Point at = Point.Empty;
                for (Control c = scene; c != null && c != root; c = c.Parent) at.Offset(c.Left, c.Top);
                using (var face = new Bitmap(scene.Width, scene.Height, PixelFormat.Format32bppArgb))
                using (Graphics g = Graphics.FromImage(picture))
                {
                    scene.DrawToBitmap(face, new Rectangle(Point.Empty, scene.Size));
                    g.TranslateTransform(at.X, at.Y);
                    if (scene.Region != null) g.SetClip(scene.Region, System.Drawing.Drawing2D.CombineMode.Replace);
                    g.DrawImageUnscaled(face, 0, 0);
                }
            }
        }

        /// v0.6.24: the caption buttons under `root` (gui/SoftChrome.cs) drawn again over the picture of it, where they stand.
        /// DrawToBitmap prints a window's children from the top of the z-order down, so the card the buttons stand over -
        /// lower in the z-order, as on the screen - was printed over them and they were in no picture.
        private static void PaintCaptionOver(Bitmap picture, Control root)
        {
            var found = new List<CaptionButton>();
            var walk = new Stack<Control>();
            walk.Push(root);
            while (walk.Count > 0)
            {
                Control parent = walk.Pop();
                foreach (Control child in parent.Controls)
                {
                    var button = child as CaptionButton;
                    if (button != null) { if (OwnVisible(button)) found.Add(button); }
                    else if (OwnVisible(child)) walk.Push(child);
                }
            }
            foreach (CaptionButton button in found)
            {
                Point at = Point.Empty;
                for (Control c = button; c != null && c != root; c = c.Parent) at.Offset(c.Left, c.Top);
                var place = new Rectangle(at, button.Size);
                if (!new Rectangle(Point.Empty, picture.Size).Contains(place)) continue;
                using (var face = new Bitmap(button.Width, button.Height, PixelFormat.Format32bppArgb))
                {
                    button.DrawToBitmap(face, new Rectangle(Point.Empty, button.Size));
                    using (Graphics g = Graphics.FromImage(picture)) g.DrawImageUnscaled(face, at.X, at.Y);
                }
            }
        }

        /// A list's own scroll bars, which its clip hides on screen, are drawn whole by DrawToBitmap - over the soft bar
        /// beside them (the owner, 2026-10-26: "고급판 캡처에서는 우리의 스크롤이 적용이 안 되네"). Each showing list's
        /// gutters are painted again on top, as far as the window shows that list, as the screen draws them.
        private void PaintListGutters(Bitmap picture)
        {
            PaintListGutters(picture, this);
        }

        /// The same for the lists under `root` - the window, or a dialog it has open (RenderDialog) - in the picture of it.
        private void PaintListGutters(Bitmap picture, Control root)
        {
            var hosts = new List<SoftListHost>();
            var walk = new Stack<Control>();
            walk.Push(root);
            while (walk.Count > 0)
            {
                Control control = walk.Pop();
                if (control != root && !Soft.OwnVisible(control)) continue;
                var host = control as SoftListHost;
                if (host != null) hosts.Add(host);
                foreach (Control child in control.Controls) walk.Push(child);
            }
            foreach (SoftListHost host in hosts)
            {
                if (!host.IsHandleCreated) continue;
                Point at = root.PointToClient(host.PointToScreen(Point.Empty));
                var shown = new Rectangle(at, host.Size);
                for (Control parent = host.Parent; parent != null && parent != root; parent = parent.Parent)
                    if (parent.IsHandleCreated)
                        shown.Intersect(new Rectangle(root.PointToClient(parent.PointToScreen(Point.Empty)), parent.ClientSize));
                if (shown.Width <= 0 || shown.Height <= 0) continue;
                using (Graphics g = Graphics.FromImage(picture))
                {
                    g.SetClip(shown);
                    g.TranslateTransform(at.X, at.Y);
                    host.PaintGutters(g);
                }
            }
        }

        /// The window drawn into a bitmap the size of its client area - and over it, when the frame has one open, a
        /// drop-down's list, which is a window of its own a picture of the window would never hold, drawn by its own
        /// painter (SoftDropList.PaintSettled) where it opens.
        private Bitmap RenderPicture(Dictionary<string, object> frame, RenderWriter writer)
        {
            var picture = new Bitmap(ClientSize.Width, ClientSize.Height, PixelFormat.Format32bppArgb);
            Invalidate(true);
            DrawToBitmap(picture, new Rectangle(Point.Empty, ClientSize));
            PaintSceneOver(picture, this);
            PaintCaptionOver(picture, this);
            PaintListGutters(picture);
            // v0.6.26: the window's own outer edge - its corner and its hairline - cut now, before anything is laid over the
            // window: what lies over it on the screen is a window of its own (the row menu, a drop-down's list, a dialog
            // and the veil under it), never cut by the window's corner, and the veil dims the window's hairline as it dims
            // the rest of the window (PaintVeil).
            if (renderEdgeDpi > 0 && EdgeFirst)
            {
                Bitmap edged = CornerStill(picture, renderEdgeDpi);
                picture.Dispose();
                picture = edged;
            }
            renderVeil = null;
            renderRows = null;
            renderMenu = null;
            renderDialogBounds = null;
            // v0.6.18: a Pending row's own menu, over everything: a window of its own too (SoftMenu), drawn by its own
            // card where it opens.
            RenderDropList(picture, Map(frame, "droplist"), writer);
            var menu = Map(frame, "menu");
            if (menu != null) RenderMenu(picture, menu, Str(frame, "hover"), writer);
            // v0.6.20: a dialog the window opened, centred over it: a top-level window of its own, drawn by its own
            // controls, with the title bar Windows draws round it.
            var dialog = Map(frame, "dialog");
            if (dialog != null) RenderDialog(picture, dialog, Str(frame, "hover"), Str(frame, "pressed"), writer);
            else renderCloseOver = renderCloseDown = -1;
            return picture;
        }

        // The items of the row menu the last picture showed open, by name (`menu.<n>`), in client coordinates.
        private Dictionary<string, Rectangle> renderMenu;
        // v0.6.26 (audit-apng M4, M5): the last picture of the row menu and of a drop-down's list, where it stood and how
        // opaque - what the product fades out once it has closed (SoftLayerFade, SoftDropList.FadeOut).
        private Bitmap renderMenuLast, renderListLast;
        private Point renderMenuLastAt, renderListLastAt;
        private int renderMenuLastAlpha, renderListLastAlpha;

        /// The Pending row `name` names (`task.<n>`) in client coordinates, and its index; false when it is not shown.
        private bool RenderTask(string name, out Rectangle bounds, out int index)
        {
            bounds = Rectangle.Empty;
            index = -1;
            if (name == null || !name.StartsWith("task.", StringComparison.Ordinal) || pendingList == null) return false;
            if (!int.TryParse(name.Substring(5), NumberStyles.None, CultureInfo.InvariantCulture, out index)) return false;
            if (index < 0 || index >= pendingList.Items.Count) return false;
            for (Control c = pendingList; c != null && c != this; c = c.Parent) if (!OwnVisible(c)) return false;
            Rectangle row = pendingList.Items[index].Bounds;
            Point list = InClient(pendingList);
            bounds = new Rectangle(list.X + row.X, list.Y + row.Y, row.Width, row.Height);
            return true;
        }

        /// The row menu of the Pending row `at` names, as a right click there opens it - filled by FillRowMenu as the
        /// menu's Opening fills it, the item `hover` names (`menu.<n>`) in hand - drawn by its own card (SoftMenuLayer)
        /// with the card's corner where the pointer is (RenderMenuPlace), and its items named for the pointer.
        private void RenderMenu(Bitmap picture, Dictionary<string, object> menu, string hover, RenderWriter writer)
        {
            // v0.6.26 (audit-apng M4): closed, its last picture fades out where it stood (SoftMenuLayer.Closed, SoftLayerFade).
            double closing = RenderMs(menu, "close_ms");
            if (closing >= 0)
            {
                if (renderMenuLast == null) { writer.Note("the row menu closes with no picture of it open"); return; }
                LayFaded(picture, renderMenuLast, renderMenuLastAt, RenderClosing(closing, renderMenuLastAlpha));
                return;
            }
            string at = Str(menu, "at");
            Rectangle row;
            int index;
            if (!RenderTask(at, out row, out index)) { writer.Note("no Pending row is called " + at); return; }
            if (pendingMenu == null || !FillRowMenu(pendingList.Items[index].Tag as Dictionary<string, object>))
            {
                writer.Note("the row menu offers nothing on " + at);
                return;
            }
            pendingMenu.Size = pendingMenu.GetPreferredSize(Size.Empty);
            pendingMenu.PerformLayout();
            IntPtr made = pendingMenu.Handle;
            int held;
            if (hover != null && hover.StartsWith("menu.", StringComparison.Ordinal) &&
                int.TryParse(hover.Substring(5), NumberStyles.None, CultureInfo.InvariantCulture, out held) &&
                held < pendingMenu.Items.Count)
                pendingMenu.Items[held].Select();
            SoftMenuLayer layer = pendingMenu.Layer;
            if (layer == null) { writer.Note("the row menu is Windows' own here: no card to draw"); return; }
            layer.Render();
            Bitmap image = layer.Image;
            if (image == null) return;
            // Where the pointer stands on the row: its centre, as the pointer is put on a target (motion_compose.locate).
            var anchor = new Point(row.X + row.Width / 2, row.Y + row.Height / 2);
            Point corner = RenderMenuPlace(anchor, image.Size, SoftMenuLayer.Reach, ClientSize);
            // v0.6.26 (audit-apng M4): opening, it fades in and rises into place (SoftMenuLayer.Open, Tick), `appear_ms` in.
            int alpha, rise;
            RenderOpening(RenderMs(menu, "appear_ms"), out alpha, out rise);
            LayFaded(picture, image, new Point(corner.X, corner.Y + rise), alpha);
            if (renderMenuLast != null) renderMenuLast.Dispose();
            renderMenuLast = (Bitmap)image.Clone();
            renderMenuLastAt = new Point(corner.X, corner.Y + rise);
            renderMenuLastAlpha = alpha;
            renderMenu = new Dictionary<string, Rectangle>();
            for (int i = 0; i < pendingMenu.Items.Count; i++)
            {
                ToolStripItem item = pendingMenu.Items[i];
                if (item is ToolStripSeparator || !item.Available) continue;
                renderMenu["menu." + i.ToString(CultureInfo.InvariantCulture)] =
                    new Rectangle(corner.X + item.Bounds.X, corner.Y + item.Bounds.Y, item.Bounds.Width, item.Bounds.Height);
            }
        }

        /// Where a menu's window `size` big goes, with its card `reach` in from each edge, when it opens at `anchor` in
        /// a client area `client` big: its card's top left corner at the anchor - or, where the card has no room right
        /// of it or below it, its right or bottom edge, as Windows turns a menu round to fit - and the card kept inside.
        internal static Point RenderMenuPlace(Point anchor, Size size, Padding reach, Size client)
        {
            int wide = size.Width - reach.Horizontal, tall = size.Height - reach.Vertical;
            int left = anchor.X + wide <= client.Width ? anchor.X : anchor.X - wide;
            int top = anchor.Y + tall <= client.Height ? anchor.Y : anchor.Y - tall;
            left = Math.Max(0, Math.Min(left, client.Width - wide));
            top = Math.Max(0, Math.Min(top, client.Height - tall));
            return new Point(left - reach.Left, top - reach.Top);
        }

        /// A drop-down's open list over the picture, when the frame has one (see RenderPicture).
        private void RenderDropList(Bitmap picture, Dictionary<string, object> listed, RenderWriter writer)
        {
            if (listed == null) return;
            // v0.6.26 (audit-apng M5): closed, its last picture fades out where it stood (SoftCombo.CloseList, FadeOut).
            double closing = RenderMs(listed, "close_ms");
            if (closing >= 0)
            {
                if (renderListLast == null) { writer.Note("the drop list closes with no picture of it open"); return; }
                LayFaded(picture, renderListLast, renderListLastAt, RenderClosing(closing, renderListLastAlpha));
                return;
            }
            Control editor;
            var combo = editors.TryGetValue(Str(listed, "field") ?? "", out editor) ? editor as SoftCombo : null;
            if (combo == null) { writer.Note("no drop-down is called " + Str(listed, "field")); return; }
            int hovered = -1;
            string value = Str(listed, "hover");
            for (int i = 0; i < combo.Items.Count; i++)
            {
                var choice = combo.Items[i] as Choice;
                if (choice != null && choice.Value == value) hovered = i;
            }
            Point field = InClient(combo);
            using (var list = new SoftDropList(combo))
            {
                // Its own placement, against the window's client area for a screen: where it opens under the field.
                Rectangle screenField = combo.RectangleToScreen(combo.ClientRectangle);
                Rectangle area = RectangleToScreen(new Rectangle(Point.Empty, ClientSize));
                // As it opens it fades in and rises into place (SoftDropList.Show and Tick): `appear_ms` into that.
                object appearing;
                double appear = listed.TryGetValue("appear_ms", out appearing) && appearing != null
                    ? Convert.ToDouble(appearing, CultureInfo.InvariantCulture) : -1;
                Bitmap image = list.PaintAt(hovered, area, appear);
                if (image == null) return;
                Rectangle card = list.Card;
                Padding margin = list.Margin;
                int rise = list.CardOnScreen.Y - card.Y;
                int left = field.X + card.X - screenField.X - margin.Left;
                int top = field.Y + card.Y - screenField.Y - margin.Top + rise;
                LayFaded(picture, image, new Point(left, top), list.Alpha);
                if (renderListLast != null) renderListLast.Dispose();
                renderListLast = (Bitmap)image.Clone();
                renderListLastAt = new Point(left, top);
                renderListLastAlpha = list.Alpha;
                renderRows = new Dictionary<string, Rectangle>();
                for (int i = 0; i < combo.Items.Count; i++)
                {
                    var choice = combo.Items[i] as Choice;
                    Rectangle pill = list.PillRect(i);
                    if (choice != null && list.Shows(i))
                        renderRows["row." + choice.Value] = new Rectangle(left + margin.Left + pill.X, top + margin.Top + pill.Y,
                                                                          pill.Width, pill.Height);
                }
            }
        }

        // The rows of the list the last picture showed open, by name, in client coordinates.
        private Dictionary<string, Rectangle> renderRows;

        /// Where `control` stands in the client area, from the positions of it and every control around it.
        private Point InClient(Control control)
        {
            int x = 0, y = 0;
            for (Control c = control; c != null && c != this; c = c.Parent) { x += c.Left; y += c.Top; }
            return new Point(x, y);
        }

        /// The bounds, in client coordinates, of every target the job names that shows in this frame.
        private Dictionary<string, object> RenderBounds(List<object> targets, Dictionary<string, object> frame)
        {
            var found = new Dictionary<string, object>();
            foreach (object item in targets)
            {
                string name = Convert.ToString(item, CultureInfo.InvariantCulture);
                Rectangle rect;
                if (renderRows != null && renderRows.TryGetValue(name, out rect)) { found[name] = Box(rect); continue; }
                if (renderMenu != null && renderMenu.TryGetValue(name, out rect)) { found[name] = Box(rect); continue; }
                if (renderDialogBounds != null && renderDialogBounds.TryGetValue(name, out rect)) { found[name] = Box(rect); continue; }
                int row;
                if (RenderTask(name, out rect, out row)) { found[name] = Box(rect); continue; }
                if (name.StartsWith("menu.", StringComparison.Ordinal) || name.StartsWith("task.", StringComparison.Ordinal) ||
                    name.StartsWith("dialog.", StringComparison.Ordinal)) continue;
                Control control = name.StartsWith("row.", StringComparison.Ordinal) ? null : (RenderControl(name) ?? FocusTarget(name));
                if (control == null) continue;
                bool shows = true;
                for (Control c = control; c != null && c != this; c = c.Parent) shows &= OwnVisible(c);
                if (!shows) continue;
                Point at = InClient(control);
                found[name] = Box(new Rectangle(at, control.Size));
            }
            return found;
        }

        private static List<object> Box(Rectangle rect)
        {
            return new List<object> { (double)rect.X, (double)rect.Y, (double)rect.Width, (double)rect.Height };
        }

        /// v0.6.26: whether a frame with the window's own edge (`edge_dpi`) is cut before anything is laid over the window -
        /// every frame but those of a job that also asks for a still, which is cut from the uncut picture (FramedStill,
        /// SquircleStill) as before.
        private static bool EdgeFirst { get { return renderStill == null; } }

        /// v0.6.26: the veil the frame lays over the window - its alpha at the window's own pixels and its ink, [a, r, g, b] -
        /// or null: written with the frame (frames.json `veil`) for the pixels at the window's edge that are only partly the
        /// window's, which the picture's compositor dims at that share, over whatever lies under them (build/motion_compose.py
        /// WindowChrome.frame), as the product's veil dims them (DialogVeil: each pixel at its edge coverage).
        private List<object> renderVeil;

        // The veil at `alpha` as a frame writes it, or null where none is laid (PaintVeil's own rule).
        private static List<object> VeilOf(int alpha)
        {
            if (!DialogVeil.Enabled || Palette.Contrast || alpha <= 0) return null;
            Color ink = DialogVeil.Ink();
            return new List<object> { (double)alpha, (double)ink.R, (double)ink.G, (double)ink.B };
        }

        // ------------------------------------------------------------------ a dialog the window opened (v0.6.20)
        // The colour of the border Windows draws round a dialog (the job's `chrome`, from the committed still of the window).
        private static Dictionary<string, object> renderChrome;

        // The named parts of the dialog the last picture showed (`dialog.close`), in client coordinates.
        private Dictionary<string, Rectangle> renderDialogBounds;

        /// Where a dialog's window `size` big goes over the window `owner` big: centred on it, as StartPosition.CenterParent
        /// centres a dialog on the window that opened it.
        internal static Point RenderDialogPlace(Size size, Size owner)
        {
            return new Point((owner.Width - size.Width) / 2, (owner.Height - size.Height) / 2);
        }

        private static Color ChromeColour(Dictionary<string, object> chrome, string key, Color otherwise)
        {
            List<object> rgb = Items(chrome, key);
            if (rgb == null || rgb.Count != 3) return otherwise;
            // Written as the page writes a colour (brand.py's #RRGGBB), never as a colour of the window's own.
            return ColorTranslator.FromHtml(string.Format(CultureInfo.InvariantCulture, "#{0:X2}{1:X2}{2:X2}",
                                                          Convert.ToInt32(rgb[0], CultureInfo.InvariantCulture),
                                                          Convert.ToInt32(rgb[1], CultureInfo.InvariantCulture),
                                                          Convert.ToInt32(rgb[2], CultureInfo.InvariantCulture)));
        }

        /// A dialog the window opens, over the picture: built by the very method the click builds it with (BuildTimeline,
        /// which OpenTimeline shows) from the reply the bridge gives for the chosen row, its controls laid out and drawn as
        /// the window's own are (a top-level window in a picture would need the screen) - its title row and caption
        /// buttons among them (v0.6.24: no window has Windows' title bar) - within the border Windows draws round it, and
        /// centred on the window (RenderDialogPlace) over a soft shadow. `hover` or `pressed` naming `dialog.close` gives
        /// the title row's Close button that face.
        private void RenderDialog(Bitmap picture, Dictionary<string, object> dialog, string hover, string pressed,
                                  RenderWriter writer)
        {
            string kind = Str(dialog, "kind");
            ListView list = Str(dialog, "list") == "history" ? historyList : pendingList;
            if (kind != "timeline") { writer.Note("no dialog is called " + kind); return; }
            var row = Selected(list);
            if (row == null || IsDemo(row)) { writer.Note("no task is chosen for the " + kind + " dialog"); return; }
            var reply = RenderAnswer("timeline", IdArgument(row));
            if (!Ok(reply)) { writer.Note("the timeline of the chosen task was not answered"); return; }
            var result = Map(reply, "result");
            using (Form form = BuildTimeline(row, Items(result, "events"), Items(result, "receipts")))
            {
                // Its client area at the size it opens at, kept when the window's own frame is taken off it.
                Size client = form.ClientSize;
                form.TopLevel = false;
                form.FormBorderStyle = FormBorderStyle.None;
                form.ClientSize = client;
                // Shown as a child of Windows' parking window, as the window itself is (OpenForRender), never as a child
                // of the window: the grounds in it would stamp the window's own lifts into the dialog.
                form.CreateControl();
                IntPtr made = form.Handle;
                // v0.6.24: as it is once made - its title row at its top (SoftDialog), as a person's opens.
                client = form.ClientSize;
                form.Visible = true;
                for (int turn = 0; turn < 20; turn++)
                {
                    Application.DoEvents();
                    Application.RaiseIdle(EventArgs.Empty);
                    Materialise(form);
                    form.PerformLayout();
                    System.Threading.Thread.Sleep(10);
                }
                // v0.6.24: the title row's Close (SoftDialog's caption), where Windows' title bar had its own.
                var soft = form as SoftDialog;
                Control close = soft != null && soft.CaptionHost != null ? soft.CaptionHost.CloseButton : null;
                if (close != null) RenderCloseFace(close, hover == "dialog.close" || pressed == "dialog.close", pressed == "dialog.close");
                Application.DoEvents();
                using (var body = new Bitmap(client.Width, client.Height, PixelFormat.Format32bppArgb))
                {
                    // On the dialog's own ground, not on whatever is behind it: a soft control draws over its parent's.
                    using (Graphics ground = Graphics.FromImage(body)) ground.Clear(form.BackColor);
                    form.Invalidate(true);
                    form.DrawToBitmap(body, new Rectangle(Point.Empty, client));
                    PaintCaptionOver(body, form);
                    PaintListGutters(body, form);
                    // v0.6.24: no caption, the window's or the dialog's: the window's client area is the whole of it.
                    // v0.6.24 final: and with its own outer corner (DialogSquircle) no frame either - its window is its
                    // client area, its hairline and shadow the corner's (PaintDialog).
                    int border = DialogSquircle() ? 0 : Math.Max(1, Px(1));
                    Size outer = new Size(client.Width + 2 * border, client.Height + 2 * border);
                    Point place = RenderDialogPlace(outer, ClientSize);
                    // v0.6.24: the window dimmed under it, as it is for as long as the dialog is open (DialogVeil).
                    // v0.6.26 (audit-apng M3): the dialog fades in over Motion.Duration once it is painted (SoftDialog's
                    // OpenFade, FadeStep: 255 * Motion.Ease), `appear_ms` in, its own corner's edge and shadow with it, and
                    // the veil with it (DialogVeil at its fullest times the dialog's alpha, gui-audit D9).
                    int fade = RenderDialogAlpha(RenderMs(dialog, "appear_ms"));
                    PaintVeil(picture, (int)Math.Round(DialogVeil.FullNow * fade / 255.0));
                    renderVeil = VeilOf((int)Math.Round(DialogVeil.FullNow * fade / 255.0));
                    if (fade >= 255) PaintDialog(picture, body, place, outer, border, form.BackColor);
                    else if (fade > 0)
                        using (var under = (Bitmap)picture.Clone())
                        {
                            PaintDialog(picture, body, place, outer, border, form.BackColor);
                            Blend(picture, under, fade);
                        }
                    renderDialogBounds = new Dictionary<string, Rectangle>();
                    renderDialogBounds["dialog.window"] = new Rectangle(place.X, place.Y, outer.Width, outer.Height);
                    if (close != null)
                    {
                        Point inForm = new Point(close.Left, close.Top);
                        for (Control up = close.Parent; up != null && up != form; up = up.Parent) { inForm.X += up.Left; inForm.Y += up.Top; }
                        renderDialogBounds["dialog.close"] = new Rectangle(place.X + border + inForm.X, place.Y + border + inForm.Y,
                                                                          close.Width, close.Height);
                    }
                }
            }
        }

        // v0.6.26 (audit-apng M6): the moments on the picture's clock the pointer came onto the dialog's Close and pressed it,
        // or -1 - what a dialog built again for each frame is told its Close's glides began at.
        private double renderCloseOver = -1, renderCloseDown = -1;

        /// The dialog's Close given its face (SetRenderFace) as though it had been on the screen since the pointer came onto
        /// it: its hover begun at the moment that began, its press at the moment that began, each drawn at this frame's.
        private void RenderCloseFace(Control close, bool over, bool down)
        {
            double moment = Transition.RenderMs;
            bool clocked = moment >= 0;
            renderCloseOver = !over ? -1 : renderCloseOver >= 0 ? renderCloseOver : clocked ? moment : -1;
            renderCloseDown = !down ? -1 : renderCloseDown >= 0 ? renderCloseDown : clocked ? moment : -1;
            if (!over) return;
            // Painted once at rest first, as it has been on the screen before the pointer came: a glide starts only from a
            // look it has shown (SoftSurfaceGlide), and a dialog built anew has shown none.
            if (clocked && close.Width > 0 && close.Height > 0)
                using (var seen = new Bitmap(close.Width, close.Height, PixelFormat.Format32bppArgb))
                    close.DrawToBitmap(seen, new Rectangle(Point.Empty, close.Size));
            try
            {
                if (clocked) Transition.RenderMs = renderCloseOver;
                SetRenderFace(close, true, false);
                if (!down) return;
                if (clocked) Transition.RenderMs = renderCloseDown;
                SetRenderFace(close, true, true);
            }
            finally { Transition.RenderMs = moment; }
        }

        /// `icon` at `size` px for a picture: the image the .ico holds for that size, or the next larger, decoded as the PNG
        /// it is. Every image in codex-auto-resume.ico is PNG-compressed, and System.Drawing's Icon paints such an image as
        /// noise offscreen - DrawIcon, ToBitmap and a resized Icon alike (2026-10-30, the README's Timeline dialog); a real
        /// title bar is drawn by Windows and never meets this. An icon with no PNG image is drawn as before.
        internal static Bitmap IconImage(Icon icon, int size)
        {
            try
            {
                byte[] file;
                using (var saved = new MemoryStream()) { icon.Save(saved); file = saved.ToArray(); }
                int count = BitConverter.ToUInt16(file, 4), best = -1, bestSide = int.MaxValue;
                for (int i = 0; i < count; i++)
                {
                    int side = file[6 + 16 * i] == 0 ? 256 : file[6 + 16 * i];
                    if (side >= size && side < bestSide) { best = i; bestSide = side; }
                }
                if (best >= 0)
                {
                    int length = BitConverter.ToInt32(file, 6 + 16 * best + 8);
                    int offset = BitConverter.ToInt32(file, 6 + 16 * best + 12);
                    if (length > 8 && file[offset] == 0x89 && file[offset + 1] == (byte)'P' && file[offset + 2] == (byte)'N')
                    {
                        // The stream stays with the bitmap, as GDI+ asks of one it decodes from (a MemoryStream holds no
                        // handle); the image at its own size is returned as it is, so nothing resamples it.
                        var decoded = new Bitmap(new MemoryStream(file, offset, length));
                        if (decoded.Width == size && decoded.Height == size) return decoded;
                        using (decoded)
                        {
                            var fitted = new Bitmap(size, size, PixelFormat.Format32bppArgb);
                            using (Graphics g = Graphics.FromImage(fitted))
                            {
                                g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
                                g.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.HighQuality;
                                g.DrawImage(decoded, new Rectangle(0, 0, size, size));
                            }
                            return fitted;
                        }
                    }
                }
            }
            catch (Exception) { /* a picture's icon is decoration: fall back to what System.Drawing makes of it */ }
            using (var scaled = new Icon(icon, new Size(size, size))) return scaled.ToBitmap();
        }

        /// v0.6.24: the veil over the window while a dialog of its own is open (DialogVeil), over `picture` - the window's whole
        /// client area: the shadow's ink (DialogVeil.Ink) at the veil's alpha at its fullest in the theme (DialogVeil.FullNow:
        /// 51 in light, 82 in dark), laid as a layered window of that alpha is laid over what is under it; none in High
        /// Contrast nor where veils are off, as DialogVeil.Over makes none.
        /// v0.6.26 (audit-apng M3, guifix D9 and D10): as the product draws it - coming in with the dialog's own fade, step for
        /// step, at the dialog's alpha of its fullest (the other overload), clear while the dialog is, and going with the
        /// dialog at once, as the dialog's closing is; and over each of the window's pixels at how much of it is the window's.
        /// Every pixel here is the window's colour: the frame of a window with its own edge is cut before the veil is laid
        /// (RenderPicture), so its hairline is dimmed with the rest, as the veil dims the companion's hairline on the screen;
        /// a pixel the edge covers only in part is dimmed here as a whole one, and the compositor, which lays it over what is
        /// under it at its coverage, lays it as the product does - the veil at its fullest times that coverage over the
        /// window's edge and what shows through it alike (the frame's `veil`, build/motion_compose.py WindowChrome.frame).
        internal static void PaintVeil(Bitmap picture)
        {
            PaintVeil(picture, DialogVeil.FullNow);
        }

        /// v0.6.26 (audit-apng M3): the veil at `alpha`, the dialog's fade times its fullest, while the dialog fades in.
        internal static void PaintVeil(Bitmap picture, int alpha)
        {
            if (!DialogVeil.Enabled || Palette.Contrast || alpha <= 0) return;
            Color ink = DialogVeil.Ink();
            int[] pixels = Argb(picture);
            for (int i = 0; i < pixels.Length; i++)
            {
                int under = pixels[i];
                pixels[i] = (under & unchecked((int)0xFF000000)) |
                            (Veiled((under >> 16) & 0xFF, ink.R, alpha) << 16) |
                            (Veiled((under >> 8) & 0xFF, ink.G, alpha) << 8) |
                            Veiled(under & 0xFF, ink.B, alpha);
            }
            BitmapData data = picture.LockBits(new Rectangle(0, 0, picture.Width, picture.Height), ImageLockMode.WriteOnly,
                                               PixelFormat.Format32bppArgb);
            try
            {
                for (int y = 0; y < picture.Height; y++)
                    Marshal.Copy(pixels, y * picture.Width, new IntPtr(data.Scan0.ToInt64() + (long)y * data.Stride), picture.Width);
            }
            finally { picture.UnlockBits(data); }
        }

        /// v0.6.26 (audit-apng M3): how opaque the dialog is `appear` ms into its fade-in (SoftDialog.FadeStep): 255 times
        /// Motion.Ease over Motion.Duration, from clear; at rest (255) for -1.
        internal static int RenderDialogAlpha(double appear)
        {
            if (appear < 0) return 255;
            double t = appear / Math.Max(1, Motion.Duration);
            return t >= 1.0 ? 255 : (int)Math.Round(255 * Motion.Ease(t));
        }

        /// `picture` - the dialog laid whole over `under` - as the dialog's window at `alpha` shows it over what is under:
        /// each channel `alpha` of the way from under to it, as a layered window of that alpha is composed.
        internal static void Blend(Bitmap picture, Bitmap under, int alpha)
        {
            int[] over = Argb(picture), below = Argb(under);
            for (int i = 0; i < over.Length; i++)
            {
                int a = over[i], b = below[i];
                over[i] = unchecked((int)0xFF000000) |
                          (Veiled((b >> 16) & 0xFF, (a >> 16) & 0xFF, alpha) << 16) |
                          (Veiled((b >> 8) & 0xFF, (a >> 8) & 0xFF, alpha) << 8) |
                          Veiled(b & 0xFF, a & 0xFF, alpha);
            }
            BitmapData data = picture.LockBits(new Rectangle(0, 0, picture.Width, picture.Height), ImageLockMode.WriteOnly,
                                               PixelFormat.Format32bppArgb);
            try
            {
                for (int y = 0; y < picture.Height; y++)
                    Marshal.Copy(over, y * picture.Width, new IntPtr(data.Scan0.ToInt64() + (long)y * data.Stride), picture.Width);
            }
            finally { picture.UnlockBits(data); }
        }

        /// One channel `under` with the veil's `ink` laid over it at `alpha` (0 to 255), rounded to the nearest level.
        internal static int Veiled(int under, int ink, int alpha)
        {
            return (ink * alpha + under * (255 - alpha) + 127) / 255;
        }

        /// v0.6.24 final (the owner, 2026-11-20): whether a dialog in a picture has its own outer corner, as every dialog the
        /// Dashboard opens has on the screen (SoftDialog.BuildTitle, ChromeHost.OwnCorner): while the switch is on
        /// (Brand.WindowSquircle) and outside High Contrast, where WindowShape.Wanted gives Windows' corner. The rest of what
        /// Wanted asks - Windows 11, composition, not a remote session - is the machine's, never a picture's.
        internal static bool DialogSquircle()
        {
            return WindowShape.Switch && !Palette.Contrast;
        }

        /// The dialog's window over `picture`: a soft shadow, the border and the drawn client area - its title row and caption
        /// buttons in it (v0.6.24). v0.6.24 final: with its own outer corner (DialogSquircle) the dialog is laid as the
        /// screen composes it (LayDialog), its shadow and its body cut to the squircle; otherwise the rectangle and its
        /// border, as before.
        private void PaintDialog(Bitmap picture, Bitmap body, Point place, Size outer, int border, Color ground)
        {
            if (DialogSquircle())
            {
                LayDialog(picture, body, place, ground);
                return;
            }
            Color line = ChromeColour(renderChrome, "line", Soft.Mix(Canvas, Ink, 0.35));
            using (Graphics g = Graphics.FromImage(picture))
            {
                g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                // The shadow Windows puts round a window: a soft one, deeper below than above.
                int reach = Px(14), drop = Px(6);
                for (int step = reach; step >= 1; step--)
                {
                    // About a sixth of the light at the edge, over every layer that reaches it, fading out to nothing.
                    using (var brush = new SolidBrush(Soft.WithAlpha(Ink, 0.17 / reach)))
                        g.FillRectangle(brush, place.X - step, place.Y - step + drop, outer.Width + 2 * step, outer.Height + 2 * step);
                }
                g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.None;
                using (var brush = new SolidBrush(line))
                    g.FillRectangle(brush, place.X, place.Y, outer.Width, outer.Height);
                // The dialog's own ground under what its controls drew: a control that draws part of itself clear shows it,
                // not the shadow that lies under the whole window.
                using (var brush = new SolidBrush(ground))
                    g.FillRectangle(brush, place.X + border, place.Y + border, body.Width, body.Height);
                g.DrawImageUnscaled(body, place.X + border, place.Y + border);
            }
        }

        /// v0.6.24 final: `body` - the dialog's client area, its window - laid over `picture` at `place` as the screen shows a
        /// dialog with its own corner (WindowShape.Lay): the card's corner at the picture's display scale (DisplayScale, as
        /// the screen takes the monitor's and not the text size; Palette.RadiusCard, the design's smoothing), its region's pixels the dialog's, the hairline (Palette.Line) and the anti-aliased edge over
        /// them on the dialog's `ground`, and the companion's shadow (WindowCorner.Shade: the ink in light, the theme's
        /// all-but-black shadow in dark) round it on what lies under - nothing of the dialog outside its outline.
        internal static void LayDialog(Bitmap picture, Bitmap body, Point place, Color ground)
        {
            // The class by its full name: inside SettingsForm a member named Shape (a test probe's helper) would hide it.
            var edge = new WindowShape.Edge(body.Width, body.Height, Palette.RadiusCard, global::CodexAutoResume.Shape.Smoothing,
                                            DisplayScale);
            int[] under = Argb(picture), drawn = Argb(body);
            WindowShape.Lay(under, picture.Width, picture.Height, drawn, place, edge,
                            ground.A == 255 ? ground : Palette.Canvas, Palette.Line, WindowCorner.Shade());
            BitmapData data = picture.LockBits(new Rectangle(0, 0, picture.Width, picture.Height), ImageLockMode.WriteOnly,
                                               PixelFormat.Format32bppArgb);
            try
            {
                for (int y = 0; y < picture.Height; y++)
                    Marshal.Copy(under, y * picture.Width, new IntPtr(data.Scan0.ToInt64() + (long)y * data.Stride), picture.Width);
            }
            finally { picture.UnlockBits(data); }
        }

        // ------------------------------------------------------------------ the still a capture takes (v0.6.20)
        // The job's `still`: {"radius": the corners' in px, "dpi": the resolution a capture's bitmap has}. v0.6.24: no title
        // bar - the window's caption is its own, in its client area, so the client area is the whole window.
        private static Dictionary<string, object> renderStill;
        // The job's `edge_dpi`: above 0, every frame is written with the window's own outer edge at that resolution.
        private static int renderEdgeDpi;

        private static int StillNumber(Dictionary<string, object> still, string key)
        {
            object value;
            return still.TryGetValue(key, out value) && value != null ? Convert.ToInt32(value, CultureInfo.InvariantCulture) : 0;
        }

        private static int[] Argb(Bitmap picture)
        {
            var pixels = new int[picture.Width * picture.Height];
            BitmapData data = picture.LockBits(new Rectangle(0, 0, picture.Width, picture.Height), ImageLockMode.ReadOnly,
                                               PixelFormat.Format32bppArgb);
            try
            {
                for (int y = 0; y < picture.Height; y++)
                    Marshal.Copy(new IntPtr(data.Scan0.ToInt64() + (long)y * data.Stride), pixels, y * picture.Width, picture.Width);
            }
            finally { picture.UnlockBits(data); }
            return pixels;
        }

        /// The window as build/capture_window.ps1 photographs it, from the client area drawn here - v0.6.24: the whole window,
        /// its caption its own - opaque, with the corners Windows rounds cut, as that script cuts them (the same GDI+ fill of
        /// the same path, `radius` px, so the same pixels), its resolution `dpi`, as a capture's bitmap has the monitor's, so
        /// the PNG it is saved as says the same. Nothing of the screen is read.
        internal static Bitmap FramedStill(Bitmap client, int radius, int dpi)
        {
            int width = client.Width, height = client.Height;
            int[] pixels = Argb(client);
            for (int i = 0; i < pixels.Length; i++) pixels[i] = unchecked((int)0xFF000000) | (pixels[i] & 0xFFFFFF);
            using (var square = new Bitmap(width, height, PixelFormat.Format32bppArgb))
            {
                BitmapData data = square.LockBits(new Rectangle(0, 0, width, height), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
                try
                {
                    for (int y = 0; y < height; y++)
                        Marshal.Copy(pixels, y * width, new IntPtr(data.Scan0.ToInt64() + (long)y * data.Stride), width);
                }
                finally { square.UnlockBits(data); }
                Bitmap rounded = Rounded(square, radius);
                if (dpi > 0) rounded.SetResolution(dpi, dpi);
                return rounded;
            }
        }

        // Whether the job's still is cut by the window's own corner (its "corner": "squircle").
        private static bool StillSquircle()
        {
            object value;
            return renderStill != null && renderStill.TryGetValue("corner", out value) && value as string == "squircle";
        }

        /// v0.6.24 W5: the window as a still while it cuts its own outer corner: FramedStill's opaque client area, cut by
        /// CornerStill, its resolution `dpi`.
        internal static Bitmap SquircleStill(Bitmap client, int dpi)
        {
            int width = client.Width, height = client.Height;
            int[] pixels = Argb(client);
            for (int i = 0; i < pixels.Length; i++) pixels[i] = unchecked((int)0xFF000000) | (pixels[i] & 0xFFFFFF);
            using (var square = new Bitmap(width, height, PixelFormat.Format32bppArgb))
            {
                BitmapData data = square.LockBits(new Rectangle(0, 0, width, height), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
                try
                {
                    for (int y = 0; y < height; y++)
                        Marshal.Copy(pixels, y * width, new IntPtr(data.Scan0.ToInt64() + (long)y * data.Stride), width);
                }
                finally { square.UnlockBits(data); }
                Bitmap cut = CornerStill(square, dpi);
                if (dpi > 0) cut.SetResolution(dpi, dpi);
                return cut;
            }
        }

        /// v0.6.24 W5: `square` with the window's own outer corner as the screen shows it while Brand.WindowSquircle is on -
        /// the card's corner at the still's scale (`dpi`), the hairline and the edge its companion paints round the region,
        /// the corners clear (WindowShape.CutStill) - so a still and the screen agree (plans/v0624-stage1-design.md 5.6).
        internal static Bitmap CornerStill(Bitmap square, int dpi)
        {
            int width = square.Width, height = square.Height;
            // The class by its full name: inside SettingsForm a member named Shape (a test probe's helper) would hide it.
            var edge = new WindowShape.Edge(width, height, Palette.RadiusCard, global::CodexAutoResume.Shape.Smoothing,
                                            (dpi > 0 ? dpi : 96) / 96.0);
            int[] pixels = Argb(square);
            WindowShape.CutStill(pixels, edge, Palette.Line);
            var cut = new Bitmap(width, height, PixelFormat.Format32bppArgb);
            BitmapData data = cut.LockBits(new Rectangle(0, 0, width, height), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
            try
            {
                for (int y = 0; y < height; y++)
                    Marshal.Copy(pixels, y * width, new IntPtr(data.Scan0.ToInt64() + (long)y * data.Stride), width);
            }
            finally { cut.UnlockBits(data); }
            return cut;
        }

        /// `square` with its corners cut round, `radius` px, the corners left clear: build/capture_window.ps1's own steps -
        /// a new 32-bit ARGB bitmap, antialiased, high-quality pixel offsets, the four arcs filled through a texture of the
        /// picture - so a still drawn here and one captured on a monitor of that scale have the same corners.
        internal static Bitmap Rounded(Bitmap square, int radius)
        {
            int width = square.Width, height = square.Height;
            var rounded = new Bitmap(width, height, PixelFormat.Format32bppArgb);
            if (radius <= 0 || width <= 2 * radius || height <= 2 * radius)
            {
                using (Graphics g = Graphics.FromImage(rounded))
                {
                    g.CompositingMode = System.Drawing.Drawing2D.CompositingMode.SourceCopy;
                    g.DrawImage(square, new Rectangle(0, 0, width, height), 0, 0, width, height, GraphicsUnit.Pixel);
                }
                return rounded;
            }
            using (Graphics paint = Graphics.FromImage(rounded))
            using (var path = new System.Drawing.Drawing2D.GraphicsPath())
            using (var brush = new TextureBrush(square))
            {
                paint.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                paint.PixelOffsetMode = System.Drawing.Drawing2D.PixelOffsetMode.HighQuality;
                int d = 2 * radius;
                path.AddArc(0, 0, d, d, 180, 90);
                path.AddArc(width - d, 0, d, d, 270, 90);
                path.AddArc(width - d, height - d, d, d, 0, 90);
                path.AddArc(0, height - d, d, d, 90, 90);
                path.CloseFigure();
                paint.FillPath(brush, path);
            }
            return rounded;
        }

        /// Writes each frame as the rectangle that changed since the one before - the first whole - as raw RGB, and
        /// frames.json: the client size, each frame's rectangle and file, the bounds of its targets, what was noted.
        private sealed class RenderWriter
        {
            private readonly string folder;
            private int[] previous;
            private int width, height;
            private readonly StringBuilder frames = new StringBuilder();
            private readonly List<string> notes = new List<string>();
            internal string Error;

            internal RenderWriter(string folder) { this.folder = folder; }

            internal void Note(string text) { notes.Add(text); }

            /// v0.6.20: a frame's still (FramedStill), whole, as `still-<index>.png` beside the frames.
            internal void WriteStill(int index, Bitmap still)
            {
                still.Save(Path.Combine(folder, "still-" + index.ToString("D5", CultureInfo.InvariantCulture) + ".png"), ImageFormat.Png);
            }

            internal void Failed(string text) { Error = text; }

            internal void Write(int index, Bitmap picture, Dictionary<string, object> bounds, List<object> veil)
            {
                width = picture.Width;
                height = picture.Height;
                var pixels = new int[width * height];
                BitmapData data = picture.LockBits(new Rectangle(0, 0, width, height), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
                try
                {
                    for (int y = 0; y < height; y++)
                        Marshal.Copy(new IntPtr(data.Scan0.ToInt64() + (long)y * data.Stride), pixels, y * width, width);
                }
                finally { picture.UnlockBits(data); }
                int left = 0, top = 0, right = width - 1, bottom = height - 1;
                if (previous != null && previous.Length == pixels.Length)
                {
                    left = width; top = height; right = -1; bottom = -1;
                    for (int y = 0; y < height; y++)
                        for (int x = 0; x < width; x++)
                        {
                            if (((pixels[y * width + x] ^ previous[y * width + x]) & 0xFFFFFF) == 0) continue;
                            if (x < left) left = x;
                            if (x > right) right = x;
                            if (y < top) top = y;
                            if (y > bottom) bottom = y;
                        }
                }
                string file = "";
                if (right >= left && bottom >= top)
                {
                    file = index.ToString("D5", CultureInfo.InvariantCulture) + ".rgb";
                    int wide = right - left + 1, tall = bottom - top + 1;
                    var raw = new byte[wide * tall * 3];
                    for (int y = 0; y < tall; y++)
                        for (int x = 0; x < wide; x++)
                        {
                            int pixel = pixels[(top + y) * width + left + x], at = (y * wide + x) * 3;
                            raw[at] = (byte)(pixel >> 16);
                            raw[at + 1] = (byte)(pixel >> 8);
                            raw[at + 2] = (byte)pixel;
                        }
                    File.WriteAllBytes(Path.Combine(folder, file), raw);
                }
                else { left = top = 0; right = bottom = -1; }
                var entry = new Dictionary<string, object>();
                entry["index"] = (double)index;
                entry["box"] = new List<object> { (double)left, (double)top, (double)(right - left + 1), (double)(bottom - top + 1) };
                entry["file"] = file;
                entry["bounds"] = bounds;
                // v0.6.26: the veil the frame lays over the window (renderVeil), for the compositor's edge.
                if (veil != null) entry["veil"] = veil;
                if (frames.Length > 0) frames.Append(",\n");
                frames.Append(Json.Write(entry));
                previous = pixels;
            }

            internal void Finish(List<string> misses)
            {
                var notesJson = new List<object>();
                foreach (string note in notes) notesJson.Add(note);
                var missesJson = new List<object>();
                foreach (string miss in misses) missesJson.Add(miss);
                var text = new StringBuilder("{\"client\": [")
                    .Append(width.ToString(CultureInfo.InvariantCulture)).Append(", ")
                    .Append(height.ToString(CultureInfo.InvariantCulture)).Append("],\n\"dpi_scale\": ")
                    .Append(DpiScale.ToString("R", CultureInfo.InvariantCulture)).Append(",\n\"notes\": ")
                    .Append(Json.Write(notesJson)).Append(",\n\"misses\": ").Append(Json.Write(missesJson))
                    .Append(",\n\"error\": ").Append(Error == null ? "null" : Json.Escape(Error))
                    .Append(",\n\"frames\": [\n").Append(frames).Append("\n]}\n");
                File.WriteAllText(Path.Combine(folder, "frames.json"), text.ToString(), new UTF8Encoding(false));
            }
        }
    }
}
