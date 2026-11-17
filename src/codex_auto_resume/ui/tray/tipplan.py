"""Where everything on the icon's own tooltip card goes (v0.6.24): a plan, in the popup renderer's items.

Hovering over the icon shows a card in the product's design instead of Windows' tooltip (the owner's option 2): the
status light the popup's header has, the product's name and - in the advanced edition - its edition's chip, the state
line with its countdown in the accent, and in the advanced edition a row per usage window, its length, a thin bar and
the share left of it (v0.6.24 final). The same facts the tooltip has said (words.tooltip_parts), no new ones, never cut short.

Pure: a function of the parts, the light, the scale and a way to measure text, as the popup's layout is. It returns
rectangles and paints nothing, so the card is laid out and checked at every language and scale with no screen; the
window that shows it, and the renderer that draws it, are tipcard.py's. Right to left is the popup's own mirror,
applied by the renderer that measures (tipcard.TipRenderer.tip_layout).
"""
from __future__ import annotations

from ... import brand


# The card, in device-independent pixels at 96 DPI (the mockup's Tray board; the owner's O16): as wide as its widest
# row needs, never wider than this - a longer line wraps, and the card is then as wide as the widest line it wrapped
# into - and padded 13 above and below, 16 at the sides. No least width: the owner, 2026-11-16, of the card with no
# usage rows - "우측이 빈공간이 큰게 아쉬워" (the 280 it had left the right side wider than the left).
TIP_MOST = 360
TIP_PAD_Y, TIP_PAD_X = 13, 16
# From the card to the taskbar, and to the icon it stands by (O16).
TIP_GAP = 8
# The box the status light sits in, beside the product's name; the light is the popup header's (STATUS_DOT["popup"]).
TIP_MARK = 14
# A usage window's bar: its height, and the narrowest it is drawn between its label and its share.
TIP_BAR = 6
TIP_BAR_LEAST = 72
# Between two pieces of the state line, as the tooltip joins them.
TIP_JOIN = " · "
# The roles each line is set in: the popup's own font roles (fonts.ROLES).
TIP_ROLES = {"title": "name", "chip": "chip", "line": "body", "meter": "small"}


