#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""slstudio_app.py - Starlancer Studio: one unified cockpit for every Starlancer
modding tool. A modern CustomTkinter "Alliance Naval Command" terminal that fronts
the validated command-line libraries as a single app (and a single .exe).

Sections:
    PATCHER         widescreen + crash fixes      -> sl_patch.py
    SHIP SWITCHER   fly a Coalition ship          -> slswitch.py + hog_pack.py
    STATS EDITOR    edit ship/gun/missile stats   -> slstats.py
    HOG TOOLS       list/extract/pack/edit .HOG   -> hog_extract.py + hog_pack.py
    CONTROLLER      install the XInput shim       -> xinput_shim/ (file copy only)
    BOOT VIDEOS     blank the startup logos       -> blank_boot_videos.py + hog_pack.py

SAFETY (non-negotiable): like every tool in this project, Starlancer Studio reads
and patches LOCAL COPIES only. It NEVER launches the game (no subprocess / os.system
/ os.startfile of any game binary anywhere in this file). The patcher writes a COPY;
the controller installer only COPIES a DLL and writes a text .ini into the user's own
game folder. In-game testing is the user's, on their own terms.

Run:    python slstudio_app.py
Build:  build.bat  ->  dist\\StarlancerStudio.exe   (PyInstaller, one-file)
Dep:    customtkinter   (pure Python; the only third-party runtime dependency)
"""
import os
import sys
import io
import json
import shutil
import contextlib
import threading
import queue
import re
import time

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    import tkinter.font as tkfont
except ImportError as _e:                 # e.g. a Linux Python without the python3-tk package
    _NO_TK = ("Starlancer Studio needs Tk (tkinter), which this Python lacks: %s\n"
              "  Windows/macOS: reinstall Python with the tcl/tk option ticked;\n"
              "  Debian/Ubuntu: sudo apt install python3-tk   Fedora: sudo dnf install python3-tkinter\n"
              "The command-line tools in this folder need nothing extra." % _e)
    if __name__ == "__main__":
        sys.exit(_NO_TK)
    raise ImportError(_NO_TK)             # an import must never kill its importer

try:
    import customtkinter as ctk
except ImportError:
    _MISSING = ("Starlancer Studio needs the 'customtkinter' package - its only third-party runtime\n"
                "dependency (see requirements-optional.txt). Install it with:\n\n"
                "    python -m pip install customtkinter\n\n"
                "The command-line tools need nothing extra, and the legacy GUI tools/slstudio.py\n"
                "runs on the standard library alone.")
    # Only a DIRECT RUN gets the dialog. When this module is merely IMPORTED - by a
    # test collector, a tooling sweep, or `python -c "import slstudio_app"` - a modal
    # Tk window blocks the importing process until a human dismisses it, and sys.exit
    # kills that process outright. Importers get a plain ImportError instead, which
    # is why Studio's logic now lives in slstudio_core: that module has no such trap.
    if __name__ == "__main__":
        try:                              # also visible when launched without a console (pythonw)
            _root = tk.Tk()
            _root.withdraw()
            messagebox.showerror("Starlancer Studio - missing dependency", _MISSING)
        except Exception:
            pass
        sys.exit(_MISSING)
    raise ImportError(_MISSING)

ctk.set_appearance_mode("dark")          # set before any window is created
ctk.set_default_color_theme("dark-blue")

# --- our validated backend libraries (imported as modules; never shelled out) ----
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slstats          # noqa: E402  ship/gun/missile stat tables
import slswitch         # noqa: E402  Coalition ship-switcher
import hog_pack         # noqa: E402  .HOG (BIGF) writer
import hog_extract      # noqa: E402  .HOG (BIGF) reader
import sl_patch         # noqa: E402  modern-systems EXE patch pack
import slstudio_core as core          # noqa: E402  headless install logic (no Tk)
import blank_boot_videos as bootvid   # noqa: E402  startup-logo blanker


# ============================================================== design system ===
# Palette - "Alliance Naval Command MFD": deep-space navy ground, faction-coded
# accents (Alliance ice-cyan, Coalition warning-red), phosphor amber for cautions.
BG0   = "#070A11"   # window / deepest space
BG1   = "#0B111B"   # base panel
BG2   = "#101A28"   # raised panel / card
BG3   = "#16243A"   # input / hover
LINE  = "#1B2A3D"   # hairline
LINE2 = "#284059"   # brighter rule
CYAN  = "#33E1F0"   # Alliance / primary accent
CYAN_D = "#15808F"  # darker cyan
INK   = "#04141A"   # text on cyan
AMBER = "#FFB23E"   # caution / phosphor
AMBER_D = "#1C1404" # caution panel ground
RED   = "#FF5266"   # Coalition / danger
RED_D = "#7A1E2A"   # danger hover ground
GREEN = "#55E08B"   # ok / online
TXT   = "#D7E3F2"   # primary text
TXT_D = "#90A2B8"   # secondary text
TXT_DD = "#566A80"  # tertiary / hints

APP_VERSION = "v1.2"
PALETTE = dict(BG0=BG0, BG1=BG1, BG2=BG2, BG3=BG3, LINE=LINE, LINE2=LINE2,
               CYAN=CYAN, AMBER=AMBER, RED=RED, GREEN=GREEN, TXT=TXT, TXT_D=TXT_D)

F = {}   # CTkFont registry (populated after the root window exists)


def _build_fonts():
    fams = set(tkfont.families())

    def fam(*names, default="Segoe UI"):
        return next((n for n in names if n in fams), default)

    disp = fam("Bahnschrift SemiBold Condensed", "Bahnschrift SemiBold", "Agency FB")
    disp2 = fam("Bahnschrift SemiBold", "Bahnschrift", "Segoe UI Semibold")
    body = fam("Bahnschrift", "Segoe UI")
    bodylt = fam("Bahnschrift SemiLight", "Bahnschrift Light", "Bahnschrift", "Segoe UI")
    mono = fam("Cascadia Mono", "Consolas", "Lucida Console")
    monosb = fam("Cascadia Mono SemiBold", "Cascadia Mono", "Consolas")

    F.update(
        wordmark=ctk.CTkFont(disp, 22),
        crest=ctk.CTkFont(disp, 17),
        h1=ctk.CTkFont(disp2, 21),
        h2=ctk.CTkFont(disp2, 14),
        nav=ctk.CTkFont(disp2, 14),
        body=ctk.CTkFont(body, 13),
        body_sb=ctk.CTkFont(disp2, 13),
        small=ctk.CTkFont(bodylt, 12),
        tiny=ctk.CTkFont(body, 11),
        btn=ctk.CTkFont(disp2, 13),
        mono=ctk.CTkFont(mono, 12),
        mono_sb=ctk.CTkFont(monosb, 12),
        mono_sm=ctk.CTkFont(mono, 11),
    )
    # raw family tuples for tk widgets (Canvas / ttk) that don't take CTkFont
    F["_disp"], F["_mono"], F["_body"] = disp, mono, body


def resource_path(rel):
    """Resolve a bundled data file both frozen (PyInstaller _MEIPASS) and in dev."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# ================================================================= preferences ==
