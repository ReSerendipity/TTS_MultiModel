# -*- coding: utf-8 -*-
"""Compare computed styles of key elements on voice_design page."""
import json
import os
from playwright.sync_api import sync_playwright

ROOT = r"c:\Users\HONOR\TTS_MultiModel"
OUTDIR = os.path.join(ROOT, "verification_output")
ACTUAL_URL = "http://127.0.0.1:7869/"
REPLICA_URL = "http://127.0.0.1:8765/tts_multimodel_replica.html"

SELECTORS = [
    ("body", ["fontSize", "lineHeight", "fontFamily", "color", "backgroundColor"]),
    (".sidebar", ["width", "minWidth", "backgroundColor", "padding", "borderRight"]),
    (".sidebar-brand", ["padding", "minHeight", "fontSize"]),
    (".sidebar-item", ["padding", "fontSize", "lineHeight", "color", "borderRadius"]),
    (".top-bar", ["height", "padding", "backgroundColor", "borderBottom"]),
    (".top-bar-title", ["fontSize", "fontWeight", "color"]),
    (".main-content", ["marginLeft", "padding", "backgroundColor"]),
    (".card", ["backgroundColor", "borderRadius", "padding", "boxShadow"]),
    (".btn-primary", ["backgroundColor", "color", "padding", "borderRadius", "fontSize"]),
    (".mini-monitor", ["padding", "borderRadius", "backgroundColor"]),
]


def get_styles(page, selector, props):
    return page.evaluate(f"""
        () => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return null;
            const s = getComputedStyle(el);
            const result = {{}};
            {json.dumps(props)}.forEach(p => result[p] = s[p]);
            result['offsetWidth'] = el.offsetWidth;
            result['offsetHeight'] = el.offsetHeight;
            return result;
        }}
    """)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})

        actual = context.new_page()
        actual.goto(ACTUAL_URL, wait_until="load", timeout=30000)
        actual.wait_for_timeout(1500)

        replica = context.new_page()
        replica.goto(REPLICA_URL, wait_until="load", timeout=30000)
        replica.wait_for_timeout(1500)

        results = []
        for selector, props in SELECTORS:
            a = get_styles(actual, selector, props)
            r = get_styles(replica, selector, props)
            same = a == r
            results.append({"selector": selector, "actual": a, "replica": r, "same": same})

        browser.close()

    report_path = os.path.join(OUTDIR, "style_compare_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 计算样式对比报告（voice_design 页面）\n\n")
        f.write("| 选择器 | 一致 | 实际 | 复刻 |\n")
        f.write("|--------|------|------|------|\n")
        for item in results:
            if item["actual"] is None or item["replica"] is None:
                f.write(f"| {item['selector']} | 无法对比 | `{item['actual']}` | `{item['replica']}` |\n")
            else:
                f.write(f"| {item['selector']} | {'是' if item['same'] else '否'} | `{item['actual']}` | `{item['replica']}` |\n")

    print(f"样式对比报告已保存: {report_path}")
    for item in results:
        print(f"  {item['selector']}: {'一致' if item['same'] else '不一致'}")


if __name__ == "__main__":
    main()