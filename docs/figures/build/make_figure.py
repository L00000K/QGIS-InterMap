"""Screenshot the demo export and draw the annotated layout figure.

Run fig_fixture.py first. Needs Playwright with a Chromium build, and network
access for the OpenStreetMap tiles.

Control positions are read out of the live page rather than hard-coded, so
most UI changes are picked up automatically. Only the badge positions in
ITEMS below (where each label sits relative to its control) are manual.
"""
import base64
import os
import subprocess

from playwright.sync_api import sync_playwright

_HERE = os.path.dirname(os.path.abspath(__file__))
MAP_HTML = "file://" + os.path.join(_HERE, "fig_demo.html")
OUT_DIR = os.path.abspath(os.path.join(_HERE, ".."))
W, H = 1600, 1000

# Basemap opacity for the figure. Both this and the greyscale set in the
# fixture are genuine export settings, so the figure still shows a state a
# user could produce.
BASEMAP_OPACITY = 0.32


def chrome():
    """Locate a Chromium binary, or None to let Playwright use its own.

    PLAYWRIGHT_BROWSERS_PATH is set in the prebuilt images, where
    <root>/chromium may be either a directory or a symlink to the binary.
    """
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    candidate = os.path.join(root, "chromium")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    for base_dir in (candidate, root):
        if os.path.isdir(base_dir):
            for base, _dirs, files in os.walk(base_dir):
                if "chrome" in files:
                    return os.path.join(base, "chrome")
    return None


def _launch_kw(exe):
    """Only pin executable_path when we actually found one."""
    return {"executable_path": exe} if exe else {}


_tile_cache = {}


def _install_tile_proxy(page):
    """Serve OSM tiles via curl.

    Playwright's Chromium does not pick up the environment's HTTPS proxy, and
    OSM refuses requests without a descriptive User-Agent.
    """
    def fetch(url):
        if url not in _tile_cache:
            try:
                res = subprocess.run(
                    ["curl", "-sL", "--max-time", "25", "-A",
                     "InterMap-docs/1.0 (QGIS plugin documentation figure)", url],
                    capture_output=True, timeout=30)
                _tile_cache[url] = res.stdout if res.returncode == 0 else b""
            except Exception:
                _tile_cache[url] = b""
        return _tile_cache[url]

    def handler(route, request):
        body = fetch(request.url)
        if body:
            route.fulfill(status=200, body=body, headers={"content-type": "image/png"})
        else:
            route.abort()

    page.route("**://*.tile.openstreetmap.org/**", handler)
    page.route("**://tile.openstreetmap.org/**", handler)


# ── Annotation model ─────────────────────────────────────────────────────────
C = {1: "#E07B39", 2: "#2D7DD2", 3: "#2E9E5B", 4: "#7C5CBF"}

# (num, label, x, y, w, h, colour, tag x, tag y, right-align tag?)
ZONES = [
    ("1", "Map Information Panel", 0, 0, 301, 1000, C[1], 10, 500, False),
    ("2", "Tools", 303, 4, 48, 412, C[2], 305, 428, False),
    ("3", "Layers", 1404, 6, 190, 180, C[3], 1396, 8, True),
    ("4", "Canvas", 303, 4, 1293, 992, C[4], 1586, 700, True),
]

# (badge letter, zone, target rect, badge x, badge y, draw leader?)
ITEMS = [
    ("a", 1, (271, 11, 17, 20), 238, 10, True),
    ("b", 1, (8, 47, 284, 40), 238, 50, False),
    ("c", 1, (14, 93, 272, 111), 238, 97, False),
    ("d", 1, (14, 208, 272, 66), 238, 213, False),
    ("e", 1, (0, 565, 300, 435), 238, 572, False),
    ("i", 2, (313, 12, 30, 30), 360, 17, True),
    ("a", 2, (311, 54, 30, 30), 360, 59, True),
    ("b", 2, (311, 94, 30, 30), 360, 99, True),
    ("c", 2, (311, 134, 30, 30), 360, 139, True),
    ("d", 2, (311, 174, 30, 30), 360, 179, True),
    ("e", 2, (311, 214, 30, 30), 360, 219, True),
    ("f", 2, (313, 256, 30, 30), 360, 261, True),
    ("g", 2, (311, 298, 30, 30), 360, 303, True),
    ("j", 2, (313, 340, 30, 30), 360, 345, True),
    ("h", 2, (311, 382, 30, 30), 360, 387, True),
    ("a", 3, (1501, 19, 25, 19), 1428, 200, True),
    ("b", 3, (1530, 18, 49, 21), 1478, 200, True),
    ("c", 3, (1559, 77, 20, 18), 1528, 200, True),
    ("a", 4, (306, 961, 67, 34), 400, 966, True),
    ("c", 4, (311, 919, 179, 32), 510, 922, True),
    ("b", 4, (1366, 983, 234, 17), 1330, 972, True),
]

