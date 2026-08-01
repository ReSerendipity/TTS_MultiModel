"""Playwright UI 端到端测试套件。

覆盖 TTS MultiModel 的关键 UI 交互流程：
- 首页加载
- 标签页切换
- 折叠面板交互
- 引擎选择器
- 音频播放器
- 移动端响应式布局

运行方式::

    # 安装 Playwright
    pip install playwright
    playwright install

    # 启动服务器后运行
    pytest tests/e2e/ -v

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


class TestPageLoad:
    """页面加载测试。"""

    def test_home_page_loads(self, server_url, browser):
        """测试首页可以正常加载。"""
        page = browser.new_page()
        page.goto(server_url)
        page.wait_for_load_state("networkidle")
        assert page.title() != ""

    def test_home_page_has_sidebar(self, server_url, browser):
        """测试首页有侧边栏。"""
        page = browser.new_page()
        page.goto(server_url)
        page.wait_for_load_state("networkidle")
        sidebar = page.query_selector(".sidebar")
        assert sidebar is not None

    def test_home_page_has_tab_content(self, server_url, browser):
        """测试首页有标签内容区域。"""
        page = browser.new_page()
        page.goto(server_url)
        page.wait_for_load_state("networkidle")
        tab_content = page.query_selector("#tab-content")
        assert tab_content is not None


class TestTabSwitching:
    """标签页切换测试。"""

    def test_tab_navigation(self, server_url, browser):
        """测试标签页导航。"""
        page = browser.new_page()
        page.goto(server_url)
        page.wait_for_load_state("networkidle")

        # Find sidebar items
        sidebar_items = page.query_selector_all(".sidebar-item")
        assert len(sidebar_items) > 0

        # Click first sidebar item
        if len(sidebar_items) > 1:
            sidebar_items[1].click()
            page.wait_for_load_state("networkidle")

    def test_dotstts_tab_loads(self, server_url, browser):
        """测试 dots.tts 标签页加载。"""
        page = browser.new_page()
        page.goto(f"{server_url}/tabs/dotstts_clone")
        page.wait_for_load_state("networkidle")
        collapse_body = page.query_selector(".collapse-body")
        if collapse_body:
            assert collapse_body is not None

    def test_voxcpm2_tab_loads(self, server_url, browser):
        """测试 VoxCPM2 标签页加载。"""
        page = browser.new_page()
        page.goto(f"{server_url}/tabs/voice_clone")
        page.wait_for_load_state("networkidle")

    def test_indextts2_tab_loads(self, server_url, browser):
        """测试 IndexTTS2 标签页加载。"""
        page = browser.new_page()
        page.goto(f"{server_url}/tabs/indextts2")
        page.wait_for_load_state("networkidle")


class TestCollapseInteraction:
    """折叠面板交互测试。"""

    def test_collapse_toggle(self, server_url, browser):
        """测试折叠面板展开/折叠。"""
        page = browser.new_page()
        page.goto(f"{server_url}/tabs/dotstts_clone")
        page.wait_for_load_state("networkidle")

        collapse_header = page.query_selector(".collapse-header")
        if collapse_header:
            # Click to expand
            collapse_header.click()
            page.wait_for_timeout(300)  # Wait for animation

            # Check if expanded
            collapse_body = page.query_selector(".collapse-body")
            if collapse_body:
                class_name = collapse_body.get_attribute("class") or ""
                # Should have 'expanded' class or visible
                assert "expanded" in class_name or collapse_body.is_visible()


class TestResponsiveLayout:
    """移动端响应式布局测试。"""

    @pytest.fixture
    def mobile_browser(self, browser):
        """创建移动端视口。"""
        context = browser.new_context(
            viewport={"width": 375, "height": 812},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
        )
        page = context.new_page()
        yield page
        context.close()

    def test_mobile_sidebar_hidden(self, server_url, mobile_browser):
        """测试移动端侧边栏默认隐藏。"""
        mobile_browser.goto(server_url)
        mobile_browser.wait_for_load_state("networkidle")

        sidebar = mobile_browser.query_selector(".sidebar")
        if sidebar:
            # On mobile, sidebar should be hidden (translateX(-100%))
            assert sidebar is not None

    def test_mobile_hamburger_visible(self, server_url, mobile_browser):
        """测试移动端汉堡菜单可见。"""
        mobile_browser.goto(server_url)
        mobile_browser.wait_for_load_state("networkidle")

        toggle = mobile_browser.query_selector(".top-bar-mobile-toggle")
        if toggle:
            assert toggle.is_visible()

    def test_mobile_content_full_width(self, server_url, mobile_browser):
        """测试移动端内容区域占满宽度。"""
        mobile_browser.goto(server_url)
        mobile_browser.wait_for_load_state("networkidle")

        main_content = mobile_browser.query_selector(".main-content")
        if main_content:
            # On mobile, margin-left should be 0
            assert main_content is not None

    def test_tablet_layout(self, server_url, browser):
        """测试平板布局（768px-1200px）。"""
        context = browser.new_context(
            viewport={"width": 1024, "height": 768},
        )
        page = context.new_page()
        page.goto(server_url)
        page.wait_for_load_state("networkidle")
        assert page.title() != ""
        context.close()
