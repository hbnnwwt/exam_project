"""答题卡 HTML 渲染器。

将 paginate() 的结果组装成完整的 HTML 文档（含 CSS）。
"""

from __future__ import annotations

from .layout_engine import Page, page_content_height
from .schema import AnswerSheetConfig

CSS_STYLES = """
* { box-sizing: border-box; }
body { font-family: "SimSun", "Microsoft YaHei", sans-serif; margin: 0; }
.page {
    width: 210mm; height: 297mm; padding: 10mm 10mm 10mm 10mm;
    page-break-after: always; position: relative;
}
.page:last-child { page-break-after: auto; }
.section { margin-bottom: 5mm; }
.section-title {
    font-weight: bold; font-size: 14pt; margin-bottom: 2mm;
    display: flex; justify-content: space-between; align-items: baseline;
}
.section-name { color: #000; }
.section-range { color: #666; font-size: 11pt; font-weight: normal; }
.bubble-grid { display: flex; flex-wrap: wrap; gap: 1.5mm; padding: 1mm 0; }
.bubble-cell {
    display: flex; gap: 0.8mm; align-items: center;
    border: 0.3mm solid #999; padding: 0.5mm 1mm;
    border-radius: 1mm; min-height: 5.5mm;
}
.bubble {
    display: inline-block; width: 4.5mm; height: 4.5mm;
    border: 0.3mm solid #333; border-radius: 50%;
}
.q-label { font-size: 10pt; min-width: 4mm; text-align: center; }
.essay-items, .solution-items { display: flex; flex-direction: column; gap: 3mm; }
.essay-item, .solution-item { padding: 1mm 0; }
.answer-line {
    height: 8mm; border-bottom: 0.2mm solid #ccc; margin: 1mm 0;
}
.section-before-gap { width: 100%; }
"""


def render_html(
    cfg: AnswerSheetConfig,
    pages: list[Page],
) -> str:
    """渲染完整 HTML 文档。"""
    paper_size = cfg.meta.paper_size
    min_height_mm = page_content_height(paper_size, 1)

    body_parts: list[str] = []
    for page in pages:
        components_html: list[str] = []
        y_offset = 0.0
        for comp in page.components:
            components_html.append(comp.render(
                page_num=page.page_number, y_offset_mm=y_offset, paper_size=paper_size,
            ))
            y_offset += comp.estimate_height(paper_size)
        body_parts.append(
            f'<section class="page" data-page="{page.page_number}" '
            f'style="min-height: {min_height_mm}mm;">'
            f'<h1 class="page-title">{cfg.meta.title}</h1>'
            f'{"".join(components_html)}'
            f'<div class="page-footer">第 {page.page_number} 页</div>'
            f'</section>'
        )

    return (
        '<!DOCTYPE html>\n'
        '<html lang="zh-CN">\n'
        '<head>\n'
        '<meta charset="UTF-8">\n'
        f'<title>{cfg.meta.title}</title>\n'
        f'<style>{CSS_STYLES}</style>\n'
        '</head>\n'
        '<body>\n'
        + '\n'.join(body_parts) + '\n'
        '</body>\n'
        '</html>\n'
    )
