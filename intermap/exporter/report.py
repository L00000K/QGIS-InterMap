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


# Matches page objects ("/Type /Page") but not the page tree ("/Type /Pages").
_PDF_PAGE_RE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")


def _pdf_page_count(data: bytes) -> int:
    """Best-effort page count from raw PDF bytes. Returns 0 when the count
    cannot be determined (e.g. compressed object streams); callers must treat
    0 as "unknown", not "empty"."""
    return len(_PDF_PAGE_RE.findall(data))


def _parse_view_opts(s: str) -> dict:
    """Parse a binding options string like "3d pitch=-35 heading=120" into the
    opts dict the web app's applyView() accepts — the same grammar as the
    markdown ":::view Name [ ... ]" directive."""
    opts = {}
    for tok in (s or "").split():
        if tok == "3d":
            opts["mode3d"] = True
            continue
        if "=" in tok:
            key, _, val = tok.partition("=")
            try:
                opts[key] = float(val)
            except ValueError:
                pass
    return opts


def _build_pdf_report_payload(pdf_path, bindings, view_names) -> dict:
    """Read the report PDF and validate its page→view bindings. Returns the
    JSON-able payload for the export: the PDF as base64 plus normalised
    bindings [{page, view}] the web app drives scrollytelling from."""
    with open(pdf_path, "rb") as f:
        data = f.read()
    view_names = set(view_names)
    page_count = _pdf_page_count(data)

    warnings = []
    norm = []
    for b in bindings or []:
        try:
            page = int(b.get("page"))
        except (TypeError, ValueError):
            warnings.append(f"pdf binding has invalid page — {b!r}")
            continue
        view = str(b.get("view") or "").strip()
        if page < 1:
            warnings.append(f"pdf binding page {page} out of range")
            continue
        if page_count and page > page_count:
            warnings.append(
                f"pdf binding page {page} beyond last page ({page_count})")
        if view and view not in view_names:
            warnings.append(f"unknown map view in pdf binding — {view}")
        if view:
            entry = {"page": page, "view": view}
            opts = _parse_view_opts(str(b.get("opts") or ""))
            if opts:
                entry["opts"] = opts
            norm.append(entry)
    norm.sort(key=lambda b: b["page"])

    return {
        "title":    os.path.splitext(os.path.basename(pdf_path))[0],
        "pdf":      base64.b64encode(data).decode("ascii"),
        "pages":    page_count,
        "bindings": norm,
        "warnings": warnings,
    }
