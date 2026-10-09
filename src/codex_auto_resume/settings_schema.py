"""The settings' schema, as every surface draws it (settings.describe): out of settings.py in v0.6.14-beta.2,
when that module reached its line budget.

The user interfaces render themselves from this, so a field added to settings.FIELDS appears in every
front end at once instead of being wired up three times. Read-only: nothing here is a value or a rule a
value is held to; those stay in settings.py, which hands itself to `describe` - so this module imports
nothing of it, and the two make no cycle.
"""
from __future__ import annotations

from . import continuation, ladder, memguard, ownvalues, power, statusfile


def describe(settings) -> list:
    """Machine-readable schema for the settings interfaces.

    The user interfaces render themselves from this, so a field added here appears in
    every front end at once instead of being wired up three times. A field in
    settings.NOT_YET_OFFERED is not described: it has no front end until something reads it.
    """
    described = []
    for name, (default, _coerce) in settings.FIELDS.items():
        if name in settings.NOT_YET_OFFERED or name in settings.ROW_ACTION_FIELDS or name in settings.DASHBOARD_ONLY:
            continue
        entry = {"name": name, "default": default, "type": settings.field_type(name)}
        if name in settings.RANGES:
            entry.update(settings.RANGES[name])
        if name in settings.OWN:
            entry["custom"] = ownvalues.published(settings.OWN[name])
        if name.startswith("recover_"):
            entry["group"] = "recovery"
            entry["category"] = name[len("recover_"):]
        elif (name.startswith("notify_") or name == "notifications"
              or name in settings.NEEDS_YOU_FIELDS):
            # v0.6.11: the needs-you notice's kinds, its stall and its sound under its own switch.
            entry["group"] = "notifications"
            entry["master"] = name == "notifications"
        elif name in ("theme", "panel_theme", "design", "reduce_motion"):
            # How the surfaces look. Both themes are offered in the window and in the panel. The
            # design and Reduce motion are offered only in the window: both decide what moves, and
            # what moves is not Codex's to change (mcp.tools.PANEL_APPEARANCE). The panel draws in
            # both since v0.6.10, as well as following the host's own reduced-motion preference.
            entry["group"] = "appearance"
        elif name in ("show_tray", "notification_card", "start_with_codex", power.KEEP_AWAKE_FIELD,
                      power.AWAKE_CAP_FIELD, memguard.GUARD_FIELD, memguard.LIMIT_FIELD, statusfile.FIELD):
            # A desktop preference, beside "run at sign-in" - not a notification, and
            # not something the notifications switch governs. The card only chooses how a
            # notification looks on this desktop, so it lives here too, and like the icon it is
            # outside what the Codex panel and MCP may change (mcpserver.USER_GROUPS). v0.6.11: so is
            # keeping this PC awake while a task waits - a question of this PC's power, not of recovery -
            # and the watcher's own memory guard, and a status file written for other tools.
            entry["group"] = "windows"
        elif name in ("max_recovery_attempts", "max_no_progress", "max_chain_continuations",
                      "retry_timing", "quiet_hours_start", "quiet_hours_end", "quiet_hours_days",
                      "default_tier", "objection_minutes", "new_conversation_policy",
                      "project_policy", *ladder.STEP_FIELDS, "retry_jitter", "chain_time_ceiling",
                      "task_changed_guard", "context_guard", power.SLEEP_FIELD, power.NETWORK_FIELD):
            # v0.6.11: quiet hours and the tier a conversation has by default join the limits -
            # how hard, and when, recovery tries - in the window and in the panel alike; and beside
            # the tier, what a new conversation gets and which projects resume without a person;
            # and after them the Custom waits, jitter, the time ceiling and the two guards; and last,
            # what waits after a long sleep, and whether a due recovery waits for the internet.
            entry["group"] = "limits"
        elif name == "observe_only":
            # v0.6.11: a switch of automatic recovery itself, under the kinds it recovers.
            entry["group"] = "recovery"
        elif name == "interface_language":
            entry["group"] = "general"
        elif name in ("continuation_language", "continuation_style", "custom_message_mode"):
            entry["group"] = "continuation"
        elif settings.is_custom_text(name):
            # Free text. The surfaces need to know that before they draw a one-line box
            # for it, and they need the limit before a person types past it.
            entry["group"] = "continuation"
            entry["multiline"] = True
            entry["max_length"] = continuation.MAX_CUSTOM_LENGTH
            if name != "custom_message":
                entry["category"] = name[len("custom_message_"):]
        else:
            entry["group"] = "advanced"
        described.append(entry)
    return described
