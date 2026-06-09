#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 LordBlacksun
# SPDX-License-Identifier: GPL-3.0-only
"""slstudio.py - Starlancer Studio: a GUI for the ship/stat editor + Coalition
ship-switcher. Dependency-free (Tkinter/ttk, ships with Python). Thin layer over
the validated slstats / slswitch / hog_pack libraries.

It edits DATA FILES only and NEVER launches the game.

Run:  python slstudio.py
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slstats          # noqa: E402
import hog_pack         # noqa: E402
import slswitch         # noqa: E402


class StatEditor(ttk.Frame):
    """Open a *stats.bin, browse records, edit fields, Save As."""

    def __init__(self, master):
        super().__init__(master, padding=8)
        self.path = None
        self.data = None
        self.fields = slstats.SHIP_FIELDS
        self._build()

    def _build(self):
        bar = ttk.Frame(self); bar.pack(fill="x")
        ttk.Button(bar, text="Open .bin…", command=self.open).pack(side="left")
        ttk.Button(bar, text="Save As…", command=self.save_as).pack(side="left", padx=4)
        self.status = ttk.Label(bar, text="No file loaded.")
        self.status.pack(side="left", padx=8)

        body = ttk.Frame(self); body.pack(fill="both", expand=True, pady=6)
        cols = ("name", "faction", "k0", "k1", "k2")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", height=22)
        self.tree.heading("name", text="Name"); self.tree.column("name", width=190)
        self.tree.heading("faction", text="Faction"); self.tree.column("faction", width=70, anchor="center")
        for c in ("k0", "k1", "k2"):
            self.tree.heading(c, text=""); self.tree.column(c, width=80, anchor="e")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(body, command=self.tree.yview); sb.pack(side="left", fill="y")
        self.tree.config(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        self.form = ttk.LabelFrame(body, text="Fields", padding=8)
        self.form.pack(side="left", fill="y", padx=8)
        self.entries = {}

    def open(self):
        p = filedialog.askopenfilename(title="Open a stat table",
                                       filetypes=[("Stat tables", "*.bin"), ("All files", "*.*")])
        if p:
            self.load(p)

    def load(self, p):
        try:
            self.data = slstats.load(p)
        except Exception as e:
            messagebox.showerror("Open failed", str(e)); return
        self.path = p
        self.fields = slstats.fields_for(p)
        keys = self.fields[:3]
        for n, (_, lbl, _) in zip(("k0", "k1", "k2"), keys):
            self.tree.heading(n, text=lbl)
        self._refresh_tree(keys)
        self._build_form()
        self.status.config(text=f"{os.path.basename(p)} — {slstats.num_records(self.data)} records")

    def _refresh_tree(self, keys):
        self.tree.delete(*self.tree.get_children())
        for i in range(slstats.num_records(self.data)):
            name = slstats.rec_name(self.data, i)
            if not name:
                continue
            vals = [name, slstats.faction(name)]
            vals += [f"{slstats.stat(self.data, i, off):g}" for off, _, _ in keys]
            while len(vals) < 5:
                vals.append("")
            self.tree.insert("", "end", iid=str(i), values=vals)

    def _build_form(self):
        for w in self.form.winfo_children():
            w.destroy()
        self.entries = {}
        for r, (off, label, conf) in enumerate(self.fields):
            ttk.Label(self.form, text=label + ("" if conf else " (?)")).grid(row=r, column=0, sticky="w")
            var = tk.StringVar()
            ttk.Entry(self.form, textvariable=var, width=12).grid(row=r, column=1, padx=4, pady=1)
            self.entries[off] = var
        ttk.Button(self.form, text="Apply to record", command=self.apply).grid(
            row=len(self.fields), column=0, columnspan=2, pady=8)

    def _selected_index(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def on_select(self, _evt):
        i = self._selected_index()
        if i is None or self.data is None:
            return
        for off, var in self.entries.items():
            var.set(f"{slstats.stat(self.data, i, off):g}")

    def apply(self):
        i = self._selected_index()
        if i is None:
            return
        try:
            vals = {off: float(var.get()) for off, var in self.entries.items()}
        except ValueError:
            messagebox.showerror("Bad value", "All fields must be numbers."); return
        for off, v in vals.items():
            slstats.set_stat(self.data, i, off, v)
        name = slstats.rec_name(self.data, i)
        row = [name, slstats.faction(name)] + [f"{slstats.stat(self.data, i, off):g}" for off, _, _ in self.fields[:3]]
        self.tree.item(str(i), values=row)
        self.status.config(text=f"{os.path.basename(self.path)} — edited record {i} (unsaved)")

    def save_as(self):
        if self.data is None:
            return
        p = filedialog.asksaveasfilename(defaultextension=".bin",
                                         initialfile=os.path.basename(self.path or "stats.bin"))
        if p:
            open(p, "wb").write(self.data)
            messagebox.showinfo("Saved", f"Wrote {p}")


class Switcher(ttk.Frame):
    """Open resource.hog, swap a fighter model (fly a Coalition ship), Save As."""

    def __init__(self, master):
        super().__init__(master, padding=8)
        self.hog = None
        self.entries = None
        self._build()

    def _build(self):
        bar = ttk.Frame(self); bar.pack(fill="x")
        ttk.Button(bar, text="Open resource.hog…", command=self.open).pack(side="left")
        ttk.Button(bar, text="Save As…", command=self.save_as).pack(side="left", padx=4)
        self.status = ttk.Label(bar, text="No archive loaded.")
        self.status.pack(side="left", padx=8)

        body = ttk.Frame(self); body.pack(fill="both", expand=True, pady=6)
        lf = ttk.LabelFrame(body, text="Fly this model (pick a Coalition ship)", padding=4)
        lf.pack(side="left", fill="both", expand=True)
        self.fly = tk.Listbox(lf, width=34, height=22, exportselection=False)
        self.fly.pack(side="left", fill="both", expand=True)
        s1 = ttk.Scrollbar(lf, command=self.fly.yview); s1.pack(side="left", fill="y")
        self.fly.config(yscrollcommand=s1.set)

        mid = ttk.Frame(body, padding=10); mid.pack(side="left", fill="y")
        ttk.Button(mid, text="Swap →", command=self.swap).pack(pady=24)

        sf = ttk.LabelFrame(body, text="Into Alliance slot (the 12 player fighters)", padding=4)
        sf.pack(side="left", fill="both", expand=True)
        self.slot = tk.Listbox(sf, width=28, height=22, exportselection=False)
        self.slot.pack(side="left", fill="both", expand=True)
        s2 = ttk.Scrollbar(sf, command=self.slot.yview); s2.pack(side="left", fill="y")
        self.slot.config(yscrollcommand=s2.set)

    def open(self):
        p = filedialog.askopenfilename(title="Open resource.hog",
                                       filetypes=[("HOG archive", "*.hog"), ("All files", "*.*")])
        if not p:
            return
        try:
            self.entries = hog_pack.read_entries(p)
        except Exception as e:
            messagebox.showerror("Open failed", str(e)); return
        self.hog = p
        self.fly.delete(0, "end"); self.slot.delete(0, "end")
        for n in sorted(slswitch.all_models(self.entries), key=str.lower):
            self.fly.insert("end", f"[{slswitch.faction_of(n)[:4]:<4}] {n}")
        for n, _ in sorted(slswitch.fighter_models(self.entries), key=lambda x: x[0].lower()):
            self.slot.insert("end", n)
        self.status.config(text=f"{os.path.basename(p)} — {len(self.entries)} entries")

    def swap(self):
        if self.entries is None:
            return
        fs, ss = self.fly.curselection(), self.slot.curselection()
        if not fs or not ss:
            messagebox.showwarning("Pick two", "Select a model on the left and a slot on the right."); return
        fly = self.fly.get(fs[0]).split("] ", 1)[-1].strip()
        slot = self.slot.get(ss[0]).strip()
        try:
            fly_name, changed = slswitch.swap_models(self.entries, fly, slot)
        except ValueError as e:
            messagebox.showerror("Not found", str(e)); return
        messagebox.showinfo("Swapped",
                            f"Player flies {fly_name}\nwhen selecting {slot}.\n\n"
                            f"Changed: {', '.join(changed)}\n\nNow 'Save As' a new resource.hog.")
        self.status.config(text=f"{os.path.basename(self.hog)} — swapped (unsaved)")

    def save_as(self):
        if self.entries is None:
            return
        p = filedialog.asksaveasfilename(defaultextension=".hog", initialfile="resource_mod.hog")
        if p:
            open(p, "wb").write(hog_pack.build(self.entries))
            messagebox.showinfo("Saved", f"Wrote {p}\n\nBack up the original, then replace it in your\n"
                                          f"game install to use. (Verify in-game yourself.)")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Starlancer Studio — ship editor & Coalition switcher")
        self.geometry("780x580")
        nb = ttk.Notebook(self)
        nb.add(StatEditor(nb), text="Stat Editor")
        nb.add(Switcher(nb), text="Ship Switcher")
        nb.pack(fill="both", expand=True)
        ttk.Label(self, text="Edits data files only — never launches the game.",
                  anchor="center").pack(fill="x", side="bottom")


if __name__ == "__main__":
    App().mainloop()
