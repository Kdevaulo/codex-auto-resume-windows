r"""v0.6.24 final: every dialog the Dashboard opens has the Dashboard's own squircle corner, on the screen and in pictures.

The owner, 2026-11-20: "대시보드 앱 안에서 뜨는 창들은 스쿼글이 아니네" (the Dashboard's dialogs had Windows' corner) and "apng에서는
아예 모서리가 뽀족한 네모창으로 나와" (the README motion drew the Timeline dialog as a sharp-cornered rectangle).

On the screen (gui/SoftChrome.cs SoftDialog.BuildTitle): every titled dialog - all the Dashboard's (Soft.DialogBar) - asks
for its outer corner with the Dashboard's one call, ChromeHost.OwnCorner, so it is the shared corner of
gui/SoftWindowShape.cs under the same switch and the same exceptions (Brand.WindowSquircle, WindowShape.Wanted and
Decide): the card's corner at the design's card radius (Palette.RadiusCard - a squircle in Soft, circular arcs in Classic
and Plain, O10), its region, its companion with the hairline, the edge and the shadow, DWMWCP_DONOTROUND, no frame. The
dialog keeps its own cloak, its fade and its veil: the corner leaves the cloak to it (WindowCorner.HostCloaks), its
companion is held off while the dialog is (Held) and is drawn at the dialog's fade alpha (Opacity).

In pictures (gui/WindowRender.cs PaintDialog): with the switch on and outside High Contrast (DialogSquircle) the dialog is
laid as the screen composes it (WindowShape.Lay through LayDialog): its region's pixels, the companion's picture over them
and over what lies under - nothing of the dialog outside its outline.

A probe compiled with the window's sources:

* plain titled dialogs - sizable and fixed, Soft, Classic and Plain - shown 30000 px off the desktop over an owner shown
  there too, never activated (SW_SHOWNOACTIVATE), sampled through their opening: held off with the dialog while it is
  cloaked, then at the dialog's own alpha at every step of its fade, then the corner, the region, the companion, no frame,
  the window its own client area; the resize band on a sizable dialog's edges, none on a fixed one; minimised Windows'
  corner and back its own; with motion reduced no fade and the companion opaque at once;
* the exceptions: High Contrast (WindowShape.Wanted false) and a dialog laid out as a child (the audit, the render mode)
  have no corner of their own and are as before;
* the Dashboard's real dialogs, built by the methods its clicks build them with, shown the same way: each has the corner;
* WindowShape.Lay at 100, 150 and 200 %, in Soft, Classic and Plain, held to the ideal corner worked out from
  brand/shape.py (tests/test_gui_window_corner.py's _Ideal): every pixel within 2 levels, the hairline round it, what was
  under it untouched outside its shadow, and the dialog's own pixels only inside its outline.

And the window's render mode draws the Timeline over Pending, as the README motion does: its corners cut, the hairline
round it, its ground inside.

GUI test module (it shows windows, off the screen): run on its own, through gui_lock.sh.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "tests"), str(ROOT / "build")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import guiscan  # noqa: E402
from codex_auto_resume import brand, l10n  # noqa: E402
from codex_auto_resume.brand import shape  # noqa: E402
from test_gui_layout import fullest_snapshot  # noqa: E402
from test_gui_window_corner import _Ideal  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
HTCLIENT, HTCAPTION, HTLEFT, HTBOTTOMRIGHT = 1, 2, 10, 17
RESIZE = set(range(HTLEFT, HTBOTTOMRIGHT + 1))

LAY_SCALES = (1.0, 1.5, 2.0)
LAY_LOGICAL = (96, 84)
GROUND, LINE, SHADE, BODY = (0xF2, 0xF4, 0xF7), (0xC9, 0xCF, 0xD8), (0x1B, 0x1F, 0x24), (0xE0, 0x10, 0xC0)
UNDER = ("grey", "checker")

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class CornerNative
    {
        [DllImport("dwmapi.dll")] internal static extern int DwmGetWindowAttribute(IntPtr h, int attribute, out int value, int size);
        [DllImport("user32.dll")] internal static extern IntPtr SendMessage(IntPtr h, int msg, IntPtr w, IntPtr l);
        [DllImport("user32.dll")] internal static extern bool IsWindowVisible(IntPtr h);
        [DllImport("user32.dll")] internal static extern bool IsWindow(IntPtr h);
        [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr h, int command);
        [DllImport("user32.dll")] internal static extern bool GetWindowRect(IntPtr h, out Chrome.RECT r);
        [DllImport("user32.dll")] internal static extern int GetWindowRgn(IntPtr h, IntPtr region);
        [DllImport("user32.dll")] internal static extern int GetWindowLong(IntPtr window, int index);
        [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] internal static extern IntPtr GetWindowLongPtr(IntPtr h, int i);
        [DllImport("gdi32.dll")] internal static extern IntPtr CreateRectRgn(int l, int t, int r, int b);
        [DllImport("gdi32.dll")] internal static extern bool PtInRegion(IntPtr region, int x, int y);
        [DllImport("gdi32.dll")] internal static extern bool DeleteObject(IntPtr o);

        internal const int Away = -30000, SW_SHOWNOACTIVATE = 4, SW_SHOWMINNOACTIVE = 7;

        internal static void Pump(int times)
        {
            for (int i = 0; i < times; i++) { Application.DoEvents(); Thread.Sleep(10); }
        }

        internal static Rectangle Rect(IntPtr h)
        {
            Chrome.RECT r;
            GetWindowRect(h, out r);
            return Rectangle.FromLTRB(r.Left, r.Top, r.Right, r.Bottom);
        }

        internal static List<object> Box(Rectangle r)
        {
            return new List<object> { (double)r.X, (double)r.Y, (double)r.Width, (double)r.Height };
        }

        internal static double Attribute(IntPtr h, int attribute)
        {
            int value;
            return DwmGetWindowAttribute(h, attribute, out value, 4) == 0 ? value : -1;
        }

        internal static bool Cloaked(IntPtr h)
        {
            return Attribute(h, 14) > 0;
        }

        internal static int RegionKind(IntPtr h)
        {
            IntPtr region = CreateRectRgn(0, 0, 0, 0);
            try { return GetWindowRgn(h, region); }
            finally { DeleteObject(region); }
        }

        internal static bool InRegion(IntPtr h, int x, int y)
        {
            IntPtr region = CreateRectRgn(0, 0, 0, 0);
            try { return GetWindowRgn(h, region) == 0 || PtInRegion(region, x, y); }
            finally { DeleteObject(region); }
        }

        // What Windows' question of what the pointer is over gets at `screen`, asked of the deepest child window first.
        internal static int Route(Control parent, Point screen)
        {
            for (int i = 0; i < parent.Controls.Count; i++)
            {
                Control c = parent.Controls[i];
                if (!Soft.OwnVisible(c) || !c.IsHandleCreated) continue;
                Chrome.RECT r;
                GetWindowRect(c.Handle, out r);
                if (screen.X < r.Left || screen.X >= r.Right || screen.Y < r.Top || screen.Y >= r.Bottom) continue;
                int code = Route(c, screen);
                if (code != Chrome.HTTRANSPARENT) return code;
            }
            IntPtr at = (IntPtr)(((screen.Y & 0xFFFF) << 16) | (screen.X & 0xFFFF));
            return SendMessage(parent.Handle, Chrome.WM_NCHITTEST, IntPtr.Zero, at).ToInt32();
        }

        internal static Dictionary<string, object> State(Form window)
        {
            IntPtr h = window.Handle;
            var soft = window as SoftDialog;
            WindowCorner corner = soft == null ? null : soft.OwnCorner;
            ChromeHost chrome = soft == null ? null : soft.CaptionHost;
            Rectangle whole = Rect(h);
            IntPtr companion = corner == null ? IntPtr.Zero : corner.Companion;
            var said = new Dictionary<string, object> {
                { "state", window.WindowState.ToString() },
                { "has", corner != null },
                { "corner", chrome == null ? "none" : chrome.OuterCorner.ToString() },
                { "frameless", chrome != null && chrome.Frameless },
                { "hostCloaks", corner != null && corner.HostCloaks },
                { "preference", Attribute(h, Soft.CornerPreferenceAttribute) },
                { "dwmFrame", Attribute(h, 1) },
                { "region", (double)RegionKind(h) },
                { "window", Box(whole) },
                { "client", new List<object> { (double)window.ClientSize.Width, (double)window.ClientSize.Height } },
                { "companion", companion != IntPtr.Zero && IsWindow(companion) },
                { "companionShown", companion != IntPtr.Zero && IsWindowVisible(companion) },
                { "companionAlpha", (double)(corner == null ? -1 : corner.CompanionAlpha) },
                { "cloaked", Cloaked(h) },
                { "layered", (GetWindowLong(h, -20) & 0x00080000) != 0 } };
            if (soft != null) said["fade"] = (double)soft.FadeAlpha;
            said["outermost"] = new List<object> {
                InRegion(h, 0, whole.Height / 2), InRegion(h, whole.Width - 1, whole.Height / 2),
                InRegion(h, whole.Width / 2, 0), InRegion(h, whole.Width / 2, whole.Height - 1) };
            said["cutCorners"] = new List<object> {
                InRegion(h, 0, 0), InRegion(h, whole.Width - 1, 0), InRegion(h, 0, whole.Height - 1),
                InRegion(h, whole.Width - 1, whole.Height - 1) };
            return said;
        }

        static void Note(List<object> codes, int code)
        {
            if (!codes.Contains((double)code)) codes.Add((double)code);
        }

        // Every edge, every 5 px along it, 0 to 5 px in: the distinct answers, as Windows routes the question.
        internal static Dictionary<string, object> Edges(Form window)
        {
            Rectangle w = Rect(window.Handle);
            var left = new List<object>();
            var right = new List<object>();
            var top = new List<object>();
            var bottom = new List<object>();
            for (int d = 0; d < 5; d++)
            {
                for (int y = w.Top + w.Height / 4; y < w.Bottom - w.Height / 4; y += 5)
                {
                    Note(left, Route(window, new Point(w.Left + d, y)));
                    Note(right, Route(window, new Point(w.Right - 1 - d, y)));
                }
                for (int x = w.Left + w.Width / 4; x < w.Right - w.Width / 4; x += 5)
                {
                    Note(top, Route(window, new Point(x, w.Top + d)));
                    Note(bottom, Route(window, new Point(x, w.Bottom - 1 - d)));
                }
            }
            return new Dictionary<string, object> { { "left", left }, { "right", right }, { "top", top }, { "bottom", bottom } };
        }

        // Shown off the desktop, never activated, and sampled through its opening: whether the companion was ever seen
        // while the dialog was held off the screen, and how far its alpha ever stood from the dialog's own.
        internal static Dictionary<string, object> Open(Form window)
        {
            var said = new Dictionary<string, object>();
            var soft = window as SoftDialog;
            IntPtr h = window.Handle;
            said["made"] = State(window);
            ShowWindow(h, SW_SHOWNOACTIVATE);
            said["first"] = State(window);
            // As it is shown: whether it fades in (OpensWithFade reads false again once it is opaque).
            said["opensWithFade"] = soft != null && soft.OpensWithFade;
            bool shownWhileCloaked = false, shownBeforeSeen = false;
            double worst = 0, alphas = 0;
            var steps = new List<object>();
            var clock = System.Diagnostics.Stopwatch.StartNew();
            while (clock.ElapsedMilliseconds < 900)
            {
                Application.DoEvents();
                WindowCorner corner = soft == null ? null : soft.OwnCorner;
                if (corner != null && corner.Companion != IntPtr.Zero)
                {
                    bool shown = IsWindowVisible(corner.Companion);
                    if (shown && Cloaked(h)) shownWhileCloaked = true;
                    if (shown && soft.Cloaked) shownBeforeSeen = true;
                    if (shown && !Cloaked(h))
                    {
                        double gap = Math.Abs(corner.CompanionAlpha - soft.FadeAlpha);
                        worst = Math.Max(worst, gap);
                        alphas++;
                        if (steps.Count == 0 || (double)steps[steps.Count - 1] != corner.CompanionAlpha)
                            steps.Add((double)corner.CompanionAlpha);
                    }
                }
                Thread.Sleep(2);
            }
            Pump(5);
            said["shownWhileCloaked"] = shownWhileCloaked;
            said["shownBeforeSeen"] = shownBeforeSeen;
            said["worstGap"] = worst;
            said["samples"] = alphas;
            said["steps"] = steps;
            said["shown"] = State(window);
            return said;
        }
    }

    internal static class DialogCornerProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try
            {
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Palette.AdoptDesign("soft");
                Palette.Adopt("light");
                said["wanted"] = WindowShape.Wanted();
                said["switch"] = WindowShape.Switch;
                said["sizable"] = Scene(true, false);
                said["fixed"] = Scene(false, false);
                Soft.ReduceMotionSetting = true;
                said["still"] = Scene(false, false);
                Soft.ReduceMotionSetting = false;
                foreach (string design in new[] { "classic", "plain" })
                {
                    Palette.AdoptDesign(design);
                    said[design] = Scene(false, false);
                }
                Palette.AdoptDesign("soft");
                Palette.Contrast = true;
                said["contrastWanted"] = WindowShape.Wanted();
                said["contrast"] = Scene(false, true);
                Palette.Contrast = false;
                said["child"] = Child();
                SettingsForm.DialogCornerRun(argv[1], said);
                said["lay"] = Lay(argv[2]);
                said["radius"] = (double)Palette.RadiusCard;
            }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }

        static Form Owner()
        {
            var owner = new Form();
            owner.FormBorderStyle = FormBorderStyle.None;
            owner.ShowInTaskbar = false;
            owner.StartPosition = FormStartPosition.Manual;
            owner.Location = new Point(CornerNative.Away, CornerNative.Away);
            owner.Size = new Size(900, 700);
            IntPtr h = owner.Handle;
            CornerNative.ShowWindow(h, CornerNative.SW_SHOWNOACTIVATE);
            CornerNative.Pump(3);
            return owner;
        }

        static SoftDialog Plain(bool sizable)
        {
            var d = new SoftDialog();
            d.Text = "A dialog of the Dashboard's";
            d.BackColor = Palette.Canvas;
            Soft.DialogBar(d);
            d.FormBorderStyle = sizable ? FormBorderStyle.Sizable : FormBorderStyle.FixedDialog;
            d.MinimizeBox = sizable;
            d.MaximizeBox = sizable;
            d.StartPosition = FormStartPosition.Manual;
            d.Location = new Point(CornerNative.Away + 100, CornerNative.Away + 100);
            d.ShowInTaskbar = false;
            d.ClientSize = new Size(Soft.Px(360), Soft.Px(220));
            return d;
        }

        static Dictionary<string, object> Scene(bool sizable, bool contrast)
        {
            Form owner = Owner();
            SoftDialog dialog = Plain(sizable);
            dialog.Owner = owner;
            Dictionary<string, object> said = CornerNative.Open(dialog);
            Padding frame = Chrome.Frame((int)CornerNative.GetWindowLongPtr(dialog.Handle, -16).ToInt64(),
                                         (int)CornerNative.GetWindowLongPtr(dialog.Handle, -20).ToInt64());
            said["styleFrame"] = new List<object> { (double)frame.Left, (double)frame.Top, (double)frame.Right, (double)frame.Bottom };
            said["edges"] = CornerNative.Edges(dialog);
            said["sizableLayout"] = dialog.CaptionHost.Layout().Sizable;
            if (sizable && !contrast)
            {
                CornerNative.ShowWindow(dialog.Handle, CornerNative.SW_SHOWMINNOACTIVE);
                CornerNative.Pump(5);
                said["minimised"] = CornerNative.State(dialog);
                CornerNative.ShowWindow(dialog.Handle, CornerNative.SW_SHOWNOACTIVATE);
                CornerNative.Pump(5);
                said["back"] = CornerNative.State(dialog);
            }
            WindowCorner corner = dialog.OwnCorner;
            IntPtr companion = corner == null ? IntPtr.Zero : corner.Companion;
            dialog.Close();
            dialog.Dispose();
            CornerNative.Pump(3);
            said["companionGone"] = companion == IntPtr.Zero || !CornerNative.IsWindow(companion);
            owner.Close();
            owner.Dispose();
            return said;
        }

        static Dictionary<string, object> Child()
        {
            var said = new Dictionary<string, object>();
            SoftDialog dialog = Plain(true);
            dialog.TopLevel = false;
            dialog.MakeTitle();
            IntPtr h = dialog.Handle;
            CornerNative.Pump(3);
            said["has"] = dialog.OwnCorner != null;
            said["frameless"] = dialog.CaptionHost.Frameless;
            dialog.Dispose();
            return said;
        }

        static string Pixels(int[] values)
        {
            var bytes = new byte[values.Length * 4];
            Buffer.BlockCopy(values, 0, bytes, 0, bytes.Length);
            return Convert.ToBase64String(bytes);
        }

        // lay width height radius smoothing scale under ground line shade body: the dialog laid over a picture, as
        // WindowRender.LayDialog lays it.
        static List<object> Lay(string cases)
        {
            var C = CultureInfo.InvariantCulture;
            var all = new List<object>();
            foreach (string entry in File.ReadAllLines(cases))
            {
                string[] w = entry.Split(' ');
                int width = int.Parse(w[1], C), height = int.Parse(w[2], C);
                var edge = new WindowShape.Edge(width, height, double.Parse(w[3], C), double.Parse(w[4], C), double.Parse(w[5], C));
                int m = edge.Margin;
                var place = new Point(m + 3, m + 5);
                int across = width + 2 * m + 8, down = height + 2 * m + 10;
                var picture = new int[across * down];
                for (int y = 0; y < down; y++)
                    for (int x = 0; x < across; x++)
                    {
                        int v = w[6] == "grey" ? 128 : (((x / 8) + (y / 8)) % 2 == 0 ? 255 : 0);
                        picture[y * across + x] = unchecked((int)0xFF000000) | v << 16 | v << 8 | v;
                    }
                Color body = ColorTranslator.FromHtml(w[10]);
                var drawn = new int[width * height];
                for (int i = 0; i < drawn.Length; i++) drawn[i] = body.ToArgb();
                WindowShape.Lay(picture, across, down, drawn, place, edge, ColorTranslator.FromHtml(w[7]),
                                ColorTranslator.FromHtml(w[8]), ColorTranslator.FromHtml(w[9]));
                all.Add(new Dictionary<string, object> {
                    { "across", (double)across }, { "down", (double)down }, { "x", (double)place.X }, { "y", (double)place.Y },
                    { "hair", (double)edge.Hair }, { "reach", (double)edge.Reach }, { "drop", (double)edge.Drop },
                    { "margin", (double)m }, { "pixels", Pixels(picture) } });
            }
            return all;
        }
    }

    internal sealed partial class SettingsForm
    {
        internal static void DialogCornerRun(string dir, Dictionary<string, object> said)
        {
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-en.json"), Encoding.UTF8)) as Dictionary<string, object>;
            var snapshot = Json.Parse(File.ReadAllText(Path.Combine(dir, "snapshot.json"), Encoding.UTF8)) as Dictionary<string, object>;
            string nowhere = Path.Combine(dir, "nowhere");
            using (var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, null))
            {
                form.auditing = true;
                form.TopLevel = false;
                var row = ((List<object>)snapshot["pending"])[0] as Dictionary<string, object>;
                var events = new List<object>();
                var entry = new Dictionary<string, object>();
                entry["at"] = 1.8e9;
                entry["code"] = "detected";
                entry["to_code"] = "waiting_reset";
                events.Add(entry);
                var dialogs = new Dictionary<string, object>();
                var made = new Dictionary<string, Func<Form>> {
                    { "conversation", delegate { return form.BuildConversationMessage(row, "Carry on, please."); } },
                    { "once", delegate { return form.BuildOnceWords(row, "Then run the tests."); } },
                    { "timeline", delegate { return form.BuildTimeline(row, events, null); } },
                    { "logs", delegate { return form.BuildLogs(); } },
                    { "check", delegate { return form.BuildDetectionCheck(); } },
                    { "report", delegate { return form.BuildOwnReport(); } },
                    { "versions", delegate { return form.BuildVersions(); } } };
                foreach (KeyValuePair<string, Func<Form>> one in made)
                {
                    using (Form d = one.Value())
                    {
                        d.StartPosition = FormStartPosition.Manual;
                        d.Location = new Point(CornerNative.Away + 200, CornerNative.Away + 200);
                        d.ShowInTaskbar = false;
                        var shown = CornerNative.Open(d);
                        shown["type"] = d.GetType().Name;
                        shown["border"] = d.FormBorderStyle.ToString();
                        dialogs[one.Key] = shown;
                        d.Close();
                    }
                    CornerNative.Pump(2);
                }
                said["dialogs"] = dialogs;
            }
        }
    }
}
"""


