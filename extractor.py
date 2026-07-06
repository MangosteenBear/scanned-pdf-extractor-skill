"""Phase 2: 内容提取

用 book-specific prompt + 用户自定义 schema 做滑窗提取。
schema 由用户示例推导，支持任意结构（不限于 Q&A）。
"""
import base64
import io
import json
from pathlib import Path
from typing import Any

from config import DEFAULT, ExtractorConfig

# 通用 item schema：stem/answer 是必须字段，其余由用户示例决定
# 用户可通过 extra_fields 参数扩展
_BASE_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "stem_markdown": {"type": "string"},
        "stem_latex": {"type": "string"},
        "answer_markdown": {"type": "string"},
        "marker": {"type": "string"},
        "page_start": {"type": "integer"},
        "page_end": {"type": "integer"},
        "confidence": {"type": "number"},
        "needs_review": {"type": "boolean"},
        "notes": {"type": "string"},
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
    "properties": {
        "items": {"type": "array", "items": _BASE_ITEM_SCHEMA}
    },
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
        content.append({"type": "text", "text": f"【第 {p['page']} 页】"})
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
            f"以上依次是第 {page_nos[0]}–{page_nos[-1]} 页。"
            f"请提取其中所有内容，按 schema 输出 {{\"items\": [...]}}。"
            f"page_start / page_end 用上面标注的页码。"
        ),
    })
    return content


def _estimate_cost(usage: dict, cfg: ExtractorConfig, batch: bool) -> float:
    m = cfg.batch_mult if batch else 1.0
    cost = (
        usage.get("input_tokens", 0) * cfg.price_in
        + usage.get("cache_read_input_tokens", 0) * cfg.price_in * 0.1
        + usage.get("cache_creation_input_tokens", 0) * cfg.price_in * 1.25
        + usage.get("output_tokens", 0) * cfg.price_out
    ) / 1_000_000
    return cost * m


def _usage_dict(usage: Any) -> dict:
    return {k: getattr(usage, k, 0) or 0 for k in
            ["input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"]}


def _parse_items(message: Any) -> list[dict]:
    for block in message.content:
        if getattr(block, "type", None) == "text":
            return json.loads(block.text).get("items", [])
    return []


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

    Args:
        render_meta_path: render_meta.json 路径
        out_dir:          产物目录
        system_prompt:    由 prompt_builder 生成的 book-specific prompt
        cfg:              配置
        page_range:       只处理这些页码；None = 全书
        on_progress:      可选回调 fn(current_window, total_windows, n_items, cost)

    Returns:
        {"windows": [...], "total_cost": float, "n_windows": int}
    """
    import anthropic

    meta = json.loads(Path(render_meta_path).read_text(encoding="utf-8"))
    pages = meta["pages"]
    if page_range:
        pages = [p for p in pages if p["page"] in page_range]
    if not pages:
        raise ValueError("没有符合 page_range 的页面")

    wins = _windows(pages, cfg.window_size, cfg.window_overlap)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / "extract_raw.jsonl"
    raw_path.write_text("", encoding="utf-8")

    system = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
    client = anthropic.Anthropic()

    results, cumulative = [], 0.0
    for idx, win in enumerate(wins):
        page_nos = [p["page"] for p in win]
        try:
            msg = client.messages.create(
                model=cfg.model,
                max_tokens=cfg.max_tokens,
                system=system,
                thinking={"type": "disabled"},
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA}},
                messages=[{"role": "user", "content": _build_content(win, cfg)}],
            )
        except Exception as e:
            r = {"pages": page_nos, "items": [], "usage": {}, "cost": 0.0,
                 "error": type(e).__name__ + ": " + str(e)[:160]}
            results.append(r)
            _append_jsonl(str(raw_path), r)
            continue

        usage = _usage_dict(msg.usage)
        cost = _estimate_cost(usage, cfg, batch=False)
        cumulative += cost
        items = _parse_items(msg)
        r = {"pages": page_nos, "items": items, "usage": usage, "cost": cost}
        results.append(r)
        _append_jsonl(str(raw_path), r)

        if on_progress:
            on_progress(idx + 1, len(wins), len(items), cumulative)

        if cumulative > cfg.max_cost_usd:
            break

    return {"windows": results, "total_cost": cumulative, "n_windows": len(wins)}