class Prefs:
    PATH = os.path.join(os.path.expanduser("~"), ".starlancer_studio.json")

    def __init__(self):
        self.data = {}
        try:
            with open(self.PATH, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception:
            self.data = {}

    def get(self, k, d=None):
        return self.data.get(k, d)

    def set(self, k, v):
        self.data[k] = v
        try:
            with open(self.PATH, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass


PREFS = Prefs()


def _initialdir():
    d = PREFS.get("last_dir")
    return d if d and os.path.isdir(d) else os.path.expanduser("~")


def _remember(path):
    if path:
        PREFS.set("last_dir", os.path.dirname(path))
    return path


def ask_open(title, filetypes):
    return _remember(filedialog.askopenfilename(title=title, filetypes=filetypes,
                                                 initialdir=_initialdir()))


def ask_save(title, defaultextension, initialfile="", filetypes=None):
    return _remember(filedialog.asksaveasfilename(
        title=title, defaultextension=defaultextension, initialfile=initialfile,
        filetypes=filetypes or [("All files", "*.*")], initialdir=_initialdir()))


def ask_dir(title):
    p = filedialog.askdirectory(title=title, initialdir=_initialdir())
    if p:
        PREFS.set("last_dir", p)
    return p


# ===================================================== tool-call plumbing ========
def run_capturing(fn, *a, **k):
    """Run a tool fn that prints to stdout and may raise SystemExit on a guard.
    Returns (ok, return_code, captured_text)."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = fn(*a, **k)
        return True, rc, buf.getvalue()
    except SystemExit as e:
        msg = buf.getvalue()
        s = "" if e.code is None else str(e.code)
        if s and s != "0":
            msg = (msg + "\n" + s).strip()
        return False, None, msg
    except BaseException as e:                       # noqa: BLE001 - surfaced to UI
        return False, None, (buf.getvalue() + "\n" + repr(e)).strip()


# ======================================================= shared game context ====
class GameContext:
    """The single Starlancer install folder/exe that every section shares, so the
    Dashboard, Controller, Boot-Videos and Deploy tabs all point at one target.
    Folder-only is persisted (the exe is re-resolved each launch -> never stale)."""

    def __init__(self):
        self.folder = PREFS.get("game_folder", "") or ""
        self.exe = self._find_exe(self.folder) if self.folder else ""

    @staticmethod
    def _find_exe(folder):
        try:
            for f in os.listdir(folder):
                if f.lower() == "lancer.exe":
                    return os.path.join(folder, f)
        except Exception:
            pass
        return ""

    def has_exe(self):
        return bool(self.exe and os.path.exists(self.exe))

    def set(self, folder):
        if not folder:
            return
        self.folder = folder
        self.exe = self._find_exe(folder)
        PREFS.set("game_folder", folder)


# ===================================================== install-status helpers ===
# These live in slstudio_core, which is standard-library only and imports with no
# GUI toolkit present. Keeping them there rather than here is what lets
# tests/run_all.py exercise Studio's logic on every platform: this module cannot
# be imported at all without customtkinter. Re-exported under their old names so
# the sections below read unchanged.
patch_states = core.patch_states
bootvid_status = core.bootvid_status
recommended_selections = core.recommended_selections
describe_selections = core.describe_selections
retire_manifest = core.retire_manifest
classify_exe = core.classify_exe
scan_install = core.scan


def shim_status(folder):
    """XInput-shim state. Core does the comparison; the app supplies the bundled
    proxy, whose path only this module can resolve (PyInstaller's _MEIPASS)."""
    return core.shim_status(folder, resource_path(os.path.join("xinput_shim", "dinput.dll")))


# ============================================================ small UI helpers ==
def hud_panel(master, **kw):
    kw.setdefault("fg_color", BG2)
    kw.setdefault("corner_radius", 4)
    kw.setdefault("border_width", 1)
    kw.setdefault("border_color", LINE2)
    return ctk.CTkFrame(master, **kw)


def panel_title(master, text, accent=CYAN):
    row = ctk.CTkFrame(master, fg_color="transparent")
    tick = ctk.CTkFrame(row, width=3, height=14, fg_color=accent, corner_radius=0)
    tick.pack(side="left", padx=(0, 8))
    ctk.CTkLabel(row, text=text, font=F["h2"], text_color=TXT).pack(side="left")
    return row


def primary_button(master, text, command, **kw):
    kw.setdefault("height", 38)
    return ctk.CTkButton(master, text=text, command=command, font=F["btn"],
                         fg_color=CYAN_D, hover_color=CYAN, text_color=INK,
                         corner_radius=4, **kw)


def ghost_button(master, text, command, **kw):
    kw.setdefault("height", 34)
    return ctk.CTkButton(master, text=text, command=command, font=F["btn"],
                         fg_color="transparent", hover_color=BG3, text_color=TXT,
                         corner_radius=4, border_width=1, border_color=LINE2, **kw)


def danger_button(master, text, command, **kw):
    kw.setdefault("height", 34)
    return ctk.CTkButton(master, text=text, command=command, font=F["btn"],
                         fg_color="transparent", hover_color=RED_D, text_color=RED,
                         corner_radius=4, border_width=1, border_color=RED_D, **kw)


def hud_entry(master, textvariable=None, **kw):
    kw.setdefault("height", 32)
    return ctk.CTkEntry(master, textvariable=textvariable, font=F["mono_sm"],
                        fg_color=BG0, border_color=LINE2, border_width=1,
                        text_color=TXT, corner_radius=3, **kw)


class LogPanel(ctk.CTkFrame):
    """A console-styled read-only log with colored lines."""

    def __init__(self, master, height=150, title="CONSOLE"):
        super().__init__(master, fg_color=BG1, corner_radius=4,
                         border_width=1, border_color=LINE)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(7, 0))
        ctk.CTkLabel(bar, text="◈ " + title, font=F["mono_sb"],
                     text_color=TXT_D).pack(side="left")
        ctk.CTkButton(bar, text="CLEAR", width=52, height=20, font=F["mono_sm"],
                      fg_color="transparent", hover_color=BG3, text_color=TXT_DD,
                      border_width=1, border_color=LINE, corner_radius=3,
                      command=self.clear).pack(side="right")
        self.box = ctk.CTkTextbox(self, font=F["mono_sm"], fg_color=BG0,
                                  text_color=TXT_D, border_width=0, wrap="word",
                                  height=height, activate_scrollbars=True)
        self.box.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self._txt = getattr(self.box, "_textbox", None)
        if self._txt is not None:
            for name, c in (("ok", GREEN), ("err", RED), ("warn", AMBER),
                            ("info", CYAN), ("dim", TXT_DD), ("hi", TXT)):
                try:
                    self._txt.tag_config(name, foreground=c)
                except Exception:
                    pass
        self.box.configure(state="disabled")

    def line(self, text, tag="dim"):
        self.box.configure(state="normal")
        try:
            self.box.insert("end", str(text) + "\n", tag)
        except Exception:
            self.box.insert("end", str(text) + "\n")
        self.box.see("end")
        self.box.configure(state="disabled")

    def block(self, text, tag="dim"):
        for ln in str(text).rstrip("\n").split("\n"):
            self.line(ln, tag)

    def rule(self, label=""):
        self.line("─" * 4 + (" " + label + " " if label else " ") +
                  "─" * 28, "dim")

    def clear(self):
        self.box.configure(state="normal")
        self.box.delete("1.0", "end")
        self.box.configure(state="disabled")


class LED(tk.Canvas):
    """A tiny status light."""

    def __init__(self, master, color=GREEN, size=12, bg=BG1):
        super().__init__(master, width=size, height=size, bg=bg,
                         highlightthickness=0, bd=0)
        r = size // 2
        self._ring = self.create_oval(2, 2, size - 2, size - 2, outline=LINE2, width=1)
        self._dot = self.create_oval(r - 3, r - 3, r + 3, r + 3, fill=color, outline="")

    def set(self, color):
        self.itemconfig(self._dot, fill=color)


# ================================================================ base section ==
class Section(ctk.CTkFrame):
    TITLE = "SECTION"
    SUB = ""
    GLYPH = "▣"

    def __init__(self, master, app):
        super().__init__(master, fg_color=BG0, corner_radius=0)
        self.app = app
        self._busy = False
        self._busy_widgets = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        head = self._build_head()
        head.grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 8))
        self.bind("<Configure>", self._on_resize)
        self.progress = ctk.CTkProgressBar(self, mode="indeterminate", height=3,
                                           fg_color=BG2, progress_color=CYAN,
                                           corner_radius=0)
        self.progress.grid(row=1, column=0, sticky="ew", padx=26)
        self.progress.grid_remove()

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=2, column=0, sticky="nsew", padx=26, pady=(12, 18))
        self.build()

    def _build_head(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(f, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(top, text="%s   %s" % (self.GLYPH, self.TITLE),
                     font=F["h1"], text_color=TXT).pack(side="left")
        self.head_status = ctk.CTkLabel(top, text="STANDBY", font=F["mono_sm"],
                                        text_color=TXT_DD)
        self.head_status.pack(side="right")
        self._sub = ctk.CTkLabel(f, text=self.SUB, font=F["small"], text_color=TXT_D,
                                 anchor="w", justify="left", wraplength=820)
        self._sub.grid(row=1, column=0, sticky="ew", pady=(2, 9))
        ctk.CTkFrame(f, height=1, fg_color=LINE2).grid(row=2, column=0, sticky="ew")
        return f

    def _on_resize(self, e):
        try:
            self._sub.configure(wraplength=max(280, e.width - 130))
        except Exception:
            pass

    # ---- async / busy state -------------------------------------------------
    def set_busy(self, flag, msg=""):
        self._busy = flag
        for w in self._busy_widgets:
            try:
                w.configure(state="disabled" if flag else "normal")
            except Exception:
                pass
        if flag:
            self.progress.grid()
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.grid_remove()
        if msg:
            self.status(msg, "busy" if flag else "ok")

    def status(self, text, level="ok"):
        col = {"ok": GREEN, "err": RED, "warn": AMBER, "busy": CYAN,
               "": TXT_DD}.get(level, TXT_D)
        self.head_status.configure(text=text, text_color=col)

    def default_error(self, e):
        """Every worker exception lands here, on the main thread.

        PermissionError is the one users actually hit (the game installed under
        Program Files, or Studio started without elevation), so it gets the
        actionable message rather than a raw OSError string. Sections must NOT
        wrap run_async/run_steps in their own try/except: those return as soon as
        the thread starts, so such a handler is unreachable.
        """
        self.status("FAULT", "err")
        if isinstance(e, PermissionError):
            where = getattr(e, "filename", None)
            msg = ("Permission denied%s\n\nWindows refused the write. Either run "
                   "Starlancer Studio as administrator, or copy the game to a "
                   "writable folder outside Program Files and point Studio there."
                   % (": " + where if where else ""))
        else:
            msg = str(e) if (str(e) and str(e) != "None") else repr(e)
        if hasattr(self, "log"):
            self.log.block(msg, "err")
        messagebox.showerror(self.TITLE.title(), msg)

    def run_async(self, work_fn, on_done, busy="WORKING"):
        # Tkinter is single-threaded: the worker touches NO tk objects, it only
        # posts its result to a queue that the main thread drains via after().
        self.set_busy(True, busy)
        q = queue.Queue()

        def body():
            try:
                q.put(("ok", work_fn()))
            except BaseException as e:                # noqa: BLE001
                q.put(("err", e))

        def poll():
            try:
                kind, payload = q.get_nowait()
            except queue.Empty:
                self.after(60, poll)
                return
            self.set_busy(False)
            if kind == "ok":
                on_done(payload)
            else:
                self.default_error(payload)

        threading.Thread(target=body, daemon=True).start()
        self.after(60, poll)

    # ---- multi-step pipeline (streams to the log + a determinate bar) --------
    def _begin_steps(self, busy):
        self._busy = True
        for w in self._busy_widgets:
            try:
                w.configure(state="disabled")
            except Exception:
                pass
        try:
            self.progress.configure(mode="determinate")
            self.progress.set(0)
        except Exception:
            pass
        self.progress.grid()
        self.status(busy, "busy")

    def _end_steps(self, ok, on_done):
        self.set_busy(False)
        try:
            self.progress.configure(mode="indeterminate")     # restore default for others
        except Exception:
            pass
        self.status("DONE" if ok else "FAILED", "ok" if ok else "err")
        if on_done:
            try:
                on_done(ok)
            except BaseException as e:                # noqa: BLE001
                self.default_error(e)

    def run_steps(self, steps, on_done=None, busy="WORKING"):
        """Run a list of (label, fn) steps on a worker thread, streaming progress to
        the log + a determinate progress bar. Each fn may return a short status string
        (logged). Stops at the first step that raises (logged red). The worker NEVER
        touches tk: it posts messages to a queue drained on the main thread."""
        self._begin_steps(busy)
        q = queue.Queue()
        n = max(1, len(steps))

        def body():
            for i, (label, fn) in enumerate(steps):
                q.put(("step", label))
                try:
                    msg = fn()
                except BaseException as e:            # noqa: BLE001
                    q.put(("fail", label, e))
                    q.put(("done", False))
                    return
                q.put(("ok", i, msg))
            q.put(("done", True))

        def poll():
            try:
                while True:
                    item = q.get_nowait()
                    kind = item[0]
                    if kind == "step":
                        self.log.line("▸ " + item[1], "info")
                    elif kind == "ok":
                        i, msg = item[1], item[2]
                        if msg:                       # a step may return (text, tag) for a warn
                            if isinstance(msg, tuple):
                                self.log.block(msg[0], msg[1])
                            else:
                                self.log.block(msg, "ok")
                        try:
                            self.progress.set((i + 1) / n)
                        except Exception:
                            pass
                    elif kind == "fail":
                        self.log.line("✗ %s — %s" % (item[1], item[2]), "err")
                    elif kind == "done":
                        self._end_steps(item[1], on_done)
                        return
            except queue.Empty:
                self.after(60, poll)

        threading.Thread(target=body, daemon=True).start()
        self.after(60, poll)

    def build(self):
        pass


# ============================================================ PATCHER section ===
RES_PRESETS = ["1280 x 720", "1366 x 768", "1600 x 900", "1920 x 1080",
               "2560 x 1080", "2560 x 1440", "3440 x 1440", "3840 x 2160",
               "Custom…"]


class PatcherFrame(Section):
    TITLE = "PATCHER"
    SUB = ("Hor+ widescreen and the RE'd crash fixes, applied to a COPY — the "
           "original exe and the game are never launched.")
    GLYPH = "◈"

    def build(self):
        b = self.body
        b.grid_columnconfigure(0, weight=1)
        b.grid_columnconfigure(1, weight=0)
        b.grid_rowconfigure(2, weight=1)

        # --- I/O panel --------------------------------------------------------
        io_p = hud_panel(b)
        io_p.grid(row=0, column=0, columnspan=2, sticky="ew")
        io_p.grid_columnconfigure(1, weight=1)
        panel_title(io_p, "TARGET EXECUTABLE").grid(row=0, column=0, columnspan=3,
                                                    sticky="w", padx=14, pady=(12, 8))
        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self._io_row(io_p, 1, "INPUT  (a copy of Lancer.exe)", self.in_var, self._pick_in)
        self._io_row(io_p, 2, "OUTPUT (patched copy)", self.out_var, self._pick_out)
        ctk.CTkLabel(io_p, text="⚑  Patches a COPY. The stock exe is read-only; "
                     "the game is never launched.", font=F["tiny"],
                     text_color=TXT_DD).grid(row=3, column=0, columnspan=3,
                                             sticky="w", padx=14, pady=(2, 12))

        # --- fixes panel ------------------------------------------------------
        fx = hud_panel(b)
        fx.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        fx.grid_columnconfigure(0, weight=1)
        panel_title(fx, "FIXES").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 6))

        self.force_on = tk.BooleanVar(value=False)

        # Fix rows are GENERATED from sl_patch's registry, not listed here. A new
        # PatchDefinition therefore shows up in this panel, in the LED strip, on the
        # Dashboard and in the deploy wizard with no GUI edit at all. Whichever fix
        # declares needs_params carries the resolution controls on its own row.
        self.fix_vars = {}
        self._param_fix = None
        fix_defs = sl_patch.ordered_fixes()

        for i, defn in enumerate(fix_defs):
            var = tk.BooleanVar(value=defn.recommended)
            self.fix_vars[defn.id] = var
            row = ctk.CTkFrame(fx, fg_color="transparent")
            row.grid(row=1 + i, column=0, sticky="ew", padx=14,
                     pady=2 if defn.needs_params else 4)
            ctk.CTkCheckBox(row, text=defn.caption, variable=var,
                            font=F["body_sb"] if defn.needs_params else F["body"],
                            text_color=TXT, command=self._sync,
                            checkbox_width=20, checkbox_height=20, corner_radius=3,
                            fg_color=CYAN_D, hover_color=CYAN,
                            border_color=LINE2).pack(side="left")
            if defn.needs_params and self._param_fix is None:
                self._param_fix = defn.id
                self.res_var = tk.StringVar(value="1920 x 1080")
                self.res_menu = ctk.CTkOptionMenu(row, values=RES_PRESETS,
                                                  variable=self.res_var,
                                                  command=lambda _=None: self._sync(),
                                                  width=140, font=F["mono_sm"],
                                                  dropdown_font=F["mono_sm"],
                                                  fg_color=BG0, button_color=BG3,
                                                  button_hover_color=LINE2,
                                                  text_color=TXT, dropdown_fg_color=BG2,
                                                  dropdown_text_color=TXT, corner_radius=3)
                self.res_menu.pack(side="left", padx=(12, 6))
                self.cw = tk.StringVar(value="1920")
                self.ch = tk.StringVar(value="1080")
                self.cw_e = hud_entry(row, textvariable=self.cw, width=64)
                self.cw_e.pack(side="left")
                ctk.CTkLabel(row, text="×", font=F["body"],
                             text_color=TXT_D).pack(side="left", padx=4)
                self.ch_e = hud_entry(row, textvariable=self.ch, width=64)
                self.ch_e.pack(side="left")

        force_row = ctk.CTkFrame(fx, fg_color="transparent")
        force_row.grid(row=1 + len(fix_defs), column=0, sticky="w", padx=14, pady=(6, 12))
        ctk.CTkCheckBox(force_row, text="Force", variable=self.force_on,
                        font=F["body"], text_color=AMBER, checkbox_width=20,
                        checkbox_height=20, corner_radius=3, fg_color=AMBER,
                        hover_color=AMBER, border_color=LINE2).pack(side="left")
        ctk.CTkLabel(force_row, text="override size/byte guards (not ImageBase / not an "
                     "already-patched site)", font=F["tiny"],
                     text_color=TXT_DD).pack(side="left", padx=8)

        # --- verify strip (right) --------------------------------------------
        vp = hud_panel(b)
        vp.grid(row=1, column=1, sticky="nsew", padx=(12, 0), pady=(12, 0))
        panel_title(vp, "PATCH STATE").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))
        self.leds = {}
        for i, defn in enumerate(fix_defs):
            row = ctk.CTkFrame(vp, fg_color="transparent")
            row.grid(row=1 + i, column=0, sticky="ew", padx=14, pady=3)
            led = LED(row, color=TXT_DD, bg=BG2)
            led.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(row, text=defn.label, font=F["mono_sm"], text_color=TXT_D,
                         width=92, anchor="w").pack(side="left")
            val = ctk.CTkLabel(row, text="—", font=F["mono_sm"], text_color=TXT_DD)
            val.pack(side="left")
            self.leds[defn.id] = (led, val)
        self.sha_lbl = ctk.CTkLabel(vp, text="manifest —", font=F["mono_sm"],
                                    text_color=TXT_DD, anchor="w")
        self.sha_lbl.grid(row=1 + len(fix_defs), column=0, sticky="ew",
                          padx=14, pady=(8, 12))

        # --- actions ----------------------------------------------------------
        acts = ctk.CTkFrame(b, fg_color="transparent")
        acts.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 8))
        self.btn_patch = primary_button(acts, "▶  PATCH COPY", self._patch, width=160)
        self.btn_patch.pack(side="left")
        self.btn_dry = ghost_button(acts, "DRY-RUN", self._dryrun, width=92)
        self.btn_dry.pack(side="left", padx=(8, 0))
        ghost_button(acts, "VERIFY…", self._verify_pick, width=92).pack(side="left", padx=(8, 0))
        ghost_button(acts, "REVERT…", self._revert_pick, width=92).pack(side="left", padx=(8, 0))
        ghost_button(acts, "FOV TABLE", self._fov, width=96).pack(side="left", padx=(8, 0))
        self._busy_widgets = [self.btn_patch, self.btn_dry]

        self.log = LogPanel(b, height=150)
        self.log.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        b.grid_rowconfigure(3, weight=1)
        self.log.line("sl_patch engine ready — " + ", ".join(sl_patch.REGISTRY), "info")
        self.log.line("expected stock build: %s bytes, ImageBase 0x%06X"
                      % (format(sl_patch.EXPECT_SIZE, ","), sl_patch.IMAGE_BASE), "dim")
        self._sync()

    # ---- I/O row helper -----------------------------------------------------
    def _io_row(self, master, r, label, var, cmd):
        ctk.CTkLabel(master, text=label, font=F["small"], text_color=TXT_D,
                     width=180, anchor="w").grid(row=r, column=0, sticky="w",
                                                 padx=(14, 8), pady=4)
        hud_entry(master, textvariable=var).grid(row=r, column=1, sticky="ew", pady=4)
        ghost_button(master, "BROWSE", cmd, width=84, height=32).grid(
            row=r, column=2, padx=(8, 14), pady=4)

    def _pick_in(self):
        p = ask_open("Select a COPY of Lancer.exe",
                     [("Executable", "*.exe"), ("All files", "*.*")])
        if not p:
            return
        self.in_var.set(p)
        stem, ext = os.path.splitext(p)
        self.out_var.set(stem + "_patched" + (ext or ".exe"))
        self.status("LOADED", "ok")
        self.log.line("input: " + p, "hi")

    def _pick_out(self):
        p = ask_save("Save patched copy as", ".exe",
                     initialfile=os.path.basename(self.out_var.get() or "Lancer_patched.exe"),
                     filetypes=[("Executable", "*.exe")])
        if p:
            self.out_var.set(p)

    def on_show(self):
        """Seed from the install picked on another tab, and show its patch state.

        Only EMPTY fields are filled, so anything browsed or typed here wins and a
        deliberate choice is never overwritten on a tab switch. The output defaults
        to a NEW file beside the input: sl_patch writes the copy and the install's
        own exe is only ever read. The state strip is refreshed only when the file
        parses as a PE, so pointing Studio at a SafeDisc loader does not throw an
        error dialog merely for opening this tab.
        """
        exe = self.app.game.exe
        if not exe or not os.path.exists(exe):
            return
        seeded = False
        if not self.in_var.get().strip():
            self.in_var.set(exe)
            seeded = True
        src = self.in_var.get().strip()
        if not self.out_var.get().strip():
            stem, ext = os.path.splitext(src)
            self.out_var.set(stem + "_patched" + (ext or ".exe"))
        if seeded:
            self.log.line("seeded from the selected install: " + src, "dim")
        states, _man, _sha = patch_states(src)
        if states:
            self._do_verify(src)

    def _sync(self):
        if not self._param_fix:            # no fix wants parameters: nothing to gate
            return
        ws = self.fix_vars[self._param_fix].get()
        custom = self.res_var.get().startswith("Custom")
        self.res_menu.configure(state="normal" if ws else "disabled")
        for e in (self.cw_e, self.ch_e):
            e.configure(state="normal" if (ws and custom) else "disabled")
        if ws and not custom:
            w, h = self._res_from_preset()
            self.cw.set(str(w))
            self.ch.set(str(h))

    def _res_from_preset(self):
        try:
            w, h = self.res_var.get().replace(" ", "").split("x")
            return int(w), int(h)
        except Exception:
            return 1920, 1080

    def _params_for(self, defn):
        """Parameters for one fix. Only needs_params fixes take any; today that is
        widescreen and its width/height, read from the preset menu or the custom
        entries. sl_patch validates them, so this only has to read the widgets."""
        if not defn.needs_params:
            return {}
        if self.res_var.get().startswith("Custom"):
            return dict(width=int(self.cw.get()), height=int(self.ch.get()))
        w, h = self._res_from_preset()
        return dict(width=w, height=h)

    def _selections(self):
        return [(d.id, self._params_for(d))
                for d in sl_patch.ordered_fixes() if self.fix_vars[d.id].get()]

    def _guard_io(self, need_out=True):
        ip = self.in_var.get().strip()
        op = self.out_var.get().strip()
        if not ip:
            messagebox.showwarning("No input", "Pick a copy of Lancer.exe first.")
            return None
        if need_out and not op:
            messagebox.showwarning("No output", "Choose an output path.")
            return None
        if need_out and os.path.abspath(ip) == os.path.abspath(op):
            messagebox.showerror("Same file",
                                 "Output must differ from the input — the patcher "
                                 "never overwrites the source exe.")
            return None
        return ip, op

    def _patch(self):
        self._apply(dry=False)

    def _dryrun(self):
        self._apply(dry=True)

    def _apply(self, dry):
        io_p = self._guard_io()
        if not io_p:
            return
        ip, op = io_p
        sel = self._selections()
        if not sel:
            messagebox.showwarning("Nothing selected", "Tick at least one fix.")
            return
        force = self.force_on.get()
        self.log.rule("PATCH (dry-run)" if dry else "PATCH")

        def work():
            return run_capturing(sl_patch.apply, ip, op, sel, force=force, dry_run=dry)

        def done(res):
            ok, _rc, text = res
            self.log.block(text or "(no output)", "ok" if ok else "err")
            if ok:
                self.status("DRY-RUN OK" if dry else "PATCHED", "ok")
                if not dry:
                    self._do_verify(op)
            else:
                self.status("REFUSED", "err")
                self._explain_guard(text)

        self.run_async(work, done, busy="PATCHING")

    def _explain_guard(self, text):
        t = (text or "").lower()
        if "size" in t and "expected" in t:
            messagebox.showwarning(
                "Build mismatch",
                "This exe isn't the analyzed build (expected %s bytes, ImageBase "
                "0x%06X). It may be the wrong file or already modified.\n\nTick "
                "Force to override the size/byte guards — ImageBase and "
                "already-patched (JMP) checks still apply."
                % (format(sl_patch.EXPECT_SIZE, ","), sl_patch.IMAGE_BASE))
        elif "already" in t and "jmp" in t:
            messagebox.showwarning("Already patched",
                                   "A hook site already contains a JMP. Revert first, "
                                   "then re-apply.")

    # ---- verify -------------------------------------------------------------
    def _verify_pick(self):
        default = self.out_var.get().strip()
        p = default if (default and os.path.exists(default)) else ask_open(
            "Verify which exe?", [("Executable", "*.exe"), ("All files", "*.*")])
        if p:
            self.log.rule("VERIFY")
            self._do_verify(p)

    def _do_verify(self, path):
        states, man, sha_ok = patch_states(path)        # shared probe (Dashboard uses it too)
        if not states:
            self.default_error("could not read %s as a PE" % os.path.basename(path))
            return
        try:
            nbytes = os.path.getsize(path)
        except OSError:
            nbytes = 0
        self.log.line("file: %s  (%s bytes)" % (os.path.basename(path), format(nbytes, ",")), "hi")
        any_p = False
        for key, (led, val) in self.leds.items():
            state, desc = states.get(key, ("unknown", ""))
            if state == "patched":
                any_p = True
            col = {"patched": GREEN, "stock": TXT_DD, "unknown": AMBER}.get(state, TXT_DD)
            led.set(col)
            val.configure(text=state.upper(), text_color=col)
            self.log.line("  %-14s %-8s %s" % (key, state.upper(), desc),
                          "ok" if state == "patched" else
                          ("warn" if state == "unknown" else "dim"))
        if man:
            self.sha_lbl.configure(
                text="manifest " + ("✓ sha matches" if sha_ok else "⚠ sha differs"),
                text_color=GREEN if sha_ok else AMBER)
            self.log.line("manifest: %s" % ("sha256 matches" if sha_ok else "sha256 DIFFERS"),
                          "ok" if sha_ok else "warn")
        else:
            self.sha_lbl.configure(text="manifest — none beside file", text_color=TXT_DD)
        self.status("VERIFIED" if any_p else "STOCK", "ok" if any_p else "")

    # ---- revert -------------------------------------------------------------
    def _revert_pick(self):
        ip = ask_open("Revert which patched exe?",
                      [("Executable", "*.exe"), ("All files", "*.*")])
        if not ip:
            return
        stem, ext = os.path.splitext(ip)
        op = ask_save("Save reverted copy as", ".exe",
                      initialfile=os.path.basename(stem + "_reverted" + (ext or ".exe")),
                      filetypes=[("Executable", "*.exe")])
        if not op:
            return
        self.log.rule("REVERT")

        def work():
            return run_capturing(sl_patch.revert, ip, op, None)

        def done(res):
            ok, _rc, text = res
            self.log.block(text or "(no output)", "ok" if ok else "err")
            self.status("REVERTED" if ok else "FAILED", "ok" if ok else "err")

        self.run_async(work, done, busy="REVERTING")

    def _fov(self):
        self.log.rule("FOV TABLE")
        ok, _rc, text = run_capturing(sl_patch.fov_table)
        self.log.block(text, "info" if ok else "err")