KEY = [
    (1, "Map Information Panel", [
        ("a", "Open / close button"),
        ("b", "Map information — title and description"),
        ("c", "Map views (dynamic) — shortcuts to preset views"),
        ("d", "Changelog — revision history (collapsible)"),
        ("e", "Title block — client, project and document control (collapsible)"),
    ]),
    (2, "Tools", [
        ("a", "Identify"),
        ("b", "Attribute table"),
        ("c", "Filter (by attributes)"),
        ("d", "Global search — filter all visible features by a search term"),
        ("e", "Measure"),
        ("f", "Download — export data to CSV or GeoJSON"),
        ("g", "Help — labels every tool on screen"),
        ("h", "Print — map with legend, scale bar and north arrow"),
        ("i", "2D / 3D view toggle"),
        ("j", "Sketch / annotate"),
    ]),
    (3, "Layers", [
        ("a", "Layer tools — reveals the per-layer buttons below"),
        ("b", "Show / hide all layers"),
        ("c", "Layer settings — opens the panel below"),
        ("d", "Attribute table for this layer"),
        ("e", "Filter this layer"),
        ("f", "Labels on / off"),
        ("g", "Explode / group overlapping points"),
        ("h", "Opacity"),
        ("i", "Labels — on / off and placement mode"),
        ("j", "Explode / group — on / off and spread or cluster"),
    ]),
    (4, "Canvas", [
        ("a", "Scale bar (metric and imperial)"),
        ("b", "Data attribution"),
        ("c", "Branding"),
    ]),
]

KEY_W, PAD = 560, 28
FIG_W = W + KEY_W + PAD * 3
FIG_H = H + PAD * 2 + 64 + 300


