"""scripts/render_pptx_slides.py
Re-renders ONLY the two SD-WAN PPTX files (5 and 11) using PowerPoint COM.
Updates existing slide rows in place (object_hash, phash, bytes) matched by file_id + page_no.
Sets files.meta.rendered = true.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import distill.config as C
import distill.db as db
from distill.util import phash_img, store_image


def render_file(file_id: int):
    f = db.q1("SELECT id, name, path, meta FROM files WHERE id=?", (file_id,))
    if not f:
        print(f"File {file_id} not found.")
        return

    path = Path(f["path"]).resolve()
    print(f"\nRe-rendering File {file_id}: {f['name']}")

    ppt = None
    pres = None
    rendered_images: list[tuple[int, Image.Image]] = []

    try:
        import win32com.client
        ppt = win32com.client.Dispatch("PowerPoint.Application")
        pres = ppt.Presentations.Open(str(path), WithWindow=False, ReadOnly=True)
        count = pres.Slides.Count
        print(f"  PowerPoint opened {count} slides.")

        with tempfile.TemporaryDirectory() as td:
            for page_no in range(1, count + 1):
                tmp_img = Path(td) / f"slide_{page_no}.png"
                pres.Slides(page_no).Export(str(tmp_img), "PNG", 1920, 1080)
                if tmp_img.exists():
                    im = Image.open(tmp_img)
                    im.load()
                    rendered_images.append((page_no, im))
                else:
                    print(f"  Warning: failed to export slide {page_no}")

        pres.Close()
        pres = None
        ppt.Quit()
        ppt = None
    except Exception as e:
        print(f"  PowerPoint COM error: {e}")
        if pres:
            try:
                pres.Close()
            except Exception:
                pass
        if ppt:
            try:
                ppt.Quit()
            except Exception:
                pass

    if not rendered_images:
        print("  Error: No slides were rendered.")
        return

    print(f"  Successfully rendered {len(rendered_images)} slides. Updating database...")

    with db.tx() as conn:
        for page_no, im in rendered_images:
            ph = phash_img(im)
            obj_hash, nbytes = store_image(im, C.SLIDE_RENDER_WIDTH, 72)

            conn.execute(
                "UPDATE slides SET object_hash=?, phash=?, bytes=? WHERE file_id=? AND page_no=?",
                (obj_hash, ph, nbytes, file_id, page_no),
            )
            print(f"    Page {page_no:02d}: obj={obj_hash[:12]}..., phash={ph[:12]}..., bytes={nbytes}")

        meta = json.loads(f["meta"] or "{}") if isinstance(f["meta"], str) else (f["meta"] or {})
        meta["rendered"] = True
        conn.execute("UPDATE files SET meta=? WHERE id=?", (json.dumps(meta), file_id))

    print(f"  [OK] File {file_id} updated. files.meta.rendered set to True.")


def main():
    print("======================================================================")
    print(" Distill: Re-rendering SD-WAN PPTX Slides (Files 5 and 11)")
    print("======================================================================")
    for fid in [5, 11]:
        render_file(fid)
    print("\n[OK] Re-rendering complete.")


if __name__ == "__main__":
    main()
