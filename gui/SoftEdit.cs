// Codex Auto Resume - a text box's right-click menu, in the window's own material (v0.6.24).
//
// Until v0.6.24 a right-click in a text box opened Windows' own edit menu: a square grey Win32 menu over a window whose
// every other menu is a card (SoftMenu, gui/SoftMenu.cs). The owner asked for ours (2026-11-13), keeping Windows' words.
// Every editable box of both editions is a SoftTextArea's Box or the edit part of a SoftNumber (gui/SoftFields.cs), and
// both hand it to EditMenu.Attach: a small NativeWindow on the box's handle takes WM_CONTEXTMENU and does not pass it
// on, so Windows' menu never opens, and opens a SoftMenu with the six items Windows' menu has, in its order - Undo |
// Cut, Copy, Paste, Delete | Select all.
//
// The words are Windows' own, exactly as it shows them, mnemonic and all ("&Undo" in English, the word and "(&U)" in Korean): user32's own edit
// menu, read once on the first right-click of the process (never at start) in the Windows display language. The
// resource's number is not documented, so it is not trusted: the menu taken is the one whose items carry the six
// commands, and each word is taken by its command, never by its position. If no such menu can be read the English
// words stand in. Each item does what Windows' does: the edit control's own message, sent to the box, so its undo,
// its limits and TextChanged behave as typing does; and each is usable when Windows' is (States).
//
// Dropped on purpose (owner): right-to-left reading order, Unicode control characters, IME reconversion.

using System;
using System.Drawing;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

namespace CodexAutoResume
{
    /// A text box's right-click menu: our SoftMenu with Windows' six edit commands and Windows' words for them.
    internal static class EditMenu
    {
        internal const int WM_CONTEXTMENU = 0x007B;
        internal const int EM_UNDO = 0x00C7, WM_UNDO = 0x0304, WM_CUT = 0x0300, WM_COPY = 0x0301, WM_PASTE = 0x0302,
                           WM_CLEAR = 0x0303, EM_SETSEL = 0x00B1;
        private const int EM_GETSEL = 0x00B0, EM_CANUNDO = 0x00C6, EM_POSFROMCHAR = 0x00D6;
        private const int GWL_STYLE = -16, ES_PASSWORD = 0x0020, ES_READONLY = 0x0800;
        private const uint CF_UNICODETEXT = 13;
        private const uint MF_BYPOSITION = 0x0400;
        private const int RT_MENU = 4;
        private const uint RESOURCE_ENUM_LN = 0x0001, RESOURCE_ENUM_MUI = 0x0002;

        /// The six commands, in the order Windows' menu has them: Undo, Cut, Copy, Paste, Delete, Select all.
        /// Filled one by one: a constant array initializer makes the compiler name a class at random, and the build
        /// would no longer be reproducible (build/normalize_pe.py refuses it).
        internal static readonly int[] Commands = Six();

        private static int[] Six()
        {
            var six = new int[6];
            six[0] = EM_UNDO; six[1] = WM_CUT; six[2] = WM_COPY; six[3] = WM_PASTE; six[4] = WM_CLEAR; six[5] = EM_SETSEL;
            return six;
        }

        /// Whether a separator comes before the item: before Cut and before Select all, as in Windows' menu.
        internal static bool RuleBefore(int item) { return item == 1 || item == 5; }

        /// The English words, as Windows shows them, for when user32's menu cannot be read.
        internal static readonly string[] Fallback = { "&Undo", "Cu&t", "&Copy", "&Paste", "&Delete", "Select &All" };

        [DllImport("user32.dll")]
        private static extern IntPtr SendMessage(IntPtr window, int message, IntPtr wParam, IntPtr lParam);

        [DllImport("user32.dll")]
        private static extern IntPtr SendMessage(IntPtr window, int message, out int wParam, out int lParam);

        [DllImport("user32.dll", EntryPoint = "GetWindowLongW")]
        private static extern int GetWindowLong(IntPtr window, int index);

        [DllImport("user32.dll")]
        private static extern int GetWindowTextLengthW(IntPtr window);

