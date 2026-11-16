r"""v0.6.24: a dialog of the window's opens centred on the window that opened it, wherever that window is.

The owner, 2026-11-16: wherever the Dashboard is, its dialogs open at the Dashboard's middle, not the monitor's. Every
dialog is asked for that (StartPosition = CenterParent), and WinForms centres a modal dialog as it is loaded; the owner
saw them at the monitor's middle all the same. SoftDialog now places itself as it is first shown - the last moment
before it is on a screen, whatever moved it before - with its visible box (DWM's frame bounds, Windows' invisible
borders not counted) centred on its owner's visible box, held inside the work area of the monitor the owner is on
(SoftDialog.WorkAreaOf) near an edge. A dialog with no owner is left where WinForms put it (CenterScreen).

A probe compiled with the window shows owners and dialogs 30000 px off the desktop, never activated (SW_SHOWNOACTIVATE),
with a stand-in work area there, nothing captured:

- owners of a sizable window's frame at several places in that work area: the dialog's visible box centred on the
  owner's within a pixel;
- owners partly past the work area's left, top, right and bottom edges: the dialog inside the work area, against that
  edge, and centred on the owner along the other axis;
- a dialog with no owner: not moved from where it was before it was shown.

Each dialog is parked before it is shown where it would stay without SoftDialog's placement, off the desktop, so the
probe never puts a window on a monitor even against code without it. The live look - a dialog over the Dashboard on
each monitor and scale - is the measurement session's.

GUI test module (it shows windows, off the screen): run on its own, through gui_lock.sh.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "src"), str(ROOT / "tests")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import guiscan  # noqa: E402

CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

PROBE = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class OnOwnerNative
    {
        [DllImport("user32.dll")] internal static extern bool GetWindowRect(IntPtr h, out Chrome.RECT r);
        [DllImport("user32.dll")] internal static extern bool ShowWindow(IntPtr h, int command);
        [DllImport("user32.dll")] internal static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int cy, uint flags);
        [DllImport("dwmapi.dll")] internal static extern int DwmGetWindowAttribute(IntPtr h, int attribute, out Chrome.RECT r, int size);
        internal const int Away = -30000;

        internal static List<object> Whole(IntPtr h)
        {
            Chrome.RECT r;
            GetWindowRect(h, out r);
            return new List<object> { (double)r.Left, (double)r.Top, (double)r.Right, (double)r.Bottom };
        }

        // What a person sees of the window: DWM's frame bounds, or its window where DWM has none.
        internal static List<object> Visible(IntPtr h)
        {
            Chrome.RECT r;
            if (DwmGetWindowAttribute(h, 9, out r, Marshal.SizeOf(typeof(Chrome.RECT))) != 0) GetWindowRect(h, out r);
            return new List<object> { (double)r.Left, (double)r.Top, (double)r.Right, (double)r.Bottom };
        }
    }

    internal static class DialogOnOwnerProbe
    {
        static readonly Rectangle Work = new Rectangle(OnOwnerNative.Away, OnOwnerNative.Away, 6000, 4000);

        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try
            {
                Application.EnableVisualStyles();
                Palette.AdoptDesign("soft");
                Palette.Adopt("light");
                said["work"] = new List<object> { (double)Work.Left, (double)Work.Top, (double)Work.Right, (double)Work.Bottom };
                SoftDialog.WorkAreaOf = delegate(IntPtr owner) { return Work; };
                var cases = new Dictionary<string, object>();
                cases["middle"] = Case(new Point(2500, 1700), true);
                cases["nearTopLeft"] = Case(new Point(300, 200), true);
                cases["farBottomRight"] = Case(new Point(4800, 3300), true);
                cases["pastLeft"] = Case(new Point(-700, 1500), true);
                cases["pastTop"] = Case(new Point(2500, -500), true);
                cases["pastRight"] = Case(new Point(5700, 1500), true);
                cases["pastBottom"] = Case(new Point(2500, 3800), true);
                cases["noOwner"] = Case(new Point(2500, 1700), false);
                // An owner wholly off the work area, as test_gui_v066_dialog holds the Dashboard off the desktop.
                cases["ownerOffTheWorkArea"] = Case(new Point(-3000, 1500), true);
                said["cases"] = cases;
            }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }

        // An owner 1000 by 600 at `at` in the work area, and a dialog over it, made and shown as the window's are - but not
        // activated and, before it is shown, parked 40 px inside the work area's top left.
        static Dictionary<string, object> Case(Point at, bool owned)
        {
            var owner = new Form();
            owner.ShowInTaskbar = false;
            owner.StartPosition = FormStartPosition.Manual;
            owner.FormBorderStyle = FormBorderStyle.Sizable;
            owner.Location = new Point(Work.Left + at.X, Work.Top + at.Y);
            owner.Size = new Size(1000, 600);
            IntPtr o = owner.Handle;
            OnOwnerNative.ShowWindow(o, 4);   // SW_SHOWNOACTIVATE
            Application.DoEvents();
            var dialog = new SoftDialog();
            dialog.Text = "A dialog";
            Soft.DialogBar(dialog);
            dialog.FormBorderStyle = FormBorderStyle.FixedDialog;
            dialog.StartPosition = FormStartPosition.CenterParent;
            dialog.MinimizeBox = false;
            dialog.MaximizeBox = false;
            dialog.ShowInTaskbar = false;
            dialog.ClientSize = new Size(420, 180);
            if (owned) dialog.Owner = owner;
            IntPtr d = dialog.Handle;
            OnOwnerNative.SetWindowPos(d, IntPtr.Zero, Work.Left + 40, Work.Top + 40, 0, 0, 0x0001 | 0x0004 | 0x0010);
            List<object> parked = OnOwnerNative.Visible(d);
            OnOwnerNative.ShowWindow(d, 4);   // SW_SHOWNOACTIVATE
            Application.DoEvents();
            var said = new Dictionary<string, object> {
                { "owner", OnOwnerNative.Visible(o) }, { "dialog", OnOwnerNative.Visible(d) }, { "parked", parked },
                { "window", OnOwnerNative.Whole(d) } };
            dialog.Dispose();
            owner.Dispose();
            return said;
        }
    }
}
"""


