#!/usr/bin/env python3
"""DOCX -> Markdown converter (pure standard library: zipfile + xml).

No third-party dependency (no python-docx needed). Produces Markdown with:
  - Heading levels from paragraph styles (Heading1/2/3...)
  - Bullet / numbered lists (detected via numbering properties)
  - Code blocks for "Code" style paragraphs
  - Tables converted to Markdown tables
  - Images embedded inline as base64 data URIs (ordered via drawing XML)

Usage:
    python convert_docx.py <input.docx> <output.md>
"""
import sys
import re
import base64
import zipfile
import xml.etree.ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def q(ns, tag):
    return f"{{{ns}}}{tag}"


def localname(tag):
    return tag.split("}")[-1]


# ----------------------------------------------------------------------------
# relationship map: relId -> media path inside the zip
# ----------------------------------------------------------------------------

def load_rels(zf, rels_path):
    rels = {}
    try:
        data = zf.read(rels_path)
    except KeyError:
        return rels
    root = ET.fromstring(data)
    for rel in root:
        rid = rel.get("Id")
        target = rel.get("Target")
        if target and (target.lower().endswith((".png", ".jpg", ".jpeg",
                                                ".gif", ".bmp", ".svg"))):
            if not target.startswith("/"):
                target = "word/" + target.lstrip("./")
            else:
                target = target.lstrip("/")
            rels[rid] = target
    return rels


# ----------------------------------------------------------------------------
# paragraph text + inline images
# ----------------------------------------------------------------------------

def para_text_and_images(p, zf, rels):
    """Return (text, list_of_base64_data_uris) for a <w:p> element."""
    texts = []
    images = []

    # iterate over all descendants in document order
    for elem in p.iter():
        tag = localname(elem.tag)
        if tag == "t":
            if elem.text:
                texts.append(elem.text)
        elif tag == "tab":
            texts.append("\t")
        elif tag == "br":
            texts.append("\n")
        elif tag == "blip":  # a:blip inside drawing
            rid = elem.get(q(R, "embed")) or elem.get(q(R, "link"))
            if rid and rid in rels:
                path = rels[rid]
                try:
                    raw = zf.read(path)
                    ext = path.rsplit(".", 1)[-1].lower()
                    mime = {
                        "png": "image/png", "jpg": "image/jpeg",
                        "jpeg": "image/jpeg", "gif": "image/gif",
                        "bmp": "image/bmp", "svg": "image/svg+xml",
                    }.get(ext, "image/png")
                    b64 = base64.b64encode(raw).decode()
                    images.append(f"![图示](data:{mime};base64,{b64})")
                except KeyError:
                    pass
    text = "".join(texts)
    return text, images


def para_style(p):
    ppr = p.find(q(W, "pPr"))
    if ppr is None:
        return None, None
    pstyle = ppr.find(q(W, "pStyle"))
    numpr = ppr.find(q(W, "numPr"))
    style_val = pstyle.get(q(W, "val")) if pstyle is not None else None
    return style_val, numpr


def is_heading(style_val):
    if not style_val:
        return 0
    m = re.match(r"Heading(\d+)", style_val)
    if m:
        return int(m.group(1))
    if style_val.lower() in ("title", "subtitle"):
        return 1
    return 0


def looks_code(style_val, text):
    if style_val and "code" in style_val.lower():
        return True
    # monospace run font
    for r in p_runs(text):
        pass
    return False


def p_runs(p):
    return p.findall(q(W, "r"))


# ----------------------------------------------------------------------------
# table -> markdown
# ----------------------------------------------------------------------------

def table_to_md(tbl, zf, rels):
    rows = []
    for tr in tbl.findall(q(W, "tr")):
        cells = []
        for tc in tr.findall(q(W, "tc")):
            cell_text = []
            for node in tc:
                tn = localname(node.tag)
                if tn == "p":
                    t, imgs = para_text_and_images(node, zf, rels)
                    cell_text.append(t)
                    for im in imgs:
                        cell_text.append(im)
                elif tn == "tbl":
                    cell_text.append("\n" + table_to_md(node, zf, rels))
            cells.append(" ".join(cell_text).strip().replace("\n", " ").replace("|", "\\|"))
        rows.append(cells)
    if not rows:
        return ""
    ncol = max(len(r) for r in rows)
    lines = []
    header = rows[0] + [""] * (ncol - len(rows[0]))
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * ncol) + " |")
    for r in rows[1:]:
        r = r + [""] * (ncol - len(r))
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def convert(docx_path: str, md_path: str) -> None:
    zf = zipfile.ZipFile(docx_path)
    rels = load_rels(zf, "word/_rels/document.xml.rels")
    doc_xml = zf.read("word/document.xml")
    root = ET.fromstring(doc_xml)
    body = root.find(q(W, "body"))
    if body is None:
        print("no body found", file=sys.stderr)
        return

    out = []
    in_code = False  # not really used; we flush per paragraph
    prev_h_norm = None

    def emit(line):
        out.append(line)

    for child in body:
        tag = localname(child.tag)
        if tag == "p":
            style_val, numpr = para_style(child)
            text, imgs = para_text_and_images(child, zf, rels)
            h = is_heading(style_val)

            if h:
                t = text.strip()
                if h == 1:
                    t = re.sub(r"^\s*\d+\s*", "", t).strip()
                    nn = re.sub(r"\s+", "", t).lower()
                    if prev_h_norm and nn == prev_h_norm:
                        prev_h_norm = nn
                        for im in imgs:
                            emit(im); emit("")
                        continue
                    emit(f"# {t}"); emit("")
                    prev_h_norm = nn
                else:
                    emit(f"{'#' * min(h, 6)} {t}".rstrip()); emit("")
                    prev_h_norm = None
                for im in imgs:
                    emit(im); emit("")
                continue

            if style_val and "code" in style_val.lower():
                emit("```text")
                emit(text)
                emit("```")
                emit("")
                for im in imgs:
                    emit(im); emit("")
                continue

            if numpr is not None:
                emit(f"- {text.strip()}".rstrip())
                emit("")
                for im in imgs:
                    emit(im); emit("")
                continue

            # plain paragraph
            if text.strip():
                emit(text.strip())
                emit("")
            for im in imgs:
                emit(im); emit("")

        elif tag == "tbl":
            md = table_to_md(child, zf, rels)
            if md:
                emit(md)
                emit("")

    result = "\n".join(out).rstrip() + "\n"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(result)
    print(f"converted {docx_path} -> {md_path} ({len(result)} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: convert_docx.py <input.docx> <output.md>")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
