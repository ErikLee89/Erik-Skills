---
name: weread-to-pdf
description: Use this skill whenever the user wants to convert an HTML file or a ZIP archive (HTML + assets) into a PDF book. Common cases include e-books exported from WeRead (微信读书), web-exported books, or any single-page HTML document with chapters. Handles full-bleed covers, visible footnotes, multi-level bookmarks, headers, footers, and CJK text automatically.
---

# WeRead → PDF Book Converter

## AI Agent Execution Rules (Token Optimization)

- **Blind Execution**: When the user requests to convert a book, DO NOT read the target `index.html` file (e.g. via `view_file`) or print its contents to the terminal.
- **No Manual Parsing**: Do not try to read the HTML to find the cover image name or book title. The `convert.py` script automatically parses the HTML, finds the existing cover, downloads a better one if needed, and swaps it dynamically.
- **Save Tokens**: Simply execute the `python convert.py` command blindly in the background and wait for it to finish. Only inspect the HTML or logs if the user explicitly reports a bug and asks for debugging.

## Usage

```powershell
# From a ZIP archive (PDF defaults to the ZIP directory)
python convert.py --zip "书名.zip" --title "书名" --cover "封面.jpg"

# From an HTML file (PDF defaults to the parent of the HTML folder)
python convert.py --input "book_folder/index.html" --title "My Book"

# Explicit output path overrides the default
python convert.py --input "book_folder/index.html" --output "custom/output.pdf"

# Different page size
python convert.py --zip "book.zip" --format Letter
```

## PDF Output Location

- For `--input path/to/book_folder/index.html`, the default output is `path/to/{book title}.pdf`.
- For `--zip path/to/book.zip`, the default output is `path/to/{book title}.pdf`.
- The file name comes from `--title`, then the HTML `<title>`, then the source folder or ZIP name.
- An explicit `--output` always takes precedence.
- Source HTML, `index_read.html`, downloaded covers, and `assets/` remain together inside the book folder; the PDF is treated as the finished deliverable and placed one level above it.

## Fetching a High-Resolution Cover

The `html-to-pdf` skill automates book cover downloading and replacement. 

### Method 1 — Fully Automatic (Recommended)

When you run `convert.py`, an explicit `--cover` takes precedence. Otherwise, if `assets/cover_hd.jpg` already exists, it is treated as the previously audited winner and all Douban network access and comparison are skipped for both PDF and `index_read.html` generation. Only when `cover_hd.jpg` is missing does the skill download the Douban cover as `{书名}_豆瓣封面.jpg`. Search results are read from Douban's embedded `window.__DATA__`, with the book title checked for an exact match and the HTML's ISBN used as a fallback query. The downloaded cover's pixel dimensions are then compared with the image currently referenced by `<div class="custom-cover">`. The larger image is copied to `assets/cover_hd.jpg`; if the original image is larger than Douban's image, the original is used. Finally, the `<img>` inside `<div class="custom-cover">` is updated to `src="./assets/cover_hd.jpg"` in both `index.html` and the generated `index_read.html`. The original image and the downloaded Douban image remain available for inspection.

### Method 2 — Standalone Cover Downloader Utility

If you only want to download the cover for a book without running the full conversion, you can run the standalone `get_cover.py` script inside the skill's `scripts/` folder:

```powershell
python get_cover.py --title "书名" [--output "path/to/cover.jpg"]
```

By default, this will save the cover to `[书名]_封面.jpg` in your current working directory.


## Requirements

```powershell
pip install playwright pdfplumber pypdf reportlab beautifulsoup4 requests pillow
python -m playwright install chromium
```

## Features

