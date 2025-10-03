#!/usr/bin/env python3
"""
legal_case_finder_gui.py
A simple Tkinter GUI wrapper around a PDF indexer + search (year + keyword).
OCR removed (only text PDFs supported).
"""

import os
import sqlite3
import threading
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# PDF library
import pdfplumber

# ---------- Helper functions ----------
def safe_text(s):
    return s if s else ""

def extract_text_pdfplumber(path):
    texts = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text()
                if txt:
                    texts.append(txt)
    except Exception:
        pass
    return "\n".join(texts)

def supports_fts5(conn):
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS __fts_test USING fts5(content)")
        conn.execute("DROP TABLE IF EXISTS __fts_test")
        return True
    except Exception:
        return False

def init_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files_meta (
            path TEXT PRIMARY KEY,
            mtime REAL
        )
    """)
    if supports_fts5(conn):
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
                case_name, year, path, content, tokenize='porter'
            )
        """)
        conn.commit()
        return conn, True
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cases (
                id INTEGER PRIMARY KEY,
                case_name TEXT,
                year TEXT,
                path TEXT UNIQUE,
                content TEXT
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cases_year ON cases(year)")
        conn.commit()
        return conn, False

# ---------- Indexer ----------
def index_pdfs_gui(base_dir, db_path, progress_callback=None, cancel_flag=lambda: False):
    conn, has_fts = init_db(db_path)
    cur = conn.cursor()

    pdf_paths = []
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdf_paths.append(os.path.join(root, f))
    total = len(pdf_paths)
    processed = 0

    for path in pdf_paths:
        if cancel_flag():
            break

        try:
            mtime = os.path.getmtime(path)
        except Exception:
            processed += 1
            if progress_callback:
                progress_callback(processed, total, path)
            continue

        # Skip if unchanged
        row = cur.execute("SELECT mtime FROM files_meta WHERE path = ?", (path,)).fetchone()
        if row and row["mtime"] == mtime:
            processed += 1
            if progress_callback:
                progress_callback(processed, total, path)
            continue

        # year = parent folder name
        year = os.path.basename(os.path.dirname(path))

        text = extract_text_pdfplumber(path)
        text = safe_text(text)
        case_name = os.path.splitext(os.path.basename(path))[0]

        if has_fts:
            try:
                cur.execute("DELETE FROM cases_fts WHERE path = ?", (path,))
                cur.execute("INSERT INTO cases_fts (case_name, year, path, content) VALUES (?, ?, ?, ?)",
                            (case_name, year, path, text))
            except Exception:
                pass
        else:
            cur.execute("INSERT OR REPLACE INTO cases (case_name, year, path, content) VALUES (?, ?, ?, ?)",
                        (case_name, year, path, text))

        cur.execute("INSERT OR REPLACE INTO files_meta (path, mtime) VALUES (?, ?)", (path, mtime))
        conn.commit()

        processed += 1
        if progress_callback:
            progress_callback(processed, total, path)

    conn.close()
    return

# ---------- Search ----------
def highlight_snippet(content, query, window=180):
    if not content:
        return ""
    q = query.lower()
    idx = content.lower().find(q)
    if idx == -1:
        snippet = content[:min(window, len(content))].strip()
        return snippet.replace("\n", " ")
    start = max(0, idx - window//2)
    end = min(len(content), idx + window//2)
    snippet = content[start:end].strip()
    s_lower = snippet.lower()
    rel_idx = s_lower.find(q)
    if rel_idx != -1:
        pre = snippet[:rel_idx]
        match = snippet[rel_idx:rel_idx+len(query)]
        post = snippet[rel_idx+len(query):]
        return (pre + "<<" + match + ">>" + post).replace("\n", " ")
    return snippet.replace("\n", " ")

def search_db(db_path, query, year=None, limit=50):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cases_fts'")
    has_fts = cur.fetchone() is not None

    results = []
    if has_fts:
        if year:
            rows = cur.execute(
                "SELECT case_name, year, path, content FROM cases_fts WHERE year = ? AND cases_fts MATCH ? LIMIT ?",
                (str(year), query, limit)
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT case_name, year, path, content FROM cases_fts WHERE cases_fts MATCH ? LIMIT ?",
                (query, limit)
            ).fetchall()
    else:
        likeq = f"%{query}%"
        if year:
            rows = cur.execute(
                "SELECT case_name, year, path, content FROM cases WHERE year = ? AND content LIKE ? LIMIT ?",
                (str(year), likeq, limit)
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT case_name, year, path, content FROM cases WHERE content LIKE ? LIMIT ?",
                (likeq, limit)
            ).fetchall()

    for r in rows:
        snippet = highlight_snippet(r["content"] or "", query)
        results.append({
            "case_name": r["case_name"],
            "year": r["year"],
            "path": r["path"],
            "snippet": snippet
        })
    conn.close()
    return results

# ---------- OS open helper ----------
def open_file_with_default_app(path):
    if sys.platform.startswith("win"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.call(["open", path])
    else:
        subprocess.call(["xdg-open", path])

# ---------- Tkinter GUI ----------
class LegalCaseFinderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Legal Case Finder")
        self.geometry("900x600")
        self.create_widgets()
        self.cancel_index = False

    def create_widgets(self):
        pad = 6
        frm = ttk.Frame(self)
        frm.pack(fill="x", padx=pad, pady=pad)

        # Base dir
        ttk.Label(frm, text="Cases folder:").grid(row=0, column=0, sticky="w")
        self.base_dir_var = tk.StringVar(value="./cases")
        ttk.Entry(frm, textvariable=self.base_dir_var, width=60).grid(row=0, column=1, sticky="w")
        ttk.Button(frm, text="Browse", command=self.browse_cases).grid(row=0, column=2, padx=4)

        # DB path
        ttk.Label(frm, text="DB file:").grid(row=1, column=0, sticky="w")
        self.db_path_var = tk.StringVar(value="./cases.db")
        ttk.Entry(frm, textvariable=self.db_path_var, width=60).grid(row=1, column=1, sticky="w")
        ttk.Button(frm, text="Browse", command=self.browse_db).grid(row=1, column=2, padx=4)

        # Index / progress
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=pad, pady=(0,pad))
        self.index_btn = ttk.Button(btn_frame, text="Index PDFs", command=self.start_index)
        self.index_btn.pack(side="left", padx=(0,8))
        self.cancel_btn = ttk.Button(btn_frame, text="Cancel Index", command=self.cancel_indexing, state="disabled")
        self.cancel_btn.pack(side="left")

        self.progress = ttk.Progressbar(self, orient="horizontal", length=600, mode="determinate")
        self.progress.pack(fill="x", padx=pad)
        self.progress_label = ttk.Label(self, text="Idle")
        self.progress_label.pack(fill="x", padx=pad, pady=(0,8))

        # Search area
        search_frame = ttk.LabelFrame(self, text="Search")
        search_frame.pack(fill="x", padx=pad, pady=pad)

        ttk.Label(search_frame, text="Query:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.query_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.query_var, width=50).grid(row=0, column=1, sticky="w", padx=4, pady=4)

        ttk.Label(search_frame, text="Year (optional):").grid(row=0, column=2, sticky="w", padx=4, pady=4)
        self.year_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.year_var, width=12).grid(row=0, column=3, sticky="w", padx=4, pady=4)

        ttk.Label(search_frame, text="Limit:").grid(row=0, column=4, sticky="w", padx=4, pady=4)
        self.limit_var = tk.IntVar(value=50)
        ttk.Spinbox(search_frame, from_=1, to=1000, textvariable=self.limit_var, width=6).grid(row=0, column=5, sticky="w", padx=4, pady=4)

        ttk.Button(search_frame, text="Search", command=self.start_search).grid(row=0, column=6, sticky="w", padx=8, pady=4)

        # Results area
        results_frame = ttk.Frame(self)
        results_frame.pack(fill="both", expand=True, padx=pad, pady=pad)

        cols = ("year", "case", "path")
        self.tree = ttk.Treeview(results_frame, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("year", text="Year")
        self.tree.heading("case", text="Case")
        self.tree.heading("path", text="Path")
        self.tree.column("year", width=80, anchor="w")
        self.tree.column("case", width=260, anchor="w")
        self.tree.column("path", width=520, anchor="w")
        self.tree.bind("<<TreeviewSelect>>", self.on_select_result)
        self.tree.pack(fill="both", expand=True, side="left")

        scroll = ttk.Scrollbar(results_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scroll.set)
        scroll.pack(side="left", fill="y")

        # Snippet and open buttons
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(fill="x", padx=pad, pady=pad)
        ttk.Label(bottom_frame, text="Snippet:").pack(anchor="w")
        self.snippet_txt = tk.Text(bottom_frame, height=6, wrap="word")
        self.snippet_txt.pack(fill="x", padx=4, pady=(0,8))
        btns = ttk.Frame(bottom_frame)
        btns.pack(fill="x")
        self.open_btn = ttk.Button(btns, text="Open Selected PDF", command=self.open_selected, state="disabled")
        self.open_btn.pack(side="left")
        self.reveal_btn = ttk.Button(btns, text="Reveal in File Explorer", command=self.reveal_selected, state="disabled")
        self.reveal_btn.pack(side="left", padx=6)

    # ---------- UI helpers ----------
    def browse_cases(self):
        d = filedialog.askdirectory(title="Select cases folder")
        if d:
            self.base_dir_var.set(d)

    def browse_db(self):
        f = filedialog.asksaveasfilename(title="Select DB file", defaultextension=".db", filetypes=[("SQLite DB","*.db"),("All files","*.*")])
        if f:
            self.db_path_var.set(f)

    def set_ui_busy(self, busy=True):
        if busy:
            self.index_btn.configure(state="disabled")
            self.cancel_btn.configure(state="normal")
        else:
            self.index_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")

    # ---------- Index thread ----------
    def start_index(self):
        base_dir = self.base_dir_var.get().strip()
        db_path = self.db_path_var.get().strip()
        if not base_dir or not os.path.isdir(base_dir):
            messagebox.showerror("Error", "Please select a valid cases folder.")
            return
        if not db_path:
            messagebox.showerror("Error", "Please select a DB file path.")
            return

        self.cancel_index = False
        self.progress['value'] = 0
        self.progress_label.config(text="Starting indexing...")
        self.set_ui_busy(True)
        t = threading.Thread(target=self.thread_index, args=(base_dir, db_path))
        t.daemon = True
        t.start()

    def cancel_indexing(self):
        self.cancel_index = True
        self.progress_label.config(text="Cancelling...")

    def thread_index(self, base_dir, db_path):
        def progress_cb(processed, total, current_file):
            self.after(0, lambda: self._update_progress(processed, total, current_file))

        try:
            index_pdfs_gui(base_dir, db_path,
                           progress_callback=progress_cb,
                           cancel_flag=lambda: self.cancel_index)
            if self.cancel_index:
                self.after(0, lambda: messagebox.showinfo("Indexing", "Indexing cancelled."))
            else:
                self.after(0, lambda: messagebox.showinfo("Indexing", "Indexing complete."))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Indexing error", str(e)))
        finally:
            self.after(0, lambda: (self.set_ui_busy(False), self.progress_label.config(text="Idle")))

    def _update_progress(self, processed, total, current_file):
        self.progress['maximum'] = max(1, total)
        self.progress['value'] = processed
        self.progress_label.config(text=f"Indexing: {processed}/{total} — {os.path.basename(current_file)}")

    # ---------- Search ----------
    def start_search(self):
        db_path = self.db_path_var.get().strip()
        query = self.query_var.get().strip()
        if not db_path or not os.path.exists(db_path):
            messagebox.showerror("Error", "Please select an existing DB file (index first).")
            return
        if not query:
            messagebox.showerror("Error", "Please enter a search query.")
            return
        year = self.year_var.get().strip() or None
        limit = int(self.limit_var.get())
        self.progress_label.config(text="Searching...")
        t = threading.Thread(target=self.thread_search, args=(db_path, query, year, limit))
        t.daemon = True
        t.start()

    def thread_search(self, db_path, query, year, limit):
        try:
            results = search_db(db_path, query, year=year, limit=limit)
            self.after(0, lambda: self.populate_results(results))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Search error", str(e)))
        finally:
            self.after(0, lambda: self.progress_label.config(text="Idle"))

    def populate_results(self, results):
        for r in self.tree.get_children():
            self.tree.delete(r)
        self.results_data = results or []
        for i, r in enumerate(self.results_data):
            self.tree.insert("", "end", iid=str(i), values=(r["year"], r["case_name"], r["path"]))
        self.snippet_txt.delete(1.0, tk.END)
        self.open_btn.configure(state="disabled")
        self.reveal_btn.configure(state="disabled")
        if not results:
            messagebox.showinfo("Search", "No matches found.")

    def on_select_result(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        r = self.results_data[idx]
        self.snippet_txt.delete(1.0, tk.END)
        self.snippet_txt.insert(tk.END, r["snippet"])
        self.open_btn.configure(state="normal")
        self.reveal_btn.configure(state="normal")

    def open_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        path = self.results_data[idx]["path"]
        try:
            open_file_with_default_app(path)
        except Exception as e:
            messagebox.showerror("Open error", str(e))

    def reveal_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        path = self.results_data[idx]["path"]
        folder = os.path.dirname(path)
        try:
            if sys.platform.startswith("win"):
                subprocess.call(["explorer", "/select,", path])
            elif sys.platform == "darwin":
                subprocess.call(["open", "-R", path])
            else:
                subprocess.call(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("Reveal error", str(e))


if __name__ == "__main__":
    app = LegalCaseFinderApp()
    app.mainloop()
