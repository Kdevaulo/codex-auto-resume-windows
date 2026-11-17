"""The window compiled with a probe of its own, never shown, on a date the probe gives (DayArt.On, DayArt.Clock): what the
special days' eggs on the version's pill do (test_gui_day_one_press, test_gui_day_six_presses, test_gui_pill_hint).

`run(body, answer_keys)` compiles gui/*.cs with a partial SettingsForm whose static DayEggRun(dir, said) is `body` - C# that
has `form`, `locale`, `Press()` and `Words()` - for each of LOCALES and each date of DATES, and returns the JSON it wrote.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

import guiscan
from codex_auto_resume import l10n

ROOT = Path(__file__).resolve().parents[1]
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LOCALES = ("en", "ko", "ar")
# A date of each special day, and an ordinary one.
DATES = {"new_year": (2027, 1, 1), "seollal": (2027, 2, 7), "birthday": (2026, 9, 6), "chuseok": (2027, 9, 15),
         "christmas": (2026, 12, 25), "ordinary": (2027, 3, 3)}

HEAD = r"""
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal static class DayEggProbe
    {
        [STAThread]
        internal static int Main(string[] argv)
        {
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.ThrowException);
            var said = new Dictionary<string, object>();
            int code = 0;
            try { SettingsForm.DayEggRun(argv[1], said); }
            catch (Exception e) { said["error"] = e.ToString(); code = 3; }
            File.WriteAllText(argv[0], Json.Write(said), new UTF8Encoding(false));
            return code;
        }
    }

    internal sealed partial class SettingsForm
    {
        private static readonly MethodInfo DayEggDown = typeof(Control).GetMethod("OnMouseDown", BindingFlags.Instance | BindingFlags.NonPublic);

        /// The line under the headline: the sentence it says or will say (its words), and whether it is on its way or said.
        private string DayEggWords()
        {
            return (string)typeof(AsideLabel).GetField("words", BindingFlags.Instance | BindingFlags.NonPublic).GetValue(detail) ?? "";
        }

        private void DayEggPress()
        {
            DayEggDown.Invoke(versionPill, new object[] { new MouseEventArgs(MouseButtons.Left, 1, 4, 4, 0) });
        }

        internal static void DayEggRun(string dir, Dictionary<string, object> said)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(null);
            Palette.Adopt("light");
            AdoptDisplayScale(1.0);
            var dates = Json.Parse(File.ReadAllText(Path.Combine(dir, "dates.json"), Encoding.UTF8)) as Dictionary<string, object>;
            foreach (string locale in new[] { "en", "ko", "ar" })
            {
                var strings = Json.Parse(File.ReadAllText(Path.Combine(dir, "strings-" + locale + ".json"), Encoding.UTF8)) as Dictionary<string, object>;
                dpiScale = 1.0;
                float factor = (float)(1.0 / SystemScale);
                Font box = SystemFonts.MessageBoxFont;
                var windowFont = new Font(box.FontFamily, box.SizeInPoints * factor, box.Style, GraphicsUnit.Point);
                Mirror.Window = Mirror.Language(locale);
                string nowhere = Path.Combine(dir, "nowhere-" + locale);
                var answer = new Dictionary<string, object>();
                using (var form = new SettingsForm(new PersistentBridge(nowhere, new Bridge(nowhere)), strings, windowFont))
                {
                    form.TopLevel = false;
                    form.MinimumSize = Size.Empty;
                    form.ClientSize = form.OpeningClient;
                    form.ShowPage("overview");
                    Materialise(form);
                    form.PerformLayout();
                    form.ShowVersion(form.versionText, new Dictionary<string, object> { { "version", "0.6.24" }, { "edition", "standard" } });
                    // Not the layout audit: a window a person opened, whose presses may play the special eggs.
                    form.auditing = false;
                    double clock = 0.0;
                    form.PressNow = delegate { return clock; };
                    form.ReadRecoveredAllTime = delegate(Action<int> then) { then(3); };
                    Func<string, string> S = delegate(string key) { return form.S(key, ""); };
                    Action Press = delegate { form.DayEggPress(); };
                    Func<string> Words = delegate { return form.DayEggWords(); };
                    Action<double> Wait = delegate(double ms) { clock = Math.Max(clock, form.SpecialUntil) + ms; };
                    foreach (KeyValuePair<string, object> pair in dates)
                    {
                        var date = (List<object>)pair.Value;
                        DateTime day = new DateTime((int)(double)date[0], (int)(double)date[1], (int)(double)date[2], 12, 0, 0);
                        DayArt.On = true;
                        DayArt.Clock = delegate { return day; };
                        var at = new Dictionary<string, object>();
/*BODY*/
                        answer[pair.Key] = at;
                    }
                    DayArt.On = false;
                }
                said[locale] = answer;
            }
        }
    }
}
"""


def run(body: str) -> dict:
    """The probe with `body` run for every locale and date: {locale: {date's name: what it set in `at`}}."""
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        for locale in LOCALES:
            reply = {"ok": True, "language": locale, "strings": l10n.catalog(locale), "endonyms": dict(l10n.ENDONYMS),
                     "preference": locale, "system_language": locale}
            (work / ("strings-%s.json" % locale)).write_text(json.dumps(reply, ensure_ascii=False), encoding="utf-8")
        (work / "dates.json").write_text(json.dumps({key: list(value) for key, value in DATES.items()}), encoding="utf-8")
        probe = work / "DayEggProbe.cs"
        probe.write_text(HEAD.replace("/*BODY*/", body), encoding="utf-8")
        exe = work / "DayEggProbe.exe"
        built = subprocess.run([str(CSC), "/nologo", "/target:winexe", "/platform:x64", "/out:" + str(exe),
                                "/main:CodexAutoResume.DayEggProbe", "/win32manifest:" + str(ROOT / "gui" / "app.manifest"),
                                "/reference:System.dll", "/reference:System.Drawing.dll", "/reference:System.Windows.Forms.dll",
                                *[str(path) for path in guiscan.sources()], str(probe)],
                               capture_output=True, timeout=600, creationflags=NO_WINDOW)
        if built.returncode != 0:
            raise AssertionError("the probe did not compile: " + built.stdout.decode("mbcs", "replace")[-3000:])
        out = work / "out.json"
        environment = dict(os.environ, CODEX_HOME=str(work / "no-codex"), LOCALAPPDATA=str(work / "no-local"))
        done = subprocess.run([str(exe), str(out), str(work)], capture_output=True, timeout=600, creationflags=NO_WINDOW,
                              env=environment)
        answer = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
        if done.returncode != 0 or "error" in answer or not answer:
            raise AssertionError("the probe failed (exit %d): %s" % (done.returncode, answer.get("error")))
        return answer