| Feature | Implementation |
|---------|---------------|
| Full-bleed cover | The first PDF page uses zero margins and a `210mm × 297mm` cover with `object-fit:cover` |
| Level-one headings | Center all `h1` and `.firstTitle` elements in PDF output |
| Visible WeRead footnotes | Convert `data-wr-footernote` attributes into `[N]` markers and inline `[注N]` blocks |
| Cached cover reuse | Existing `assets/cover_hd.jpg` skips all Douban access and comparison |
| Default PDF location | Parent directory of the HTML folder; explicit `--output` overrides it |
| Remove nav & back-to-top | Regex removal before rendering |
| Page margins | CSS `@page { margin: 22mm 18mm 18mm 18mm }` (gives 8mm breathing room to headers/footers) |
| Section page breaks | Every WeRead `section.readerChapterContent` starts on a new PDF page, regardless of heading level |
| Optically centered title pages | Heading-only sections and title-plus-decoration wrappers are vertically centered, then shifted 10mm upward in print/PDF only |
| Header: book title + chapter | reportlab overlay per page |
| Footer: page number | reportlab overlay `— N —` |
| Multi-level PDF bookmarks | pypdf `add_outline_item()` (h1 → h2) |
| Heading hierarchy | Section level comes from its first real `h1`/`h2`/`h3`; PDF bookmarks and the HTML sidebar share this level model |
| Sidebar order | In-section headings are rendered before later child sections, preserving document order within each parent heading |
| Sidebar scroll sync | Tracks section and heading anchors and activates the last anchor above the reading line, including an `h2` immediately after its parent `h1` |
| Accurate chapter page detection | ASCII text markers + pdfplumber |
| Precise vertical (Y) navigation | `pdfplumber` character-level coordinates + `pypdf` `Fit.xyz()` |
| Inherited zoom bookmarks | `/XYZ null y null` via `Fit.xyz(zoom=None)` |
| Prevent orphaned content | CSS `page-break-inside: avoid;` keeps tables, images, and code blocks (`pre`, `code`) intact across pages |
| Graceful write lock fallback | `PermissionError` handling with timestamp backup outputs |
| HTML Web Reader View | Generates a persistent `index_read.html` reader view with a warm cream theme, draggable sidebar, decoupled folder toggles, SVG icons, and scroll syncing |

## Pipeline

```
ZIP/HTML
  │
  ▼ preprocess_html()
    • Replace cover image (optional --cover)
    • Remove <nav>, back-to-top
    • Preserve paragraph-image sizing and expand WeRead footnotes
    • Inject ASCII markers INSIDE each <section> as first child (with height separation)
    • Inject @page CSS with proper margins and double page break overrides
  │
  ▼ Playwright render_pdf()
    • Headless Chromium → PDF
    • CSS @page controls all margins (Playwright margin=0)
  │
  ▼ pdfplumber find_pages()
    • Scan each PDF page text stream for markers (e.g. BKMK0006)
    • Extract character-level coordinates (`page.chars`) to find precise Y heights
    • Returns page mapping and Y-coordinates for outline generation
  │
  ▼ reportlab build_overlay()
    • Per-page header + footer as transparent PDF overlay
  │
  ▼ pypdf merge_final()
    • Overlay merged onto content pages
    • PDF outline (bookmarks) written with precise Y coordinates and inherited zoom
  │
  ▼ Final PDF (with lock handling fallback)
```

## Key Designs & Troubleshooting

### 1. ASCII Marker-Based Page Detection
Accurate chapter positions are **critical** for bookmarks and header chapter names.
Two naive approaches fail:

| Approach | Why it fails |
|----------|--------------|
| JS `element.offsetTop / pageHeight` | Chromium reports screen layout positions, not paginated print positions → off by 2× |
| pdfplumber Chinese title search | Chromium embeds CJK fonts in ways pdfplumber can't decode → titles not found |

**Solution**: Inject tiny (3pt, `#FFFFFF` pure white) ASCII markers at the start of each section:
```html
<!-- BKMK0006 injected by script, invisible to reader -->
<section id="chapter-0006" class="readerChapterContent">
  <span class="bkmark">BKMK0006</span>
  ...chapter content...
</section>
```
Since they are pure white and Tiny, they are completely invisible to readers but remain in the PDF text stream.

### 2. Preventing Character Interleaving
If the hidden `.bkmark` is styled with `height: 0; line-height: 0;`, the rendering engine overlaps its bounding box with the subsequent heading. This causes `pdfplumber` to extract them together as interleaved characters (e.g., `"BKMK0003"` and `"推荐序一"` merges into `"B推KMK0003"`), which breaks exact match detection.
**Solution**: Set `.bkmark` to have block display and `12pt` line-height/height (e.g., a standard line size). It occupies invisible space at the top of the section and avoids character collision:
```css
.bkmark {
  font-size: 3pt;
  color: #FFFFFF;
  display: block;
  line-height: 12pt;
  height: 12pt;
  overflow: hidden;
  user-select: none;
}
```

