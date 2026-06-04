"""答题卡 HTML 渲染器。"""

from __future__ import annotations

from typing import List, Optional

from .layout_engine import PAGE_SIZES, Page, paginate
from .schema import AnswerSheetConfig


_DEFAULT_INSTRUCTIONS: dict[str, str] = {
    "solution": "请在下方空白区域作答",
    "choice": "请将正确答案对应的圆圈涂黑",
    "judge": "正确的涂 T，错误的涂 F",
    "essay": "请在下方横线上作答",
    "student_id": "请用 2B 铅笔将对应数字涂黑",
}


def resolve_instruction(section_type: str, instruction: Optional[str]) -> str:
    """返回 section 实际渲染的 instruction 文本。

    - instruction == ""：明确不显示 → 返回 ""
    - instruction 为非空字符串：用户覆盖 → 返回它
    - instruction == None：使用默认 → 返回 _DEFAULT_INSTRUCTIONS[type]
    """
    if instruction == "":
        return ""
    if instruction is not None:
        return instruction
    return _DEFAULT_INSTRUCTIONS.get(section_type, "")


def _page_css(paper_size: str) -> str:
    """根据纸张尺寸返回 @page 的 size 值。"""
    size_map = {
        "A4": "210mm 297mm",
        "B5": "176mm 250mm",
    }
    return size_map.get(paper_size, "210mm 297mm")


def _to_chinese_numeral(n: int) -> str:
    """把 1-99 的整数转为中文数字（用于页眉"（一）"等）。

    超出范围返回 str(n)。
    """
    if not (1 <= n <= 99):
        return str(n)
    digits = "零一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + digits[n - 10]
    if n == 20:
        return "二十"
    tens = n // 10
    ones = n % 10
    if ones == 0:
        return digits[tens] + "十"
    return digits[tens] + "十" + digits[ones]


def _render_exam_info() -> str:
    """渲染考生信息填写区域。"""
    return """<div class="exam-info">
  <div class="info-row"><span class="info-label">班级：</span><span class="info-blank"></span></div>
  <div class="info-row"><span class="info-label">学号：</span><span class="info-blank"></span></div>
  <div class="info-row"><span class="info-label">姓名：</span><span class="info-blank"></span></div>
</div>"""


def render_html(cfg: AnswerSheetConfig, pages: List[Page]) -> str:
    """将分页结果渲染为完整 HTML 文档。

    新设计：每个 article 内部用 normal flow + page-break-inside: avoid，
    让浏览器按真实高度排版。页眉有"（一）"中文数字前缀，页脚带
    data-page-num 属性，由 beforeprint 监听的 JS 填入"共 N 页"。
    """
    paper_size = cfg.meta.paper_size
    page_size_css = _page_css(paper_size)
    total_pages = len(pages)

    pages_html = ""
    for page_idx, page in enumerate(pages):
        # 渲染本页所有组件（normal flow，不再算 top 坐标）
        components_html = ""
        for comp in page.components:
            components_html += comp.render(page.page_number, 0.0, paper_size)

        # 决定页标题：page_config.title > meta.title
        page_title = cfg.meta.title
        if page_idx < len(cfg.pages) and cfg.pages[page_idx].title:
            page_title = cfg.pages[page_idx].title

        # 中文页序号放在标题后，避免抢占主标题开头。
        chinese_n = _to_chinese_numeral(page.page_number)
        full_title = f"{page_title}（{chinese_n}）"

        # 仅 page 1 显示注意事项
        notice_html = ""
        if page_idx == 0:
            notice_html = """<div class="notice">
  注意事项：请用 2B 铅笔填涂，修改时擦除干净，保持卡面整洁，请勿折叠。
</div>"""

        # article 表示完整物理纸张；内部 padding 才是打印留白。
        min_height = PAGE_SIZES.get(paper_size, PAGE_SIZES["A4"])["height"]

        pages_html += f"""<article class="page" data-page-num="{page.page_number}" style="min-height: {min_height}mm;">
  <div class="print-hint">打印提示：请使用 {paper_size} 纸，在浏览器打印对话框中选择「另存为 PDF」或连接打印机直接打印。</div>
  <header class="page-header">
    <h1 class="page-title">{full_title}</h1>
    {_render_exam_info()}
    {notice_html}
  </header>
  <main class="page-content">
{components_html}
  </main>
  <footer class="page-mark" data-page-num="{page.page_number}">第 {page.page_number} 页 / 共 {total_pages} 页</footer>
</article>
"""

    # 屏显提示（仅 screen 媒体）
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{cfg.meta.title}</title>
<style>
@page {{ size: {page_size_css}; margin: 0; }}

