# Paper MD to Word / Markdown 论文转 Word

Convert academic or technical Markdown manuscripts into Word `.docx` files with editable Word equations.

将学术或技术类 Markdown 稿件转换为 Word `.docx` 文件，并保留可编辑的 Word 公式。

This repository contains a Codex skill and a reusable conversion script for manuscripts with Chinese text, Markdown tables, figures, inline formulas, display equations, equation numbers, and references.

本仓库包含一个 Codex skill 和一个可复用的转换脚本，适用于包含中文正文、Markdown 表格、图片、行内公式、块公式、公式编号和参考文献的稿件。

## Features / 功能特点

- Convert Markdown manuscripts to Word `.docx`.
- 将 Markdown 稿件转换为 Word `.docx`。
- Convert standard LaTeX math to editable Word equations through Pandoc, MathML, and Office OMML.
- 通过 Pandoc、MathML 和 Office OMML，将标准 LaTeX 数学公式转换为可编辑的 Word 公式。
- Keep display-equation numbers outside the formula object so they can be right-aligned and updated as Word fields.
- 将块公式编号放在公式对象外部，便于右对齐，并可作为 Word 域更新。
- Repair the common Word OMML issue where summation symbols show an empty square placeholder.
- 修复 Word OMML 中常见的求和符号后出现空方块占位的问题。
- Apply company-style paper formatting rules for title, author, abstract, keywords, headings, captions, tables, and references.
- 应用公司内部论文格式规则，包括标题、作者、摘要、关键词、章节标题、图题、表格和参考文献。
- Convert citation markers such as `[1]`, `[1-2]`, and `[5-8]` in body text to superscript runs.
- 将正文中的 `[1]`、`[1-2]`、`[5-8]` 等参考文献标识转换为上标。
- Convert reference entries to Word automatic numbering with bracket style, such as `[1]`.
- 将参考文献条目转换为 Word 自动编号，编号样式为 `[1]`。

## Repository Layout / 仓库结构

```text
paper-md-to-word/
  SKILL.md
  README.md
  agents/openai.yaml
  references/company-paper-format.md
  references/word-equation-repair.md
  scripts/md_to_word_equations.py
```

## Requirements / 环境依赖

Required / 必需环境:

- Python 3.10 or later / Python 3.10 或更高版本
- `python-docx`
- `lxml`
- Pandoc
- Microsoft Office `MML2OMML.XSL` / Microsoft Office 的 `MML2OMML.XSL`

Optional but recommended / 可选但推荐:

- Microsoft Word, for opening the output document and updating Word fields after manual edits.
- Microsoft Word，用于打开输出文档，并在手动修改后更新 Word 域。

Quick environment check / 快速检查环境:

```powershell
python -c "import docx, lxml; print('python packages ok')"
pandoc --version
Test-Path "C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"
```

## Usage / 使用方法

Basic conversion / 基本转换:

```powershell
python .\scripts\md_to_word_equations.py `
  --input D:\path\paper.md `
  --output D:\path\paper.docx
```

Optional metadata / 可选作者与单位信息:

```powershell
python .\scripts\md_to_word_equations.py `
  --input D:\path\paper.md `
  --output D:\path\paper.docx `
  --author-line "作者姓名" `
  --affiliation-line "（单位名称    邮编）"
```

## Markdown Conventions / Markdown 写法约定

Inline formulas / 行内公式:

```markdown
The apparent wind speed is $V_{\mathrm{rel}}$.
```

Display equations / 块公式:

```markdown
$$
E_{\mathrm{voyage}}=\sum_{i=1}^{N}P_{\mathrm{save},i}\Delta t_i \tag{1}
$$
```

Images / 图片: `![System interface](figures/interface.png)`

Tables / 表格: Markdown pipe tables are supported.

References / 参考文献:

```markdown
[1] Author. Paper title[J]. Journal, 2024.
[2] Author. Book title[M]. Publisher, 2023.
```

The script strips typed reference numbers and rewrites references as Word automatic numbering.

脚本会去掉手写的参考文献编号，并改用 Word 自动编号。

## Equation Handling / 公式处理

The script uses Pandoc for generic LaTeX math conversion. This supports most standard LaTeX math expressions, but it is not a full LaTeX engine.

脚本使用 Pandoc 处理通用 LaTeX 数学公式。它可以覆盖大多数标准 LaTeX 数学表达式，但并不是完整的 LaTeX 引擎。

Well supported / 通常支持较好: subscripts, superscripts, fractions, sums, integrals, Greek letters, `\mathrm{...}`, and `\tag{...}` numbering.

通常支持较好：上下标、分式、求和、积分、希腊字母、`\mathrm{...}` 和 `\tag{...}` 编号。

Possible limitations / 可能存在限制: custom macros, uncommon package commands, malformed syntax, and very complex aligned environments.

可能存在限制：自定义宏、特殊宏包命令、非标准数学写法以及复杂对齐环境。

For exceptional formulas, pass a JSON equation map.

对于特殊公式，可以传入外部 JSON 公式映射。

## Validation / 结果校验

After conversion, check the script output / 转换后检查脚本输出:

```text
omath_count=...
empty_nary_count=0
raw_dollar_count=0
```

Manual checks / 人工检查: editable equations, no empty square after `\sum`, right-aligned equation numbers, bracketed reference numbering, correct images and tables.

人工检查：公式可编辑，求和符号后没有空方块，公式编号右对齐，参考文献使用方括号自动编号，图片和表格位置正确。

## Notes / 注意事项

- If the target Word file is open, Word may lock it. Write to a new filename such as `_v2.docx`.
- 如果目标 Word 文件正在打开，可能会被 Word 锁定。此时请输出到新的文件名，例如 `_v2.docx`。
- Do not use formula screenshots for papers unless a visual-only document is explicitly required.
- 除非明确只需要视觉效果，否则论文中不建议使用公式截图。
- Keep document-specific paths, titles, images, and formula overrides outside the reusable skill files.
- 与具体文档相关的路径、标题、图片和特殊公式映射应放在项目文件中，不应写入可复用 skill 文件。
