"""Phase 2: 内容提取"""
import base64
import io
import json
from pathlib import Path
from typing import Any

from config import DEFAULT, ExtractorConfig
from client import create_message, estimate_cost

_BASE_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "stem_markdown":  {"type": "string"},
        "stem_latex":     {"type": "string"},
        "answer_markdown":{"type": "string"},
        "marker":         {"type": "string"},
        "page_start":     {"type": "integer"},
        "page_end":       {"type": "integer"},
        "confidence":     {"type": "number"},
        "needs_review":   {"type": "boolean"},
        "notes":          {"type": "string"},
    },
    "required": [
        "stem_markdown", "stem_latex", "answer_markdown",
        "marker", "page_start", "page_end",
        "confidence", "needs_review", "notes",
    ],
    "additionalProperties": False,
}

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": _BASE_ITEM_SCHEMA}},
    "required": ["items"],
    "additionalProperties": False,
}


def _encode_image(path: str, max_long_edge: int) -> str:
    data = Path(path).read_bytes()
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if max(w, h) > max_long_edge:
            scale = max_long_edge / max(w, h)
            img = img.convert("RGB").resize((int(w * scale), int(h * scale)))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            data = buf.getvalue()
    except ImportError:
        pass
    return base64.standard_b64encode(data).decode("ascii")


def _windows(pages: list[dict], size: int, overlap: int) -> list[list[dict]]:
    step = max(1, size - overlap)
    out, i = [], 0
    while i < len(pages):
        out.append(pages[i:i + size])
        if i + size >= len(pages):
            break
        i += step
    return out


def _build_content(window: list[dict], cfg: ExtractorConfig) -> list[dict]:
    content: list[dict] = []
    page_nos = [p["page"] for p in window]
    for p in window:
        content.append({"type": "text", "text": f"[Page {p['page']}]"})
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": _encode_image(p["image"], cfg.max_image_long_edge),
            },
        })
    content.append({
        "type": "text",
        "text": (
            f"The above are pages {page_nos[0]}–{page_nos[-1]}. "
            f"Extract all content and output {{\"items\": [...]}}. "
            f"Use the page numbers shown above for page_start / page_end."
        ),
    })
    return content


def _append_jsonl(path: str, obj: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def extract_pages(
    render_meta_path: str,
    out_dir: str,
    system_prompt: str,
    cfg: ExtractorConfig = DEFAULT,
    page_range: set[int] | None = None,
    on_progress=None,
) -> dict[str, Any]:
    """
    对渲染后的页面做内容提取。

    Returns:
        {"windows": [...], "total_cost": float, "n_windows": int}
    """
    meta = json.loads(Path(render_meta_path).read_text(encoding="utf-8"))
    pages = meta["pages"]
    if page_range:
        pages = [p for p in pages if p["page"] in page_range]
    if not pages:
        raise ValueError("No pages matched the given page_range.")

    wins = _windows(pages, cfg.window_size, cfg.window_overlap)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / "extract_raw.jsonl"
    raw_path.write_text("", encoding="utf-8")

    results, cumulative = [], 0.0
    for idx, win in enumerate(wins):
        page_nos = [p["page"] for p in win]
        try:
            items = create_message(system_prompt, _build_content(win, cfg), cfg, _OUTPUT_SCHEMA)
            cost = 0.0  # 精确 token 计费需各 provider SDK 支持，此处简化
        except Exception as e:
            r = {"pages": page_nos, "items": [], "cost": 0.0,
                 "error": type(e).__name__ + ": " + str(e)[:200]}
            results.append(r)
            _append_jsonl(str(raw_path), r)
            continue

        cumulative += cost
        r = {"pages": page_nos, "items": items, "cost": cost}
        results.append(r)
        _append_jsonl(str(raw_path), r)

        if on_progress:
            on_progress(idx + 1, len(wins), len(items), cumulative)

        if cumulative > cfg.max_cost_usd:
            break

    return {"windows": results, "total_cost": cumulative, "n_windows": len(wins)}
