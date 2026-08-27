# Conversion Notes & Gotchas

Pitfalls encountered while building this skill. Read before debugging a converter.

## PDF (PyMuPDF / fitz)

- **Image xref key**: `page.get_image_info()` returns dicts keyed by `number`,
  NOT `xref`. Always use `page.get_images(full=True)` to get the real `xref`,
  then `doc.extract_image(xref)` (Document method, not Page method) for bytes.
- **Bbox**: `page.get_image_rects(xref)` returns a list of rects; take `[0]`.
  Skip tiny images (width under 5 or height under 5) to avoid bullet/icon noise.
- **Per-page ordering is mandatory**. Do NOT accumulate all pages' elements in
  one list and sort globally — that interleaves pages. Sort elements by `y0`
  *within each page*, then append page-by-page.
- **Heading detection**: use *relative* sizes, not hard-coded thresholds.
  `body_size = mode(round(size))`; sizes greater than `body_size + 0.8` are headings,
  mapped largest→H1, next→H2, next→H3. This survives different PDFs.
- **Code blocks**: identified by the `Menlo` font. BUT a single Menlo line that
  is actually CJK prose (e.g. "`AGENTS.md` 这个名称很重要") must be demoted to
  body — otherwise filenames in monospace get fenced. Rule: if a code buffer has
  exactly one line and `is_real_code()` is False, emit as paragraph.
- **H1 de-duplication**: PDFs repeat the document title as a page header on
  every page. De-dup by normalized title so only the first `# Title` remains.
- **List ordering**: check list patterns (`^\d+[.、)）]` and `^[-•*]\s`) AFTER
  heading detection but BEFORE code, so Menlo list items stay as list items.
- **Font warnings** (`TTF`/missing-glyph) are harmless; filter with
  `warnings.filterwarnings("ignore")`.

## DOCX (pure stdlib: zipfile + xml.etree)

- No `python-docx` needed. A `.docx` is a ZIP; `word/document.xml` holds content.
- **Namespaces**: every tag is `{ns}local`. Register the W/R/A namespaces and use
  `q(ns, "p")` helpers. `localname()` strips the namespace for matching.
- **Inline images**: scan each paragraph element for the drawing blip element
  that carries `r:embed="rIdN"`; resolve `rIdN` to a media path via
  `word/_rels/document.xml.rels`; read `word/media/...` bytes from the zip;
  embed as base64 data URI. Iterate `p.iter()` in document order so text and
  images stay interleaved.
- **Headings**: `w:pStyle/@w:val` like `Heading1`/`Heading2` → level. `Title` → H1.
- **Lists**: presence of `w:numPr` → render as `- ` (we don't resolve actual
  numbering; Obsidian lists render fine).
- **Code**: paragraph style name containing `code` (case-insensitive) → fenced.
- **Tables**: `w:tbl` → rows `w:tr` → cells `w:tc`; join cell text with spaces,
  escape `|` as `\|`. Emit a Markdown table with a `---` separator row.

## General

- Embedding images as base64 makes the `.md` self-contained (no external asset
  files) — exactly what the user asked for. Downside: file size grows with images.
  If a lighter note is wanted, switch to local `assets/` references instead.
- PDF text extraction loses *graphically rendered* list numbers / inline quotes
  (they are shapes, not text). This is an inherent limitation; note it to the
  user rather than fabricating numbers.
