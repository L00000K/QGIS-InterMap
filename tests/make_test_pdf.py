"""Generate a small multi-page PDF with no dependencies (raw PDF syntax).

Used by tests to exercise the PDF report mode. Each page shows its page
number in large Helvetica text.
"""


def make_pdf(pages=3):
    objs = []

    def add(body):
        objs.append(body)
        return len(objs)  # 1-based object number

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    content_ids = []
    for i in range(1, pages + 1):
        text = ("BT /F1 36 Tf 72 700 Td (Page %d) Tj ET\n"
                "BT /F1 14 Tf 72 660 Td (InterMap PDF report test) Tj ET" % i)
        stream = text.encode("ascii")
        content_ids.append(add(
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)))

    # reserve page-tree object number after content objects
    pages_id = len(objs) + pages + 1
    page_ids = []
    for cid in content_ids:
        page_ids.append(add(
            (b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
             b"/Contents %d 0 R /Resources << /Font << /F1 %d 0 R >> >> >>"
             % (pages_id, cid, font))))
    kids = b" ".join(b"%d 0 R" % p for p in page_ids)
    real_pages_id = add(b"<< /Type /Pages /Kids [%s] /Count %d >>"
                        % (kids, pages))
    assert real_pages_id == pages_id
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += b"%010d 00000 n \n" % off
    out += (b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF"
            % (len(objs) + 1, catalog, xref_pos))
    return bytes(out)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "test.pdf"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    with open(path, "wb") as f:
        f.write(make_pdf(n))
    print("wrote", path, n, "pages")