        [DllImport("user32.dll")]
        private static extern bool IsClipboardFormatAvailable(uint format);

        [DllImport("user32.dll")]
        private static extern bool GetCaretPos(out Point point);

        [DllImport("user32.dll")]
        private static extern IntPtr GetFocus();

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr GetModuleHandleW(string name);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern IntPtr LoadMenuW(IntPtr module, IntPtr name);

        [DllImport("user32.dll")]
        private static extern bool DestroyMenu(IntPtr menu);

        [DllImport("user32.dll")]
        private static extern int GetMenuItemCount(IntPtr menu);

        [DllImport("user32.dll")]
        private static extern IntPtr GetSubMenu(IntPtr menu, int position);

        [DllImport("user32.dll")]
        private static extern uint GetMenuItemID(IntPtr menu, int position);

        [DllImport("user32.dll", CharSet = CharSet.Unicode)]
        private static extern int GetMenuStringW(IntPtr menu, uint item, StringBuilder text, int max, uint flags);

        private delegate bool EnumName(IntPtr module, IntPtr type, IntPtr name, IntPtr param);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        private static extern bool EnumResourceNamesExW(IntPtr module, IntPtr type, EnumName callback, IntPtr param,
                                                        uint flags, ushort language);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
        private static extern bool EnumResourceNamesW(IntPtr module, IntPtr type, EnumName callback, IntPtr param);

        private static readonly ConditionalWeakTable<TextBoxBase, Hook> hooks = new ConditionalWeakTable<TextBoxBase, Hook>();

        /// Gives the box our menu in place of Windows'. Once per box; it follows the box's handle when it is made anew.
        internal static void Attach(TextBoxBase box)
        {
            if (box == null) return;
            Hook hook;
            if (hooks.TryGetValue(box, out hook)) return;
            hooks.Add(box, new Hook(box));
        }

        /// Whether the box's menu is ours (for the tests).
        internal static bool Attached(TextBoxBase box)
        {
            Hook hook;
            return box != null && hooks.TryGetValue(box, out hook) && hook.Handle != IntPtr.Zero;
        }

        /// What a right-click or the menu key does: opens the menu at a point on the screen. A field so the tests can
        /// see where without a menu opening.
        internal static Action<TextBoxBase, Point> Opening = Open;

        // ---- the words ----

        private static string[] words;

        /// Windows' six words, read from user32 on the first call and kept; the English ones if they cannot be read.
        internal static string[] Words()
        {
            if (words == null)
            {
                string[] read = null;
                try { read = Read(); } catch { read = null; }
                words = read ?? (string[])Fallback.Clone();
            }
            return words;
        }

        /// Whether the words came from Windows (for the tests and the measurement).
        internal static bool FromWindows { get { Words(); return fromWindows; } }

        private static bool fromWindows;

        private static string[] Read()
        {
            IntPtr user32 = GetModuleHandleW("user32.dll");
            if (user32 == IntPtr.Zero) return null;
            string[] found = null;
            EnumName each = delegate(IntPtr module, IntPtr type, IntPtr name, IntPtr param)
            {
                IntPtr menu = LoadMenuW(module, name);
                if (menu == IntPtr.Zero) return true;
                try { found = Match(menu, 0); }
                finally { DestroyMenu(menu); }
                return found == null;
            };
            bool listed = false;
            try { listed = EnumResourceNamesExW(user32, (IntPtr)RT_MENU, each, IntPtr.Zero, RESOURCE_ENUM_LN | RESOURCE_ENUM_MUI, 0); }
            catch (EntryPointNotFoundException) { listed = false; }
            if (found == null && !listed) EnumResourceNamesW(user32, (IntPtr)RT_MENU, each, IntPtr.Zero);
            GC.KeepAlive(each);
            fromWindows = found != null;
            return found;
        }

