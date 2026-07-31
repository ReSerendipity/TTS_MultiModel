#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""UI/UX Optimization Verification Script - Playwright-based"""
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

# Configuration
BASE_URL = "http://127.0.0.1:7869"
SCREENSHOT_DIR = Path(__file__).parent.parent / "docs" / "screenshots" / "ui_audit"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# Viewport configurations
VIEWPORTS = [
    {"width": 1920, "height": 1080, "name": "1920x1080"},
    {"width": 1440, "height": 900, "name": "1440x900"},
    {"width": 1280, "height": 800, "name": "1280x800"},
]

# Key pages to capture
PAGES = [
    {"path": "/", "name": "home_voice_design", "label": "首页-语音设计"},
]

# Sidebar items mapping (text -> tab identifier)
SIDEBAR_ITEMS = [
    ("语音设计", "voice_design"),
    ("语音克隆", "voice_clone"),
    ("终极克隆", "ultimate_clone"),
    ("剧本工坊", "script"),
    ("设置", "settings"),
    ("帮助", "help"),
]

def log(msg):
    print(f"[UI Verify] {msg}")

def take_fullpage_screenshot(page, filename, viewport_name):
    """Take full page screenshot with cache-busting"""
    filepath = SCREENSHOT_DIR / f"{viewport_name}_{filename}.png"
    page.screenshot(path=str(filepath), full_page=True)
    log(f"  Screenshot saved: {filepath.name}")
    return filepath

def wait_for_content(page):
    """Wait for page content to load"""
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except:
        pass
    page.wait_for_timeout(500)

def dismiss_onboarding(page):
    """Dismiss any onboarding/intro overlays"""
    try:
        # Try to find and click "Skip" or "Got it" buttons
        for text in ["跳过", "Skip", "知道了", "Got it", "关闭"]:
            btn = page.get_by_role("button", name=text)
            if btn.is_visible(timeout=1000):
                btn.click()
                page.wait_for_timeout(300)
                log(f"  Dismissed onboarding via '{text}' button")
                return True
    except:
        pass
    
    # Try removing overlay via JS
    try:
        page.evaluate("""() => {
            const overlays = document.querySelectorAll('.onboarding-overlay, .introjs-overlay, [class*="intro"], [class*="onboard"]');
            overlays.forEach(el => el.remove());
            return true;
        }""")
        log("  Removed onboarding overlay via JS")
    except:
        pass
    return True

def expand_sidebar(page):
    """Ensure sidebar is expanded"""
    try:
        # Check if sidebar is collapsed
        is_collapsed = page.evaluate("""() => {
            const sidebar = document.getElementById('sidebar');
            return sidebar ? sidebar.classList.contains('collapsed') : false;
        }""")
        
        if is_collapsed:
            # Try clicking toggle button
            toggle = page.locator("#sidebar-toggle, [title*='sidebar'], [aria-label*='sidebar']").first
            if toggle.is_visible(timeout=1000):
                toggle.click()
                page.wait_for_timeout(300)
                log("  Expanded sidebar via toggle button")
            else:
                # Force expand via JS
                page.evaluate("""() => {
                    const sidebar = document.getElementById('sidebar');
                    if (sidebar) sidebar.classList.remove('collapsed');
                    const mainContent = document.querySelector('.main-content');
                    if (mainContent) mainContent.style.marginLeft = '';
                }""")
                log("  Expanded sidebar via JS")
        else:
            log("  Sidebar already expanded")
    except Exception as e:
        log(f"  Sidebar handling note: {e}")

def verify_sidebar_active_state(page):
    """Verify sidebar active state styling is applied"""
    try:
        # Check that active sidebar item has the enhanced styles
        has_active_styles = page.evaluate("""() => {
            const activeItem = document.querySelector('.sidebar-item.active');
            if (!activeItem) return { found: false };
            
            const style = window.getComputedStyle(activeItem);
            const beforeStyle = window.getComputedStyle(activeItem, '::before');
            
            return {
                found: true,
                hasBoxShadow: style.boxShadow !== 'none',
                fontWeight: style.fontWeight,
                hasTransform: style.transform !== 'none',
                hasBeforeContent: beforeStyle.content !== 'none' && beforeStyle.content !== '',
                color: style.color,
            };
        }""")
        log(f"  Sidebar active state check: {has_active_styles}")
        return has_active_styles
    except Exception as e:
        log(f"  Sidebar style check error: {e}")
        return None