@unittest.skipUnless(os.name == "nt" and CSC.is_file(), "needs Windows and the in-box C# compiler")
class DialogOnOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory(prefix="car-dialog-on-owner-")
        work = Path(cls.folder.name)
        probe = work / "DialogOnOwnerProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "DialogOnOwner.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.DialogOnOwnerProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
            done = subprocess.run([str(exe), str(out)], capture_output=True, timeout=300, creationflags=NO_WINDOW,
                                  env=environment)
            cls.answer = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
            if done.returncode != 0 or "error" in cls.answer or not cls.answer:
                cls.failure = "the probe failed (exit %d): %s" % (done.returncode, cls.answer.get("error"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    @staticmethod
    def centre(box):
        return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0

    def inside(self, box, work):
        self.assertGreaterEqual(box[0], work[0])
        self.assertGreaterEqual(box[1], work[1])
        self.assertLessEqual(box[2], work[2])
        self.assertLessEqual(box[3], work[3])

    def test_a_dialog_opens_centred_on_its_owner_wherever_the_owner_is(self):
        work = self.answer["work"]
        for name in ("middle", "nearTopLeft", "farBottomRight"):
            said = self.answer["cases"][name]
            with self.subTest(case=name):
                (ox, oy), (dx, dy) = self.centre(said["owner"]), self.centre(said["dialog"])
                self.assertLessEqual(abs(ox - dx), 1.0, "centred across: owner %s, dialog %s" % (said["owner"], said["dialog"]))
                self.assertLessEqual(abs(oy - dy), 1.0, "centred down: owner %s, dialog %s" % (said["owner"], said["dialog"]))
                self.inside(said["dialog"], work)

    def test_an_owner_past_the_work_area_s_edge_keeps_its_dialog_inside_against_that_edge(self):
        work = self.answer["work"]
        for name, side in (("pastLeft", 0), ("pastTop", 1), ("pastRight", 2), ("pastBottom", 3)):
            said = self.answer["cases"][name]
            with self.subTest(case=name):
                self.inside(said["dialog"], work)
                self.assertEqual(said["dialog"][side], work[side], "against the edge the owner reaches past")
                (ox, oy), (dx, dy) = self.centre(said["owner"]), self.centre(said["dialog"])
                along = abs(oy - dy) if side in (0, 2) else abs(ox - dx)
                self.assertLessEqual(along, 1.0, "centred on the owner along the other axis")

    def test_an_owner_off_the_work_area_keeps_what_is_seen_of_its_dialog_inside(self):
        # The visible box inside within a pixel, against the edge; the window may reach past it by Windows' invisible
        # resize border, which nobody sees (CI 43895825113 read the window's left, -7, in test_gui_v066_dialog).
        work, said = self.answer["work"], self.answer["cases"]["ownerOffTheWorkArea"]
        dialog, window = said["dialog"], said["window"]
        self.assertLessEqual(abs(dialog[0] - work[0]), 1.0, "against the left edge: %s" % dialog)
        self.assertGreaterEqual(dialog[1], work[1] - 1)
        self.assertLessEqual(dialog[2], work[2] + 1)
        self.assertLessEqual(dialog[3], work[3] + 1)
        self.assertLessEqual(window[0], dialog[0])
        self.assertGreaterEqual(window[0], dialog[0] - 16, "no more than an invisible border past it")

    def test_a_dialog_with_no_owner_is_left_where_it_was(self):
        said = self.answer["cases"]["noOwner"]
        self.assertEqual(said["dialog"], said["parked"])


if __name__ == "__main__":
    unittest.main()