def tip_layout(parts, light, scale, measure) -> dict:
    """Every rectangle of the card in device pixels, left to right, and its size.

    `parts` is words.tooltip_parts' dict; `light` the status light's state (a key of brand.STATUS_FILL); `measure(role,
    text, width, wrap)` returns the (width, height) a text takes in a popup font role. The plan is the popup's shape -
    `size`, `card`, `items`, `targets` (none: nothing on the card is pressed), `scale` - so the popup's renderer draws
    its items and its mirror turns it right to left. The card fills the window: nothing is drawn round it, as round the
    icon's menu (the owner, 2026-11-01 and 11-02: a lift's lit edge and its pale shadow shone as a halo on a dark
    taskbar)."""
    space = brand.SPACING

    def px(value):
        return int(round(value * scale))

    roles = TIP_ROLES
    pad_y, pad_x, gap = px(TIP_PAD_Y), px(TIP_PAD_X), px(space["s"])
    mark = px(TIP_MARK)
    wide = 10 ** 5

    # What each row needs on one line, to choose the card's width.
    title_w, title_h = measure(roles["title"], parts["title"], wide, False)
    chip = parts.get("edition")
    chip_w = chip_h = chip_pad = 0
    if chip:
        chip_text_w, chip_text_h = measure(roles["chip"], chip, wide, False)
        chip_pad = px(brand.LAYOUT["chip_pad_x"])
        chip_w = chip_text_w + 2 * chip_pad
        chip_h = max(px(brand.LAYOUT["chip_height"]), chip_text_h)
    head_need = mark + gap + title_w + (gap + chip_w if chip else 0)
    most = px(TIP_MOST)
    pieces = list(parts.get("line") or ())
    join_w, line_h = measure(roles["line"], TIP_JOIN, wide, False)
    widths = [measure(roles["line"], text, wide, False)[0] for text, _ in pieces]
    # The state line, broken where the widest card breaks it: a piece that does not fit what is left of a line starts
    # the next one (the join is not carried over), and one wider than a whole line wraps. The card then takes the
    # widest line it broke into, so no line leaves the right side emptier than the left.
    line_room = most - 2 * pad_x - mark - gap
    lines = []
    if pieces:
        current, used = [], 0
        for (value, counts), piece_w in zip(pieces, widths):
            if current and used + join_w + piece_w > line_room:
                lines.append(current)
                current, used = [], 0
            if current:
                current.append((TIP_JOIN, "ink", join_w))
                used += join_w
            current.append((value, "accent" if counts else "ink", piece_w))
            used += piece_w
        lines.append(current)
    line_need = mark + gap + max([min(line_room, sum(run[2] for run in runs)) for runs in lines] or [0])
    rows = list(parts.get("meter") or ())
    label_w = max([measure(roles["meter"], row["label"], wide, False)[0] for row in rows] or [0])
    share_w = max([measure(roles["meter"], row["percent"], wide, False)[0] for row in rows] or [0])
    meter_need = (label_w + gap + px(TIP_BAR_LEAST) + gap + share_w) if rows else 0
    width = min(most, max(head_need, line_need, meter_need) + 2 * pad_x)
    left, right = pad_x, width - pad_x
    inner = right - left
    items = []

    def text(rect, role, value, colour, *, wrap=False, align="left"):
        items.append({"kind": "text", "rect": rect, "role": role, "text": value, "colour": colour, "wrap": wrap,
                      "align": align, "target": None})

    # Row 1: the light, the name, the edition's chip.
    y = pad_y
    text_left = left + mark + gap
    if chip:
        chip_w = min(chip_w, inner // 2)
    title_room = right - text_left - (gap + chip_w if chip else 0)
    title_w = min(title_w, title_room)
    head_h = max(mark, title_h, chip_h)
    items.append({"kind": "halo", "cx": left + mark / 2.0, "cy": y + head_h / 2.0, "state": light,
                  "radius": brand.glow_extent(brand.STATUS_DOT["popup"]) * scale, "sweep_reach": 0.0})
    top = y + (head_h - title_h) // 2
    text((text_left, top, text_left + title_w, top + title_h), roles["title"], parts["title"], "ink")
    if chip:
        chip_left = text_left + title_w + gap
        chip_top = y + (head_h - chip_h) // 2
        rect = (chip_left, chip_top, chip_left + chip_w, chip_top + chip_h)
        items.append({"kind": "chip", "rect": rect, "tone": "accent"})
        text((rect[0] + chip_pad, rect[1], rect[2] - chip_pad, rect[3]), roles["chip"], chip, "accent", align="center")
    y += head_h

    # Row 2: the state line under the name, as it was broken above, piece by piece, the countdown in the accent.
    if lines:
        y += px(space["xs"])
        room = right - text_left
        for runs in lines:
            if len(runs) == 1 and runs[0][2] > room:
                value, colour, _ = runs[0]
                _, wrapped_h = measure(roles["line"], value, room, True)
                text((text_left, y, right, y + wrapped_h), roles["line"], value, colour, wrap=True)
                y += wrapped_h
                continue
            x = text_left
            for value, colour, piece_w in runs:
                text((x, y, min(right, x + piece_w), y + line_h), roles["line"], value, colour)
                x += piece_w
            y += line_h

    # The advanced edition's meter: a row per window - its length, a bar filled as far as the window has LEFT, the share
    # left (v0.6.24 final). As little left as words.LOW_LEFT or less is the warning colour, bar, well and share alike, so an
    # empty bar never reads as nothing to worry about.
    if rows:
        y += px(space["s"])
        _, row_h = measure(roles["meter"], "Ag", wide, False)
        label_col = min(label_w, inner // 3)
        bar_left, bar_right = left + label_col + gap, right - share_w - gap
        bar_h = max(2, px(TIP_BAR))
        for index, row in enumerate(rows):
            if index:
                y += px(space["xs"])
            text((left, y, left + label_col, y + row_h), roles["meter"], row["label"], "muted")
            bar_top = y + (row_h - bar_h) // 2
            low = bool(row.get("low"))
            items.append({"kind": "meter", "rect": (bar_left, bar_top, bar_right, bar_top + bar_h),
                          "fraction": row["fraction"], "low": low})
            text((right - share_w, y, right, y + row_h), roles["meter"], row["percent"], "warning" if low else "ink",
                 align="right")
            y += row_h

    y += pad_y
    card = (0, 0, width, y)
    items.insert(0, {"kind": "card", "rect": card, "radius": px(brand.RADII["card"]), "corner": "card"})
    return {"size": (width, y), "card": card, "items": items, "targets": [], "scale": scale, "rows": []}


def tip_anchor(icon=None, point=None, cursor=None):
    """The box the card stands beside, in screen pixels: the icon's rectangle (Shell_NotifyIconGetRect) when the pointer
    or the shell's anchor point is on it; else the anchor point - in the hidden-icons flyout Windows 11 gives the
    flyout button's rectangle, not the icon's - else the pointer, else the rectangle as it is, else None."""
    def on(spot, rect):
        return bool(spot and rect) and rect[0] <= spot[0] < rect[2] and rect[1] <= spot[1] < rect[3]
    if icon and (on(cursor, icon) or on(point, icon)):
        return tuple(icon)
    for spot in (point, cursor):
        if spot:
            return (spot[0], spot[1], spot[0] + 1, spot[1] + 1)
    return tuple(icon) if icon else None


def tip_text(plan) -> str:
    """Every word the plan draws, in drawing order, each line once: what a test reads the card's words back from."""
    return " ".join(item["text"] for item in plan["items"] if item["kind"] == "text")
