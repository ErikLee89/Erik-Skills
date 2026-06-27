# Doc88 Extractor / 道客巴巴文档提取

## 这是什么 / What This Skill Does

这个 skill 用来把你有权限访问的道客巴巴 Doc88 预览文档转换成可复制文字的 PDF。你给它一个 `doc88.com/p-*.html` 链接，它会读取页面里公开列出的预览资源，下载对应的 EBT/SWF 分片，然后合成为 PDF。

This skill converts authorized Doc88 preview documents into text-selectable PDFs. Give it a `doc88.com/p-*.html` URL, and it downloads only the EBT/SWF preview resources explicitly listed by the page, then converts them into a PDF.

默认走 **ffdec 转换路线**。这条路线适合大多数文档：速度快、文件小，通常也能保留可复制文字。

The default route is **ffdec conversion**. It is the best first choice for most documents: faster, smaller, and usually text-selectable.

## 使用边界 / Access Boundary

请只用于你有权访问的文档。脚本只下载页面 `m_main.init(...)` 配置里列出的预览资源，不扫描隐藏页，不绕过登录，不绕过滑块或验证码，也不绕过付费访问。

Use this only for documents you are authorized to access. The script only fetches preview resources listed in the page's `m_main.init(...)` configuration. It does not scan hidden pages, bypass login, bypass slider/captcha checks, or bypass paid access.

如果页面没有暴露 `m_main.init(...)`，通常说明需要先登录或验证。请先用合法方式打开页面，或提供你已经取得授权的本地文件。

If `m_main.init(...)` is not available, the page probably requires login or verification. Open it with authorized access first, or provide local authorized files.

## 最常用命令 / Basic Command

```bash
python -X utf8 scripts/doc88_to_pdf.py "https://www.doc88.com/p-123456.html"
```

默认情况下，最终 PDF 会放到当前系统用户的“下载”文件夹。过程文件会自动删除，只保留最终 PDF。

By default, the final PDF is written to the current user's system Downloads folder. Temporary files are removed automatically, leaving only the final PDF.

## 默认流程 / Default Workflow

脚本会自动完成这些步骤：

The script does the following:

1. 读取页面配置 / Reads the page configuration.
2. 下载授权预览 EBT 分片 / Downloads the authorized preview EBT fragments.
3. 重建每页 SWF / Rebuilds each page SWF.
4. 用 ffdec 把 SWF 转成单页 PDF / Converts SWFs into page PDFs with ffdec.
5. 合并单页 PDF / Merges the page PDFs.
6. 在不栅格化的前提下压缩 PDF / Optimizes the final PDF without rasterizing it.
7. 输出结果，并提醒你人工检查 / Prints the result and reminds you to review the pages.

## 一定要人工检查 / Please Review The Output

每次生成 PDF 后，都建议打开最终文件检查页面准确性，尤其注意：

After each run, open the delivered PDF and check page accuracy. Pay special attention to:

- 横版页面 / landscape pages
- 公式 / formulas
- 表格 / tables
- 括号和标点 / brackets and punctuation
- 摘要里列出的 `swf2xml_candidate_pages`

少数 Doc88 文档会使用自定义符号字体，ffdec 有时会把这些字体映射错。常见现象是页面上多出 `]`，或者公式、括号显示不对。即使文字能复制，也不代表视觉结果一定正确。

ffdec can occasionally mis-map Doc88 custom symbol fonts. A common symptom is extra `]` characters or wrong formula/bracket glyphs. The text layer may still be selectable, so selectable text alone does not guarantee visual correctness.

## 常用参数 / Useful Options

### 输出位置 / Output Location

```bash
--output-root DIR
```

指定最终 PDF 的输出目录。默认是系统“下载”文件夹。

Choose where the final PDF is written. The default is the system Downloads folder.

### 保留过程文件 / Keep Intermediate Files

```bash
--keep-intermediates
```

保留 EBT、SWF、单页 PDF、诊断 JSON 和运行摘要，方便排查问题。

Keep EBT files, SWFs, page PDFs, diagnostic JSON files, and the run summary for debugging.

### 跳过压缩 / Skip Optimization

```bash
--no-optimize
```

跳过最终 PDF 压缩，主要用于对比原始转换效果。

Skip final PDF optimization. This is mainly useful when comparing raw conversion output.

### ?? Doc88 marker ?? / Keep Doc88 Marker Watermarks

```bash
--no-remove-watermark
```

????? PDF ??????????? `doc88vounge` ? `doc88vuonge` ???????????????????????????????

By default, the script removes text blocks that normalize to `doc88vounge` or `doc88vuonge`. It no longer removes content merely because it is rotated, transparent, or large.

### Ghostscript 压缩设置 / Ghostscript Compression Setting

