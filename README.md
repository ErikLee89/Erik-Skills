# Erik's Skills Repository

[English](#english) | [中文](#中文)

---

<a id="english"></a>
## English

This repository is a collection of various skills, scripts, and automation tools designed to improve productivity. These skills are generally applicable and can be used by any AI agent, automation script, or human developer.

### Included Skills

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
A highly specialized HTML-to-PDF book converter designed specifically for WeChat Reading (微信读书) exports and other web-exported books. 

**Key Features:**
- **Token-Efficient Execution:** The conversion runs locally without sending the full book through an AI context window; agent orchestration still uses a small amount of context.
- **Smart Cover Handling:** Automatically extracts the book's cover, compares it with Douban's high-res covers, and dynamically replaces it. Ensures the cover image fits full-screen (A4 size).
- **Anti-Pagination Engine:** Prevents images from separating from their captions, ensures code blocks (`pre`, `code`) stay together, and dynamically restrains image heights to prevent page-overflows.
- **Chromium Bug Bypass:** Automatically splits long URLs within code blocks into 15-character chunks to prevent Chromium's render truncation bug when `page-break-inside: avoid` is triggered.
- **Modular Execution Steps:** Run the conversion pipeline in modular steps (`--step cover`, `--step html`, `--step pdf`) to skip heavy Chromium processing and generate web readers instantly.
- **Web Reader Cleaner & Enhancer:** Strips away decorative but distracting elements (like "bleed-pic" chapter headers) in the `index_read.html` reader view. Automatically prevents layout shifts during native image loading by computing absolute aspect ratios.
- **Perfect Chinese Encoding:** Safely preserves Chinese colons (`：`) and other characters in output filenames without mangling them.
- **Native PDF Compression:** Uses PyMuPDF for lossless structural compression. File-size reduction depends on the source PDF and can be bypassed via `--no-compress`.
- **Offline LXGW WenKai Injection:** Bundled with the gorgeous LXGW WenKai Lite (霞鹜文楷) webfont. Use `--font lxgw` to instantly transform the entire book into a premium calligraphy-style layout, completely offline.

---

<a id="中文"></a>
## 中文

这个仓库是我个人收集和开发的各种技能（Skills）、脚本与自动化工具的集合，旨在全面提升工作效率。这些技能具有通用性，可以被任何 AI 智能体、自动化工作流或开发者直接调用。

### 包含的技能

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
一个高度定制化的 HTML 转 PDF 电子书排版神器，专门为微信读书（WeRead）导出以及其他网页端书籍量身打造。

**核心功能：**
- **Token 友好的本地执行：** AI 无需在上下文中读取整本书籍源码，转换由本地脚本完成；智能体编排和日志检查仍会使用少量 Token。
- **智能封面处理：** 自动提取书籍封面，与豆瓣高清封面库比对并替换。解除最高高度限制，使封面图铺满 A4 尺寸。
- **防断页排版引擎：** 强制图片与描述文字不可分割，确保代码块（`pre`, `code`）不会被切分到两页，动态限制普通插图高度以防止版面溢出。
- **跨行超链接修复：** 针对长链接在防断页代码块中可能被 Chromium 截断的问题，采用“15字符分块 + 避免高亮器二次重绘”的处理方式改善渲染。
- **模块化运行：** 支持通过 `--step` 参数进行解耦运行（如仅查验封面、仅生成网页阅读器、仅生成 PDF），跳过不需要的耗时阶段。
- **网页阅读器净化与增强：** 针对生成的网页版阅读器（`index_read.html`），自动剔除会干扰视觉的微信读书专属“章首大图”（bleed-pic），并在底层注入原生物理高宽比属性，彻底消灭懒加载带来的布局侧边栏错位抖动问题。
- **中文编码：** 支持 Windows 原生文件命名特性，不再将书名中的中文全角冒号（`：`）强制转换为下划线。
- **无损结构压缩：** 默认调用 PyMuPDF 对生成的 PDF 进行无损结构压缩，具体压缩幅度取决于原始文件。支持通过 `--no-compress` 参数保留原始体积。
- **内置霞鹜文楷：** 技能仓库原生内置 25MB 切片版“霞鹜文楷 Lite”字体包。只需追加 `--font lxgw`，即可在纯离线环境下瞬间让整本电子书焕发极具呼吸感的手写排版质感，且底层附带专属字号放大视觉补偿。
