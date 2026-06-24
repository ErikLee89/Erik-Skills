# Company Paper Formatting Defaults

Use these defaults for company internal conference or technical-paper manuscripts unless the user provides a stricter template.

- Page margins: top 3.2 cm, bottom 1.6 cm, left 1.5 cm, right 1.5 cm.
- Title: centered, Xiaoer (18 pt), SimHei, not Word bold.
- Title blank paragraph: centered, Xiaowu (9 pt), SimHei, same paragraph/run formatting as the author line.
- Author and affiliation: centered, Xiaowu (9 pt), SimHei, not Word bold.
- Abstract: label `摘要：` in Xiaosi (12 pt) SimHei; content in Wuhao (10.5 pt) Songti; no first-line indent.
- Keywords: label `关键词：` in Xiaosi (12 pt) SimHei; content in Wuhao (10.5 pt) Songti; no first-line indent.
- Level-1 headings: Xiaosi (12 pt) SimHei.
- Level-2 headings: Xiaosi (12 pt) Songti.
- Body text: Wuhao (10.5 pt) Songti with first-line indent.
- Reference heading: centered Xiaosi (12 pt) SimHei.
- Reference entries: Wuhao (10.5 pt) Songti and Word automatic numbering with level text `[%1]`; strip any leading typed `[1]` from Markdown before writing the paragraph.
- Figure captions: below figures, Xiaowu (9 pt) Songti.
- Table captions: above tables, Xiaowu (9 pt) SimHei.
- Table body: Liuhao (7.5 pt) Songti.
- Convert citation markers such as `[1-2]`, `[3]`, `[4]`, and `[5-8]` to superscript Word runs in body text.
- For display equations, keep equation numbers outside the OMML formula object: set a centered tab stop at the text-width midpoint, a right tab stop at the text-width end, insert `Tab + OMML + Tab + (SEQ Equation)` so numbers align right and can update via Word fields.
- Allocate Markdown table column widths from content length, with fixed total page width and Word autofit disabled. Mark the first table row as a repeated header row.
