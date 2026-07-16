"""
Assemble the exported web page from the template files in templates/.

The template parts are plain HTML/CSS/JS with @@name@@ placeholders;
render_page() substitutes them in a single pass, so placeholder-like text
inside substituted values is never re-processed.
"""
import os
import re

_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")

# Concatenated in this order (with the glue markup below) the parts form the
# complete page. They are kept separate so the CSS and each JS block can be
# read and edited as ordinary files.
_PARTS = ("head.html", "webmap.css", "body.html", "app.js", "cesium.js", "report.js")

_PLACEHOLDER_RE = re.compile(r"@@([A-Za-z_][A-Za-z0-9_]*)@@")

_template_cache = None


def _read(name: str) -> str:
    path = os.path.join(_TEMPLATE_DIR, name)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    # Each part file carries a conventional trailing newline that is not part
    # of the page; the glue strings below supply the real separators.
    return text[:-1] if text.endswith("\n") else text


def _page_template() -> str:
    global _template_cache
    if _template_cache is None:
        head, css, body, app_js, cesium_js, report_js = (_read(p) for p in _PARTS)
        _template_cache = (
            head
            + "\n<style>\n" + css
            + "\n</style>\n</head>\n<body>\n" + body
            + "\n<script>\n" + app_js
            + "\n" + cesium_js
            + "\n" + report_js
            + "\n</script>\n</body>\n</html>"
        )
    return _template_cache


def render_page(ctx: dict) -> str:
    """Substitute @@placeholders@@ in the page template from ctx."""

    def _sub(m):
        name = m.group(1)
        if name not in ctx:
            raise KeyError("template placeholder missing from context: %s" % name)
        return format(ctx[name], "")

    return _PLACEHOLDER_RE.sub(_sub, _page_template())
