---
name: obsidian-note-pipeline
description: "This skill should be used when the user wants to turn a document (PDF, Word/DOCX, plain text, or an existing Markdown note) into a processed Obsidian-style Markdown note. It first detects the file type: if the file is already .md, it processes it directly; otherwise it converts the file to Markdown (PDF via PyMuPDF with inline base64 images, DOCX via pure stdlib with inline images), then applies the vault's AGENTS.md/PRD.md pipeline (frontmatter, AI summary, concept double-links, AI doubts, status fields). Use it for requests like '把这篇 PDF/Word 转成 md 笔记并处理' or any convert-and-process-a-document task."
agent_created: true
---

# Obsidian Note Pipeline

Turn any document into a processed Obsidian Markdown note. The defining rule:
**detect the file type first; if it is already Markdown, process it directly;
otherwise convert it to Markdown (with images embedded inline) and then process.**

## When to use

- "把 `xxx.pdf` 转成 md 笔记并处理" / "convert this PDF/DOCX to a note"
- "处理一下这篇笔记" when the target is a raw `.md` (no conversion needed)
- Any task that should land a document in the vault following `AGENTS.md` / `PRD.md`

## Workflow

### Step 1 — Detect type (by extension)

| Extension | Action |
|-----------|--------|
| `.md`     | Process directly (no conversion) |
| `.pdf`    | Convert with `scripts/convert_pdf.py` |
| `.docx`   | Convert with `scripts/convert_docx.py` |
| `.txt`    | Light wrap as Markdown, then process |
| other     | Stop and tell the user the format is unsupported |

### Step 2 — Convert (skip for `.md`)

Run every script with the **managed venv Python** so PyMuPDF is available:
`C:\Users\Lenovo\.workbuddy\binaries\python\envs\default\Scripts\python.exe`
(DOCX/TXT conversion is pure stdlib, but using the venv Python uniformly is simplest).

- **PDF → MD** (`convert_pdf.py`): heading levels from *relative* font sizes,
  code blocks from the `Menlo` font, images embedded as base64 data URIs.
  See `references/conversion_notes.md` for the pitfalls that are already handled
  (xref key, per-page ordering, single-line code demotion, H1 de-dup).
- **DOCX → MD** (`convert_docx.py`): pure `zipfile`+`xml`, no `python-docx`
  needed. Handles headings, lists, code-style paragraphs, tables, and inline
  images (ordered via drawing XML).

### Step 3 — Produce the judgment content (agent does this)

The conversion is mechanical; the *content* of the note requires judgment. Before
processing, generate (and, if useful, write to temp files):

1. **Title** — the document's main title (or reuse the first H1 / filename stem).
2. **Tags** — from the vault's tag whitelist in `AGENTS.md`/`PRD.md`
   (e.g. `#AI #编程 #教程 #方法论 #效率`). Keep ≤ 5, whitelist-only.
3. **AI summary** — a `## 📝 AI摘要` block: 4–5 sentences of core points
   (≤ 30 chars each), plus "相关笔记" and "关键标签" lines. Keep original wording.
4. **Concept list** — the vault's "双链概念词表" terms that actually appear in
   the body (skip any inside code blocks). Link only the first occurrence of each.
5. **AI doubts** — append the AI-doubt HTML comment (the `DOUBT_COMMENT`
   token, i.e. `🤖AI疑问` wrapped in an HTML comment as defined in
   process_note.py) with any contradictions / copy-paste errors found. Omit if none.

If the vault has `AGENTS.md`/`PRD.md`, the pipeline auto-discovers the tag
whitelist and concept vocabulary from them (best-effort) when `--tags`/`--concepts`
are not passed. Always read `AGENTS.md`/`PRD.md` first to honor the exact rules
(white-list tags, red lines, link granularity: whole-note `[[note]]`, heading
anchor `[[#heading]]`, block ref `[[#^id]]`).

### Step 4 — Process (run `scripts/process_note.py` or `run_pipeline.py`)

`run_pipeline.py` combines detection + conversion + processing in one call:

```bash
PY="C:/Users/Lenovo/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
$PY scripts/run_pipeline.py "path/to/file.pdf" \
  --title "项目开发流程" \
  --tags "AI,编程,教程,方法论,效率" \
  --summary-text "..." \
  --concepts "提示词,回滚,类型安全" \
  --doubts-text "..." \
  --out "vibe_conding学习及使用技巧/项目开发流程.md"
```

For a raw `.md` note, pass it directly (conversion is skipped):
```bash
$PY scripts/run_pipeline.py "debug_纠错.md" --summary-text "..." --concepts "..."
```

If you already converted separately, call `process_note.py` on the `.md` directly.

## Red-line rules (do not violate)

- Never rewrite paragraph wording or reorder original content beyond structural
  Markdown normalization (setext→ATX, bare fences→` ```text `, bullet normalization).
- Only whitelist tags; no extra tags, no extra sections beyond summary + doubts.
- Skip double-link injection inside code fences, frontmatter, and existing `[[...]]`.
- Images stay embedded inline (base64) unless the user asks for external assets.

## Scripts

- `scripts/run_pipeline.py` — detect → convert → process (entry point).
- `scripts/convert_pdf.py` — PDF → MD (PyMuPDF).
- `scripts/convert_docx.py` — DOCX → MD (stdlib).
- `scripts/process_note.py` — AGENTS/PRD processing (frontmatter, summary, links, doubts).
- `references/conversion_notes.md` — conversion pitfalls already solved.

## Notes / limitations

- PDFs render list numbers / inline quotes as *shapes*, so those may be lost in
  extraction — report this rather than fabricating them.
- Concept links inserted via the "概念建链" mode may point to notes not yet
  created (Obsidian creates them on click). Confirm with the user if the vault
  requires links to existing notes only.