### 3. Avoiding Double Page Breaks (Blank Pages)
If both `<section>` and the inner `<h1>` title have page break rules (such as `force-page-break` class in CJK HTML), Chromium triggers two page breaks, leaving an empty page containing only the hidden marker.
**Solution**: Override page break rules on headings inside chapter containers:
```css
.readerChapterContent h1.force-page-break,
.readerChapterContent h2.force-page-break {
  page-break-before: avoid !important;
}
```

### 4. Precise Y-Coordinate Navigation & Inherit Zoom
Instead of directing bookmarks to the top of pages, we locate the exact Y-coordinate of the marker in PDF space:
- **Y Calculation**: `pdfplumber` characters coordinates run top-down (`char['top']`). We convert them to PDF's bottom-up coordinate space: `found_y[key] = page.height - char['top']`.
- **Zoom Level (承前缩放)**: To prevent PDF readers from resetting to "Fit Page" when clicking a bookmark, use `Fit.xyz(left=None, top=top, zoom=None)`. This produces `/XYZ null y null` in the PDF outline dictionary, ensuring the viewer's current zoom is preserved.
- **Cover Alignment**: Force the cover bookmark's Y-coordinate to the page height so it always jumps to the top of page 1:
  ```python
  found_pages[first] = 1
  found_y[first] = first_page_height
  ```

### 5. Windows PDF Reader Lock handling
PDF writers fail on Windows with `PermissionError` if the output file is open in a reader (like Edge or Acrobat).
**Solution**: Wrap the output write in a try-except block to save to a fallback filename with a timestamp (e.g., `Book_1780999175.pdf`) so the Playwright rendering time is not lost.

### 6. Cover Download and Resolution Comparison

Do not assume the downloaded Douban image is larger than the exported HTML cover. Always keep both files long enough to compare their pixel dimensions:

1. Download the Douban result to `{书名}_豆瓣封面.jpg`.
2. Read the dimensions of that file and the image currently referenced by `.custom-cover`.
3. Copy the image with the larger pixel area to `assets/cover_hd.jpg` (prefer the original on an exact tie).
4. Update `.custom-cover img` in both `index.html` and `index_read.html` to `./assets/cover_hd.jpg`.
5. Preserve the original image and the downloaded Douban image so the decision can be audited.

### 7. Cover Display Size

The PDF cover occupies the full first A4 page: `@page :first` has zero margins,
the cover box is `210mm × 297mm`, and `object-fit: cover` fills the page. The
hidden bookmark marker is absolutely positioned so it cannot shrink or offset
the cover image.

### 8. Section-Based Page Breaks

WeRead's structural boundary determines pagination: every `section.readerChapterContent` starts on a new PDF page. Do not infer page breaks from whether the first heading is `h1`, `h2`, or `h3`, and do not exempt second-level sections from page breaks. Heading-level `force-page-break` rules inside a section are suppressed so the section boundary creates exactly one page break rather than a blank page.

### 9. Standalone Title Pages

If a section contains one or more headings but no substantive body text, images, tables, lists, code blocks, quotes, or other media, mark it as `title-only-section`. A direct `div[xmlns]` containing only one `h1` plus optional `bleed-pic`/`bleed-pic1` decoration paragraphs is treated the same way, as is a WeRead `bgimg-*` title block. In print/PDF mode, these containers occupy the available page content height, center their contents vertically, then shift them 10mm upward for better optical balance. These rules stay inside `@media print` and must not alter the continuous scrolling layout of `index_read.html`.

## Margin Layout

```
┌─────────────────────────────┐  ← top of page
│   ← 22mm top margin →       │
│  [Book title]  [Chapter]    │  ← header at 14mm (8mm gap to content)
│  ─────────────────────────  │  ← separator line
│                             │  ← content area
│                             │
│  ─────────────────────────  │
│         — 42 —              │  ← footer at 10mm (8mm gap to content)
│   ← 18mm bottom margin →   │
└─────────────────────────────┘  ← bottom of page
  ←  18mm  →        ← 18mm →
```