# ======================================================== selectable list =======
class SelectList(ctk.CTkScrollableFrame):
    """A single-select list of rows inside a scroll frame."""

    def __init__(self, master, title, on_select=None):
        super().__init__(master, fg_color=BG0, corner_radius=4,
                         border_width=1, border_color=LINE2,
                         label_text=title, label_font=F["mono_sb"],
                         label_fg_color=BG2, label_text_color=TXT_D)
        self.on_select = on_select
        self.rows = []
        self.selected = None
        self._value = {}
        self._colors = {}

    def clear(self):
        for w in self.rows:
            w.destroy()
        self.rows = []
        self._value = {}
        self._colors = {}
        self.selected = None

    def add(self, label, value, color=TXT):
        btn = ctk.CTkButton(self, text=label, anchor="w", font=F["mono_sm"],
                            fg_color="transparent", hover_color=BG3,
                            text_color=color, corner_radius=3, height=26,
                            command=lambda b=None: self._pick(value))
        btn.pack(fill="x", padx=4, pady=1)
        self.rows.append(btn)
        self._value[value] = btn
        self._colors[value] = color

    def _pick(self, value):
        self.selected = value
        for v, b in self._value.items():
            on = (v == value)
            b.configure(fg_color=CYAN_D if on else "transparent",
                        text_color=INK if on else self._colors.get(v, TXT))
        if self.on_select:
            self.on_select(value)

    def get(self):
        return self.selected


# ==================================================== SHIP SWITCHER section =====
class SwitcherFrame(Section):
    TITLE = "SHIP SWITCHER"
    SUB = ("Fly an enemy Coalition ship. Swaps a model's .shp pair in resource.hog, "
           "then Save As a new archive — back up the original before you use it.")
    GLYPH = "⇄"

    def build(self):
        b = self.body
        b.grid_columnconfigure(0, weight=1)
        b.grid_columnconfigure(2, weight=1)
        b.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(b, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self.b_open = ghost_button(bar, "OPEN resource.hog…", self._open, width=190)
        self.b_open.pack(side="left")
        self.b_save = primary_button(bar, "SAVE AS…", self._save, width=120)
        self.b_save.pack(side="left", padx=(8, 0))
        self.b_save.configure(state="disabled")
        for fac, col in (("ALLIANCE", CYAN), ("COALITION", RED)):
            chip = ctk.CTkFrame(bar, fg_color="transparent")
            chip.pack(side="right", padx=(10, 0))
            LED(chip, color=col, bg=BG0).pack(side="left", padx=(0, 4))
            ctk.CTkLabel(chip, text=fac, font=F["mono_sm"], text_color=col).pack(side="left")

        self.fly = SelectList(b, "  FLY THIS MODEL  ·  pick a Coalition ship")
        self.fly.grid(row=1, column=0, sticky="nsew")
        mid = ctk.CTkFrame(b, fg_color="transparent", width=120)
        mid.grid(row=1, column=1, sticky="ns", padx=14)
        ctk.CTkLabel(mid, text="➤", font=ctk.CTkFont(F["_disp"], 30),
                     text_color=CYAN).pack(pady=(60, 6))
        self.b_swap = primary_button(mid, "SWAP", self._swap, width=96)
        self.b_swap.pack()
        self.b_swap.configure(state="disabled")
        self.slot = SelectList(b, "  INTO ALLIANCE SLOT  ·  the player fighters")
        self.slot.grid(row=1, column=2, sticky="nsew")

        self.log = LogPanel(b, height=104)
        self.log.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(12, 0))
        b.grid_rowconfigure(2, weight=0)

        self.entries = None
        self.path = None
        self._busy_widgets = [self.b_open, self.b_save, self.b_swap]

    def _open(self):
        p = ask_open("Open resource.hog",
                     [("HOG archive", "*.hog"), ("All files", "*.*")])
        if not p:
            return

        def work():
            return hog_pack.read_entries(p)

        def done(entries):
            self.entries = entries
            self.path = p
            self.fly.clear()
            self.slot.clear()
            for n in sorted(slswitch.all_models(entries), key=str.lower):
                fac = slswitch.faction_of(n)
                col = CYAN if fac == "Alliance" else (RED if fac == "Coalition" else TXT_D)
                self.fly.add("[%-4s] %s" % (fac[:4], n), n, color=col)
            for n, _f in sorted(slswitch.fighter_models(entries), key=lambda x: x[0].lower()):
                self.slot.add(n, n, color=TXT)
            self.b_save.configure(state="normal")
            self.b_swap.configure(state="normal")
            self.status("%d ENTRIES" % len(entries), "ok")
            self.log.line("loaded %s — %d entries" % (os.path.basename(p), len(entries)), "hi")

        self.run_async(work, done, busy="READING HOG")

    def _swap(self):
        if self.entries is None:
            return
        fly = self.fly.get()
        slot = self.slot.get()
        if not fly or not slot:
            messagebox.showwarning("Pick two", "Select a model on the left and a slot on the right.")
            return
        try:
            fly_name, changed = slswitch.swap_models(self.entries, fly, slot)
        except ValueError as e:
            messagebox.showerror("Not found", str(e))
            return
        self.status("SWAPPED (unsaved)", "warn")
        self.log.line("fly %s  →  when selecting %s" % (fly_name, slot), "ok")
        self.log.line("  changed: " + ", ".join(changed), "dim")

    def _save(self):
        if self.entries is None:
            return
        p = ask_save("Save modified resource.hog", ".hog",
                     initialfile="resource_mod.hog",
                     filetypes=[("HOG archive", "*.hog")])
        if not p:
            return

        def work():
            blob = hog_pack.build(self.entries)
            with open(p, "wb") as f:
                f.write(blob)
            return len(blob)

        def done(n):
            self.status("SAVED", "ok")
            self.log.line("wrote %s (%s bytes)" % (p, format(n, ",")), "ok")
            messagebox.showinfo("Saved",
                                "Wrote %s\n\nBack up the original, then replace it in your "
                                "game install. Verify in-game yourself." % p)

        self.run_async(work, done, busy="BUILDING HOG")


