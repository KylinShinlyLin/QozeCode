import fitz  # PyMuPDF
import json
import sys
from jinja2 import Template


# 1. 提取 PDF 内容
def extract_pdf_content(pdf_path):
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()  # [[lvl, title, page, ...], ...]

    structure = []

    # 简单处理：如果没有目录，就按每 10 页一个章节
    if not toc:
        for i in range(0, len(doc), 10):
            end_page = min(i + 10, len(doc))
            text = ""
            for p in range(i, end_page):
                text += doc[p].get_text()
            structure.append({
                "title": f"Pages {i + 1}-{end_page}",
                "content": text,
                "summary": "待分析...",
                "insights": []
            })
    else:
        # 基于目录提取（简化版，实际需处理层级覆盖）
        # 这里仅作演示，实际建议按页码范围聚合
        for i, item in enumerate(toc):
            lvl, title, page = item[0], item[1], item[2]
            if page <= 0: continue

            # 计算结束页
            next_page = toc[i + 1][2] if i + 1 < len(toc) else len(doc)

            text = ""
            for p in range(page - 1, min(next_page - 1, len(doc))):
                text += doc[p].get_text()

            structure.append({
                "title": title,
                "content": text[:5000],  # 限制长度防止 Token 溢出
                "summary": "",
                "details": ""
            })

    return structure


# 2. HTML 模板 (内嵌)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{{ title }} - 深度研报</title>
    <style>
        :root { --primary: #2563eb; --bg: #f8fafc; --text: #334155; --card: #ffffff; }
        @media (prefers-color-scheme: dark) {
            :root { --primary: #60a5fa; --bg: #0f172a; --text: #e2e8f0; --card: #1e293b; }
        }
        body { font-family: -apple-system, system-ui, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; margin: 0; display: flex; }
        .sidebar { width: 300px; height: 100vh; overflow-y: auto; padding: 20px; border-right: 1px solid #ccc; position: fixed; background: var(--card); }
        .main { margin-left: 320px; padding: 40px; max-width: 800px; }
        .card { background: var(--card); padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); margin-bottom: 30px; }
        h1, h2, h3 { color: var(--primary); }
        .tag { display: inline-block; background: var(--primary); color: white; padding: 4px 8px; border-radius: 4px; font-size: 0.8em; margin-right: 5px; }
        blockquote { border-left: 4px solid var(--primary); margin: 0; padding-left: 15px; color: #64748b; }
        a { text-decoration: none; color: inherit; display: block; padding: 8px; border-radius: 6px; }
        a:hover { background: rgba(0,0,0,0.05); color: var(--primary); }
    </style>
</head>
<body>
    <div class="sidebar">
        <h3>📑 目录导航</h3>
        {% for section in sections %}
        <a href="#section-{{ loop.index }}">{{ section.title }}</a>
        {% endfor %}
    </div>
    <div class="main">
        <h1>📑 {{ title }} <span style="font-size:0.6em; opacity:0.7">深度分析报告</span></h1>

        <div class="card">
            <h2>💡 执行摘要 (Executive Summary)</h2>
            <p>{{ global_summary | replace('\n', '<br>') }}</p>
        </div>

        {% for section in sections %}
        <div id="section-{{ loop.index }}" class="card">
            <h3>{{ section.title }}</h3>
            <div class="analysis-content">
                {{ section.analysis | safe }}
            </div>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""


# 3. 报告生成函数
def generate_report(file_name, sections, global_summary):
    template = Template(HTML_TEMPLATE)
    html_content = template.render(
        title=file_name,
        sections=sections,
        global_summary=global_summary
    )
    output_path = f"{file_name}_report.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Report generated: {output_path}")