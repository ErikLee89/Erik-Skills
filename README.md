# Erik's Skills Repository

[English](#english) | [中文](#中文)

---

<a id="english"></a>
## English

This repository is a collection of various skills, scripts, and automation tools designed to improve productivity. These skills are generally applicable and can be used by any AI agent, automation script, or human developer.

### Included Skills

#### 📚 [weread-to-pdf](./skills/weread-to-pdf)
A highly specialized HTML-to-PDF book converter designed specifically for WeChat Reading (微信读书) exports and other web-exported books. 

**Key Features:**
- **Zero Token Consumption Execution:** AI agents can run this skill completely in the background without manually parsing the book, saving token quotas.
- **Smart Cover Handling:** Automatically extracts the book's cover, compares it with Douban's high-res covers, and dynamically replaces it. Ensures the cover image fits full-screen (A4 size).
- **Anti-Pagination Engine:** Prevents images from separating from their captions, ensures code blocks (`pre`, `code`) stay together, and dynamically restrains image heights to prevent page-overflows.
- **Chromium Bug Bypass:** Automatically splits long URLs within code blocks into 15-character chunks to prevent Chromium's render truncation bug when `page-break-inside: avoid` is triggered.
- **Modular Execution Steps:** Run the conversion pipeline in modular steps (`--step cover`, `--step html`, `--step pdf`) to skip heavy Chromium processing and generate web readers instantly.
- **Web Reader Cleaner & Enhancer:** Strips away decorative but distracting elements (like "bleed-pic" chapter headers) in the `index_read.html` reader view. Automatically prevents layout shifts during native image loading by computing absolute aspect ratios.
- **Perfect Chinese Encoding:** Safely preserves Chinese colons (`：`) and other characters in output filenames without mangling them.

---

<a id="中文"></a>
## 中文

这个仓库是我个人收集和开发的各种技能（Skills）、脚本与自动化工具的集合，旨在全面提升工作效率。这些技能具有通用性，可以被任何 AI 智能体、自动化工作流或开发者直接调用。

### 包含的技能

#### 📚 [weread-to-pdf](./skills/weread-to-pdf)
一个高度定制化的 HTML 转 PDF 电子书排版神器，专门为微信读书（WeRead）导出以及其他网页端书籍量身打造。

**核心功能：**
- **零 Token 盲跑：** 完美适配 AI 智能体调用。AI 无需在上下文中读取十几万字的书籍源码即可在后台全自动完成高质量排版，不浪费任何 Token 额度。
- **智能封面处理：** 自动提取书籍封面，与豆瓣高清封面库比对并替换。解除最高高度限制，确保封面图能够顶天立地，完美铺满 A4 尺寸。
- **防断页排版引擎：** 强制图片与描述文字不可分割，确保代码块（`pre`, `code`）不会被切分到两页，动态限制普通插图高度以防止版面溢出。
- **跨行超链接修复黑科技：** 针对长链接在防断页代码块中会被 Chromium 渲染引擎吞掉属性的 Bug，采用了“15字符碎片化分块注射 + 屏蔽高亮器二次重绘”的底层黑科技进行完美修复。
- **模块化精准运行：** 支持通过 `--step` 参数进行解耦运行（如仅查验封面、仅生成网页阅读器、仅生成PDF），完美跳过不需要的耗时阶段，瞬间秒开网页版。
- **网页阅读器净化与增强：** 针对生成的网页版阅读器（`index_read.html`），自动剔除会干扰视觉的微信读书专属“章首大图”（bleed-pic），并在底层注入原生物理高宽比属性，彻底消灭懒加载带来的布局侧边栏错位抖动问题。
- **完美中文编码：** 支持 Windows 原生文件命名特性，不再将书名中的中文全角冒号（`：`）强制转换为下划线，保持原汁原味。
