"""
Load exported HTML files in headless Chromium and report console errors.

Usage: python3 tests/browser_check.py <file.html> [file2.html ...]

Fails (exit 1) if any page throws an uncaught error or logs console errors,
excluding expected network failures (tile servers etc. are unreachable in CI).
"""
import sys
import os
from playwright.sync_api import sync_playwright

CHROMIUM = "/opt/pw-browsers/chromium"

# Errors caused purely by the sandbox having no internet (tile fetches, CDN
# fallbacks) are expected and not the app's fault.
_NETWORK_NOISE = (
    "net::ERR_", "Failed to load resource", "ERR_NAME_NOT_RESOLVED",
    "ERR_INTERNET_DISCONNECTED", "ERR_PROXY", "ERR_TUNNEL",
)


def check(path):
    errors = []
    with sync_playwright() as p:
        exe = CHROMIUM
        if os.path.isdir(exe):
            for root, _dirs, files in os.walk(exe):
                if "chrome" in files:
                    exe = os.path.join(root, "chrome")
                    break
        browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
        page = browser.new_page()
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                if m.type == "error" else None)
        page.goto("file://" + os.path.abspath(path),
                  wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        # Interact a little: map should exist
        has_map = page.evaluate("typeof L !== 'undefined' && !!document.getElementById('map')")
        browser.close()
    real = [e for e in errors if not any(n in e for n in _NETWORK_NOISE)]
    return has_map, real


def main(paths):
    failed = False
    for path in paths:
        has_map, errs = check(path)
        status = "OK" if (has_map and not errs) else "FAIL"
        if status == "FAIL":
            failed = True
        print(f"[{status}] {os.path.basename(path)}  leaflet+#map={has_map}  errors={len(errs)}")
        for e in errs[:10]:
            print(f"    {e}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
