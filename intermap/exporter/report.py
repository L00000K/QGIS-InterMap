"""Report / story-mode: markdown front matter, figures, reference checks."""
import os
import re
import base64


_REPORT_IMG_RE = re.compile(r'!\[[^\]]*\]\(([^)\s]+)[^)]*\)')
_REPORT_MIME = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "svg": "image/svg+xml", "webp": "image/webp",
}


def _parse_front_matter(text: str) -> tuple:
    """Parse the report's leading front-matter block. Supports the limited
    schema this feature defines (title + autolink list) rather than general
    YAML, so no dependency is needed. Returns (meta dict, body markdown)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    header = text[3:end]
    body = text[end + 4:]
    if body.startswith("\n"):
        body = body[1:]
    meta: dict = {}
    autolink: list = []
    cur = None
    in_autolink = False
    for raw in header.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        s = raw.strip()
        if indent == 0:
            if ":" not in s:
                continue
            k, v = s.split(":", 1)
            k, v = k.strip(), v.strip().strip("\"'")
            if k == "autolink":
                in_autolink = True
            else:
                meta[k] = v
                in_autolink = False
        elif in_autolink:
            if s.startswith("- "):
                cur = {}
                autolink.append(cur)
                s = s[2:].strip()
            if cur is not None and ":" in s:
                k, v = s.split(":", 1)
                cur[k.strip()] = v.strip().strip("\"'")
    meta["autolink"] = [
        a for a in autolink
        if a.get("layer") and a.get("field") and a.get("pattern")
    ]
    return meta, body


def _report_image_refs(md: str) -> list:
    """Unique image paths referenced by the markdown, in order."""
    return list(dict.fromkeys(_REPORT_IMG_RE.findall(md)))


def _validate_report_refs(md: str, meta: dict, layer_names, view_names) -> list:
    """Cross-check the report's GIS references against what the export
    actually contains. Returns human-readable warnings for dead links."""
    warnings = []
    layer_names = set(layer_names)
    view_names = set(view_names)
    for m in re.finditer(r'^:::view[ \t]+(.+)$', md, re.M):
        name = re.sub(r'\[[^\]]*\]\s*$', '', m.group(1)).strip()
        if name and name not in view_names:
            warnings.append(f"unknown map view in :::view — {name}")
    for m in re.finditer(r'\]\(view:([^)]+)\)', md):
        name = m.group(1).strip()
        if name not in view_names:
            warnings.append(f"unknown map view in link — {name}")
    for m in re.finditer(r'\]\(gis:([^)?]+)\?', md):
        name = m.group(1).strip()
        if name not in layer_names:
            warnings.append(f"unknown layer in gis link — {name}")
    for m in re.finditer(r'^:::table\b[^\n]*?layer="?([^"\s{}]+)"?', md, re.M):
        name = m.group(1).strip()
        if name not in layer_names:
            warnings.append(f"unknown layer in :::table — {name}")
    for a in meta.get("autolink", []):
        if a["layer"] not in layer_names:
            warnings.append(f"autolink layer not in export — {a['layer']}")
    return warnings


def _build_report_payload(md_path, figures_dir, layer_names, view_names) -> dict:
    """Read the report markdown, embed its figures as data URIs, and validate
    its GIS references. Returns the JSON-able payload for the export."""
    with open(md_path, encoding="utf-8") as f:
        text = f.read()
    meta, body = _parse_front_matter(text)

    figures = {}
    warnings = []
    base_dirs = [d for d in (figures_dir, os.path.dirname(md_path)) if d]
    for ref in _report_image_refs(body):
        if ref.startswith(("http://", "https://", "data:")):
            continue
        found = None
        for d in base_dirs:
            for candidate in (os.path.join(d, ref),
                              os.path.join(d, os.path.basename(ref))):
                if os.path.isfile(candidate):
                    found = candidate
                    break
            if found:
                break
        if not found:
            warnings.append(f"figure file not found — {ref}")
            continue
        ext = os.path.splitext(found)[1].lower().lstrip(".")
        mime = _REPORT_MIME.get(ext, "application/octet-stream")
        with open(found, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        figures[ref] = f"data:{mime};base64,{b64}"

    warnings.extend(_validate_report_refs(body, meta, layer_names, view_names))
    return {
        "title":    meta.get("title", ""),
        "md":       body,
        "figures":  figures,
        "autolink": meta.get("autolink", []),
        "warnings": warnings,
    }
