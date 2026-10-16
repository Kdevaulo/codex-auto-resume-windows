// The setup programs' window (v0.6.16): what a double-clicked CodexAutoResume-Setup-v<version>.exe shows instead of
// a console. The window itself is the product's (gui/InstallerWindow.cs, gui/InstallerFlow.cs, drawn with the
// window's [controls] in its [generated] palette - gui/window.sources); this file gives it what a setup program
// has and the settings window would have given it: the archive's edition, version and words, this machine's
// installation, the display's scale and Windows' text size, and the run itself (Setup.cs, InstallFrom).
//
// Nothing here writes anything. It reads the archive it carries, whether and which edition is installed where
// install.ps1 would install (InstallerFlow.InstalledAt), and Windows' theme and text size, as the settings window
// reads them. It starts the installer through Setup.cs alone, and once it has finished, if the person left
// "Open the Dashboard" on, the Dashboard of the installation it has just made, by its full path.
//
// C# 5 only: compiled by the in-box csc with Setup.cs (build/make_setup.py).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;
using CodexAutoResume;

namespace CodexAutoResumeSetup
{
    internal delegate int Installing(IList<string> switches, Action<string> heard, Action<double> unpacked);

    internal static class SetupWindow
    {
        internal const string Locales = "payload/app/src/codex_auto_resume/locales/";
        internal const string Manifest = "payload/app/.codex-plugin/plugin.json";
        internal const string Dashboard = "CodexAutoResumeSettings.exe";

        // A stop said before there is a window: Windows' own message box, in English, as Setup.cs says it.
        internal static void Tell(string text)
        {
            MessageBox.Show(text, "Codex Auto Resume", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }

        internal static int Run(byte[] archive, string[] arguments, Installing install)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Palette.AdoptDesign(Brand.DesignDefault);
            Palette.Adopt(Theme.Current(Theme.System));
            double read = TextScale.Read();
            SettingsForm.AdoptTextSize(TextScale.Fitting(read, Screen.PrimaryScreen.WorkingArea.Size, SettingsForm.SystemScale));
            Font font = TextScale.Apply(SystemFonts.MessageBoxFont, read, SettingsForm.TextSize);

            Archive carried = new Archive(archive);
            string home = InstallerFlow.HomeFrom(Environment.GetEnvironmentVariable("CODEX_AUTO_RESUME_PLUGIN_HOME"),
                                                 Environment.GetFolderPath(Environment.SpecialFolder.UserProfile));
            var flow = new InstallerFlow(InstallerFlow.Install, home, carried.Edition, InstallerFlow.InstalledAt(home),
                                         carried.Version);
            // What the command line already says, as the window's first answers.
            flow.StartAtSignIn = !InstallerFlow.Has(arguments, "-SkipStartup");
            flow.ChangeEdition = InstallerFlow.Has(arguments, "-AllowEditionChange");
            string language = InstallerLanguages.FromSystem(InstallerLanguages.Preferred());
            var window = new InstallerWindow(flow, carried.Words(language), carried.Words,
                delegate(InstallerFlow answered, Action<string> heard, Action<double> unpacked)
                {
                    return install(answered.Switches(arguments), heard, unpacked);
                }, arguments, font);
            Application.Run(window);
            if (window.OpenDashboard) OpenDashboard(flow.Home);
            return window.Code == int.MinValue ? Codes.Cancelled : window.Code;
        }

        // The Dashboard of the installation just made: its own program, by its full path, which is a window and
        // has no console.
        private static void OpenDashboard(string home)
        {
            string exe = Path.Combine(home, Dashboard);
            if (!File.Exists(exe)) return;
            try
            {
                var start = new ProcessStartInfo(exe);
                start.UseShellExecute = false;
                start.WorkingDirectory = home;
                Process.Start(start).Dispose();
            }
            catch (Exception) { /* it is installed; the Start menu opens it */ }
        }

        /// What the window reads from the archive it carries: its entries' names, its version and the catalogs.
        internal sealed class Archive
        {
            private readonly byte[] archive;
            private readonly Dictionary<string, InstallerWords> spoken = new Dictionary<string, InstallerWords>();
            internal readonly string Edition;
            internal readonly string Version;

            internal Archive(byte[] archive)
            {
                this.archive = archive;
                var names = new List<string>();
                using (ZipArchive zip = Open())
                    foreach (ZipArchiveEntry entry in zip.Entries) names.Add(entry.FullName);
                Edition = InstallerFlow.EditionOfEntries(names);
                Version = InstallerFlow.VersionOf(Text(Manifest));
            }

            private ZipArchive Open()
            {
                return new ZipArchive(new MemoryStream(archive, false), ZipArchiveMode.Read);
            }

