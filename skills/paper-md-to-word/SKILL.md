---
name: paper-md-to-word
description: Convert academic or technical Markdown manuscripts into Word DOCX files with editable Word equations, especially when display equations, inline formulas, tables, figures, citations, and Chinese paper formatting must survive conversion.
---

# Paper MD to Word

## Overview

Use this skill when a Markdown manuscript needs to become a `.docx` paper with real editable Word equations instead of formula screenshots or plain text. It is designed for Chinese technical papers that mix headings, abstract, keywords, figures, Markdown tables, references, inline `$...$` formulas, and display `$$...$$` equations.

Keep this skill generic. Do not put a specific paper title, source path, output path, figure filename, formula list, or project-specific data in `SKILL.md` or the bundled scripts. Pass all document-specific values through command-line arguments or external files.

## Quick Start

Run the conversion script with an input Markdown file and an output path:

```powershell
python <skill-dir>\scripts\md_to_word_equations.py `
  --input D:\path\paper.md `
  --output D:\path\paper.docx
```

Optional metadata:

```powershell
python <skill-dir>\scripts\md_to_word_equations.py `
  --input D:\path\paper.md `
  --output D:\path\paper.docx `
  --author-line "作者姓名" `
  --affiliation-line "（单位名称    邮编）"
```

Optional paths:

- Use `--root` when image paths should resolve relative to a directory other than the Markdown file directory.
- Use `--pandoc` when Pandoc is installed at a non-standard path.
- Use `--equation-map path\to\equations.json` only for exceptional formulas that Pandoc cannot parse. The JSON must be an object mapping LaTeX expressions to complete MathML strings.

## Workflow

1. Read the source Markdown and confirm the formula style:
   - inline formulas are written as `$...$`;
   - display formulas are fenced as `$$` blocks;
   - equation numbers may be written as `\tag{1}` inside display formulas;
   - figures use normal Markdown image syntax;
   - tables are Markdown pipe tables.

2. Run `scripts/md_to_word_equations.py`.
   - It builds the Word document with `python-docx`.
   - It uses Pandoc to convert generic LaTeX math to MathML.
   - It converts MathML to Word OMML using Microsoft Office `MML2OMML.XSL`.
   - It keeps equation numbers outside the formula object and places them with Word fields.
   - It repairs DOCX XML after saving.

3. Validate the result:
   - confirm the script reports a nonzero Word equation count;
   - confirm `raw_dollar_count` is `0` unless intentionally leaving dollar signs in normal text;
   - open formulas containing `\sum`, `\int`, fractions, or aligned equations and check there is no empty square after the operator;
   - in Word, select all and update fields if equation numbers need refreshing.

## Paper Formatting Defaults

For company internal conference or technical-paper formatting, follow `references/company-paper-format.md`. Load that reference when formatting details matter or when updating the conversion script's template rules.

## Equation Handling

Prefer generic conversion over hardcoded formula mappings. The script strips `\tag{...}` before math conversion, sends the LaTeX formula body to Pandoc, converts Pandoc MathML to OMML, and writes the equation number separately on the right side of the line.

Use an external equation map only when necessary. Do not edit the reusable script for one paper's formulas. The equation-map file is deliberately outside the skill so document-specific content stays with the document project.

## Word Equation Repair

Always keep `repair_docx_xml()` in the workflow. It performs three important repairs:

- moves empty `m:nary/m:e` bodies into the correct Word equation structure, fixing the dotted square after summation signs;
- orders table border and shading XML in a way Word accepts cleanly;
- normalizes Word zoom settings so strict validators do not complain about missing attributes.

See `references/word-equation-repair.md` for details.


## Dependencies

Required environment:

- Python 3.10 or later.
- Python packages: `python-docx` and `lxml`.
- Pandoc, available from the command line as `pandoc`, unless `--pandoc` is used.
- Microsoft Office MathML-to-OMML transform file `MML2OMML.XSL`, normally at `C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL`, unless `--mml2omml` is used.

Optional but recommended:

- Microsoft Word, for opening the result and updating Word fields such as `SEQ Equation` and reference numbering after manual edits.

Quick checks on Windows:

```powershell
python -c "import docx, lxml; print('python packages ok')"
pandoc --version
Test-Path "C:\Program Files\Microsoft Office\root\Office16\MML2OMML.XSL"
```

## Notes

- If the target Word file is open and locked, write to a new versioned filename such as `_v2.docx`.
- Do not use formula screenshots for papers unless the user explicitly wants a visual-only document.
