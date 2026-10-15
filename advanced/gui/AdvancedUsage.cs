// ADVANCED-EDITION-CODE: in the advanced edition's window, never the standard one's.
//
// Codex Auto Resume - the Advanced features page's near-the-limit choices (v0.6.16-beta.4, the owner's additions to
// issue #29).
//
// Wrap up near a limit's words as they would be sent: under its drop-downs, for each window, the exact words the wrap-up
// would send now - its wording, numbers, reset time and Custom words as they stand, in the continuation language - as
// the continuation styles show theirs (the bridge makes them: advanced-wordings' `previews`).
//
// Wrap up near a limit's Custom wording: while its Wording is Custom, its Choices card has, under the drop-downs, one
// box for each window - the five-hour and the weekly - with the person's own words (advanced-wordings, read when the
// capability opens), a line saying which numbers the words may hold, and Save words under each (advanced-wording, with
// the generation the page read). A refusal says why, in the page's words for each of the custom text's checks. The words
// are the person's own and are never written anywhere but the advanced state.
//
// Nothing here draws anything the page does not draw already: the captions, help lines, boxes and buttons are the
// Settings page's.
//
// C# 5 (the in-box compiler), as the rest of the window.

using System;
using System.Collections.Generic;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal sealed partial class SettingsForm
    {
        // Wrap up near a limit (registry.USAGE_WRAP_UP), whose Choices card holds its Custom wording.
        private const string WrapUpId = "usage_wrap_up";
        private const int CustomWording = 5;
        // The two windows' wording keys (vocabulary.WordingKey), in the order the boxes are shown.
        private static readonly string[] WordingKeys = { "wrap_custom_five_hour", "wrap_custom_weekly" };

        // advanced-wordings' last answer, or null where it was not read or the read failed.
        private Dictionary<string, object> advancedWordings;
        // Each window's box and its Save words, as the card was built.
        private readonly Dictionary<string, SoftTextArea> wordingBoxes = new Dictionary<string, SoftTextArea>();
        private readonly Dictionary<string, Button> wordingSaves = new Dictionary<string, Button>();
        // The windows' lengths in minutes, as advanced-wordings' previews are keyed, and each one's line on the card.
        private static readonly string[] PreviewWindows = { "300", "10080" };
        private readonly List<Label> previewLines = new List<Label>();

        /// The wrap-up's wordings read, then `after`.
        private void ReadWordings(MethodInvoker after)
        {
            AdvancedCall("advanced-wordings", "{\"capability\":" + Json.Escape(WrapUpId) + "}", false, delegate(Dictionary<string, object> reply)
            {
                Dictionary<string, object> result = AdvancedResult(reply);
                advancedWordings = AdvancedDone(result) ? result : null;
                ShowAdvancedDetail();
                after();
            });
        }

        /// What the wrap-up's wording boxes are built from, for ShowAdvancedDetail to compare.
        private string WordingsShown(Dictionary<string, object> item)
        {
            return Str(item, "id") == WrapUpId ? AdvancedWritten(advancedWordings) : "";
        }

        /// Under the wrap-up's drop-downs, while its Wording is Custom: a box for each window with the person's words and
        /// Save words under it.
        private void BuildWordings(string id, List<object> options, TableLayoutPanel card)
        {
            wordingBoxes.Clear();
            wordingSaves.Clear();
            previewLines.Clear();
            if (id != WrapUpId || advancedWordings == null) return;
            // (a) What is sent, exactly, for each window - whatever the wording.
            Dictionary<string, object> previews = Map(advancedWordings, "previews");
            card.Controls.Add(Caption(Word("page.preview.title", "What is sent")));
            foreach (string minutes in PreviewWindows)
            {
                string words = Str(previews, minutes);
                if (words == null) continue;
                Label line = HelpText(Word("page.preview." + minutes, minutes) + Environment.NewLine + words);
                line.ForeColor = Ink;
                line.Margin = Pad(0, 2, 0, 6);
                card.Controls.Add(line);
                previewLines.Add(line);
            }
            if (OptionValue(options, "wrap_style") != CustomWording) return;
            Dictionary<string, object> held = Map(advancedWordings, "wordings");
            int most = Math.Max(1, Whole(Get(advancedWordings, "limit")));
            card.Controls.Add(HelpText(Word("page.wording.help", "Your words may hold {percent}, {window}, {stop_at} and {reset}, each filled in when they are sent, and nothing else in braces. A window with no words of its own is sent the standard wording.")));
            foreach (string key in WordingKeys)
            {
                string caption = Word("page.wording." + key, key);
                var box = new SoftTextArea();
                box.Font = Font;
                box.Box.Font = Font;
                box.Box.MaxLength = most;
                box.Box.AccessibleName = caption;
                box.Height = Px(72);
                box.Dock = DockStyle.Fill;
                box.Margin = Pad(0, 4, 0, 2);
                string draft;
                box.Box.Text = resetDrafts.TryGetValue("wording." + key, out draft) ? draft : (Str(held, key) ?? "");
                string draftKey = "wording." + key;
                SoftTextArea typed = box;
                box.Box.TextChanged += delegate { resetDrafts[draftKey] = typed.Box.Text; };
                card.Controls.Add(Caption(caption));
                card.Controls.Add(box);
                string chosen = key;
                Button save = CardButton(card, Word("page.wording.save", "Save words"), delegate { SaveWording(chosen); });
                save.AccessibleName = Word("page.wording.save", "Save words") + " " + caption;
                wordingBoxes[key] = box;
                wordingSaves[key] = save;
            }
        }

        /// A choice's value as the list says it is now, or 0.
        private static int OptionValue(List<object> options, string key)
        {
            foreach (object entry in options ?? new List<object>())
            {
                var option = entry as Dictionary<string, object>;
                if (Str(option, "key") == key) return Whole(Get(option, "value"));
            }
            return 0;
        }

        /// One window's words saved as typed - or, where the box is blank, taken away, so that window is sent the standard
        /// wording - against the generation the page read.
        private void SaveWording(string key)
        {
            SoftTextArea box;
            if (busy > 0 || advancedListing == null || !wordingBoxes.TryGetValue(key, out box)) return;
            string text = box.Box.Text;
            string words = text.Trim().Length == 0 ? "null" : Json.Escape(text);
            string argument = "{\"capability\":" + Json.Escape(WrapUpId) + ",\"key\":" + Json.Escape(key) + ",\"words\":" + words +
                              ",\"generation\":" + AdvancedGeneration() + "}";
            string name = AdvancedName(WrapUpId);
            AdvancedCall("advanced-wording", argument, true, delegate(Dictionary<string, object> reply)
            {
                Dictionary<string, object> result = AdvancedResult(reply);
                if (AdvancedDone(result))
                {
                    resetDrafts.Remove("wording." + key);
                    SetNote(advancedNote, Word("page.done.wording", "{name} uses these words from now on.", "name", name));
                }
                advancedShown = null;
                ReadAdvanced(null);
                if (!AdvancedDone(result)) TellAdvanced(WordingRefusal(result));
            });
        }

        /// A refused wording in words: which of the custom text's checks it failed, or as the page says any refusal.
        private string WordingRefusal(Dictionary<string, object> result)
        {
            string problem = Str(result, "problem");
            if (Str(result, "refusal") == "wording_invalid" && problem != null)
                return Word("page.refused.wording." + problem, Word("page.refused.other", "That request was refused. Nothing was changed."));
            return KeptRefusal(Str(result, "refusal"));
        }

        /// What Save words may do now: nothing while another action is under way.
        private void UpdateWordingButtons(bool idle)
        {
            foreach (Button save in wordingSaves.Values) save.Enabled = idle && advancedListing != null;
        }
    }
}