            private string Text(string name)
            {
                try
                {
                    using (ZipArchive zip = Open())
                    {
                        ZipArchiveEntry entry = zip.GetEntry(name);
                        if (entry == null) return null;
                        using (var reader = new StreamReader(entry.Open(), new UTF8Encoding(false)))
                            return reader.ReadToEnd().TrimStart('\uFEFF');
                    }
                }
                catch (Exception)
                {
                    return null;
                }
            }

            /// The words of `language`, from the catalog the archive carries; English's where it has none.
            internal InstallerWords Words(string language)
            {
                InstallerWords words;
                if (spoken.TryGetValue(language, out words)) return words;
                var catalog = InstallerFlow.ParseObject(Text(Locales + language + ".json"));
                words = catalog == null && language != "en" ? Words("en") : new InstallerWords(catalog, language);
                spoken[language] = words;
                return words;
            }
        }
    }
}

namespace CodexAutoResume
{
    /// The setup program's stand-in for the settings window's scale (SettingsForm.DpiScale in gui/SettingsApp.cs),
    /// which the window's controls are drawn at: the display's, measured as the settings window measures it, times
    /// the text size the window is drawn at. The setup program has no settings window, so this is the whole of it.
    internal sealed partial class SettingsForm
    {
        [DllImport("user32.dll")]
        private static extern int GetDpiForSystem();

        internal static readonly double SystemScale = MeasureDpiScale();
        private static double scale = SystemScale;
        internal static double TextSize = 1.0;

        internal static double DpiScale { get { return scale; } }

        internal static void AdoptTextSize(double drawn)
        {
            TextSize = Math.Max(1.0, drawn);
            scale = SystemScale * TextSize;
        }

        /// Stands another scaling in, for the layout audit (InstallerAudit).
        internal static void StandIn(double displayScale, double text)
        {
            TextSize = Math.Max(1.0, text);
            scale = displayScale * TextSize;
        }

        private static double MeasureDpiScale()
        {
            try
            {
                int dpi = GetDpiForSystem();
                if (dpi >= 96) return dpi / 96.0;
            }
            catch (Exception) { /* before Windows 10 1607 */ }
            return 1.0;
        }
    }

    /// The installer window checking its own layout, as the settings window's LayoutAudit does: every page of every
    /// way it is shown, in one language at one scaling and text size, built and never shown. One line for each
    /// thing cut off or out of place; nothing when there is none. tests/test_installer_window.py runs it in every
    /// language at every scaling and text size.
    internal static class InstallerAudit
    {
        internal static string LayoutAudit(string catalogJson, string language, double displayScale, double text)
        {
            var findings = new List<string>();
            Font baseBefore = Soft.BaseFont;
            try
            {
                SettingsForm.StandIn(displayScale, text);
                Font box = TextScale.Apply(SystemFonts.MessageBoxFont, 1.0, text);
                var font = new Font(box.FontFamily, (float)(box.SizeInPoints * displayScale / SettingsForm.SystemScale),
                                    box.Style, GraphicsUnit.Point);
                var words = new InstallerWords(Json.Parse(catalogJson) as Dictionary<string, object>, language);
                string home = @"C:\Users\ExampleUser\.codex-auto-resume";
                var cases = new List<KeyValuePair<string, InstallerFlow>>();
                cases.Add(Case("first", new InstallerFlow(InstallerFlow.Install, home, InstallerFlow.Standard, null, "0.6.16")));
                cases.Add(Case("update", new InstallerFlow(InstallerFlow.Install, home, InstallerFlow.Advanced, InstallerFlow.Advanced, "0.6.16")));
                cases.Add(Case("edition", new InstallerFlow(InstallerFlow.Install, home, InstallerFlow.Standard, InstallerFlow.Advanced, "0.6.16")));
                cases.Add(Case("edition-advanced", new InstallerFlow(InstallerFlow.Install, home, InstallerFlow.Advanced, InstallerFlow.Standard, "0.6.16")));
                cases.Add(Case("dashboard-update", new InstallerFlow(InstallerFlow.Update, home, InstallerFlow.Standard, InstallerFlow.Standard, "0.6.16")));
                cases.Add(Case("uninstall", new InstallerFlow(InstallerFlow.Uninstall, home, InstallerFlow.Standard, InstallerFlow.Standard, "0.6.16")));
                foreach (KeyValuePair<string, InstallerFlow> each in cases)
                {
                    foreach (int ended in Endings())
                    {
                        using (var window = new InstallerWindow(each.Value, words, delegate(string other) { return words; },
                                                                delegate { return 0; }, null, font))
                        {
                            string where = each.Key + "/" + (ended == int.MinValue ? "pages" : "finish " + ended);
                            if (ended == int.MinValue)
                            {
                                foreach (string page in each.Value.Pages())
                                {
                                    window.ShowPage(page);
                                    Check(window, where + "/" + page, findings);
                                }
                                continue;
                            }
                            window.Finished(ended, ended == 0
                                ? "The watcher could not be confirmed running, so nothing is being watched yet.\n" +
                                  "The previous version of the watcher was asked to stop and is still finishing"
                                : "  [x]  Something did not work.");
                            Check(window, where, findings);
                        }
                    }
                }
            }
            catch (Exception error)
            {
                findings.Add("the audit itself failed: " + error);
            }
            finally
            {
                Soft.BaseFont = baseBefore;
            }
            return string.Join("\n", findings);
        }