# =========================================================== STATS section ======
class StatsFrame(Section):
    TITLE = "STATS EDITOR"
    SUB = ("Edit SHIP / GUN / MISSILE stat tables. Field set auto-detected by "
           "filename; (?) marks an unconfirmed offset. Save As a new .bin.")
    GLYPH = "≣"

    def build(self):
        b = self.body
        b.grid_columnconfigure(0, weight=3)
        b.grid_columnconfigure(1, weight=2)
        b.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(b, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.b_open = ghost_button(bar, "OPEN .bin…", self._open, width=120)
        self.b_open.pack(side="left")
        self.b_save = primary_button(bar, "SAVE AS…", self._save, width=120)
        self.b_save.pack(side="left", padx=(8, 0))
        self.b_save.configure(state="disabled")

        # records table (themed ttk.Treeview)
        self.app.ensure_tree_style()
        tw = ctk.CTkFrame(b, fg_color=BG0, corner_radius=4, border_width=1, border_color=LINE2)
        tw.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        tw.grid_rowconfigure(0, weight=1)
        tw.grid_columnconfigure(0, weight=1)
        cols = ("name", "faction", "k0", "k1", "k2")
        self.tree = ttk.Treeview(tw, columns=cols, show="headings", style="SL.Treeview")
        self.tree.heading("name", text="NAME")
        self.tree.column("name", width=170)
        self.tree.heading("faction", text="FAC")
        self.tree.column("faction", width=56, anchor="center")
        for c in ("k0", "k1", "k2"):
            self.tree.heading(c, text="")
            self.tree.column(c, width=78, anchor="e")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        sb = ttk.Scrollbar(tw, orient="vertical", command=self.tree.yview, style="SL.Vertical.TScrollbar")
        sb.grid(row=0, column=1, sticky="ns", pady=6)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # field form
        self.form = hud_panel(b)
        self.form.grid(row=1, column=1, sticky="nsew")
        self.form.grid_columnconfigure(0, weight=1)
        panel_title(self.form, "RECORD FIELDS").grid(row=0, column=0, sticky="w",
                                                     padx=14, pady=(12, 6))
        self.fields_holder = ctk.CTkScrollableFrame(self.form, fg_color="transparent")
        self.fields_holder.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        self.form.grid_rowconfigure(1, weight=1)
        self.b_apply = primary_button(self.form, "APPLY TO RECORD", self._apply, width=180)
        self.b_apply.grid(row=2, column=0, pady=12)
        self.b_apply.configure(state="disabled")

        self.data = None
        self.path = None
        self.fields = slstats.SHIP_FIELDS
        self.entries = {}
        self._busy_widgets = [self.b_open, self.b_save, self.b_apply]

    def _open(self):
        p = ask_open("Open a stat table",
                     [("Stat tables", "*.bin"), ("All files", "*.*")])
        if not p:
            return
        try:
            self.data = slstats.load(p)
        except Exception as e:
            self.default_error(e)
            return
        self.path = p
        self.fields = slstats.fields_for(p)
        keys = self.fields[:3]
        for n, (_, lbl, _) in zip(("k0", "k1", "k2"), keys):
            self.tree.heading(n, text=lbl.upper())
        self._refresh_tree(keys)
        self._build_form()
        self.b_save.configure(state="normal")
        self.b_apply.configure(state="normal")
        kind = ("GUN" if "gun" in os.path.basename(p).lower() else
                "MISSILE" if "missile" in os.path.basename(p).lower() else "SHIP")
        self.status("%s · %d REC" % (kind, slstats.num_records(self.data)), "ok")

    def _refresh_tree(self, keys):
        self.tree.delete(*self.tree.get_children())
        for i in range(slstats.num_records(self.data)):
            name = slstats.rec_name(self.data, i)
            if not name:
                continue
            vals = [name, slstats.faction(name)]
            vals += ["%g" % slstats.stat(self.data, i, off) for off, _, _ in keys]
            while len(vals) < 5:
                vals.append("")
            self.tree.insert("", "end", iid=str(i), values=vals)

    def _build_form(self):
        for w in self.fields_holder.winfo_children():
            w.destroy()
        self.entries = {}
        for off, label, conf in self.fields:
            row = ctk.CTkFrame(self.fields_holder, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=label + ("" if conf else " (?)"), font=F["small"],
                         text_color=TXT if conf else TXT_DD, width=150,
                         anchor="w").pack(side="left")
            var = tk.StringVar()
            hud_entry(row, textvariable=var, width=96).pack(side="right")
            self.entries[off] = var

    def _sel_index(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def _on_select(self, _evt):
        i = self._sel_index()
        if i is None or self.data is None:
            return
        for off, var in self.entries.items():
            var.set("%g" % slstats.stat(self.data, i, off))

    def _apply(self):
        i = self._sel_index()
        if i is None:
            messagebox.showinfo("No record", "Select a record in the table first.")
            return
        try:
            vals = {off: float(var.get()) for off, var in self.entries.items()}
        except ValueError:
            messagebox.showerror("Bad value", "All fields must be numbers.")
            return
        for off, v in vals.items():
            slstats.set_stat(self.data, i, off, v)
        name = slstats.rec_name(self.data, i)
        row = [name, slstats.faction(name)] + ["%g" % slstats.stat(self.data, i, off)
                                               for off, _, _ in self.fields[:3]]
        self.tree.item(str(i), values=row)
        self.status("EDITED #%d (unsaved)" % i, "warn")

    def _save(self):
        if self.data is None:
            return
        p = ask_save("Save stat table", ".bin",
                     initialfile=os.path.basename(self.path or "stats.bin"),
                     filetypes=[("Stat table", "*.bin")])
        if not p:
            return
        with open(p, "wb") as f:
            f.write(self.data)
        self.status("SAVED", "ok")
        messagebox.showinfo("Saved", "Wrote %s" % p)


# ============================================================ HOG TOOLS section =
class HogToolsFrame(Section):
    TITLE = "HOG TOOLS"
    SUB = ("Inspect and rebuild .HOG (EA BIGF) archives: list, extract, pack a folder, "
           "or replace / rename a single entry.")
    GLYPH = "▦"

    def build(self):
        b = self.body
        b.grid_columnconfigure(0, weight=1)
        b.grid_rowconfigure(0, weight=1)

        tv = ctk.CTkTabview(b, fg_color=BG1, segmented_button_fg_color=BG2,
                            segmented_button_selected_color=CYAN_D,
                            segmented_button_selected_hover_color=CYAN,
                            segmented_button_unselected_color=BG2,
                            segmented_button_unselected_hover_color=BG3,
                            text_color=TXT, corner_radius=4, border_width=1,
                            border_color=LINE2)
        tv.grid(row=0, column=0, sticky="nsew")
        for name in ("LIST", "EXTRACT", "PACK", "REPLACE", "RENAME"):
            tv.add(name)
        self._tab_list(tv.tab("LIST"))
        self._tab_extract(tv.tab("EXTRACT"))
        self._tab_pack(tv.tab("PACK"))
        self._tab_replace(tv.tab("REPLACE"))
        self._tab_rename(tv.tab("RENAME"))

        self.log = LogPanel(b, height=120)
        self.log.grid(row=1, column=0, sticky="ew", pady=(12, 0))

    # ---- small reusable file-row -------------------------------------------
    def _filerow(self, master, label, var, cmd, r=0):
        ctk.CTkLabel(master, text=label, font=F["small"], text_color=TXT_D,
                     width=130, anchor="w").grid(row=r, column=0, sticky="w", padx=4, pady=5)
        hud_entry(master, textvariable=var).grid(row=r, column=1, sticky="ew", padx=4, pady=5)
        ghost_button(master, "BROWSE", cmd, width=84, height=32).grid(row=r, column=2, padx=4, pady=5)
        master.grid_columnconfigure(1, weight=1)

    # ---- LIST ---------------------------------------------------------------
    def _tab_list(self, t):
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(1, weight=1)
        self.list_hog = tk.StringVar()
        top = ctk.CTkFrame(t, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        self._filerow(top, "Archive (.hog)", self.list_hog, lambda: self._browse_hog(self.list_hog, self._do_list))
        self.app.ensure_tree_style()
        wrap = ctk.CTkFrame(t, fg_color=BG0, corner_radius=4, border_width=1, border_color=LINE2)
        wrap.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_columnconfigure(0, weight=1)
        cols = ("idx", "name", "size", "offset")
        self.list_tree = ttk.Treeview(wrap, columns=cols, show="headings", style="SL.Treeview")
        for c, w, a in (("idx", 54, "e"), ("name", 320, "w"), ("size", 100, "e"), ("offset", 110, "e")):
            self.list_tree.heading(c, text=c.upper())
            self.list_tree.column(c, width=w, anchor=a)
        self.list_tree.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.list_tree.yview, style="SL.Vertical.TScrollbar")
        sb.grid(row=0, column=1, sticky="ns", pady=6)
        self.list_tree.configure(yscrollcommand=sb.set)

    def _do_list(self, p=None):
        p = p or self.list_hog.get().strip()
        if not p:
            return
        try:
            data = open(p, "rb").read()
            _sz, num, start, toc = hog_extract.parse(data)
        except Exception as e:
            self.default_error(e)
            return
        self.list_tree.delete(*self.list_tree.get_children())
        for i, (name, off, length) in enumerate(toc):
            self.list_tree.insert("", "end", values=(i, name, format(length, ","), "0x%08X" % off))
        self.status("%d FILES" % num, "ok")
        self.log.line("listed %s — %d files, data @ 0x%X" % (os.path.basename(p), num, start), "hi")

    # ---- EXTRACT ------------------------------------------------------------
    def _tab_extract(self, t):
        t.grid_columnconfigure(0, weight=1)
        self.ex_hog = tk.StringVar()
        self.ex_out = tk.StringVar()
        self.ex_only = tk.StringVar()
        top = ctk.CTkFrame(t, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        self._filerow(top, "Archive (.hog)", self.ex_hog, lambda: self._browse_hog(self.ex_hog), 0)
        self._filerow(top, "Output folder", self.ex_out, lambda: self._browse_dir(self.ex_out), 1)
        ctk.CTkLabel(top, text="Only this name", font=F["small"], text_color=TXT_D,
                     width=130, anchor="w").grid(row=2, column=0, sticky="w", padx=4, pady=5)
        hud_entry(top, textvariable=self.ex_only).grid(row=2, column=1, sticky="ew", padx=4, pady=5)
        ctk.CTkLabel(top, text="(blank = all)", font=F["tiny"], text_color=TXT_DD).grid(row=2, column=2, padx=4)
        self.b_extract = primary_button(t, "▼  EXTRACT", self._do_extract, width=140)
        self.b_extract.grid(row=1, column=0, sticky="w", pady=12)
        self._busy_widgets.append(self.b_extract)

    def _do_extract(self):
        hog = self.ex_hog.get().strip()
        outdir = self.ex_out.get().strip()
        only = self.ex_only.get().strip() or None
        if not hog or not outdir:
            messagebox.showwarning("Need paths", "Pick an archive and an output folder.")
            return
        self.log.rule("EXTRACT")

        def work():
            data = open(hog, "rb").read()
            _sz, num, _start, toc = hog_extract.parse(data)
            want = {only.lower()} if only else None
            n, skipped = 0, []
            for name, off, length in toc:
                if want and name.lower() not in want:
                    continue
                if off + length > len(data):
                    skipped.append(name + " (range)")
                    continue
                dest = hog_extract.safe_join(outdir, name)
                if not dest:
                    skipped.append(name + " (unsafe)")
                    continue
                os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
                with open(dest, "wb") as f:
                    f.write(data[off:off + length])
                n += 1
            return n, num, skipped

        def done(res):
            n, num, skipped = res
            self.log.line("extracted %d / %d file(s) → %s" % (n, num, outdir), "ok")
            for s in skipped[:8]:
                self.log.line("  skipped " + s, "warn")
            self.status("EXTRACTED %d" % n, "ok")

        self.run_async(work, done, busy="EXTRACTING")

    # ---- PACK ---------------------------------------------------------------
    def _tab_pack(self, t):
        t.grid_columnconfigure(0, weight=1)
        self.pk_dir = tk.StringVar()
        self.pk_out = tk.StringVar()
        top = ctk.CTkFrame(t, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        self._filerow(top, "Source folder", self.pk_dir, lambda: self._browse_dir(self.pk_dir), 0)
        self._filerow(top, "Output (.hog)", self.pk_out, lambda: self._browse_save(self.pk_out, "resource.hog"), 1)
        self.b_pack = primary_button(t, "▲  PACK FOLDER", self._do_pack, width=160)
        self.b_pack.grid(row=1, column=0, sticky="w", pady=12)
        self._busy_widgets.append(self.b_pack)

    def _do_pack(self):
        src = self.pk_dir.get().strip()
        out = self.pk_out.get().strip()
        if not src or not out:
            messagebox.showwarning("Need paths", "Pick a source folder and an output file.")
            return
        self.log.rule("PACK")

        def work():
            entries = []
            for dp, _d, files in os.walk(src):
                for f in sorted(files):
                    full = os.path.join(dp, f)
                    rel = os.path.relpath(full, src).replace(os.sep, "\\")
                    with open(full, "rb") as fh:
                        entries.append((rel, fh.read()))
            blob = hog_pack.build(entries)
            with open(out, "wb") as f:
                f.write(blob)
            return len(entries), len(blob)

        def done(res):
            n, size = res
            self.log.line("packed %d files → %s (%s bytes)" % (n, out, format(size, ",")), "ok")
            self.status("PACKED %d" % n, "ok")

        self.run_async(work, done, busy="PACKING")

    # ---- REPLACE / RENAME ---------------------------------------------------
    def _tab_replace(self, t):
        t.grid_columnconfigure(0, weight=1)
        self.rp_hog = tk.StringVar()
        self.rp_file = tk.StringVar()
        self.rp_out = tk.StringVar()
        self.rp_name = tk.StringVar(value="(load a .hog)")
        top = ctk.CTkFrame(t, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        self._filerow(top, "Archive (.hog)", self.rp_hog,
                      lambda: self._browse_hog(self.rp_hog, lambda p: self._load_names(p, self.rp_menu, self.rp_name)), 0)
        ctk.CTkLabel(top, text="Entry to replace", font=F["small"], text_color=TXT_D,
                     width=130, anchor="w").grid(row=1, column=0, sticky="w", padx=4, pady=5)
        self.rp_menu = ctk.CTkOptionMenu(top, values=["(load a .hog)"], variable=self.rp_name,
                                         font=F["mono_sm"], dropdown_font=F["mono_sm"], fg_color=BG0,
                                         button_color=BG3, button_hover_color=LINE2, text_color=TXT,
                                         dropdown_fg_color=BG2, dropdown_text_color=TXT, corner_radius=3)
        self.rp_menu.grid(row=1, column=1, sticky="ew", padx=4, pady=5)
        self._filerow(top, "Replacement file", self.rp_file, lambda: self._browse_any(self.rp_file), 2)
        self._filerow(top, "Output (.hog)", self.rp_out, lambda: self._browse_save(self.rp_out, "resource_mod.hog"), 3)
        self.b_replace = primary_button(t, "REPLACE ENTRY", self._do_replace, width=160)
        self.b_replace.grid(row=1, column=0, sticky="w", pady=12)
        self._busy_widgets.append(self.b_replace)

    def _tab_rename(self, t):
        t.grid_columnconfigure(0, weight=1)
        self.rn_hog = tk.StringVar()
        self.rn_new = tk.StringVar()
        self.rn_out = tk.StringVar()
        self.rn_name = tk.StringVar(value="(load a .hog)")
        top = ctk.CTkFrame(t, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        self._filerow(top, "Archive (.hog)", self.rn_hog,
                      lambda: self._browse_hog(self.rn_hog, lambda p: self._load_names(p, self.rn_menu, self.rn_name)), 0)
        ctk.CTkLabel(top, text="Entry to rename", font=F["small"], text_color=TXT_D,
                     width=130, anchor="w").grid(row=1, column=0, sticky="w", padx=4, pady=5)
        self.rn_menu = ctk.CTkOptionMenu(top, values=["(load a .hog)"], variable=self.rn_name,
                                         font=F["mono_sm"], dropdown_font=F["mono_sm"], fg_color=BG0,
                                         button_color=BG3, button_hover_color=LINE2, text_color=TXT,
                                         dropdown_fg_color=BG2, dropdown_text_color=TXT, corner_radius=3)
        self.rn_menu.grid(row=1, column=1, sticky="ew", padx=4, pady=5)
        ctk.CTkLabel(top, text="New name", font=F["small"], text_color=TXT_D,
                     width=130, anchor="w").grid(row=2, column=0, sticky="w", padx=4, pady=5)
        hud_entry(top, textvariable=self.rn_new).grid(row=2, column=1, sticky="ew", padx=4, pady=5)
        self._filerow(top, "Output (.hog)", self.rn_out, lambda: self._browse_save(self.rn_out, "resource_mod.hog"), 3)
        self.b_rename = primary_button(t, "RENAME ENTRY", self._do_rename, width=160)
        self.b_rename.grid(row=1, column=0, sticky="w", pady=12)
        self._busy_widgets.append(self.b_rename)

    def _load_names(self, p, menu, var):
        try:
            entries = hog_pack.read_entries(p)
        except Exception as e:
            self.default_error(e)
            return
        names = [n for n, _ in entries]
        menu.configure(values=names or ["(empty)"])
        var.set(names[0] if names else "(empty)")
        self.log.line("loaded %d names from %s" % (len(names), os.path.basename(p)), "hi")

    def _do_replace(self):
        hog, name, newf, out = (self.rp_hog.get().strip(), self.rp_name.get(),
                                self.rp_file.get().strip(), self.rp_out.get().strip())
        if not (hog and newf and out) or name.startswith("("):
            messagebox.showwarning("Need fields", "Load a .hog, pick the entry, a replacement file, and an output.")
            return
        self.log.rule("REPLACE")

        def work():
            entries = hog_pack.read_entries(hog)
            idx = next((i for i, (n, _) in enumerate(entries) if n.lower() == name.lower()), None)
            if idx is None:
                raise ValueError("entry %r not found" % name)
            with open(newf, "rb") as f:
                nb = f.read()
            old = len(entries[idx][1])
            entries[idx] = (entries[idx][0], nb)
            with open(out, "wb") as f:
                f.write(hog_pack.build(entries))
            return entries[idx][0], old, len(nb)

        def done(res):
            nm, old, new = res
            self.log.line("replaced %r: %s → %s bytes → %s" % (nm, format(old, ","), format(new, ","), out), "ok")
            self.status("REPLACED", "ok")

        self.run_async(work, done, busy="REBUILDING")

    def _do_rename(self):
        hog, old, new, out = (self.rn_hog.get().strip(), self.rn_name.get(),
                              self.rn_new.get().strip(), self.rn_out.get().strip())
        if not (hog and new and out) or old.startswith("("):
            messagebox.showwarning("Need fields", "Load a .hog, pick the entry, a new name, and an output.")
            return
        self.log.rule("RENAME")

        def work():
            entries = hog_pack.read_entries(hog)
            idx = next((i for i, (n, _) in enumerate(entries) if n.lower() == old.lower()), None)
            if idx is None:
                raise ValueError("entry %r not found" % old)
            entries[idx] = (new, entries[idx][1])
            with open(out, "wb") as f:
                f.write(hog_pack.build(entries))
            return old, new

        def done(res):
            a, b = res
            self.log.line("renamed %r → %r → %s" % (a, b, out), "ok")
            self.status("RENAMED", "ok")

        self.run_async(work, done, busy="REBUILDING")

    # ---- shared browsers ----------------------------------------------------
    def _browse_hog(self, var, then=None):
        p = ask_open("Open .hog", [("HOG archive", "*.hog"), ("All files", "*.*")])
        if p:
            var.set(p)
            if then:
                then(p)

    def _browse_any(self, var):
        p = ask_open("Select file", [("All files", "*.*")])
        if p:
            var.set(p)

    def _browse_dir(self, var):
        p = ask_dir("Select folder")
        if p:
            var.set(p)

    def _browse_save(self, var, initial):
        p = ask_save("Save as", ".hog", initialfile=initial, filetypes=[("HOG archive", "*.hog")])
        if p:
            var.set(p)


# ======================================================= CONTROLLER section =====
SHIM_KEYS = [
    ("SeparateTriggers", "Separate triggers (LT→Rx, RT→Ry)", 1),
    ("TwistRightStickX", "Twist = right-stick X", 1),
    ("RightStickYToZ", "Right-stick Y → Z axis", 0),
    ("DPadAsPOV", "D-pad as POV hat", 1),
    ("InvertY", "Invert Y", 0),
]


class ControllerFrame(Section):
    TITLE = "CONTROLLER SHIM"
    SUB = ("Install the XInput→DirectInput proxy for modern pads. Copies dinput.dll "
           "+ a config into your game folder; runs nothing.")
    GLYPH = "⎈"

    def build(self):
        b = self.body
        b.grid_columnconfigure(0, weight=1)
        b.grid_columnconfigure(1, weight=1)
        b.grid_rowconfigure(2, weight=1)

        # target
        tp = hud_panel(b)
        tp.grid(row=0, column=0, columnspan=2, sticky="ew")
        tp.grid_columnconfigure(1, weight=1)
        panel_title(tp, "TARGET FOLDER").grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(12, 6))
        self.dir_var = tk.StringVar(value=self.app.game.folder)
        ctk.CTkLabel(tp, text="Starlancer install", font=F["small"], text_color=TXT_D,
                     width=130, anchor="w").grid(row=1, column=0, sticky="w", padx=(14, 4), pady=5)
        e = hud_entry(tp, textvariable=self.dir_var)
        e.grid(row=1, column=1, sticky="ew", pady=5)
        e.configure(state="disabled")
        ghost_button(tp, "BROWSE", self._pick_dir, width=84, height=32).grid(row=1, column=2, padx=(8, 14), pady=5)
        self.valid_lbl = ctk.CTkLabel(tp, text="no folder selected", font=F["tiny"], text_color=TXT_DD)
        self.valid_lbl.grid(row=2, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 12))

        # mapping
        mp = hud_panel(b)
        mp.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        panel_title(mp, "MAPPING").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))
        self.sw_vars = {}
        defaults = self._read_ini_defaults()
        for i, (key, label, dflt) in enumerate(SHIM_KEYS):
            v = tk.BooleanVar(value=bool(defaults.get(key.lower(), dflt)))
            self.sw_vars[key] = v
            ctk.CTkSwitch(mp, text=label, variable=v, font=F["body"], text_color=TXT,
                          progress_color=CYAN_D, button_color=TXT_D, button_hover_color=CYAN,
                          fg_color=BG3).grid(row=1 + i, column=0, sticky="w", padx=16, pady=5)
        dz_row = ctk.CTkFrame(mp, fg_color="transparent")
        dz_row.grid(row=1 + len(SHIM_KEYS), column=0, sticky="ew", padx=16, pady=(10, 14))
        self.dz_var = tk.IntVar(value=int(defaults.get("deadzone", 7849)))
        ctk.CTkLabel(dz_row, text="Deadzone", font=F["body"], text_color=TXT).pack(side="left")
        self.dz_lbl = ctk.CTkLabel(dz_row, text=str(self.dz_var.get()), font=F["mono_sm"], text_color=CYAN, width=54)
        self.dz_lbl.pack(side="right")
        ctk.CTkSlider(dz_row, from_=0, to=32767, variable=self.dz_var, number_of_steps=64,
                      progress_color=CYAN_D, button_color=CYAN, button_hover_color=CYAN, fg_color=BG3,
                      command=lambda v: self.dz_lbl.configure(text=str(int(float(v))))
                      ).pack(side="left", fill="x", expand=True, padx=12)

        # actions + status
        sp = hud_panel(b)
        sp.grid(row=1, column=1, sticky="nsew", padx=(12, 0), pady=(12, 0))
        panel_title(sp, "ACTIONS").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))
        self.b_install = primary_button(sp, "⤓  INSTALL SHIM", self._install, width=200)
        self.b_install.grid(row=1, column=0, sticky="w", padx=14, pady=4)
        self.b_uninstall = danger_button(sp, "UNINSTALL", self._uninstall, width=200)
        self.b_uninstall.grid(row=2, column=0, sticky="w", padx=14, pady=4)
        ctk.CTkLabel(sp, text="A backup of any existing dinput.dll is saved as\n"
                     "dinput.dll.xinput-bak before install.", font=F["tiny"],
                     text_color=TXT_DD, justify="left").grid(row=3, column=0, sticky="w", padx=14, pady=(8, 12))

        self.log = LogPanel(b, height=120)
        self.log.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        self._busy_widgets = [self.b_install, self.b_uninstall]
        self._check_shim_asset()

    def _check_shim_asset(self):
        src = resource_path(os.path.join("xinput_shim", "dinput.dll"))
        if os.path.exists(src):
            self.log.line("shim asset ready: %s (%s bytes)" % (src, format(os.path.getsize(src), ",")), "dim")
        else:
            self.log.line("WARNING: bundled xinput_shim/dinput.dll not found at " + src, "warn")

    def _read_ini_defaults(self):
        d = {}
        p = resource_path(os.path.join("xinput_shim", "xinput_shim.ini"))
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for ln in f:
                    m = re.match(r"\s*([A-Za-z]\w*)\s*=\s*(\S+)", ln)
                    if m:
                        try:
                            d[m.group(1).lower()] = int(m.group(2))
                        except ValueError:
                            pass
        except Exception:
            pass
        return d

    def _pick_dir(self):
        p = ask_dir("Pick your Starlancer folder (contains Lancer.exe)")
        if not p:
            return
        self.dir_var.set(p)
        self.app.game.set(p)                         # share the target with the other tabs
        self._reflect_dir()

    def _reflect_dir(self):
        p = self.dir_var.get().strip()
        has = os.path.isdir(p) and any(f.lower() == "lancer.exe" for f in os.listdir(p))
        if has:
            self.valid_lbl.configure(text="✓ Lancer.exe found", text_color=GREEN)
            self.status("READY", "ok")
        elif p:
            self.valid_lbl.configure(text="⚠ Lancer.exe not found here (you can still install)",
                                     text_color=AMBER)
            self.status("CHECK FOLDER", "warn")

    def on_show(self):                               # reflect a folder picked on another tab
        if self.app.game.folder and self.app.game.folder != self.dir_var.get():
            self.dir_var.set(self.app.game.folder)
        if self.dir_var.get().strip():
            self._reflect_dir()

    def _ini_text(self):
        vals = {k: (1 if v.get() else 0) for k, v in self.sw_vars.items()}
        vals["Deadzone"] = int(self.dz_var.get())
        src = resource_path(os.path.join("xinput_shim", "xinput_shim.ini"))
        base = None
        try:
            with open(src, "r", encoding="utf-8", errors="replace") as f:
                base = f.read()
        except Exception:
            base = None
        if base:                                    # patch known keys, keep the rest
            text = base
            for k, v in vals.items():
                pat = re.compile(r"(?im)^(\s*%s\s*=\s*).*$" % re.escape(k))
                if pat.search(text):
                    text = pat.sub(lambda m: m.group(1) + str(vals[k]), text)
                else:
                    text = text.rstrip() + "\n%s=%s\n" % (k, v)
            return text
        lines = ["[mapping]"] + ["%s=%s" % (k, v) for k, v in vals.items()]
        return "\n".join(lines) + "\n"

    def _install(self):
        folder = self.dir_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("No folder", "Pick your Starlancer folder first.")
            return
        src = resource_path(os.path.join("xinput_shim", "dinput.dll"))
        if not os.path.exists(src):
            messagebox.showerror("Missing asset", "Bundled dinput.dll not found:\n" + src)
            return
        dest = os.path.join(folder, "dinput.dll")
        ini = os.path.join(folder, "xinput_shim.ini")
        bak = dest + ".xinput-bak"
        ini_text = self._ini_text()
        self.log.rule("INSTALL")

        def work():
            backed = False
            if os.path.exists(dest) and not os.path.exists(bak):
                shutil.copyfile(dest, bak)
                backed = True
            shutil.copyfile(src, dest)
            with open(ini, "w", encoding="utf-8") as f:
                f.write(ini_text)
            return backed

        def done(backed):
            if backed:
                self.log.line("backed up existing dinput.dll → dinput.dll.xinput-bak", "warn")
            self.log.line("installed dinput.dll → " + dest, "ok")
            self.log.line("wrote xinput_shim.ini", "ok")
            self.log.line("nothing was launched. Calibrate in-game yourself.", "dim")
            self.status("INSTALLED", "ok")
            messagebox.showinfo("Installed", "XInput shim installed to:\n%s\n\nNothing was launched." % folder)

        # No try/except here: run_async returns the moment the thread starts, so a
        # handler around this call never sees the worker's error. PermissionError is
        # routed to Section.default_error, which words it for this exact case.
        self.run_async(work, done, busy="INSTALLING")

    def _uninstall(self):
        folder = self.dir_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("No folder", "Pick your Starlancer folder first.")
            return
        dest = os.path.join(folder, "dinput.dll")
        ini = os.path.join(folder, "xinput_shim.ini")
        bak = dest + ".xinput-bak"
        self.log.rule("UNINSTALL")
        removed = []
        try:
            for p in (dest, ini):
                if os.path.exists(p):
                    os.remove(p)
                    removed.append(os.path.basename(p))
            if os.path.exists(bak):
                if messagebox.askyesno("Restore backup", "Restore the original dinput.dll from "
                                       "dinput.dll.xinput-bak?"):
                    shutil.move(bak, dest)
                    self.log.line("restored original dinput.dll from backup", "ok")
        except PermissionError:
            messagebox.showerror("Permission denied", "Run as administrator, or use a writable copy.")
            return
        self.log.line("removed: " + (", ".join(removed) if removed else "(nothing present)"), "ok")
        self.status("UNINSTALLED", "ok")


