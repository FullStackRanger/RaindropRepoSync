#!/usr/bin/env python3
"""GUI: clip a web page to a Markdown note, optionally copying it into an Obsidian vault.

Usage:
    python web_clipper.py                       # paste a URL (clipboard URLs are pre-filled)
    python web_clipper.py https://example.com   # clip a URL straight away
    python web_clipper.py URL --no-gui --save-to ~/Notes --tags reading,ai

While the window is open it listens on http://127.0.0.1:47811 so the browser extension
or bookmarklet in browser/web-clipper/ can send the current tab. Running the script
again with a URL hands it to the open window instead of starting a second one.
"""

import argparse
import os
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote, urlsplit

from clip_bridge import DEFAULT_PORT, ClipServer, bookmarklet, focus_running, is_running, is_web_url, send_url
from clip_storage import (DEFAULT_TAGS, DOCUMENTS, DOWNLOADS, Settings, VaultError, copy_to_vault,
                          is_obsidian_vault, list_vault_folders, normalize_tag, note_filename, parse_tags,
                          relative_vault_folder, save_note)
from web_clip import Article, ClipError, build_note, clip_url

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # headless mode still works without Tk
    tk = None

HOME_DIR = Path.home()


def reveal_in_file_manager(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    elif sys.platform.startswith("win"):
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])


def obsidian_uri(path: Path) -> str:
    return "obsidian://open?path=" + quote(str(path), safe="")


