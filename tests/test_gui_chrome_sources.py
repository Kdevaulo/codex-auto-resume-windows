r"""v0.6.24 (stage 1, surface A): no Windows title bar on any window or dialog - read in the window's sources.

The owner, 2026-11-13 and 2026-11-15 (board TitleB, option B): the minimise, maximise and close buttons stand in each
window's first card - the Dashboard's hero, the setup window's header card, a title card every dialog is given - and close
is filled red under the pointer. gui/SoftChrome.cs is the one place they are made. This holds the sources to it:

* every dialog the window and the advanced page build is a SoftDialog (its ClientSize means what it says once the caption
  is ours) and takes its title card from Soft.DialogBar; no `new Form()` is left;
* the Dashboard and the setup window install the caption in their first card, and every form's window procedure hands
  the frame's messages to it first;
* the buttons a window has are the ones Windows gave it - both of the pair when either box is on, the one that is off
  faint and doing nothing, Close alone when both are off - and section 2 of plans/v0624-stage1-design.md is that table;
* every size is Brand's (LAYOUT caption_*, CAPTION_STROKE); close under the pointer is Palette.Danger;
* a press on the maximise button (HTMAXBUTTON) is never handed to Windows, which would track and paint a button of its own
  there; every button acts through WM_SYSCOMMAND;
* the buttons are never in the Tab order nor given the keyboard; a screen reader hears Windows' own words, read from the
  window menu, with the four fallbacks;
* the window asks for round corners in every theme (DWMWCP_ROUND) and still for the dark border in dark;
* what drags the window is the card and the empty ground - never a tab, a button or the page.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

import guiscan

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted(list((ROOT / "gui").glob("*.cs")) + list((ROOT / "advanced" / "gui").glob("*.cs")))
MADE = re.compile(r"\b(?:var|using \(var)\s+dialog\s*=\s*new (\w+)\(\)")
REACH = 30

# Section 2 of the design: each dialog, by its source and the words of its title, and the buttons it has -
# (minimise shown, minimise on, maximise shown, maximise on).
CLOSE_ONLY = (False, False, False, False)
PAIR_MAXIMISE = (True, False, True, True)
TABLE = {
    ("gui/DashboardActions.cs", 'dialog.Text = "Codex Auto Resume";'): CLOSE_ONLY,
    ("gui/DashboardActions.cs", 'S("timeline.title", "Timeline")'): PAIR_MAXIMISE,
    ("gui/DashboardOwnReport.cs", 'S("ownreport.title"'): PAIR_MAXIMISE,
    ("gui/DashboardTools.cs", 'S("conversation.title"'): CLOSE_ONLY,
    ("gui/DashboardTools.cs", 'S("once.title"'): CLOSE_ONLY,
    ("gui/DashboardTools.cs", 'S("logs.title"'): PAIR_MAXIMISE,
    ("gui/DashboardTools.cs", 'S("check.title"'): PAIR_MAXIMISE,
    ("gui/DashboardVersions.cs", 'S("pick.title"'): PAIR_MAXIMISE,
    ("gui/SettingsHomes.cs", 'S("homes.alias"'): CLOSE_ONLY,
    ("gui/SettingsOwn.cs", "dialog.Text = title;"): CLOSE_ONLY,
    ("advanced/gui/AdvancedEditor.cs", "dialog.Text = title;"): CLOSE_ONLY,
    ("advanced/gui/AdvancedExamples.cs", 'Word("page.example.title"'): CLOSE_ONLY,
    ("advanced/gui/AdvancedFind.cs", 'Word("page.find.title"'): CLOSE_ONLY,
    ("advanced/gui/AdvancedFollow.cs", 'Word("page.follow.title"'): CLOSE_ONLY,
}


def made() -> list:
    """(source, line, the class made, the lines that set the dialog up) of every dialog the sources make."""
    found = []
    for path in SOURCES:
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, 1):
            match = MADE.search(line)
            if match:
                found.append((path.relative_to(ROOT).as_posix(), number, match.group(1), lines[number:number + REACH]))
    return found


def buttons(after: list) -> tuple:
    """The buttons Windows gives the dialog its lines set up, as Chrome.Pair and ChromeHost.Place give them."""
    text = "\n".join(after)
    minimize = "dialog.MinimizeBox = false;" not in text
    maximize = "dialog.MaximizeBox = false;" not in text
    pair = minimize or maximize
    return (pair, minimize, pair, maximize)


class DialogSourceTests(unittest.TestCase):
    def test_every_dialog_is_a_soft_dialog_and_takes_its_title_card(self):
        found = made()
        self.assertEqual(len(found), len(TABLE), "the dialogs of section 2, and no other")
        for source, line, kind, after in found:
            with self.subTest(source=source, line=line):
                self.assertEqual(kind, "SoftDialog", "a dialog's caption is its own (gui/SoftChrome.cs)")
                self.assertTrue(any("Soft.DialogBar(dialog);" in later for later in after))
        for path in SOURCES:
            with self.subTest(path=path.name):
                self.assertNotIn("new Form()", path.read_text(encoding="utf-8"))

    def test_each_dialog_has_the_buttons_windows_gave_it(self):
        seen = set()
        for source, line, _kind, after in made():
            text = "\n".join(after)
            keys = [key for key in TABLE if key[0] == source and key[1] in text]
            with self.subTest(source=source, line=line):
                self.assertEqual(len(keys), 1, "the dialog is one row of section 2's table")
                seen.add(keys[0])
                self.assertEqual(buttons(after), TABLE[keys[0]])
        self.assertEqual(seen, set(TABLE))

    def test_the_title_card_is_made_once_the_dialog_is_and_its_strip_is_docked_first(self):
        bar = guiscan.member_body("Soft", "DialogBar")
        self.assertIn("soft.Titled = true;", bar)
        self.assertIn("dialog.ShowIcon = false;", bar)
        self.assertIn("if (Titled && titleCard == null) BuildTitle();", guiscan.member_body("SoftDialog", "OnHandleCreated"))
        build = guiscan.member_body("SoftDialog", "BuildTitle")
        for part in ("titleGround.Dock = DockStyle.Top;", "Controls.Add(titleGround);",
                     "ClientSize = new Size(ClientSize.Width, ClientSize.Height + grown);",
                     "ChromeHost.Install(this, titleCard, titleGround)", 'Soft.RoleFont("title")', "titleWords.AutoEllipsis = true;",
                     "TextChanged += delegate"):
            self.assertIn(part, build)
        self.assertNotIn("Padding = new Padding", build.replace("titleCard.Padding = new Padding", ""),
                         "no padding of the dialog's: its anchored controls would move with it")

    def test_every_dialog_that_fits_its_height_counts_its_title(self):
        for source, member, type_name in (("gui/SettingsOwn.cs", "BuildOwnValue", "SettingsForm"),
                                          ("advanced/gui/AdvancedEditor.cs", "FitEditor", None),
                                          ("advanced/gui/AdvancedExamples.cs", "FitExample", None)):
            text = (ROOT / source).read_text(encoding="utf-8")
            with self.subTest(source):
                self.assertIn("SoftDialog.TitleRoom(", text)


class WindowSourceTests(unittest.TestCase):
    def test_the_dashboard_and_the_setup_window_install_their_caption_in_their_first_card(self):
        header = guiscan.member_body("SettingsForm", "BuildHeader")
        self.assertIn("chrome = ChromeHost.Install(this, hero, this);", header)
        for dragged in ("chrome.Drag(header);", "chrome.Drag(headline);", "chrome.Drag(detail);", "chrome.Drag(stateDot);"):
            self.assertIn(dragged, header)
        window = guiscan.read("gui/SettingsApp.cs")
        for dragged in ("chrome.Drag(nav);", "chrome.Drag(footer);"):
            self.assertIn(dragged, window)
        self.assertIn("chrome.Scene = dayScene;", guiscan.member_body("SettingsForm", "JoinDayScene"))
        installer = guiscan.read("gui/InstallerWindow.cs")
        self.assertIn("chrome = ChromeHost.Install(this, header, ground);", installer)

    def test_nothing_a_person_acts_on_drags_the_window(self):
        sources = guiscan.read("gui/SettingsApp.cs") + guiscan.read("gui/InstallerWindow.cs") + guiscan.read("gui/SoftChrome.cs")
        dragged = set(re.findall(r"\b(?:chrome|host)\.Drag\((\w+)\);", sources))
        for never in ("startButton", "pageHost", "savebar", "forward", "back", "cancel", "body", "sheet"):
            self.assertNotIn(never, dragged)
        through = guiscan.member_body("DragThrough", "WndProc")
        self.assertIn("Chrome.HTTRANSPARENT", through)
        # A line cut short keeps its tooltip of the whole line.
        self.assertIn("label.AutoEllipsis", guiscan.member_body("DragThrough", "Through"))

    def test_every_form_hands_its_frame_to_the_caption_first(self):
        for type_name, source in (("SettingsForm", "gui/WindowReopen.cs"), ("InstallerWindow", "gui/InstallerWindow.cs"),
                                  ("SoftDialog", "gui/SoftChrome.cs")):
            body = guiscan.member_body(type_name, "WndProc")
            with self.subTest(type_name):
                first = [line.strip() for line in body.splitlines()
                         if line.strip() and not line.strip().startswith(("//", "{", "protected"))][0]
                self.assertEqual(first, "if (chrome != null && chrome.Intercept(ref m, PassOn)) return;")
                self.assertIn("Chrome.WindowSize(clientSize, OwnFrame())", guiscan.member_body(type_name, "SizeFromClientSize"))
                self.assertIn("UpdateBounds(Left, Top, Width, Height, client.Width, client.Height)",
                              guiscan.member_body(type_name, "SetBoundsCore"))

    def test_the_window_asks_for_round_corners_in_every_theme(self):
        title = guiscan.member_body("Soft", "TitleBar")
        self.assertLess(title.index("CornerPreferenceAttribute, ref corner"), title.index("if (!Palette.Dark || form == null) return;"))
        self.assertIn("internal const int CornerPreferenceAttribute = 33, CornerRound = 2;", guiscan.controls())
        self.assertIn("DarkTitleBarAttribute, ref on", title)


class ButtonSourceTests(unittest.TestCase):
    def setUp(self):
        self.chrome = guiscan.read("gui/SoftChrome.cs")

    def test_the_buttons_are_the_ones_the_form_s_properties_ask_for(self):
        place = guiscan.member_body("ChromeHost", "Place")
        for part in ("Chrome.Pair(form.MinimizeBox, form.MaximizeBox)", "MinimizeButton.Visible = pair;",
                     "MaximizeButton.Visible = pair;", "MinimizeButton.Enabled = form.MinimizeBox;",
                     "MaximizeButton.Enabled = form.MaximizeBox;", "CloseButton.Visible = form.ControlBox;"):
            self.assertIn(part, place)
        self.assertIn("return minimizeBox || maximizeBox;", guiscan.member_body("Chrome", "Pair"))

    def test_every_size_is_brand_s(self):
        place = guiscan.member_body("ChromeHost", "Place")
        for size in ("Brand.CaptionButtonW", "Brand.CaptionButtonH", "Brand.CaptionGap", "Brand.CaptionInsetEnd",
                     "Brand.CaptionInsetTop"):
            self.assertIn(size, place)
        glyph = guiscan.member_body("CaptionButton", "Glyph")
        for size in ("Brand.CaptionGlyph", "Brand.CaptionStroke", "Brand.CaptionGlyphCorner"):
            self.assertIn(size, glyph)
        self.assertIn("Math.Max(1f, Soft.PxF(Brand.CaptionStroke))", glyph, "never under a device pixel")
        code = "\n".join(line for line in self.chrome.splitlines() if not line.lstrip().startswith("//"))
        for literal in (" 34", " 26", "1.3"):
            self.assertNotIn("Soft.Px(" + literal.strip() + ")", code)

    def test_close_under_the_pointer_is_danger_and_the_others_a_well(self):
        wanted = guiscan.member_body("CaptionButton", "Wanted")
        self.assertIn("Command == Chrome.SC_CLOSE", wanted)
        self.assertIn("Soft.Mix(Palette.Danger, Palette.Ink, 0.15) : Palette.Danger", wanted, "O3: pressed 15 % toward ink")
        self.assertIn("new SurfaceLook(Palette.Inset, Palette.Inset, Palette.Ink)", wanted)
        self.assertIn("SystemColors.Highlight", wanted, "High Contrast: the person's colours, no red")
        self.assertIn("Soft.WithAlpha(muted, 0.43)", wanted, "the faint one of a pair")
        self.assertIn("Command != Chrome.SC_CLOSE && Palette.Depth", guiscan.member_body("CaptionButton", "OnPaint"))

    def test_a_press_on_the_maximise_button_is_never_handed_to_windows(self):
        intercept = guiscan.member_body("ChromeHost", "Intercept")
        start = intercept.index("case Chrome.WM_NCLBUTTONDOWN:")
        presses = intercept[start:]
        self.assertIn("case Chrome.WM_NCLBUTTONDBLCLK:", presses)
        self.assertIn("case Chrome.WM_NCLBUTTONUP:", presses)
        self.assertNotIn("pass(", presses, "no button message over a button goes on to DefWindowProc")
        self.assertEqual(presses.count("if (!IsButton(code)) return false;"), 2)
        self.assertIn("if (code == Chrome.HTMAXBUTTON) return false;", intercept, "its hover goes on: the snap layouts")
        self.assertIn("return code == Chrome.HTMINBUTTON || code == Chrome.HTMAXBUTTON || code == Chrome.HTCLOSE;",
                      guiscan.member_body("ChromeHost", "IsButton"))
        act = guiscan.member_body("ChromeHost", "Act")
        self.assertIn("PostMessage(form.Handle, Chrome.WM_SYSCOMMAND, (IntPtr)command, IntPtr.Zero);", act)
        self.assertIn("Chrome.SC_RESTORE", act)
        self.assertIn("m.Result = (IntPtr)Chrome.HTTRANSPARENT;", guiscan.member_body("CaptionButton", "WndProc"))

    def test_the_buttons_are_never_in_the_tab_order_and_are_push_buttons_named_in_windows_words(self):
        made = guiscan.member_body("CaptionButton", "CaptionButton")
        self.assertIn("TabStop = false;", made)
        self.assertIn("SetStyle(ControlStyles.Selectable, false);", made)
        self.assertIn("AccessibleRole = AccessibleRole.PushButton;", made)
        names = guiscan.member_body("ChromeHost", "Names")
        self.assertIn("GetSystemMenu(form.Handle, false)", names)
        for command, fallback in (("SC_MINIMIZE", "MinimizeWord"), ("SC_MAXIMIZE", "MaximizeWord"),
                                  ("SC_RESTORE", "RestoreWord"), ("SC_CLOSE", "CloseWord")):
            self.assertIn("Chrome.%s, Chrome.%s" % (command, fallback), names)
        self.assertIn('MinimizeWord = "Minimize", MaximizeWord = "Maximize", RestoreWord = "Restore", CloseWord = "Close"',
                      self.chrome)
        self.assertIn("GetMenuString(menu, command, text, text.Capacity, MF_BYCOMMAND)", guiscan.member_body("ChromeHost", "Word"))

    def test_the_buttons_have_windows_tooltips_and_maximise_the_snap_layouts(self):
        hovered = guiscan.member_body("ChromeHost", "Hovered")
        self.assertIn("if (button == MaximizeButton && Chrome.SnapLayouts) return;", hovered)
        self.assertIn("new SoftTipWindow(", guiscan.member_body("ChromeHost", "ShowTip"))

    def test_the_hit_test_reads_rectangles_kept_since_the_last_layout(self):
        layout = guiscan.member_body("ChromeHost", "Layout")
        self.assertIn("if (!dirty) return layout;", layout)
        self.assertIn("Chrome.Hit(form.PointToClient(screen), Layout())", guiscan.member_body("ChromeHost", "Intercept"))


if __name__ == "__main__":
    unittest.main()
