// Codex Auto Resume - the setup program's window drawing frames of itself, offscreen, for the install motion picture
// (build/make_install_motion.py). Picture-build only.
//
// This file is never part of anything shipped: it is not in gui/window.sources and not in what build/make_setup.py
// compiles (tests/test_install_motion.py holds both). The picture's generator compiles it TOGETHER with the setup
// program's own sources - build/setup/Setup.cs, build/setup/SetupWindow.cs and the window's [installer], [controls] and
// [generated] groups, exactly as make_setup.py lists them - into a scratch program whose entry point is Main below, so
// the window drawn is the setup program's window, byte for byte the same code.
//
// It drives that window as a person and a run would, through the window's own doors: the window is made as
// SetupWindow.Run makes it - a first installation, or an update over an older version with what is new in it -
// (FlowFor, the catalog's words, the display's scale and text size), its primary button is
// clicked (Form.AcceptButton), the run is the window's own Start on its own worker, told each line the installer would
// print and how far the archive is unpacked - the lines install.ps1 really prints, from the plan - and the run ends
// with the code a run that succeeded ends with. Nothing is installed, unpacked, started or written anywhere but the
// job's folder: the runner only hands the window the plan's lines.
//
// For each frame of the job the window is put in the frame's page and progress (forward only), its primary button in
// its hover or pressed face (the button's own `hover` flag and Press, as gui/WindowRender.cs gives a face), its light
// held at the frame's moment of the state it is in (Soft.StillLightMs), and drawn into a bitmap, never shown: built as
// a child of Windows' parking window, as the render mode builds the Dashboard. Only what changed since the frame
// before is written, as raw RGB, with frames.json beside it, in the render mode's own format.
//
// C# 5 only: the in-box csc compiles it, as it compiles the setup program.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class InstallerRender
    {
        [DllImport("user32.dll", EntryPoint = "SendMessageW")]
        private static extern IntPtr SendMessage(IntPtr window, int message, IntPtr wParam, IntPtr lParam);

        private const int WM_UPDATEUISTATE = 0x0128;
        // UIS_SET with UISF_HIDEFOCUS | UISF_HIDEACCEL: the window as a person using the mouse sees it.
        private static readonly IntPtr HideCues = (IntPtr)0x00030001;
        // The pages of a first installation, in the order the window goes through them (InstallerFlow.Pages).
        private static readonly string[] Order = { InstallerFlow.Welcome, InstallerFlow.Options, InstallerFlow.Progress,
                                                   InstallerFlow.Finish };
        // The longest one step of the window may take to be shown, in milliseconds.
        private const int StepLimit = 10000;

        [STAThread]
        private static int Main(string[] arguments)
        {
            if (arguments.Length != 1 || !File.Exists(arguments[0])) return 2;
            var job = Json.Parse(File.ReadAllText(arguments[0], new UTF8Encoding(false))) as Dictionary<string, object>;
            if (job == null) return 2;
            string folder = Str(job, "out");
            if (string.IsNullOrEmpty(folder)) return 2;
            Directory.CreateDirectory(folder);
            var writer = new Writer(folder);
            Driver driver = null;
            try
            {
                driver = new Driver(job, writer);
                foreach (object item in Items(job, "frames"))
                {
                    var frame = item as Dictionary<string, object>;
                    if (frame == null) continue;
                    driver.Put(frame);
                    using (Bitmap picture = driver.Picture())
                        writer.Write(Int(frame, "index"), picture, driver.Bounds(Items(job, "targets")));
                }
            }
            catch (Exception error)
            {
                writer.Failed(error.ToString());
            }
            finally
            {
                if (driver != null) driver.Dispose();
                writer.Finish();
            }
            return writer.Error == null ? 0 : 2;
        }

        /// The window and the run behind it, put in one frame's state after another.
        private sealed class Driver : IDisposable
        {
            private readonly InstallerWindow window;
            private readonly List<object> events;
            private readonly Writer writer;
            // What the run is told next: an event of the plan, or the end. The worker takes one at a time and says when
            // it has handed it to the window (told).
            private readonly Queue<object> next = new Queue<object>();
            private readonly object gate = new object();
            private readonly AutoResetEvent given = new AutoResetEvent(false);
            private readonly AutoResetEvent told = new AutoResetEvent(false);
            private int delivered;
            private Control faced;
            private HaloDot light;
            private string lightState;
            private double lightSince;

            internal Driver(Dictionary<string, object> job, Writer writer)
            {
                this.writer = writer;
                events = Items(job, "events");
                string theme = Str(job, "theme") ?? "light", design = Str(job, "design") ?? "soft";
                string locales = Str(job, "locales"), language = Str(job, "locale") ?? "en";
                // As SetupWindow.Run opens the window: its look, the display's scale and Windows' text size.
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Soft.ReduceMotionSetting = false;
                Palette.AdoptDesign(design);
                Palette.Adopt(Theme.Current(theme));
                double read = TextScale.Read();
                SettingsForm.AdoptTextSize(TextScale.Fitting(read, Screen.PrimaryScreen.WorkingArea.Size, SettingsForm.SystemScale));
                Font font = TextScale.Apply(SystemFonts.MessageBoxFont, read, SettingsForm.TextSize);
                Soft.StillLightMs = 0;
                var spoken = new Dictionary<string, InstallerWords>();
                InstallerWindow.Speaker speaker = delegate(string other)
                {
                    InstallerWords found;
                    if (spoken.TryGetValue(other, out found)) return found;
                    string path = Path.Combine(locales ?? "", other + ".json");
                    var catalog = File.Exists(path)
                        ? InstallerFlow.ParseObject(File.ReadAllText(path, new UTF8Encoding(false)).TrimStart('\uFEFF'))
                        : null;
                    found = new InstallerWords(catalog, other);
                    spoken[other] = found;
                    return found;
                };
                // The flow the setup program makes for its archive's edition and version over what is installed: nothing
                // (a first installation), or an older version of an edition (an update), with what is new in the version
                // it carries read as SetupWindow.Run reads it (Archive.Notes).
                string installed = Str(job, "installed"), version = Str(job, "version");
                var flow = CodexAutoResumeSetup.SetupWindow.FlowFor(new string[0], Str(job, "home"), Str(job, "edition"),
                                                                    installed, version,
                                                                    installed == null ? "" : Str(job, "from") ?? "");
                if (flow.Upgrade && flow.Mode == InstallerFlow.Install && !flow.Maintaining)
                    flow.NotesText = Notes(Str(job, "docs"), language, version);
                window = new InstallerWindow(flow, speaker(language), speaker, Run, new string[0], font);
                Size client = window.ClientSize;
                window.TopLevel = false;
                window.FormBorderStyle = FormBorderStyle.None;
                window.ClientSize = client;
                window.CreateControl();
                IntPtr made = window.Handle;
                // A child of Windows' parking window, which is never on the screen.
                window.Visible = true;
                SendMessage(made, WM_UPDATEUISTATE, HideCues, IntPtr.Zero);
                Settle();
                light = Find<HaloDot>(window);
                if (light == null) throw new InvalidOperationException("the window has no status light");
            }

            /// The run the window starts (InstallerWindow.Runner): it tells the window each event the frames ask for,
            /// one at a time, and ends with the code it is given - as Setup.cs's InstallFrom tells it what the installer
            /// prints and how far the archive is unpacked.
            private int Run(InstallerFlow flow, Action<string> line, Action<double> unpacked)
            {
                while (true)
                {
                    object item;
                    lock (gate)
                    {
                        while (next.Count == 0) Monitor.Wait(gate);
                        item = next.Dequeue();
                    }
                    if (item is int) return (int)item;
                    var said = (Dictionary<string, object>)item;
                    if (said.ContainsKey("unpacked")) unpacked(Convert.ToDouble(said["unpacked"], CultureInfo.InvariantCulture));
                    else line(Str(said, "line") ?? "");
                    told.Set();
                }
            }

            private void Tell(object item)
            {
                lock (gate)
                {
                    next.Enqueue(item);
                    Monitor.PulseAll(gate);
                }
            }

            /// Puts the window in `frame`'s state: its page and its progress, forward only, as the window's own
            /// buttons and run take it there; the primary button's face; the light's moment.
            internal void Put(Dictionary<string, object> frame)
            {
                string page = Str(frame, "page") ?? InstallerFlow.Welcome;
                int want = Array.IndexOf(Order, page);
                if (want < 0) throw new InvalidDataException("the window has no page " + page);
                int progress = frame.ContainsKey("progress") ? Int(frame, "progress") : delivered;
                if (progress < delivered || progress > events.Count)
                    throw new InvalidDataException("progress " + progress + " after " + delivered + " of " + events.Count);
                int at = Array.IndexOf(Order, window.Page);
                if (want < at) throw new InvalidDataException("the window is on " + window.Page + " and cannot go back to " + page);
                while (Array.IndexOf(Order, window.Page) < Math.Min(want, Array.IndexOf(Order, InstallerFlow.Progress)))
                {
                    // Next on the Welcome page, Install on Options: the window's own primary button.
                    string before = window.Page;
                    Face(null, null);
                    ((Button)window.AcceptButton).PerformClick();
                    Settle();
                    if (window.Page == before) throw new InvalidOperationException("the window's " + ((Button)window.AcceptButton).Text + " did not leave " + before);
                }
                while (delivered < progress)
                {
                    if (window.Page != InstallerFlow.Progress) throw new InvalidDataException("progress is told only while the window is installing");
                    Tell(events[delivered]);
                    if (!told.WaitOne(StepLimit)) throw new TimeoutException("the run did not take event " + delivered);
                    delivered++;
                    Settle();
                }
                if (want == Array.IndexOf(Order, InstallerFlow.Finish) && window.Page != InstallerFlow.Finish)
                {
                    if (delivered != events.Count) throw new InvalidDataException("the run ends only after every event");
                    Tell(0);
                    var waited = Stopwatch.StartNew();
                    while (window.Page != InstallerFlow.Finish && waited.ElapsedMilliseconds < StepLimit) Settle();
                }
                if (window.Page != page) throw new InvalidOperationException("the window shows " + window.Page + ", the frame " + page);
                Face(Str(frame, "hover"), Str(frame, "pressed"));
                // The light at the frame's moment of the state it is in: its own clock starts when the state does.
                double t = frame.ContainsKey("light") ? Convert.ToDouble(frame["light"], CultureInfo.InvariantCulture) : 0;
                if (light.State != lightState)
                {
                    lightState = light.State;
                    lightSince = t;
                }
                Soft.StillLightMs = Math.Max(0, t - lightSince);
                Settle();
            }

            /// The hover or pressed face of the control a frame names, as the pointer gives it.
            private void Face(string hover, string pressed)
            {
                if (faced != null) SetFace(faced, false, false);
                faced = null;
                string name = pressed ?? hover;
                if (name == null) return;
                Control control = Target(name);
                if (control == null) { writer.Note("no control is called " + name); return; }
                SetFace(control, true, pressed != null);
                faced = control;
            }

            private static void SetFace(Control control, bool hover, bool pressed)
            {
                const System.Reflection.BindingFlags own = System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance;
                Type type = control.GetType();
                System.Reflection.FieldInfo hovered = type.GetField("hover", own);
                if (hovered != null && hovered.FieldType == typeof(bool)) hovered.SetValue(control, hover);
                System.Reflection.MethodInfo press = type.GetMethod("Press", own, null, new[] { typeof(bool) }, null);
                if (press != null) press.Invoke(control, new object[] { pressed });
                control.Invalidate();
            }

            /// A control the plan names: `button.forward` is the page's primary button (Next, Install, Finish).
            private Control Target(string name)
            {
                if (name == "button.forward") return window.AcceptButton as Control;
                return null;
            }

            /// Pumps the window's messages until nothing moves.
            private void Settle()
            {
                var waited = Stopwatch.StartNew();
                int quiet = 0;
                while (waited.ElapsedMilliseconds < StepLimit)
                {
                    Application.DoEvents();
                    Application.RaiseIdle(EventArgs.Empty);
                    if (Transition.Moving > 0) quiet = 0;
                    else if (++quiet >= 3) return;
                    Thread.Sleep(5);
                }
                writer.Note("the " + window.Page + " page did not hold still");
            }

            internal Bitmap Picture()
            {
                var picture = new Bitmap(window.ClientSize.Width, window.ClientSize.Height, PixelFormat.Format32bppArgb);
                window.Invalidate(true);
                window.DrawToBitmap(picture, new Rectangle(Point.Empty, window.ClientSize));
                return picture;
            }

            /// The bounds, in client coordinates, of every target the job names that shows now.
            internal Dictionary<string, object> Bounds(List<object> targets)
            {
                var found = new Dictionary<string, object>();
                foreach (object item in targets)
                {
                    string name = Convert.ToString(item, CultureInfo.InvariantCulture);
                    Control control = Target(name);
                    if (control == null || !control.Visible) continue;
                    int x = 0, y = 0;
                    for (Control c = control; c != null && c != window; c = c.Parent) { x += c.Left; y += c.Top; }
                    found[name] = new List<object> { (double)x, (double)y, (double)control.Width, (double)control.Height };
                }
                return found;
            }

            public void Dispose()
            {
                // A run still waiting is ended, so its worker does not outlive the window.
                Tell(InstallerFlow.NotStarted);
                window.Dispose();
            }
        }

        /// What is new in `version`: its section of the changelog, the language's own where there is one - as the setup
        /// program reads it from the archive it carries (SetupWindow.Archive.Notes), here from the docs folder the
        /// archive is made from.
        private static string Notes(string docs, string language, string version)
        {
            string own = language == "en" ? null : Text(Path.Combine(docs ?? "", "CHANGELOG." + language + ".md"));
            return InstallerNotes.Section(own ?? Text(Path.Combine(docs ?? "", "CHANGELOG.md")), version);
        }

        private static string Text(string path)
        {
            return File.Exists(path) ? File.ReadAllText(path, new UTF8Encoding(false)).TrimStart('\uFEFF') : null;
        }

        private static T Find<T>(Control root) where T : Control
        {
            foreach (Control child in root.Controls)
            {
                if (child is T) return (T)child;
                T found = Find<T>(child);
                if (found != null) return found;
            }
            return null;
        }

        private static string Str(Dictionary<string, object> map, string key)
        {
            object value;
            return map != null && map.TryGetValue(key, out value) && value != null
                ? Convert.ToString(value, CultureInfo.InvariantCulture) : null;
        }

        private static int Int(Dictionary<string, object> map, string key)
        {
            return Convert.ToInt32(map[key], CultureInfo.InvariantCulture);
        }

        private static List<object> Items(Dictionary<string, object> map, string key)
        {
            object value;
            return map != null && map.TryGetValue(key, out value) && value is List<object> ? (List<object>)value : new List<object>();
        }

        /// Writes each frame as the rectangle that changed since the one before - the first, and any after the window
        /// changed size, whole - as raw RGB, and frames.json: each frame's client size, rectangle and file, the bounds
        /// of its targets, what was noted. gui/WindowRender.cs's format, with the client size per frame.
        private sealed class Writer
        {
            private readonly string folder;
            private int[] previous;
            private int width, height;
            private readonly StringBuilder frames = new StringBuilder();
            private readonly List<object> notes = new List<object>();
            internal string Error;

            internal Writer(string folder) { this.folder = folder; }

            internal void Note(string text) { notes.Add(text); }

            internal void Failed(string text) { Error = text; }

            internal void Write(int index, Bitmap picture, Dictionary<string, object> bounds)
            {
                bool resized = picture.Width != width || picture.Height != height;
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
                if (previous != null && !resized)
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
                entry["client"] = new List<object> { (double)width, (double)height };
                entry["box"] = new List<object> { (double)left, (double)top, (double)(right - left + 1), (double)(bottom - top + 1) };
                entry["file"] = file;
                entry["bounds"] = bounds;
                if (frames.Length > 0) frames.Append(",\n");
                frames.Append(Json.Write(entry));
                previous = pixels;
            }

            internal void Finish()
            {
                var text = new StringBuilder("{\"client\": [")
                    .Append(width.ToString(CultureInfo.InvariantCulture)).Append(", ")
                    .Append(height.ToString(CultureInfo.InvariantCulture)).Append("],\n\"dpi_scale\": ")
                    .Append(SettingsForm.DpiScale.ToString("R", CultureInfo.InvariantCulture)).Append(",\n\"notes\": ")
                    .Append(Json.Write(notes)).Append(",\n\"misses\": [],\n\"error\": ")
                    .Append(Error == null ? "null" : Json.Escape(Error))
                    .Append(",\n\"frames\": [\n").Append(frames).Append("\n]}\n");
                File.WriteAllText(Path.Combine(folder, "frames.json"), text.ToString(), new UTF8Encoding(false));
            }
        }
    }
}
