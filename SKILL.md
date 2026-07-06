---
name: pdf-extract
description: Extract structured content from scanned or image-based PDF books. Use when the user wants to extract Q&A, problems, or any content from a scanned/image PDF, or says "/pdf-extract". Guides the user through providing a PDF path and an example of what to extract, then runs the two-phase extraction pipeline.
version: 0.1.0
metadata:
  author: MangosteenBear
  homepage: https://github.com/MangosteenBear/scanned-pdf-extractor-skill
  category: productivity
---

# PDF Vision Extractor

从扫描版 PDF 中提取结构化内容。

## 适用场景

用户说以下任意一种时调用：
- `/pdf-extract`
- "帮我提取这本 PDF"
- "从这本书里提取题目/问答/内容"
- 提到 PDF + 提取/抽取/识别

## 运行步骤

**Step 1 — 收集必要信息**

如果用户没有提供，逐一询问：
1. PDF 文件路径
2. 提取示例（2-3 行，展示期望的输入→输出格式）
3. API Key（检查 `ANTHROPIC_API_KEY` 环境变量是否已设置；未设置则询问）

**Step 2 — 检查依赖**

```bash
python3 -c "import anthropic, fitz, PIL, click; print('OK')" 2>&1
```

如果失败，提示用户：
```bash
pip install anthropic pymupdf pillow click
```

**Step 3 — 检查 pdf_extractor 是否可用**

```bash
python3 -c "import pdf_extractor; print(pdf_extractor.__version__)" 2>&1
```

如果失败，提示用户：
```bash
git clone https://github.com/MangosteenBear/scanned-pdf-extractor-skill.git
cd scanned-pdf-extractor-skill
pip install -r requirements.txt
```
然后让用户在 `scanned-pdf-extractor-skill` 目录下运行后续命令。

**Step 4 — 运行提取**

```bash
python3 -m pdf_extractor run \
  --pdf "<PDF路径>" \
  --example "<用户提供的示例>"
```

实时显示进度（每个窗口完成后输出题数和累计费用）。

**Step 5 — 告知结果**

提取完成后告诉用户：
- 提取了多少条内容
- 有多少条需要人工复核（`needs_review: true`）
- 估算费用
- 结果文件位置（`./pdf_extract_output/<书名>/extracted.json`）

## 可选参数

| 参数 | 说明 |
|------|------|
| `--pages 1-50` | 只处理部分页（调试时用） |
| `--batch` | Batch API，省 50% 费用，速度稍慢 |
| `--dpi 300` | 提高渲染分辨率（扫描质量差时用） |
| `--skip-analyze` | 跳过书籍结构分析，直接用通用 prompt |

## 提取示例参考

引导用户写 2-3 行即可，例如：

```
Q: What is delta hedging?
A: Delta hedging involves continuously rebalancing a portfolio to maintain a delta-neutral position...
```