class App:
    def __init__(self, root, settings: Settings, initial_url: Optional[str] = None,
                 port: int = DEFAULT_PORT, listen: bool = True):
        self.root = root
        self.root.title("Web Clipper \u2192 Markdown")
        self.root.geometry("940x900")
        self.root.minsize(760, 720)

        self.settings = settings
        self.article: Optional[Article] = None
        self.saved_path: Optional[Path] = None
        self.vault_copy_path: Optional[Path] = None
        self.pending_url: Optional[str] = None
        self.busy = False
        self.events: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.server: Optional[ClipServer] = None
        self.port = port

        self.url_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.tags_var = tk.StringVar(value=DEFAULT_TAGS)
        self.info_var = tk.StringVar(value="")
        self.save_dir_var = tk.StringVar(value=settings.save_dir or str(DOWNLOADS))
        self.copy_var = tk.BooleanVar(value=settings.copy_to_vault)
        self.vault_var = tk.StringVar(value=settings.vault_path)
        self.vault_folder_var = tk.StringVar(value=settings.vault_folder)
        self.vault_hint_var = tk.StringVar()
        self.listen_var = tk.StringVar(value="Browser button: off")
        self.status_var = tk.StringVar(value="Paste a URL and press Clip.")

        self._build_ui()
        self._refresh_vault()
        self._sync_vault_state()
        self.root.after(100, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        if listen:
            self._start_listener()
        if initial_url:
            self.url_var.set(initial_url)
            self.root.after(200, self.clip)
        else:
            self._prefill_from_clipboard()

    # ------------------------------------------------------------------ layout
    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}
        outer = ttk.Frame(self.root, padding=8)
        outer.pack(fill="both", expand=True)

        page = ttk.LabelFrame(outer, text="Web page", padding=6)
        page.pack(fill="x", **pad)
        ttk.Label(page, text="URL:").grid(row=0, column=0, sticky="w")
        self.url_entry = ttk.Entry(page, textvariable=self.url_var)
        self.url_entry.grid(row=0, column=1, sticky="ew", padx=4)
        self.url_entry.bind("<Return>", lambda _e: self.clip())
        ttk.Button(page, text="Paste", command=self.paste_url).grid(row=0, column=2, padx=2)
        self.clip_btn = ttk.Button(page, text="Clip page", command=self.clip)
        self.clip_btn.grid(row=0, column=3, padx=2)
        ttk.Label(page, textvariable=self.listen_var, foreground="#57606a").grid(
            row=1, column=1, sticky="w", padx=4, pady=(4, 0))
        ttk.Button(page, text="Copy bookmarklet", command=self.copy_bookmarklet).grid(
            row=1, column=2, columnspan=2, sticky="e", pady=(4, 0))
        page.columnconfigure(1, weight=1)

        note = ttk.LabelFrame(outer, text="Note", padding=6)
        note.pack(fill="both", expand=True, **pad)
        ttk.Label(note, text="Title:").grid(row=0, column=0, sticky="w")
        ttk.Entry(note, textvariable=self.title_var).grid(row=0, column=1, columnspan=2, sticky="ew", padx=4)
        ttk.Label(note, text="Tags:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(note, textvariable=self.tags_var).grid(row=1, column=1, sticky="ew", padx=4, pady=(4, 0))
        ttk.Label(note, text="comma or space separated \u2192 YAML front matter",
                  foreground="#57606a").grid(row=1, column=2, sticky="w", pady=(4, 0))
        ttk.Label(note, textvariable=self.info_var, foreground="#57606a").grid(
            row=2, column=0, columnspan=3, sticky="w", pady=(4, 2))
        text_frame = ttk.Frame(note)
        text_frame.grid(row=3, column=0, columnspan=3, sticky="nsew")
        self.preview = tk.Text(text_frame, wrap="word", undo=True, height=10,
                               font=("Menlo", 12) if sys.platform == "darwin" else ("TkFixedFont", 10))
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=scroll.set)
        self.preview.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        note.columnconfigure(1, weight=1)
        note.rowconfigure(3, weight=1)

        save = ttk.LabelFrame(outer, text="Save to", padding=6)
        save.pack(fill="x", **pad)
        ttk.Entry(save, textvariable=self.save_dir_var).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(save, text="Browse\u2026", command=self.pick_save_dir).grid(row=0, column=1, padx=2)
        ttk.Button(save, text="Downloads", command=lambda: self.save_dir_var.set(str(DOWNLOADS))).grid(
            row=0, column=2, padx=2)
        ttk.Button(save, text="Documents", command=lambda: self.save_dir_var.set(str(DOCUMENTS))).grid(
            row=0, column=3, padx=2)
        save.columnconfigure(0, weight=1)

        vault = ttk.LabelFrame(outer, text="Obsidian", padding=6)
        vault.pack(fill="x", **pad)
        ttk.Checkbutton(vault, text="After saving, also copy the note into my Obsidian vault",
                        variable=self.copy_var, command=self._sync_vault_state).grid(
            row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(vault, text="Vault:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.vault_entry = ttk.Entry(vault, textvariable=self.vault_var)
        self.vault_entry.grid(row=1, column=1, sticky="ew", padx=4, pady=(4, 0))
        self.vault_entry.bind("<FocusOut>", lambda _e: self._refresh_vault())
        ttk.Button(vault, text="Browse\u2026", command=self.pick_vault).grid(row=1, column=2, padx=2, pady=(4, 0))
        ttk.Label(vault, text="Folder:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        self.folder_combo = ttk.Combobox(vault, textvariable=self.vault_folder_var)
        self.folder_combo.grid(row=2, column=1, sticky="ew", padx=4, pady=(4, 0))
        ttk.Button(vault, text="Pick\u2026", command=self.pick_vault_folder).grid(
            row=2, column=2, padx=2, pady=(4, 0))
        ttk.Button(vault, text="Refresh", command=self._refresh_vault).grid(row=2, column=3, padx=2, pady=(4, 0))
        ttk.Label(vault, textvariable=self.vault_hint_var, foreground="#57606a").grid(
            row=3, column=1, columnspan=3, sticky="w", padx=4)
        vault.columnconfigure(1, weight=1)

        actions = ttk.Frame(outer)
        actions.pack(fill="x", **pad)
        self.save_btn = ttk.Button(actions, text="Save note", command=self.save, state="disabled")
        self.save_btn.pack(side="left")
        self.vault_btn = ttk.Button(actions, text="Copy to vault", command=self.copy_to_vault, state="disabled")
        self.vault_btn.pack(side="left", padx=4)
        self.reveal_btn = ttk.Button(actions, text="Show in folder", command=self.reveal, state="disabled")
        self.reveal_btn.pack(side="left", padx=4)
        self.obsidian_btn = ttk.Button(actions, text="Open in Obsidian", command=self.open_in_obsidian,
                                       state="disabled")
        self.obsidian_btn.pack(side="left", padx=4)
        self.progress = ttk.Progressbar(actions, mode="determinate", length=140)
        self.progress.pack(side="right")

        # Packed first (at the bottom) so a short window squeezes the preview, not the log.
        log_frame = ttk.LabelFrame(outer, text="Log", padding=4)
        log_frame.pack(fill="x", side="bottom", before=page, **pad)
        ttk.Label(outer, textvariable=self.status_var).pack(fill="x", side="bottom", before=log_frame, padx=8)
        self.log = tk.Text(log_frame, height=4, state="disabled", wrap="word")
        self.log.tag_configure("error", foreground="#cf222e")
        self.log.pack(fill="both", expand=True)

        mod = "Command" if sys.platform == "darwin" else "Control"
        self.root.bind(f"<{mod}-s>", lambda _e: self.save())
        self.root.bind(f"<{mod}-l>", lambda _e: (self.url_entry.focus_set(), self.url_entry.select_range(0, "end")))

    # ----------------------------------------------------------------- helpers
    def _log(self, message: str, error: bool = False):
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n", ("error",) if error else ())
        self.log.see("end")
        self.log.configure(state="disabled")

    def _run_in_background(self, work, on_done, on_error):
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

    def _remember(self):
        self.settings.save_dir = self.save_dir_var.get().strip() or str(DOWNLOADS)
        self.settings.copy_to_vault = bool(self.copy_var.get())
        self.settings.vault_path = self.vault_var.get().strip()
        self.settings.vault_folder = self.vault_folder_var.get().strip()
        try:
            self.settings.save()
        except OSError as e:
            self._log(f"Could not save settings: {e}", error=True)

    def bring_to_front(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(300, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()
        if sys.platform == "darwin":
            script = ('tell application "System Events" to set frontmost of '
                      f'(first process whose unix id is {os.getpid()}) to true')
            subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---------------------------------------------------------------- listener
    def _start_listener(self):
        self.server = ClipServer(on_url=lambda url: self.events.put(lambda: self.receive_url(url)),
                                 on_focus=lambda: self.events.put(self.bring_to_front), port=self.port)
        try:
            port = self.server.start()
        except OSError as e:
            self.server = None
            self.listen_var.set(f"Browser button: off (port {self.port} busy)")
            self._log(f"Could not listen on 127.0.0.1:{self.port} for the browser button: {e}", error=True)
            return
        self.listen_var.set(f"Browser button: listening on 127.0.0.1:{port}")

    def receive_url(self, url: str):
        self.bring_to_front()
        self._log(f"Received from browser: {url}")
        if self.busy:
            self.pending_url = url
            return
        self.url_var.set(url)
        self.clip()

    def copy_bookmarklet(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(bookmarklet(self.port))
        self.status_var.set("Bookmarklet copied \u2014 paste it as the URL of a new bookmark.")

    # -------------------------------------------------------------------- clip
    def _clipboard_text(self) -> str:
        try:
            return self.root.clipboard_get().strip()
        except tk.TclError:
            return ""

    def _prefill_from_clipboard(self):
        text = self._clipboard_text()
        if is_web_url(text) and "\n" not in text:
            self.url_var.set(text)
            self.status_var.set("URL from clipboard \u2014 press Clip page (or Return).")

    def paste_url(self):
        text = self._clipboard_text()
        if not text:
            self.status_var.set("Clipboard is empty.")
            return
        self.url_var.set(text.split()[0])
        self.clip()

    def _set_busy(self, busy: bool):
        self.busy = busy
        self.clip_btn.configure(state="disabled" if busy else "normal")
        if busy:
            self.save_btn.configure(state="disabled")
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)

    def clip(self):
        if self.busy:
            return
        url = self.url_var.get().strip()
        if not url:
            self.status_var.set("Enter a URL first.")
            return
        self._set_busy(True)
        self.status_var.set(f"Fetching {url}\u2026")
        self._run_in_background(lambda: clip_url(url), self._clip_done, self._clip_failed)

    def _clip_done(self, article: Article):
        self._set_busy(False)
        if self.article is not None and self.saved_path is None:
            self._log(f"Discarded unsaved clip: {self.article.title}")
        self.article = article
        self.saved_path = None
        self.vault_copy_path = None
        self.url_var.set(article.url)
        self.title_var.set(article.title)
        keywords = [normalize_tag(k) for k in article.tags[:5]]
        self.tags_var.set(" ".join(parse_tags(" ".join([DEFAULT_TAGS] + keywords))))
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", article.markdown)
        self.preview.edit_reset()
        details = [urlsplit(article.url).netloc, article.author, article.published and f"published {article.published}"]
        self.info_var.set(" \u00b7 ".join(d for d in details if d) + f" \u00b7 {len(article.markdown.split())} words")
        self.save_btn.configure(state="normal")
        for btn in (self.vault_btn, self.reveal_btn, self.obsidian_btn):
            btn.configure(state="disabled")
        self.status_var.set("Review the note, then Save (\u2318S / Ctrl+S).")
        self._log(f"Clipped: {article.title}")
        self._next_pending()

    def _clip_failed(self, error: Exception):
        self._set_busy(False)
        if self.article is not None and self.saved_path is None:
            self.save_btn.configure(state="normal")
        message = str(error) if isinstance(error, ClipError) else f"{type(error).__name__}: {error}"
        self.status_var.set("Could not clip that page.")
        self._log(f"Failed: {message}", error=True)
        if not self._next_pending():
            messagebox.showerror("Web Clipper", message)

    def _next_pending(self) -> bool:
        if not self.pending_url:
            return False
        url, self.pending_url = self.pending_url, None
        self.url_var.set(url)
        self.clip()
        return True

    # -------------------------------------------------------------------- save
    def pick_save_dir(self):
        folder = filedialog.askdirectory(title="Save notes to", initialdir=self.save_dir_var.get() or str(HOME_DIR),
                                         mustexist=False)
        if folder:
            self.save_dir_var.set(folder)

    def save(self):
        if self.article is None or self.busy:
            return
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("Web Clipper", "Give the note a title.")
            return
        folder = self.save_dir_var.get().strip() or str(DOWNLOADS)
        note = build_note(self.article, tags=parse_tags(self.tags_var.get()), title=title,
                          body=self.preview.get("1.0", "end"))
        fallback = urlsplit(self.article.url).netloc
        try:
            path = save_note(note, folder, note_filename(title, fallback=fallback))
        except OSError as e:
            self._log(f"Save failed: {e}", error=True)
            messagebox.showerror("Web Clipper", f"Could not save the note:\n{e}")
            return
        self.saved_path = path
        self._remember()
        self._log(f"Saved: {path}")
        self.status_var.set(f"Saved to {path}")
        self.vault_btn.configure(state="normal")
        self.reveal_btn.configure(state="normal")
        if self.copy_var.get():
            self.copy_to_vault()

    def reveal(self):
        path = self.vault_copy_path or self.saved_path
        if path:
            reveal_in_file_manager(path)

    # ------------------------------------------------------------------- vault
    def _sync_vault_state(self):
        self.settings.copy_to_vault = bool(self.copy_var.get())

    def _refresh_vault(self):
        vault = self.vault_var.get().strip()
        if not vault:
            self.vault_hint_var.set("Choose your vault folder (the one that contains .obsidian).")
            self.folder_combo.configure(values=[])
            return
        if not Path(vault).expanduser().is_dir():
            self.vault_hint_var.set("Folder not found.")
            self.folder_combo.configure(values=[])
            return
        folders = list_vault_folders(vault)
        self.folder_combo.configure(values=[""] + folders)
        hint = "Leave Folder empty for the vault root; type a new name to create it."
        if not is_obsidian_vault(vault):
            hint = "No .obsidian folder here \u2014 is this your vault? " + hint
        self.vault_hint_var.set(hint)

    def pick_vault(self):
        folder = filedialog.askdirectory(title="Choose your Obsidian vault",
                                         initialdir=self.vault_var.get() or str(HOME_DIR))
        if folder:
            self.vault_var.set(folder)
            self.vault_folder_var.set("")
            self._refresh_vault()
            self._remember()

    def pick_vault_folder(self):
        vault = self.vault_var.get().strip()
        if not vault:
            self.pick_vault()
            return
        start = Path(vault).expanduser() / self.vault_folder_var.get().strip()
        folder = filedialog.askdirectory(title="Choose a folder inside your vault",
                                         initialdir=str(start if start.is_dir() else Path(vault).expanduser()))
        if not folder:
            return
        try:
            self.vault_folder_var.set(relative_vault_folder(vault, folder))
        except VaultError as e:
            messagebox.showwarning("Web Clipper", str(e))
            return
        self._remember()

    def copy_to_vault(self):
        if self.saved_path is None:
            return
        try:
            path = copy_to_vault(self.saved_path, self.vault_var.get().strip(), self.vault_folder_var.get(),
                                 tags=parse_tags(self.tags_var.get()))
        except (VaultError, OSError) as e:
            self._log(f"Vault copy failed: {e}", error=True)
            messagebox.showerror("Web Clipper", f"Could not copy into the vault:\n{e}")
            return
        self.vault_copy_path = path
        self._remember()
        self._refresh_vault()
        self.obsidian_btn.configure(state="normal")
        self._log(f"Copied to vault: {path}")
        self.status_var.set(f"Saved to {self.saved_path.parent} and copied to vault: {path}")

    def open_in_obsidian(self):
        if self.vault_copy_path:
            webbrowser.open(obsidian_uri(self.vault_copy_path))

    def on_close(self):
        self._remember()
        if self.server:
            self.server.stop()
        self.root.destroy()


def run_headless(url: str, save_to: Optional[str], tags: Optional[str], settings: Settings) -> int:
    try:
        article = clip_url(url)
    except ClipError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    folder = save_to or settings.save_dir or str(DOWNLOADS)
    note = build_note(article, tags=parse_tags(DEFAULT_TAGS if tags is None else tags))
    path = save_note(note, folder, note_filename(article.title, fallback=urlsplit(article.url).netloc))
    print(path)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Clip a web page to a Markdown note.")
    parser.add_argument("url", nargs="?", help="page to clip")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"browser-button port (default {DEFAULT_PORT})")
    parser.add_argument("--no-listen", action="store_true", help="don't listen for the browser button")
    parser.add_argument("--no-gui", action="store_true", help="clip URL and save it without opening a window")
    parser.add_argument("--save-to", help="folder for --no-gui (default: last folder used, else ~/Downloads)")
    parser.add_argument("--tags", help=f"tags for --no-gui (default: {DEFAULT_TAGS})")
    args = parser.parse_args(argv)
    settings = Settings.load()

    if args.no_gui:
        if not args.url:
            parser.error("--no-gui needs a URL")
        return run_headless(args.url, args.save_to, args.tags, settings)

    if not args.no_listen and is_running(args.port):
        if args.url and send_url(args.url, args.port):
            print("Sent to the Web Clipper window that is already open.")
            return 0
        if not args.url and focus_running(args.port):
            print("Web Clipper is already open.")
            return 0

    if tk is None:
        print("tkinter is not available; install it (e.g. `brew install python-tk`) or use --no-gui.",
              file=sys.stderr)
        return 1
    root = tk.Tk()
    App(root, settings, initial_url=args.url, port=args.port, listen=not args.no_listen)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