        /// The six words if this menu, or one of its submenus, has an item for each of the six commands; null if not.
        private static string[] Match(IntPtr menu, int depth)
        {
            int count = GetMenuItemCount(menu);
            if (count <= 0) return null;
            var mine = new string[Commands.Length];
            for (int position = 0; position < count; position++)
            {
                IntPtr sub = GetSubMenu(menu, position);
                if (sub != IntPtr.Zero)
                {
                    if (depth < 2)
                    {
                        string[] inner = Match(sub, depth + 1);
                        if (inner != null) return inner;
                    }
                    continue;
                }
                uint id = GetMenuItemID(menu, position);
                int slot = Slot((int)id);
                if (slot < 0 || mine[slot] != null) continue;
                var text = new StringBuilder(256);
                if (GetMenuStringW(menu, (uint)position, text, text.Capacity, MF_BYPOSITION) > 0) mine[slot] = text.ToString();
            }
            foreach (string word in mine) if (string.IsNullOrEmpty(word)) return null;
            return mine;
        }

        /// Which of the six a menu item's id is: Undo is EM_UNDO or WM_UNDO, the others their one message.
        internal static int Slot(int id)
        {
            if (id == WM_UNDO) return 0;
            return Array.IndexOf(Commands, id);
        }

        // ---- what can be used ----

        /// Which of the six can be used, in Commands' order, as Windows' edit menu decides it: Undo while there is
        /// something to undo; Cut and Delete while text is selected; Copy too, unless the box hides its text; Paste while
        /// the clipboard holds text; Select all unless all of it already is. A read-only box offers only Copy and
        /// Select all, a password box neither Cut nor Copy.
        internal static bool[] States(bool canUndo, bool readOnly, bool password, int selectionStart, int selectionLength,
                                      int textLength, bool clipboardText)
        {
            bool selected = selectionLength > 0;
            return new[]
            {
                canUndo && !readOnly,
                selected && !readOnly && !password,
                selected && !password,
                clipboardText && !readOnly,
                selected && !readOnly,
                textLength > 0 && !(selectionStart == 0 && selectionLength >= textLength),
            };
        }

        /// The box's own answers to States' questions. Asking the clipboard whether it holds text never reads the text.
        internal static bool[] StatesOf(TextBoxBase box)
        {
            IntPtr handle = box.Handle;
            int start, end;
            SendMessage(handle, EM_GETSEL, out start, out end);
            int style = GetWindowLong(handle, GWL_STYLE);
            bool canUndo = SendMessage(handle, EM_CANUNDO, IntPtr.Zero, IntPtr.Zero) != IntPtr.Zero;
            return States(canUndo, (style & ES_READONLY) != 0, (style & ES_PASSWORD) != 0, Math.Min(start, end),
                          Math.Abs(end - start), GetWindowTextLengthW(handle), IsClipboardFormatAvailable(CF_UNICODETEXT));
        }

        // ---- the menu ----

        /// The menu's items for this box: the six with Windows' words and Windows' enablement, and the two lines.
        internal static ToolStripItem[] Build(TextBoxBase box)
        {
            string[] said = Words();
            bool[] usable = StatesOf(box);
            var items = new ToolStripItem[Commands.Length + 2];
            int at = 0;
            for (int i = 0; i < Commands.Length; i++)
            {
                if (RuleBefore(i)) items[at++] = new ToolStripSeparator();
                string word = said[i];
                int tab = word.IndexOf('\t');
                var item = new ToolStripMenuItem(tab >= 0 ? word.Substring(0, tab) : word);
                if (tab >= 0) item.ShortcutKeyDisplayString = word.Substring(tab + 1);
                item.Enabled = usable[i];
                int command = Commands[i];
                item.Tag = command;
                item.Click += delegate { Run(box, command); };
                items[at++] = item;
            }
            return items;
        }

        /// One command, as Windows' menu runs it: the edit control's own message, sent to the box.
        internal static void Run(TextBoxBase box, int command)
        {
            if (box == null || box.IsDisposed || !box.IsHandleCreated) return;
            if (command == EM_SETSEL) SendMessage(box.Handle, EM_SETSEL, IntPtr.Zero, (IntPtr)(-1));
            else SendMessage(box.Handle, command, IntPtr.Zero, IntPtr.Zero);
        }

