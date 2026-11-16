r"""v0.6.24-beta.2 (the owner, 2026-11-16): the status light's sweep - the easter egg's - as the Dashboard opens and as the
light turns on, and the line under the headline gliding in as the sweep ends.

- The sweep (HaloDot.Sweep) and the line's arrival (AsideLabel.Arrive: its own words, faded in as they come back after
  the egg's sentence, AsideLabel.OutMs, AsideAfterMs after the sweep begins) - never the egg's sentence, which stays the
  egg's own (VersionPressed).
- Once as the window opens, at the first read that gives the light its colour - and not in a window that reopens itself
  (a change of language, theme or scale: `--reopened`, OpenRequest.Generation), which is the same open going on. Held for
  the moment the window is on screen when the first read comes before it is (Shown).
- As the light turns on: from off (idle - the watcher not running or not known to - or paused) to watching (monitoring,
  waiting, checking, recovering), as the watcher's state reads it - not a light an action in flight turns to checking
  (BusyLight), not between two watching states, never as it turns off.
- Never over itself: a second while one is on its way does nothing. Nothing with motion reduced, in High Contrast or out
  of sight (Motion.Allowed, as the sweep and the fade ask), and nothing in a render job, a capture or the layout audit:
  every picture stays what it was (Soft.StillLightMs, StillReady, StillNow, RenderPinned).

A probe compiled with the window builds it never shown (TopLevel = false) and feeds the header what reads give it (Hero).
GUI test module (it makes windows, never shown): run on its own, through gui_lock.sh.
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
from codex_auto_resume import l10n  # noqa: E402

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
    internal static class LightSweepProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.SweepRun(argv[1], said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        private static Dictionary<string, object> SweepStatus(bool running, bool enabled)
        {
            return new Dictionary<string, object> { { "watcher_running", running }, { "enabled", enabled }, { "pending", 0.0 },
                                                    { "version", "0.6.24-beta.2" }, { "edition", "standard" } };
        }

        private static SettingsForm SweepWindow(string dir, int generation)
        {
            var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-en.json"), Encoding.UTF8)) as Dictionary<string, object>;
            string nowhere = Path.Combine(dir, "nowhere");
            var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, null);
            form.TopLevel = false;
            form.request.Generation = generation;
            return form;
        }

        // Each read in turn, as Hero is given it; what the light's sweep was asked for after each.
        private static List<object> SweepReads(SettingsForm form, params Dictionary<string, object>[] reads)
        {
            var asked = new List<object>();
            foreach (Dictionary<string, object> status in reads)
            {
                form.Hero(status, null, 0);
                asked.Add(string.Join(",", form.LightSweepsAsked.ToArray()));
            }
            return asked;
        }

        internal static void SweepRun(string dir, Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
            Palette.Adopt("light");
            var watching = SweepStatus(true, true);
            var paused = SweepStatus(true, false);
            var stopped = SweepStatus(false, true);
            var waiting = SweepStatus(true, true);
            waiting["pending"] = 2.0;
            var attention = SweepStatus(true, true);
            attention["upgrade_pending"] = true;
            using (var form = SweepWindow(dir, 0))
            {
                said["opened"] = SweepReads(form, watching, watching, waiting, watching, attention, watching, paused, paused, watching,
                                            stopped, watching);
                // Never shown: the opening sweep waits for the window to be (SweepLight), and none plays out of sight.
                said["onShown"] = form.sweepOnShown;
                said["sweeping"] = form.stateDot.Sweeping;
                // As if on screen: asked, and not played - the light and the line may not move here (Motion.Allowed).
                form.shown = true;
                form.Hero(stopped, null, 0);
                form.Hero(watching, null, 0);
                said["shownAsked"] = string.Join(",", form.LightSweepsAsked.ToArray());
                said["shownSweeping"] = form.stateDot.Sweeping;
                said["shownArriving"] = form.detail.Arriving;
                form.detail.Arrive(AsideAfterMs);
                said["arriveOutOfSight"] = form.detail.Arriving;
                // An action in flight lights "checking" over a paused light: not the light turning on.
                form.Hero(paused, null, 0);
                int before = form.LightSweepsAsked.Count;
                form.busy++;
                form.Hero(paused, null, 0);
                said["busyLight"] = form.stateDot.State;
                said["busyAsked"] = (double)(form.LightSweepsAsked.Count - before);
                form.busy--;
            }
            using (var form = SweepWindow(dir, 1))
                said["reopened"] = SweepReads(form, watching, stopped, watching);
            // A picture: the light held still (WindowRender sets StillLightMs), no sweep at all.
            double still = Soft.StillLightMs;
            Soft.StillLightMs = 0;
            try
            {
                using (var form = SweepWindow(dir, 0))
                    said["render"] = SweepReads(form, watching, stopped, watching);
            }
            finally { Soft.StillLightMs = still; }
            // The layout audit's window likewise.
            using (var form = SweepWindow(dir, 0))
            {
                form.auditing = true;
                said["audit"] = SweepReads(form, watching, stopped, watching);
            }
            var pairs = new List<object>();
            foreach (string from in new[] { "idle", "paused", "attention", "monitoring", "waiting", "checking", "recovering" })
                foreach (string to in new[] { "idle", "paused", "attention", "monitoring", "waiting", "checking", "recovering" })
                    if (LightTurnsOn(from, to)) pairs.Add(from + ">" + to);
            said["turnsOn"] = pairs;
        }
    }
}
"""


