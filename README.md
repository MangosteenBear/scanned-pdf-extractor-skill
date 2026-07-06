# Scanned PDF Extractor

Extract structured content from scanned or image-based PDF books using Claude's vision — no copy-paste, no OCR setup, no manual work.

Point it at any scanned PDF, give it a 2-line example of what you want, and it handles the rest.

[English](#scanned-pdf-extractor) · [中文说明](#中文说明)

---

## 中文说明

用 Claude 视觉模型从扫描版 PDF 书籍中提取结构化内容。无需复制粘贴，无需配置 OCR，给它一个 2 行示例，剩下的它来搞定。

### 解决什么问题

很多经典教材和参考书只有扫描版 PDF —— 把纸质书逐页拍照或复印成图片文件。这类文件无法复制文字，通用 OCR 工具又容易把数学公式识别乱、丢失结构。

```
普通复制粘贴：
  ░░░░░░░░░░░░░░░░░░░  ← 全是图片，没有可选中的文字

本工具：
  Q: 什么是 Black-Scholes 公式？          ✓ 干净的 Markdown 文本
  A: C = S·N(d₁) - K·e^{-rT}·N(d₂)，其中...  ✓ LaTeX 公式完整保留
```

### 与其他方案对比

| | 传统 OCR<br>（Tesseract / PaddleOCR） | 直接把 PDF 扔给模型 | **本工具** |
|---|---|---|---|
| **数学公式** | ❌ 识别成乱码或跳过 | ⚠️ 能读，但不保证 LaTeX 格式 | ✅ 输出标准 LaTeX |
| **双列排版** | ❌ 左右列内容混排 | ⚠️ 看模型上下文窗口大小 | ✅ 先分析排版再提取 |
| **结构化输出** | ❌ 纯文本，无结构 | ⚠️ 需要手动写 prompt | ✅ 自动生成 JSON，含题号/置信度/页码 |
| **跨页内容** | ❌ 按页切断，无法合并 | ❌ 超长书籍超出上下文限制 | ✅ 滑动窗口 + 去重合并 |
| **长书支持** | ✅ 无限制 | ❌ 受模型上下文窗口限制（通常 200 页以内） | ✅ 无页数限制，按窗口分批处理 |
| **需要配置** | ❌ 需安装 OCR 引擎、训练模型 | ⚠️ 需要自己写 prompt、处理输出 | ✅ 只需提供 2 行示例 |
| **适合的书** | 纯文字书（无公式）| 短文档（< 50 页）| 任意长度扫描版书籍 |

**传统 OCR 的核心问题：** 只负责"把图片变成文字"，不理解语义——它不知道哪里是题目、哪里是答案、哪里是页眉页脚。输出是一堆乱序的文本块，还需要大量后处理才能用。

**直接扔给模型的核心问题：** 上下文窗口有限。一本 200 页的书，图片 token 加起来轻松超过 100K，大多数模型处理不了，即使能处理也贵得多。而且模型没有针对这本书的结构知识，容易漏题或格式不一致。

### 工作原理

```
┌─────────────────────────────────────────────────────────────────┐
│                         扫描版 PDF                               │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │   渲染页面   │  PDF → 逐页图片（PNG）
                    └──────┬──────┘
                           │
           ┌───────────────▼───────────────┐
           │      第一阶段 · 结构分析        │  抽样约 9 页（首/中/尾）
           │                               │  → 识别版面、问答格式、
           │  单列还是双列？                │    公式密度、语言
           │  题目怎么标记的？              │
           │  公式多不多？                  │  费用约 $0.05
           └───────────────┬───────────────┘
                           │
                    生成针对本书的提取 Prompt
                    （比通用 Prompt 短约 67%）
                           │
           ┌───────────────▼───────────────┐
           │      第二阶段 · 内容提取        │  滑动窗口：每次 5 页
           │                               │  相邻窗口重叠 1 页
           │  ┌────┐┌────┐┌────┐┌────┐    │  确保跨页内容不丢失
           │  │p1  ││p2  ││p3  ││p4  │    │
           │  └────┘└────┘└────┘└────┘    │  每个窗口 → 结构化 JSON
           │       ┌────┐┌────┐┌────┐┌────┐│
           │       │p2  ││p3  ││p4  ││p5  ││
           │       └────┘└────┘└────┘└────┘│
           └───────────────┬───────────────┘
                           │
                    ┌──────▼──────┐
                    │  去重合并    │  合并重叠窗口的重复内容
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │extracted.json│  干净的结构化输出
                    └─────────────┘
```

### 输出格式

`extracted.json` 中每条内容如下：

```json
{
  "marker": "Question 3",
  "stem_markdown": "风险与不确定性有什么区别？",
  "stem_latex": "",
  "answer_markdown": "风险指概率已知的情形（如掷骰子）；不确定性指概率本身未知的情形——这是 Knight（1921）的经典区分。",
  "page_start": 12,
  "page_end": 12,
  "confidence": 0.95,
  "needs_review": false,
  "notes": ""
}
```

| 字段 | 说明 |
|------|------|
| `stem_markdown` | 题目或正文内容（Markdown 格式） |
| `stem_latex` | 题干中的数学公式（LaTeX，无公式则为空） |
| `answer_markdown` | 答案或解析 |
| `marker` | 原书标记，如 `"Q3"`、`"第5题"`、`"Problem 2.3"` |
| `confidence` | 模型置信度 0–1 |
| `needs_review` | 文字不清或答案被截断时为 `true` |
| `notes` | 需要人工关注时的简短说明 |

### MCP 工具说明

```
┌─────────────────────────────────────────────────────────────┐
│                        三个 MCP 工具                         │
│                                                             │
│  analyze_pdf          extract_pages_only      extract_pdf   │
│  ─────────────        ──────────────────      ───────────── │
│  抽样约 9 页           提取指定页码范围         提取整本书    │
│  → 输出书籍结构        → 快速验证示例            → 生产使用   │
│                                                             │
│  先用这个了解          用这个验证示例格式         确认没问题   │
│  书的排版结构          再决定要不要跑全书          后再用这个  │
│                                                             │
│  费用：约 $0.05        费用：按页数比例            见下方表格  │
└─────────────────────────────────────────────────────────────┘
```

**推荐工作流：**

```
第 1 步：analyze_pdf        → 了解书的结构
第 2 步：extract_pages_only → 测试前 20 页，验证示例是否正确
第 3 步：extract_pdf        → 跑全书
```

### 安装

**1. 克隆仓库**

```bash
git clone https://github.com/MangosteenBear/scanned-pdf-extractor-skill.git
cd scanned-pdf-extractor-skill
```

**2. 安装依赖**

```bash
pip install -r requirements.txt
```

**3. 注册为 MCP Server**

在 Claude Code 的配置文件 `~/.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "pdf-extractor": {
      "command": "python",
      "args": ["/你的路径/scanned-pdf-extractor-skill/server.py"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

将 `/你的路径/` 替换为你实际克隆的目录路径。

**4. （可选）注册 Skill 文件**

```bash
cp SKILL.md ~/.claude/skills/pdf-extract.md
```

注册后可以直接对 Claude 说"帮我提取这本 PDF"来触发工具，无需手动调用。

### 使用方式

**通过 Claude Code（推荐）**

MCP Server 注册后，直接告诉 Claude 你想做什么：

> *"分析一下这本书的结构：`/path/to/mybook.pdf`"*

> *"从这本书里提取所有问答题：`/path/to/mybook.pdf`。示例格式：*
> *Q: 什么是 delta？*
> *A: Delta 衡量期权价格对标的资产价格的敏感度……"*

> *"先测试前 20 页，确认没问题再跑全书"*

Claude 会直接调用工具，你不需要输入任何命令。

**通过命令行**

```bash
# 仅分析书籍结构
python -m pdf_extractor analyze --pdf /path/to/book.pdf

# 先测试小范围
python -m pdf_extractor run \
  --pdf /path/to/book.pdf \
  --example "Q: ...\nA: ..." \
  --pages 1-20

# 提取全书
python -m pdf_extractor run \
  --pdf /path/to/book.pdf \
  --example "Q: ...\nA: ..."

# 使用 Batch API（省 50% 费用，等待约 10 分钟）
python -m pdf_extractor run \
  --pdf /path/to/book.pdf \
  --example "Q: ...\nA: ..." \
  --batch
```

### 如何写一个好的示例

示例告诉模型你想要什么格式。**2–3 行就够了**，不需要面面俱到。

**英文问答书：**
```
Q: What is Brownian motion?
A: Brownian motion is a continuous-time stochastic process with independent, normally distributed increments.
```

**中文教材：**
```
题目：什么是套利定价理论（APT）？
答案：APT 由 Ross 于 1976 年提出，认为资产超额收益由多个系统性风险因子的线性组合决定。
```

**带编号的习题册：**
```
Problem 2.3: A stock follows GBM with μ = 0.05 and σ = 0.2. Find the probability it doubles within 1 year.
Solution: Using the log-normal distribution, P(S_T > 2S_0) = N(...)
```

模型会自适应你展示的任何格式，示例只是提示，不是严格模板。

### 费用参考

使用默认模型 `claude-sonnet-4-6`：

| 书籍页数 | 标准模式 | 使用 `--batch` |
|---------|---------|---------------|
| ~100 页 | ~$1.50  | ~$0.75        |
| ~200 页 | ~$3.00  | ~$1.50        |
| ~300 页 | ~$5.00  | ~$2.50        |

### 输出文件

所有文件保存在 `./pdf_extract_output/<书名>/`：

```
pdf_extract_output/
└── my-book/
    ├── extracted.json       ← 最终结果（用这个）
    ├── extract_raw.jsonl    ← 每个窗口的原始输出（调试用）
    ├── book_profile.json    ← 识别出的书籍结构
    ├── system_prompt.txt    ← 为这本书生成的提取 Prompt
    └── pages/
        ├── page_0001.png
        ├── page_0002.png
        └── ...
```

### 常见问题

**提取不到任何内容**
先用 `--pages 1-20` 测试小范围。如果还是空，说明示例格式和书的实际格式不匹配，先运行 `analyze_pdf` 看看书的结构再调整示例。

**置信度很低（`confidence < 0.7`）**
扫描质量可能较差，试试 `--dpi 300` 提高渲染分辨率。

**答案被截断了**
对于很长的答案（跨 3 页以上）会有此情况，这些条目会被标记为 `needs_review: true`。滑动窗口设计已经能捕获大多数跨页内容，但极长答案可能仍不完整。

**数学公式显示不对**
查看 `stem_latex` 字段——LaTeX 原始内容在那里，即使 `stem_markdown` 显示的是简化版。把 LaTeX 传入 KaTeX 或 MathJax 渲染器即可正确显示。

---

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

## Why Not Just Use OCR or Drop the PDF into a Chat?

| | Traditional OCR<br>(Tesseract / PaddleOCR) | Dropping PDF into a chat | **This tool** |
|---|---|---|---|
| **Math formulas** | ❌ Garbled or skipped | ⚠️ Readable but no LaTeX output | ✅ Outputs standard LaTeX |
| **Double-column layout** | ❌ Left and right columns get mixed | ⚠️ Depends on context window size | ✅ Detects layout before extracting |
| **Structured output** | ❌ Plain text dump, no structure | ⚠️ Requires manual prompt engineering | ✅ Auto-generates JSON with markers, confidence, page numbers |
| **Cross-page content** | ❌ Cuts at page boundaries | ❌ Long books exceed context limits | ✅ Sliding window + deduplication |
| **Long books** | ✅ No limit | ❌ Limited by model context window (typically < 200 pages) | ✅ No page limit, processed in batches |
| **Setup required** | ❌ Install OCR engine, train on domain | ⚠️ Write prompts, parse output manually | ✅ Just provide a 2-line example |
| **Best for** | Plain-text books (no formulas) | Short documents (< 50 pages) | Any length scanned book |

**The core problem with traditional OCR:** It only converts images to text — it doesn't understand meaning. It doesn't know what's a question, what's an answer, what's a page header. You get a jumbled text dump that still needs heavy post-processing.

**The core problem with dropping PDFs into a chat:** Context windows are finite. A 200-page book easily exceeds 100K image tokens — most models can't handle it, and even if they can, it's far more expensive. The model also has no prior knowledge of the book's structure, leading to missed items and inconsistent formatting.

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
