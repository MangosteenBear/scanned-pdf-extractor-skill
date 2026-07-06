# Scanned PDF Extractor

Extract structured content from scanned or image-based PDF books using Claude's vision — no copy-paste, no OCR setup, no manual work.

Point it at any scanned PDF, give it a 2-line example of what you want, and it handles the rest.

---

## The Problem It Solves

Most classic textbooks and reference materials exist only as scanned PDFs — pages photographed or photocopied into images. Normal copy-paste returns nothing, and generic OCR tools mangle math formulas and lose structure.

```
Normal copy-paste from a scanned PDF:
  ░░░░░░░░░░░░░░░░░░░  ← just images, no selectable text

This tool:
  Q: What is the Black-Scholes formula?        ✓ clean markdown
  A: C = S·N(d₁) - K·e^{-rT}·N(d₂) where...  ✓ LaTeX preserved
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                         Your scanned PDF                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │   Render    │  PDF → page images (PNG)
                    └──────┬──────┘
                           │
           ┌───────────────▼───────────────┐
           │      Phase 1 · Analyze        │  Sample ~9 pages
           │                               │  → detect layout, Q&A format,
           │  single/double column?        │    math density, language
           │  how are Q&A marked?          │
           │  math-heavy or text-only?     │  Cost: ~$0.05
           └───────────────┬───────────────┘
                           │
                           │  book-specific prompt generated
                           │  (67% shorter than a generic one)
                           │
           ┌───────────────▼───────────────┐
           │      Phase 2 · Extract        │  Sliding window: 5 pages at a time
           │                               │  with 1-page overlap to catch
           │  ┌────┐┌────┐┌────┐┌────┐    │  content that spans page breaks
           │  │p1  ││p2  ││p3  ││p4  │    │
           │  └────┘└────┘└────┘└────┘    │  Each window → structured JSON
           │       ┌────┐┌────┐┌────┐┌────┐│
           │       │p2  ││p3  ││p4  ││p5  ││
           │       └────┘└────┘└────┘└────┘│
           └───────────────┬───────────────┘
                           │
                    ┌──────▼──────┐
                    │   Dedupe    │  Merge overlapping windows
                    │   & Merge   │  Remove duplicates
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │extracted.json│  Clean, structured output
                    └─────────────┘
```

---

## What You Get

Each extracted item in `extracted.json` looks like this:

```json
{
  "marker": "Question 3",
  "stem_markdown": "What is the difference between risk and uncertainty?",
  "stem_latex": "",
  "answer_markdown": "Risk refers to situations where probabilities are known (e.g. rolling a die). Uncertainty refers to situations where probabilities themselves are unknown — Knight's distinction (1921).",
  "page_start": 12,
  "page_end": 12,
  "confidence": 0.95,
  "needs_review": false,
  "notes": ""
}
```

| Field | Description |
|-------|-------------|
| `stem_markdown` | The question or main content, in Markdown |
| `stem_latex` | Math formulas in LaTeX (empty string if none) |
| `answer_markdown` | The answer or explanation |
| `marker` | Original label: `"Q3"`, `"Problem 5"`, `"例2"` |
| `confidence` | Model confidence score 0–1 |
| `needs_review` | `true` if text was unclear or answer was cut off |
| `notes` | Short note if something needs human attention |

---

## MCP Tools

Once installed, Claude has access to three tools:

```
┌─────────────────────────────────────────────────────────────┐
│                      MCP Tools                              │
│                                                             │
│  analyze_pdf          extract_pages_only      extract_pdf   │
│  ─────────────        ──────────────────      ───────────── │
│  Sample ~9 pages      Extract a page range    Full book     │
│  → book profile       → quick test            → everything  │
│                                                             │
│  Use first to         Use to verify your      Use when      │
│  understand the       example works before    ready for     │
│  book structure       spending on full book   production    │
│                                                             │
│  Cost: ~$0.05         Cost: proportional      Cost: see     │
│                       to pages tested         table below   │
└─────────────────────────────────────────────────────────────┘
```

**Recommended workflow:**

```
1. analyze_pdf        → understand book structure
2. extract_pages_only → test on pages 1-20
3. extract_pdf        → run the full book
```

---

## Requirements

