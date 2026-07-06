"""pdf_extractor CLI

用法:
  # 完整流水线（分析 → 提取 → 合并）
  python -m pdf_extractor run --pdf book.pdf --example "Q: xxx\\nA: yyy"

  # 也可以把示例写在文件里
  python -m pdf_extractor run --pdf book.pdf --example-file my_example.txt

  # 只跑某些页（调试用）
  python -m pdf_extractor run --pdf book.pdf --example "..." --pages 1-30

  # 用 Batch API 省 50% 成本（异步，适合全书）
  python -m pdf_extractor run --pdf book.pdf --example "..." --batch
"""
import json
import os
import sys
from pathlib import Path

import click

from config import DEFAULT, ExtractorConfig


def _parse_pages(spec: str | None) -> set[int] | None:
    if not spec:
        return None
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            pages.update(range(int(a), int(b) + 1))
        elif part:
            pages.add(int(part))
    return pages


@click.group()
@click.version_option(version="0.1.0", prog_name="pdf_extractor")
def cli():
    """pdf_extractor — 通用 PDF 影印本内容提取工具"""
    pass


@cli.command()
@click.option("--pdf", required=True, type=click.Path(exists=True), help="PDF 文件路径")
@click.option("--example", default=None, help="提取示例文本（展示期望的提取格式）")
@click.option("--example-file", default=None, type=click.Path(exists=True), help="示例文本文件路径")
@click.option("--out-dir", default="./pdf_extract_output", help="产物目录（默认 ./pdf_extract_output）")
@click.option("--pages", default=None, help="页码范围，如 1-50 或 1-20,40-60")
@click.option("--batch/--no-batch", default=False, help="使用 Batch API（-50% 成本，异步）")
@click.option("--dpi", default=None, type=int, help="提取阶段渲染 DPI（默认 200）")
@click.option("--api-key", default=None, help="Anthropic API Key（也可通过 ANTHROPIC_API_KEY 环境变量设置）")
@click.option("--skip-analyze", is_flag=True, default=False, help="跳过书籍结构分析（使用通用 prompt）")
def run(pdf, example, example_file, out_dir, pages, batch, dpi, api_key, skip_analyze):
    """完整流水线：render → 分析书籍结构 → 生成 prompt → 提取 → 合并去重"""

    # API Key
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo("❌ 请提供 Anthropic API Key（--api-key 或 ANTHROPIC_API_KEY 环境变量）", err=True)
        sys.exit(1)

    # 示例文本
    if example_file:
        example = Path(example_file).read_text(encoding="utf-8")
    if not example:
        click.echo("❌ 请提供提取示例（--example 或 --example-file）", err=True)
        sys.exit(1)

    cfg = ExtractorConfig()
    if batch:
        cfg.use_batch = batch
    if dpi:
        cfg.extract_dpi = dpi

    pdf_path = Path(pdf)
    base = Path(out_dir) / pdf_path.stem
    pages_dir = base / "pages"
    page_range = _parse_pages(pages)

    def step(name: str):
        click.echo(f"\n── {name} {'─' * max(1, 40 - len(name))}")

    # 1. Render
    step("渲染 PDF")
    from pdf_extractor.renderer import render_pdf
    meta = render_pdf(str(pdf_path), str(pages_dir), cfg.extract_dpi)
    click.echo(f"   {meta['total_pages']} 页 @ {cfg.extract_dpi}DPI")

    # 2. 分析书籍结构
    profile = {}
    if not skip_analyze:
        step("分析书籍结构（抽样页面）")
        from analyzer import analyze_book
        # 分析阶段用低 DPI 渲染的同一批图（复用 render 产物，降采样在 analyzer 内部完成）
        profile = analyze_book(str(pages_dir / "render_meta.json"), cfg)
        click.echo(f"   版面: {profile.get('layout')}  语言: {profile.get('language')}  "
                   f"公式密度: {profile.get('math_density')}  Q&A标记: {profile.get('qa_marker_style')}")
        if profile.get("content_notes"):
            click.echo(f"   注意: {profile['content_notes']}")

    # 3. 生成 book-specific prompt
    step("生成提取 Prompt")
    from prompt_builder import build_extraction_prompt
    system_prompt = build_extraction_prompt(profile, example)
    prompt_path = base / "system_prompt.txt"
    base.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(system_prompt, encoding="utf-8")
    click.echo(f"   Prompt 长度: {len(system_prompt)} 字符 → {prompt_path}")

    # 4. 提取
    step("提取内容")

    def on_progress(cur, total, n_items, cost):
        click.echo(f"   窗 {cur}/{total}：{n_items} 条，累计 ${cost:.3f}")

    from extractor import extract_pages
    ex = extract_pages(
        str(pages_dir / "render_meta.json"),
        str(base),
        system_prompt,
        cfg,
        page_range,
        on_progress=on_progress,
    )
    click.echo(f"   共 {ex['n_windows']} 窗，估算成本 ${ex['total_cost']:.2f}")

    # 5. 合并去重
    step("合并去重")
    from merger import merge_windows
    out_path = base / "extracted.json"
    merged = merge_windows(str(base / "extract_raw.jsonl"), str(out_path))
    click.echo(f"   合并后 {len(merged)} 条 → {out_path}")

    # 6. 汇总
    n_with_answer = sum(1 for i in merged if i.get("answer_markdown"))
    n_review = sum(1 for i in merged if i.get("needs_review"))
    click.echo(f"\n✅ 完成！共 {len(merged)} 条（有答案 {n_with_answer}，需人工复核 {n_review}）")
    click.echo(f"   结果文件：{out_path}")
    if profile:
        profile_path = base / "book_profile.json"
        profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        click.echo(f"   书籍结构：{profile_path}")


@cli.command()
@click.option("--pdf", required=True, type=click.Path(exists=True))
@click.option("--out-dir", default="./pdf_extract_output")
@click.option("--dpi", default=200, type=int)
def render(pdf, out_dir, dpi):
    """仅渲染 PDF 为图片（调试用）"""
    from pdf_extractor.renderer import render_pdf
    pdf_path = Path(pdf)
    pages_dir = Path(out_dir) / pdf_path.stem / "pages"
    meta = render_pdf(str(pdf_path), str(pages_dir), dpi)
    click.echo(f"渲染完成：{meta['total_pages']} 页 → {pages_dir}")


@cli.command()
@click.option("--pdf", required=True, type=click.Path(exists=True))
@click.option("--out-dir", default="./pdf_extract_output")
@click.option("--api-key", default=None)
def analyze(pdf, out_dir, api_key):
    """仅分析书籍结构（不提取）"""
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key
    from pdf_extractor.renderer import render_pdf
    from analyzer import analyze_book
    pdf_path = Path(pdf)
    base = Path(out_dir) / pdf_path.stem
    pages_dir = base / "pages"
    render_pdf(str(pdf_path), str(pages_dir), 150)
    profile = analyze_book(str(pages_dir / "render_meta.json"))
    click.echo(json.dumps(profile, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
