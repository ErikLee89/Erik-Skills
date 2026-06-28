# Doc88 Extractor / 道客巴巴文档提取

## 这是什么 / What This Skill Does

这个 skill 用来把你有权限访问的 Doc88 / 道客巴巴预览文档转换成 PDF。你提供一个 `doc88.com/p-*.html` 链接或文档 ID，脚本会读取页面 `m_main.init(...)` 中公开列出的预览资源，下载对应的 EBT/SWF 分片，并合成为 PDF。

This skill converts authorized Doc88 preview documents into PDFs. Provide a `doc88.com/p-*.html` URL or document ID, and the script reads the preview resources explicitly listed in `m_main.init(...)`, downloads the corresponding EBT/SWF fragments, and merges them into a PDF.

默认路线是 **ffdec 转换 + 非栅格化压缩**。这适合大多数文档：速度快、文件较小，通常也能保留可复制文字。

The default route is **ffdec conversion plus non-rasterized optimization**. It is the best first choice for most documents: fast, compact, and usually text-selectable.

## 使用边界 / Access Boundary

请只用于你有权访问的文档。脚本只下载页面配置中列出的预览资源，不扫描隐藏页，不调用 `get_more`，不绕过登录、滑块、验证码或付费访问。

Use this only for documents you are authorized to access. The script only downloads preview resources listed by the page configuration. It does not scan hidden pages, call `get_more`, bypass login, bypass slider/captcha checks, or bypass paid access.

如果页面没有暴露 `m_main.init(...)`，通常说明需要先登录或验证。请先用合法方式打开页面，或提供你已经取得授权的本地文件。

If `m_main.init(...)` is not available, the page probably requires login or verification. Open it with authorized access first, or provide local authorized files.

## 常用命令 / Basic Commands

下载完整文档：

Download a full document:

```bash
python -X utf8 scripts/doc88_to_pdf.py "https://www.doc88.com/p-123456.html"
```

只下载指定页：

Download selected pages only:

```bash
python -X utf8 scripts/doc88_to_pdf.py "https://www.doc88.com/p-123456.html" --pages 1,20-22
```

强制指定页面走 swf2xml 修复：

Force selected pages through swf2xml repair:

```bash
python -X utf8 scripts/doc88_to_pdf.py "https://www.doc88.com/p-123456.html" --force-swf2xml-pages 33,48-50
```

默认情况下，最终 PDF 会放到当前系统用户的“下载”文件夹。每个文档的过程工作目录会在运行结束时自动删除，只保留最终 PDF。

By default, the final PDF is written to the current user's system Downloads folder. The per-document working folder is removed automatically at process exit, leaving only the final PDF.

## 默认流程 / Default Workflow

脚本会自动完成这些步骤：

The script does the following:

1. 读取页面配置 / Reads the page configuration.
2. 下载授权预览 EBT 分片 / Downloads authorized preview EBT fragments.
3. 重建每页 SWF / Rebuilds each page SWF.
4. 用 ffdec 把 SWF 转成单页 PDF / Converts SWFs into page PDFs with ffdec.
5. 按 Doc88 `pageInfo` 裁切可见页面区域 / Crops to the visible page area from Doc88 `pageInfo`.
6. 合并单页 PDF / Merges the page PDFs.
7. 默认进行非栅格化压缩 / Optimizes the final PDF without rasterizing it.
8. 删除过程工作目录，只保留最终 PDF / Deletes the working folder and keeps only the final PDF.

## 输出文件 / Output Files

默认只保留最终 PDF。

By default, only the final PDF is kept.

使用 `--keep-intermediates` 时，下载目录下会保留 `doc88_<p_code>_ebt` 工作目录，包含：

With `--keep-intermediates`, the Downloads folder keeps a `doc88_<p_code>_ebt` working directory containing:

- `index.json`：页面配置 / Page configuration.
- `page_analysis.json`：逐页诊断 / Per-page diagnostics.
- `run_summary.json`：运行摘要 / Run summary.
- `*.ebt`：下载的预览分片 / Downloaded preview fragments.
- `swf/`：重建后的 SWF 页面 / Rebuilt SWF pages.
- `pdf_pages/`：每页一个 PDF；fallback 页是 ffdec 背景 + swf2xml 文字轮廓的混合页 / One PDF per page; fallback pages are hybrid pages with ffdec background plus swf2xml text outlines.
- `pdf_pages_ffdec_original/`：swf2xml 替换前的原始 ffdec 页面 / Original ffdec pages before swf2xml replacement.
- `xml_pages/`：swf2xml 导出的 XML 和纯 swf2xml 诊断页 / XML exported by swf2xml plus vector-only diagnostic PDFs.
- `swf2xml_replacements.json`：替换诊断结果，包括触发原因、背景混合、保留图片/线框、隐藏文字层和优化状态 / Replacement diagnostics, including trigger reasons, background hybridization, preserved images/line art, hidden text layer, and optimization status.

