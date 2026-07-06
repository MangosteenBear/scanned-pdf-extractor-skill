"""PDF 渲染模块：PDF → 页面图片 + render_meta.json"""
import json
from pathlib import Path

_SCANNED_CHAR_THRESHOLD = 50
_SCANNED_RATIO_THRESHOLD = 0.8


def render_pdf(pdf_path: str, out_dir: str, dpi: int = 200) -> dict:
    """
    将 PDF 渲染为逐页 PNG 图片。

    输出：
      {out_dir}/page_XXXX.png
      {out_dir}/render_meta.json

    Returns:
        render_meta dict
    """
    import fitz

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    total = len(doc)
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pages_meta, scanned_count = [], 0

    for i, page in enumerate(doc):
        img_path = out / f"page_{i+1:04d}.png"
        pix = page.get_pixmap(matrix=mat, alpha=False)
        pix.save(str(img_path))

        text = page.get_text()
        char_count = len(text.strip())
        is_scanned = char_count < _SCANNED_CHAR_THRESHOLD
        if is_scanned:
            scanned_count += 1

        pages_meta.append({
            "page": i + 1,
            "image": str(img_path),
            "char_count": char_count,
            "is_scanned": is_scanned,
        })

    doc.close()

    scan_ratio = scanned_count / total if total else 0
    meta = {
        "source": pdf_path,
        "total_pages": total,
        "dpi": dpi,
        "is_scanned_pdf": scan_ratio > _SCANNED_RATIO_THRESHOLD,
        "pages": pages_meta,
    }
    (out / "render_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta
