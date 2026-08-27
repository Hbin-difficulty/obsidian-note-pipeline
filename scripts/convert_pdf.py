#!/usr/bin/env python3
"""PDF -> Markdown converter (PyMuPDF / fitz).

Produces a Markdown file with:
  - Heading levels inferred from *relative* font sizes (no hard-coded thresholds)
  - Code blocks detected by the Menlo monospace font, with single-line
    "fake code" prose lines demoted back to body text
  - Images embedded inline as base64 data URIs (so the .md is self-contained)

Usage:
    python convert_pdf.py <input.pdf> <output.md>
"""
import sys
import re
import base64
import warnings

warnings.filterwarnings("ignore")

import fitz  # PyMuPDF

# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------

TERM = set("。！？.!?")  # characters that end a paragraph (CJK + Latin)


def is_real_code(line: str) -> bool:
    """Heuristic: is this Menlo line genuinely code (vs. a CJK prose line that
    merely happens to use a monospace font for a filename)?"""
    s = line.strip()
    if not s:
        return False
    markers = (
        "#", "$", ">", "-", "*", "+", "=", "{", "(", "./", "`",
        "import ", "def ", "function", "class ", "SELECT", "select",
        "git ", "npm ", "cd ", "const ", "let ", "var ", "public ",
        "private ", "void ", "int ", "return", "<", "//", "/*", "#!/",
        "FROM", "UPDATE", "INSERT", "print", "echo", "sudo", "pip",
        "npx", "yarn", "cargo", "docker", "kubectl",
    )
    if any(s.startswith(m) or m in s[:8] for m in markers):
        return True
    # code punctuation
    if re.search(r"[;{}()=]\s*\S", s):
        return True
    # pure CJK prose line -> not code
    if re.search(r"[一-鿿]", s) and not re.search(r"[A-Za-z]{2,}\s*[{}();=]", s):
        if s[-1] in "。！？，、）]”" and not s[0].isascii():
            return False
    return False


def code_lang(block: str) -> str:
    b = block.strip()
    if b.startswith(("```", "#!", "$", ">", "sudo", "git", "npm", "cd ",
                     "pip", "npx", "yarn", "docker", "kubectl", "apt",
                     "brew", "cargo", "echo", "export", "source")):
        return "bash"
    if b.startswith("# ") or b.startswith("## ") or b.startswith("### ") \
            or b.startswith("- ") or b.startswith("* ") or b.startswith("> ") \
            or b.startswith("[") or b.startswith("!["):
        return "markdown"
    if re.search(r"^\s*[{\[]", b) or re.search(r":\s*\n", b):
        return "json"
    return "text"


def img_to_uri(doc, xref: int) -> str:
    info = doc.extract_image(xref)
    data = info["image"]
    ext = info["ext"].lower()
    mime = {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "svg": "image/svg+xml",
    }.get(ext, "image/png")
    b64 = base64.b64encode(data).decode()
    return f"![图示](data:{mime};base64,{b64})"


def norm_title(t: str) -> str:
    return re.sub(r"\s+", "", t).lower()


def heading_level(size, heading_sizes, body_size):
    if size <= body_size + 0.8:
        return 0
    for i, hs in enumerate(heading_sizes):
        if size >= hs - 0.3:
            return min(i + 1, 3)
    return 3


# ----------------------------------------------------------------------------
# main conversion
# ----------------------------------------------------------------------------

def convert(pdf_path: str, md_path: str) -> None:
    doc = fitz.open(pdf_path)

    # pass 1: collect font sizes to find the body size + heading sizes
    from collections import Counter
    size_counter = Counter()
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            if b["type"] != 0:
                continue
            for line in b["lines"]:
                for span in line["spans"]:
                    size_counter[round(span["size"], 1)] += 1
    if not size_counter:
        body_size = 9.0
        heading_sizes = []
    else:
        body_size = size_counter.most_common(1)[0][0]
        heading_sizes = sorted(
            (s for s in size_counter if s > body_size + 0.8), reverse=True
        )[:3]

    out = []
    prev_h_norm = None

    for pno in range(doc.page_count):
        page = doc[pno]
        elements = []

        d = page.get_text("dict")
        for b in d["blocks"]:
            if b["type"] == 0:
                for line in b["lines"]:
                    y0 = line["bbox"][1]
                    text = "".join(s["text"] for s in line["spans"]).strip()
                    if not text:
                        continue
                    is_code = any(
                        "Menlo" in (s.get("font") or "") for s in line["spans"]
                    )
                    size = max((s["size"] for s in line["spans"]), default=body_size)
                    elements.append((y0, "text", (text, is_code, size)))

        # images (use real xref from get_images; bbox from get_image_rects)
        try:
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    rects = page.get_image_rects(xref)
                except Exception:
                    rects = []
                if not rects:
                    continue
                bbox = rects[0]
                w = abs(bbox[2] - bbox[0])
                h = abs(bbox[3] - bbox[1])
                if w < 5 or h < 5:
                    continue
                try:
                    uri = img_to_uri(doc, xref)
                except Exception as e:
                    print("img err", e, file=sys.stderr)
                    continue
                elements.append((float(bbox[1]), "img", uri))
        except Exception as e:
            print("img loop err", e, file=sys.stderr)

        elements.sort(key=lambda e: e[0])

        code_buf = []
        para = []

        def flush_code():
            nonlocal code_buf
            if not code_buf:
                return
            if len(code_buf) == 1 and not is_real_code(code_buf[0]):
                # single Menlo line that is actually prose -> body
                out.append(code_buf[0])
                out.append("")
            else:
                block = "\n".join(code_buf)
                out.append(f"```{code_lang(block)}")
                out.append(block)
                out.append("```")
                out.append("")
            code_buf = []

        def flush_para():
            nonlocal para
            if not para:
                return
            out.append("".join(para).strip())
            out.append("")
            para = []

        for y0, kind, payload in elements:
            if kind == "img":
                flush_para()
                flush_code()
                out.append(payload)
                out.append("")
                continue

            text, is_code, size = payload
            h = heading_level(size, heading_sizes, body_size)

            if is_code:
                flush_para()
                code_buf.append(text)
                continue

            flush_code()

            if h:
                flush_para()
                t = text.strip()
                if h == 1:
                    t = re.sub(r"^\s*\d+\s*", "", t).strip()
                    nn = norm_title(t)
                    if prev_h_norm and nn == prev_h_norm:
                        prev_h_norm = nn
                        continue  # de-duplicate repeated H1 (e.g. page headers)
                    out.append(f"# {t}")
                    out.append("")
                    prev_h_norm = nn
                else:
                    nn = norm_title(t)
                    if prev_h_norm and nn == prev_h_norm:
                        prev_h_norm = nn
                        continue
                    out.append(f"{'#' * h} {t}")
                    out.append("")
                    prev_h_norm = nn
                continue

            lst = re.match(r"^(\d+)[.、)）]\s*(.*)$", text)
            if lst:
                flush_para()
                out.append(f"{lst.group(1)}. {lst.group(2)}".rstrip())
                out.append("")
                continue
            if re.match(r"^\s*[-•*]\s+", text):
                flush_para()
                out.append(re.sub(r"^(\s*)[-•*]\s+", "- ", text).rstrip())
                out.append("")
                continue

            last = text.rstrip()[-1:] if text.rstrip() else ""
            para.append(text.strip())
            if last in TERM:
                flush_para()

        flush_para()
        flush_code()

    md = "\n".join(out).rstrip() + "\n"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"converted {pdf_path} -> {md_path} ({len(md)} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: convert_pdf.py <input.pdf> <output.md>")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
