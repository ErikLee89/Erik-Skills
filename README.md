# Erik's Skills Repository

[English](#english) | [中文](#中文)

---

<a id="english"></a>
## English

This repository is a collection of reusable skills, scripts, and automation tools designed to improve productivity. These skills are generally applicable and can be used by AI agents, automation scripts, or human developers.

### Included Skills

#### 📄 [doc88-extractor](./skills/doc88-extractor)
A Doc88 / 道客巴巴 preview-document extractor that converts authorized `doc88.com/p-*.html` URLs into PDFs, with ffdec conversion by default and targeted swf2xml repair for problematic pages.

**Key Features:**
- **Authorized Preview Pipeline:** Downloads only EBT/SWF resources explicitly listed by the page configuration; no hidden-page scanning, login bypass, captcha bypass, or paid-access bypass.
- **Default ffdec Conversion:** Converts SWF previews into non-rasterized PDFs, then merges and optimizes them for everyday use.
- **Selected Page Downloads:** Supports `--pages` for extracting one page or a range without downloading every page fragment.
- **swf2xml Repair Mode:** Rebuilds problematic text from SWF glyph outlines while preserving ffdec images, line art, and page backgrounds.
- **Diagnostics:** Writes per-page analysis and fallback diagnostics when intermediates are kept, including trigger reasons, preserved images, removed text objects, and hidden-text-layer status.
- **Clean Output:** Writes the final PDF to the system Downloads folder and removes the per-document working folder by default.

#### 📝 [paper-md-to-word](./skills/paper-md-to-word)
A Markdown-to-Word manuscript converter for academic and technical papers, with editable Word equations and Chinese paper formatting support.

**Key Features:**
- **Editable Word Equations:** Converts standard LaTeX math through Pandoc, MathML, and Office OMML instead of using formula screenshots.
- **Equation Numbering:** Keeps display-equation numbers outside the formula object, right-aligned with Word fields for easier updates.
- **OMML Repair:** Fixes the common dotted-square placeholder after summation symbols in Word equations.
- **Paper Formatting:** Applies company-style technical-paper formatting for title, author, abstract, keywords, headings, captions, tables, and references.
- **Reference Handling:** Converts body citation markers to superscript and rewrites reference entries as bracketed Word automatic numbering, such as `[1]`.
- **Reusable Inputs:** Keeps paper-specific paths, titles, images, and special formula mappings outside the skill so the converter remains reusable.

#### 📚 [weread-to-pdf](./skills/weread-to-pdf)
A specialized HTML-to-PDF book converter designed for WeChat Reading (微信读书) exports and other web-exported books.

**Key Features:**
- **Token-Efficient Execution:** The conversion runs locally without sending the full book through an AI context window; agent orchestration still uses only a small amount of context.
- **Smart Cover Handling:** Automatically extracts the book cover, compares it with Douban high-resolution covers, and can replace it dynamically.
- **Anti-Pagination Engine:** Prevents images from separating from captions, keeps code blocks together, and dynamically restrains image heights to prevent page overflow.
- **Chromium Bug Bypass:** Splits long URLs inside code blocks to reduce Chromium truncation issues triggered by `page-break-inside: avoid`.
- **Modular Execution Steps:** Supports `--step cover`, `--step html`, and `--step pdf` to skip heavy stages when only part of the pipeline is needed.
- **Web Reader Cleaner:** Cleans distracting web-export elements and stabilizes native image layout in the generated reader view.
- **Native PDF Compression:** Uses PyMuPDF for lossless structural compression; file-size reduction depends on the source PDF and can be bypassed.
- **Offline LXGW WenKai Injection:** Bundles LXGW WenKai Lite (霞鹜文楷) for offline typographic styling.

---

<a id="中文"></a>
## 中文

这个仓库是我个人收集和开发的各种技能（Skills）、脚本与自动化工具集合，用来提升日常工作效率。这些技能尽量保持通用，可以被 AI 智能体、自动化工作流或开发者直接调用。

### 包含的技能

#### 📄 [doc88-extractor](./skills/doc88-extractor)
一个 Doc88 / 道客巴巴预览文档提取工具，可以把有权限访问的 `doc88.com/p-*.html` 链接转换成 PDF。默认使用 ffdec 路线，必要时可对问题页面启用 swf2xml 修复。

**核心功能：**
- **授权预览链路：** 只下载页面配置中明确列出的 EBT/SWF 预览资源，不扫描隐藏页，不绕过登录、验证码、滑块或付费访问。
- **默认 ffdec 转换：** 将 SWF 预览页转换为非栅格化 PDF，再合并和压缩，适合日常使用。
- **指定页下载：** 支持 `--pages` 提取单页或页码范围，不必下载所有页面分片。
- **swf2xml 修复模式：** 对问题页从 SWF 字形轮廓重建文字，同时保留 ffdec 原页中的图片、线框和背景。
- **诊断信息：** 保留过程文件时会输出逐页分析和 fallback 诊断，包括触发原因、保留图片、删除文字对象和隐藏文字层状态。
- **干净输出：** 最终 PDF 写入系统下载文件夹，默认删除每个文档的过程工作目录。

#### 📝 [paper-md-to-word](./skills/paper-md-to-word)
一个面向学术和技术论文的 Markdown 转 Word 工具，支持可编辑 Word 公式和中文论文格式。

**核心功能：**
- **可编辑 Word 公式：** 通过 Pandoc、MathML 和 Office OMML 转换标准 LaTeX 公式，避免使用公式截图。
- **公式编号：** 将块公式编号放在公式对象外部，并使用 Word 域右对齐，便于后续更新。
- **OMML 修复：** 修复 Word 公式中求和符号后出现空方块占位的常见问题。
- **论文格式：** 支持公司内部技术论文格式，包括标题、作者、摘要、关键词、章节标题、图题、表格和参考文献。
- **参考文献处理：** 将正文引用标识转换为上标，并将参考文献条目改写为 `[1]` 样式的 Word 自动编号。
- **可复用设计：** 具体论文的路径、标题、图片和特殊公式映射不写入 skill 本体，便于长期复用。

#### 📚 [weread-to-pdf](./skills/weread-to-pdf)
一个面向微信读书（WeRead）导出和其他网页端书籍的 HTML 转 PDF 工具。

**核心功能：**
- **Token 友好的本地执行：** AI 无需在上下文中读取整本书籍源码，转换由本地脚本完成。
- **智能封面处理：** 自动提取书籍封面，并可与豆瓣高清封面库比对替换。
- **防断页排版：** 防止图片与说明文字分离，确保代码块不被切分到两页，并动态限制图片高度。
- **跨行超链接修复：** 改善长链接在 Chromium PDF 渲染中的截断问题。
- **模块化运行：** 支持按步骤生成封面、网页阅读器或 PDF，跳过不需要的耗时阶段。
- **网页阅读器增强：** 清理干扰视觉的导出元素，并稳定图片加载时的版面。
- **无损结构压缩：** 默认使用 PyMuPDF 对生成 PDF 做结构压缩。
- **内置霞鹜文楷：** 可离线使用 LXGW WenKai Lite 字体提升排版质感。
