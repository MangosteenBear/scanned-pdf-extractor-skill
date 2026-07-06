"""PDF Extractor MCP Server

Exposes three tools to Claude:
  - analyze_pdf   : sample pages and return book structure profile
  - extract_pdf   : full pipeline (render → analyze → extract → merge)
  - extract_pages : extract a page range only (for testing)

Start with:
  python -m pdf_extractor.server

Or add to Claude Code settings:
  {
    "mcpServers": {
      "pdf-extractor": {
        "command": "python",
        "args": ["-m", "pdf_extractor.server"],
        "env": { "ANTHROPIC_API_KEY": "sk-ant-..." }
      }
    }
  }
"""
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "pdf-extractor",
    instructions=(
        "Tools for extracting structured content from scanned PDF books. "
        "Always start with analyze_pdf to understand the book structure, "
        "then call extract_pdf with an example showing the desired output format."
    ),
)


def _require_api_key():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. "
            "Pass it via environment variable or use --api-key."
        )


@mcp.tool()
def analyze_pdf(pdf_path: str) -> str:
    """
    Analyze the structure of a scanned PDF book.

    Samples ~9 pages from the beginning, middle, and end of the book,
    then returns a profile describing the layout, language, Q&A format,
    math density, and other structural characteristics.

    Use this before extract_pdf to understand what you're working with.
    Cost: ~$0.05.

    Args:
        pdf_path: Absolute path to the PDF file.

    Returns:
        JSON string with book profile fields:
        layout, language, qa_marker_style, math_density,
        has_chapter_structure, typical_qa_length, content_notes.
    """
    _require_api_key()
    pdf_path = str(Path(pdf_path).expanduser().resolve())
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    from renderer import render_pdf
    from analyzer import analyze_book
    from config import ExtractorConfig

    cfg = ExtractorConfig()
    with tempfile.TemporaryDirectory() as tmpdir:
        pages_dir = Path(tmpdir) / "pages"
        render_pdf(pdf_path, str(pages_dir), dpi=150)
        profile = analyze_book(str(pages_dir / "render_meta.json"), cfg)

    return json.dumps(profile, ensure_ascii=False, indent=2)


@mcp.tool()
def extract_pdf(
    pdf_path: str,
    example: str,
    output_dir: str = "",
    pages: str = "",
    use_batch: bool = False,
) -> str:
    """
    Extract structured content from a scanned PDF book.

    Runs the full pipeline:
    1. Renders PDF pages as images
    2. Analyzes book structure (samples ~9 pages)
    3. Generates a book-specific extraction prompt
    4. Extracts content using sliding windows
    5. Deduplicates results across overlapping windows

    Args:
        pdf_path:   Absolute path to the PDF file.
        example:    2-3 lines showing the desired extraction format.
                    Example: "Q: What is delta?\\nA: Delta measures..."
        output_dir: Where to save results. Defaults to ./pdf_extract_output/<book-name>/
        pages:      Optional page range, e.g. "1-50" or "1-20,40-60".
                    Leave empty to process the whole book.
        use_batch:  Use Anthropic Batch API for 50% cost savings (slower).

    Returns:
        Summary with item count, cost estimate, needs_review count,
        and path to the extracted.json results file.
    """
    _require_api_key()
    pdf_path = str(Path(pdf_path).expanduser().resolve())
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    from renderer import render_pdf
    from analyzer import analyze_book
    from prompt_builder import build_extraction_prompt
    from extractor import extract_pages
    from merger import merge_windows
    from config import ExtractorConfig

    cfg = ExtractorConfig()
    cfg.use_batch = use_batch

    pdf = Path(pdf_path)
    base = Path(output_dir) / pdf.stem if output_dir else Path("./pdf_extract_output") / pdf.stem
    pages_dir = base / "pages"
    base.mkdir(parents=True, exist_ok=True)

    # Parse page range
    page_range = None
    if pages:
        page_range = set()
        for part in pages.split(","):
            part = part.strip()
            if "-" in part:
                a, b = part.split("-", 1)
                page_range.update(range(int(a), int(b) + 1))
            elif part:
                page_range.add(int(part))

    # 1. Render
    meta = render_pdf(pdf_path, str(pages_dir), cfg.extract_dpi)
    total_pages = meta["total_pages"]

    # 2. Analyze
    profile = analyze_book(str(pages_dir / "render_meta.json"), cfg)

    # 3. Build prompt
    system_prompt = build_extraction_prompt(profile, example)
    (base / "system_prompt.txt").write_text(system_prompt, encoding="utf-8")

    # 4. Extract
    progress_log = []

    def on_progress(cur, total, n_items, cost):
        progress_log.append(f"Window {cur}/{total}: {n_items} items, ${cost:.3f} so far")

    ex = extract_pages(
        str(pages_dir / "render_meta.json"),
        str(base),
        system_prompt,
        cfg,
        page_range,
        on_progress=on_progress,
    )

    # 5. Merge
    out_path = base / "extracted.json"
    merged = merge_windows(str(base / "extract_raw.jsonl"), str(out_path))

    # Save profile
    (base / "book_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    n_review = sum(1 for i in merged if i.get("needs_review"))
    n_answered = sum(1 for i in merged if i.get("answer_markdown"))

    summary = {
        "status": "success",
        "total_pages": total_pages,
        "items_extracted": len(merged),
        "items_with_answer": n_answered,
        "items_needs_review": n_review,
        "estimated_cost_usd": round(ex["total_cost"], 3),
        "output_file": str(out_path),
        "book_profile": profile,
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


@mcp.tool()
def extract_pages_only(
    pdf_path: str,
    example: str,
    pages: str,
    output_dir: str = "",
) -> str:
    """
    Extract content from specific pages only (useful for testing before running the full book).

    Same as extract_pdf but requires a page range. Use this to verify your
    extraction example works correctly before committing to the full book cost.

    Args:
        pdf_path:   Absolute path to the PDF file.
        example:    2-3 lines showing the desired extraction format.
        pages:      Page range to process, e.g. "1-20" or "5-10,20-25".
        output_dir: Where to save results (optional).

    Returns:
        Same summary format as extract_pdf.
    """
    if not pages:
        raise ValueError("pages is required for extract_pages_only. Example: '1-20'")
    return extract_pdf(pdf_path, example, output_dir, pages)


if __name__ == "__main__":
    mcp.run(transport="stdio")
