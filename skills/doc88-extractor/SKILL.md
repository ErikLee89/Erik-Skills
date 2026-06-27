---
name: doc88-extractor
description: Convert authorized Doc88/道客巴巴 document preview URLs into text-selectable PDFs. Use when the user provides a doc88.com p-*.html URL or document ID and asks to download, extract, convert, rebuild, or compress a Doc88 document, including workflows involving m_main, EBT, SWF, ffdec, or non-image PDF output.
---

# Doc88 Extractor

Use the bundled script for the whole workflow. Do not reimplement the downloader in chat.

## Compliance Boundary

- Proceed only when the user says they have authorization or the document is their own/publicly authorized.
- Download only the EBT files listed in the page's `m_main.init(...)` configuration.
- Do not enable hidden-page scanning, `get_more`, captcha bypass, login automation, or paid-access bypass.
- If the page is blocked by login or verification and `m_main.init(...)` is not present, ask the user to log in and provide authorized page access, `m_main` data, or local `.ebt` files.

## Quick Start

Run:

```bash
python -X utf8 scripts/doc88_to_pdf.py "https://www.doc88.com/p-123456.html"
```

Useful options:

- Optimization is enabled by default. It uses skill-local Ghostscript first for strong text-selectable PDF compression, auto-downloading it when missing, then falls back to PyMuPDF if Ghostscript is unavailable.
- `--no-optimize`: skip the default non-rasterized optimization step.
- `--gs-pdfsettings`: choose Ghostscript compression settings, default `/default`; useful alternatives are `/prepress` and `/ebook`.
- `--output-root`: override where the final PDF is written. Default: the current user's system Downloads folder.
- `--tools-dir`: override the portable Java/ffdec directory. Default: the skill-local `.tools` directory; the script auto-downloads portable Java/ffdec there if missing.
- `--no-download-tools`: fail instead of downloading portable Java/ffdec when missing.
- `--keep-intermediates`: keep EBT/SWF/page-PDF working files for debugging.
- `--keep-groups`: also keep temporary grouped SWF/PDF conversion folders.
- `--force-swf2xml-pages`: force selected pages through the Doc88 XML vector renderer, e.g. `1,48-50`.
- `--skip-swf2xml-pages`: keep selected pages on the normal ffdec PDF path even if diagnostics mark them as fallback candidates.
- `--no-swf2xml-fallback`: disable automatic XML vector reconstruction for pages with bad ffdec text/layout diagnostics.

The script prints a JSON summary containing `final_pdf`, optional `optimized_pdf`, page count, size, and output directory.

## Output

By default, the script leaves only the final PDF in the output root and deletes the working directory.

With `--keep-intermediates`, the script keeps `doc88_<p_code>_ebt` under the output root with:

- `index.json`: decoded page configuration.
- `page_analysis.json`: deterministic per-page SWF/PDF diagnostics. Pages with garbled ffdec text layers are automatically replaced through `swf2xml` vector reconstruction unless `--no-swf2xml-fallback` is used.
- `*.ebt`: downloaded PH/PK files from the listed preview configuration.
- `swf/`: rebuilt SWF pages.
- `pdf_pages/`: one PDF per page; detected fallback pages are replaced by vector PDFs rebuilt from `swf2xml`.
- `pdf_pages_ffdec_original/`: original ffdec page PDFs saved before fallback replacement; used as a source for optional hidden text layers.
- `xml_pages/`: XML exports for pages rebuilt through the `swf2xml` fallback.
- `swf2xml_replacements.json`: per-page replacement diagnostics, including whether a hidden text layer was added or skipped.
- final `*_doc88_preview.pdf`.
- optional `*_vector_optimized.pdf`.

## Notes

- The normal ffdec path is text-selectable when the source SWF contains text objects or text layers.
- The `swf2xml` fallback keeps vector outlines and can add an invisible text layer only when the original ffdec page has a usable text layer. If diagnostics mark that original text as garbled, the fallback deliberately skips the text layer rather than embedding wrong searchable text.
- The fallback renderer is Doc88-document-page-specific. It handles the common Doc88 glyph-outline and line-shape patterns, but it is not a complete Flash/SWF renderer.
- Large PDFs are expected because ffdec and the XML fallback preserve many vector, font, and image objects. Use default optimization first; do not rasterize unless the user explicitly accepts image-only PDFs.


## Tool Downloads

- Ghostscript is downloaded from the official Artifex GitHub release URL embedded in `scripts/doc88_to_pdf.py`.
- Portable 7za is stored under `.tools/7zip` when bundled or auto-downloaded from the official 7-Zip URL embedded in the script. It is used to unpack the Ghostscript installer without requiring a system 7-Zip install.
- Portable Java and ffdec URLs are also embedded in the script and are used only when the corresponding `.tools` files are missing.
