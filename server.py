"""PDF Extractor MCP Server

Exposes three tools to Claude:
  - analyze_pdf        : sample pages, return book structure profile
  - extract_pdf        : full pipeline (render → analyze → extract → merge)
  - extract_pages_only : extract a page range only (for testing)

Start:
  python server.py

Configure in Claude Code (~/.claude/settings.json):
  {
    "mcpServers": {
      "pdf-extractor": {
        "command": "python",
        "args": ["/path/to/scanned-pdf-extractor-skill/server.py"],
        "env": {
          "ANTHROPIC_API_KEY": "sk-ant-...",
          "PDF_EXTRACTOR_PROVIDER": "anthropic"
        }
      }
    }
  }

To use OpenAI or Google instead:
  "env": { "OPENAI_API_KEY": "sk-...", "PDF_EXTRACTOR_PROVIDER": "openai" }
  "env": { "GOOGLE_API_KEY": "...",    "PDF_EXTRACTOR_PROVIDER": "google"  }
"""
import json
import os
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "pdf-extractor",
    instructions=(
        "Tools for extracting structured content from scanned PDF books. "
        "Recommended workflow: analyze_pdf first → extract_pages_only to test → extract_pdf for the full book."
    ),
)


def _make_config():
    from config import ExtractorConfig, API_KEY_ENV
    cfg = ExtractorConfig()
    provider = os.environ.get("PDF_EXTRACTOR_PROVIDER", "anthropic").lower()
    cfg.provider = provider
    env = API_KEY_ENV.get(provider, "ANTHROPIC_API_KEY")
    if not os.environ.get(env):
        raise ValueError(
            f"API key not found. Set the {env} environment variable "
            f"(or set PDF_EXTRACTOR_PROVIDER to match your key)."
        )
    return cfg


@mcp.tool()
def analyze_pdf(pdf_path: str) -> str:
    """
    Analyze the structure of a scanned PDF book.

    Samples ~9 pages from beginning, middle, and end, then returns a profile
    describing layout, language, Q&A format, math density, and other structural
    characteristics. Use this before extract_pdf to understand the book.

    Cost: ~$0.05.

    Args:
        pdf_path: Absolute path to the PDF file.

    Returns:
        JSON with: layout, language, qa_marker_style, math_density,
        has_chapter_structure, typical_qa_length, content_notes.
    """
    cfg = _make_config()
    pdf_path = str(Path(pdf_path).expanduser().resolve())
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    from renderer import render_pdf
    from analyzer import analyze_book

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
    Extract structured content from a scanned PDF book (full pipeline).

    Runs: render → analyze structure → generate prompt → extract → deduplicate.

    Args:
        pdf_path:   Absolute path to the PDF file.
        example:    2-3 lines showing the desired output format.
                    e.g. "Q: What is delta?\\nA: Delta measures sensitivity..."
        output_dir: Where to save results (default: ./pdf_extract_output/<name>/).
        pages:      Optional page range, e.g. "1-50" or "1-20,40-60".
        use_batch:  Use Batch API for 50% cost savings — Anthropic only, slower.

    Returns:
        JSON summary: item count, cost, needs_review count, output file path.
    """
    cfg = _make_config()
    cfg.use_batch = use_batch

    pdf_path = str(Path(pdf_path).expanduser().resolve())
    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    from renderer import render_pdf
    from analyzer import analyze_book
    from prompt_builder import build_extraction_prompt
    from extractor import extract_pages
    from merger import merge_windows

    pdf = Path(pdf_path)
    base = Path(output_dir) / pdf.stem if output_dir else Path("./pdf_extract_output") / pdf.stem
    pages_dir = base / "pages"
    base.mkdir(parents=True, exist_ok=True)

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

    meta = render_pdf(pdf_path, str(pages_dir), cfg.extract_dpi)
    profile = analyze_book(str(pages_dir / "render_meta.json"), cfg)
    system_prompt = build_extraction_prompt(profile, example)
    (base / "system_prompt.txt").write_text(system_prompt, encoding="utf-8")

    ex = extract_pages(str(pages_dir / "render_meta.json"), str(base), system_prompt, cfg, page_range)

    out_path = base / "extracted.json"
    merged = merge_windows(str(base / "extract_raw.jsonl"), str(out_path))
    (base / "book_profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    return json.dumps({
        "status": "success",
        "total_pages": meta["total_pages"],
        "items_extracted": len(merged),
        "items_with_answer": sum(1 for i in merged if i.get("answer_markdown")),
        "items_needs_review": sum(1 for i in merged if i.get("needs_review")),
        "estimated_cost_usd": round(ex["total_cost"], 3),
        "output_file": str(out_path),
        "book_profile": profile,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
def extract_pages_only(pdf_path: str, example: str, pages: str, output_dir: str = "") -> str:
    """
    Extract content from specific pages only — use this to test before running the full book.

    Same as extract_pdf but requires a page range. Verify your example works on
    a small section before committing to the full book cost.

    Args:
        pdf_path:   Absolute path to the PDF file.
        example:    2-3 lines showing the desired output format.
        pages:      Required page range, e.g. "1-20" or "5-10,20-25".
        output_dir: Where to save results (optional).
    """
    if not pages:
        raise ValueError("pages is required. Example: '1-20'")
    return extract_pdf(pdf_path, example, output_dir, pages)


if __name__ == "__main__":
    mcp.run(transport="stdio")