@unittest.skipUnless(CSC.is_file(), "needs the in-box C# compiler")
class LightSweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        work = Path(cls.folder.name)
        reply = {"ok": True, "language": "en", "strings": l10n.catalog("en"), "endonyms": dict(l10n.ENDONYMS),
                 "preference": "en", "system_language": "en"}
        (work / "strings-en.json").write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        probe = work / "LightSweepProbe.cs"
        probe.write_text(PROBE, encoding="utf-8")
        exe = work / "LightSweep.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.LightSweepProbe",
                                "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        cls.failure = None if built.returncode == 0 else built.stdout.decode("mbcs", "replace")[-3000:]
        cls.answer = {}
        if cls.failure is None:
            out = work / "out.json"
            environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
            for name in ("CODEX_AR_STILL_LIGHT", "CODEX_AR_STILL_READY", "CODEX_AR_STILL_NOW", "CODEX_AR_STILL_CLOCK"):
                environment.pop(name, None)
            done = subprocess.run([str(exe), str(out), str(work)], capture_output=True, timeout=300,
                                  creationflags=NO_WINDOW, env=environment)
            cls.answer = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
            if done.returncode != 0 or "error" in cls.answer or not cls.answer:
                cls.failure = "the probe failed (exit %d): %s" % (done.returncode, cls.answer.get("error"))

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        if self.failure:
            self.fail(self.failure)

    def test_once_as_the_window_opens_then_only_as_the_light_turns_on(self):
        # Reads: watching, watching, waiting, watching, attention, watching, paused, paused, watching, stopped, watching.
        self.assertEqual(self.answer["opened"], [
            "open", "open", "open", "open", "open", "open", "open", "open", "open,on", "open,on", "open,on,on"])

    def test_not_in_a_window_that_reopened_itself(self):
        self.assertEqual(self.answer["reopened"], ["", "", "on"], "the reopen is the same open going on; a turn-on still sweeps")

    def test_off_to_watching_only(self):
        self.assertEqual(sorted(self.answer["turnsOn"]), sorted(
            "%s>%s" % (a, b) for a in ("idle", "paused") for b in ("monitoring", "waiting", "checking", "recovering")))

    def test_an_action_in_flight_is_not_the_light_turning_on(self):
        self.assertEqual(self.answer["busyLight"], "checking")
        self.assertEqual(self.answer["busyAsked"], 0)

    def test_nothing_moves_where_motion_is_not_allowed(self):
        self.assertTrue(self.answer["onShown"], "a window not yet on screen sweeps as it is shown")
        self.assertFalse(self.answer["sweeping"])
        self.assertEqual(self.answer["shownAsked"], "open,on,on,on")
        self.assertFalse(self.answer["shownSweeping"], "out of sight (Motion.Allowed): no sweep")
        self.assertFalse(self.answer["shownArriving"], "and the line is simply there")
        self.assertFalse(self.answer["arriveOutOfSight"])

    def test_no_sweep_in_a_picture_or_the_layout_audit(self):
        self.assertEqual(self.answer["render"], ["", "", ""])
        self.assertEqual(self.answer["audit"], ["", "", ""])


class LightSweepSourceTests(unittest.TestCase):
    def test_the_sweep_and_the_line_are_the_egg_s_without_its_sentence(self):
        sweep = guiscan.member_body("SettingsForm", "SweepLight")
        self.assertIn("stateDot.Sweep();", sweep)
        self.assertIn("detail.Arrive(AsideAfterMs);", sweep)
        self.assertNotIn(".Aside(", sweep, "never the egg's sentence")
        self.assertIn("stateDot.Sweeping) return;", sweep, "never over itself")
        egg = guiscan.member_body("SettingsForm", "VersionPressed")
        self.assertIn("stateDot.Sweep();", egg)
        self.assertIn('detail.Aside(S("status.aside"', egg)
        self.assertIn("Glide(OutMs);", guiscan.member_body("AsideLabel", "Arrived"),
                      "the line comes in as it comes back after the egg's sentence")
        self.assertIn("!Motion.Allowed(this)", guiscan.member_body("AsideLabel", "Arrive"))
        self.assertIn("if (!Motion.Allowed(this)) return;", guiscan.member_body("HaloDot", "Sweep"))


if __name__ == "__main__":
    unittest.main()