# ======================================================== BOOT VIDEOS section ===
def _find_blank_bik():
    """Locate a real black blank.bik (esc0rtd3w's blank-intro-videos clip) IF the user supplied
    one: bundled inside the frozen exe (sys._MEIPASS/assets), or dropped into tools/assets/ for
    source runs. The clip is third-party and never ships in this repo (*.bik is git-ignored), so on
    a fresh clone this returns None and _blank_bytes() falls back to the project's own generated
    zero-frame clip (blank_boot_videos.make_blank_bik, version-matched to the clip being replaced)
    -- the RE-backed method described in docs/modern-fixes.md s1. Either way the Boot Videos log
    says which one is in use."""
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (resource_path(os.path.join("assets", "blank.bik")),
              os.path.join(here, "assets", "blank.bik")):
        if os.path.exists(p):
            return p
    return None


def _blank_bytes(ver=b"i"):
    """Replacement bytes for a blanked clip: the real black blank.bik when available
    (the verified method), else a version-matched zero-frame stub. -> (bytes, label)."""
    p = _find_blank_bik()
    if p:
        try:
            with open(p, "rb") as f:
                return f.read(), os.path.basename(p)
        except Exception:
            pass
    return bootvid.make_blank_bik(ver), "generated stub"


# Retail truth (docs/modern-fixes.md s1, verified 2026-06-12): the three startup logos are LOOSE
# .bik files in the game folder (NOT in any HOG); "splash to mm.bik" is loose too; only the campaign
# intro new_intro.bik lives in a HOG (CD2.HOG). So the primary method is loose-file replacement.
LOOSE_LOGOS = list(bootvid.LOGO_VIDEOS)       # warty_ / new_dalogo / new_nms
LOOSE_SPLASH = list(bootvid.SPLASH_VIDEOS)    # splash to mm.bik
_LOOSE_ALL = {n.lower() for n in LOOSE_LOGOS + LOOSE_SPLASH}


