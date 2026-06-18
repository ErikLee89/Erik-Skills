# -*- coding: utf-8 -*-
"""
html-to-pdf skill -- convert.py  v3.5

Usage:
  python convert.py --zip   path/to/book.zip [--output book.pdf] [--title "书名"]
  python convert.py --input path/to/index.html [--output book.pdf] [--title "书名"]

Requirements:
  pip install playwright pdfplumber pypdf reportlab
  python -m playwright install chromium
"""

import asyncio
import argparse
import re
import shutil
import subprocess
import warnings
import zipfile
from io import BytesIO
from pathlib import Path
import urllib.parse
import requests


warnings.filterwarnings('ignore', message='Could not get FontBBox')

# Page margins (mm) — used in CSS @page
MT = 22   # top    → header lives here
MB = 18   # bottom → footer lives here
MH = 18   # left / right


def sanitize_filename(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', '_', name)


def default_pdf_path(html_in: Path, book_title: str,
                     zip_path: Path | None = None) -> Path:
    """Place finished PDFs beside the HTML folder, or beside the source ZIP."""
    output_dir = zip_path.parent if zip_path else html_in.parent.parent
    return output_dir / f'{sanitize_filename(book_title)}.pdf'


# ─────────────────────────────────────────────────────────────
# 1. Parse HTML structure
# ─────────────────────────────────────────────────────────────

def extract_structure(html: str) -> list:
    """Return sections with heading-derived levels and nested in-section headings."""
    nav_titles, nav_order = {}, []
    nav_m = re.search(r'<nav\b[^>]*>(.*?)</nav>', html, re.DOTALL | re.I)
    if nav_m:
        for m in re.finditer(r'<a\s+href="#(chapter-\d+)"[^>]*>(.*?)</a>', nav_m.group(1)):
            cid   = m.group(1)
            title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if cid not in nav_titles:
                nav_titles[cid] = title
                nav_order.append(cid)

    ch_map = {}
    for sm in re.finditer(r'<section\s[^>]*id="(chapter-\d+)"[^>]*>(.*?)</section>',
                          html, re.DOTALL | re.I):
        cid, body = sm.group(1), sm.group(2)
        first_heading = re.search(r'<h([1-3])\b[^>]*>(.*?)</h\1>', body, re.DOTALL | re.I)
        heading_title = (re.sub(r'<[^>]+>', '', first_heading.group(2)).strip()
                         if first_heading else '')
        ch_title = heading_title or nav_titles.get(cid, cid)
        ch_level = int(first_heading.group(1)) if first_heading else 1
        h2s = []
        h2_idx = [0]  # mutable counter
        current_h2 = None
        for m in re.finditer(r'<h([23])([^>]*)>(.*?)</h\1>', body, re.DOTALL | re.I):
            level = int(m.group(1))
            attrs = m.group(2)
            t = re.sub(r'<[^>]+>', '', m.group(3)).strip()
            id_m = re.search(r'id="([^"]+)"', attrs)
            h_id = id_m.group(1) if id_m else None

            if not t or t == ch_title:
                continue

            if level == 2:
                current_h2 = {'id': h_id, 'title': t, 'h3s': [], '_seq': h2_idx[0]}
                h2_idx[0] += 1
                h2s.append(current_h2)
            elif level == 3:
                if current_h2 is None:
                    # h3 with no parent h2 — treat as h2-level (no untitled wrapper)
                    h2s.append({'id': None, 'title': t, 'h3s': [], '_seq': h2_idx[0]})
                    h2_idx[0] += 1
                else:
                    current_h2['h3s'].append({'id': h_id, 'title': t})

        ch_map[cid] = {'id': cid, 'title': ch_title, 'level': ch_level, 'h2s': h2s}

    return [ch_map[c] for c in nav_order if c in ch_map]


def ch_mk(cid: str) -> str:
    """ASCII marker string for a chapter, e.g. BKMK0006"""
    return 'BKMK' + cid.replace('chapter-', '').zfill(4)

def h2_mk(cid: str, idx: int) -> str:
    """ASCII marker string for an h2 sub-section"""
    return 'BKMKH' + cid.replace('chapter-', '').zfill(4) + str(idx).zfill(2)

def h3_mk(cid: str, idx: int, jdx: int) -> str:
    return 'BKMKT' + cid.replace('chapter-', '').zfill(4) + str(idx).zfill(2) + str(jdx).zfill(2)


# ─────────────────────────────────────────────────────────────
# 2. Preprocess HTML
# ─────────────────────────────────────────────────────────────

# NOTE: This is a regular str, NOT an f-string.
# MT / MB / MH are substituted with .format() below.
PRINT_CSS_TEMPLATE = """\
<style id="__print__">
{FONT_FACE}
/* Global styles for both screen and print */
img {{
  max-width: 100%;
  height: auto;
}}
.custom-cover,
.custom-cover img {{
  width: 100% !important;
  max-width: 100% !important;
  height: auto !important;
}}
.bodyPic img, .qrbodyPic img {{
  max-width: 100% !important;
  width: auto !important;
  height: auto !important;
  display: inline-block;
}}
pre, code, .code-block, .readerCode {{
  white-space: pre-wrap !important;
  word-wrap: break-word !important;
  word-break: break-all !important;
}}
.bkmark {{
  display: none !important; /* Hide on screen so it doesn't leave gaps */
}}
.footnote-inline, .footnote-marker {{
  display: none !important; /* Hide on screen so they don't clutter the web view */
}}
.readerChapterContent h1,
.readerChapterContent .firstTitle {{
  text-align: center !important;
}}

/* Print-specific layout overrides */
@media print {{
  @page {{
    size: A4;
    margin: {MT}mm {MH}mm {MB}mm {MH}mm;
  }}
  @page :first {{
    margin: 0;
  }}
  body {{
    padding: 0 !important;
    margin: 0 auto !important;
    max-width: none !important;
    font-family: "Microsoft YaHei","PingFang SC","Source Han Serif CN",serif;
  }}
  nav, #nav, #back_top {{
    display: none !important;
  }}
  #main {{
    max-width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
  }}

  /* Cover: full-bleed A4 page */
  #chapter-0001 {{
    position: relative !important;
    width: 210mm !important;
    height: 297mm !important;
    min-height: 297mm !important;
    overflow: hidden !important;
    page-break-before: auto !important;
    page-break-after: always !important;
    margin: 0 !important;
    padding: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
  }}
  #chapter-0001 div, #chapter-0001 .custom-cover {{
    width: 100% !important;
    height: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
  }}
  #chapter-0001 img {{
    width: 210mm !important;
    max-width: none !important;
    height: 297mm !important;
    max-height: none !important;
    object-fit: cover !important;
    display: block !important;
  }}
  #chapter-0001 > .bkmark {{
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
  }}

  /* Every WeRead content section starts on a new page */
  section.readerChapterContent {{
    page-break-before: always !important;
    break-before: always !important;
  }}

  /* An xmlns wrapper is a standalone title page only when its direct
     children are one h1 plus optional WeRead bleed-image paragraphs. */
  section.readerChapterContent > div[xmlns]:has(> h1):not(:has(> :not(h1):not(p))):not(:has(> p:not(.bleed-pic):not(.bleed-pic1))) {{
    page-break-after: always !important;
    break-after: page !important;
    page-break-inside: avoid !important;
    break-inside: avoid-page !important;
    height: calc(297mm - {MT}mm - {MB}mm - 12pt) !important;
    padding: 0 !important;
    box-sizing: border-box !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
    text-align: center !important;
    transform: translateY(-10mm) !important;
  }}

  /* Styled chapter title pages (e.g. for 宏大细节) occupy a standalone page and are centered */
  section.readerChapterContent > div[class*="bgimg-"] {{
    page-break-after: always !important;
    break-after: always !important;
    text-align: center !important;
    height: calc(297mm - {MT}mm - {MB}mm - 12pt) !important;
    padding: 0 !important;
    box-sizing: border-box !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
    transform: translateY(-10mm) !important;
  }}

  section.readerChapterContent > div[class*="bgimg-"] h1,
  section.readerChapterContent > div[class*="bgimg-"] .firstTitle {{
    text-align: center !important;
    margin-top: 0 !important;
  }}

  section.readerChapterContent > div[class*="bgimg-"] p {{
    text-align: center !important;
  }}

  /* Sections containing only headings become vertically centered title pages. */
  section.title-only-section {{
    position: relative !important;
    min-height: calc(297mm - {MT}mm - {MB}mm) !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: center !important;
    text-align: center !important;
    transform: translateY(-10mm) !important;
  }}
  section.title-only-section > .bkmark {{
    position: absolute !important;
    top: 0 !important;
    left: 0 !important;
  }}
  section.title-only-section h1,
  section.title-only-section h2,
  section.title-only-section h3 {{
    text-align: center !important;
    margin-top: 0 !important;
  }}

  /* Prevent double page breaks when h1/h2 headings also have force-page-break class */
  .readerChapterContent h1.force-page-break,
  .readerChapterContent h2.force-page-break {{
    page-break-before: avoid !important;
    break-before: avoid !important;
  }}

  .readerChapterContent h1, .firstTitle {{
    text-align: center !important;
    margin-top: 1em !important;
    padding-top: 0 !important;
  }}

  .readerChapterContent h2, .readerChapterContent h3, .secondTitle, .thirdTitle {{
    text-align: left !important;
    margin-top: 1em !important;
    padding-top: 0 !important;
  }}

  /* Prevent headings from being orphaned at the bottom of a page */
  h1, h2, h3, .firstTitle, .secondTitle, .thirdTitle {{
    page-break-after: avoid !important;
    break-after: avoid !important;
  }}

  /* Disable WeasyPrint default bookmarks on headings to avoid duplicate/untitled bookmarks */
  h1, h2, h3, h4, h5, h6 {{
    bookmark-level: none !important;
  }}

  /* Hide chapter bleed images that push the title down */
  .readerChapterContent > div > p.bleed-pic:first-child,
  .readerChapterContent .bleed-pic {{
    display: none !important;
  }}

  /* Prevent images, tables, and code blocks from breaking across pages */
  .bodyPic, .qrbodyPic, pre, code, .readerCode {{
    page-break-inside: avoid !important;
    break-inside: avoid !important;
  }}

  /* Avoid page breaks right after images so they stick with their captions */
  img {{
    page-break-after: avoid !important;
    break-after: avoid !important;
    max-height: 235mm !important;
    object-fit: contain !important;
  }}

  /* Keep image captions glued to the preceding image */
  img + p.imgtitle, .bodyPic + p.imgtitle {{
    page-break-before: avoid !important;
    break-before: avoid !important;
  }}

  /* Inline footnote styling for print */
  .footnote-inline {{
    display: block !important;
    background-color: #faf6f0 !important;
    border-left: 3px solid #8b572a !important;
    margin: 8px 0 8px 2em !important;
    padding: 6px 12px !important;
    font-size: 0.88em !important;
    color: #555555 !important;
    line-height: 1.5 !important;
    page-break-inside: avoid !important;
    break-inside: avoid !important;
  }}
  .footnote-marker {{
    display: inline !important;
    font-size: 0.75em !important;
    vertical-align: super !important;
    color: #8b572a !important;
    font-weight: bold !important;
    margin-left: 2px !important;
  }}

  /* Bookmark markers: pure white, 3pt, zero height.
     INVISIBLE to readers (white on white page background).
     Still present in the PDF content stream, so pdfplumber
     extracts them regardless of color.
     Injected INSIDE each <section> as first child so that
     page-break-before:always places them on the correct page. */
  .bkmark {{
    font-size: 3pt;
    color: #FFFFFF;
    display: block !important;
    line-height: 12pt;
    height: 12pt;
    overflow: hidden;
    user-select: none;
    bookmark-level: none !important;
  }}
}}
</style>
"""

def build_print_css() -> str:
    font_face = ''
    pingfang_candidates = [
        Path.home() / 'AppData/Local/Microsoft/Windows/Fonts/PingFang-Regular.ttf',
        Path(r'C:\Windows\Fonts\PingFang-Regular.ttf'),
    ]
    for font_path in pingfang_candidates:
        if font_path.exists():
            font_face = (
                '@font-face {\n'
                '  font-family: "PingFang SC";\n'
                f'  src: url("{font_path.resolve().as_uri()}") format("truetype");\n'
                '  font-style: normal;\n'
                '  font-weight: 400;\n'
                '  font-display: block;\n'
                '}\n'
            )
            break
    return PRINT_CSS_TEMPLATE.format(
        MT=MT, MB=MB, MH=MH, FONT_FACE=font_face
    )


def build_sidebar(chapters: list, book_title: str) -> str:
    """WeRead-style reader: flex layout, draggable sidebar, proper nesting."""
    import json

    tree, section_stack = [], {}
    for ch in chapters:
        title, cid, h2s = ch['title'], ch['id'], ch.get('h2s', [])
        level = max(1, min(3, ch.get('level', 1)))
        node = {'id': cid, 'title': title, 'children': [], 'h2s': []}
        for h2 in h2s:
            h2n = {'title': h2['title'], 'id': h2.get('id') or '', 'children': []}
            for h3 in h2.get('h3s', []):
                h2n['children'].append({'title': h3['title'], 'id': h3.get('id') or ''})
            node['h2s'].append(h2n)
        parent = next(
            (section_stack[candidate]
             for candidate in range(level - 1, 0, -1)
             if candidate in section_stack),
            None,
        )
        if parent:
            parent['children'].append(node)
        else:
            tree.append(node)
        section_stack[level] = node
        for deeper_level in list(section_stack):
            if deeper_level > level:
                del section_stack[deeper_level]

    tj = json.dumps(tree, ensure_ascii=False)
    bj = json.dumps(book_title, ensure_ascii=False)

    # CSS + HTML + JS are built as plain strings (no f-string to avoid {{ }} issues)
    css = (
        '<style>\n'
        '@media print{#wb-sidebar,#wb-handle,#wb-tog{display:none!important}'
        '#wb-layout,#wb-content{height:auto!important;overflow:visible!important;display:block!important;margin:0!important}'
        'html,body{height:auto!important;overflow:visible!important;display:block!important;background:#fff!important}}\n'
        '*,*::before,*::after{box-sizing:border-box}\n'
        'html,body{margin:0;padding:0!important;height:100%;overflow:hidden!important;background:#f4f0eb;'
        'font-family:"PingFang SC","Microsoft YaHei",sans-serif}\n'
        '#wb-layout{display:flex;align-items:stretch;height:100vh;overflow:hidden}\n'
        '#wb-sidebar{width:260px;flex-shrink:0;background:#f4f0eb;color:#333333;display:flex;'
        'flex-direction:column;height:100%;overflow:hidden;z-index:100;border-right:1px solid #e5dec9}\n'
        '#wb-hdr{padding:14px 12px 10px 48px;border-bottom:1px solid #e5dec9;flex-shrink:0}\n'
        '#wb-title{font-size:12px;font-weight:700;color:#8b572a;margin-bottom:8px;'
        'white-space:nowrap;overflow:hidden;text-overflow:ellipsis}\n'
        '#wb-acts{display:flex;gap:6px}\n'
        '.wb-btn{flex:1;padding:3px 0;font-size:11px;background:#e8d5bf;color:#5c3a21;'
        'border:none;border-radius:4px;cursor:pointer;transition:background .15s}\n'
        '.wb-btn:hover{background:#e0cca5;color:#5c3a21}\n'
        '#wb-toc{flex:1;overflow-y:auto;padding:6px 0 20px;'
        'scrollbar-width:thin;scrollbar-color:#e8d5bf transparent}\n'
        '#wb-toc::-webkit-scrollbar{width:4px}\n'
        '#wb-toc::-webkit-scrollbar-thumb{background:#e5dec9;border-radius:2px}\n'
        '.ti{display:block}\n'
        '.tr{display:flex;align-items:flex-start;cursor:pointer;'
        'border-radius:4px;transition:background .12s;min-height:24px}\n'
        '.tr:hover{background:#eedcc5}\n'
        '.tr.active{background:#e8d5bf}\n'
        '.tr.active .tl{color:#8b572a;font-weight:600}\n'
        '.tc{flex-shrink:0;width:20px;color:#8b572a;'
        'display:inline-flex;align-items:center;justify-content:center;cursor:pointer;transition:transform .18s}\n'
        '.ti.open>.tr>.tc{transform:rotate(90deg)}\n'
        '.tl{flex:1;line-height:1.45;word-break:break-all;padding-top:3px}\n'
        '.tch{display:none}\n'
        '.ti.open>.tch{display:block}\n'
        '.tl1>.tr{padding:4px 8px 4px 10px}.tl1>.tr .tl{font-size:13px;font-weight:600;color:#111111}\n'
        '.tl2>.tr{padding:3px 8px 3px 22px}.tl2>.tr .tl{font-size:12px;color:#444444}\n'
        '.tl3>.tr{padding:2px 8px 2px 34px}.tl3>.tr .tl{font-size:11.5px;color:#666666}\n'
        '.tl4>.tr{padding:2px 8px 2px 46px}.tl4>.tr .tl{font-size:11px;color:#888888}\n'
        '#wb-handle{width:5px;background:transparent;cursor:col-resize;'
        'flex-shrink:0;transition:background .2s;z-index:101}\n'
        '#wb-handle:hover,#wb-handle.drag{background:#8b572a33}\n'
        '#wb-content{flex:1;min-width:0;height:100%;overflow-y:auto;background:#faf8f5;-webkit-overflow-scrolling:touch}\n'
        '#wb-content>section,.readerChapterContent{max-width:780px;margin:0 auto;padding:32px 48px}\n'
        '.bodyPic,.qrbodyPic{text-align:center!important}\n'
        '.bodyPic img,.qrbodyPic img{display:inline-block;max-width:100%;width:auto!important;height:auto!important}\n'
        '.readerChapterContent > div > p.bleed-pic:first-child, .readerChapterContent .bleed-pic {display: none !important}\n'
        '#wb-tog{position:fixed;top:10px;left:8px;z-index:200;width:32px;height:32px;'
        'background:#faf8f5;color:#8b572a;border:1px solid #e5dec9;border-radius:6px;'
        'cursor:pointer;display:flex;align-items:center;justify-content:center;'
        'box-shadow:0 2px 8px #0002}\n'
        '#wb-tog:hover{background:#e8d5bf}\n'
        '</style>\n'
    )

    js = (
        '<script>\n'
        'document.addEventListener("DOMContentLoaded", function() {\n'
        '  var TREE=' + tj + ';\n'
        '  var BT=' + bj + ';\n'
        '  var SVG_MENU = \'<svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:middle"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>\';\n'
        '  var SVG_CHEVRON = \'<svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block;vertical-align:middle"><polyline points="9 18 15 12 9 6"></polyline></svg>\';\n'
        '  var SVG_ARROW = \'<svg viewBox="0 0 24 24" width="10" height="10" stroke="currentColor" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round" style="display:inline-block"><polyline points="9 18 15 12 9 6"></polyline></svg>\';\n'
        '  var body=document.body;\n'
        '  var layout=document.createElement("div");layout.id="wb-layout";\n'
        '  var sidebar=document.createElement("div");sidebar.id="wb-sidebar";\n'
        '  sidebar.innerHTML='
        '  "<div id=\\"wb-hdr\\"><div id=\\"wb-title\\">\\u{1F4D6} "+BT+"</div>"'
        '  +"<div id=\\"wb-acts\\"><button class=\\"wb-btn\\" id=\\"wb-ea\\">\\u5168\\u90E8\\u5C55\\u5F00</button>"'
        '  +"<button class=\\"wb-btn\\" id=\\"wb-ca\\">\\u5168\\u90E8\\u6298\\u53E0</button>"'
        '  +"</div></div><div id=\\"wb-toc\\"></div>";\n'
        '  var handle=document.createElement("div");handle.id="wb-handle";\n'
        '  var content=document.createElement("div");content.id="wb-content";\n'
        '  Array.from(body.children).forEach(function(c){\n'
        '    if(c.id!=="wb-tog" && c.id!=="wb-layout") content.appendChild(c);\n'
        '  });\n'
        '  layout.appendChild(sidebar);layout.appendChild(handle);layout.appendChild(content);\n'
        '  body.appendChild(layout);\n'
        '  var toc=document.getElementById("wb-toc");\n'
        '  var all=[];\n'
        '  function mk(node,lv){\n'
        '    var kids=(node.h2s||[]).concat(node.children||[]);\n'
        '    var hc=kids.length>0;\n'
        '    var item=document.createElement("div");\n'
        '    item.className="ti tl"+lv+(hc?" hc":"");\n'
        '    var row=document.createElement("div");row.className="tr";\n'
        '    var car=document.createElement("span");car.className="tc";\n'
        '    if(hc){car.innerHTML=SVG_ARROW;}\n'
        '    var lbl=document.createElement("span");lbl.className="tl";lbl.textContent=node.title;\n'
        '    row.appendChild(car);row.appendChild(lbl);item.appendChild(row);\n'
        '    if(hc){\n'
        '      var cd=document.createElement("div");cd.className="tch";\n'
        '      kids.forEach(function(k){cd.appendChild(mk(k,lv+1));});\n'
        '      item.appendChild(cd);\n'
        '      car.addEventListener("click",function(e){\n'
        '        item.classList.toggle("open");\n'
        '        e.stopPropagation();\n'
        '      });\n'
        '    }\n'
        '    row.addEventListener("click",function(){\n'
        '      nav(node);\n'
        '      setA(item);\n'
        '    });\n'
        '    all.push({item:item,node:node});\n'
        '    return item;\n'
        '  }\n'
        '  TREE.forEach(function(ch){toc.appendChild(mk(ch,1));});\n'
        '  function nav(node){\n'
        '    if(node.id){var el=document.getElementById(node.id);\n'
        '      if(el){el.scrollIntoView({behavior:"smooth",block:"start"});return;}}\n'
        '    var t=(node.title||"").trim();\n'
        '    var hh=document.querySelectorAll("h1,h2,h3,h4");\n'
        '    for(var i=0;i<hh.length;i++){if(hh[i].textContent.trim().indexOf(t)>=0){\n'
        '      hh[i].scrollIntoView({behavior:"smooth",block:"start"});return;}}\n'
        '  }\n'
        '  function setA(item,smooth){\n'
        '    all.forEach(function(x){x.item.querySelector(".tr").classList.remove("active");});\n'
        '    item.querySelector(".tr").classList.add("active");\n'
        '    item.scrollIntoView({block:"nearest",behavior:smooth===false?"auto":"smooth"});\n'
        '  }\n'
        '  document.getElementById("wb-ea").addEventListener("click",function(){\n'
        '    document.querySelectorAll(".ti.hc").forEach(function(el){el.classList.add("open");});});\n'
        '  document.getElementById("wb-ca").addEventListener("click",function(){\n'
        '    document.querySelectorAll(".ti.hc").forEach(function(el){el.classList.remove("open");});});\n'
        '  var tog=document.getElementById("wb-tog");var vis=true;\n'
        '  tog.innerHTML=SVG_MENU;\n'
        '  tog.addEventListener("click",function(){\n'
        '    vis=!vis;sidebar.style.display=vis?"":"none";\n'
        '    handle.style.display=vis?"":"none";\n'
        '    tog.innerHTML=vis?SVG_MENU:SVG_CHEVRON;\n'
        '  });\n'
        '  var sx,sw;\n'
        '  handle.addEventListener("mousedown",function(e){\n'
        '    sx=e.clientX;sw=sidebar.offsetWidth;handle.classList.add("drag");\n'
        '    e.preventDefault();\n'
        '    document.addEventListener("mousemove",drag);\n'
        '    document.addEventListener("mouseup",dragEnd);});\n'
        '  function drag(e){sidebar.style.width=Math.max(160,Math.min(500,sw+e.clientX-sx))+"px";}\n'
        '  function dragEnd(){handle.classList.remove("drag");\n'
        '    document.removeEventListener("mousemove",drag);\n'
        '    document.removeEventListener("mouseup",dragEnd);}\n'
        '  var anchors=[];\n'
        '  all.forEach(function(x){if(!x.node.id)return;\n'
        '    var el=document.getElementById(x.node.id);\n'
        '    if(el)anchors.push({el:el,item:x.item});});\n'
        '  var syncPending=false;\n'
        '  function syncActive(){syncPending=false;if(!anchors.length)return;\n'
        '    var box=content.getBoundingClientRect();\n'
        '    var line=box.top+Math.min(120,box.height*.15);\n'
        '    var best=null,bestTop=-Infinity,next=null,nextTop=Infinity;\n'
        '    anchors.forEach(function(a){var top=a.el.getBoundingClientRect().top;\n'
        '      if(top<=line&&top>bestTop){best=a;bestTop=top;}\n'
        '      if(top>line&&top<nextTop){next=a;nextTop=top;}});\n'
        '    var active=best||next;\n'
        '    if(active&&!active.item.querySelector(".tr").classList.contains("active"))\n'
        '      setA(active.item,false);\n'
        '  }\n'
        '  content.addEventListener("scroll",function(){if(syncPending)return;\n'
        '    syncPending=true;requestAnimationFrame(syncActive);},{passive:true});\n'
        '  window.addEventListener("resize",syncActive);\n'
        '  syncActive();\n'
        '});\n'
        '</script>\n'
    )

    toggle = '\n<button id="wb-tog" title="目录"></button>\n'
    return toggle + css + js


def _curl_fetch(url: str, headers: dict) -> bytes:
    """Fetch bytes with system curl when a site rejects Python HTTP clients."""
    curl = shutil.which('curl.exe') or shutil.which('curl')
    if not curl:
        return b''
    command = [curl, '-L', '--fail', '--silent', '--show-error']
    for name, value in headers.items():
        command.extend(['-H', f'{name}: {value}'])
    command.append(url)
    result = subprocess.run(command, capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else b''


async def auto_download_cover(book_title: str, output_path: Path, isbn: str = '') -> bool:
    from playwright.async_api import async_playwright
    import json
    import requests
    import re
    import urllib.parse

    # Clean title for searching (remove subtitle after colon)
    search_title = book_title.split('：')[0].split(':')[0].strip()
    print(f'[*] Attempting to auto-download cover for: {search_title} ...')

    # Douban embeds stable JSON search results in window.__DATA__. Prefer this
    # over the client-rendered .item-root selector, and retry by ISBN.
    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 Chrome/126.0 Safari/537.36'),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    queries = [search_title] + ([isbn] if isbn else [])
    for query_text in queries:
        query = urllib.parse.quote(query_text)
        douban_url = (
            'https://search.douban.com/book/subject_search?'
            f'search_text={query}&cat=1001'
        )
        print(f'[*] Searching Douban: {douban_url}')
        try:
            resp = requests.get(douban_url, headers=headers, timeout=20)
            resp.raise_for_status()
            data_match = re.search(r'window\.__DATA__\s*=\s*(\{.*?\});', resp.text, re.DOTALL)
            if not data_match:
                curl_html = _curl_fetch(douban_url, headers).decode('utf-8', errors='replace')
                data_match = re.search(
                    r'window\.__DATA__\s*=\s*(\{.*?\});', curl_html, re.DOTALL
                )
            if not data_match:
                continue
            items = json.loads(data_match.group(1)).get('items', [])
            normalized_title = re.sub(r'\s+', '', search_title)
            item = next(
                (candidate for candidate in items
                 if re.sub(r'\s+', '', candidate.get('title', '')) == normalized_title),
                items[0] if items else None,
            )
            if not item or not item.get('cover_url'):
                continue

            book_url = item.get('url', '')
            hd_url = item['cover_url'].replace('/s/', '/l/').replace('/m/', '/l/')
            print(f'[*] Found Douban book page: {book_url}')
            print(f'[*] Downloading Douban cover: {hd_url}')
            image_headers = dict(headers)
            image_headers['Accept'] = 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8'
            if book_url:
                image_headers['Referer'] = book_url
            image_bytes = b''
            try:
                image_resp = requests.get(hd_url, headers=image_headers, timeout=20)
                if image_resp.ok:
                    image_bytes = image_resp.content
            except Exception:
                pass
            if len(image_bytes) <= 1000:
                image_bytes = _curl_fetch(hd_url, image_headers)
            if len(image_bytes) > 1000:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(image_bytes)
                if image_dimensions(output_path):
                    print(f'[OK] Douban cover saved to: {output_path.name}')
                    return True
                output_path.unlink(missing_ok=True)
            print(f'[WARNING] Douban returned an invalid cover image for {query_text}')
        except Exception as e:
            print(f'[WARNING] Douban search failed for {query_text}: {e}')
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            for query_text in queries:
                query = urllib.parse.quote(query_text)
                douban_url = (
                    'https://search.douban.com/book/subject_search?'
                    f'search_text={query}&cat=1001'
                )
                print(f'[*] Searching Douban with browser: {douban_url}')
                await page.goto(douban_url, wait_until='domcontentloaded', timeout=30000)
                data_match = re.search(
                    r'window\.__DATA__\s*=\s*(\{.*?\});',
                    await page.content(),
                    re.DOTALL,
                )
                if not data_match:
                    continue
                items = json.loads(data_match.group(1)).get('items', [])
                normalized_title = re.sub(r'\s+', '', search_title)
                item = next(
                    (candidate for candidate in items
                     if re.sub(r'\s+', '', candidate.get('title', '')) == normalized_title),
                    items[0] if items else None,
                )
                if not item or not item.get('cover_url'):
                    continue
                book_url = item.get('url', '')
                hd_url = item['cover_url'].replace('/s/', '/l/').replace('/m/', '/l/')
                print(f'[*] Found Douban book page: {book_url}')
                image_resp = await page.context.request.get(
                    hd_url, headers={'Referer': book_url, 'Accept': 'image/*'}
                )
                image_bytes = await image_resp.body()
                if image_resp.ok and len(image_bytes) > 1000:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(image_bytes)
                    if image_dimensions(output_path):
                        print(f'[OK] Douban cover saved to: {output_path.name}')
                        await browser.close()
                        return True
                    output_path.unlink(missing_ok=True)
            
            # Step 1: Search Douban Book
            query = urllib.parse.quote(search_title)
            douban_url = f'https://search.douban.com/book/subject_search?search_text={query}&cat=1001'
            print(f'[*] Searching Douban: {douban_url}')
            await page.goto(douban_url, wait_until='domcontentloaded', timeout=30000)
            
            # Check if there is an item root anchor link
            item_selector = '.item-root a'
            try:
                await page.wait_for_selector(item_selector, timeout=8000)
                href = await page.get_attribute(item_selector, 'href')
            except Exception:
                href = None
                
            if href:
                print(f'[*] Found book page: {href}')
                await page.goto(href, wait_until='domcontentloaded', timeout=30000)
                await page.wait_for_selector('#mainpic img', timeout=10000)
                img_url = await page.get_attribute('#mainpic img', 'src')
                if img_url:
                    # Douban high-res image URL: replace /s/ with /l/
                    hd_url = img_url.replace('/s/', '/l/')
                    print(f'[*] Downloading cover from Douban: {hd_url}')
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    resp = requests.get(hd_url, headers=headers, timeout=15)
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        output_path.write_bytes(resp.content)
                        print(f'[OK] Cover downloaded and saved to: {output_path.name}')
                        await browser.close()
                        return True
            
            # Step 2: Fallback to JD.com Search
            jd_url = f'https://search.jd.com/Search?keyword={query}'
            print(f'[*] Fallback: Searching JD.com: {jd_url}')
            await page.goto(jd_url, wait_until='domcontentloaded', timeout=30000)
            
            img_selector = '.p-img img'
            try:
                await page.wait_for_selector(img_selector, timeout=8000)
                img_url = await page.get_attribute(img_selector, 'data-lazy-img')
                if not img_url:
                    img_url = await page.get_attribute(img_selector, 'src')
            except Exception:
                img_url = None
                
            if img_url:
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                # JD high-res image: replace s160x160_ with s800x800_
                hd_url = re.sub(r's\d+x\d+_', 's800x800_', img_url)
                hd_url = re.sub(r'n\d+/', 'n1/', hd_url)
                print(f'[*] Downloading cover from JD: {hd_url}')
                headers = {'User-Agent': 'Mozilla/5.0'}
                resp = requests.get(hd_url, headers=headers, timeout=15)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    output_path.write_bytes(resp.content)
                    print(f'[OK] Cover downloaded and saved to: {output_path.name}')
                    await browser.close()
                    return True
                    
            await browser.close()
        except Exception as e:
            print(f'[WARNING] Auto-download cover failed: {e}')
    return False


def find_custom_cover_path(src: Path) -> Path | None:
    """Return the local image currently referenced by ``.custom-cover``."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(src.read_text(encoding='utf-8'), 'html.parser')
    cover_div = soup.find('div', class_='custom-cover')
    img = cover_div.find('img') if cover_div else None
    img_src = img.get('src', '').strip() if img else ''
    parsed = urllib.parse.urlsplit(img_src)
    if not img_src or parsed.scheme or parsed.netloc or img_src.startswith('//'):
        return None
    candidate = (src.parent / urllib.parse.unquote(parsed.path)).resolve()
    return candidate if candidate.is_file() else None


def image_dimensions(path: Path) -> tuple[int, int] | None:
    """Read raster dimensions using reportlab, which is already required."""
    try:
        from reportlab.lib.utils import ImageReader
        width, height = ImageReader(str(path)).getSize()
        return int(width), int(height)
    except Exception as e:
        print(f'[WARNING] Could not read cover dimensions for {path.name}: {e}')
        return None


def select_larger_cover(original_cover: Path | None,
                        douban_cover: Path | None) -> Path | None:
    """Choose the cover with the larger pixel area, preferring original on ties."""
    ranked = []
    for priority, label, path in ((1, 'original', original_cover),
                                  (0, 'Douban', douban_cover)):
        if not path or not path.is_file():
            continue
        dimensions = image_dimensions(path)
        if not dimensions:
            continue
        width, height = dimensions
        print(f'[*] {label} cover: {width}x{height} ({path.name})')
        ranked.append((width * height, priority, path))
    if not ranked:
        return None
    selected = max(ranked)[2]
    print(f'[OK] Selected larger cover: {selected.name}')
    return selected


def sync_custom_cover(src: Path, cover_jpg: Path) -> Path | None:
    """Save the high-resolution cover and point ``.custom-cover`` to it."""
    html = src.read_text(encoding='utf-8')
    pattern = re.compile(
        r'(<div\b[^>]*class=["\'][^"\']*\bcustom-cover\b[^"\']*["\'][^>]*>'
        r'.*?<img\b[^>]*\bsrc\s*=\s*)(["\'])[^"\']*(["\'])',
        re.DOTALL | re.I,
    )
    match = pattern.search(html)
    if not match:
        return None

    target = src.parent / 'assets' / 'cover_hd.jpg'
    target.parent.mkdir(parents=True, exist_ok=True)
    if cover_jpg.resolve() != target.resolve():
        try:
            shutil.copyfile(cover_jpg, target)
        except PermissionError:
            import stat
            target.chmod(target.stat().st_mode | stat.S_IWRITE)
            shutil.copyfile(cover_jpg, target)

    replacement = match.group(1) + match.group(2) + './assets/cover_hd.jpg' + match.group(3)
    html = html[:match.start()] + replacement + html[match.end():]
    src.write_text(html, encoding='utf-8')
    print('[OK] Original HTML cover updated -> ./assets/cover_hd.jpg')
    return target


def preprocess_html(src: Path, dst: Path, chapters: list,
                    book_title: str, cover_jpg: Path = None,
                    inject_sidebar: bool = False):

    from bs4 import BeautifulSoup
    html = src.read_text(encoding='utf-8')

    # Remove nav & back-to-top
    html = re.sub(r'<nav\b[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.I)
    html = re.sub(r'<[^>]*id=["\']back_top["\'][^>]*>.*?</a>', '', html, flags=re.DOTALL | re.I)

    # Shrink inline icons (images inside <p> with text)
    def shrink_icon(m):
        p_content = m.group(0)
        text_content = re.sub(r'<[^>]+>', '', p_content).strip()
        if len(text_content) > 0 and 'content-image-class' in p_content:
            p_content = re.sub(r'(<img[^>]*?)style="[^"]*"', r'\1', p_content, flags=re.I)
            p_content = p_content.replace('content-image-class', 'content-image-class" style="height:2.0em;width:auto;vertical-align:middle;margin:0 4px;')
        return p_content
    html = re.sub(r'<p\b[^>]*>.*?</p>', shrink_icon, html, flags=re.DOTALL | re.I)

    # Remove leading full-width spaces (　) from paragraph text
    html = re.sub(r'(<p\b[^>]*>(?:<[^/][^>]*>)*)\s*[\u3000\u00a0]+', r'\1', html, flags=re.I)

    # Parse with BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')

    # Mark sections that contain headings but no substantive body content.
    heading_tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']
    media_tags = ['img', 'table', 'ul', 'ol', 'pre', 'blockquote', 'svg', 'video', 'audio']
    for section in soup.find_all('section', class_='readerChapterContent'):
        if section.get('id') == 'chapter-0001' or not section.find(heading_tags):
            continue
        has_body_text = any(
            text.strip() and not text.find_parent(heading_tags)
            for text in section.find_all(string=True)
        )
        if not has_body_text and not section.find(media_tags):
            classes = list(section.get('class', []))
            if 'title-only-section' not in classes:
                section['class'] = classes + ['title-only-section']

    # Update <title>
    if soup.title:
        soup.title.string = book_title
    else:
        title_tag = soup.new_tag('title')
        title_tag.string = book_title
        if soup.head:
            soup.head.append(title_tag)

    # Replace cover image with high-res jpg (if supplied)
    if cover_jpg and cover_jpg.exists():
        section_cover = soup.find('section', id='chapter-0001')
        if section_cover:
            img = section_cover.find('img')
            if img:
                img['src'] = './assets/cover_hd.jpg'
                target_cover = src.parent / 'assets' / 'cover_hd.jpg'
                target_cover.parent.mkdir(parents=True, exist_ok=True)
                if cover_jpg.resolve() != target_cover.resolve():
                    import shutil as _sh
                    _sh.copy2(str(cover_jpg), str(target_cover))
                print(f'[OK] Cover image updated -> cover_hd.jpg')

    # Inject ASCII markers
    for ch in chapters:
        cid = ch['id']
        section = soup.find('section', id=cid)
        if not section:
            continue

        # Inject chapter marker as the first child of the section
        ch_marker = soup.new_tag('span', attrs={'class': 'bkmark'})
        ch_marker.string = ch_mk(cid)
        section.insert(0, ch_marker)

        # Inject h2 and h3 markers
        # Find all h2 and h3 elements inside this section, filtering out empty ones or chapter title
        ch_title = ch['title']
        headings = []
        for el in section.find_all(['h2', 'h3']):
            t = el.get_text(strip=True)
            if not t or t == ch_title:
                continue
            headings.append(el)

        marked_elements = set()
        for i, h2 in enumerate(ch['h2s']):
            h2_el = None
            for el in headings:
                if el not in marked_elements and el.get_text(strip=True) == h2['title']:
                    h2_el = el
                    break
            if not h2_el:
                for el in headings:
                    if el not in marked_elements and h2['title'] in el.get_text(strip=True):
                        h2_el = el
                        break
            
            if h2_el:
                marked_elements.add(h2_el)
                h2_marker = soup.new_tag('span', attrs={'class': 'bkmark'})
                h2_marker.string = h2_mk(cid, i)
                h2_el.insert_before(h2_marker)

                # Now do the same for h3s under this h2
                for j, h3 in enumerate(h2.get('h3s', [])):
                    h3_el = None
                    for el in headings:
                        if el not in marked_elements and el.get_text(strip=True) == h3['title']:
                            h3_el = el
                            break
                    if not h3_el:
                        for el in headings:
                            if el not in marked_elements and h3['title'] in el.get_text(strip=True):
                                h3_el = el
                                break
                    if h3_el:
                        marked_elements.add(h3_el)
                        h3_marker = soup.new_tag('span', attrs={'class': 'bkmark'})
                        h3_marker.string = h3_mk(cid, i, j)
                        h3_el.insert_before(h3_marker)

    # Process footnotes (convert data-wr-footernote to visible footnote block quotes)
    for ch in chapters:
        cid = ch['id']
        section = soup.find('section', id=cid)
        if not section:
            continue

        sec_notes = section.find_all(class_='reader_footer_note')
        note_counter = 0
        last_inserted_map = {}

        for note_span in sec_notes:
            if not note_span.get('data-wr-footernote'):
                continue

            note_counter += 1
            note_text = note_span['data-wr-footernote'].strip()

            # Create superscript marker
            sup = soup.new_tag('sup', attrs={'class': 'footnote-marker'})
            sup.string = f'[{note_counter}]'
            note_span.insert_after(sup)

            # Find parent block element or use direct parent
            parent_p = note_span.find_parent(['p', 'div', 'li', 'blockquote', 'section', 'td', 'th', 'h1', 'h2', 'h3', 'h4']) or note_span.parent

            # Create inline footnote block quote
            bq = soup.new_tag('blockquote', attrs={'class': 'footnote-inline'})
            strong = soup.new_tag('strong')
            strong.string = f'[注{note_counter}] '
            bq.append(strong)
            bq.append(note_text)

            # Insert footnote block in correct order after paragraph
            last_node = last_inserted_map.get(parent_p, parent_p)
            last_node.insert_after(bq)
            last_inserted_map[parent_p] = bq

    # Auto-link plain text URLs (分块切分法绕过 Chromium 吞长链接 bug)
    url_pattern = re.compile(r'(https?://[a-zA-Z0-9\-\._~:/?#\[\]@!$&\'()*+,;=%\n]+[a-zA-Z0-9\-\._~:/?#\[\]@!$&\'()*+,;=%])')
    for text_node in soup.find_all(string=True):
        # 避开已经被处理过，或者不能加链接的标签
        if text_node.parent.name in ['a', 'script', 'style', 'head', 'title']:
            continue
        text = str(text_node)
        if 'http' not in text:
            continue
        matches = list(url_pattern.finditer(text))
        if not matches:
            continue
        
        new_html = ""
        last_end = 0
        for match in matches:
            start, end = match.span()
            raw_url = match.group(1)
            # 清理可能的换行符，拿到纯净 URL
            href = raw_url.replace('\n', '').replace('\r', '')
            # 文本转义防止破坏 HTML
            before = text[last_end:start].replace('<', '&lt;').replace('>', '&gt;')
            new_html += before
            
            # 【核心逻辑】：将长 URL 按照 15 个字符切块，每块单独包裹 <a>
            chunk_size = 15
            for i in range(0, len(href), chunk_size):
                chunk = href[i:i+chunk_size]
                new_html += f'<a href="{href}" style="color: #0066cc; text-decoration: none; word-wrap: break-word; word-break: break-all;">{chunk}</a>'
            
            last_end = end
        new_html += text[last_end:].replace('<', '&lt;').replace('>', '&gt;')
        
        # 【重要防护】：为了防止 highlight.js 二次重绘毁掉我们的碎块 <a> 标签，给外层的 pre 加上 nohighlight
        pre_parent = text_node.find_parent('pre')
        if pre_parent:
            classes = pre_parent.get('class', [])
            if 'nohighlight' not in classes:
                pre_parent['class'] = classes + ['nohighlight']
                
        # 替换原文本节点
        new_soup = BeautifulSoup(new_html, 'html.parser')
        text_node.replace_with(new_soup)

    # Convert back to string
    html = str(soup)

    # Inject print CSS before </head>
    head_match = re.search(r'</head>', html, re.I)
    if head_match:
        head_tag = head_match.group(0)
        html = html.replace(head_tag, build_print_css() + '\n' + head_tag, 1)

    # Inject sidebar after <body> opening tag (only if inject_sidebar is True)
    if inject_sidebar:
        body_match = re.search(r'<body\b[^>]*>', html, re.I)
        if body_match:
            body_tag = body_match.group(0)
            html = html.replace(body_tag, body_tag + build_sidebar(chapters, book_title), 1)

    dst.write_text(html, encoding='utf-8')
    print('[OK] HTML preprocessed')


# ─────────────────────────────────────────────────────────────
# 3. Playwright: render PDF
# ─────────────────────────────────────────────────────────────

async def render_pdf(html_file: Path, pdf_out: Path, page_format: str = 'A4'):
    from playwright.async_api import async_playwright
    print('[*] Rendering PDF with Playwright (Chromium) ...')
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page    = await browser.new_page()
        await page.goto(html_file.resolve().as_uri(),
                        wait_until='networkidle', timeout=180000)
        await page.wait_for_timeout(3000)
        await page.pdf(
            path=str(pdf_out),
            format=page_format,
            print_background=True,
            display_header_footer=False,
            margin={'top': '0', 'bottom': '0', 'left': '0', 'right': '0'},
        )
        await browser.close()
    print(f'[OK] Base PDF: {pdf_out.name}  ({pdf_out.stat().st_size/1e6:.1f} MB)')


def render_pdf_weasyprint(html_file: Path, pdf_out: Path, page_format: str = 'A4'):
    """Render HTML to PDF using WeasyPrint.
    Advantage over Chromium: text is stored as continuous paragraph streams,
    so copy-paste from the PDF does NOT include hard line breaks.
    Limitation: less CSS compatibility than Chromium (flexbox, grid limited).
    """
    import os, sys
    # Auto-detect GTK DLL directories on Windows (required for WeasyPrint)
    gtk_candidates = [
        r'C:\Program Files\GTK3-Runtime Win64\bin',
        r'C:\Program Files\GTK4\bin',
        r'C:\msys64\mingw64\bin',
        r'C:\msys64\ucrt64\bin',
        r'C:\msys2\mingw64\bin',
    ]
    if sys.platform == 'win32':
        for gtk_path in gtk_candidates:
            if os.path.isdir(gtk_path):
                print(f'[*] Found GTK at: {gtk_path}')
                os.add_dll_directory(gtk_path)
                break
        else:
            print('[WARNING] GTK DLL directory not found. WeasyPrint may fail.')
            print('  Install GTK with: winget install -e --id tschoonj.GTKForWindows')
            print('  Then re-run this command.')

    import weasyprint
    print('[*] Rendering PDF with WeasyPrint ...')
    # WeasyPrint resolves relative asset paths from the base_url
    base_url = html_file.resolve().as_uri()
    wp = weasyprint.HTML(filename=str(html_file), base_url=base_url)
    wp.write_pdf(str(pdf_out))
    print(f'[OK] Base PDF: {pdf_out.name}  ({pdf_out.stat().st_size/1e6:.1f} MB)')


# ─────────────────────────────────────────────────────────────
# 4. pdfplumber: locate chapters by ASCII markers
# ─────────────────────────────────────────────────────────────

def find_pages(pdf_path: Path, chapters: list) -> tuple:
    import pdfplumber
    wanted = {}
    for ch in chapters:
        wanted[ch_mk(ch['id'])] = ch['id']
        for i, h2 in enumerate(ch['h2s']):
            key2 = f"{ch['id']}::h2_{i}"
            wanted[h2_mk(ch['id'], i)] = key2
            for j, h3 in enumerate(h2.get('h3s', [])):
                key3 = f"{ch['id']}::h2_{i}::h3_{j}"
                wanted[h3_mk(ch['id'], i, j)] = key3

    found_pages = {}
    found_y     = {}

    with pdfplumber.open(str(pdf_path)) as pdf:
        total = len(pdf.pages)
        first_page_height = pdf.pages[0].height if total > 0 else 842
        for pnum, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ''
            for mk, key in wanted.items():
                if key not in found_pages and mk in text:
                    found_pages[key] = pnum
                    chars_str = ''.join(c['text'] for c in page.chars)
                    idx = chars_str.find(mk)
                    found_y[key] = page.height - page.chars[idx]['top'] if idx >= 0 else page.height

    if chapters:
        first = chapters[0]['id']
        found_pages[first] = 1
        found_y[first]     = first_page_height

    return found_pages, found_y, total


# ─────────────────────────────────────────────────────────────
# 5. reportlab: header/footer overlay
# ─────────────────────────────────────────────────────────────

def _cjk_font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for fp, idx in [(r'C:\Windows\Fonts\msyh.ttc', 0),
                    (r'C:\Windows\Fonts\simhei.ttf', 0),
                    (r'C:\Windows\Fonts\simsun.ttc', 0)]:
        if Path(fp).exists():
            pdfmetrics.registerFont(TTFont('CJK', fp, subfontIndex=idx))
            return 'CJK'
    return 'Helvetica'


def build_overlay(total: int, chapters: list, pmap: dict, book_title: str) -> bytes:
    from reportlab.pdfgen import canvas as C
    from reportlab.lib.pagesizes import A4
    font = _cjk_font()
    W, H = A4
    mm   = 2.8346

    by_page = {pmap.get(ch['id'], 1): ch['title'] for ch in chapters}
    def ch_at(n):
        t = ''
        for p in sorted(by_page):
            if p <= n: t = by_page[p]
        return t

    buf = BytesIO()
    c   = C.Canvas(buf, pagesize=A4)
    for pnum in range(1, total + 1):
        if pnum >= 2:
            ch = ch_at(pnum)
            hy = H - 14 * mm
            c.setFont(font, 8);  c.setFillColorRGB(.30, .30, .30)
            c.drawString(MH * mm, hy, book_title)
            if ch: c.drawRightString(W - MH * mm, hy, ch)
            c.setStrokeColorRGB(.70, .70, .70);  c.setLineWidth(0.4)
            c.line(MH * mm, hy - 3, W - MH * mm, hy - 3)
            c.setFont(font, 8);  c.setFillColorRGB(.40, .40, .40)
            c.drawCentredString(W / 2, 10 * mm, f'\u2014 {pnum} \u2014')
        c.showPage()
    c.save()
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────
# 6. pypdf: merge overlay + bookmarks
# ─────────────────────────────────────────────────────────────

def merge_final(base: Path, overlay_bytes: bytes,
                chapters: list, pmap: dict, ymap: dict, out_pdf: Path, compress: bool = False):
    from pypdf import PdfWriter, PdfReader
    from pypdf.generic import Fit
    br  = PdfReader(str(base))
    ovr = PdfReader(BytesIO(overlay_bytes))
    tot = len(br.pages)
    w   = PdfWriter()

    for i, pg in enumerate(br.pages):
        if i < len(ovr.pages):
            pg.merge_page(ovr.pages[i])
        w.add_page(pg)

    def make_fit(key, fallback_page_idx):
        y = ymap.get(key)
        top = float(y) if y is not None else float(br.pages[fallback_page_idx].mediabox.height)
        return Fit.xyz(left=None, top=top, zoom=None)

    outline_stack = {}
    for ch in chapters:
        cp = pmap.get(ch['id'], 1) - 1
        level = max(1, min(3, ch.get('level', 1)))
        outline_parent = next(
            (outline_stack[candidate]
             for candidate in range(level - 1, 0, -1)
             if candidate in outline_stack),
            None,
        )
        parent = w.add_outline_item(
            ch['title'], cp, parent=outline_parent, fit=make_fit(ch['id'], cp)
        )
        outline_stack[level] = parent
        for deeper_level in list(outline_stack):
            if deeper_level > level:
                del outline_stack[deeper_level]
            
        for i, h2 in enumerate(ch['h2s']):
            key = f"{ch['id']}::h2_{i}"
            h2p = pmap.get(key, cp + 1) - 1
            h2_parent = w.add_outline_item(h2['title'], h2p, parent=parent, fit=make_fit(key, h2p))
            for j, h3 in enumerate(h2.get('h3s', [])):
                key3 = f"{ch['id']}::h2_{i}::h3_{j}"
                h3p = pmap.get(key3, h2p + 1) - 1
                w.add_outline_item(h3['title'], h3p, parent=h2_parent, fit=make_fit(key3, h3p))

    try:
        with open(out_pdf, 'wb') as f:
            w.write(f)
        final_path = out_pdf
    except PermissionError:
        import time
        suffix = int(time.time())
        fallback_pdf = out_pdf.with_name(f"{out_pdf.stem}_{suffix}.pdf")
        print(f'[WARNING] Permission denied writing to {out_pdf.name}. The file might be open in a PDF viewer.')
        print(f'[*] Attempting to write to fallback path: {fallback_pdf.name} ...')
        with open(fallback_pdf, 'wb') as f:
            w.write(f)
        final_path = fallback_pdf

    if compress:
        try:
            import fitz
            import os
            print(f'[*] Compressing {final_path.name} with PyMuPDF ...')
            doc = fitz.open(str(final_path))
            temp_path = final_path.with_name(f"{final_path.stem}_temp.pdf")
            doc.save(str(temp_path), garbage=4, deflate=True)
            doc.close()
            os.replace(temp_path, final_path)
        except ImportError:
            print('[WARNING] PyMuPDF (fitz) is not installed. Install with: pip install pymupdf')
        except Exception as e:
            print(f'[WARNING] Compression failed: {e}')

    print(f'[OK] PDF ready: {final_path}  ({final_path.stat().st_size/1e6:.1f} MB)')


# ─────────────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────────────

async def main_async(args):
    temp_dir = None
    zip_path = None

    if args.zip:
        zip_path = Path(args.zip)
        temp_dir = zip_path.parent / '_html_temp'
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        print(f'[*] Extracting {zip_path.name} ...')
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(temp_dir)
        candidates = sorted(temp_dir.glob('**/index.html')) or sorted(temp_dir.glob('**/*.html'))
        if not candidates:
            raise FileNotFoundError('No HTML file found in ZIP')
        html_in = candidates[0]
    else:
        html_in = Path(args.input)

    html       = html_in.read_text(encoding='utf-8')
    title_match = re.search(r'<title\b[^>]*>(.*?)</title>', html, re.DOTALL | re.I)
    html_title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ''
    fallback_title = zip_path.stem if zip_path else html_in.parent.name
    book_title = args.title or html_title or fallback_title
    pdf_out = (Path(args.output) if args.output
               else default_pdf_path(html_in, book_title, zip_path))
    pdf_out.parent.mkdir(parents=True, exist_ok=True)
    html_clean = html_in.parent / '_print.html'
    pdf_stage  = pdf_out.with_name('_stage.pdf')
    if not args.output:
        print(f'[*] Default PDF output: {pdf_out}')

    chapters   = extract_structure(html)
    print(f'[*] {len(chapters)} chapters')
    original_cover = find_custom_cover_path(html_in)
    isbn_match = re.search(r'ISBN[：:\s]*([0-9Xx-]{10,17})', html)
    isbn = re.sub(r'[^0-9Xx]', '', isbn_match.group(1)) if isbn_match else ''

    # Explicit --cover is an override. An existing cover_hd.jpg is already the
    # audited winner, so skip all network work. Otherwise download from Douban,
    # compare it with the current HTML cover, and keep the larger image.
    cover_jpg = None
    existing_hd_cover = html_in.parent / 'assets' / 'cover_hd.jpg'
    if args.cover:
        explicit_cover = Path(args.cover)
        if explicit_cover.exists():
            cover_jpg = explicit_cover
    elif existing_hd_cover.is_file():
        cover_jpg = existing_hd_cover
        print(f'[*] Found existing cover_hd.jpg; skipping Douban: {cover_jpg}')
    else:
        douban_cover = html_in.parent / f"{sanitize_filename(book_title)}_豆瓣封面.jpg"
        downloaded = await auto_download_cover(book_title, douban_cover, isbn)
        douban_candidate = douban_cover if downloaded or douban_cover.exists() else None
        cover_jpg = select_larger_cover(original_cover, douban_candidate)

    if cover_jpg:
        if not sync_custom_cover(html_in, cover_jpg):
            print('[WARNING] Could not update the image referenced by .custom-cover; using the rendering fallback.')

    step = getattr(args, 'step', 'all')
    if step == 'cover':
        print('[OK] Done! (--step cover finished)')
        return
                
    # For PDF generation: clean preprocessed HTML (no sidebar)
    if step in ('all', 'pdf'):
        preprocess_html(html_in, html_clean, chapters, book_title, cover_jpg, inject_sidebar=False)

    # For web reader view: preprocessed HTML with sidebar injected
    if step in ('all', 'html'):
        persistent_html = html_in.parent / 'index_read.html'
        try:
            preprocess_html(html_in, persistent_html, chapters, book_title, cover_jpg, inject_sidebar=True)
            if cover_jpg and not sync_custom_cover(persistent_html, cover_jpg):
                print('[WARNING] Could not update the image referenced by .custom-cover in index_read.html.')
            print(f'[OK] Saved preprocessed HTML reader view to: {persistent_html.name}')
        except Exception as e:
            print(f'[WARNING] Could not save persistent HTML copy: {e}')

    if step == 'html':
        print('[OK] Done! (--step html finished)')
        return

    try:
        engine = getattr(args, 'engine', 'chromium')
        if engine == 'weasyprint':
            # WeasyPrint is synchronous — run directly (no asyncio needed)
            render_pdf_weasyprint(html_clean, pdf_stage, args.format)
        else:
            await render_pdf(html_clean, pdf_stage, args.format)

        print('[*] Scanning PDF for markers ...')
        pmap, ymap, total = find_pages(pdf_stage, chapters)
        print(f'[*] {total} pages total')
        print('[*] Chapter pages:')
        for ch in chapters:
            y = ymap.get(ch['id'])
            ys = f'y={y:.0f}pt' if y is not None else 'y=top'
            print(f'    p.{pmap.get(ch["id"],"?"):>4}  {ys}  {ch["title"]}')

        overlay = build_overlay(total, chapters, pmap, book_title)
        merge_final(pdf_stage, overlay, chapters, pmap, ymap, pdf_out, compress=getattr(args, 'compress', False))
        print('[OK] Done!')

    finally:
        html_clean.unlink(missing_ok=True)
        pdf_stage.unlink(missing_ok=True)
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir)


def main():
    p = argparse.ArgumentParser(description='Convert HTML/ZIP ebook to PDF')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--input',  help='Path to HTML entry file')
    g.add_argument('--zip',    help='Path to ZIP containing HTML book')
    p.add_argument('--output', default='',
                   help='Output PDF path (default: parent of the HTML folder)')
    p.add_argument('--title',  default='',    help='Book title for header')
    p.add_argument('--cover',  default='',    help='Path to high-res cover jpg (optional)')
    p.add_argument('--format', default='A4',  help='Page format: A4, Letter, A5, etc.')
    p.add_argument('--engine', default='chromium', choices=['chromium', 'weasyprint'],
                   help='Rendering engine: chromium (default, better CSS) or weasyprint (seamless copy-paste)')
    p.add_argument('--compress', action='store_true', help='Compress output PDF with PyMuPDF (requires pip install pymupdf)')
    p.add_argument('--step', default='all', choices=['all', 'cover', 'html', 'pdf'],
                   help='Execution step: cover (only update cover), html (generate index_read.html), pdf (generate PDF), or all (default)')
    args = p.parse_args()
    asyncio.run(main_async(args))


if __name__ == '__main__':
    main()
