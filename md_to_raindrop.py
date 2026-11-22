#!/usr/bin/env python3
"""GUI: extract links from Markdown files and save them as Raindrop.io bookmarks.

Usage:
    export RAINDROP_TOKEN="your-token"
    python md_to_raindrop.py [notes.md ...]
"""

import argparse
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional

from md_links import Link, extract_links_from_files
from raindrop_api import Collection, RaindropClient, RaindropError, SaveResult

CHECKED = "\u2611"
UNCHECKED = "\u2610"


class App:
    def __init__(self, root: tk.Tk, files: Optional[List[str]] = None):
        self.root = root
        self.root.title("Markdown \u2192 Raindrop.io")
        self.root.geometry("1000x820")
        self.root.minsize(760, 640)

        self.files: List[str] = []
        self.links: Dict[str, Link] = {}
        self.checked: Dict[str, bool] = {}
        self.collections: List[Collection] = []
        self.events: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.busy = False
        self.stop_requested = threading.Event()

        self.token_var = tk.StringVar(value=os.getenv("RAINDROP_TOKEN", ""))
        self.collection_var = tk.StringVar()
        self.tags_var = tk.StringVar()
        self.skip_existing_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Add Markdown files to get started.")
        self.count_var = tk.StringVar(value="No links")

        self._build_ui()
        self.root.after(100, self._drain_events)
        if files:
            self.add_files(files)
        if self.token_var.get():
            self.load_collections()

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill="both", expand=True)

        account = ttk.LabelFrame(outer, text="Raindrop.io", padding=6)
        account.pack(fill="x", **pad)
        ttk.Label(account, text="API token:").grid(row=0, column=0, sticky="w")
        self.token_entry = ttk.Entry(account, textvariable=self.token_var, show="\u2022", width=40)
        self.token_entry.grid(row=0, column=1, sticky="ew", padx=4)
        self.show_token_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(account, text="Show", variable=self.show_token_var,
                        command=self._toggle_token).grid(row=0, column=2, padx=4)
        self.load_btn = ttk.Button(account, text="Load collections", command=self.load_collections)
        self.load_btn.grid(row=0, column=3, padx=4)
        ttk.Label(account, text="Save to:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.collection_combo = ttk.Combobox(account, textvariable=self.collection_var, state="readonly")
        self.collection_combo.grid(row=1, column=1, columnspan=3, sticky="ew", padx=4, pady=(6, 0))
        account.columnconfigure(1, weight=1)

        files_frame = ttk.LabelFrame(outer, text="Markdown files", padding=6)
        files_frame.pack(fill="x", **pad)
        self.files_list = tk.Listbox(files_frame, height=4, selectmode="extended")
        self.files_list.grid(row=0, column=0, rowspan=3, sticky="nsew")
        ttk.Button(files_frame, text="Add files\u2026", command=self.pick_files).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(files_frame, text="Remove selected",
                   command=self.remove_selected_files).grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Button(files_frame, text="Clear", command=self.clear_files).grid(row=2, column=1, sticky="ew", padx=4)
        files_frame.columnconfigure(0, weight=1)

        links_frame = ttk.LabelFrame(outer, text="Links to save (click a row or press Space to toggle)", padding=6)
        links_frame.pack(fill="both", expand=True, **pad)
        cols = ("save", "title", "url", "source")
        self.tree = ttk.Treeview(links_frame, columns=cols, show="headings", selectmode="extended")
        for col, label, width, stretch in (
            ("save", "Save", 50, False),
            ("title", "Title", 260, True),
            ("url", "URL", 420, True),
            ("source", "Source", 160, True),
        ):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, stretch=stretch, anchor="center" if col == "save" else "w")
        self.tree.tag_configure("ok", foreground="#1a7f37")
        self.tree.tag_configure("skipped", foreground="#6e7781")
        self.tree.tag_configure("error", foreground="#cf222e")
        scroll = ttk.Scrollbar(links_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<space>", self._on_tree_space)
        links_frame.rowconfigure(0, weight=1)
        links_frame.columnconfigure(0, weight=1)

        sel_bar = ttk.Frame(links_frame)
        sel_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(sel_bar, text="Select all", command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(sel_bar, text="Select none", command=lambda: self._set_all(False)).pack(side="left", padx=4)
        ttk.Label(sel_bar, textvariable=self.count_var).pack(side="right")

        options = ttk.Frame(outer)
        options.pack(fill="x", **pad)
        ttk.Label(options, text="Tags (comma-separated):").pack(side="left")
        ttk.Entry(options, textvariable=self.tags_var, width=30).pack(side="left", padx=4)
        ttk.Checkbutton(options, text="Skip links already in Raindrop",
                        variable=self.skip_existing_var).pack(side="left", padx=12)
        self.cancel_btn = ttk.Button(options, text="Cancel", command=self.cancel_save, state="disabled")
        self.cancel_btn.pack(side="right")
        self.save_btn = ttk.Button(options, text="Save selected", command=self.save_selected)
        self.save_btn.pack(side="right", padx=4)

        self.progress = ttk.Progressbar(outer, mode="determinate")
        self.progress.pack(fill="x", **pad)
        ttk.Label(outer, textvariable=self.status_var).pack(fill="x", padx=8)

        log_frame = ttk.LabelFrame(outer, text="Log", padding=4)
        log_frame.pack(fill="both", **pad)
        self.log = tk.Text(log_frame, height=6, state="disabled", wrap="word")
        self.log.tag_configure("error", foreground="#cf222e")
        self.log.pack(fill="both", expand=True)

    def _toggle_token(self):
        self.token_entry.configure(show="" if self.show_token_var.get() else "\u2022")

    def _log(self, message: str, error: bool = False):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n", ("error",) if error else ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def _run_in_background(self, work: Callable[[], object], on_done: Callable[[object], None],
                           on_error: Callable[[Exception], None]):
        def runner():
            try:
                result = work()
            except Exception as e:  # surfaced in the GUI instead of dying silently in the thread
                self.events.put(lambda err=e: on_error(err))
            else:
                self.events.put(lambda: on_done(result))
        threading.Thread(target=runner, daemon=True).start()

    def _drain_events(self):
        try:
            while True:
                self.events.get_nowait()()
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _client(self) -> Optional[RaindropClient]:
        token = self.token_var.get().strip()
        if not token:
            messagebox.showwarning("Missing token", "Enter your Raindrop API token (or set RAINDROP_TOKEN).")
            return None
        return RaindropClient(token)

    def load_collections(self):
        client = self._client()
        if client is None:
            return
        self.load_btn.configure(state="disabled")
        self.status_var.set("Loading collections\u2026")

        def done(collections):
            self.load_btn.configure(state="normal")
            previous = self.collection_var.get()
            self.collections = collections
            labels = [self._collection_label(c) for c in collections]
            self.collection_combo.configure(values=labels)
            if previous in labels:
                self.collection_var.set(previous)
            elif labels:
                self.collection_var.set(labels[0])
            self.status_var.set(f"Loaded {len(collections)} collections.")
            self._log(f"Loaded {len(collections)} collections.")

        def failed(e):
            self.load_btn.configure(state="normal")
            self.status_var.set("Could not load collections.")
            self._log(f"Failed to load collections: {e}", error=True)
            messagebox.showerror("Raindrop.io", f"Could not load collections:\n{e}")

        self._run_in_background(client.get_collections, done, failed)

    @staticmethod
    def _collection_label(c: Collection) -> str:
        return f"{c.path} ({c.count})" if c.count else c.path

    def _selected_collection(self) -> Optional[Collection]:
        label = self.collection_var.get()
        for c in self.collections:
            if self._collection_label(c) == label:
                return c
        return None

    def pick_files(self):
        paths = filedialog.askopenfilenames(
            title="Choose Markdown files",
            filetypes=[("Markdown", "*.md *.markdown *.mdown *.mkd"), ("Text", "*.txt"), ("All files", "*")],
        )
        if paths:
            self.add_files(paths)

    def add_files(self, paths):
        for p in paths:
            p = os.path.abspath(p)
            if p not in self.files:
                self.files.append(p)
        self._refresh_files()

    def remove_selected_files(self):
        for index in reversed(self.files_list.curselection()):
            del self.files[index]
        self._refresh_files()

    def clear_files(self):
        self.files = []
        self._refresh_files()

    def _refresh_files(self):
        self.files_list.delete(0, "end")
        for p in self.files:
            self.files_list.insert("end", p)
        try:
            links = extract_links_from_files(self.files)
        except OSError as e:
            self._log(f"Could not read file: {e}", error=True)
            messagebox.showerror("Read error", str(e))
            return
        previous = self.checked
        self.links = {link.url: link for link in links}
        self.checked = {url: previous.get(url, True) for url in self.links}
        self.tree.delete(*self.tree.get_children())
        for link in links:
            source = ", ".join(os.path.basename(s) for s in link.sources)
            self.tree.insert("", "end", iid=link.url, values=(
                CHECKED if self.checked[link.url] else UNCHECKED, link.title, link.url, source))
        self._update_count()
        if self.files:
            self.status_var.set(f"Found {len(links)} unique links in {len(self.files)} file(s).")

    def _update_count(self):
        selected = sum(self.checked.values())
        self.count_var.set(f"{selected} of {len(self.links)} selected")

    def _set_checked(self, url: str, value: bool):
        self.checked[url] = value
        self.tree.set(url, "save", CHECKED if value else UNCHECKED)

    def _set_all(self, value: bool):
        for url in self.links:
            self._set_checked(url, value)
        self._update_count()

    def _on_tree_click(self, event):
        if self.busy or self.tree.identify_region(event.x, event.y) != "cell":
            return
        row = self.tree.identify_row(event.y)
        if row and self.tree.identify_column(event.x) == "#1":
            self._set_checked(row, not self.checked[row])
            self._update_count()
            return "break"

    def _on_tree_space(self, _event):
        if self.busy:
            return "break"
        rows = self.tree.selection()
        if rows:
            value = not all(self.checked[r] for r in rows)
            for r in rows:
                self._set_checked(r, value)
            self._update_count()
        return "break"

    def _set_busy(self, busy: bool):
        self.busy = busy
        self.save_btn.configure(state="disabled" if busy else "normal")
        self.load_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")

    def save_selected(self):
        to_save = [self.links[url] for url in self.links if self.checked[url]]
        if not to_save:
            messagebox.showinfo("Nothing to save", "Select at least one link.")
            return
        collection = self._selected_collection()
        if collection is None:
            messagebox.showwarning("No collection", "Load your collections and choose where to save.")
            return
        client = self._client()
        if client is None:
            return

        tags = [t.strip() for t in self.tags_var.get().split(",") if t.strip()]
        skip_existing = self.skip_existing_var.get()
        self.stop_requested.clear()
        self._set_busy(True)
        self.progress.configure(maximum=len(to_save), value=0)
        for link in to_save:
            self.tree.item(link.url, tags=())
        self.status_var.set(f"Saving {len(to_save)} links to \u201c{collection.path}\u201d\u2026")
        self._log(f"Saving {len(to_save)} links to {collection.path}\u2026")

        def on_progress(i: int, total: int, result: SaveResult):
            self.events.put(lambda: self._show_progress(i, total, result))

        def work():
            return client.save_links(to_save, collection.id, tags=tags, skip_existing=skip_existing,
                                     progress=on_progress, should_stop=self.stop_requested.is_set)

        self._run_in_background(work, lambda results: self._save_finished(results, len(to_save)), self._save_failed)

    def _show_progress(self, i: int, total: int, result: SaveResult):
        self.progress.configure(value=i)
        self.status_var.set(f"Saving {i}/{total}\u2026")
        if result.ok:
            self.tree.item(result.url, tags=("skipped",) if result.skipped else ("ok",))
            self._set_checked(result.url, False)
            self._update_count()
            self._log(f"SKIP (already saved): {result.url}" if result.skipped else f"SAVED: {result.url}")
        else:
            self.tree.item(result.url, tags=("error",))
            self._log(f"FAILED: {result.url} \u2014 {result.error}", error=True)

    def _save_finished(self, results: List[SaveResult], requested: int):
        self._set_busy(False)
        saved = sum(1 for r in results if r.ok and not r.skipped)
        skipped = sum(1 for r in results if r.skipped)
        failed = [r for r in results if not r.ok]
        summary = f"Saved {saved}, skipped {skipped}, failed {len(failed)}"
        if len(results) < requested:
            summary += f", cancelled {requested - len(results)}"
        self.status_var.set(summary + ".")
        self._log(summary + ".", error=bool(failed))
        if failed:
            messagebox.showwarning("Some links failed",
                                   f"{summary}.\nFailed links stay selected so you can retry. See the log for details.")

    def _save_failed(self, e: Exception):
        self._set_busy(False)
        message = str(e) if isinstance(e, RaindropError) else f"{type(e).__name__}: {e}"
        self.status_var.set("Save failed.")
        self._log(f"Save failed: {message}", error=True)
        messagebox.showerror("Raindrop.io", f"Save failed:\n{message}")

    def cancel_save(self):
        self.stop_requested.set()
        self.status_var.set("Cancelling after the current link\u2026")


def main():
    ap = argparse.ArgumentParser(description="Save links from Markdown files as Raindrop.io bookmarks (GUI).")
    ap.add_argument("files", nargs="*", help="Markdown files to preload.")
    args = ap.parse_args()
    root = tk.Tk()
    App(root, files=args.files)
    root.mainloop()


if __name__ == "__main__":
    main()
