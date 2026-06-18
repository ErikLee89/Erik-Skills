# My Gemini Skills

This repository contains custom skills and customizations for the Gemini desktop agent. 

## Included Skills

### 📚 [weread-to-pdf](./skills/weread-to-pdf)
A highly specialized HTML-to-PDF book converter designed specifically for WeChat Reading (微信读书) exports and other web-exported books. 

**Key Features:**
- **Zero Token Consumption Execution:** The AI runs this skill completely in the background without manually parsing the book, saving all your token quota.
- **Smart Cover Handling:** Automatically extracts the book's cover, compares it with Douban's high-res covers, and dynamically replaces it. Ensures the cover image fits full-screen (A4 size).
- **Anti-Pagination Engine:** Prevents images from separating from their captions, ensures code blocks (`pre`, `code`) stay together, and dynamically restrains image heights to prevent page-overflows.
- **Web Reader Cleaner:** Strips away decorative but distracting elements (like "bleed-pic" chapter headers) in the `index_read.html` reader view for a clean reading experience.
- **Perfect Chinese Encoding:** Safely preserves Chinese colons (`：`) and other characters in output filenames without mangling them.

## Installation & Usage

If you want your Gemini agent to use these skills, you can point your customizations root (`skills.json`) to this repository, or copy the `skills` folder directly into your `.gemini/config` directory.