        // The pages, then a finish of each kind. Added one by one: a constant array would give the program a class
        // with a random name (build/normalize_pe.py).
        private static List<int> Endings()
        {
            var endings = new List<int>();
            endings.Add(int.MinValue);
            endings.Add(0);
            endings.Add(1);
            endings.Add(InstallerFlow.EditionChangeRefused);
            endings.Add(InstallerFlow.StillRunning);
            return endings;
        }

        private static KeyValuePair<string, InstallerFlow> Case(string name, InstallerFlow flow)
        {
            return new KeyValuePair<string, InstallerFlow>(name, flow);
        }

        /// The page on show: every row inside the card and as wide as its words need at most, every button inside
        /// the window and clear of the others, the header's two lines whole, and every control a person can act on
        /// with a name a screen reader says.
        private static void Check(InstallerWindow window, string where, List<string> findings)
        {
            window.PerformLayout();
            Control body = window.Body;
            int width = body.Parent.Width - body.Parent.Padding.Horizontal;
            int height = body.Parent.Height - body.Parent.Padding.Vertical;
            int used = window.Arrange(width);
            if (used > height) findings.Add(where + " :: the page needs " + used + " px and its card holds " + height);
            foreach (Control control in window.ShownRows())
            {
                string name = control.GetType().Name + "'" + Short(control.Text) + "'";
                if (control.Right > width) findings.Add(where + " :: " + name + " reaches past the card by " + (control.Right - width) + " px");
                Size wanted = control.GetPreferredSize(new Size(control.Width, 0));
                if ((control is WrapLabel || control is SoftCheck || control is SoftCallout) && wanted.Width > control.Width)
                    findings.Add(where + " :: " + name + " needs " + wanted.Width + " px and has " + control.Width);
                if ((control is WrapLabel || control is SoftCheck || control is SoftCallout) && wanted.Height > control.Height)
                    findings.Add(where + " :: " + name + " needs " + wanted.Height + " px high and has " + control.Height);
                if (control is LinkLabel)
                {
                    Size line = TextRenderer.MeasureText(control.Text, control.Font, new Size(int.MaxValue, 0), TextFormatFlags.NoPrefix);
                    if (line.Width > control.Width && line.Height >= control.Height)
                        findings.Add(where + " :: " + name + " needs " + line.Width + " px and has " + control.Width);
                }
                if (control is SoftCombo && control.Height != SoftCombo.FieldHeight)
                    findings.Add(where + " :: the language picker is " + control.Height + " px high, not " + SoftCombo.FieldHeight);
                if ((control is SoftCheck || control is SoftCombo || control is LinkLabel) &&
                    string.IsNullOrEmpty(control.AccessibleName) && string.IsNullOrEmpty(control.Text))
                    findings.Add(where + " :: " + name + " has no name a screen reader says");
            }
            int left = int.MaxValue;
            foreach (Control button in window.Buttons())
            {
                Size wanted = button.GetPreferredSize(Size.Empty);
                if (wanted.Width > button.Width) findings.Add(where + " :: button '" + button.Text + "' needs " + wanted.Width + " px and has " + button.Width);
                if (button.Left < Soft.Px(16)) findings.Add(where + " :: button '" + Short(button.Text) + "' runs past the window's left side");
                if (button.Right > left) findings.Add(where + " :: button '" + button.Text + "' overlaps the one beside it");
                left = Math.Min(left, button.Left);
                if (button.Bottom > window.ClientSize.Height) findings.Add(where + " :: button '" + button.Text + "' is below the window");
            }
            foreach (Label line in window.HeaderLines())
            {
                Size needed = TextRenderer.MeasureText(line.Text, line.Font, new Size(int.MaxValue, 0), TextFormatFlags.NoPrefix);
                if (needed.Width > line.Width) findings.Add(where + " :: the header's '" + Short(line.Text) + "' needs " + needed.Width + " px and has " + line.Width);
                if (needed.Height > line.Height) findings.Add(where + " :: the header's '" + Short(line.Text) + "' needs " + needed.Height + " px high and has " + line.Height);
            }
        }

        private static string Short(string text)
        {
            text = (text ?? "").Replace("\r", " ").Replace("\n", " ");
            return text.Length > 40 ? text.Substring(0, 40) : text;
        }
    }
}