:root {{
  --color-bg: #fff;
  --color-text: #222;
  --color-text-secondary: #666;
  --color-text-tertiary: #444;
  --color-border: #333;
  --border-light: #ccc;
  --border-subtle: #999;
  --color-hint-bg: #fffbe6;
  --color-hint-border: #ffe58f;
  --color-hint-text: #ad8b00;
  --color-screen-bg: #e5e5e5;
  --font-base: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  --font-size-base: 10.5pt;
  --font-size-title: 18pt;
  --font-size-section: 11pt;
  --font-size-label: 12pt;
  --font-size-small: 9pt;
  --font-size-xsmall: 8pt;
  --font-size-xsmall2: 8.5pt;
  --space-page-pad: 10mm;
  --space-section-gap: 5mm;
  --space-item-gap: 2mm;
  --space-footer-bottom: 8mm;
  --radius-base: 4px;
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: var(--font-base);
  font-size: var(--font-size-base);
  line-height: 1.4;
  color: var(--color-text);
}}

@media screen {{
  body {{ background: var(--color-screen-bg); padding: 20px; }}
  .page {{ background: var(--color-bg); box-shadow: 0 2px 8px rgba(0,0,0,0.12); margin: 0 auto 20px; }}
  .print-hint {{ display: block; }}
}}

@media print {{
  body {{ background: var(--color-bg); padding: 0; }}
  .page {{
    box-shadow: none;
    margin: 0;
  }}
  .print-hint {{ display: none; }}
}}

.page {{
  position: relative;
  width: {PAGE_SIZES.get(paper_size, PAGE_SIZES["A4"])["width"]}mm;
  padding: var(--space-page-pad);
  page-break-inside: avoid;
  page-break-after: always;
}}
.page:last-child {{ page-break-after: auto; }}

.print-hint {{
  background: var(--color-hint-bg);
  border: 1px solid var(--color-hint-border);
  border-radius: var(--radius-base);
  color: var(--color-hint-text);
  font-size: var(--font-size-small);
  padding: 6px 10px;
  margin-bottom: var(--space-section-gap);
  text-align: center;
}}

.page-title {{
  font-size: var(--font-size-title);
  font-weight: bold;
  text-align: center;
  margin-bottom: var(--space-section-gap);
  letter-spacing: 2px;
}}

.exam-info {{
  display: flex;
  gap: 12mm;
  margin-bottom: var(--space-section-gap);
  padding-bottom: 4mm;
  border-bottom: 1px solid var(--border-light);
}}

.notice {{
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  margin-bottom: 2mm;
  padding: 1.5mm 2mm;
  background: #f8f8f8;
  border: 1px dashed var(--border-subtle);
  border-radius: var(--radius-base);
  line-height: 1.5;
}}
.info-row {{ display: flex; align-items: baseline; }}
.info-label {{ font-size: var(--font-size-base); color: var(--color-text-tertiary); white-space: nowrap; }}
.info-blank {{
  display: inline-block;
  width: 35mm;
  border-bottom: 1px solid var(--color-border);
  margin-left: var(--space-item-gap);
  height: 1em;
}}