class BootVideoFrame(Section):
    TITLE = "BOOT VIDEOS"
    SUB = ("Skip the startup branding logos. On a retail install the logos are LOOSE .bik files in "
           "the game folder — blanked in place with a black blank.bik if one is bundled, else with a "
           "generated zero-frame clip (.orig backups kept either way).")
    GLYPH = "▷"

    def build(self):
        b = self.body
        b.grid_columnconfigure(0, weight=1)
        b.grid_rowconfigure(0, weight=1)

        tv = ctk.CTkTabview(b, fg_color=BG1, segmented_button_fg_color=BG2,
                            segmented_button_selected_color=CYAN_D,
                            segmented_button_selected_hover_color=CYAN,
                            segmented_button_unselected_color=BG2,
                            segmented_button_unselected_hover_color=BG3,
                            text_color=TXT, corner_radius=4, border_width=1, border_color=LINE2)
        tv.grid(row=0, column=0, sticky="nsew")
        tv.add("GAME FOLDER")
        tv.add("HOG ARCHIVE")
        self._tab_folder(tv.tab("GAME FOLDER"))
        self._tab_hog(tv.tab("HOG ARCHIVE"))

        self.log = LogPanel(b, height=104)
        self.log.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        bp = _find_blank_bik()
        self.log.line("blank.bik: " + (bp if bp else "NOT FOUND — will fall back to a generated stub"),
                      "dim" if bp else "warn")
        self.hog = None
        self.toc = None

    # ---------------- primary: loose .bik in the game folder ----------------
    def _tab_folder(self, t):
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(t, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text="Starlancer folder", font=F["small"], text_color=TXT_D,
                     width=120, anchor="w").grid(row=0, column=0, sticky="w", padx=4, pady=6)
        self.gf_var = tk.StringVar(value=self.app.game.folder)
        e = hud_entry(top, textvariable=self.gf_var)
        e.grid(row=0, column=1, sticky="ew", pady=6)
        e.configure(state="disabled")
        ghost_button(top, "BROWSE", self._pick_folder, width=84, height=32).grid(row=0, column=2, padx=4, pady=6)

        self.inc_splash_f = tk.BooleanVar(value=False)
        opt = ctk.CTkFrame(t, fg_color="transparent")
        opt.grid(row=1, column=0, sticky="ew", pady=(2, 4))
        ctk.CTkCheckBox(opt, text='also blank "splash to mm.bik"', variable=self.inc_splash_f,
                        font=F["small"], text_color=TXT_D, checkbox_width=18, checkbox_height=18,
                        corner_radius=3, fg_color=CYAN_D, hover_color=CYAN, border_color=LINE2,
                        command=self._scan_folder).pack(side="left", padx=4)
        ctk.CTkLabel(opt, text="(the campaign intro new_intro.bik is in CD2.HOG — use the HOG tab)",
                     font=F["tiny"], text_color=TXT_DD).pack(side="left", padx=8)

        self.gf_list = ctk.CTkScrollableFrame(t, fg_color=BG0, corner_radius=3,
                                              label_text="  LOOSE STARTUP CLIPS", label_font=F["mono_sb"],
                                              label_fg_color=BG2, label_text_color=TXT_D)
        self.gf_list.grid(row=2, column=0, sticky="nsew", pady=(4, 8))

        acts = ctk.CTkFrame(t, fg_color="transparent")
        acts.grid(row=3, column=0, sticky="ew")
        self.b_blank_f = primary_button(acts, "■  BLANK LOGOS", self._blank_folder, width=170)
        self.b_blank_f.pack(side="left")
        self.b_restore_f = ghost_button(acts, "RESTORE (.orig)", self._restore_folder, width=150)
        self.b_restore_f.pack(side="left", padx=(8, 0))

    def _pick_folder(self):
        p = ask_dir("Pick your Starlancer folder (has Lancer.exe + the logo .bik files)")
        if p:
            self.gf_var.set(p)
            self.app.game.set(p)                     # share the target with the other tabs
            self._scan_folder()

    def on_show(self):                               # reflect a folder picked on another tab
        if self.app.game.folder and self.app.game.folder != self.gf_var.get():
            self.gf_var.set(self.app.game.folder)
        if self.gf_var.get().strip():
            self._scan_folder()

    def _loose_targets(self):
        names = {n.lower() for n in LOOSE_LOGOS}
        if self.inc_splash_f.get():
            names |= {n.lower() for n in LOOSE_SPLASH}
        return names

    def _scan_folder(self):
        for w in self.gf_list.winfo_children():
            w.destroy()
        folder = self.gf_var.get().strip()
        if not folder or not os.path.isdir(folder):
            return
        try:
            by_lower = {f.lower(): f for f in os.listdir(folder)}
        except Exception as e:
            self.default_error(e)
            return
        found = 0
        for tname in sorted(self._loose_targets()):
            actual = by_lower.get(tname)
            has_orig = (tname + ".orig") in by_lower
            row = ctk.CTkFrame(self.gf_list, fg_color="transparent")
            row.pack(fill="x", padx=2, pady=2)
            if actual:
                found += 1
                col = AMBER if has_orig else GREEN
                LED(row, color=col, bg=BG0).pack(side="left", padx=6, pady=4)
                ctk.CTkLabel(row, text=actual, font=F["mono_sm"], text_color=TXT, width=250,
                             anchor="w").pack(side="left")
                ctk.CTkLabel(row, text="blanked (.orig kept)" if has_orig else "original",
                             font=F["tiny"], text_color=col).pack(side="left", padx=8)
            else:
                LED(row, color=TXT_DD, bg=BG0).pack(side="left", padx=6, pady=4)
                ctk.CTkLabel(row, text=tname + "   (not in this folder)", font=F["mono_sm"],
                             text_color=TXT_DD, anchor="w").pack(side="left")
        ok = "lancer.exe" in by_lower
        self.status(("%d CLIP(S)" % found) if ok else "NO Lancer.exe HERE",
                    "ok" if (found and ok) else "warn")

    def _blank_folder(self):
        folder = self.gf_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("No folder", "Pick your Starlancer folder first.")
            return
        targets = self._loose_targets()
        blob, srclabel = _blank_bytes()
        self.log.rule("BLANK (loose files)")

        def work():
            by_lower = {f.lower(): f for f in os.listdir(folder)}
            done_n = []
            for tname in targets:
                actual = by_lower.get(tname)
                if not actual:
                    continue
                full = os.path.join(folder, actual)
                bak = full + ".orig"
                if not os.path.exists(bak):          # keep the first (true) original
                    shutil.copyfile(full, bak)
                with open(full, "wb") as f:
                    f.write(blob)
                done_n.append(actual)
            return done_n, srclabel

        def done(res):
            names, src = res
            if not names:
                self.status("NO CLIPS", "warn")
                self.log.line("none of the target logos are in that folder.", "warn")
                return
            for n in names:
                self.log.line("blanked %s   (backup %s.orig)" % (n, n), "ok")
            self.log.line("replacement: %s" % src, "dim")
            self.status("BLANKED %d" % len(names), "ok")
            self._scan_folder()

        self.run_async(work, done, busy="BLANKING")

    def _restore_folder(self):
        folder = self.gf_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("No folder", "Pick your Starlancer folder first.")
            return
        self.log.rule("RESTORE")

        def work():
            restored = []
            for f in os.listdir(folder):
                if not f.lower().endswith(".orig"):
                    continue
                target_name = f[:-5]                 # strip ".orig"
                if target_name.lower() in _LOOSE_ALL:
                    shutil.copyfile(os.path.join(folder, f), os.path.join(folder, target_name))
                    restored.append(target_name)
            return restored

        def done(restored):
            self.log.line("restored: " + (", ".join(restored) if restored else "(no .orig backups found)"),
                          "ok" if restored else "warn")
            self.status("RESTORED %d" % len(restored), "ok" if restored else "warn")
            self._scan_folder()

        self.run_async(work, done, busy="RESTORING")

    # ---------------- fallback: blank inside a .HOG (intro / HOG-bundled builds) ----------------
    def _tab_hog(self, t):
        t.grid_columnconfigure(0, weight=1)
        t.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(t, text="For the campaign intro new_intro.bik (CD2.HOG) or unusual builds that keep "
                     "logos inside a HOG. Writes a NEW archive — never edits the original.",
                     font=F["tiny"], text_color=TXT_DD, justify="left", anchor="w",
                     wraplength=820).grid(row=0, column=0, sticky="ew", pady=(2, 8))
        bar = ctk.CTkFrame(t, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew")
        self.b_open_h = ghost_button(bar, "OPEN .hog…", self._open_hog, width=130)
        self.b_open_h.pack(side="left")
        self.inc_splash_h = tk.BooleanVar(value=False)
        self.inc_intro_h = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(bar, text="splash", variable=self.inc_splash_h, font=F["small"], text_color=TXT_D,
                        checkbox_width=18, checkbox_height=18, corner_radius=3, fg_color=CYAN_D,
                        hover_color=CYAN, border_color=LINE2, command=self._refresh_hog).pack(side="left", padx=(12, 6))
        ctk.CTkCheckBox(bar, text="intro", variable=self.inc_intro_h, font=F["small"], text_color=TXT_D,
                        checkbox_width=18, checkbox_height=18, corner_radius=3, fg_color=CYAN_D,
                        hover_color=CYAN, border_color=LINE2, command=self._refresh_hog).pack(side="left", padx=6)
        self.b_write_h = primary_button(bar, "WRITE BLANKED .hog…", self._write_hog, width=190)
        self.b_write_h.pack(side="right")
        self.b_write_h.configure(state="disabled")

        self.hog_list = ctk.CTkScrollableFrame(t, fg_color=BG0, corner_radius=3,
                                               label_text="  CLIPS IN ARCHIVE", label_font=F["mono_sb"],
                                               label_fg_color=BG2, label_text_color=TXT_D)
        self.hog_list.grid(row=2, column=0, sticky="nsew", pady=(8, 0))

    def _open_hog(self):
        p = ask_open("Open a .hog (CD2.HOG for the intro)",
                     [("HOG archive", "*.hog"), ("All files", "*.*")])
        if not p:
            return
        try:
            raw = open(p, "rb").read()
            _sz, _num, _start, self.toc = hog_extract.parse(raw)
        except Exception as e:
            self.default_error(e)
            return
        self.hog = p
        self.b_write_h.configure(state="normal")
        self.log.line("opened " + os.path.basename(p), "hi")
        self._refresh_hog()

    def _refresh_hog(self):
        for w in self.hog_list.winfo_children():
            w.destroy()
        if not self.toc:
            return
        want = bootvid.boot_targets(include_splash=True, include_intro=True)
        active = bootvid.boot_targets(self.inc_splash_h.get(), self.inc_intro_h.get())
        found = 0
        for name, off, length in self.toc:
            bn = bootvid.basename(name)
            if bn not in want:
                continue
            found += 1
            on = bn in active
            row = ctk.CTkFrame(self.hog_list, fg_color=BG2 if on else "transparent", corner_radius=3)
            row.pack(fill="x", padx=2, pady=2)
            LED(row, color=AMBER if on else TXT_DD, bg=BG2 if on else BG0).pack(side="left", padx=6, pady=4)
            ctk.CTkLabel(row, text=name, font=F["mono_sm"], text_color=TXT if on else TXT_D,
                         width=240, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=bootvid.role_of(bn), font=F["tiny"],
                         text_color=AMBER if on else TXT_DD).pack(side="left", padx=8)
        if not found:
            ctk.CTkLabel(self.hog_list, text="No startup clips in this HOG. The retail logos are loose "
                         "files — use the GAME FOLDER tab.", font=F["small"], text_color=TXT_DD,
                         wraplength=620).pack(pady=16)
            self.status("NONE IN HOG", "warn")
        else:
            self.status("%d IN HOG" % found, "ok")

    def _write_hog(self):
        if not self.hog:
            return
        out = ask_save("Save blanked .hog", ".hog",
                       initialfile=os.path.splitext(os.path.basename(self.hog))[0] + "_noboot.hog",
                       filetypes=[("HOG archive", "*.hog")])
        if not out:
            return
        inc_s, inc_i = self.inc_splash_h.get(), self.inc_intro_h.get()
        self.log.rule("BLANK (HOG)")

        def work():
            entries = hog_pack.read_entries(self.hog)
            targets = bootvid.boot_targets(inc_s, inc_i)
            changed, new = [], []
            for name, data in entries:
                if bootvid.basename(name) in targets:
                    ver = data[3:4] if data[:3] == b"BIK" else b"i"
                    blob, _ = _blank_bytes(ver)
                    changed.append((name, len(data), len(blob)))
                    new.append((name, blob))
                else:
                    new.append((name, data))
            if not changed:
                return None
            blob = hog_pack.build(new)
            with open(out, "wb") as f:
                f.write(blob)
            return changed, len(new), len(blob)

        def done(res):
            if res is None:
                self.status("NO CLIPS", "warn")
                self.log.line("no startup clips in this HOG (logos are usually loose).", "warn")
                return
            changed, n, size = res
            for name, old, new in changed:
                self.log.line("blanked %-28s %s -> %s B" % (name, format(old, ","), format(new, ",")), "ok")
            self.log.line("wrote %s (%d files, %s bytes)" % (out, n, format(size, ",")), "ok")
            self.status("BLANKED %d" % len(changed), "ok")

        self.run_async(work, done, busy="WRITING HOG")


# ================================================================ boot reveal ===
class BootOverlay(ctk.CTkFrame):
    """A brief 'system online' boot sequence shown over the app on launch."""

    LINES = [
        ("ALLIANCE NAVAL COMMAND · MAINTENANCE TERMINAL", CYAN),
        ("> mounting subsystems .............. OK", GREEN),
        ("> sl_patch / slswitch / slstats .... OK", GREEN),
        ("> hog engine / boot blanker ........ OK", GREEN),
        ("> static tooling · game NEVER launched", AMBER),
        ("STARLANCER STUDIO ONLINE", CYAN),
    ]

    def __init__(self, master, on_done):
        super().__init__(master, fg_color=BG0, corner_radius=0)
        self.on_done = on_done
        self._dead = False
        self.cv = tk.Canvas(self, bg=BG0, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.bind("<Button-1>", lambda e: self._finish())
        self.cv.bind("<Button-1>", lambda e: self._finish())
        self.after(60, self._start)

    def _start(self):
        if self._dead:
            return
        w = self.winfo_width() or 1100
        h = self.winfo_height() or 720
        cx, cy = w // 2, h // 2 - 40
        # faint starfield
        stars = [(0.12, 0.18), (0.27, 0.62), (0.41, 0.32), (0.55, 0.78), (0.68, 0.22),
                 (0.74, 0.55), (0.83, 0.4), (0.9, 0.7), (0.18, 0.82), (0.6, 0.12),
                 (0.34, 0.88), (0.47, 0.5)]
        for i, (sx, sy) in enumerate(stars):
            x, y = sx * w, sy * h
            r = 1 + (i % 3) * 0.7
            self.cv.create_oval(x - r, y - r, x + r, y + r, fill=TXT_DD, outline="")
        # emblem: concentric arcs + chevron
        for rr, col in ((64, LINE2), (48, CYAN_D), (30, CYAN)):
            self.cv.create_arc(cx - rr, cy - rr, cx + rr, cy + rr, start=35, extent=290,
                               style="arc", outline=col, width=2)
        self.cv.create_polygon(cx, cy - 16, cx - 13, cy + 10, cx, cy + 2, cx + 13, cy + 10,
                               fill=CYAN, outline="")
        self.cv.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=AMBER, outline="")
        self._ty = cy + 96
        self._typed = []
        self._reveal(0)

    def _reveal(self, i):
        if self._dead:
            return
        if i >= len(self.LINES):
            self.after(420, self._finish)
            return
        text, col = self.LINES[i]
        big = (i == 0 or i == len(self.LINES) - 1)
        w = self.winfo_width() or 1100
        self.cv.create_text(w // 2, self._ty,
                            text=text, fill=col,
                            font=(F["_disp"] if big else F["_mono"], 17 if big else 12,
                                  "bold" if big else "normal"))
        self._ty += 30 if big else 22
        self.after(150 if not big else 240, lambda: self._reveal(i + 1))

    def _finish(self):
        if self._dead:
            return
        self._dead = True
        try:
            self.place_forget()
            self.destroy()
        except Exception:
            pass
        if self.on_done:
            self.on_done()


# ============================================================= DASHBOARD section =
class DashboardFrame(Section):
    TITLE = "DASHBOARD"
    SUB = ("At-a-glance status of your Starlancer install — what's patched and installed — "
           "plus one-click recommended fixes and a backup manager. Nothing is ever launched.")
    GLYPH = "▤"

    @staticmethod
    def _logo_label(fn):
        f = fn.lower()
        if f.startswith("warty"):
            return "Warthog"
        if "dalogo" in f:
            return "Digital Anvil"
        if "nms" in f:
            return "MS Game Studios"
        return fn

    def build(self):
        b = self.body
        b.grid_columnconfigure(0, weight=1)
        b.grid_columnconfigure(1, weight=1)
        b.grid_rowconfigure(3, weight=1)

        # --- TARGET install -------------------------------------------------
        tp = hud_panel(b)
        tp.grid(row=0, column=0, columnspan=2, sticky="ew")
        tp.grid_columnconfigure(1, weight=1)
        panel_title(tp, "TARGET INSTALL").grid(row=0, column=0, columnspan=3, sticky="w",
                                               padx=14, pady=(12, 8))
        ctk.CTkLabel(tp, text="Starlancer folder", font=F["small"], text_color=TXT_D,
                     width=120, anchor="w").grid(row=1, column=0, sticky="w", padx=(14, 8), pady=5)
        self.folder_var = tk.StringVar(value=self.app.game.folder or "(no folder selected)")
        e = hud_entry(tp, textvariable=self.folder_var)
        e.grid(row=1, column=1, sticky="ew", pady=5)
        e.configure(state="disabled")
        ghost_button(tp, "BROWSE", self._browse, width=84, height=32).grid(
            row=1, column=2, padx=(8, 14), pady=5)
        srow = ctk.CTkFrame(tp, fg_color="transparent")
        srow.grid(row=2, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 12))
        self.size_led = LED(srow, color=TXT_DD, bg=BG2)
        self.size_led.pack(side="left", padx=(0, 8))
        self.size_lbl = ctk.CTkLabel(srow, text="—", font=F["mono_sm"], text_color=TXT_DD)
        self.size_lbl.pack(side="left")

        # --- STATUS CARDS ---------------------------------------------------
        cards = ctk.CTkFrame(b, fg_color="transparent")
        cards.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for c in range(3):
            cards.grid_columnconfigure(c, weight=1, uniform="cards")

        fp = hud_panel(cards)
        fp.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        panel_title(fp, "SYSTEM FIXES").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))
        self.fix_leds = {}
        dash_fixes = sl_patch.ordered_fixes()
        for i, defn in enumerate(dash_fixes):
            row = ctk.CTkFrame(fp, fg_color="transparent")
            row.grid(row=1 + i, column=0, sticky="ew", padx=14, pady=3)
            led = LED(row, color=TXT_DD, bg=BG2)
            led.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(row, text=defn.label, font=F["mono_sm"], text_color=TXT_D,
                         width=92, anchor="w").pack(side="left")
            val = ctk.CTkLabel(row, text="—", font=F["mono_sm"], text_color=TXT_DD)
            val.pack(side="left")
            self.fix_leds[defn.id] = (led, val)
        self.man_lbl = ctk.CTkLabel(fp, text="manifest —", font=F["tiny"], text_color=TXT_DD, anchor="w")
        self.man_lbl.grid(row=1 + len(dash_fixes), column=0, sticky="ew", padx=14, pady=(6, 12))

        cp = hud_panel(cards)
        cp.grid(row=0, column=1, sticky="nsew", padx=6)
        panel_title(cp, "CONTROLLER").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))
        crow = ctk.CTkFrame(cp, fg_color="transparent")
        crow.grid(row=1, column=0, sticky="ew", padx=14, pady=3)
        self.ctrl_led = LED(crow, color=TXT_DD, bg=BG2)
        self.ctrl_led.pack(side="left", padx=(0, 8))
        self.ctrl_lbl = ctk.CTkLabel(crow, text="—", font=F["mono_sm"], text_color=TXT_DD,
                                     anchor="w", justify="left", wraplength=180)
        self.ctrl_lbl.pack(side="left")
        cp.grid_rowconfigure(2, weight=1)

        bp = hud_panel(cards)
        bp.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        panel_title(bp, "BOOT LOGOS").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))
        self.boot_leds = {}
        for i, name in enumerate(LOOSE_LOGOS):
            row = ctk.CTkFrame(bp, fg_color="transparent")
            row.grid(row=1 + i, column=0, sticky="ew", padx=14, pady=3)
            led = LED(row, color=TXT_DD, bg=BG2)
            led.pack(side="left", padx=(0, 8))
            ctk.CTkLabel(row, text=self._logo_label(name), font=F["mono_sm"], text_color=TXT_D,
                         width=110, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(row, text="—", font=F["tiny"], text_color=TXT_DD)
            lbl.pack(side="left")
            self.boot_leds[name] = (led, lbl)
        bp.grid_rowconfigure(1 + len(LOOSE_LOGOS), weight=1)

        # --- QUICK ACTIONS --------------------------------------------------
        ap = hud_panel(b)
        ap.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ap.grid_columnconfigure(3, weight=1)
        panel_title(ap, "QUICK ACTIONS").grid(row=0, column=0, columnspan=4, sticky="w",
                                              padx=14, pady=(12, 8))
        ctk.CTkLabel(ap, text="Resolution", font=F["small"], text_color=TXT_D).grid(
            row=1, column=0, sticky="w", padx=(14, 6), pady=(0, 12))
        self.res_var = tk.StringVar(value="1920 x 1080")
        ctk.CTkOptionMenu(ap, values=[r for r in RES_PRESETS if not r.startswith("Custom")],
                          variable=self.res_var, width=140, font=F["mono_sm"], dropdown_font=F["mono_sm"],
                          fg_color=BG0, button_color=BG3, button_hover_color=LINE2, text_color=TXT,
                          dropdown_fg_color=BG2, dropdown_text_color=TXT, corner_radius=3
                          ).grid(row=1, column=1, sticky="w", pady=(0, 12))
        self.b_apply = primary_button(ap, "▶  APPLY RECOMMENDED FIXES", self._apply_recommended, width=270)
        self.b_apply.grid(row=1, column=2, sticky="w", padx=(12, 0), pady=(0, 12))
        ghost_button(ap, "REFRESH", self.refresh, width=92).grid(
            row=1, column=3, sticky="e", padx=(8, 14), pady=(0, 12))
        self._busy_widgets = [self.b_apply]

        # --- BACKUPS + LOG --------------------------------------------------
        self.backups = ctk.CTkScrollableFrame(b, fg_color=BG0, corner_radius=4, border_width=1,
                                              border_color=LINE2, label_text="  BACKUPS  ·  restore any time",
                                              label_font=F["mono_sb"], label_fg_color=BG2, label_text_color=TXT_D)
        self.backups.grid(row=3, column=0, sticky="nsew", padx=(0, 6), pady=(12, 0))
        self.log = LogPanel(b, height=120)
        self.log.grid(row=3, column=1, sticky="nsew", padx=(6, 0), pady=(12, 0))

    # ---- data refresh (also the on_show hook) -------------------------------
    def on_show(self):
        self.refresh()

    def refresh(self):
        folder = self.app.game.folder
        exe = self.app.game.exe
        self.folder_var.set(folder or "(no folder selected)")
        if exe and os.path.exists(exe):
            sz = os.path.getsize(exe)
            stock = (sz == sl_patch.EXPECT_SIZE)
            self.size_led.set(GREEN if stock else AMBER)
            self.size_lbl.configure(
                text="Lancer.exe · %s bytes · %s" % (
                    format(sz, ","), "analyzed stock build" if stock else "loader or modified build"),
                text_color=GREEN if stock else AMBER)
        else:
            self.size_led.set(TXT_DD)
            self.size_lbl.configure(text="no Lancer.exe found in this folder", text_color=TXT_DD)

        states, man, sha_ok = patch_states(exe)
        for key, (led, val) in self.fix_leds.items():
            state, desc = states.get(key, ("—", "")) if states else ("—", "")
            col = {"patched": GREEN, "stock": TXT_DD, "unknown": AMBER}.get(state, TXT_DD)
            led.set(col)
            val.configure(text=state.upper() + (("  " + desc) if (desc and state == "patched") else ""),
                          text_color=col)
        if man:
            self.man_lbl.configure(text="manifest " + ("✓ sha ok" if sha_ok else "⚠ sha differs"),
                                   text_color=GREEN if sha_ok else AMBER)
        else:
            self.man_lbl.configure(text="manifest — none", text_color=TXT_DD)

        cs, has_bak = shim_status(folder)
        ccol, ctext = {"ours": (GREEN, "XInput shim (ours)"),
                       "other": (AMBER, "third-party dinput.dll"),
                       "absent": (TXT_DD, "not installed")}.get(cs, (TXT_DD, "—"))
        self.ctrl_led.set(ccol)
        self.ctrl_lbl.configure(text=ctext + ("\n· .xinput-bak kept" if has_bak else ""), text_color=ccol)

        present, blanked = bootvid_status(folder)
        pl = {p.lower() for p in present}
        bl = {x.lower() for x in blanked}
        for name, (led, lbl) in self.boot_leds.items():
            nl = name.lower()
            if nl in pl:
                isb = nl in bl
                col = AMBER if isb else GREEN
                led.set(col)
                lbl.configure(text="blanked" if isb else "original", text_color=col)
            else:
                led.set(TXT_DD)
                lbl.configure(text="absent", text_color=TXT_DD)

        self._scan_backups()
        self.status("READY" if folder else "NO TARGET", "ok" if folder else "")

    def _scan_backups(self):
        for w in self.backups.winfo_children():
            w.destroy()
        folder = self.app.game.folder
        if not folder or not os.path.isdir(folder):
            ctk.CTkLabel(self.backups, text="no folder selected", font=F["small"],
                         text_color=TXT_DD).pack(pady=10)
            return
        try:
            names = os.listdir(folder)
        except Exception:
            names = []
        items = []                                    # (backup_name, restore_target)
        for n in names:
            nl = n.lower()
            if nl == "dinput.dll.xinput-bak":
                items.append((n, "dinput.dll"))
            elif nl == "lancer.exe.bak":
                items.append((n, "Lancer.exe"))
            elif nl.endswith(".orig"):
                items.append((n, n[:-5]))
        if not items:
            ctk.CTkLabel(self.backups, text="no backups in this folder yet", font=F["small"],
                         text_color=TXT_DD).pack(pady=10)
            return
        for bak, target in sorted(items, key=lambda x: x[0].lower()):
            row = ctk.CTkFrame(self.backups, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=2)
            ctk.CTkLabel(row, text="%s  →  %s" % (bak, target), font=F["mono_sm"],
                         text_color=TXT_D, anchor="w").pack(side="left")
            ghost_button(row, "RESTORE", lambda b=bak, t=target: self._restore_one(b, t),
                         width=90, height=26).pack(side="right")

    def _restore_one(self, bak, target):
        folder = self.app.game.folder
        src = os.path.join(folder, bak)
        dst = os.path.join(folder, target)
        if not messagebox.askyesno("Restore",
                                   "Restore %s\n  → %s ?\n\n(the backup itself is kept)" % (bak, target)):
            return
        self.log.rule("RESTORE")

        def work():
            shutil.copyfile(src, dst)
            return retire_manifest(dst)      # stale sidecar would misreport the restore

        def done(retired):
            self.log.line("restored %s → %s" % (bak, target), "ok")
            if retired:
                self.log.line("retired stale patch manifest → " + retired, "warn")
            self.refresh()

        self.run_async(work, done, busy="RESTORING")

    # ---- one-click recommended ----------------------------------------------
    def _res(self):
        w, h = self.res_var.get().replace(" ", "").split("x")
        return int(w), int(h)

    def _default_ini(self):
        p = resource_path(os.path.join("xinput_shim", "xinput_shim.ini"))
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception:
            return "[mapping]\nSeparateTriggers=1\nDPadAsPOV=1\nDeadzone=7849\n"

    def _browse(self):
        p = ask_dir("Pick your Starlancer install folder (contains Lancer.exe)")
        if p:
            self.app.game.set(p)
            self.refresh()

    def _apply_recommended(self):
        folder = self.app.game.folder
        exe = self.app.game.exe
        if not folder or not exe or not os.path.exists(exe):
            messagebox.showwarning("No target",
                                   "Pick your Starlancer folder (with Lancer.exe) first.")
            return
        try:
            w, h = self._res()
        except Exception:
            messagebox.showerror("Resolution", "Pick a valid resolution.")
            return
        if not messagebox.askyesno(
                "Apply recommended fixes",
                "Patch Lancer.exe in place (a Lancer.exe.bak backup is made first), install the "
                "XInput shim, and blank the boot logos in:\n\n%s\n\nThe game is NOT launched." % folder):
            return
        self.log.rule("APPLY RECOMMENDED")
        bundled_dll = resource_path(os.path.join("xinput_shim", "dinput.dll"))
        ini_text = self._default_ini()

        def work():
            out = []
            bak = exe + ".bak"
            if not os.path.exists(bak):
                shutil.copyfile(exe, bak)
                out.append(("backed up Lancer.exe → Lancer.exe.bak", "ok"))
            sel = recommended_selections(w, h)
            ok, _rc, text = run_capturing(sl_patch.apply, bak, exe, sel, force=False)
            if not ok:
                raise RuntimeError("exe patch refused:\n" + (text or "").strip())
            out.append(("patched Lancer.exe: " + describe_selections(sel), "ok"))

            dest = os.path.join(folder, "dinput.dll")
            if os.path.exists(bundled_dll):
                shimbak = dest + ".xinput-bak"
                if os.path.exists(dest) and not os.path.exists(shimbak):
                    shutil.copyfile(dest, shimbak)
                shutil.copyfile(bundled_dll, dest)
                with open(os.path.join(folder, "xinput_shim.ini"), "w", encoding="utf-8") as f:
                    f.write(ini_text)
                out.append(("installed XInput shim (dinput.dll + xinput_shim.ini)", "ok"))
            else:
                out.append(("bundled dinput.dll missing — controller shim skipped", "warn"))

            blob, _src = _blank_bytes()
            by_lower = {f.lower(): f for f in os.listdir(folder)}
            blanked = []
            for name in LOOSE_LOGOS:
                actual = by_lower.get(name.lower())
                if not actual:
                    continue
                full = os.path.join(folder, actual)
                bk = full + ".orig"
                if not os.path.exists(bk):
                    shutil.copyfile(full, bk)
                with open(full, "wb") as f:
                    f.write(blob)
                blanked.append(actual)
            out.append(("blanked %d boot logo(s)%s" % (
                len(blanked), (": " + ", ".join(blanked)) if blanked else ""),
                "ok" if blanked else "warn"))
            return out

        def done(out):
            for msg, level in out:
                self.log.line(msg, level)
            self.status("FIXES APPLIED", "ok")
            self.refresh()
            messagebox.showinfo(
                "Applied",
                "Recommended fixes applied to:\n%s\n\nThe game was NOT launched — test it yourself." % folder)

        self.run_async(work, done, busy="APPLYING")


# ========================================================= READY-TO-PLAY section =
class DeployFrame(Section):
    TITLE = "READY-TO-PLAY"
    SUB = ("Assemble a complete, patched, ready-to-run copy of Starlancer in an OUTPUT folder: "
           "copy the game, apply the EXE fixes, install the shim, blank the logos, drop in the "
           "dgVoodoo2 wrapper + sound fix, write setup notes. It stages the folder only — it "
           "never launches the game.")
    GLYPH = "⬢"

    def build(self):
        b = self.body
        b.grid_columnconfigure(0, weight=1)
        b.grid_rowconfigure(3, weight=1)

        form = hud_panel(b)
        form.grid(row=0, column=0, sticky="ew")
        form.grid_columnconfigure(1, weight=1)
        panel_title(form, "FOLDERS").grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(12, 8))
        self.src_var = tk.StringVar(value=self.app.game.folder)
        self.dst_var = tk.StringVar()
        self.drop_var = tk.StringVar(value=PREFS.get("dropins_folder", "") or self._guess_dropins())
        self._formrow(form, 1, "SOURCE  game folder", self.src_var,
                      lambda: self._pick(self.src_var, share=True))
        self._formrow(form, 2, "OUTPUT  folder (new)", self.dst_var, lambda: self._pick(self.dst_var))
        self._formrow(form, 3, "DROP-INS  (dgVoodoo2 + mss32.dll)", self.drop_var,
                      lambda: self._pick(self.drop_var, drop=True))
        ctk.CTkLabel(form, text="⚑ Patches a COPY in the OUTPUT folder; SOURCE is read-only and the "
                     "game is never launched.", font=F["tiny"], text_color=TXT_DD).grid(
                         row=4, column=0, columnspan=3, sticky="w", padx=14, pady=(2, 12))

        opt = hud_panel(b)
        opt.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        panel_title(opt, "OPTIONS").grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))
        orow = ctk.CTkFrame(opt, fg_color="transparent")
        orow.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 12))
        ctk.CTkLabel(orow, text="Resolution", font=F["small"], text_color=TXT_D).pack(side="left", padx=(0, 6))
        self.res_var = tk.StringVar(value="1920 x 1080")
        ctk.CTkOptionMenu(orow, values=["4:3 (no widescreen)"] +
                          [r for r in RES_PRESETS if not r.startswith("Custom")],
                          variable=self.res_var, width=180, font=F["mono_sm"], dropdown_font=F["mono_sm"],
                          fg_color=BG0, button_color=BG3, button_hover_color=LINE2, text_color=TXT,
                          dropdown_fg_color=BG2, dropdown_text_color=TXT, corner_radius=3).pack(side="left", padx=(0, 16))
        self.opt_shim = tk.BooleanVar(value=True)
        self.opt_logos = tk.BooleanVar(value=True)
        self.opt_dgv = tk.BooleanVar(value=True)
        self.opt_mss = tk.BooleanVar(value=True)
        for var, label in ((self.opt_shim, "XInput shim"), (self.opt_logos, "blank logos"),
                           (self.opt_dgv, "dgVoodoo2"), (self.opt_mss, "mss32 sound")):
            ctk.CTkCheckBox(orow, text=label, variable=var, font=F["small"], text_color=TXT,
                            checkbox_width=18, checkbox_height=18, corner_radius=3,
                            fg_color=CYAN_D, hover_color=CYAN, border_color=LINE2).pack(side="left", padx=(0, 12))

        acts = ctk.CTkFrame(b, fg_color="transparent")
        acts.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.b_stage = primary_button(acts, "▶  STAGE BUILD", self._stage, width=180)
        self.b_stage.pack(side="left")
        ctk.CTkLabel(acts, text="assembles an output folder only — the game is never launched",
                     font=F["tiny"], text_color=TXT_DD).pack(side="left", padx=12)
        self._busy_widgets = [self.b_stage]

        self.log = LogPanel(b, height=150)
        self.log.grid(row=3, column=0, sticky="nsew", pady=(12, 0))

    # ---- helpers ------------------------------------------------------------
    def _formrow(self, master, r, label, var, cmd):
        ctk.CTkLabel(master, text=label, font=F["small"], text_color=TXT_D, width=230,
                     anchor="w").grid(row=r, column=0, sticky="w", padx=(14, 8), pady=4)
        hud_entry(master, textvariable=var).grid(row=r, column=1, sticky="ew", pady=4)
        ghost_button(master, "BROWSE", cmd, width=84, height=32).grid(row=r, column=2, padx=(8, 14), pady=4)

    @staticmethod
    def _guess_dropins():
        """Initial drop-ins folder when no preference is saved. Third-party drop-ins (dgVoodoo2,
        mss32 ...) are never part of this repo, so there is no repo-relative place to guess:
        start empty and let the user browse; the choice is remembered in preferences."""
        return ""

    def _pick(self, var, share=False, drop=False):
        p = ask_dir("Select folder")
        if not p:
            return
        var.set(p)
        if share:
            self.app.game.set(p)
        if drop:
            PREFS.set("dropins_folder", p)

    @staticmethod
    def _copytree(src, dst):
        n = 0
        for dp, _dirs, files in os.walk(src):
            rel = os.path.relpath(dp, src)
            outdir = dst if rel == "." else os.path.join(dst, rel)
            os.makedirs(outdir, exist_ok=True)
            for f in files:
                shutil.copy2(os.path.join(dp, f), os.path.join(outdir, f))
                n += 1
        return n

    @staticmethod
    def _copy_dropins(drop, dst, filenames):
        copied = []
        if not drop or not os.path.isdir(drop):
            return copied
        index = {}
        try:
            for entry in os.listdir(drop):
                full = os.path.join(drop, entry)
                if os.path.isfile(full):
                    index.setdefault(entry.lower(), full)
                elif os.path.isdir(full):
                    try:
                        for sub in os.listdir(full):
                            sf = os.path.join(full, sub)
                            if os.path.isfile(sf):
                                index.setdefault(sub.lower(), sf)
                    except Exception:
                        pass
        except Exception:
            return copied
        for fn in filenames:
            sp = index.get(fn.lower())
            if sp:
                shutil.copyfile(sp, os.path.join(dst, fn))
                copied.append(fn)
        return copied

    def _write_notes(self, dst, o):
        fixes = describe_selections(
            recommended_selections(o["w"], o["h"], include_params=o["do_ws"]))
        lines = ["STARLANCER — READY-TO-PLAY BUILD",
                 "Assembled by Starlancer Studio. The game was NOT launched during assembly.",
                 "", "Applied:", "  - EXE fixes: " + fixes]
        if o["shim"]:
            lines.append("  - XInput controller shim (dinput.dll + xinput_shim.ini)")
        if o["logos"]:
            lines.append("  - Boot logos blanked (.orig backups kept)")
        if o["dgv"]:
            lines.append("  - dgVoodoo2 wrapper (DDraw.dll / D3DImm.dll / dgVoodoo.conf / dgVoodooCpl.exe)")
        if o["mss"]:
            lines.append("  - mss32.dll sound fix (Miles 6.0a)")
        lines += ["", "To run (do these yourself — Starlancer Studio never launches the game):",
                  "  1. Enable the legacy DirectPlay Windows feature if you want multiplayer.",
                  "  2. (Optional) Run dgVoodooCpl.exe here to tune the wrapper, then close it.",
                  "  3. Start Lancer.exe.", "",
                  "Undo the EXE fixes:  sl_patch.py --verify Lancer.exe   |   --revert Lancer.exe out.exe",
                  "A pristine Lancer.exe.bak is kept next to the patched exe."]
        path = os.path.join(dst, "READ-ME-RUN-ME.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path

    # ---- the pipeline -------------------------------------------------------
    def _build_steps(self, src, dst, o):
        def s_validate():
            exe = os.path.join(src, next(f for f in os.listdir(src) if f.lower() == "lancer.exe"))
            sz = os.path.getsize(exe)
            if sz != sl_patch.EXPECT_SIZE:
                return ("source Lancer.exe is %s bytes (not the analyzed %s) — fixes may not verify"
                        % (format(sz, ","), format(sl_patch.EXPECT_SIZE, ",")), "warn")
            return "source validated: stock Lancer.exe (%s bytes)" % format(sz, ",")

        def s_copy():
            return "copied %d files → %s" % (self._copytree(src, dst), dst)

        def s_patch():
            exe = os.path.join(dst, next(f for f in os.listdir(dst) if f.lower() == "lancer.exe"))
            bak = exe + ".bak"
            if not os.path.exists(bak):
                shutil.copyfile(exe, bak)
            sel = recommended_selections(o["w"], o["h"], include_params=o["do_ws"])
            ok, _rc, text = run_capturing(sl_patch.apply, bak, exe, sel, force=False)
            if not ok:
                raise RuntimeError("exe patch refused:\n" + (text or "").strip())
            return "patched Lancer.exe: " + describe_selections(sel)

        def s_shim():
            dll = resource_path(os.path.join("xinput_shim", "dinput.dll"))
            ini = resource_path(os.path.join("xinput_shim", "xinput_shim.ini"))
            if not os.path.exists(dll):
                return ("bundled dinput.dll missing — shim skipped", "warn")
            shutil.copyfile(dll, os.path.join(dst, "dinput.dll"))
            if os.path.exists(ini):
                shutil.copyfile(ini, os.path.join(dst, "xinput_shim.ini"))
            return "installed XInput shim (dinput.dll + xinput_shim.ini)"

        def s_logos():
            blob, _src = _blank_bytes()
            by_lower = {f.lower(): f for f in os.listdir(dst)}
            done = []
            for name in LOOSE_LOGOS:
                actual = by_lower.get(name.lower())
                if not actual:
                    continue
                full = os.path.join(dst, actual)
                bk = full + ".orig"
                if not os.path.exists(bk):
                    shutil.copyfile(full, bk)
                with open(full, "wb") as f:
                    f.write(blob)
                done.append(actual)
            return ("blanked %d boot logo(s)" % len(done) if done
                    else ("no loose logos found to blank", "warn"))

        def s_dgv():
            copied = self._copy_dropins(o["drop"], dst,
                                        ["DDraw.dll", "D3DImm.dll", "dgVoodoo.conf", "dgVoodooCpl.exe"])
            if not copied:
                return ("dgVoodoo2 files not found in the drop-ins folder — skipped "
                        "(add them there and re-run)", "warn")
            return "dropped dgVoodoo2 (copied, not run): " + ", ".join(copied)

        def s_mss():
            copied = self._copy_dropins(o["drop"], dst, ["mss32.dll"])
            if not copied:
                return ("mss32.dll not found in the drop-ins folder — skipped", "warn")
            return "dropped mss32.dll sound fix"

        def s_notes():
            return "wrote " + os.path.basename(self._write_notes(dst, o))

        steps = [("Validate source", s_validate), ("Copy game files", s_copy),
                 ("Patch executable", s_patch)]
        if o["shim"]:
            steps.append(("Install controller shim", s_shim))
        if o["logos"]:
            steps.append(("Blank boot logos", s_logos))
        if o["dgv"]:
            steps.append(("Drop dgVoodoo2 wrapper", s_dgv))
        if o["mss"]:
            steps.append(("Drop sound fix (mss32)", s_mss))
        steps.append(("Write setup notes", s_notes))
        return steps

    def _stage(self):
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        if not src or not dst:
            messagebox.showwarning("Need folders", "Pick a SOURCE game folder and an OUTPUT folder.")
            return
        if not os.path.isdir(src):
            messagebox.showerror("No source", "The SOURCE folder doesn't exist.")
            return
        if not any(f.lower() == "lancer.exe" for f in os.listdir(src)):
            messagebox.showerror("No Lancer.exe", "The SOURCE folder doesn't contain Lancer.exe.")
            return
        a_src, a_dst = os.path.abspath(src), os.path.abspath(dst)
        if a_dst == a_src or a_dst.startswith(a_src + os.sep):
            messagebox.showerror("Bad output", "OUTPUT must be a separate folder, not SOURCE or inside it.")
            return
        res = self.res_var.get()
        do_ws = not res.startswith("4:3")
        w = h = None
        if do_ws:
            try:
                ws, hs = res.replace(" ", "").split("x")
                w, h = int(ws), int(hs)
            except Exception:
                messagebox.showerror("Resolution", "Pick a valid resolution.")
                return
        if os.path.isdir(dst) and os.listdir(dst):
            if not messagebox.askyesno("Output not empty",
                                       "The OUTPUT folder isn't empty. Continue and overwrite "
                                       "matching files?"):
                return
        o = dict(shim=self.opt_shim.get(), logos=self.opt_logos.get(), dgv=self.opt_dgv.get(),
                 mss=self.opt_mss.get(), drop=self.drop_var.get().strip(), w=w, h=h, do_ws=do_ws)
        self.log.rule("STAGE BUILD")
        self.log.line("source: " + src, "dim")
        self.log.line("output: " + dst, "dim")
        self.run_steps(self._build_steps(src, dst, o), on_done=self._staged, busy="STAGING")

    def _staged(self, ok):
        if ok:
            self.log.line("build staged — launch Lancer.exe yourself; nothing was run.", "ok")
            messagebox.showinfo("Ready-to-Play",
                                "Staged a ready-to-play build in:\n%s\n\nThe game was NOT launched."
                                % self.dst_var.get())


# ===================================================================== shell =====
NAV = [
    ("dashboard", "▤", "DASHBOARD", DashboardFrame),
    ("patcher", "◈", "PATCHER", PatcherFrame),
    ("switcher", "⇄", "SHIP SWITCHER", SwitcherFrame),
    ("stats", "≣", "STATS EDITOR", StatsFrame),
    ("hog", "▦", "HOG TOOLS", HogToolsFrame),
    ("controller", "⎈", "CONTROLLER", ControllerFrame),
    ("bootvid", "▷", "BOOT VIDEOS", BootVideoFrame),
    ("deploy", "⬢", "READY-TO-PLAY", DeployFrame),
]


class NavItem(ctk.CTkFrame):
    def __init__(self, master, glyph, label, command):
        super().__init__(master, fg_color="transparent", corner_radius=0, height=44)
        self.grid_propagate(False)                   # honour the fixed height
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.bar = ctk.CTkFrame(self, width=3, height=44, fg_color="transparent", corner_radius=0)
        self.bar.grid(row=0, column=0, sticky="ns")
        self.btn = ctk.CTkButton(self, text="  %s   %s" % (glyph, label), anchor="w",
                                 font=F["nav"], fg_color="transparent", hover_color=BG2,
                                 text_color=TXT_D, corner_radius=0, command=command)
        self.btn.grid(row=0, column=1, sticky="nsew")

    def set_selected(self, on):
        self.bar.configure(fg_color=CYAN if on else "transparent")
        self.btn.configure(fg_color=BG2 if on else "transparent",
                           text_color=CYAN if on else TXT_D)


class App(ctk.CTk):
    def __init__(self, selftest=False):
        super().__init__()
        _build_fonts()
        self._tree_style_done = False

        self.title("Starlancer Studio")
        self._icon_path = resource_path(os.path.join("assets", "app.ico"))
        self._set_app_icon()
        self.geometry("1120x740")
        self.minsize(1000, 660)
        self.configure(fg_color=BG0)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.game = GameContext()                   # shared target folder/exe (all tabs)
        self._build_topbar()
        self._build_sidebar()
        self._build_content()
        self._build_footer()

        self.show(PREFS.get("section", "dashboard"))
        self.after(12, self._theme_titlebar)
        self.after(300, self._set_app_icon)         # re-assert (CTk can reset it late)

        if not selftest:
            self.boot = BootOverlay(self, on_done=self._after_boot)
            self.boot.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.boot.lift()

    # ---- ttk dark style (lazy) ---------------------------------------------
    def ensure_tree_style(self):
        if self._tree_style_done:
            return
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("SL.Treeview", background=BG1, fieldbackground=BG1, foreground=TXT,
                     bordercolor=LINE, borderwidth=0, rowheight=24, font=(F["_mono"], 10))
        st.map("SL.Treeview", background=[("selected", CYAN_D)], foreground=[("selected", INK)])
        st.configure("SL.Treeview.Heading", background=BG2, foreground=TXT_D,
                     font=(F["_disp"], 10), relief="flat", borderwidth=0)
        st.map("SL.Treeview.Heading", background=[("active", BG3)])
        st.configure("SL.Vertical.TScrollbar", background=BG2, troughcolor=BG0,
                     bordercolor=BG0, arrowcolor=TXT_D)
        self._tree_style_done = True

    def _build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, height=58)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)
        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w", padx=18, pady=10)
        ctk.CTkLabel(left, text="◉", font=ctk.CTkFont(F["_disp"], 22),
                     text_color=CYAN).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(left, text="STARLANCER", font=F["wordmark"], text_color=TXT).pack(side="left")
        ctk.CTkLabel(left, text="STUDIO", font=F["wordmark"], text_color=CYAN).pack(side="left", padx=(7, 0))
        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e", padx=18)
        self.sys_led = LED(right, color=GREEN, bg=BG1)
        self.sys_led.pack(side="left", padx=(0, 6))
        ctk.CTkLabel(right, text="SYSTEM ONLINE", font=F["mono_sm"], text_color=GREEN).pack(side="left")
        ctk.CTkLabel(right, text="│  STATIC · NO-LAUNCH", font=F["mono_sm"],
                     text_color=TXT_DD).pack(side="left", padx=(8, 0))
        ctk.CTkFrame(bar, height=1, fg_color=CYAN_D).grid(row=1, column=0, columnspan=3, sticky="ew")
        self._pulse(0)

    def _pulse(self, t):
        if not self.winfo_exists():
            return
        self.sys_led.set(GREEN if (t % 2 == 0) else "#2C7A4E")
        self.after(900, lambda: self._pulse(t + 1))

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=BG1, corner_radius=0, width=212)
        sb.grid(row=1, column=0, sticky="nsw")
        sb.grid_propagate(False)
        sb.grid_rowconfigure(2, weight=1)

        crest = tk.Canvas(sb, width=212, height=92, bg=BG1, highlightthickness=0, bd=0)
        crest.grid(row=0, column=0, sticky="ew")
        for (sx, sy, r) in [(28, 22, 1), (60, 60, 1.4), (110, 30, 1), (160, 64, 1.3),
                            (185, 28, 1), (135, 18, 0.9), (84, 40, 1)]:
            crest.create_oval(sx - r, sy - r, sx + r, sy + r, fill=TXT_DD, outline="")
        crest.create_text(18, 44, text="NAVAL ENGINEERING", anchor="w", fill=TXT_D,
                          font=(F["_disp"], 12, "bold"))
        crest.create_text(18, 64, text="MODDING SUITE", anchor="w", fill=CYAN,
                          font=(F["_disp"], 12, "bold"))
        crest.create_line(18, 80, 194, 80, fill=LINE2)

        ctk.CTkLabel(sb, text="  SUBSYSTEMS", font=F["mono_sm"], text_color=TXT_DD,
                     anchor="w").grid(row=1, column=0, sticky="ew", pady=(8, 2))
        navwrap = ctk.CTkFrame(sb, fg_color="transparent")
        navwrap.grid(row=2, column=0, sticky="new")
        navwrap.grid_columnconfigure(0, weight=1)
        self.nav_items = {}
        for i, (key, glyph, label, _cls) in enumerate(NAV):
            it = NavItem(navwrap, glyph, label, command=lambda k=key: self.show(k))
            it.grid(row=i, column=0, sticky="ew", pady=1)
            self.nav_items[key] = it

        tele = tk.Canvas(sb, width=212, height=92, bg=BG1, highlightthickness=0, bd=0)
        tele.grid(row=3, column=0, sticky="ew")
        tele.create_line(0, 6, 212, 6, fill=LINE2)
        pts = []
        for x in range(8, 205, 6):
            import math
            yy = 40 + 12 * math.sin(x / 12.0)
            pts += [x, yy]
        tele.create_line(*pts, fill=CYAN_D, width=1, smooth=True)
        tele.create_text(18, 70, text="STATIC TOOLING", anchor="w", fill=TXT_DD,
                         font=(F["_mono"], 9))
        tele.create_text(18, 84, text="%s · GAME NEVER LAUNCHED" % APP_VERSION, anchor="w",
                         fill=TXT_DD, font=(F["_mono"], 9))

    def _build_content(self):
        self.content = ctk.CTkFrame(self, fg_color=BG0, corner_radius=0)
        self.content.grid(row=1, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.sections = {}
        for key, _g, _l, cls in NAV:
            frame = cls(self.content, self)
            frame.grid(row=0, column=0, sticky="nsew")
            self.sections[key] = frame

    def _build_footer(self):
        # plain tk widgets with explicit colors -> always paints exactly BG1/amber
        ft = tk.Frame(self, bg=BG1, height=34)
        ft.grid(row=2, column=0, columnspan=2, sticky="ew")
        ft.grid_propagate(False)
        ft.pack_propagate(False)
        tk.Frame(ft, bg=AMBER, height=2).pack(side="top", fill="x")
        tk.Label(ft, text="⚑   Starlancer Studio edits and patches LOCAL COPIES only "
                 "— it never launches the game.", bg=BG1, fg=AMBER,
                 font=(F["_body"], 10), anchor="w").pack(side="left", padx=18, fill="y")

    def show(self, key):
        if key not in self.sections:
            key = "dashboard" if "dashboard" in self.sections else "patcher"
        frame = self.sections[key]
        frame.tkraise()
        for k, it in self.nav_items.items():
            it.set_selected(k == key)
        PREFS.set("section", key)
        on = getattr(frame, "on_show", None)         # let a section re-scan when raised
        if callable(on):
            try:
                on()
            except Exception:
                pass

    def _after_boot(self):
        self.boot = None

    def _set_app_icon(self):
        """Set the window/taskbar icon from the bundled app.ico (dev + frozen)."""
        try:
            if os.path.exists(self._icon_path):
                self.iconbitmap(self._icon_path)
        except Exception:
            pass

    def _theme_titlebar(self):
        """Force a dark, on-theme caption bar (Win11) instead of the system accent."""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()

            def ref(hx):
                r, g, b = int(hx[1:3], 16), int(hx[3:5], 16), int(hx[5:7], 16)
                return (b << 16) | (g << 8) | r
            dwm = ctypes.windll.dwmapi
            for attr, val in ((20, 1),            # USE_IMMERSIVE_DARK_MODE
                              (35, ref(BG1)),     # CAPTION_COLOR (Win11 22000+)
                              (36, ref(TXT))):    # TEXT_COLOR
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ctypes.c_int(val)),
                                          ctypes.sizeof(ctypes.c_int))
        except Exception:
            pass