```bash
--gs-pdfsettings /default
--gs-pdfsettings /ebook
--gs-pdfsettings /prepress
```

ffdec-only 文档默认会用 Ghostscript 压缩，通常可以显著减小文件体积。默认值是 `/default`。

ffdec-only documents are optimized with Ghostscript by default, which usually reduces file size significantly. `/default` is the default setting.

## swf2xml 修复模式 / swf2xml Repair Mode

大多数文档不需要 swf2xml。它默认关闭，因为 ffdec 通常更快、文件更小。

Most documents do not need swf2xml. It is disabled by default because ffdec is usually smaller and faster.

当某些页出现多余 `]`、横版文字错乱、公式或括号错误时，可以启用 swf2xml。它会从 SWF 的字形轮廓重新绘制页面，常常能修复 ffdec 的字体映射问题。

Use swf2xml when some pages show extra `]`, broken landscape text, or wrong formula/bracket glyphs. It redraws text from SWF glyph outlines while preserving images, line art, and other background objects from the original ffdec page. This often fixes ffdec font-mapping issues.

### 自动修复候选页 / Automatically Repair Candidate Pages

```bash
python -X utf8 scripts/doc88_to_pdf.py "https://www.doc88.com/p-123456.html" --swf2xml-fallback
```

开启后，脚本会替换诊断认为风险较高的页面。

With this enabled, the script replaces pages that diagnostics mark as risky.

### 指定修复页码 / Repair Specific Pages

```bash
python -X utf8 scripts/doc88_to_pdf.py "https://www.doc88.com/p-123456.html" --force-swf2xml-pages 33,48-50
```

如果你已经知道哪些页有问题，推荐用这种方式。它比自动替换大量页面更可控。

If you already know which pages are wrong, this is the recommended approach. It is more controlled than repairing many pages automatically.

### 判断严格度 / Detection Strictness

```bash
--swf2xml-mode conservative
--swf2xml-mode auto
--swf2xml-mode aggressive
--swf2xml-mode all
```

- `conservative`：只替换文字层明显损坏的页面 / Replaces only pages with clearly broken text layers.
- `auto`：替换损坏页和高置信符号字体风险页 / Replaces broken text pages plus high-confidence symbol-font risk pages.
- `aggressive`：替换更多使用可疑特殊字体的页面 / Replaces more pages that use risky special fonts.
- `all`：替换所有静态候选页，通常更慢也更大 / Replaces every static candidate page; usually slower and larger.

## 输出文件 / Output Files

默认只保留最终 PDF。

By default, only the final PDF is kept.

如果使用 `--keep-intermediates`，工作目录里会保留：

With `--keep-intermediates`, the working folder contains:

- `index.json`：页面配置 / Page configuration.
- `page_analysis.json`：逐页诊断 / Per-page diagnostics.
- `run_summary.json`：运行摘要 / Run summary.
- `*.ebt`：下载的预览分片 / Downloaded preview fragments.
- `swf/`：重建后的 SWF 页面 / Rebuilt SWF pages.
- `pdf_pages/`：每页一个 PDF / One PDF per page.
- `pdf_pages_ffdec_original/`：swf2xml 替换前的原始 ffdec 页面 / Original ffdec pages before swf2xml replacement.
- `xml_pages/`：swf2xml 导出的 XML / XML exported by swf2xml.
- `swf2xml_replacements.json`：替换诊断结果 / Replacement diagnostics.

## 工具和依赖 / Tools and Dependencies

这个 skill 使用这些工具：

The skill uses these tools:

- `.tools/jre17`：便携 Java 17 / Portable Java 17.
- `.tools/ffdec`：JPEXS Free Flash Decompiler.
- `.tools/7zip`：便携 7-Zip 命令行文件 / Portable 7-Zip command-line files.
- Ghostscript 不随仓库打包；脚本里写有官方下载链接，需要时会自动下载 / Ghostscript is not bundled in the repository; the official download URL is embedded and used when needed.

Python 依赖：

Python packages:

- `requests`
- `pypdf`
- `PyMuPDF` / `fitz`
- `reportlab`

## 推荐用法 / Recommended Use

先用默认 ffdec 流程。大多数文档到这里就够了。

Start with the default ffdec workflow. This is enough for most documents.

如果检查后发现少数页面不对，用 `--force-swf2xml-pages` 指定这些页重跑。

If some pages are wrong after review, rerun with `--force-swf2xml-pages` for those pages.

如果很多页都有问题，再考虑 `--swf2xml-fallback --swf2xml-mode auto` 或 `aggressive`。

If many pages are wrong, consider `--swf2xml-fallback --swf2xml-mode auto` or `aggressive`.

除非明确接受图片型 PDF，否则不建议走 OCR 或纯图片转换。

OCR or image-only conversion is not recommended unless an image-based PDF is explicitly acceptable.
