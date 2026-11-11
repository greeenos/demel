from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
svg = (root / "public/icon.svg").read_text().replace('<svg ', '<svg width="100%" height="100%" ')
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for size, name in ((192, 'icon-192.png'), (512, 'icon-512.png'), (180, 'apple-touch-icon.png')):
        page = browser.new_page(viewport={"width": size, "height": size}, device_scale_factor=1)
        page.set_content('<html><body style="margin:0;width:100vw;height:100vh">' + svg + '</body></html>')
        page.wait_for_timeout(200)
        page.screenshot(path=str(root / "public" / name), omit_background=False)
        page.close()
    browser.close()
print("PWA icons exported from source SVG.")