/* 题型区块：normal flow，不再 absolute 定位 */
.section-before-gap {{
  height: 0;
  page-break-after: avoid;
  break-after: avoid;
}}
.student-id-section,
.choice-section,
.judge-section,
.essay-section,
.solution-section {{
  page-break-inside: avoid;
  border: 1px solid var(--color-border);
  margin-bottom: var(--space-section-gap);
  padding: 0 4mm;
}}
.student-id-section {{
  padding: 4mm;
}}

.sid-title {{
  font-size: var(--font-size-label);
  font-weight: bold;
  margin-bottom: 2mm;
}}
.sid-instruction {{
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  margin-bottom: 2mm;
}}
.sid-grid {{
  display: grid;
  grid-template-rows: 8mm repeat(10, 7mm);
}}
.sid-cell {{
  text-align: center;
  font-size: var(--font-size-small);
  display: flex;
  align-items: center;
  justify-content: center;
  outline: 1px solid var(--color-border);
  outline-offset: -1px;
}}
.sid-write-cell {{
  background-color: var(--color-bg);
}}
.sid-omr {{
  width: 5.5mm;
  height: 5.5mm;
  border: 1px solid var(--color-border);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xsmall);
}}

.sec-title {{
  font-size: var(--font-size-section);
  font-weight: bold;
  margin-top: 2mm;
  margin-bottom: 2mm;
  padding-left: 2mm;
  border-left: 3px solid var(--color-border);
}}
.sec-instruction {{
  font-size: var(--font-size-small);
  font-weight: normal;
  color: var(--color-text-secondary);
  margin: 0 0 1.5mm 2mm;
  padding-left: 3mm;
  border-left: 2px solid var(--border-subtle);
}}
.choice-grid, .judge-grid {{
  display: grid;
  gap: 3mm 4mm;
  margin-bottom: 2mm;
}}
.q-item {{
  display: flex;
  align-items: center;
  gap: var(--space-item-gap);
  font-size: 10pt;
}}
.q-num {{ font-weight: bold; }}
.opt {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 5.5mm;
  height: 5.5mm;
  border: 1px solid var(--color-border);
  border-radius: 50%;
  font-size: var(--font-size-xsmall2);
}}

.essay-list {{ display: flex; flex-direction: column; gap: 3mm; margin-bottom: 2mm; }}
.essay-item {{ display: flex; gap: var(--space-item-gap); }}
.essay-label {{
  font-weight: bold;
  font-size: 10pt;
  min-width: 6mm;
}}
.essay-lines {{ flex: 1; display: flex; flex-direction: column; gap: var(--space-item-gap); }}
.essay-line {{
  height: 8mm;
  border-bottom: 1px solid var(--border-subtle);
}}
.solution-list {{ display: flex; flex-direction: column; gap: 3mm; margin-bottom: 2mm; }}
.solution-item {{ display: flex; gap: var(--space-item-gap); }}
.solution-label {{
  font-weight: bold;
  font-size: 10pt;
  min-width: 6mm;
}}
.solution-box {{
  flex: 1;
  min-height: 8mm;
}}

.page-mark {{
  position: absolute;
  bottom: var(--space-footer-bottom);
  right: var(--space-page-pad);
  font-size: var(--font-size-small);
  color: var(--color-text-secondary);
  text-align: right;
}}
</style>
</head>
<body>
{pages_html}
<script>
window.addEventListener('beforeprint', () => {{
  const total = document.querySelectorAll('.page').length;
  document.querySelectorAll('.page-mark').forEach(el => {{
    const n = el.dataset.pageNum;
    el.textContent = `第 ${{n}} 页 / 共 ${{total}} 页`;
  }});
}});
</script>
</body>
</html>"""
    return html


def generate(cfg: AnswerSheetConfig) -> str:
    """一键生成答题卡 HTML。

    先调用 paginate(cfg) 进行分页，再调用 render_html 渲染。
    """
    pages = paginate(cfg)
    return render_html(cfg, pages)
