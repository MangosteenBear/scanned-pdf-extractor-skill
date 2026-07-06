# Scanned PDF Extractor Skill

A Claude Code skill that extracts structured content from scanned or image-based PDF books using AI vision.

Point it at any scanned PDF, give it one example of what you want to extract, and it figures out the rest.

---

## What It Does

Many textbooks and reference materials exist only as scanned PDFs — pages photographed or photocopied into image files. Normal copy-paste doesn't work on these.

This skill:
1. **Analyzes** the book's layout (single/double column, math density, how Q&A are formatted)
2. **Generates** a tailored extraction prompt based on that analysis — instead of a generic one-size-fits-all approach
3. **Extracts** all content page by page using Claude's vision model
4. **Deduplicates** results across overlapping page windows

The two-phase design means the AI understands *this specific book's structure* before extracting, which improves accuracy and reduces token usage by ~67% compared to a generic prompt.

---

## What You Get

A `extracted.json` file where each item looks like:

```json
{
  "marker": "Question 3",
  "stem_markdown": "What is the difference between risk and uncertainty?",
  "stem_latex": "",
  "answer_markdown": "Risk refers to situations where probabilities are known (e.g. rolling a die). Uncertainty refers to situations where probabilities themselves are unknown (Knight's distinction, 1921).",
  "page_start": 12,
  "page_end": 12,
  "confidence": 0.95,
  "needs_review": false,
  "notes": ""
}
```

Fields:
- `stem_markdown` — the question or main content
- `stem_latex` — math formulas in LaTeX (empty if none)
- `answer_markdown` — the answer or explanation
- `marker` — original label like "Q3", "Problem 5", "例2"
- `confidence` — how confident the model is (0–1)
- `needs_review` — flagged if the text was unclear or cut off across pages

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

**3. Copy the skill file to Claude Code**

```bash
cp skill.md ~/.claude/skills/pdf-extract.md
```

**4. Set your API key**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Or pass it directly with `--api-key` each time.

---

## Usage

### Option A: Use it through Claude Code (recommended)

Open Claude Code and just say:

> "Help me extract content from this PDF: `/path/to/mybook.pdf`"

Claude will ask for your extraction example and handle the rest.

### Option B: Run it directly from the command line

```bash
python -m pdf_extractor run \
  --pdf /path/to/mybook.pdf \
  --example "Q: What is delta hedging?\nA: Delta hedging involves..."
```

With more options:

```bash
python -m pdf_extractor run \
  --pdf /path/to/mybook.pdf \
  --example-file my_example.txt \   # put your example in a text file instead
  --pages 1-50 \                    # only process certain pages (useful for testing)
  --batch \                         # use Batch API for 50% cost savings (slower)
  --out-dir ./my_output             # where to save results
```

---

## Writing a Good Example

The example tells the model what format you want. You only need 2–3 lines — it doesn't need to be long.

**For a Q&A book:**
```
Q: What is Brownian motion?
A: Brownian motion is a continuous-time stochastic process where increments are independent and normally distributed.
```

**For a Chinese textbook:**
```
题目：什么是套利定价理论？
答案：APT 由 Ross 于 1976 年提出，认为资产收益由多个系统性风险因子线性决定。
```

**For a problem set:**
```
Problem 2.3: A stock follows GBM with drift μ = 0.05 and volatility σ = 0.2. Find the probability that the stock price doubles within 1 year.
Solution: Using the log-normal distribution...
```

The model adapts to whatever format you show it.

---

## Cost Estimate

Costs depend on book length. These are rough estimates using `claude-sonnet-4-6`:

| Book length | Estimated cost |
|-------------|---------------|
| ~100 pages  | ~$1.50        |
| ~200 pages  | ~$3.00        |
| ~300 pages  | ~$5.00        |

Add `--batch` to cut costs by 50% (results take a few minutes longer).

---

## Output Files

All files are saved to `./pdf_extract_output/<book-name>/`:

| File | Contents |
|------|----------|
| `extracted.json` | Final extracted content (deduplicated) |
| `extract_raw.jsonl` | Raw per-window results (for debugging) |
| `book_profile.json` | Detected book structure (layout, math density, etc.) |
| `system_prompt.txt` | The generated extraction prompt for this book |
| `pages/` | Rendered page images |

---

## Troubleshooting

**"No items extracted"** — Try testing with `--pages 1-20` first to check the example is working. The model may need a better example if the book format is unusual.

**Low confidence scores** — The scan quality may be poor. Try increasing DPI: `--dpi 300`.

**Content cut off mid-answer** — Normal for very long answers. Items flagged with `needs_review: true` are ones the model detected as potentially incomplete.