# ===================================================================== main ======
def _save_window_png(app, path):
    """Capture the app window's own pixels via Win32 PrintWindow (DPI- and
    z-order-proof; used only by --selftest)."""
    import ctypes
    from ctypes import wintypes
    from PIL import Image
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    app.update_idletasks()
    app.update()
    hwnd = app.winfo_id()
    hwnd = user32.GetParent(hwnd) or hwnd
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        raise RuntimeError("bad window rect")
    hwndDC = user32.GetWindowDC(hwnd)
    saveDC = gdi32.CreateCompatibleDC(hwndDC)
    bmp = gdi32.CreateCompatibleBitmap(hwndDC, w, h)
    gdi32.SelectObject(saveDC, bmp)
    res = user32.PrintWindow(hwnd, saveDC, 2)        # PW_RENDERFULLCONTENT

    class BMIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                    ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]
    bi = BMIH()
    bi.biSize = ctypes.sizeof(BMIH)
    bi.biWidth, bi.biHeight = w, -h               # negative -> top-down
    bi.biPlanes, bi.biBitCount, bi.biCompression = 1, 32, 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(hwndDC, bmp, 0, h, buf, ctypes.byref(bi), 0)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    img.save(path)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(saveDC)
    user32.ReleaseDC(hwnd, hwndDC)
    return res, w, h


def _selftest(shotdir):
    os.makedirs(shotdir, exist_ok=True)
    app = App(selftest=True)
    app.update()
    app.deiconify()
    app.lift()
    keys = [k for k, *_ in NAV]

    def step(i):
        if i >= len(keys):
            app.after(150, app.destroy)
            return
        k = keys[i]
        app.show(k)
        app.update_idletasks()
        app.update()

        def shoot():
            try:
                res, w, h = _save_window_png(app, os.path.join(shotdir, k + ".png"))
                print("shot", k, w, h, "pw=%s" % res)
            except Exception as ex:                  # noqa: BLE001
                print("shot-fail", k, repr(ex))
            app.after(120, lambda: step(i + 1))

        app.after(380, shoot)

    app.after(250, lambda: step(0))
    app.mainloop()
    print("selftest done")


def main():
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        shotdir = sys.argv[i + 1] if len(sys.argv) > i + 1 else "shots"
        _selftest(shotdir)
        return
    App().mainloop()


if __name__ == "__main__":
    main()
