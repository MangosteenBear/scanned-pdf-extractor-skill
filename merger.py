"""跨窗口去重合并

相邻窗口重叠一页导致同一条内容可能出现两次。
用 Jaccard 相似度 + 页码重叠判断重复，取更完整的一条。
"""
import json
import re
from pathlib import Path

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[一-鿿]")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _page_overlap(q1: dict, q2: dict) -> bool:
    s1, e1 = q1.get("page_start") or 0, q1.get("page_end") or 0
    s2, e2 = q2.get("page_start") or 0, q2.get("page_end") or 0
    return bool(s1 and s2 and not (e1 < s2 or e2 < s1))


def _is_duplicate(q1: dict, q2: dict, threshold: float = 0.6) -> bool:
    m1 = (q1.get("marker") or "").strip()
    m2 = (q2.get("marker") or "").strip()
    sim = _jaccard(_tokens(q1.get("stem_markdown")), _tokens(q2.get("stem_markdown")))
    if m1 and m1 == m2 and (_page_overlap(q1, q2) or sim >= 0.3):
        return True
    return sim >= threshold


def _merge_two(q1: dict, q2: dict) -> dict:
    """两条重复项合并：取题干更长的，答案取更长非空的。"""
    base = q1 if len(q1.get("stem_markdown") or "") >= len(q2.get("stem_markdown") or "") else q2
    merged = dict(base)
    a1 = q1.get("answer_markdown") or ""
    a2 = q2.get("answer_markdown") or ""
    merged["answer_markdown"] = a1 if len(a1) >= len(a2) else a2
    merged["page_start"] = min(q1.get("page_start") or 9999, q2.get("page_start") or 9999)
    merged["page_end"] = max(q1.get("page_end") or 0, q2.get("page_end") or 0)
    return merged


def merge_windows(raw_jsonl_path: str, out_path: str, threshold: float = 0.6) -> list[dict]:
    """
    读取 extract_raw.jsonl，合并跨窗重复项，写出 extracted.json。

    Returns:
        合并后的 items 列表
    """
    all_items: list[dict] = []
    for line in Path(raw_jsonl_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        window = json.loads(line)
        all_items.extend(window.get("items", []))

    # 顺序去重：对每个新 item，检查是否已有重复
    merged: list[dict] = []
    for item in all_items:
        t = _tokens(item.get("stem_markdown"))
        found = False
        for i, existing in enumerate(merged):
            if _is_duplicate(existing, item, threshold):
                merged[i] = _merge_two(existing, item)
                found = True
                break
        if not found:
            merged.append(item)

    Path(out_path).write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return merged
