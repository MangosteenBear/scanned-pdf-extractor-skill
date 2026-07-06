"""Phase 1: 书籍结构分析

抽样首/中/尾共 ~9 页 → 让模型输出 BookProfile JSON。
成本极低（~$0.05），为后续提取生成 book-specific prompt。
"""
import base64
import io
import json
from pathlib import Path
from typing import Any

from config import DEFAULT, ExtractorConfig
from client import create_message

_PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "layout":               {"type": "string"},
                    "language":             {"type": "string"},
                    "qa_marker_style":      {"type": "string"},
                    "math_density":         {"type": "string"},
                    "has_chapter_structure":{"type": "boolean"},
                    "typical_qa_length":    {"type": "string"},
                    "content_notes":        {"type": "string"},
                },
                "required": ["layout", "language", "qa_marker_style", "math_density",
                             "has_chapter_structure", "typical_qa_length", "content_notes"],
                "additionalProperties": False,
            }
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

_ANALYZE_SYSTEM = (
    "You are a document structure analyst. I will show you sampled pages from a book. "
    "Analyze the layout and content characteristics, then output a single profile object inside the 'items' array. "
    "Only describe what you actually observe — do not guess."
    "\n\nFields to fill:\n"
    "- layout: single_column / double_column / mixed\n"
    "- language: en / zh / mixed\n"
    "- qa_marker_style: describe how Q&A are marked, e.g. 'Q: ... A: ...' or 'Problem N. ... Solution.'\n"
    "- math_density: none / low / high\n"
    "- has_chapter_structure: true/false\n"
    "- typical_qa_length: short(<100 words) / medium(100-300 words) / long(>300 words)\n"
    "- content_notes: any other layout or content quirks worth noting for extraction"
)


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


def _sample_pages(pages: list[dict], n: int) -> list[dict]:
    candidates = pages[2:]  # 跳过封面
    if len(candidates) <= n:
        return candidates
    step = len(candidates) / n
    return [candidates[int(i * step)] for i in range(n)]


def analyze_book(render_meta_path: str, cfg: ExtractorConfig = DEFAULT) -> dict:
    """分析书籍结构，返回 BookProfile dict。"""
    meta = json.loads(Path(render_meta_path).read_text(encoding="utf-8"))
    pages = meta["pages"]
    samples = _sample_pages(pages, cfg.analyze_sample_pages)

    content: list[dict] = []
    for p in samples:
        content.append({"type": "text", "text": f"[Page {p['page']}]"})
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": _encode_image(p["image"], 800),
            },
        })
    content.append({
        "type": "text",
        "text": "These are sampled pages from the book (beginning, middle, end). Analyze the structure and output one profile object in the 'items' array.",
    })

    items = create_message(_ANALYZE_SYSTEM, content, cfg, _PROFILE_SCHEMA)
    return items[0] if items else {}
