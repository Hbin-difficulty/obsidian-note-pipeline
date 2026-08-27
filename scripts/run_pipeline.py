#!/usr/bin/env python3
"""Orchestrator: detect file type -> convert to Markdown (if needed) -> process.

Decision logic (this is the core of the skill):
  - If input is already .md  -> process directly (no conversion).
  - If input is .pdf         -> convert with PyMuPDF (convert_pdf.py).
  - If input is .docx        -> convert with stdlib (convert_docx.py).
  - If input is .txt         -> copy as Markdown (light wrap).

Run with the managed venv Python so PyMuPDF is available:
  .../envs/default/Scripts/python.exe run_pipeline.py <input> [options]

All processing options (--title, --tags, --summary-*, --concepts,
--doubts-*) are forwarded to process_note.py. See process_note.py -h.
"""
import sys
import os
import tempfile
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from convert_pdf import convert as convert_pdf
from convert_docx import convert as convert_docx
import process_note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--tags", default=None)
    ap.add_argument("--summary-file", default=None)
    ap.add_argument("--summary-text", default=None)
    ap.add_argument("--concepts", default=None)
    ap.add_argument("--doubts-file", default=None)
    ap.add_argument("--doubts-text", default=None)
    ap.add_argument("--ai-version", default="1.0")
    ap.add_argument("--config-dir", default=None)
    args = ap.parse_args()

    inp = args.input
    ext = os.path.splitext(inp)[1].lower()
    base = os.path.splitext(os.path.basename(inp))[0]
    indir = os.path.dirname(os.path.abspath(inp))

    out = args.out
    if ext == ".md":
        raw = inp  # process in place
        if out is None:
            out = inp
    else:
        # convert to a temporary / target Markdown first
        if out is None:
            out = os.path.join(indir, base + ".md")
        raw = os.path.join(tempfile.gettempdir(), base + ".raw.md")
        if ext == ".pdf":
            try:
                import fitz  # noqa
            except ImportError:
                sys.exit("ERROR: PyMuPDF (fitz) not found. Run with the managed "
                         "venv Python, or: pip install pymupdf")
            convert_pdf(inp, raw)
        elif ext == ".docx":
            convert_docx(inp, raw)
        elif ext == ".txt":
            with open(inp, encoding="utf-8") as f:
                txt = f.read()
            with open(raw, "w", encoding="utf-8") as f:
                f.write(txt)
            print(f"copied txt -> {raw}")
        else:
            sys.exit(f"ERROR: unsupported extension {ext} "
                     "(supported: .md .pdf .docx .txt)")

    process_note.main_with(
        raw, out, title=args.title, tags=args.tags,
        summary_file=args.summary_file, summary_text=args.summary_text,
        concepts=args.concepts, doubts_file=args.doubts_file,
        doubts_text=args.doubts_text, ai_version=args.ai_version,
        config_dir=args.config_dir,
    )
    print(f"DONE -> {out}")


if __name__ == "__main__":
    main()
