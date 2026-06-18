# 📚 WeRead to PDF: Ultimate Typography Engine
**微信读书导出 HTML 到极致排版 PDF 的终极转换引擎**

[English](#english) | [中文](#中文)

---

<a id="english"></a>
## English

### What is this?
`weread-to-pdf` is a highly specialized, production-grade script designed to convert exported HTML books (especially from WeChat Reading / WeRead) into perfectly paginated, typography-focused PDF documents. 

It is not just a simple HTML-to-PDF wrapper. It is an entire layout engine built on top of Chromium, designed to solve the most painful edge cases of web-to-print conversion.

### Why does this exist? (Core Philosophies)

1. **AI-Native & Zero Token Cost**: This tool is designed as a "Skill" for AI agents. Instead of feeding a 200,000-word book into an LLM's context window (wasting massive amounts of tokens and risking truncation), the AI can simply execute this script blindly in the background. The script handles all the heavy lifting automatically.
2. **Defeating Chromium's Print Bugs**: Standard browsers notoriously fail at complex pagination. Long URLs bleed off the page, code blocks split across pages, and images detach from their captions. This engine injects microscopic ASCII markers, dynamically overrides CSS, and splits long strings to ensure **flawless page-break behavior**.
3. **Premium Typography Offline**: Electronic books should feel like physical books. We bundle a 25MB sliced version of the gorgeous **LXGW WenKai Lite (霞鹜文楷)** calligraphy font. It dynamically mounts during rendering and auto-cleans afterward, providing a premium reading experience entirely offline.
4. **Deep Lossless Compression**: High-res covers and embedded fonts lead to bloated PDFs. By natively integrating `PyMuPDF` into the final pipeline step, the engine compresses the PDF structure and image layers by over 60% with zero visual quality loss.

### Installation

Ensure you have Python installed, then install the required dependencies and the headless Chromium browser:

```powershell
pip install playwright pdfplumber pypdf reportlab beautifulsoup4 requests pillow pymupdf
python -m playwright install chromium
```

### How to Use

#### Basic Usage
Point the script to the main `index.html` file of your exported book.
```powershell
# From an HTML file
python convert.py --input "path/to/book/index.html"

# From a ZIP archive
python convert.py --zip "book.zip" --title "Book Title" --cover "cover.jpg"
```
*The resulting PDF will be saved one level above the HTML folder.*

#### Custom Configurations
```powershell
# Explicit output path
python convert.py --input "book.html" --output "custom/output.pdf"

# Different page format
python convert.py --input "book.html" --format Letter

# Switch rendering engine (WeasyPrint generates PDFs with perfect copy-paste text selection, but CSS support is slightly weaker than Chromium)
python convert.py --input "book.html" --engine weasyprint
```

#### Advanced Typography & Compression
Inject the offline calligraphy font and utilize default deep compression:
```powershell
python convert.py --input "book.html" --font lxgw
```
*(If you wish to keep the raw, uncompressed PDF, append `--no-compress`)*

#### Modular Execution
Only want to fetch a high-res cover from Douban without generating the PDF? Or only want to generate a cleaned-up Web Reader (`index_read.html`)? Use the `--step` parameter:
```powershell
python convert.py --input "book.html" --step cover  # Only fetch & replace cover
python convert.py --input "book.html" --step html   # Only generate the Web Reader view, skip PDF
python convert.py --input "book.html" --step pdf    # Only generate the PDF, skip Web Reader
python convert.py --input "book.html" --step all    # Default behavior: do everything
```

#### Standalone Utilities
If you just want to download a high-res cover from Douban without processing any book files:
```powershell
python get_cover.py --title "Book Title" --output "cover.jpg"
```

---

<a id="中文"></a>
## 中文

### 这是什么？
`weread-to-pdf` 是一个高度定制化、生产环境级别的排版脚本。它的核心使命，是将导出的 HTML 电子书（尤其是微信读书导出文件）完美转化为具备极佳纸质书阅读质感的 PDF 文档。

它绝不是一个简单的“调用浏览器打印 PDF”的套壳脚本。它是建立在 Chromium 之上的完整排版引擎，专门用于解决“网页转打印”中最让人头疼的各种边缘排版事故。

### 为什么要做这个项目？（核心设计理念）

1. **为 AI 智能体而生（零 Token 消耗）**：这是一个标准的 AI “技能（Skill）”。如果是传统 AI，你可能需要把几十万字的书籍源码塞进上下文里让它处理，这不仅极其耗费 Token，还会导致模型“忘词”或崩溃。而这个脚本允许 AI 在后台**“盲跑”**，AI 只需要敲下一行运行命令，剩下的脏活累活全由脚本在本地自动完成。
2. **彻底解决 Chromium 排版断页 Bug**：原生浏览器在处理复杂打印断页时极其拉胯（长链接冲出纸张边缘、代码块被切成两半、插图和文字描述天各一方）。本引擎通过底层注入隐形 ASCII 定位标记、动态重写 CSS 以及长字符切片黑科技，实现了**完美的防断页保护**。
3. **极致的离线排版美学**：电子书也应该有纸质书的温度。我们在底层内置了 25MB 的切片版**“霞鹜文楷 Lite”**手写字体包。只需一个参数，它就能在完全断网的环境下，让整本书焕发书法排版的质感，并在生成结束后“阅后即焚”清理缓存。
4. **底层无损深度压缩**：高清封面和内置字体会导致 PDF 体积暴涨。我们在最终合成阶段原生集成了 `PyMuPDF`，在保证视觉质量绝对零损失的前提下，对 PDF 底层代码和图层进行深度重编码，通常能让体积暴降 60% 以上。

### 环境安装

请确保已安装 Python，然后安装所需的底层依赖库以及无头 Chromium 浏览器：

```powershell
pip install playwright pdfplumber pypdf reportlab beautifulsoup4 requests pillow pymupdf
python -m playwright install chromium
```

### 使用指南

#### 基础转换
直接将脚本指向电子书源文件夹中的 `index.html` 即可：
```powershell
# 从 HTML 文件直接转换
python convert.py --input "path/to/book/index.html"

# 直接从 ZIP 压缩包转换
python convert.py --zip "book.zip" --title "书名" --cover "封面.jpg"
```
*生成的 PDF 会自动保存在与 HTML 文件夹平级的目录中，保持书籍目录的干净整洁。*

#### 自定义配置
```powershell
# 指定 PDF 输出路径
python convert.py --input "book.html" --output "custom/output.pdf"

# 更改纸张画幅尺寸 (如 Letter, A5 等)
python convert.py --input "book.html" --format Letter

# 切换渲染引擎（WeasyPrint 引擎生成的 PDF 文本复制体验极佳，不会出现多余换行，但 CSS 支持度略逊于 Chromium）
python convert.py --input "book.html" --engine weasyprint
```

#### 极致美学与深度压缩
一键注入离线书法字体，并默认开启深度无损压缩：
```powershell
python convert.py --input "book.html" --font lxgw
```
*（如果你由于特殊原因需要保留未压缩的原始 PDF，可以追加 `--no-compress` 参数）*

#### 模块化解耦运行
有时候你只想去豆瓣抓取并替换一张高清封面，或者只想生成一个剔除了乱七八糟元素的网页版纯净阅读器（`index_read.html`），并不想花时间生成 PDF。你可以使用 `--step` 参数：
```powershell
python convert.py --input "book.html" --step cover  # 仅抓取并替换高清封面
python convert.py --input "book.html" --step html   # 仅生成纯净网页版阅读器，跳过 PDF
python convert.py --input "book.html" --step pdf    # 仅生成 PDF，跳过网页版阅读器
python convert.py --input "book.html" --step all    # 默认行为：全部都做
```

#### 独立小工具
如果你仅仅是想从豆瓣抓取一张超清的书籍封面，并不想转换任何电子书，可以直接调用独立的封面脚本：
```powershell
python get_cover.py --title "书籍名称" --output "封面.jpg"
```
