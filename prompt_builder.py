"""根据 BookProfile + 用户示例动态生成 book-specific 提取 prompt

通用 prompt 需覆盖所有情况，词量约 600+。
book-specific prompt 只描述这本书实际的特征，通常 200-300 词，省 ~60% system token。
"""


def build_extraction_prompt(profile: dict, user_example: str) -> str:
    """
    Args:
        profile:      analyze_book() 返回的 BookProfile dict
        user_example: 用户提供的提取示例（展示期望的输入→输出格式）

    Returns:
        用于提取阶段的 system prompt 字符串
    """
    layout = profile.get("layout", "single_column")
    language = profile.get("language", "en")
    qa_style = profile.get("qa_marker_style", "")
    math = profile.get("math_density", "low")
    has_chapters = profile.get("has_chapter_structure", False)
    qa_length = profile.get("typical_qa_length", "medium")
    notes = profile.get("content_notes", "")

    # 按实际特征拼装指令，不相关的部分不写
    parts = []

    parts.append("你是一名内容提取员。输入是一本书的连续若干页扫描/排版图片，请把其中的内容逐一提取为结构化数据。")

    # 版面
    if layout == "double_column":
        parts.append("本书为双列排版，请按正常阅读顺序（先读完左列再读右列）理解内容。")
    elif layout == "mixed":
        parts.append("本书版面混合（部分页双列），注意判断当前页的排版再阅读。")

    # Q&A 标记方式
    if qa_style:
        parts.append(f"题目标记方式：{qa_style}。以此为切题依据。")

    # 公式
    if math == "high":
        parts.append("本书含大量数学公式，stem_latex 字段请用 LaTeX 表达题干中的公式；无公式则留空字符串。")
    elif math == "low":
        parts.append("stem_latex 字段：有公式则写 LaTeX，否则留空字符串。")
    else:
        parts.append("stem_latex 字段留空字符串即可。")

    # 章节
    if has_chapters:
        parts.append("遇到章节/小节标题时忽略，不作为提取内容。")

    # 长度提示（影响窗口能装多少题）
    if qa_length == "long":
        parts.append("题目较长，答案可能跨页；若答案在本批页面范围内未出现，answer_markdown 留空字符串，并将 needs_review 置为 true。")

    # 特殊注意
    if notes:
        parts.append(f"注意：{notes}")

    # 通用规则（精简版）
    parts.append(
        "通用规则：①忠实原文，不编造补全。②看不清的字用…占位，needs_review 置 true。"
        "③跨页截断的题仍提取已有部分，notes 注明'疑似跨页截断'。"
        "④目录、版权页、页眉页脚、页码一律忽略。"
    )

    # 用户示例
    if user_example.strip():
        parts.append(f"\n## 提取示例（展示期望格式）\n\n{user_example.strip()}")

    # 输出格式
    parts.append('\n## 输出\n严格按给定 JSON schema 输出 {"items": [...]}。本批无内容则返回 {"items": []}。')

    return "\n\n".join(parts)
