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

_PROFILE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "layout": {
            "type": "string",
            "description": "版面类型: single_column / double_column / mixed"
        },
        "language": {
            "type": "string",
            "description": "主要语言: en / zh / mixed"
        },
        "qa_marker_style": {
            "type": "string",
            "description": "题目标记方式，如 'Q: ... A: ...' / 'Problem N. ... Solution.' / '第N题 ... 解答：' 等，用原文举例"
        },
        "math_density": {
            "type": "string",
            "description": "公式密度: none / low / high"
        },
        "has_chapter_structure": {
            "type": "boolean",
            "description": "是否有章节/小节标题"
        },
        "typical_qa_length": {
            "type": "string",
            "description": "典型题目长度: short(<100字) / medium(100-300字) / long(>300字)"
        },
        "content_notes": {
            "type": "string",
            "description": "其他需要提取时注意的特殊排版或内容特征，简短说明"
        }
    },
    "required": ["layout", "language", "qa_marker_style", "math_density",
                 "has_chapter_structure", "typical_qa_length", "content_notes"],
    "additionalProperties": False
}

_ANALYZE_SYSTEM = """你是一名文档结构分析专家。我会给你一本书的几个抽样页面，你的任务是分析这本书的排版结构和内容特征，输出一个简短的结构描述，用于指导后续的内容提取工作。请只描述你实际观察到的，不要猜测。"""


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
    """从首/中/尾均匀抽样，跳过第 1-2 页（通常是封面/版权页）"""
    candidates = pages[2:]
    if len(candidates) <= n:
        return candidates
    step = len(candidates) / n
    return [candidates[int(i * step)] for i in range(n)]


def analyze_book(
    render_meta_path: str,
    cfg: ExtractorConfig = DEFAULT,
) -> dict:
    """
    分析书籍结构，返回 BookProfile dict。
    """
    import anthropic

    meta = json.loads(Path(render_meta_path).read_text(encoding="utf-8"))
    pages = meta["pages"]
    samples = _sample_pages(pages, cfg.analyze_sample_pages)

    content: list[dict] = []
    for p in samples:
        content.append({"type": "text", "text": f"【第 {p['page']} 页】"})
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": _encode_image(p["image"], 800),  # 分析阶段用小图省 token
            },
        })
    content.append({
        "type": "text",
        "text": "以上是这本书的抽样页面（首/中/尾各取）。请分析这本书的排版结构和内容特征，按 schema 输出。"
    })

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=cfg.model,
        max_tokens=1000,
        system=_ANALYZE_SYSTEM,
        thinking={"type": "disabled"},
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": _PROFILE_SCHEMA}
        },
        messages=[{"role": "user", "content": content}],
    )

    for block in msg.content:
        if getattr(block, "type", None) == "text":
            return json.loads(block.text)

    return {}
