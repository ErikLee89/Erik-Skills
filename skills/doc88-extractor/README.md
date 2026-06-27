# Doc88 Extractor Skill

Convert authorized Doc88 / ???? preview URLs into text-selectable PDFs.

## Compliance Boundary

- Use only when you have authorization to access the document.
- The downloader only fetches EBT resources listed in the page's `m_main.init(...)` configuration.
- It does not scan hidden pages, call `get_more`, bypass login, bypass captcha/slider verification, or bypass paid access.
- If `m_main.init(...)` is not available because the page requires login or verification, open the page with authorized access first or provide local authorized EBT/SWF files.

## Default Workflow

```bash
python -X utf8 scripts/doc88_to_pdf.py "https://www.doc88.com/p-123456.html"
```

Default behavior:

- Downloads the authorized EBT preview files listed by the page.
- Rebuilds page SWFs.
- Converts each SWF to PDF with ffdec.
- Merges the page PDFs.
- Optimizes the final PDF without rasterizing it.
- Writes the final PDF to the current user's system Downloads folder.
- Deletes process files unless `--keep-intermediates` is used.

The default path is ffdec-only because most Doc88 documents render correctly this way and the resulting PDF is much smaller.

## Important Review Step

After every run, check the delivered PDF manually, especially:

- landscape pages,
- formulas,
- tables,
- brackets and punctuation,
- pages listed in `swf2xml_candidate_pages` in the JSON summary.

ffdec can occasionally render custom Doc88 symbol fonts incorrectly. A common symptom is extra `]` characters or wrong formula/bracket glyphs even though the text layer may look extractable.

## Main Options

- `--output-root DIR`: write the final PDF to a specific directory. Default is the system Downloads folder.
- `--no-optimize`: skip final PDF optimization.
- `--gs-pdfsettings VALUE`: Ghostscript compression setting for ffdec-only PDFs. Default `/default`; alternatives include `/ebook` and `/prepress`.
- `--keep-intermediates`: keep the working directory with EBT, SWF, page PDFs, diagnostics, and run summary.
- `--keep-groups`: keep temporary ffdec group conversion folders.
- `--tools-dir DIR`: override the portable tool directory. Default is the skill-local `.tools` folder.
- `--no-download-tools`: fail instead of downloading missing portable tools.

## swf2xml Fallback

Use swf2xml fallback only when ffdec output has visual problems.

Enable automatic fallback:

```bash
python -X utf8 scripts/doc88_to_pdf.py "https://www.doc88.com/p-123456.html" --swf2xml-fallback
```

Force specific pages:

```bash
python -X utf8 scripts/doc88_to_pdf.py "https://www.doc88.com/p-123456.html" --force-swf2xml-pages 33,48-50
```

Fallback modes used with `--swf2xml-fallback`:

- `--swf2xml-mode conservative`: replace only pages with clearly broken text layers.
- `--swf2xml-mode auto`: replace broken text pages plus high-confidence visual glyph risk pages.
- `--swf2xml-mode aggressive`: replace more pages that use risky special fonts.
- `--swf2xml-mode all`: replace every static swf2xml candidate page.

Notes:

- swf2xml fallback preserves vector glyph outlines and can add an invisible text layer when the ffdec text layer is usable.
- Fallback pages are larger than ffdec pages, although PyMuPDF font subsetting is applied.
- If fallback pages are used, final optimization prefers PyMuPDF instead of Ghostscript to avoid corrupting hidden-text ToUnicode mappings.
- The fallback renderer is Doc88-page-specific, not a full Flash/SWF renderer.

## Output Files

Without `--keep-intermediates`, only the final PDF is left in the output root.

With `--keep-intermediates`, the working folder contains:

- `index.json`: decoded page configuration.
- `page_analysis.json`: per-page SWF/PDF diagnostics.
- `run_summary.json`: final run summary.
- `*.ebt`: downloaded PH/PK files.
- `swf/`: rebuilt page SWFs.
- `pdf_pages/`: one PDF per page.
- `pdf_pages_ffdec_original/`: original ffdec pages saved before fallback replacement.
- `xml_pages/`: swf2xml exports for fallback pages.
- `swf2xml_replacements.json`: fallback diagnostics.

## Tools and Dependencies

Bundled or auto-managed tools:

- Portable Java 17 under `.tools/jre17`.
- ffdec under `.tools/ffdec`.
- 7-Zip command-line files under `.tools/7zip`.
- Ghostscript is not bundled; its official download URL is embedded in the script and it is downloaded when needed.

Python dependencies used by the script:

- `requests`
- `pypdf`
- `PyMuPDF` / `fitz`
- `reportlab` (used by `swf_xml_vector.py`)

## Typical Recommendations

- Start with the default ffdec workflow.
- If pages are visually wrong, rerun with `--force-swf2xml-pages` for those pages.
- If many pages are wrong, rerun with `--swf2xml-fallback --swf2xml-mode auto` or `aggressive`.
- Avoid raster/OCR workflows unless image-only output is explicitly acceptable.
