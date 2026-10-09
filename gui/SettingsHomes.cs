// Codex Auto Resume - the Codex homes watched (v0.6.14-beta.2): a card of Settings > Advanced, after the limits.
//
// The default Codex home is always watched. Up to three more can be added here and only here - MCP refuses the
// setting by name, and no generated editor draws it - each a folder and an alias of 1 to 32 characters, which
// Pending and History show beside a record of that home when there are several. Like the power action's card it
// is no editor: Add, Rename and Remove write at once through the bridge's `update`, which checks every folder
// against this PC (homes.strict) and answers a refusal in words a person can act on; Save does not change it.
// What the watcher found of each home - watched, another watcher has it, unavailable, the Codex app on another
// home, the same folder as another, being removed - comes with every status read (`codex_homes`).

using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal sealed partial class SettingsForm
    {
        /// At most this many homes beside the default one (homes.MAX_EXTRA), and an alias at most this long.
        internal const int HomesMax = 3;
        internal const int HomeAliasMax = 32;

        private TableLayoutPanel homesCard, homesRows;
        private Label homesWarning, homesRefusal;
        private Button homesAdd;
        /// The homes as the last status said them: `codex_homes.homes`, each {alias, path, state}, the default first.
        private List<Dictionary<string, object>> homesShown = new List<Dictionary<string, object>>();
        private string homesSignature;

        /// Builds the card at the end of `stack` - Settings > Advanced, after the limits.
        private void BuildHomes(TableLayoutPanel stack)
        {
            homesCard = NewGroup(S("homes.title", "Codex homes"), stack);
            homesCard.Controls[0].Anchor = AnchorStyles.Left | AnchorStyles.Right | AnchorStyles.Top;
            homesCard.Controls.Add(HelpText(S("homes.help",
                "Your default Codex home is always watched. Add up to three more; a conversation in one is resumed only while the Codex app was started on that home (CODEX_HOME set before it starts). It applies at once; Save does not change it.")));
            homesRows = new TableLayoutPanel();
            homesRows.AutoSize = true;
            homesRows.AutoSizeMode = AutoSizeMode.GrowAndShrink;
            homesRows.ColumnCount = 1;
            homesRows.Dock = DockStyle.Top;
            homesRows.Margin = Pad(0, 2, 0, 2);
            homesCard.Controls.Add(homesRows);
            homesWarning = HelpText("");
            homesCard.Controls.Add(homesWarning);
            homesRefusal = HelpText("");
            homesRefusal.ForeColor = Palette.Danger;
            homesCard.Controls.Add(homesRefusal);
            FlowLayoutPanel buttons = ButtonRow();
            homesAdd = MakeButton(S("homes.add", "Add a Codex home..."), false, delegate { AddHome(); });
            homesAdd.Margin = Pad(0, 0, 0, 0);
            buttons.Controls.Add(homesAdd);
            homesCard.Controls.Add(buttons);
            ShowHomes();
        }

        /// From a status read (ApplyStatus): the homes and what the watcher found of each, and whether watching a
        /// second home is unproven on the Codex in force (MH, measured on 0.158 only).
        private void ApplyHomesStatus(Dictionary<string, object> status)
        {
            if (homesCard == null || status == null) return;
            var view = Map(status, "codex_homes");
            var shown = new List<Dictionary<string, object>>();
            foreach (object entry in Items(view, "homes") ?? new List<object>())
            {
                var home = entry as Dictionary<string, object>;
                if (home != null) shown.Add(home);
            }
            homesShown = shown;
            ShowLine(homesWarning, Equals(Get(view, "unmeasured"), true)
                ? S("homes.unmeasured", "Watching a second Codex home was proven on Codex 0.158; on this Codex it is unproven.")
                : "");
            ShowHomes();
        }

        /// The rows: one line per home - its alias, its folder and what the watcher found - with Rename and Remove for
        /// each one added here. Rebuilt only when what it shows changed.
        private void ShowHomes()
        {
            if (homesRows == null) return;
            var signature = new System.Text.StringBuilder();
            foreach (var home in homesShown)
                signature.Append(Str(home, "alias")).Append('|').Append(Str(home, "path")).Append('|')
                         .Append(Str(home, "state")).Append('\n');
            string key = signature.ToString();
            homesAdd.Enabled = Extras().Count < HomesMax;
            if (key == homesSignature) return;
            homesSignature = key;
            homesRows.SuspendLayout();
            homesRows.Controls.Clear();
            foreach (var home in homesShown)
            {
                bool extra = Str(home, "key") != "";
                var line = HelpText((extra ? Str(home, "alias") : S("homes.default", "Default")) + " · "
                                    + (Str(home, "path") ?? "") + " · " + HomeStateName(Str(home, "state")));
                line.ForeColor = Ink;
                homesRows.Controls.Add(line);
                if (!extra) continue;
                FlowLayoutPanel actions = ButtonRow();
                string path = Str(home, "path");
                actions.Controls.Add(MakeButton(S("homes.rename", "Rename..."), false, delegate { RenameHome(path); }));
                actions.Controls.Add(MakeButton(S("homes.remove", "Remove"), false, delegate { RemoveHome(path); }));
                homesRows.Controls.Add(actions);
            }
            homesRows.ResumeLayout();
        }

        /// What the watcher found of a home, in words (HomeState). Written as tests, not a switch: a switch of this many
        /// strings makes the compiler emit a class it names at random (build/normalize_pe.py).
        private string HomeStateName(string state)
        {
            if (state == "watched") return S("homes.state.watched", "Watched");
            if (state == "lock_busy") return S("homes.state.lock_busy", "Another watcher has it");
            if (state == "unavailable") return S("homes.state.unavailable", "Folder unavailable");
            if (state == "other_home") return S("homes.state.other_home", "The Codex app runs on another home");
            if (state == "duplicate") return S("homes.state.duplicate", "The same folder as another home");
            if (state == "retiring") return S("homes.state.retiring", "Removing: waiting for what was sent there to settle");
            return S("homes.state.waiting", "Not looked at yet");
        }

        /// The homes added here, as the setting holds them: {path, alias}, in their order.
        private List<Dictionary<string, object>> Extras()
        {
            var found = new List<Dictionary<string, object>>();
            foreach (var home in homesShown)
            {
                if (Str(home, "key") == "" || Str(home, "path") == null) continue;
                var entry = new Dictionary<string, object>();
                entry["path"] = Str(home, "path");
                entry["alias"] = Str(home, "alias") ?? "";
                found.Add(entry);
            }
            return found;
        }

        private void AddHome()
        {
            if (Extras().Count >= HomesMax) return;
            string path;
            using (var picker = new FolderBrowserDialog())
            {
                picker.Description = S("homes.pick", "Choose a Codex home: a folder with Codex's state in it");
                picker.ShowNewFolderButton = false;
                if (picker.ShowDialog(this) != DialogResult.OK || string.IsNullOrEmpty(picker.SelectedPath)) return;
                path = picker.SelectedPath;
            }
            string name = Path.GetFileName(path.TrimEnd('\\', '/'));
            string alias = AskAlias(string.IsNullOrEmpty(name) ? path : name);
            if (alias == null) return;
            var homes = Extras();
            var entry = new Dictionary<string, object>();
            entry["path"] = path;
            entry["alias"] = alias;
            homes.Add(entry);
            WriteHomes(homes);
        }

        private void RenameHome(string path)
        {
            var homes = Extras();
            foreach (var home in homes)
            {
                if (Str(home, "path") != path) continue;
                string alias = AskAlias(Str(home, "alias"));
                if (alias == null) return;
                home["alias"] = alias;
                WriteHomes(homes);
                return;
            }
        }

        private void RemoveHome(string path)
        {
            var homes = Extras();
            homes.RemoveAll(delegate(Dictionary<string, object> home) { return Str(home, "path") == path; });
            WriteHomes(homes);
        }

        /// The homes written at once (`update`), and the card redrawn from the next status. A refusal is shown under
        /// the rows in the settings layer's own words, and nothing changed.
        private void WriteHomes(List<Dictionary<string, object>> homes)
        {
            var list = new List<object>();
            foreach (var home in homes) list.Add(home);
            var changes = new Dictionary<string, object>();
            changes["codex_homes"] = list;
            ShowLine(homesRefusal, "");
            CallAsync("update", Json.Write(changes), delegate(Dictionary<string, object> reply)
            {
                if (!Ok(reply))
                {
                    ShowLine(homesRefusal, S("homes.refused", "Not saved: {reason}", "reason", Str(reply, "error") ?? ""));
                    return;
                }
                homesSignature = null;
                RefreshNow();
            });
        }

        /// An alias for a home, asked in a small dialog: 1 to 32 characters on one line. Null when cancelled.
        private string AskAlias(string current)
        {
            using (var dialog = new Form())
            {
                dialog.Text = S("homes.alias", "Name for this Codex home");
                dialog.Font = Font;
                dialog.BackColor = Canvas;
                dialog.ForeColor = Ink;
                Soft.TitleBar(dialog);
                dialog.StartPosition = FormStartPosition.CenterParent;
                dialog.MinimizeBox = false;
                dialog.MaximizeBox = false;
                dialog.ShowInTaskbar = false;
                dialog.ShowIcon = false;
                dialog.ClientSize = new Size(Px(420), Px(170));
                var body = new SoftStack();
                body.Dock = DockStyle.Fill;
                body.ColumnCount = 1;
                body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));
                body.GrowStyle = TableLayoutPanelGrowStyle.AddRows;
                body.Padding = Pad(16, 16, 16, 0);
                body.BackColor = Canvas;
                var area = new SoftTextArea();
                area.Dock = DockStyle.Fill;
                area.Margin = Pad(0, 6, 0, 2);
                area.Font = Font;
                area.Box.Font = Font;
                area.Box.Multiline = false;
                area.Box.MaxLength = HomeAliasMax;
                string start = current ?? "";
                area.Box.Text = start.Length > HomeAliasMax ? start.Substring(0, HomeAliasMax) : start;
                area.Box.AccessibleName = S("homes.alias", "Name for this Codex home");
                area.Height = Px(38);
                body.Controls.Add(area);
                dialog.Controls.Add(body);
                string chosen = null;
                FlowLayoutPanel buttons = ButtonRow();
                buttons.FlowDirection = FlowDirection.RightToLeft;
                buttons.Padding = Pad(0, 12, 16, 16);
                Button save = MakeButton(S("action.save", "Save"), true, delegate
                {
                    string text = (area.Box.Text ?? "").Trim();
                    if (text.Length == 0) return;
                    chosen = text;
                    dialog.Close();
                });
                Button cancel = MakeButton(S("action.cancel", "Cancel"), false, delegate { dialog.Close(); });
                buttons.Controls.Add(save);
                buttons.Controls.Add(cancel);
                buttons.Dock = DockStyle.Bottom;
                dialog.Controls.Add(buttons);
                dialog.AcceptButton = save;
                dialog.CancelButton = cancel;
                dialog.ShowDialog(this);
                return chosen;
            }
        }
    }
}
