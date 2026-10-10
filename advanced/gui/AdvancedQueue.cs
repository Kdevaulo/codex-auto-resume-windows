// ADVANCED-EDITION-CODE: in the advanced edition's window, never the standard one's.
//
// Codex Auto Resume - the prompt queue on the Advanced features page, and on Pending's Scheduled group (v0.6.15-beta).
//
// While prompt_queue is on, its column has a card under its limits: each message queued, a flat line saying for which
// conversation, when it goes and where it stands, with Cancel under it - and Go on for one held - then the form one is
// queued with: the conversation, the words (counted to the bound), when (after this turn, at a time, every day or every
// week), at which hour, how many times for a series, and whether it waits for the one before it to arrive. Queue
// message... asks first. Cancel takes back one Codex already holds (the owner's answer of 2026-10-09); one being sent it
// no longer reaches. Each request is the bridge's (advanced-prompts, advanced-prompt-add, advanced-prompt-cancel,
// advanced-prompt-go-on), with the generation the list was read at.
//
// On Pending, the same lines join the Scheduled group under the reset actions' rules (AddScheduledPrompts), so a message
// queued for later is seen beside the recoveries waiting.
//
// Nothing here draws anything the page does not draw already.
//
// C# 5 (the in-box compiler), as the rest of the window.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Windows.Forms;

namespace CodexAutoResume
{
    internal sealed partial class SettingsForm
    {
        private const string PromptQueueId = "prompt_queue";
        private const int SeriesMost = 30;

        // advanced-prompts' last answer, or null where it was not read or the read failed.
        private Dictionary<string, object> advancedPrompts;
        private SoftCombo queueConversation, queueWhen, queueHour, queueTimes, queueDepends;
        private SoftTextArea queueWords;
        private Label queueCount;
        private Button queueAdd;
        private readonly List<Button> queueCancels = new List<Button>();
        private readonly List<Button> queueGoOns = new List<Button>();

        private string QueueShown(Dictionary<string, object> item)
        {
            if (item == null || Str(item, "id") != PromptQueueId) return "";
            return AdvancedWritten(advancedPrompts) + "|" + AdvancedWritten(ConversationsWritten());
        }

        /// Read advanced-prompts, keep it, and show it on the page and on Pending; `done` once it is shown.
        private void ReadPrompts(MethodInvoker done)
        {
            AdvancedCall("advanced-prompts", "{}", false, delegate(Dictionary<string, object> reply)
            {
                Dictionary<string, object> result = AdvancedResult(reply);
                advancedPrompts = AdvancedDone(result) ? result : null;
                ShowAdvancedDetail();
                FillScheduled();
                if (done != null) done();
            });
        }

        /// The prompts still to go, in their order.
        private List<Dictionary<string, object>> PendingPrompts()
        {
            var found = new List<Dictionary<string, object>>();
            foreach (object entry in Items(advancedPrompts, "prompts") ?? new List<object>())
            {
                var row = entry as Dictionary<string, object>;
                string state = Str(row, "state");
                if (row != null && (state == "waiting" || state == "ready" || state == "held")) found.Add(row);
            }
            return found;
        }

        /// When one goes, in words: after this turn, at a time, or a series with how many of it went.
        private string PromptWhen(Dictionary<string, object> row)
        {
            string trigger = Str(row, "trigger");
            if (trigger == "after_turn") return Word("page.queue.when.after_turn", "After this turn");
            double at = Get(row, "due_at") is double ? (double)Get(row, "due_at") : 0;
            string time = ClockTime(at);
            if (trigger == "at_time") return Word("page.queue.at", "at {time}", "time", time);
            string every = Str(row, "every") == "week" ? Word("page.queue.when.weekly", "Every week")
                                                       : Word("page.queue.when.daily", "Every day");
            return Word("page.queue.series", "{every} at {time}, {sent} of {n}", "every", every).Replace("{time}", time)
                   .Replace("{sent}", Whole(Get(row, "sent_count")).ToString(CultureInfo.CurrentCulture))
                   .Replace("{n}", Whole(Get(row, "occurrences")).ToString(CultureInfo.CurrentCulture));
        }

        /// Where one stands, in words.
        private string PromptState(Dictionary<string, object> row)
        {
            if (Str(row, "reason") == "withdraw_refused")
                return Word("page.queue.state.refused", "Codex would not give it back; it is never sent again");
            if (Str(row, "state") == "held") return Word("page.queue.state.held", "held for you: go on or cancel");
            if (Equals(Get(row, "in_codex"), true)) return Word("page.queue.state.in_codex", "queued in Codex - Cancel takes it back");
            if (Equals(Get(row, "being_sent"), true)) return Word("page.queue.state.being_sent", "being sent");
            return Word("page.queue.state.waiting", "waiting");
        }

