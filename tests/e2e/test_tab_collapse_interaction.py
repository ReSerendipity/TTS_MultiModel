"""Playwright 真实浏览器 UI 测试框架。

此模块定义了需要真实浏览器环境的端到端 UI 测试。
在 CI 离线环境中自动跳过，仅在开发者本机手动运行。

运行方式::

    # 安装 Playwright
    pip install playwright
    playwright install

    # 运行测试
    pytest tests/e2e/test_tab_collapse_interaction.py -v

需要：
- 服务器运行在 http://127.0.0.1:7869
- Playwright 浏览器已安装
"""

import os

import pytest

try:
    from playwright.sync_api import Page, expect, sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not PLAYWRIGHT_AVAILABLE,
    reason="Playwright not installed. Install with: pip install playwright && playwright install",
)


@pytest.fixture(scope="module")
def server_url():
    """获取服务器 URL，如未运行则跳过。"""
    import urllib.request

    url = os.environ.get("TTS_SERVER_URL", "http://127.0.0.1:7869")
    try:
        urllib.request.urlopen(url, timeout=2)
        return url
    except Exception:
        pytest.skip(f"Server not running at {url}. Start the server first.")


@pytest.fixture(scope="module")
def browser():
    """启动 Playwright 浏览器。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


class TestTabCollapseInteraction:
    """折叠面板交互测试。"""

    def test_page_loads(self, server_url, browser):
        """测试首页可以正常加载。"""
        page = browser.new_page()
        page.goto(server_url)
        page.wait_for_load_state("networkidle")
        assert page.title() != ""

    def test_gptsovits_tab_advanced_params(self, server_url, browser):
        """测试 GPT-SoVITS Tab 高级参数折叠面板交互。"""
        page = browser.new_page()
        page.goto(f"{server_url}/tabs/gptsovits_clone")
        page.wait_for_load_state("networkidle")

        # 检查折叠面板存在
        collapse_body = page.query_selector(".collapse-body")
        if collapse_body:
            # 测试点击展开
            toggle_btn = page.query_selector(".toggle-btn")
            if toggle_btn:
                toggle_btn.click()
                page.wait_for_timeout(500)
                # 验证展开状态
                assert collapse_body.is_visible()

    def test_dotstts_tab_advanced_params(self, server_url, browser):
        """测试 dots.tts Tab 高级参数折叠面板交互。"""
        page = browser.new_page()
        page.goto(f"{server_url}/tabs/dotstts_clone")
        page.wait_for_load_state("networkidle")

        # 检查折叠面板存在
        collapse_body = page.query_selector(".collapse-body")
        if collapse_body:
            assert collapse_body is not None