def capture(exe):
    """Screenshot the map, plus a detail capture of the expanded layers panel."""
    shots = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"], **_launch_kw(exe))

        page = browser.new_page(viewport={"width": W, "height": H},
                                device_scale_factor=2)
        _install_tile_proxy(page)
        page.goto(MAP_HTML, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(9000)
        page.add_style_tag(
            content=".basemap-tiles{opacity:%s !important;}" % BASEMAP_OPACITY)
        page.wait_for_timeout(600)
        shots["map"] = page.screenshot()
        page.close()

        # The per-layer buttons and settings panel only exist after clicking
        # the spanner and then a layer's cog, so they need their own capture.
        page = browser.new_page(viewport={"width": W, "height": H},
                                device_scale_factor=2)
        _install_tile_proxy(page)
        page.goto(MAP_HTML, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        page.evaluate("()=>{const t=document.getElementById('legend-tools-btn');"
                      " if(t)t.click();}")
        page.wait_for_timeout(300)
        page.evaluate("""()=>{const bh=[...document.querySelectorAll('.legend-layer')]
            .find(r=>/Boreholes/.test(r.textContent));
            bh.querySelector('.legend-cog-btn').click();}""")
        page.wait_for_timeout(700)
        shots["detail_geom"] = page.evaluate("""()=>{
          const lg=document.querySelector('#legend'); const L=lg.getBoundingClientRect();
          const rel=e=>{const b=e.getBoundingClientRect();
            return [Math.round(b.x-L.x),Math.round(b.y-L.y),
                    Math.round(b.width),Math.round(b.height)];};
          const bh=[...document.querySelectorAll('.legend-layer')]
                   .find(r=>/Boreholes/.test(r.textContent));
          const acts=[...bh.querySelectorAll('.layer-actions button')];
          const panel=[...document.querySelectorAll('.layer-settings')]
                      .find(e=>e.getBoundingClientRect().height>0);
          return {size:[Math.round(L.width),Math.round(L.height)],
                  acts:acts.map(rel), cog:rel(bh.querySelector('.legend-cog-btn')),
                  rows:[...panel.querySelectorAll('.layer-settings-row')].map(rel)};}""")
        shots["detail"] = page.locator("#legend").screenshot()
        page.close()
        browser.close()
    return shots


def build_html(shots):
    img_b64 = base64.b64encode(shots["map"]).decode()
    det_b64 = base64.b64encode(shots["detail"]).decode()
    detail = shots["detail_geom"]

    svg, badges = [], []
    for num, _name, x, y, w, h, col, _tx, _ty, _ra in ZONES:
        dash = ' stroke-dasharray="10 8" opacity="0.55"' if num == "4" else ""
        svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" '
                   f'stroke="{col}" stroke-width="3" rx="6"{dash}/>')

    for letter, zone, (tx, ty, tw, th), bx, by, leader in ITEMS:
        col = C[zone]
        svg.append(f'<rect x="{tx-3}" y="{ty-3}" width="{tw+6}" height="{th+6}" '
                   f'fill="none" stroke="{col}" stroke-width="2.5" rx="5" opacity="0.95"/>')
        if leader:
            svg.append(f'<line x1="{bx+13}" y1="{by+13}" x2="{tx+tw/2}" '
                       f'y2="{ty+th/2}" stroke="{col}" stroke-width="1.6" opacity="0.75"/>')
        badges.append(f'<div class="badge" style="left:{bx}px;top:{by}px;'
                      f'background:{col}">{zone}{letter}</div>')

    zone_tags = []
    for num, name, _x, _y, _w, _h, col, tgx, tgy, ralign in ZONES:
        shift = "translateX(-100%)" if ralign else "none"
        zone_tags.append(f'<div class="ztag" style="left:{tgx}px;top:{tgy}px;'
                         f'background:{col};transform:{shift}"><b>{num}</b>'
                         f'&nbsp; {name}</div>')

    key_html = []
    for zn, title, rows in KEY:
        col = C[zn]
        key_html.append(f'<div class="kgroup"><div class="khdr">'
                        f'<span class="kbadge" style="background:{col}">{zn}</span>'
                        f'<span class="ktitle" style="color:{col}">{title}</span></div>')
        for letter, text in rows:
            key_html.append(f'<div class="krow"><span class="kkey" style="color:{col};'
                            f'border-color:{col}">{zn}{letter}</span>'
                            f'<span class="ktext">{text}</span></div>')
        key_html.append("</div>")

    # Detail inset: zoomed capture of the expanded layers panel.
    zoom, band = 1.55, 40
    dw, dh = detail["size"]
    DW, DH = round(dw * zoom), round(dh * zoom)
    c3 = C[3]
    det_svg, det_badges = [], []

    def mark(letter, rect, bx, by):
        x, y, w, h = [v * zoom for v in rect]
        y += band
        det_svg.append(f'<rect x="{x-2:.0f}" y="{y-2:.0f}" width="{w+4:.0f}" '
                       f'height="{h+4:.0f}" fill="none" stroke="{c3}" '
                       f'stroke-width="2.2" rx="4"/>')
        det_svg.append(f'<line x1="{bx+11}" y1="{by+11}" x2="{x+w/2:.0f}" '
                       f'y2="{y+h/2:.0f}" stroke="{c3}" stroke-width="1.5" opacity="0.8"/>')
        det_badges.append(f'<div class="dbadge" style="left:{bx}px;top:{by}px;'
                          f'background:{c3}">3{letter}</div>')

    for letter, rect in zip("defgc", list(detail["acts"]) + [detail["cog"]]):
        mark(letter, rect, round((rect[0] + rect[2] / 2) * zoom - 11), 6)
    for letter, rect in zip("hij", detail["rows"]):
        mark(letter, rect, 4, round((rect[1] + rect[3] / 2) * zoom + band - 11))

    det_html = (
        f'<div class="detail"><div class="dhdr">Layer tools &amp; settings '
        f'<span>— these appear only after clicking <b>3a</b>, then <b>3c</b></span></div>'
        f'<div class="dwrap" style="width:{DW}px;height:{DH + band}px">'
        f'<img src="data:image/png;base64,{det_b64}" '
        f'style="width:{DW}px;height:{DH}px;top:{band}px">'
        f'<svg viewBox="0 0 {DW} {DH + band}" width="{DW}" height="{DH + band}">'
        f'{"".join(det_svg)}</svg>{"".join(det_badges)}</div></div>'
    )

    return f"""<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#F4F5F7;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif; }}
  .fig {{ width:{FIG_W}px; height:{FIG_H}px; padding:{PAD}px; display:flex; gap:{PAD}px; }}
  .mapwrap {{ position:relative; width:{W}px; height:{H}px; flex:0 0 auto;
              box-shadow:0 2px 14px rgba(0,0,0,0.16); border-radius:4px; overflow:hidden; }}
  .mapwrap img {{ width:{W}px; height:{H}px; display:block; }}
  .mapwrap svg {{ position:absolute; inset:0; }}
  .badge {{ position:absolute; width:26px; height:26px; border-radius:50%;
            color:#fff; font-size:12.5px; font-weight:700; line-height:26px;
            text-align:center; box-shadow:0 1px 4px rgba(0,0,0,0.35); }}
  .ztag {{ position:absolute; color:#fff; font-size:12.5px; font-weight:600;
           padding:4px 10px; border-radius:4px; white-space:nowrap;
           box-shadow:0 1px 4px rgba(0,0,0,0.3); }}
  .key {{ width:{KEY_W}px; }}
  .kh {{ font-size:20px; font-weight:700; color:#1F2430; margin:0 0 2px; }}
  .ksub {{ font-size:12px; color:#6B7280; margin:0 0 16px; }}
  .kgroup {{ margin-bottom:14px; }}
  .khdr {{ display:flex; align-items:center; gap:8px; margin-bottom:5px; }}
  .kbadge {{ width:22px; height:22px; border-radius:50%; color:#fff; font-size:12px;
             font-weight:700; line-height:22px; text-align:center; }}
  .ktitle {{ font-size:14.5px; font-weight:700; }}
  .krow {{ display:flex; gap:8px; padding:2.5px 0 2.5px 30px; align-items:baseline; }}
  .kkey {{ flex:0 0 26px; font-size:11px; font-weight:700; text-align:center;
           border:1.5px solid; border-radius:4px; padding:0 3px; }}
  .ktext {{ font-size:12.5px; color:#333; line-height:1.45; }}
  .foot {{ margin-top:10px; font-size:11px; color:#8A8F98; }}
  .detail {{ margin-top:16px; padding-top:14px; border-top:1px solid #DDE0E5; }}
  .dhdr {{ font-size:13px; font-weight:700; color:{C[3]}; margin-bottom:8px; }}
  .dhdr span {{ font-weight:400; color:#6B7280; font-size:11.5px; }}
  .dwrap {{ position:relative; margin-left:46px; }}
  .dwrap img {{ display:block; border-radius:4px; position:absolute; left:0; }}
  .dwrap svg {{ position:absolute; inset:0; }}
  .dbadge {{ position:absolute; width:22px; height:22px; border-radius:50%;
             color:#fff; font-size:11px; font-weight:700; line-height:22px;
             text-align:center; box-shadow:0 1px 3px rgba(0,0,0,0.35); }}
</style>
<div class="fig">
  <div class="mapwrap">
    <img src="data:image/png;base64,{img_b64}">
    <svg viewBox="0 0 {W} {H}" width="{W}" height="{H}">{''.join(svg)}</svg>
    {''.join(zone_tags)}{''.join(badges)}
  </div>
  <div class="key">
    <p class="kh">InterMap — exported web map layout</p>
    <p class="ksub">Zones and controls of the self-contained HTML map package</p>
    {''.join(key_html)}
    <p class="foot">Controls shown are those enabled at export; any tool can be
    switched off under Map tools, in which case its button does not appear.</p>
    {det_html}
  </div>
</div>"""


def main():
    exe = chrome()
    if not os.path.exists(os.path.join(_HERE, "fig_demo.html")):
        raise SystemExit("fig_demo.html missing — run fig_fixture.py first.")

    page_html = build_html(capture(exe))
    page_path = os.path.join(_HERE, "figure.html")
    with open(page_path, "w", encoding="utf-8") as fh:
        fh.write(page_html)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"], **_launch_kw(exe))
        for name, scale in (("webmap-layout.png", 1), ("webmap-layout@2x.png", 2)):
            page = browser.new_page(viewport={"width": FIG_W, "height": FIG_H},
                                    device_scale_factor=scale)
            page.goto("file://" + page_path, wait_until="load", timeout=60000)
            page.wait_for_timeout(1200)
            out = os.path.join(OUT_DIR, name)
            page.locator(".fig").screenshot(path=out)
            print("wrote", out, os.path.getsize(out) // 1024, "KB")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
