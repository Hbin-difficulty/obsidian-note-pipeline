#!/usr/bin/env python3
"""Process a Markdown note per an Obsidian vault's AGENTS.md / PRD.md rules.

Mechanical, red-line-safe transformations only. The *judgment* content
(summary text, concept list, doubt list, tags) is supplied by the agent and
passed in via arguments / files.

What it does:
  1. Normalize structure (setext -> ATX headings, bare ``` -> ```text, "- " bullets)
  2. Insert/refresh YAML frontmatter (title, tags, ai_processed, ai_version)
  3. Ensure a single top-level "# Title"
  4. Insert "## 📝 AI摘要" right after the title, with the supplied summary
  5. Inject [[concept]] at the FIRST occurrence of each concept (skipping
     frontmatter, code fences, and text already inside [[...]])
  6. Append "<!-- 🤖AI疑问 -->" with any supplied doubts
  7. Update ai_processed / ai_version status

It NEVER rewrites paragraph wording or reorders original content beyond the
structural normalizations above.

Usage:
  python process_note.py <note.md> \
      [--out out.md] [--title "T"] [--tags "AI,编程,教程"] \
      [--summary-file sum.md | --summary-text "..."] \
      [--concepts "提示词,回滚,..."] \
      [--doubts-file d.md | --doubts-text "..."] \
      [--ai-version 1.0] [--config-dir DIR]
"""
import sys
import re
import os
import datetime
import argparse

SUMMARY_HEADING = "## 📝 AI摘要"
DOUBT_COMMENT = "<!-- 🤖AI疑问 -->"


# ---------------------------------------------------------------------------
# config auto-discovery (best-effort): pull tag whitelist + concept list from
# the vault's AGENTS.md / PRD.md so the agent doesn't have to retype them.
# ---------------------------------------------------------------------------

def find_config(start_dir):
    d = os.path.abspath(start_dir)
    while True:
        for name in ("AGENTS.md", "PRD.md"):
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_concepts_from_config(cfg_dir):
    """Extract the concept vocabulary under a '双链概念词表' style heading."""
    concepts = []
    for name in ("PRD.md", "AGENTS.md"):
        p = os.path.join(cfg_dir, name) if cfg_dir else None
        if not p or not os.path.isfile(p):
            continue
        txt = open(p, encoding="utf-8").read()
        # find a section titled something with 概念词表 / 双链概念
        m = re.search(r"^#+\s*.*?(概念词表|双链概念).*$", txt, re.M)
        if not m:
            continue
        section = txt[m.end():]
        # stop at next heading
        nxt = re.search(r"^#+\s", section, re.M)
        if nxt:
            section = section[:nxt.start()]
        for line in section.splitlines():
            # bullet items like "- 提示词" or "`提示词`" or "提示词"
            mm = re.findall(r"[`#]?([\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_ ]{1,20}?)[`#]?\s*$", line.strip())
            for c in mm:
                c = c.strip().strip("`").strip()
                if c and len(c) <= 12 and c not in concepts:
                    concepts.append(c)
        if concepts:
            break
    return concepts


# ---------------------------------------------------------------------------
# transformations
# ---------------------------------------------------------------------------

def normalize(lines):
    """Return normalized lines: setext -> ATX, bare OPENING fences -> ```text.

    Only opening fences (when not already inside a code block) get a language
    annotation; closing fences stay bare so code blocks are not corrupted.
    """
    out = []
    i = 0
    n = len(lines)
    in_fence = False
    while i < n:
        line = lines[i]
        nxt = lines[i + 1] if i + 1 < n else ""
        # setext: a line followed by a line of only --- or ===
        if nxt.strip() and set(nxt.strip()) <= set("-") and len(set(nxt.strip())) == 1 and line.strip():
            out.append(f"## {line.strip()}")
            i += 2
            in_fence = False
            continue
        if nxt.strip() and set(nxt.strip()) <= set("=") and len(set(nxt.strip())) == 1 and line.strip():
            out.append(f"# {line.strip()}")
            i += 2
            in_fence = False
            continue
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_fence:
                out.append("```text" if stripped == "```" else line)
                in_fence = True
            else:
                out.append("```")  # closing fence stays bare
                in_fence = False
            i += 1
            continue
        out.append(line)
        i += 1
    return out


