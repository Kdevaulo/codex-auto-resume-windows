r"""A list's pinned header stays pinned through a garbage collection (v0.6.24-beta.2).

The beta.2 pictures' motion fidelity failed on History alone, and not every time: the offscreen render's list header was
2 px shorter than the still's, every row under it 2 px higher. SoftList.PinnedHeader - the NativeWindow that gives a
list's header the height a monitor of the pinned scale gives it - was made and attached and then referred to by nothing,
so a garbage collection took it and let the header go, and the header's next layout was Windows' own again: taller on a
monitor whose DPI is not the pinned scale's. Whether a collection came before or after a page's header was laid out
decided the picture. The list holds it now.

A probe compiled with the window makes a list as a render does (pinned at 150 %), reads where its first row starts,
collects the garbage, lays the list out again and reads it again; and a list of the same words unpinned, to show the
pin changes something on this machine. GUI test module (it makes windows, never shown): run on its own, through
gui_lock.sh.
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
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class PinnedHeaderProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.PinnedHeaderRun(said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        private static int FirstRow(bool pinned, bool collect)
        {
            RenderPinned = pinned;
            var host = new Form();
            host.TopLevel = false;
            host.FormBorderStyle = FormBorderStyle.None;
            host.ClientSize = new Size(900, 600);
            var list = new SoftList();
            list.View = View.Details;
            list.Font = Soft.BaseFont;
            list.Columns.Add("Conversation", 200);
            list.Columns.Add("Outcome", 200);
            list.Items.Add(new ListViewItem(new[] { "example-service", "recovered" }));
            list.Bounds = new Rectangle(10, 10, 800, 400);
            host.Controls.Add(list);
            host.CreateControl();
            IntPtr made = host.Handle;
            host.Visible = true;
            Application.DoEvents();
            if (collect)
            {
                GC.Collect();
                GC.WaitForPendingFinalizers();
                GC.Collect();
                // Laid out again, as a page's list is when its card is sized or its rows come.
                list.Size = new Size(list.Width + 3, list.Height + 3);
                Application.DoEvents();
            }
            int top = list.GetItemRect(0).Top;
            host.Dispose();
            return top;
        }

        internal static void PinnedHeaderRun(Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
            Palette.Adopt("light");
            AdoptDisplayScale(1.5);
            ScaleDefaultFont();
            AdoptTextSize(1.0, 1.0);
            said["pinned"] = (double)FirstRow(true, false);
            said["pinnedAfterCollection"] = (double)FirstRow(true, true);
            said["windows"] = (double)FirstRow(false, false);
            RenderPinned = false;
        }
    }
}
"""


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class PinnedHeaderHeldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        probe = work / "PinnedHeaderProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "PinnedHeaderProbe.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.PinnedHeaderProbe",
                                "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=300, creationflags=NO_WINDOW)
        cls.failure = None
        cls.answer = {}
        if built.returncode != 0:
            cls.failure = "the probe did not compile: " + built.stdout.decode("utf-8", "replace")[-3000:]
            return
        out = work / "out.json"
        done = subprocess.run([str(exe), str(out)], capture_output=True, timeout=300, creationflags=NO_WINDOW)
        cls.answer = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
        if done.returncode != 0 or "error" in cls.answer or not cls.answer:
            cls.failure = "the probe failed (exit %d): %s" % (done.returncode, cls.answer.get("error"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_a_collection_leaves_the_header_pinned(self):
        self.assertEqual(self.answer["pinnedAfterCollection"], self.answer["pinned"],
                         "the first row moved after a garbage collection: the pinned header was let go")

    def test_the_list_holds_what_pins_its_header(self):
        self.assertIn("pinnedHeader = PinnedHeader.Attach(this);", guiscan.member_body("SoftList", "OnHandleCreated"))
        self.assertIn("private PinnedHeader pinnedHeader;", guiscan.type_body("SoftList"))

    def test_the_pin_changes_the_header_where_the_screen_is_not_at_the_pinned_scale(self):
        # Where this machine's DPI is the pinned scale's (144), the pin is the header Windows makes and nothing differs.
        if self.answer["pinned"] == self.answer["windows"]:
            self.skipTest("this machine's header at the pinned scale is Windows' own")
        self.assertNotEqual(self.answer["pinned"], self.answer["windows"])


if __name__ == "__main__":
    unittest.main()
