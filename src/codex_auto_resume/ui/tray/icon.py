"""The icon itself: one thread, one hidden window, and the life of both.

Everything Windows says to this product's notification-area icon arrives at `_wndproc` below
and leaves as a call into one of the mixins beside it. `Tray` is composed here rather than in
the package's `__init__`, so that the front holds no code of its own.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os
import threading
import time
from pathlib import Path

from .animation import AnimationMixin
from .cards import CardsMixin
from .clicks import ClicksMixin
from .menu import APP_MODE_DEFAULT, MenuMixin
from .model import snapshot_from  # noqa: F401
from .motion import build_icon_frames
from .stored import StoredMixin
from .win32 import (CALLBACK,
                    IDI_APPLICATION,
                    IMAGE_ICON,
                    LR_LOADFROMFILE,
                    MSG,
                    NIF_ICON,
                    NIF_MESSAGE,
                    NIF_SHOWTIP,
                    NIF_TIP,
                    NIM_ADD,
                    NIM_DELETE,
                    NIM_MODIFY,
                    NIM_SETVERSION,
                    NIN_KEYSELECT,
                    NIN_SELECT,
                    NOTIFYICONDATAW,
                    NOTIFYICON_VERSION_4,
                    NOTIFY_FOR_THIS_SESSION,
                    SM_CXSMICON,
                    SM_CYSMICON,
                    TIMER_FRAME,
                    TIMER_TICK,
                    WM_CLOSE,
                    WM_CONTEXTMENU,
                    WM_DESTROY,
                    WM_LBUTTONDBLCLK,
                    WM_LBUTTONUP,
                    WM_RBUTTONUP,
                    WM_TIMER,
                    WM_TRAY_FRAMES,
                    WM_USER,
                    WM_WTSSESSION_CHANGE,
                    WTS_CONSOLE_CONNECT,
                    WTS_CONSOLE_DISCONNECT,
                    WTS_REMOTE_CONNECT,
                    WTS_REMOTE_DISCONNECT,
                    WTS_SESSION_LOCK,
                    WTS_SESSION_UNLOCK,
                    _dll)
from .words import tooltip, tooltip_parts
from ...win.dll import LRESULT, WNDCLASSW, WNDPROC
from ...win.sync import DemoEvent


# v0.6.24: with NIF_SHOWTIP left out under version 4, the shell draws no tooltip and says instead when the pointer rests
# on the icon and when it leaves (shellapi.h: WM_USER + 6 and + 7); the icon shows its own card then (tipcard.py).
NIN_POPUPOPEN, NIN_POPUPCLOSE = WM_USER + 6, WM_USER + 7
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_RBUTTONDOWN = 0x0200, 0x0201, 0x0204
# Until the shell has once said the pointer rests on the icon (NIN_POPUPOPEN), each visit of the pointer is timed from its
# first move (TIMER_TIP): TIP_PROBE_S on, with the pointer still on the icon - resting on it, or moving over it within the
# last TIP_EPISODE_GAP_S - and no word, the visit was a silent one. After TIP_SILENT_VISITS of them this Windows is taken
# to send none with its tooltip off, and its own tooltip comes back - the standard tooltip, never none - until the shell
# says the word after all, which turns the card back on at once. Once it has said it, no visit is timed again.
TIP_PROBE_S, TIP_EPISODE_GAP_S, TIP_SILENT_VISITS = 2.0, 1.0, 2
TIMER_TIP = 3


class Tray(MenuMixin, StoredMixin, CardsMixin, ClicksMixin, AnimationMixin):
    """One icon, one hidden window, one thread - and, once clicked, one popup on it."""


    def __init__(self, *, icon_path=None, strings=None, on_open=None, on_toggle=None, on_stop=None,
                 on_pending=None, log=None, control=None, pending_source=None, on_dashboard=None,
                 inbox=None, on_notice_action=None, on_notice_complete=None, demo_name=None, on_demo=None, days=False,
                 edition=None):
        self.icon_path = Path(icon_path) if icon_path else None
        self.strings = strings or {}
        # v0.6.11: the edition that runs (edition.shown), which the tooltip's title names (v0.6.14: if advanced).
        self.edition = edition
        self.on_open, self.on_toggle, self.on_stop = on_open, on_toggle, on_stop
        self.on_pending = on_pending
        self.log = log or (lambda *args: None)
        # The popup's only way to act: the shared control layer, plus the read-only source
        # `list_pending` uses to attach conversation names. Without a control there is no
        # popup, and a double click opens the Dashboard as it did before v0.6.3.
        self.control = control
        self.pending_source = pending_source
        self.on_dashboard = on_dashboard
        self._snapshot = {}
        self._lock = threading.Lock()
        self._thread = None
        self._hwnd = None
        self._ready = threading.Event()
        self._proc = None           # keeps the callback alive for the window's life
        self._icon = None
        self._icon_owned = False
        self._failed = False        # the icon shows a failure nobody has seen (_failure_unseen)
        self._unconfirmed = False   # v0.6.20: or, in amber, a sending nobody has confirmed (_unconfirmed_unseen)
        self._shown_icon = None
        self._last_tip = None
        self._taskbar_created = None
        self._class_name = None
        self._version4 = False
        self._popup = None
        self._popup_failed = False
        self._settings_stamp = None   # the settings file as last read: (mtime, size), or None
        self._settings_values = None
        self._menu_mode = APP_MODE_DEFAULT   # what this process's menus were last asked to be
        self._menu_theming = True            # False once Windows could not be asked
        # v0.6.20: the menu drawn in the product's design (menu.py): made on the first right click, False once it
        # could not be made or shown - Windows' own menu from then on.
        self._menu_drawn = None
        # v0.6.5: the icon's motion. Until its frame table is built (off this thread) the icon is
        # the .ico, and if the table cannot be built it stays that way. Once it is, every icon shown is one composed frame, made into
        # an HICON as it is shown and destroyed once the shell holds the next: two at most.
        self.days = days              # only the watcher's own icon: nothing else may depend on the date
        self._frames = None           # IconFrames once built; False when it could not be
        self._frames_result = None    # what the building thread left: (frames, reason)
        self._frames_pending = False
        self._frame_icon = None       # the composed frame on show, if any
        self._frame_key = None
        self._icon_state = None
        self._state_since = time.monotonic()
        self._epoch = time.monotonic()      # the motion's clock: breaths and turns count from here
        self._motion_allowed = False
        self._motion_ms = None              # the frame timer's interval while it runs
        self._session_locked = False
        self._session_away = False
        self._session_watch = False
        self._motion_read_failed = False    # said once until the settings file can be read again
        self._placement = None              # IconPlacement once the icon has something to move
        # v0.6.5: the notification card. With an inbox, this thread hosts the cards once its window
        # exists (notice_window.CardStack attaches itself to the inbox); a card's button calls
        # `on_notice_action(uri)` and each notice the stack took is ended by
        # `on_notice_complete(notice, shown)`, both on worker threads. No inbox, or a stack that
        # could not be made: no card, and every notification stays today's toast.
        self.inbox = inbox
        self.on_notice_action = on_notice_action
        self.on_notice_complete = on_notice_complete
        self._cards = None
        # v0.6.11: Show me what happens. The demo event this icon makes for its state folder and looks
        # at once a second (win/sync.py DemoEvent); signalled, `on_demo()` draws one made-up card.
        self.demo_name, self.on_demo = demo_name, on_demo
        self._demo = None
        # v0.6.24: the icon's own tooltip card (tipcard.TipCard): None until the pointer first rests on the icon, False
        # once it could not be made or shown - Windows' own tooltip from then on (NIF_SHOWTIP, _notify). `_tip_heard`: the
        # shell has said NIN_POPUPOPEN at least once; `_tip_moves`: (first, last) move of the visit being timed while it
        # has not; `_tip_silent`: how many visits went by with no word; `_tip_fallback`: Windows' tooltip is back because of
        # them (until the word comes).
        self._tip = None
        self._tip_heard = False
        self._tip_moves = None
        self._tip_silent = 0
        self._tip_fallback = False

    # ----------------------------------------------------------------- public
    def start(self) -> bool:
        if os.name != "nt":
            return False
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)
        self._thread.start()
        return self._ready.wait(5) and self._hwnd is not None

    def update(self, snapshot: dict) -> None:
        with self._lock:
            self._snapshot = dict(snapshot)

    def set_strings(self, strings: dict) -> None:
        """Adopt a new vocabulary, after the Interface language changed."""
        with self._lock:
            self.strings = dict(strings or {})
            # Forget the last tooltip so the next tick rewrites it even if the numbers in
            # it have not moved.
            self._last_tip = None
        popup = self._popup
        if popup is not None:
            popup.set_strings(strings)

    def stop(self) -> None:
        if self._hwnd:
            _dll("user32").PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        if self._thread is not None:
            self._thread.join(5)

    # ---------------------------------------------------------------- window
    def _run(self):
        try:
            self._create()
        except Exception as exc:          # a missing tray must never stop the watcher
            self.log("tray unavailable (%s)" % type(exc).__name__)
            self._ready.set()
            return
        self._ready.set()
        user32 = _dll("user32")
        message = MSG()
        while user32.GetMessageW(C.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(C.byref(message))
            user32.DispatchMessageW(C.byref(message))
        # The class name is this icon's own; free it so the next icon can register.
        user32.UnregisterClassW.argtypes = [W.LPCWSTR, W.HINSTANCE]
        user32.UnregisterClassW(self._class_name, _dll("kernel32").GetModuleHandleW(None))

    def _create(self):
        user32, kernel32 = _dll("user32"), _dll("kernel32")
        user32.DefWindowProcW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        user32.CreateWindowExW.restype = W.HWND
        user32.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_int, C.c_int,
                                           C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, W.LPVOID]
        user32.LoadImageW.restype = W.HANDLE
        user32.LoadImageW.argtypes = [W.HINSTANCE, W.LPCWSTR, W.UINT, C.c_int, C.c_int, W.UINT]
        user32.LoadIconW.restype = W.HICON
        user32.LoadIconW.argtypes = [W.HINSTANCE, W.LPVOID]
        user32.DestroyIcon.argtypes = [W.HICON]
        user32.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        user32.TrackPopupMenu.argtypes = [W.HMENU, W.UINT, C.c_int, C.c_int, C.c_int, W.HWND, W.LPVOID]
        user32.AppendMenuW.argtypes = [W.HMENU, W.UINT, C.c_size_t, W.LPCWSTR]
        user32.CreatePopupMenu.restype = W.HMENU
        user32.DestroyMenu.argtypes = [W.HMENU]
        user32.SetTimer.argtypes = [W.HWND, C.c_size_t, W.UINT, W.LPVOID]
        user32.KillTimer.argtypes = [W.HWND, C.c_size_t]
        user32.RegisterWindowMessageW.restype = W.UINT
        _dll("shell32").Shell_NotifyIconW.argtypes = [W.DWORD, C.POINTER(NOTIFYICONDATAW)]
        kernel32.GetModuleHandleW.restype = W.HMODULE
        instance = kernel32.GetModuleHandleW(None)
        self._proc = WNDPROC(self._wndproc)
        klass = WNDCLASSW()
        klass.lpfnWndProc = self._proc
        klass.hInstance = instance
        # Unique per icon, not per process: an icon started after another one in the
        # same process must not collide with a class the first one registered.
        self._class_name = "CodexAutoResumeTray-%d-%d" % (os.getpid(), id(self))
        klass.lpszClassName = self._class_name
        if not user32.RegisterClassW(C.byref(klass)):
            raise OSError("RegisterClassW")
        # A hidden top-level window, not a message-only one: only a real top-level
        # window hears "TaskbarCreated", which is how the icon comes back after Explorer
        # restarts.
        self._hwnd = user32.CreateWindowExW(0, klass.lpszClassName, "Codex Auto Resume", 0,
                                            0, 0, 0, 0, None, None, instance, None)
        if not self._hwnd:
            raise OSError("CreateWindowExW")
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self._icon = self._load_icon()
        self._shown_icon = self._icon
        self._notify(NIM_ADD)
        self._set_version()
        self._host_cards()
        self._demo = self._open_demo()
        user32.SetTimer(self._hwnd, TIMER_TICK, 1000, None)
        self._watch_session()
        if self._icon_owned:
            # Only for our own mark: a missing .ico keeps Windows' generic icon, unmoved.
            self._build_frames_later(user32.GetSystemMetrics(SM_CXSMICON))



    def _open_demo(self):
        """The demo event, made by this icon; None without a demo, or when it cannot be made (one a
        lower-integrity process made first is refused, as the wake event's is)."""
        if not self.demo_name or self.on_demo is None:
            return None
        try:
            return DemoEvent(self.demo_name).__enter__()
        except Exception as exc:
            self.log("demo unavailable (%s)" % type(exc).__name__)
            return None

    def _look_for_demo(self):
        if self._demo is not None and self._demo.taken():
            try:
                self.on_demo()
            except Exception as exc:
                self.log("demo failed (%s)" % type(exc).__name__)

    def _load_icon(self):
        user32 = _dll("user32")
        width, height = user32.GetSystemMetrics(SM_CXSMICON), user32.GetSystemMetrics(SM_CYSMICON)
        if self.icon_path and self.icon_path.is_file():
            handle = user32.LoadImageW(None, str(self.icon_path), IMAGE_ICON, width, height, LR_LOADFROMFILE)
            if handle:
                self._icon_owned = True
                return handle
        self._icon_owned = False            # a shared system icon is never destroyed
        return user32.LoadIconW(None, C.c_void_p(IDI_APPLICATION))

    def _data(self, flags):
        data = NOTIFYICONDATAW()
        data.cbSize = C.sizeof(NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        data.uFlags = flags
        data.uCallbackMessage = CALLBACK
        data.hIcon = self._shown_icon or self._icon
        data.szTip = tooltip(self._shown(), self.strings, time.time(), self.edition)
        return data

    def _shown(self) -> dict:
        """The last tick's snapshot as the icon shows it: with whether a failure nobody has seen is on it."""
        with self._lock:
            snapshot = dict(self._snapshot)
        snapshot["failed"] = self._failed
        snapshot["unconfirmed"] = self._unconfirmed
        return snapshot

    def _notify(self, action):
        # NIF_SHOWTIP: under version 4 the shell hides the standard tooltip unless asked - and since v0.6.24 it is not
        # asked while the icon's own card can be shown (_tip_shows), which the shell's NIN_POPUPOPEN calls for. szTip is
        # the whole tooltip either way: what a screen reader and Windows' own surfaces read.
        flags = NIF_MESSAGE | NIF_ICON | NIF_TIP | (0 if self._tip_shows() else NIF_SHOWTIP)
        data = self._data(flags)
        self._last_tip = data.szTip
        return _dll("shell32").Shell_NotifyIconW(action, C.byref(data))

    def _set_version(self):
        data = NOTIFYICONDATAW()
        data.cbSize = C.sizeof(NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        data.uVersion = NOTIFYICON_VERSION_4
        self._version4 = bool(_dll("shell32").Shell_NotifyIconW(NIM_SETVERSION, C.byref(data)))
        if self._tip_shows():
            self._notify(NIM_MODIFY)            # the icon was added with Windows' tooltip, before the version was known

    # ----------------------------------------------------------------- the tooltip card (v0.6.24)
    def _tip_shows(self) -> bool:
        """Whether hovering shows the icon's own card rather than Windows' tooltip: only under version 4, whose shell says
        when the pointer rests on the icon, only while the card has not failed, and not while the shell has been silent."""
        return (bool(getattr(self, "_version4", False)) and getattr(self, "_tip", None) is not False
                and not getattr(self, "_tip_fallback", False))

    def _tip_content(self):
        """What the card shows, read on its own thread each time it is drawn: (tooltip_parts, the snapshot, the catalog)."""
        with self._lock:
            strings = dict(self.strings)
        snapshot = self._shown()
        return tooltip_parts(snapshot, strings, time.time(), self.edition), snapshot, strings

    def _show_tip(self, wparam):
        """NIN_POPUPOPEN: the card beside the icon, at the shell's anchor point (GET_X_LPARAM / GET_Y_LPARAM of wParam) -
        not over the popup or the menu, which say more."""
        self._tip_heard, self._tip_moves, self._tip_silent = True, None, 0
        if self._hwnd:
            _dll("user32").KillTimer(self._hwnd, TIMER_TIP)
        if self._tip_fallback:
            self._tip_fallback = False           # the shell does say it: the card again, and Windows' tooltip off
            self._notify(NIM_MODIFY)
        if not self._tip_shows():
            return
        popup, menu = self._popup, self._menu_drawn
        if (popup is not None and popup.visible) or (menu and menu.visible):
            return
        point = (C.c_short(wparam & 0xFFFF).value, C.c_short((wparam >> 16) & 0xFFFF).value)
        try:
            if self._tip is None:
                from .tipcard import TipCard
                self._tip = TipCard(content=self._tip_content, held=self._popup_held, log=self.log, days=self.days)
            from .. import popup as tray_popup
            self._tip.show(icon=lambda: tray_popup.icon_rect(self._hwnd, 1), point=point)
        except Exception as exc:
            self._tip_gone("tray tip card unavailable (%s)" % type(exc).__name__)

    def _hide_tip(self, at_once=True):
        """The card hidden: at once for a click, the menu, the popup, a lock; fading (`at_once` False) as the pointer leaves."""
        tip = getattr(self, "_tip", None)
        if not tip:
            return
        try:
            tip.hide(at_once)
        except Exception as exc:
            self._tip_gone("tray tip card failed (%s)" % type(exc).__name__)

    def _tip_moved(self):
        """The pointer moved over the icon. Until the shell has once said it rests there, a visit's first move starts its
        timer (TIMER_TIP, TIP_PROBE_S); a resting pointer sends no moves, so the timer, not the moves, decides."""
        if self._tip_heard or not self._tip_shows() or not self._hwnd:
            return
        now = time.monotonic()
        if self._tip_moves is None:
            self._tip_moves = (now, now)
            _dll("user32").SetTimer(self._hwnd, TIMER_TIP, int(TIP_PROBE_S * 1000), None)
        else:
            self._tip_moves = (self._tip_moves[0], now)

    def _tip_probe(self):
        """A visit's TIP_PROBE_S are up with no word from the shell. It was a silent visit if the pointer is still on the
        icon - resting on it, or moving over it a moment ago; a pointer that only passed by asked for no tooltip. After
        TIP_SILENT_VISITS silent visits, Windows' own tooltip comes back (_tip_fallback)."""
        if self._hwnd:
            _dll("user32").KillTimer(self._hwnd, TIMER_TIP)
        moves, self._tip_moves = self._tip_moves, None
        if self._tip_heard or moves is None or not self._tip_shows():
            return
        if not (time.monotonic() - moves[1] < TIP_EPISODE_GAP_S or self._pointer_on_icon()):
            return
        self._tip_silent += 1
        if self._tip_silent >= TIP_SILENT_VISITS:
            self.log("tray tip card waits: no hover word from the shell, Windows' tooltip meanwhile")
            self._tip_fallback = True
            self._notify(NIM_MODIFY)

    def _pointer_on_icon(self) -> bool:
        """Whether the pointer is on the icon's rectangle, both read in per-monitor pixels; no when either cannot be read."""
        from .. import popup as tray_popup
        try:
            with tray_popup._PerMonitorDpi():
                rect = tray_popup.icon_rect(self._hwnd, 1)
                spot = W.POINT()
                _dll("user32").GetCursorPos(C.byref(spot))
        except Exception:
            return False
        return bool(rect) and rect[0] <= spot.x < rect[2] and rect[1] <= spot.y < rect[3]

    def _tip_gone(self, why):
        """The card cannot be used: let it go, and give Windows' own tooltip back for the rest of the icon's life."""
        self.log(why)
        tip, self._tip = self._tip, False
        if tip:
            try:
                tip.destroy()
            except Exception:
                pass
        if self._hwnd:
            self._notify(NIM_MODIFY)

    def _refresh(self):
        with self._lock:
            snapshot = dict(self._snapshot)
        self._failed = self._failure_unseen(snapshot)
        self._unconfirmed = self._unconfirmed_unseen(snapshot)
        snapshot["failed"] = self._failed
        snapshot["unconfirmed"] = self._unconfirmed
        text = tooltip(snapshot, self.strings, time.time(), self.edition)
        changed, replaced = False, []
        if self._frames:
            self._follow_the_day(self._frames.size)
            self._observe(snapshot)
            changed, replaced = self._frame_for(time.monotonic())
        if text != self._last_tip or changed:
            self._notify(NIM_MODIFY)
        for handle in replaced:
            if handle:
                _dll("user32").DestroyIcon(handle)      # only after the shell holds the new one
        self._sync_motion()



    def _watch_session(self):
        """Hear when the session is locked or disconnected: nobody sees the icon move then."""
        try:
            wts = _dll("wtsapi32")
            wts.WTSRegisterSessionNotification.argtypes = [W.HWND, W.DWORD]
            wts.WTSRegisterSessionNotification.restype = W.BOOL
            self._session_watch = bool(wts.WTSRegisterSessionNotification(self._hwnd, NOTIFY_FOR_THIS_SESSION))
        except Exception:
            self._session_watch = False           # then the lock is simply not known; nothing else changes

    def _session_changed(self, event):
        if event == WTS_SESSION_LOCK:
            self._session_locked = True
        elif event == WTS_SESSION_UNLOCK:
            self._session_locked = False
        elif event in (WTS_CONSOLE_DISCONNECT, WTS_REMOTE_DISCONNECT):
            self._session_away = True
        elif event in (WTS_CONSOLE_CONNECT, WTS_REMOTE_CONNECT):
            self._session_away = False
        else:
            return
        if self._session_locked or self._session_away:
            self._hide_tip()                     # nobody is at the screen to read it
        self._refresh()



    def _wndproc(self, hwnd, message, wparam, lparam):
        user32 = _dll("user32")
        try:
            if message == CALLBACK:
                event = lparam & 0xFFFF
                if self._version4:
                    if event == NIN_POPUPOPEN:
                        self._show_tip(wparam)
                    elif event == NIN_POPUPCLOSE:
                        self._hide_tip(at_once=False)
                    elif event == WM_MOUSEMOVE:
                        self._tip_moved()
                    elif event in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
                        self._hide_tip()
                    elif event in (NIN_SELECT, NIN_KEYSELECT):
                        self._select(keyboard=event == NIN_KEYSELECT)
                    elif event == WM_LBUTTONDBLCLK:
                        self._double_click()
                    elif event == WM_CONTEXTMENU:
                        self._hide_popup()
                        self._menu()
                else:
                    if event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                        self._hide_popup()
                        self._menu()
                    elif event == WM_LBUTTONUP:
                        self._select()
                    elif event == WM_LBUTTONDBLCLK:
                        self._double_click()
                return 0
            if message == WM_TIMER:
                if wparam == TIMER_TIP:
                    self._tip_probe()
                elif wparam == TIMER_FRAME:
                    self._animate()
                else:
                    self._refresh()
                    self._look_for_demo()
                return 0
            if message == WM_TRAY_FRAMES:
                self._frames_built()
                return 0
            if message == WM_WTSSESSION_CHANGE:
                self._session_changed(wparam)
                return 0
            if self._taskbar_created and message == self._taskbar_created:
                self._hide_tip()
                self._hide_popup()
                self._notify(NIM_ADD)
                self._set_version()
                return 0
            if message == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                user32.KillTimer(hwnd, TIMER_TICK)
                user32.KillTimer(hwnd, TIMER_FRAME)
                user32.KillTimer(hwnd, TIMER_TIP)
                self._motion_ms = None
                if self._session_watch:
                    try:
                        wts = _dll("wtsapi32")
                        wts.WTSUnRegisterSessionNotification.argtypes = [W.HWND]
                        wts.WTSUnRegisterSessionNotification(hwnd)
                    except Exception:
                        pass
                    self._session_watch = False
                self._drop_cards()
                self._drop_menu()
                tip, self._tip = self._tip, None
                if tip:
                    try:
                        tip.destroy()
                    except Exception as exc:
                        self.log("tray tip card cleanup failed (%s)" % type(exc).__name__)
                demo, self._demo = self._demo, None
                if demo is not None:
                    demo.__exit__(None, None, None)
                popup, self._popup = self._popup, None
                if popup is not None:
                    try:
                        popup.destroy()
                    except Exception as exc:
                        self.log("tray popup cleanup failed (%s)" % type(exc).__name__)
                data = NOTIFYICONDATAW()
                data.cbSize = C.sizeof(NOTIFYICONDATAW)
                data.hWnd = hwnd
                data.uID = 1
                _dll("shell32").Shell_NotifyIconW(NIM_DELETE, C.byref(data))
                if self._frame_icon:
                    user32.DestroyIcon(self._frame_icon)
                    self._frame_icon = self._frame_key = None
                if self._icon and self._icon_owned:
                    user32.DestroyIcon(self._icon)
                self._icon = self._shown_icon = None
                user32.PostQuitMessage(0)
                return 0
        except Exception as exc:
            self.log("tray message failed (%s)" % type(exc).__name__)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)