def _channel(value: int, shift: int) -> int:
    return (value >> shift) & 255


class _Probe:
    answer: dict = {}
    failure: str | None = None
    folder = None
    cases: list = []

    @classmethod
    def run(cls):
        if cls.answer or cls.failure:
            return
        cls.folder = tempfile.TemporaryDirectory(prefix="car-dialog-corner-")
        work = Path(cls.folder.name)
        reply = {"ok": True, "language": "en", "strings": l10n.catalog("en"), "endonyms": dict(l10n.ENDONYMS),
                 "preference": "en", "system_language": "en"}
        (work / "strings-en.json").write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        (work / "snapshot.json").write_text(json.dumps(fullest_snapshot(time.time()), ensure_ascii=False), encoding="utf-8")
        lines = []
        cls.cases = []
        for design in ("soft", "classic", "plain"):
            for scale in LAY_SCALES:
                width, height = (int(round(side * scale)) for side in LAY_LOGICAL)
                radius = float(brand.design_radii(design)["card"])
                for under in UNDER:
                    for body in (GROUND, BODY):
                        cls.cases.append((design, scale, width, height, radius, under, body))
                        lines.append("lay %d %d %r %r %r %s %s %s %s %s" % (
                            width, height, radius, shape.design_smoothing(design), scale, under,
                            *("#%02X%02X%02X" % c for c in (GROUND, LINE, SHADE, body))))
        (work / "lay.txt").write_text("\n".join(lines), encoding="utf-8")
        probe = work / "DialogCornerProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "DialogCorner.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/optimize+", "/out:" + str(exe),
                                "/main:CodexAutoResume.DialogCornerProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        if built.returncode != 0:
            cls.failure = "the probe did not compile: " + built.stdout.decode("mbcs", "replace")[-3000:]
            return
        out = work / "out.json"
        environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
        # Shown as a person's dialog is - cloaked, then faded in - never as a still takes one.
        environment.pop("CODEX_AR_STILL_READY", None)
        done = subprocess.run([str(exe), str(out), str(work), str(work / "lay.txt")], capture_output=True, timeout=600,
                              creationflags=NO_WINDOW, env=environment)
        cls.answer = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
        if done.returncode != 0 or "error" in cls.answer or not cls.answer:
            cls.failure = "the probe failed (exit %d): %s" % (done.returncode, cls.answer.get("error"))


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class ScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _Probe.run()
        cls.answer = _Probe.answer

    def setUp(self):
        if _Probe.failure:
            self.fail(_Probe.failure)

    def wanted(self):
        if not self.answer["wanted"]:
            self.skipTest("this machine gives a window no corner of its own (WindowShape.Wanted)")

    def assert_own_corner(self, state, where):
        with self.subTest(where=where):
            self.assertTrue(state["has"], "the dialog asked for its own corner (ChromeHost.OwnCorner)")
            self.assertEqual(state["corner"], "Squircle")
            self.assertTrue(state["frameless"], "no frame while its corner is its own")
            self.assertTrue(state["hostCloaks"], "the dialog keeps its own cloak")
            self.assertEqual(state["preference"], 1, "DWMWCP_DONOTROUND under the dialog's own corner")
            self.assertEqual(state["dwmFrame"], 0, "a window with a region has no frame from DWM")
            self.assertIn(state["region"], (2, 3), "the region is cut")
            self.assertEqual(state["window"][2:], state["client"], "the window is its own client area")
            self.assertEqual(state["outermost"], [True, True, True, True], "the outermost pixel of each side is its own")
            self.assertEqual(state["cutCorners"], [False, False, False, False], "the four corners are cut")

    def test_every_plain_dialog_has_the_dashboard_s_corner_once_open(self):
        self.wanted()
        for name in ("sizable", "fixed", "still", "classic", "plain"):
            said = self.answer[name]
            self.assert_own_corner(said["shown"], name)
            with self.subTest(name=name):
                self.assertTrue(said["shown"]["companion"] and said["shown"]["companionShown"], "its companion is shown")
                self.assertEqual(said["shown"]["companionAlpha"], 255, "opaque once the dialog is")
                self.assertFalse(said["shown"]["cloaked"])
                self.assertFalse(said["shown"]["layered"], "an ordinary window again once opaque, as before")
                self.assertTrue(said["companionGone"], "gone with the dialog")

    def test_the_corner_is_asked_before_the_dialog_is_made(self):
        self.wanted()
        made = self.answer["fixed"]["made"]
        self.assertTrue(made["has"])
        self.assertTrue(made["frameless"])
        self.assertEqual(made["window"][2:], made["client"], "made at its ClientSize, with no frame round it")

    def test_the_companion_is_held_off_with_the_dialog_and_fades_in_with_it(self):
        self.wanted()
        for name in ("sizable", "fixed", "classic", "plain"):
            said = self.answer[name]
            with self.subTest(name=name):
                self.assertTrue(said["opensWithFade"], "the dialog's own fade is kept")
                self.assertTrue(said["first"]["cloaked"], "held off the screen as it is shown, as before")
                self.assertFalse(said["first"]["companionShown"], "no edge or shadow round a dialog not yet seen")
                self.assertFalse(said["shownWhileCloaked"])
                self.assertFalse(said["shownBeforeSeen"])
                self.assertGreater(said["samples"], 0, "the companion was seen with the dialog")
                self.assertEqual(said["worstGap"], 0, "at the dialog's own alpha at every step")
                steps = said["steps"]
                self.assertLess(steps[0], 128, "it fades in from near clear with the dialog: %r" % (steps,))
                self.assertEqual(steps[-1], 255)
                self.assertEqual(steps, sorted(steps), "never darker and lighter again")

    def test_with_motion_reduced_the_companion_is_opaque_as_soon_as_the_dialog_is_seen(self):
        self.wanted()
        said = self.answer["still"]
        self.assertFalse(said["opensWithFade"])
        self.assertFalse(said["first"]["companionShown"])
        self.assertFalse(said["shownWhileCloaked"])
        self.assertEqual(said["steps"], [255])

    def test_a_sizable_dialog_resizes_from_its_edges_and_a_fixed_one_does_not(self):
        self.wanted()
        sizable, fixed = self.answer["sizable"], self.answer["fixed"]
        self.assertTrue(sizable["sizableLayout"])
        self.assertFalse(fixed["sizableLayout"])
        for side in ("left", "right", "bottom"):
            with self.subTest(side=side):
                self.assertTrue(set(int(c) for c in sizable["edges"][side]) & RESIZE,
                                "the band inside the visible edge resizes it (Chrome.Hit)")
                self.assertFalse(set(int(c) for c in fixed["edges"][side]) & RESIZE)
        self.assertTrue(set(int(c) for c in sizable["edges"]["top"]) & RESIZE)

    def test_minimised_it_has_windows_corner_and_back_its_own(self):
        self.wanted()
        said = self.answer["sizable"]
        minimised, back = said["minimised"], said["back"]
        self.assertEqual(minimised["state"], "Minimized")
        self.assertEqual(minimised["corner"], "Round")
        self.assertEqual(minimised["region"], 0)
        self.assertFalse(minimised["companionShown"])
        self.assertEqual(back["state"], "Normal")
        self.assert_own_corner(back, "back")
        self.assertEqual(back["window"], said["shown"]["window"], "the same rectangle to the pixel")
        self.assertTrue(back["companionShown"])

    def test_the_dashboard_s_real_dialogs_each_have_it(self):
        self.wanted()
        dialogs = self.answer["dialogs"]
        self.assertEqual(sorted(dialogs), ["check", "conversation", "logs", "once", "report", "timeline", "versions"])
        for name, said in sorted(dialogs.items()):
            self.assertEqual(said["type"], "SoftDialog", name)
            self.assert_own_corner(said["shown"], name)
            with self.subTest(name=name):
                self.assertTrue(said["shown"]["companionShown"])
                self.assertFalse(said["shownWhileCloaked"])
                self.assertEqual(said["worstGap"], 0)

    def test_high_contrast_and_a_child_dialog_keep_what_they_had(self):
        self.assertFalse(self.answer["contrastWanted"], "High Contrast: WindowShape.Wanted is false")
        said = self.answer["contrast"]
        frame = said["styleFrame"]
        for step in ("made", "shown"):
            state = said[step]
            with self.subTest(step=step):
                self.assertFalse(state["has"], "no WindowCorner")
                self.assertFalse(state["frameless"])
                self.assertEqual(state["region"], 0, "no region")
                self.assertFalse(state["companion"])
                self.assertEqual(state["window"][2:], [state["client"][0] + frame[0] + frame[2],
                                                       state["client"][1] + frame[1] + frame[3]],
                                 "the client inside the frame Windows gives the style, as before")
        windows11 = sys.getwindowsversion().build >= 22000
        self.assertEqual(said["shown"]["corner"], "Round" if windows11 else "Square")
        self.assertEqual(said["shown"]["preference"], 2 if windows11 else said["shown"]["preference"],
                         "DWMWCP_ROUND: Windows' round corner, as before")
        child = self.answer["child"]
        self.assertFalse(child["has"], "a dialog laid out as a child (the audit, the render mode) has none")
        self.assertFalse(child["frameless"])

    def test_the_corner_is_the_design_s_card_corner(self):
        self.assertEqual(self.answer["radius"], brand.design_radii("soft")["card"])
        self.assertTrue(self.answer["switch"] is brand.WINDOW_SQUIRCLE)


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class LayTests(unittest.TestCase):
    """WindowShape.Lay - what the render mode lays a dialog with - against the ideal corner."""

    @classmethod
    def setUpClass(cls):
        _Probe.run()
        cls.answer = _Probe.answer

    def setUp(self):
        if _Probe.failure:
            self.fail(_Probe.failure)

    def each(self):
        for case, said in zip(_Probe.cases, self.answer["lay"]):
            design, scale, width, height, radius, under, body = case
            pixels = struct.unpack("<%di" % (int(said["across"]) * int(said["down"])), base64.b64decode(said["pixels"]))
            yield case, said, pixels

    @staticmethod
    def under(name, x, y):
        if name == "grey":
            return (128, 128, 128)
        return (255, 255, 255) if ((x // 8) + (y // 8)) % 2 == 0 else (0, 0, 0)

    @staticmethod
    def rgb(value):
        return (_channel(value, 16), _channel(value, 8), _channel(value, 0))

    def ideal_of(self, case, said):
        design, scale, width, height, radius, _under, _body = case
        return _Ideal(width, height, radius * scale, shape.design_smoothing(design), int(said["hair"]),
                      int(said["reach"]), int(said["drop"]))

    def test_every_pixel_is_the_ideal_corner_over_what_is_under_it(self):
        for case, said, pixels in self.each():
            design, scale, width, height, radius, under, body = case
            if body != GROUND:
                continue
            ideal = self.ideal_of(case, said)
            across, ox, oy = int(said["across"]), int(said["x"]), int(said["y"])
            worst = 0
            # The four corners, and a stretch of each straight edge, with the shadow round them.
            m = int(said["margin"])
            spots = set()
            reach = ideal.corner + m
            for y in range(-m, height + m):
                for x in range(-m, width + m):
                    near_x = x < reach - m or x >= width - (reach - m)
                    near_y = y < reach - m or y >= height - (reach - m)
                    if (near_x and near_y) or (near_x and abs(y - height // 2) < 2) or (near_y and abs(x - width // 2) < 2):
                        spots.add((x, y))
            for x, y in spots:
                outer, inner = ideal.covers(x, y)
                shadow = 0.0 if outer >= 1.0 else ideal.shadow(x, y) * (1.0 - outer)
                alpha = outer + shadow
                a = max(0, min(255, round(alpha * 255)))
                edge = outer - inner
                px, py = ox + x, oy + y
                below = GROUND if outer >= 1.0 else self.under(under, px, py)
                want = []
                for channel in range(3):
                    premultiplied = min(a, round(GROUND[channel] * inner + LINE[channel] * edge + SHADE[channel] * shadow))
                    want.append(min(255, premultiplied + (below[channel] * (255 - a) + 127) // 255))
                got = self.rgb(pixels[py * across + px])
                worst = max(worst, max(abs(g - w) for g, w in zip(got, want)))
            with self.subTest(design=design, scale=scale, under=under):
                self.assertLessEqual(worst, 2, "every channel within 2 levels of the ideal")

    def test_the_hairline_runs_round_it_and_nothing_of_it_lies_outside_its_shadow(self):
        for case, said, pixels in self.each():
            design, scale, width, height, radius, under, body = case
            across, down, ox, oy = int(said["across"]), int(said["down"]), int(said["x"]), int(said["y"])
            hair, m = int(said["hair"]), int(said["margin"])
            with self.subTest(design=design, scale=scale, under=under, body=body):
                for x, y in ((width // 2, 0), (0, height // 2), (width - 1, height // 2), (width // 2, height - 1)):
                    self.assertEqual(self.rgb(pixels[(oy + y) * across + ox + x]), LINE, "the hairline at (%d, %d)" % (x, y))
                inside = self.rgb(pixels[(oy + hair) * across + ox + width // 2])
                self.assertEqual(inside, body, "the dialog's own pixel just inside the hairline")
                for py in range(down):
                    for px in range(across):
                        x, y = px - ox, py - oy
                        if -m <= x < width + m and -m <= y < height + m:
                            continue
                        self.assertEqual(self.rgb(pixels[py * across + px]), self.under(under, px, py),
                                         "untouched beyond its shadow at (%d, %d)" % (px, py))

    def test_the_dialog_s_own_pixels_lie_only_inside_its_outline(self):
        laid = {}
        for case, said, pixels in self.each():
            design, scale, width, height, radius, under, body = case
            laid[(design, scale, under, body)] = (case, said, pixels)
        for (design, scale, under, body), (case, said, pixels) in laid.items():
            if body != BODY:
                continue
            _c, _s, grounded = laid[(design, scale, under, GROUND)]
            width, height = case[2], case[3]
            ideal = self.ideal_of(case, said)
            across, ox, oy = int(said["across"]), int(said["x"]), int(said["y"])
            leaks, holes = [], []
            for y in range(height):
                for x in range(width):
                    at = (oy + y) * across + ox + x
                    differs = pixels[at] != grounded[at]
                    outer, inner = ideal.covers(x, y)
                    if differs and (inner < 0.99 or self.rgb(pixels[at]) != BODY):
                        leaks.append((x, y))
                    if not differs and inner >= 1.0 and outer >= 1.0:
                        holes.append((x, y))
            with self.subTest(design=design, scale=scale, under=under):
                self.assertEqual(leaks, [], "the dialog's own pixels only where the outline a hairline in covers them")
                self.assertLessEqual(len(holes), 4, "and everywhere it covers them whole: %r" % (holes[:8],))
            # The cut corner: the box's corner pixel is not the dialog's.
            self.assertNotEqual(self.rgb(pixels[oy * across + ox]), BODY)


class SourceTests(unittest.TestCase):
    def test_every_titled_dialog_asks_for_the_corner_as_its_title_row_is_made(self):
        build = guiscan.member_body("SoftDialog", "BuildTitle")
        install = build.index("chrome = ChromeHost.Install(this, titleRow, titleGround);")
        asked = build.index("chrome.OwnCorner();")
        self.assertLess(install, asked)
        self.assertIn("if (chrome.Corner != null) chrome.Corner.HostCloaks = true;", build)
        self.assertLess(asked, build.index("ClientSize = new Size(ClientSize.Width, ClientSize.Height + grown);"),
                        "asked before the dialog grows by its strip, so its ClientSize is its window")
        own = guiscan.member_body("SoftDialog", "OwnFrame")
        self.assertIn("if (chrome != null && chrome.Frameless) return Padding.Empty;", own)
        self.assertIn("Chrome.Uncaption(created, ClientSize, chrome != null && chrome.Frameless);",
                      guiscan.type_body("SoftDialog"), "made at its ClientSize with no frame while its corner is its own")
        procedure = guiscan.member_body("SoftDialog", "WndProc")
        statements = [line.strip() for line in procedure.splitlines()[1:]
                      if line.strip() and not line.strip().startswith(("//", "{", "}"))]
        self.assertEqual(statements[0], "if (chrome != null && chrome.Intercept(ref m, PassOn)) return;",
                         "every message to the caption, and so to the corner, first")
        # The shared corner alone: no copy of its code in the dialog.
        body = guiscan.type_body("SoftDialog")
        code = " ".join(line.split("//")[0] for line in body.splitlines())
        for name in ("SetWindowRgn", "UpdateLayeredWindow", "WindowShape."):
            self.assertNotIn(name, code, name)

    def test_every_dialog_the_dashboard_builds_is_a_titled_soft_dialog(self):
        sites = 0
        for path in sorted((ROOT / "gui").glob("*.cs")):
            text = path.read_text(encoding="utf-8")
            for found in re.finditer(r"var (\w+) = new SoftDialog\(\)", text):
                sites += 1
                after = text[found.end():found.end() + 600]
                self.assertIn("Soft.DialogBar(%s);" % found.group(1), after, "%s: a dialog with no title row" % path.name)
            self.assertNotRegex(text, r"new Form\(\)", path.name + " builds a Form that is no SoftDialog")
        self.assertGreaterEqual(sites, 10)

    def test_the_dialog_s_fade_and_cloak_take_its_corner_with_them(self):
        fade = guiscan.member_body("SoftDialog", "SetFade")
        self.assertIn("own.Opacity(fadeAlpha);", fade)
        created = guiscan.member_body("SoftDialog", "OnHandleCreated")
        self.assertIn("if (OwnCorner != null) OwnCorner.Held = cloaked;", created)
        uncloak = guiscan.member_body("SoftDialog", "Uncloak")
        self.assertLess(uncloak.index("DwmSetCloak(Handle, DWMWA_CLOAK, ref off, 4)"),
                        uncloak.index("if (OwnCorner != null) OwnCorner.Held = false;"))
        self.assertLess(uncloak.index("if (OwnCorner != null) OwnCorner.Held = false;"), uncloak.index("OpenFade();"))
        cloak = guiscan.member_body("WindowCorner", "Cloak")
        self.assertIn("HostCloaks) return;", cloak)
        show = guiscan.member_body("WindowCorner", "MayShow")
        self.assertIn("|| held ||", show)

    def test_a_picture_lays_the_dialog_with_its_corner(self):
        paint = guiscan.member_body("SettingsForm", "PaintDialog")
        self.assertLess(paint.index("if (DialogSquircle())"), paint.index("g.FillRectangle"))
        self.assertIn("LayDialog(picture, body, place, ground);", paint)
        decide = guiscan.member_body("SettingsForm", "DialogSquircle")
        self.assertIn("return WindowShape.Switch && !Palette.Contrast;", decide)
        lay = guiscan.member_body("SettingsForm", "LayDialog")
        self.assertIn("new WindowShape.Edge(body.Width, body.Height, Palette.RadiusCard,", lay)
        self.assertIn("WindowShape.Lay(", lay)
        self.assertIn("WindowCorner.Shade()", lay)
        render = guiscan.member_body("SettingsForm", "RenderDialog")
        self.assertIn("int border = DialogSquircle() ? 0 : Math.Max(1, Px(1));", render)


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "the window is built with Windows' C# compiler")
class RenderTests(unittest.TestCase):
    """The window's render mode draws the Timeline over Pending as the README motion does."""

    @classmethod
    def setUpClass(cls):
        import make_screenshots
        import motion_window
        cls.folder = tempfile.TemporaryDirectory(prefix="car-dialog-corner-render-")
        work = Path(cls.folder.name)
        exe = motion_window.compile_window(work)
        still = {"window": {"still": "assets/screenshot-dashboard.png"}}
        width, height, _rgb, _alpha = make_screenshots.read_png(ROOT / still["window"]["still"])
        job = {"out": str(work / "out"), "theme": "light", "design": "soft", "scale": make_screenshots.PINNED_SCALE,
               **motion_window.frame_edge(),
               "forms": {"en": {"answers": motion_window.answers("en")}},
               "targets": ["dialog.close", "dialog.window"], "outer": [width, height], "chrome": motion_window.chrome(still),
               "frames": [{"index": 0, "locale": "en", "page": "pending", "light": 0},
                          {"index": 1, "locale": "en", "page": "pending", "light": 0, "dialog": {"kind": "timeline"}}]}
        cls.result = motion_window.render(exe, job, work)
        cls.pictures = list(motion_window.pictures(cls.result, work / "out"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def pixel(self, index, x, y):
        width = self.result["client"][0]
        picture = self.pictures[index][1]
        return tuple(picture[(y * width + x) * 3:(y * width + x) * 3 + 3])

    def test_the_timeline_s_corners_are_cut_with_the_hairline_round_it(self):
        if not brand.WINDOW_SQUIRCLE:
            self.skipTest("the switch is off: the dialog is the rectangle it was")
        self.assertEqual(self.result["notes"], [])
        x, y, wide, tall = self.pictures[1][2]["dialog.window"]
        scale = float(self.result["dpi_scale"])
        ideal = _Ideal(wide, tall, brand.design_radii("soft")["card"] * scale, shape.design_smoothing("soft"),
                       max(1, int(scale + 1e-6)), max(1, round(14 * scale)), round(6 * scale))
        ground = self.pixel(1, x + wide // 2, y + 4)
        self.assertEqual(ground, self.pixel(0, 8, 150), "the dialog's ground is the window's canvas")
        line = self.pixel(1, x + wide // 2, y)
        self.assertNotEqual(line, ground)
        for at in ((x, y + tall // 2), (x + wide - 1, y + tall // 2), (x + wide // 2, y + tall - 1)):
            self.assertEqual(self.pixel(1, *at), line, "the hairline round it at %r" % (at,))
        outside = inside = 0
        tile = int(ideal.corner + 1)
        for cy in range(tile):
            for cx in range(tile):
                for px, py, ix, iy in ((x + cx, y + cy, cx, cy), (x + wide - 1 - cx, y + cy, wide - 1 - cx, cy),
                                       (x + cx, y + tall - 1 - cy, cx, tall - 1 - cy),
                                       (x + wide - 1 - cx, y + tall - 1 - cy, wide - 1 - cx, tall - 1 - cy)):
                    outer, inner = ideal.covers(ix, iy)
                    drawn = self.pixel(1, px, py)
                    if outer == 0.0:
                        outside += 1
                        self.assertNotEqual(drawn, ground, "nothing of the dialog outside its outline at %r" % ((cx, cy),))
                        under = self.pixel(0, px, py)
                        self.assertTrue(all(d <= u for d, u in zip(drawn, under)),
                                        "only the veil and the shadow over the window there: %r over %r" % (drawn, under))
                    elif inner == 1.0 and iy < tall // 2 and (cy < round(8 * scale) or cx < round(16 * scale)):
                        # The top corners round the title row (8 px below the top, 16 px in from the sides): the
                        # dialog's own ground and nothing on it there.
                        inside += 1
                        self.assertEqual(drawn, ground, "the dialog's ground inside its outline at %r" % ((cx, cy),))
        self.assertGreater(outside, 40, "the corner is cut, not a rectangle's")
        self.assertGreater(inside, 40)


if __name__ == "__main__":
    unittest.main()