        private string PromptLine(Dictionary<string, object> row)
        {
            return Word("page.queue.line", "{conversation} · {when} · {state}", "conversation", ConversationOf(Str(row, "thread_id")))
                   .Replace("{when}", PromptWhen(row)).Replace("{state}", PromptState(row));
        }

        // ---------------------------------------------------------------- the card
        private void BuildQueue(Dictionary<string, object> item)
        {
            ForgetQueueCard();
            if (Str(item, "id") != PromptQueueId || Str(item, "state") != StateArmed || advancedPrompts == null) return;
            TableLayoutPanel card = NewGroup(Word("page.queue.title", "Queued messages"), advancedStack);
            List<Dictionary<string, object>> rows = PendingPrompts();
            if (rows.Count == 0) card.Controls.Add(HelpText(Word("page.queue.none", "No message is queued.")));
            foreach (Dictionary<string, object> row in rows) AddPromptLine(card, row, queueCancels, queueGoOns);
            card.Controls.Add(Caption(Word("page.queue.add", "Queue a message")));
            string conversation = Word("page.resets.field.conversation", "Conversation");
            queueConversation = NewResetCombo(conversation, 260, "queue.conversation");
            foreach (KeyValuePair<string, string> pair in Conversations())
                queueConversation.Items.Add(new Choice(pair.Key, pair.Value));
            PickDraft(queueConversation, "queue.conversation");
            card.Controls.Add(NewRow(conversation, queueConversation));
            if (queueConversation.Items.Count == 0)
                card.Controls.Add(HelpText(Word("page.resets.no_conversation",
                    "No conversation is listed yet. One is offered here once Pending or History lists it.")));
            string words = Word("page.resets.field.words", "Message");
            queueWords = new SoftTextArea();
            queueWords.Font = Font;
            queueWords.Box.Font = Font;
            queueWords.Box.MaxLength = Math.Max(1, Whole(Get(Map(advancedPrompts, "limits"), "words")));
            queueWords.Box.AccessibleName = words;
            queueWords.Height = Px(96);
            queueWords.Dock = DockStyle.Fill;
            queueWords.Margin = Pad(0, 4, 0, 2);
            string draft;
            if (resetDrafts.TryGetValue("queue.words", out draft)) queueWords.Box.Text = draft;
            card.Controls.Add(Caption(words));
            card.Controls.Add(queueWords);
            queueCount = HelpText("");
            card.Controls.Add(queueCount);
            SoftTextArea box = queueWords;
            box.Box.TextChanged += delegate
            {
                resetDrafts["queue.words"] = box.Box.Text;
                CountQueueWords();
                UpdateQueueButtons(busy == 0);
            };
            CountQueueWords();
            string when = Word("page.queue.when", "When");
            queueWhen = NewResetCombo(when, 220, "queue.when");
            queueWhen.Items.Add(new Choice("after_turn", Word("page.queue.when.after_turn", "After this turn")));
            queueWhen.Items.Add(new Choice("at_time", Word("page.queue.when.at_time", "At a time")));
            queueWhen.Items.Add(new Choice("day", Word("page.queue.when.daily", "Every day")));
            queueWhen.Items.Add(new Choice("week", Word("page.queue.when.weekly", "Every week")));
            PickDraft(queueWhen, "queue.when");
            if (queueWhen.SelectedItem == null) queueWhen.SelectedIndex = 0;
            card.Controls.Add(NewRow(when, queueWhen));
            string hour = Word("page.queue.hour", "At");
            queueHour = NewResetCombo(hour, 120, "queue.hour");
            for (int h = 0; h < 24; h++)
                queueHour.Items.Add(new Choice(h.ToString(CultureInfo.InvariantCulture), h.ToString("00", CultureInfo.InvariantCulture) + ":00"));
            PickDraft(queueHour, "queue.hour");
            if (queueHour.SelectedItem == null) queueHour.SelectedIndex = 9;
            card.Controls.Add(NewRow(hour, queueHour));
            string times = Word("page.queue.times", "How many times");
            queueTimes = NewResetCombo(times, 120, "queue.times");
            for (int n = 1; n <= SeriesMost; n++)
                queueTimes.Items.Add(new Choice(n.ToString(CultureInfo.InvariantCulture), n.ToString(CultureInfo.CurrentCulture)));
            PickDraft(queueTimes, "queue.times");
            if (queueTimes.SelectedItem == null) queueTimes.SelectedIndex = 0;
            card.Controls.Add(NewRow(times, queueTimes));
            string depends = Word("page.queue.depends", "Wait for the one before it to arrive");
            queueDepends = NewResetCombo(depends, 120, "queue.depends");
            queueDepends.Items.Add(new Choice("no", Word("page.queue.depends.no", "No")));
            queueDepends.Items.Add(new Choice("yes", Word("page.queue.depends.yes", "Yes")));
            PickDraft(queueDepends, "queue.depends");
            if (queueDepends.SelectedItem == null) queueDepends.SelectedIndex = 0;
            card.Controls.Add(NewRow(depends, queueDepends));
            if (Equals(Get(advancedPrompts, "after_turn_unproven"), true))
                card.Controls.Add(HelpText(Word("page.queue.unproven",
                    "After this turn is unproven on this Codex until it has been measured.")));
            queueWhen.SelectionChangeCommitted += delegate { UpdateQueueButtons(busy == 0); };
            queueAdd = CardButton(card, Word("page.queue.button", "Queue message..."), delegate { AddPrompt(); });
            queueAdd.Margin = Pad(0, 8, 0, 4);
        }