        /// Where the menu opens: where the pointer was, or for Shift+F10 and the menu key (-1, -1) below the caret,
        /// inside the box.
        internal static Point At(TextBoxBase box, IntPtr lParam)
        {
            long packed = lParam.ToInt64();
            int x = unchecked((short)(packed & 0xFFFF)), y = unchecked((short)((packed >> 16) & 0xFFFF));
            if (x != -1 || y != -1) return new Point(x, y);
            Point caret = Point.Empty;
            bool known = false;
            if (GetFocus() == box.Handle) known = GetCaretPos(out caret);
            if (!known)
            {
                int start, end;
                SendMessage(box.Handle, EM_GETSEL, out start, out end);
                long place = SendMessage(box.Handle, EM_POSFROMCHAR, (IntPtr)end, IntPtr.Zero).ToInt64();
                if (place != -1)
                {
                    caret = new Point(unchecked((short)(place & 0xFFFF)), unchecked((short)((place >> 16) & 0xFFFF)));
                    known = true;
                }
                else if (end > 0 && end <= box.TextLength)
                {
                    // The caret after the last character: EM_POSFROMCHAR has no place for it (it answers -1), so the
                    // menu went to the box's corner (v0.6.24 review). Take the last character's place and step past
                    // it - past its width, or to the next line's start after a line break.
                    long last = SendMessage(box.Handle, EM_POSFROMCHAR, (IntPtr)(end - 1), IntPtr.Zero).ToInt64();
                    if (last != -1)
                    {
                        caret = new Point(unchecked((short)(last & 0xFFFF)), unchecked((short)((last >> 16) & 0xFFFF)));
                        char after = box.Text[end - 1];
                        if (after == '\n') caret = new Point(0, caret.Y + box.Font.Height);
                        else caret.X += TextRenderer.MeasureText(after.ToString(), box.Font, Size.Empty,
                                                                 TextFormatFlags.NoPadding).Width;
                        known = true;
                    }
                }
            }
            if (!known) caret = Point.Empty;
            Size room = box.ClientSize;
            int below = caret.Y + box.Font.Height;
            caret = new Point(Math.Max(0, Math.Min(caret.X, room.Width - 1)), Math.Max(0, Math.Min(below, room.Height - 1)));
            return box.PointToScreen(caret);
        }

        /// Opens the menu over the box at a point on the screen, and lets it go when it closes.
        internal static void Open(TextBoxBase box, Point screen)
        {
            if (box.CanFocus && !box.Focused) box.Focus();
            var menu = new SoftMenu();
            Form form = box.FindForm();
            if (form != null) menu.Font = form.Font;            // the window's face, as its other menus have it
            menu.Items.AddRange(Build(box));
            menu.Closed += delegate
            {
                if (box.IsHandleCreated && !box.IsDisposed) box.BeginInvoke((MethodInvoker)delegate { menu.Dispose(); });
                else menu.Dispose();
            };
            menu.Show(box, box.PointToClient(screen));
        }

        /// Takes the box's WM_CONTEXTMENU and opens ours; Windows' menu never sees it.
        private sealed class Hook : NativeWindow
        {
            private readonly TextBoxBase box;

            internal Hook(TextBoxBase box)
            {
                this.box = box;
                box.HandleCreated += delegate { if (Handle == IntPtr.Zero) AssignHandle(box.Handle); };
                box.HandleDestroyed += delegate { ReleaseHandle(); };
                box.Disposed += delegate { ReleaseHandle(); };
                if (box.IsHandleCreated) AssignHandle(box.Handle);
            }

            protected override void WndProc(ref Message m)
            {
                if (m.Msg == WM_CONTEXTMENU)
                {
                    try
                    {
                        Opening(box, At(box, m.LParam));
                        m.Result = IntPtr.Zero;
                        return;
                    }
                    catch
                    {
                        // Ours could not open: Windows' own is better than none.
                    }
                }
                base.WndProc(ref m);
            }
        }
    }
}
