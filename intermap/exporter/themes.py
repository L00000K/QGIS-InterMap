"""Export colour themes for the generated web map UI."""


# ── Export themes ─────────────────────────────────────────────────────────────
# Each theme supplies CSS colour tokens that are injected as Python f-string
# variables into the HTML template. Keys:
#   hdr/hdr_bdr  panel header background / border
#   acc/acc_dk   primary accent / dark shade
#   acc_lt/md/ft light / mid / faint accent tints
#   pnl/pnl_a    panel background / alternate (slightly darker)
#   pnl_r        panel background as rgba(…) for semi-transparent panels
#   txt/txt2/txt3 primary / secondary / muted text
#   bdr/bdr2     border / light divider
#   map          map container background (visible while tiles load)
_THEMES = {
    "corporate": dict(
        hdr="#1e293b",       hdr_bdr="#0f172a",
        acc="#2563eb",       acc_dk="#1d4ed8",
        acc_lt="#dbeafe",    acc_md="#93c5fd",    acc_ft="#eff6ff",
        pnl="#ffffff",       pnl_a="#f8fafc",
        pnl_r="rgba(255,255,255,0.97)",
        txt="#1e293b",       txt2="#475569",       txt3="#94a3b8",
        bdr="#e2e8f0",       bdr2="#f1f5f9",
        map="#e8ecf0",
    ),
    "purple": dict(
        hdr="#3f32f1",       hdr_bdr="#2b22c0",
        acc="#3f32f1",       acc_dk="#2b22c0",
        acc_lt="#ede9fe",    acc_md="#d5cffc",    acc_ft="#f4f3fe",
        pnl="#ffffff",       pnl_a="#f8f7ff",
        pnl_r="rgba(255,255,255,0.97)",
        txt="#1a1a2e",       txt2="#555",          txt3="#888",
        bdr="#e2e0f0",       bdr2="#f0eff9",
        map="#eceaf8",
    ),
    "dark": dict(
        hdr="#0f172a",       hdr_bdr="#020617",
        acc="#60a5fa",       acc_dk="#93c5fd",
        acc_lt="#1e3a5f",    acc_md="#1e3a5f",    acc_ft="#0f2540",
        pnl="#1e293b",       pnl_a="#0f172a",
        pnl_r="rgba(30,41,59,0.97)",
        txt="#f1f5f9",       txt2="#cbd5e1",       txt3="#94a3b8",
        bdr="#334155",       bdr2="#1e293b",
        map="#0f172a",
    ),
}
