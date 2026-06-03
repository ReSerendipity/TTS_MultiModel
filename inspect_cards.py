"""
Playwright script to inspect IndexTTS 2.0 card headers and capture screenshots.
Uses timeout-based waits instead of networkidle for SPA compatibility.
"""
import json
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()

    # Collect console logs
    logs = []
    page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))

    # 1. Navigate to the app
    print("Navigating to http://127.0.0.1:7871...")
    page.goto("http://127.0.0.1:7871", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)

    # Initial screenshot
    page.screenshot(path="initial_page.png", full_page=True)
    print("Initial page screenshot saved to initial_page.png")

    # 2. Hard refresh (Ctrl+Shift+R)
    print("\nPerforming hard refresh (Ctrl+Shift+R)...")
    page.keyboard.press("Control+Shift+r")
    page.wait_for_timeout(4000)

    page.screenshot(path="after_refresh.png", full_page=True)
    print("After refresh screenshot saved")

    # 3. Click the IndexTTS 2.0 model tab
    print("\nLooking for IndexTTS 2.0 tab...")
    
    # First, dump all text content to understand page structure
    all_text = page.evaluate("() => document.body.innerText")
    print(f"Page text (first 500 chars): {all_text[:500]}")
    
    # Try multiple selectors for the tab
    tab_selectors = [
        'text=IndexTTS 2.0',
        'text="IndexTTS 2.0"',
        'text="IndexTTS"',
        '[role="tab"]:has-text("IndexTTS")',
        'button:has-text("IndexTTS")',
        'div:has-text("IndexTTS 2.0")',
    ]
    
    tab_clicked = False
    for sel in tab_selectors:
        try:
            tab = page.locator(sel).first
            if tab.count() > 0 and tab.is_visible():
                tab.click()
                print(f"Clicked IndexTTS 2.0 tab using selector: {sel}")
                tab_clicked = True
                break
        except Exception as e:
            continue
    
    if not tab_clicked:
        print("WARNING: Could not find IndexTTS 2.0 tab by text.")
        # Dump all buttons/tabs
        buttons = page.locator('button, [role="tab"], a, [class*="tab"]').all()
        for b in buttons[:20]:
            print(f"  Element: {b.text_content()}")
    
    page.wait_for_timeout(1500)
    page.screenshot(path="after_tts_tab.png", full_page=True)
    print("Screenshot after clicking IndexTTS 2.0 tab saved")

    # 4. Click sub-items and capture screenshots
    sub_items = [
        {"name": "语音克隆", "screenshot": "clone_icon.png"},
        {"name": "情感控制", "screenshot": "emotion_icon.png"},
        {"name": "时长控制", "screenshot": "duration_icon.png"},
    ]

    results = []

    for item in sub_items:
        print(f"\n--- Clicking '{item['name']}' ---")
        
        # Try multiple selectors for sub-item
        sub_selectors = [
            f'text="{item["name"]}"',
            f'text={item["name"]}',
            f'button:has-text("{item["name"]}")',
            f'div:has-text("{item["name"]}")',
            f'span:has-text("{item["name"]}")',
        ]
        
        clicked = False
        for sel in sub_selectors:
            try:
                locator = page.locator(sel).first
                if locator.count() > 0 and locator.is_visible():
                    locator.click()
                    print(f"Clicked '{item['name']}' using selector: {sel}")
                    clicked = True
                    break
            except:
                continue
        
        if not clicked:
            print(f"WARNING: Could not find '{item['name']}'")
            continue

        # Wait for content to load
        page.wait_for_timeout(500)

        # 5. Take screenshot of top card area
        # Try various card header selectors
        card_selectors = [
            '[class*="card-header"]',
            '[class*="cardHeader"]',
            '.v-card-title',
            '[class*="card"] > div:first-child',
            'header:has-text("' + item["name"] + '")',
        ]
        
        card_header_found = False
        for sel in card_selectors:
            card_header = page.locator(sel).first
            if card_header.count() > 0:
                # Screenshot the card header area
                card_header.screenshot(path=item["screenshot"])
                print(f"Screenshot saved to {item['screenshot']}")
                card_header_found = True
                break
        
        if not card_header_found:
            # Screenshot the full page and log DOM structure
            page.screenshot(path=item["screenshot"], full_page=True)
            print(f"No specific card header found. Full page screenshot saved to {item['screenshot']}")
            
            # Dump DOM structure around the clicked item for debugging
            body_html = page.evaluate("() => document.body.innerHTML")
            print(f"Body HTML length: {len(body_html)}")

        # 6. Get computed style of card-header-icon span
        icon_selectors = [
            '[class*="card-header-icon"]',
            '[class*="card-icon"]',
            '[class*="cardHeaderIcon"]',
            '.card-header-icon',
            'span[class*="icon"]',
            'div[class*="icon"]',
        ]
        
        icon_found = False
        for sel in icon_selectors:
            icons = page.locator(sel).all()
            if len(icons) > 0:
                icon = icons[0]
                style = icon.evaluate("el => JSON.stringify(getComputedStyle(el))")
                computed = json.loads(style)
                
                display = computed.get("display", "unknown")
                width = computed.get("width", "unknown")
                height = computed.get("height", "unknown")
                
                print(f"  Icon selector: {sel}")
                print(f"  card-header-icon span computed style:")
                print(f"    display: {display}")
                print(f"    width: {width}")
                print(f"    height: {height}")
                
                # 7. Check if SVG inside is visible
                svg = icon.locator("svg").first
                if svg.count() > 0:
                    svg_style = svg.evaluate("el => JSON.stringify(getComputedStyle(el))")
                    svg_computed = json.loads(svg_style)
                    svg_display = svg_computed.get("display", "unknown")
                    svg_width = svg_computed.get("width", "0px")
                    
                    # Parse width value
                    try:
                        w_val = float(svg_width.replace("px", ""))
                        is_visible = svg_display != "none" and w_val > 0
                    except:
                        is_visible = svg_display != "none"
                    
                    print(f"  SVG inside:")
                    print(f"    display: {svg_display}")
                    print(f"    width: {svg_width}")
                    print(f"    visible: {is_visible}")
                else:
                    # Check for other icon content (img, font icon, etc.)
                    img = icon.locator("img").first
                    if img.count() > 0:
                        print(f"  Found <img> inside icon (no SVG)")
                    font_icon = icon.locator('[class*="icon"], [class*="fa-"]').first
                    if font_icon.count() > 0:
                        print(f"  Found font icon inside span")
                    print(f"  No SVG found inside card-header-icon")
                
                results.append({
                    "item": item["name"],
                    "screenshot": item["screenshot"],
                    "icon_display": display,
                    "icon_width": width,
                    "icon_height": height,
                    "svg_display": svg_display if svg.count() > 0 else "not found",
                    "svg_visible": is_visible if svg.count() > 0 else None,
                })
                icon_found = True
                break
        
        if not icon_found:
            print(f"  No card-header-icon span found with any selector")
            results.append({
                "item": item["name"],
                "screenshot": item["screenshot"],
                "icon_display": "not found",
                "icon_width": "n/a",
                "icon_height": "n/a",
                "svg_display": "not found",
                "svg_visible": None,
            })

        page.wait_for_timeout(500)

    # 8. Print final summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    for r in results:
        print(f"\n{r['item']}:")
        print(f"  Screenshot: {r['screenshot']}")
        print(f"  card-header-icon display: {r['icon_display']}")
        print(f"  card-header-icon width: {r['icon_width']}")
        print(f"  card-header-icon height: {r['icon_height']}")
        print(f"  SVG display: {r['svg_display']}")
        print(f"  SVG visible: {r['svg_visible']}")

    browser.close()
    print("\nDone!")
