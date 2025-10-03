#!/usr/bin/env python3
"""
legal_case_finder.py

Usage:
  # Index PDFs (first run or to update index)
  python legal_case_finder.py index --base_dir ./cases --db ./cases.db --ocr

  # Search:
  python legal_case_finder.py search --db ./cases.db --query "theft" --year 2020 --limit 20
"""

import os
import argparse
import sqlite3
import time
from tqdm import tqdm

# PDF extraction libraries
import pdfplumber
from pdf2image import convert_from_path
import pytesseract

# ======== Utilities ========
def safe_text(s):
    return s if s else ""

def extract_text_pdfplumber(path):
    """Extract text using pdfplumber (fast & good for text PDFs)."""
    texts = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                txt = page.extract_text()
                if txt:
                    texts.append(txt)
    except Exception as e:
        # log if needed
        # print(f"pdfplumber failed for {path}: {e}")
        pass
    return "\n".join(texts)

def ocr_pdf(path, dpi=200, poppler_path=None):
    """OCR entire PDF: convert pages to images (pdf2image) then pytesseract."""
    texts = []
    try:
        pages = convert_from_path(path, dpi=dpi, poppler_path=poppler_path)
        for img in pages:
            txt = pytesseract.image_to_string(img)
            if txt:
                texts.append(txt)
    except Exception as e:
        # print(f"OCR failed for {path}: {e}")
        pass
    return "\n".join(texts)

def is_likely_scanned(text, min_chars=100):
    """If extracted text is very short, we treat file as 'scanned' likely needing OCR."""
    return len(text.strip()) < min_chars

# ======== SQLite helpers (FTS5 if available) ========
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
    # metadata table to track mtimes (so we do incremental updates)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files_meta (
            path TEXT PRIMARY KEY,
            mtime REAL
        )
    """)
    if supports_fts5(conn):
        # FTS table
        cur.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
                case_name, year, path, content, tokenize='porter'
            )
        """)
        conn.commit()
        return conn, True
    else:
        # fallback to regular table (slower searches)
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

# ======== Indexing ========
def find_case_name_from_path(path):
    """Heuristic: use filename (without extension) as case name; optionally parse inside text later."""
    return os.path.splitext(os.path.basename(path))[0]

def index_pdfs(base_dir, db_path, use_ocr=False, poppler_path=None, min_text_chars=100):
    conn, has_fts = init_db(db_path)
    cur = conn.cursor()

    # find all pdf files under base_dir
    pdf_paths = []
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdf_paths.append(os.path.join(root, f))

    for path in tqdm(pdf_paths, desc="Indexing PDFs"):
        try:
            mtime = os.path.getmtime(path)
        except Exception:
            continue

        # check metadata (skip unchanged files)
        row = cur.execute("SELECT mtime FROM files_meta WHERE path = ?", (path,)).fetchone()
        if row and row["mtime"] == mtime:
            # unchanged -> skip
            continue

        # extract year from parent folder name (best-effort)
        parent = os.path.basename(os.path.dirname(path))
        year = parent

        # Extract text (try pdfplumber first)
        text = extract_text_pdfplumber(path)
        if use_ocr and is_likely_scanned(text, min_chars=min_text_chars):
            # fallback to OCR
            ocr_text = ocr_pdf(path, poppler_path=poppler_path)
            # prefer ocr_text if it has more content
            if len(ocr_text.strip()) > len(text.strip()):
                text = ocr_text

        text = safe_text(text)
        case_name = find_case_name_from_path(path)

        if has_fts:
            # remove old entry for path (if any) and insert fresh
            cur.execute("DELETE FROM cases_fts WHERE path = ?", (path,))
            cur.execute(
                "INSERT INTO cases_fts (case_name, year, path, content) VALUES (?, ?, ?, ?)",
                (case_name, year, path, text)
            )
        else:
            # fallback
            cur.execute("INSERT OR REPLACE INTO cases (case_name, year, path, content) VALUES (?, ?, ?, ?)",
                        (case_name, year, path, text))

        # update metadata
        cur.execute("INSERT OR REPLACE INTO files_meta (path, mtime) VALUES (?, ?)", (path, mtime))
        conn.commit()

    conn.close()
    print("Indexing complete.")

# ======== Searching ========
def highlight_snippet(content, query, window=120):
    q = query.lower()
    idx = content.lower().find(q)
    if idx == -1:
        # return start snippet
        return content[:min(window, len(content))].strip()
    start = max(0, idx - window//2)
    end = min(len(content), idx + window//2)
    snippet = content[start:end].strip()
    # Highlight (simple bracket highlight)
    s_lower = snippet.lower()
    rel_idx = s_lower.find(q)
    if rel_idx != -1:
        pre = snippet[:rel_idx]
        match = snippet[rel_idx:rel_idx+len(query)]
        post = snippet[rel_idx+len(query):]
        return pre + "<<" + match + ">>" + post
    return snippet

def search_db(db_path, query, year=None, limit=50):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # detect FTS
    has_fts = False
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cases_fts'")
        has_fts = cur.fetchone() is not None
    except Exception:
        pass

    results = []
    if has_fts:
        # build FTS query; if year supplied, add it as a token to the query using AND
        fts_query = query
        if year:
            # this searches content for query AND year in year field isn't directly set. Instead filter by year separately
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
        # fallback: LIKE search on content (case-insensitive)
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

# ======== CLI ========
def main():
    parser = argparse.ArgumentParser(description="Legal Case Finder - index & search PDFs by year + keyword")
    sub = parser.add_subparsers(dest="cmd")

    # index
    p_index = sub.add_parser("index", help="Index PDFs into SQLite DB")
    p_index.add_argument("--base_dir", required=True, help="Root folder with year subfolders")
    p_index.add_argument("--db", default="cases.db", help="SQLite DB path")
    p_index.add_argument("--ocr", action="store_true", help="Enable OCR fallback for scanned PDFs")
    p_index.add_argument("--poppler_path", default=None, help="(Windows) path to poppler bin for pdf2image")

    # search
    p_search = sub.add_parser("search", help="Search indexed cases")
    p_search.add_argument("--db", default="cases.db", help="SQLite DB path")
    p_search.add_argument("--query", required=True, help="Search keyword or phrase")
    p_search.add_argument("--year", default=None, help="Year folder to restrict search")
    p_search.add_argument("--limit", default=50, type=int, help="Max results")

    args = parser.parse_args()
    if args.cmd == "index":
        index_pdfs(args.base_dir, args.db, use_ocr=args.ocr, poppler_path=args.poppler_path)
    elif args.cmd == "search":
        res = search_db(args.db, args.query, year=args.year, limit=args.limit)
        if not res:
            print("No matches found.")
            return
        for r in res:
            print(f"Year: {r['year']} | Case: {r['case_name']} | File: {r['path']}")
            print(f"  ...{r['snippet']}...\n")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