def parse_frontmatter(text):
    if text.startswith("---\n"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            body = text[end + 4:]
            return fm, body
    return None, text


def build_frontmatter(existing_fm, title, tags, ai_version, today):
    d = {}
    if existing_fm:
        for line in existing_fm.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                d[k.strip()] = v.strip()
    d["title"] = title
    d["tags"] = " ".join(tags)
    d["ai_processed"] = today
    d["ai_version"] = ai_version
    keys_order = ["title", "tags", "ai_processed", "ai_version"]
    lines = ["---"]
    for k in keys_order:
        if k in d:
            lines.append(f"{k}: {d[k]}")
    # preserve any other keys
    for k, v in d.items():
        if k not in keys_order:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def inject_concepts(body, concepts):
    if not concepts:
        return body
    placed = set()
    out_lines = []
    in_code = False
    for line in body.split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            out_lines.append(line)
            continue
        if in_code:
            out_lines.append(line)
            continue
        for c in concepts:
            if c in placed:
                continue
            if c not in line:
                continue
            # skip if already inside an existing [[...]]
            idx = 0
            found = False
            while True:
                pos = line.find(c, idx)
                if pos == -1:
                    break
                before = line[max(0, pos - 2):pos]
                after = line[pos + len(c):pos + len(c) + 2]
                if "[[" in before or "]]" in after or "[[" in line[:pos] and "]]" in line[pos + len(c):]:
                    # crude: if there is a [[ before and ]] after on same line
                    if "[[" in line[:pos] and "]]" in line[pos + len(c):]:
                        idx = pos + len(c)
                        continue
                # replace first safe occurrence
                line = line[:pos] + f"[[{c}]]" + line[pos + len(c):]
                placed.add(c)
                found = True
                break
        out_lines.append(line)
    return "\n".join(out_lines)


def process(input_path, out_path, title, tags, summary, concepts, doubts,
            ai_version, today, cfg_dir):
    text = open(input_path, encoding="utf-8").read()
    fm, body = parse_frontmatter(text)
    lines = normalize(body.split("\n"))

    # title
    if not title:
        for ln in lines:
            if ln.startswith("# "):
                title = ln[2:].strip()
                break
        if not title:
            title = os.path.splitext(os.path.basename(input_path))[0]

    # ensure single H1 title present
    has_h1 = any(ln.startswith("# ") for ln in lines)
    if not has_h1:
        lines = ["# " + title, ""] + lines

    # insert summary after the first H1
    if summary and SUMMARY_HEADING not in lines:
        new_lines = []
        inserted = False
        for ln in lines:
            new_lines.append(ln)
            if not inserted and ln.startswith("# "):
                new_lines.append("")
                new_lines.append(SUMMARY_HEADING)
                for sline in summary.strip().split("\n"):
                    new_lines.append(sline)
                new_lines.append("")
                inserted = True
        lines = new_lines

    body2 = "\n".join(lines)

    # inject concept links
    body2 = inject_concepts(body2, concepts)

    # append doubts
    if doubts:
        if not body2.rstrip().endswith("\n"):
            body2 = body2.rstrip() + "\n"
        body2 = body2.rstrip() + f"\n\n{DOUBT_COMMENT}\n" + doubts.strip() + "\n"

    # frontmatter
    fm_text = build_frontmatter(fm, title, tags, ai_version, today)
    final = fm_text + "\n" + body2 if not body2.startswith("\n") else fm_text + body2
    final = final.rstrip() + "\n"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final)
    print(f"processed -> {out_path} (title={title!r}, tags={tags}, concepts={len(concepts)}, doubts={'yes' if doubts else 'no'})")


def main_with(input_path, out_path=None, title=None, tags=None,
               summary_file=None, summary_text=None, concepts=None,
               doubts_file=None, doubts_text=None, ai_version="1.0",
               config_dir=None):
    out = out_path or input_path
    summary = summary_text
    if summary_file:
        summary = open(summary_file, encoding="utf-8").read()
    doubts = doubts_text
    if doubts_file:
        doubts = open(doubts_file, encoding="utf-8").read()

    tags_list = []
    if tags:
        for t in tags.split(","):
            t = t.strip().lstrip("#").strip()
            if t:
                tags_list.append("#" + t)

    concepts_list = []
    if concepts:
        concepts_list = [c.strip() for c in concepts.split(",") if c.strip()]

    cfg = config_dir or find_config(os.path.dirname(os.path.abspath(out)))
    if cfg:
        if not tags_list:
            for name in ("PRD.md", "AGENTS.md"):
                p = os.path.join(cfg, name)
                if os.path.isfile(p):
                    txt = open(p, encoding="utf-8").read()
                    m = re.search(r"白名单[^#]*((?:#[^\s,，]+)+)", txt)
                    if m:
                        tags_list = ["#" + t for t in re.findall(r"#([^\s,，]+)", m.group(1))]
                        break
        if not concepts_list:
            concepts_list = load_concepts_from_config(cfg)

    today = datetime.date.today().isoformat()
    process(input_path, out, title, tags_list, summary, concepts_list, doubts,
            ai_version, today, cfg)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--tags", default=None, help="comma list, with or without #")
    ap.add_argument("--summary-file", default=None)
    ap.add_argument("--summary-text", default=None)
    ap.add_argument("--concepts", default=None, help="comma list")
    ap.add_argument("--doubts-file", default=None)
    ap.add_argument("--doubts-text", default=None)
    ap.add_argument("--ai-version", default="1.0")
    ap.add_argument("--config-dir", default=None)
    args = ap.parse_args()
    main_with(
        args.input, out_path=args.out, title=args.title, tags=args.tags,
        summary_file=args.summary_file, summary_text=args.summary_text,
        concepts=args.concepts, doubts_file=args.doubts_file,
        doubts_text=args.doubts_text, ai_version=args.ai_version,
        config_dir=args.config_dir,
    )


if __name__ == "__main__":
    main()