- [Claude Code](https://claude.ai/code) installed
- An [Anthropic API key](https://console.anthropic.com/)
- Python 3.10+

---

## Setup

**1. Clone this repo**

```bash
git clone https://github.com/MangosteenBear/scanned-pdf-extractor-skill.git
cd scanned-pdf-extractor-skill
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Register as an MCP server**

Add this to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "pdf-extractor": {
      "command": "python",
      "args": ["/absolute/path/to/scanned-pdf-extractor-skill/server.py"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

Replace `/absolute/path/to/` with where you cloned the repo. For example:
- Mac/Linux: `"/Users/yourname/scanned-pdf-extractor-skill/server.py"`
- Windows: `"C:\\Users\\yourname\\scanned-pdf-extractor-skill\\server.py"`

**4. (Optional) Register the skill file for natural language triggers**

```bash
cp SKILL.md ~/.claude/skills/pdf-extract.md
```

This lets you trigger the tool by just saying "extract this PDF" instead of calling tools explicitly.

---

## Usage

### Via Claude Code (recommended)

Once the MCP server is registered, just tell Claude what you want:

> *"Analyze the structure of `/path/to/mybook.pdf`"*

> *"Extract all Q&A from `/path/to/mybook.pdf`. Here's an example:*
> *Q: What is delta?*
> *A: Delta measures the sensitivity of an option's price to the underlying asset price."*

> *"First test the extraction on pages 1–20 before running the full book"*

Claude calls the tools directly — you never need to run any commands.

### Via command line

```bash
# Analyze book structure only
python -m pdf_extractor analyze --pdf /path/to/book.pdf

# Test on a small page range first
python -m pdf_extractor run \
  --pdf /path/to/book.pdf \
  --example "Q: ...\nA: ..." \
  --pages 1-20

# Full extraction
python -m pdf_extractor run \
  --pdf /path/to/book.pdf \
  --example "Q: ...\nA: ..."

# Full extraction with Batch API (50% cheaper, ~10 min wait)
python -m pdf_extractor run \
  --pdf /path/to/book.pdf \
  --example "Q: ...\nA: ..." \
  --batch
```

---

## Writing a Good Example

The example shows the model what format you want. **2–3 lines is enough** — it doesn't need to be comprehensive.

**Q&A book (English):**
```
Q: What is Brownian motion?
A: Brownian motion is a continuous-time stochastic process with independent, normally distributed increments. It is the basis for modeling stock price dynamics in Black-Scholes.
```

**Textbook (Chinese):**
```
题目：什么是套利定价理论（APT）？
答案：APT 由 Ross 于 1976 年提出，认为资产超额收益由多个系统性风险因子的线性组合决定，是 CAPM 的多因子推广。
```

**Problem set with numbered problems:**
```
Problem 2.3: A stock follows GBM with μ = 0.05 and σ = 0.2. Find the probability it doubles within 1 year.
Solution: Using the log-normal distribution, P(S_T > 2S_0) = N(...)
```

The model adapts to whatever structure you show it — the example is just a hint, not a template it rigidly follows.

---

## Cost Reference

Estimates using `claude-sonnet-4-6` (default model):

| Book length | Standard | With `--batch` |
|-------------|----------|----------------|
| ~100 pages  | ~$1.50   | ~$0.75         |
| ~200 pages  | ~$3.00   | ~$1.50         |
| ~300 pages  | ~$5.00   | ~$2.50         |

`--batch` uses Anthropic's Batch API (asynchronous) — same quality, half the price, results in ~10 minutes.

---

## Output Files

All saved to `./pdf_extract_output/<book-name>/`:

```
pdf_extract_output/
└── my-book/
    ├── extracted.json       ← final results (use this)
    ├── extract_raw.jsonl    ← raw per-window output (for debugging)
    ├── book_profile.json    ← detected book structure
    ├── system_prompt.txt    ← the generated extraction prompt
    └── pages/
        ├── page_0001.png
        ├── page_0002.png
        └── ...
```

---

## Troubleshooting

**No items extracted**
Test on a small range first: `--pages 1-20`. If nothing comes back, your example may not match the book's actual format. Try `analyze_pdf` first to see how the book is structured.

**Low confidence scores (`confidence < 0.7`)**
The scan quality may be poor. Try `--dpi 300` for higher resolution rendering.

**Answers cut off mid-sentence**
Normal for very long answers that span multiple pages. These items are flagged with `needs_review: true`. The overlapping window design catches most cross-page content, but very long answers (3+ pages) may still be incomplete.

**Math formulas look wrong**
Check `stem_latex` — the LaTeX is there even if `stem_markdown` shows a simplified version. Pass the LaTeX field to a renderer like KaTeX or MathJax for correct display.