        /// One prompt's line, with Go on for one held and Cancel while Cancel reaches it, into `card`.
        private void AddPromptLine(TableLayoutPanel card, Dictionary<string, object> row, List<Button> cancels, List<Button> goOns)
        {
            int prompt = Whole(Get(row, "prompt_id"));
            string text = PromptLine(row);
            Label shown = HelpText(text);
            shown.ForeColor = Ink;
            shown.Margin = Pad(0, 6, 0, 2);
            card.Controls.Add(shown);
            if (Str(row, "state") == "held")
            {
                Button goOn = CardButton(card, Word("page.queue.go_on", "Go on"), delegate { GoOnPrompt(prompt); });
                goOn.Tag = (double)prompt;
                goOn.AccessibleName = Word("page.queue.go_on", "Go on") + " " + text;
                goOns.Add(goOn);
            }
            if (Equals(Get(row, "being_sent"), true) || Str(row, "reason") == "withdraw_refused") return;
            Button cancel = CardButton(card, Word("page.resets.cancel", "Cancel"), delegate { CancelPrompt(prompt); });
            cancel.Tag = (double)prompt;
            cancel.AccessibleName = Word("page.resets.cancel", "Cancel") + " " + text;
            cancels.Add(cancel);
        }

        /// Pending's Scheduled group: the prompts still to go, under the reset rules (AdvancedResets.FillScheduled).
        private int AddScheduledPrompts(TableLayoutPanel lines)
        {
            List<Dictionary<string, object>> rows = PendingPrompts();
            foreach (Dictionary<string, object> row in rows) AddPromptLine(lines, row, scheduledCancels, scheduledGoOns);
            return rows.Count;
        }

        private void ForgetQueueCard()
        {
            queueConversation = queueWhen = queueHour = queueTimes = queueDepends = null;
            queueWords = null;
            queueCount = null;
            queueAdd = null;
            queueCancels.Clear();
            queueGoOns.Clear();
        }

        private void CountQueueWords()
        {
            if (queueWords == null || queueCount == null) return;
            queueCount.Text = Word("page.resets.count", "{n} of {most} characters", "n", queueWords.Box.Text.Length)
                .Replace("{most}", Math.Max(1, Whole(Get(Map(advancedPrompts, "limits"), "words"))).ToString(CultureInfo.CurrentCulture));
        }

        private void UpdateQueueButtons(bool idle)
        {
            bool listed = idle && advancedListing != null && advancedPrompts != null;
            var when = queueWhen == null ? null : queueWhen.SelectedItem as Choice;
            if (queueHour != null) queueHour.Enabled = listed && when != null && when.Value != "after_turn";
            if (queueTimes != null) queueTimes.Enabled = listed && when != null && (when.Value == "day" || when.Value == "week");
            if (queueAdd != null)
                queueAdd.Enabled = listed && queueConversation != null && queueConversation.SelectedItem != null && when != null &&
                                   queueWords != null && queueWords.Box.Text.Trim().Length > 0;
            foreach (Button button in queueCancels) button.Enabled = listed;
            foreach (Button button in queueGoOns) button.Enabled = listed;
        }