def verify_progress_bar_styles(page):
    """Verify progress bar has smooth transition styles"""
    try:
        styles = page.evaluate("""() => {
            const fills = document.querySelectorAll('.tts-progress-fill');
            if (fills.length === 0) return { found: false };
            const fill = fills[0];
            const style = window.getComputedStyle(fill);
            return {
                found: true,
                transition: style.transition,
                willChange: style.willChange,
            };
        }""")
        log(f"  Progress bar styles: {styles}")
        return styles
    except Exception as e:
        log(f"  Progress style check error: {e}")
        return None

def verify_scroll_padding(page):
    """Verify tab-content has scroll-padding-top set"""
    try:
        scroll_padding = page.evaluate("""() => {
            const tabContent = document.getElementById('tab-content');
            if (!tabContent) return null;
            const style = window.getComputedStyle(tabContent);
            return {
                scrollPaddingTop: style.scrollPaddingTop,
                scrollBehavior: style.scrollBehavior,
                overflowY: style.overflowY,
            };
        }""")
        log(f"  Scroll padding check: {scroll_padding}")
        return scroll_padding
    except Exception as e:
        log(f"  Scroll padding check error: {e}")
        return None

def main():
    log("=" * 60)
    log("UI/UX Optimization Verification")
    log("=" * 60)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        results = {"pages": {}, "viewports": [], "verifications": {}}
        
        for viewport in VIEWPORTS:
            log(f"\n--- Testing viewport: {viewport['name']} ---")
            context = browser.new_context(
                viewport={"width": viewport["width"], "height": viewport["height"]},
                locale="zh-CN",
                bypass_csp=True,
            )
            # Disable cache to get fresh assets
            context.set_default_navigation_timeout(15000)
            
            page = context.new_page()
            
            # Navigate with cache-busting
            log(f"Navigating to {BASE_URL}...")
            page.goto(f"{BASE_URL}/?v={int(time.time())}", wait_until="domcontentloaded")
            wait_for_content(page)
            
            # Dismiss onboarding
            dismiss_onboarding(page)
            wait_for_content(page)
            
            # Expand sidebar
            expand_sidebar(page)
            wait_for_content(page)
            
            # Take homepage screenshot
            take_fullpage_screenshot(page, "after_home", viewport["name"])
            
            # Run verifications on first viewport only
            if viewport["name"] == "1920x1080":
                log("\nRunning CSS/JS verifications...")
                results["verifications"]["sidebar_active"] = verify_sidebar_active_state(page)
                results["verifications"]["progress_styles"] = verify_progress_bar_styles(page)
                results["verifications"]["scroll_padding"] = verify_scroll_padding(page)
            
            # Navigate through key sidebar items
            for item_text, item_id in SIDEBAR_ITEMS:
                try:
                    log(f"  Navigating to: {item_text}")
                    # Find sidebar item by text
                    item = page.locator(f".sidebar-item:has-text('{item_text}')").first
                    if item.is_visible(timeout=2000):
                        item.click()
                        wait_for_content(page)
                        take_fullpage_screenshot(page, f"after_{item_id}", viewport["name"])
                    else:
                        log(f"    Sidebar item not found: {item_text}")
                except Exception as e:
                    log(f"    Error navigating to {item_text}: {e}")
            
            context.close()
            results["viewports"].append(viewport["name"])
        
        browser.close()
        
        log("\n" + "=" * 60)
        log("Verification Summary")
        log("=" * 60)
        for key, value in results["verifications"].items():
            log(f"  {key}: {value}")
        log(f"\nScreenshots saved to: {SCREENSHOT_DIR}")
        log("Verification complete!")

if __name__ == "__main__":
    main()
