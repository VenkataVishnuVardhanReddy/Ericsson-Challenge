"""Break PDFs / PowerPoints into slides and give every slide a stable identifier.

Each slide gets two identifiers:
* content_id : sha256 of the slide's normalised text + hashes of its embedded images,
               *excluding deck boilerplate* (page numbers, repeated footers such as
               document number, date, "Ericsson Internal"). The same slide copied into
               another deck therefore gets the SAME id even though its footer differs.
* phash      : 64-bit perceptual hash of the rendered slide -> visual near-duplicate and
               revision detection via Hamming distance.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw

from . import config as C
from .util import (find_doc_number, find_revision, norm_text, phash_img, sha256_bytes,
                   store_image, text_hash)

_pure_num = re.compile(r"^\s*(slide|page|sida)?\s*\d{1,4}\s*(/\s*\d{1,4})?\s*$", re.I)
_digits = re.compile(r"\d+")


def _line_tpl(line: str) -> str:
    return _digits.sub("#", norm_text(line))


def _boilerplate(pages_lines: list[list[str]]) -> set[str]:
    """Digit-masked line templates that repeat on most pages of a deck (footers/headers)."""
    if len(pages_lines) < 3:
        return set()
    cnt = Counter()
    for lines in pages_lines:
        cnt.update({_line_tpl(l) for l in lines if l.strip()})
    lim = max(2, int(0.6 * len(pages_lines)))
    return {t for t, c in cnt.items() if c >= lim and t}


def _content_id(lines: list[str], boiler: set[str], image_digests: list[str], phash: str) -> tuple[str, str]:
    body = []
    for l in lines:
        nl = norm_text(l)
        if not nl or _line_tpl(l) in boiler or _pure_num.match(nl):
            continue
        body.append(nl)
    core = "\n".join(body)
    payload = core + "\n#img:" + ",".join(sorted(image_digests))
    if not core and not image_digests:   # pure vector graphic -> fall back to the visual hash
        payload = "#vis:" + phash
    return hashlib.sha256(payload.encode()).hexdigest(), core


def _soffice() -> str | None:
    for p in (shutil.which("soffice"), r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
        if p and Path(p).exists():
            return p
    return None


# --------------------------------------------------------------------------- PDF
def process_pdf(path: str) -> dict:
    import fitz

    doc = fitz.open(path)
    meta = {k: v for k, v in (doc.metadata or {}).items() if v}
    pages = []
    all_lines = []
    for page in doc:
        txt = page.get_text("text") or ""
        lines = [l for l in txt.splitlines() if l.strip()]
        all_lines.append(lines)
        # title = largest font span in the upper part of the page
        title, best = "", 0.0
        try:
            d = page.get_text("dict")
            for b in d.get("blocks", []):
                for ln in b.get("lines", []):
                    for sp in ln.get("spans", []):
                        if sp["text"].strip() and sp["size"] > best and sp["bbox"][1] < page.rect.height * 0.4:
                            best, title = sp["size"], sp["text"].strip()
        except Exception:
            pass
        digests = []
        for img in page.get_images(full=True):
            try:
                digests.append(sha256_bytes(doc.extract_image(img[0])["image"])[:16])
            except Exception:
                pass
        zoom = C.SLIDE_RENDER_WIDTH / max(1.0, page.rect.width)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        pages.append({"lines": lines, "text": txt.strip(), "title": title or (lines[0] if lines else ""),
                      "digests": digests, "image": im})
    boiler = _boilerplate(all_lines)
    full_text = "\n".join(p["text"] for p in pages)
    first = pages[0]["text"] if pages else ""
    slides = []
    for i, p in enumerate(pages, 1):
        ph = phash_img(p["image"])
        cid, core = _content_id(p["lines"], boiler, p["digests"], ph)
        key, nbytes = store_image(p["image"], C.SLIDE_RENDER_WIDTH, 72)
        slides.append({"page_no": i, "content_id": cid, "phash": ph, "text": p["text"], "core": core,
                       "title": p["title"][:200], "object_hash": key, "bytes": nbytes})
    doc_no = find_doc_number(meta.get("subject", "") + " " + meta.get("keywords", "") + " " + first) \
        or find_doc_number(full_text)
    return {
        "kind": "pdf",
        "title": meta.get("title") or (pages[0]["title"] if pages else Path(path).stem),
        "author": meta.get("author"),
        "doc_date": meta.get("modDate") or meta.get("creationDate"),
        "doc_number": doc_no,
        "revision": find_revision(meta.get("subject", "") + " " + meta.get("keywords", "") + " " + first)
        or find_revision(full_text) or find_revision(Path(path).stem),
        "text_hash": text_hash("\n".join(s["core"] for s in slides)),
        "slides": slides,
        "meta": {**meta, "pages": len(slides), "boilerplate": sorted(boiler)[:20]},
    }


# --------------------------------------------------------------------------- PPTX
def _pptx_preview(title: str, body: list[str]) -> Image.Image:
    """Crisp text preview if LibreOffice is not installed to render the real slide."""
    from PIL import ImageFont

    im = Image.new("RGB", (960, 540), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 960, 76], fill=(0, 37, 97))
    try:
        ft = ImageFont.truetype("arial.ttf", 24)
        fb = ImageFont.truetype("arial.ttf", 17)
    except Exception:
        ft = fb = ImageFont.load_default()
    d.text((30, 24), (title or "Untitled Slide")[:72], fill="white", font=ft)
    y = 104
    for l in body[:13]:
        d.text((40, y), "• " + l[:92], fill=(20, 30, 45), font=fb)
        y += 30
    return im


def process_pptx(path: str) -> dict:
    from pptx import Presentation

    prs = Presentation(path)
    cp = prs.core_properties
    rendered: list[Image.Image] | None = None
    so = _soffice()
    if so:  # real rendering through LibreOffice -> PDF -> images
        try:
            with tempfile.TemporaryDirectory() as td:
                subprocess.run([so, "--headless", "--convert-to", "pdf", "--outdir", td, path],
                               check=True, capture_output=True, timeout=180)
                import fitz

                pdf = fitz.open(next(Path(td).glob("*.pdf")))
                rendered = []
                for page in pdf:
                    zoom = C.SLIDE_RENDER_WIDTH / page.rect.width
                    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                    rendered.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
        except Exception:
            rendered = None

    raw = []
    for slide in prs.slides:
        lines, digests, title, notes = [], [], "", ""
        for shp in slide.shapes:
            if shp.has_text_frame:
                for para in shp.text_frame.paragraphs:
                    t = "".join(r.text for r in para.runs).strip()
                    if t:
                        lines.append(t)
            if getattr(shp, "has_table", False) and shp.has_table:
                for row in shp.table.rows:
                    lines.append(" | ".join(c.text for c in row.cells))
            if shp.shape_type == 13:  # picture
                try:
                    digests.append(sha256_bytes(shp.image.blob)[:16])
                except Exception:
                    pass
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            title = slide.shapes.title.text_frame.text.strip()
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        raw.append({"lines": lines, "digests": digests, "title": title or (lines[0] if lines else ""), "notes": notes})

    boiler = _boilerplate([r["lines"] for r in raw])
    slides = []
    for i, r in enumerate(raw, 1):
        im = rendered[i - 1] if rendered and i - 1 < len(rendered) else _pptx_preview(r["title"], r["lines"][1:])
        ph = phash_img(im)
        cid, core = _content_id(r["lines"], boiler, r["digests"], ph)
        key, nbytes = store_image(im, C.SLIDE_RENDER_WIDTH, 72)
        text = "\n".join(r["lines"]) + (f"\n[Speaker notes] {r['notes']}" if r["notes"] else "")
        slides.append({"page_no": i, "content_id": cid, "phash": ph, "text": text, "core": core,
                       "title": r["title"][:200], "object_hash": key, "bytes": nbytes})
    full = "\n".join(s["text"] for s in slides)
    head = " ".join(filter(None, [cp.subject, cp.keywords, cp.identifier if hasattr(cp, "identifier") else "",
                                  slides[0]["text"] if slides else ""]))
    return {
        "kind": "pptx",
        "title": cp.title or (slides[0]["title"] if slides else Path(path).stem),
        "author": cp.author or cp.last_modified_by,
        "doc_date": (cp.modified or cp.created).isoformat() if (cp.modified or cp.created) else None,
        "doc_number": find_doc_number(head) or find_doc_number(full),
        "revision": find_revision(head) or find_revision(full) or find_revision(Path(path).stem)
        or (str(cp.revision) if cp.revision else None),
        "text_hash": text_hash("\n".join(s["core"] for s in slides)),
        "slides": slides,
        "meta": {"pages": len(slides), "rendered": bool(rendered), "boilerplate": sorted(boiler)[:20]},
    }


# --------------------------------------------------------------------------- DOCX & MSG (chat / notes)
def process_docx(path: str) -> dict:
    import defusedxml.ElementTree as ET
    import zipfile

    with zipfile.ZipFile(path) as z:
        total_size = sum(info.file_size for info in z.infolist())
        if total_size > 500 * 1024 * 1024:
            raise ValueError("ZIP bomb guard triggered: uncompressed size exceeds 500 MB limit")
        root = ET.fromstring(z.read("word/document.xml"))
    paras = []
    for p in root.iter():
        if p.tag.endswith("}p"):
            t = "".join(el.text for el in p.iter() if el.tag.endswith("}t") and el.text).strip()
            if t:
                paras.append(t)
    full = "\n".join(paras)
    return {
        "title": paras[0][:120] if paras else Path(path).stem,
        "text": full,
        "text_hash": text_hash(full) if full else None,
        "doc_number": find_doc_number(full),
        "revision": find_revision(full) or find_revision(Path(path).stem),
    }


def process_msg(path: str) -> dict:
    try:
        import olefile
        ole = olefile.OleFileIO(path)
        for entry in ole.listdir():
            path_str = "/".join(entry)
            if "1000001" in path_str:
                body = ole.openstream(entry).read().decode("utf-16le", errors="ignore").strip()
                if body:
                    return {"title": Path(path).stem, "text": body, "text_hash": text_hash(body)}
    except Exception:
        pass
    raw = Path(path).read_bytes()
    u16 = raw.decode("utf-16le", errors="ignore")
    blocks = []
    for m in re.finditer(r"[\x20-\x7e\r\n\t\u00a0-\u00ff]{25,}", u16):
        s = m.group(0).strip()
        if any(k in s.lower() for k in ("[1", "[0", "[2", "http", "ericsson", "chat", "links")):
            blocks.append(s)
    full = "\n\n".join(dict.fromkeys(blocks))
    return {
        "title": Path(path).stem,
        "text": full,
        "text_hash": text_hash(full) if full else None,
    }