        /// The next time the hour chosen comes, in Codex's seconds: today's, or tomorrow's where it has gone by.
        private static double NextHour(int hour)
        {
            DateTime now = DateTime.Now;
            DateTime at = now.Date.AddHours(hour);
            if (at <= now.AddMinutes(1)) at = at.AddDays(1);
            return (at.ToUniversalTime() - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds;
        }

        private void AddPrompt()
        {
            if (busy > 0 || advancedListing == null || queueConversation == null || queueWords == null || queueWhen == null) return;
            var conversation = queueConversation.SelectedItem as Choice;
            var when = queueWhen.SelectedItem as Choice;
            if (conversation == null || when == null) return;
            var argument = new System.Text.StringBuilder("{\"thread_id\":");
            argument.Append(Json.Escape(conversation.Value)).Append(",\"words\":").Append(Json.Escape(queueWords.Box.Text));
            string whenWords = when.ToString();
            if (when.Value == "after_turn") argument.Append(",\"trigger\":\"after_turn\"");
            else
            {
                var hour = queueHour == null ? null : queueHour.SelectedItem as Choice;
                if (hour == null) return;
                double at = NextHour(int.Parse(hour.Value, CultureInfo.InvariantCulture));
                bool series = when.Value == "day" || when.Value == "week";
                argument.Append(",\"trigger\":").Append(Json.Escape(series ? "recurring" : "at_time"))
                        .Append(",\"at\":").Append(at.ToString("0", CultureInfo.InvariantCulture));
                if (series)
                {
                    var times = queueTimes == null ? null : queueTimes.SelectedItem as Choice;
                    argument.Append(",\"every\":").Append(Json.Escape(when.Value))
                            .Append(",\"occurrences\":").Append(times == null ? "1" : times.Value);
                }
                whenWords = whenWords + " " + hour;
            }
            var depends = queueDepends == null ? null : queueDepends.SelectedItem as Choice;
            argument.Append(",\"depends\":").Append(depends != null && depends.Value == "yes" ? "true" : "false");
            argument.Append(",\"generation\":").Append(AdvancedGeneration()).Append('}');
            string question = Word("page.confirm.prompt",
                "Queue this message for {conversation}, {when}? It is sent once, exactly as written.",
                "conversation", conversation.ToString()).Replace("{when}", whenWords);
            if (!AskAdvanced(question, Affirm(Word("page.queue.button", "Queue message...")))) return;
            AdvancedCall("advanced-prompt-add", argument.ToString(), true, delegate(Dictionary<string, object> reply)
            {
                Dictionary<string, object> result = AdvancedResult(reply);
                if (AdvancedDone(result))
                {
                    resetDrafts.Remove("queue.words");
                    ResetNote(Word("page.done.prompt_added", "Queued."));
                }
                ReadAdvanced(null);
                if (!AdvancedDone(result)) TellAdvanced(PromptRefusal(Str(result, "refusal")));
            });
        }

        private void CancelPrompt(int prompt)
        {
            if (busy > 0 || advancedListing == null) return;
            string argument = "{\"prompt\":" + prompt.ToString(CultureInfo.InvariantCulture) + ",\"generation\":" + AdvancedGeneration() + "}";
            AdvancedCall("advanced-prompt-cancel", argument, true, delegate(Dictionary<string, object> reply)
            {
                Dictionary<string, object> result = AdvancedResult(reply);
                if (AdvancedDone(result)) ResetNote(Word("page.done.reset_cancelled", "Cancelled."));
                ReadAdvanced(null);
                if (advancedOpen != PromptQueueId) ReadPrompts(null);
                if (!AdvancedDone(result)) TellAdvanced(PromptRefusal(Str(result, "refusal")));
            });
        }

        private void GoOnPrompt(int prompt)
        {
            if (busy > 0 || advancedListing == null) return;
            string argument = "{\"prompt\":" + prompt.ToString(CultureInfo.InvariantCulture) + ",\"generation\":" + AdvancedGeneration() + "}";
            AdvancedCall("advanced-prompt-go-on", argument, true, delegate(Dictionary<string, object> reply)
            {
                Dictionary<string, object> result = AdvancedResult(reply);
                if (AdvancedDone(result)) ResetNote(Word("page.done.prompt_added", "Queued."));
                ReadAdvanced(null);
                if (advancedOpen != PromptQueueId) ReadPrompts(null);
                if (!AdvancedDone(result)) TellAdvanced(PromptRefusal(Str(result, "refusal")));
            });
        }

        private string PromptRefusal(string refusal)
        {
            if (refusal == "prompt_refused")
                return Word("page.refused.prompt_refused", "That message cannot be queued: it is empty or too long, holds a marker of this product's, or is one of its own continuations.");
            if (refusal == "queue_full")
                return Word("page.refused.queue_full", "As many messages are queued as may: five for a conversation, twenty in all. Cancel one to queue another.");
            if (refusal == "dependency_unknown")
                return Word("page.refused.dependency_unknown", "No message is queued before it in that conversation, so it cannot wait for one.");
            return ResetRefusal(refusal);
        }
    }
}
