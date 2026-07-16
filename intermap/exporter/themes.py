"""Export colour themes for the generated web map UI."""


# ── Export themes ─────────────────────────────────────────────────────────────
# Each theme supplies the colour tokens substituted into the page template
# (templates/*). Keys:
#   hdr/hdr_bdr  panel header background / border
#   acc/acc_dk   primary accent / dark shade
#   acc_lt/md    light / mid accent tints
#   pnl_r        panel background as rgba(…) for semi-transparent panels
# (An @15%-opacity accent for hover states is derived from acc at export.)
_THEMES = {
    "corporate": dict(
        hdr="#1e293b",       hdr_bdr="#0f172a",
        acc="#2563eb",       acc_dk="#1d4ed8",
        acc_lt="#dbeafe",    acc_md="#93c5fd",
        pnl_r="rgba(255,255,255,0.97)",
    ),
    "purple": dict(
        hdr="#3f32f1",       hdr_bdr="#2b22c0",
        acc="#3f32f1",       acc_dk="#2b22c0",
        acc_lt="#ede9fe",    acc_md="#d5cffc",
        pnl_r="rgba(255,255,255,0.97)",
    ),
    "dark": dict(
        hdr="#0f172a",       hdr_bdr="#020617",
        acc="#60a5fa",       acc_dk="#93c5fd",
        acc_lt="#1e3a5f",    acc_md="#1e3a5f",
        pnl_r="rgba(30,41,59,0.97)",
    ),
}