## swf2xml 修复模式 / swf2xml Repair Mode

大多数页面默认走 ffdec。脚本会自动把两类高风险页面切换到 swf2xml：`pageInfo` 标记为横版的页面，以及 ffdec 文字层已经高置信损坏的页面，例如大量 `?`、没有中文、括号/公式错乱。其他问题页也可以手动强制。

Most pages use ffdec by default. The script automatically switches two high-risk page types to swf2xml: pages marked as landscape by `pageInfo`, and pages whose ffdec text layer is clearly broken, such as many `?` characters, no CJK text, or badly mapped brackets/formulas. Other pages can still be forced manually.

swf2xml fallback 会先保留 ffdec 原页中的图片、线框和其他背景对象，删除 ffdec 的可见错误文字，再叠加从 SWF 字形轮廓重建的文字。这样通常能保持图片和表格背景，同时修复文字视觉错误。

The swf2xml fallback preserves images, line art, and other background objects from the ffdec page, removes the visible ffdec text, and overlays text rebuilt from SWF glyph outlines. This usually keeps images/table backgrounds while fixing visual text errors.


有些异常页看起来会出现重复的“态”“示”“放”或零散的 `i`、`1`、括号等字符，复制粘贴时又变成 `?`。这通常不是正常中文，而是 Doc88 自定义字体或 ToUnicode 映射错位后的假文字。新规则会把这类高置信坏文字层页自动放入 `auto_swf2xml_broken_text_pages` 并用 swf2xml 替换；如果还有漏判，再用 `--force-swf2xml-pages` 单独修复。

Some broken pages may visually show repeated fake CJK glyphs such as `态`, `示`, or `放`, or scattered `i`, `1`, and bracket-like glyphs, while copied text turns into `?`. This usually means the visible glyphs and the PDF text/ToUnicode layer no longer agree. The current rule automatically places these high-confidence broken text-layer pages in `auto_swf2xml_broken_text_pages` and replaces them with swf2xml; use `--force-swf2xml-pages` only for remaining missed pages.

可用模式：

Available modes:

```bash
--swf2xml-fallback
--swf2xml-mode conservative
--swf2xml-mode auto
--swf2xml-mode aggressive
--swf2xml-mode all
--force-swf2xml-pages 1,48-50
--skip-swf2xml-pages 8,10
--no-auto-swf2xml-landscape
--no-auto-swf2xml-broken-text
```

## 常用参数 / Useful Options

```bash
--pages 1,20-22              # 只下载指定页 / selected pages only
--output-root DIR            # 指定最终 PDF 输出目录 / output directory
--no-optimize                # 跳过最终压缩 / skip optimization
--gs-pdfsettings /default    # Ghostscript 压缩设置 / Ghostscript setting
--no-remove-watermark        # 保留 doc88vounge/doc88vuonge marker 水印 / keep marker watermarks
--keep-intermediates         # 保留过程工作目录 / keep working folder
--keep-groups                # 保留 ffdec 分组转换目录 / keep ffdec group folders
--no-download-tools          # 缺工具时直接失败，不自动下载 / do not auto-download tools
```

## 工具和依赖 / Tools and Dependencies

脚本会优先使用 skill 本地 `.tools` 目录中的工具，缺失时按脚本内置的官方下载链接自动下载。

The script prefers tools under the skill-local `.tools` directory and auto-downloads missing tools from official URLs embedded in the script.

- `.tools/jre17`：便携 Java 17 / Portable Java 17.
- `.tools/ffdec`：JPEXS Free Flash Decompiler.
- `.tools/7zip`：便携 7-Zip 命令行文件 / Portable 7-Zip command-line files.
- Ghostscript：不随仓库打包，脚本按需自动下载 / Not bundled; auto-downloaded on demand.

Python 依赖 / Python packages:

- `requests`
- `pypdf`
- `PyMuPDF` / `fitz`
- `reportlab`

## 检查输出 / Review The Output

每次生成 PDF 后，都建议打开最终文件检查页面准确性，尤其注意横版页面、公式、表格、括号、标点，以及摘要里列出的 `swf2xml_candidate_pages`。

After each run, open the delivered PDF and check page accuracy, especially landscape pages, formulas, tables, brackets, punctuation, and pages listed in `swf2xml_candidate_pages`.

默认不要走 OCR 或纯图片转换，除非你明确接受图片型 PDF。

Avoid OCR or image-only conversion by default unless an image-based PDF is explicitly acceptable.
