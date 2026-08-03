# Figures

## `webmap-layout.png` / `webmap-layout@2x.png`

Annotated layout of the exported web map: the four zones (map information
panel, tools, layers, canvas) with every control numbered and keyed, plus a
detail inset for the layer tools and settings panel — controls that only
appear after clicking the layer-tools spanner and then a layer's cog.

Both files are the same figure. Use `webmap-layout.png` (2244 x 1420) for
documents and email; `webmap-layout@2x.png` (4488 x 2840) is for print or
where it will be zoomed.

The figure is a real screenshot of an export, not a mock-up. The basemap is
rendered greyscale at reduced opacity so the data and annotations read
clearly; both of those are genuine export settings rather than image editing.

Regenerate after a UI change rather than editing the image — see
"Regenerating" below.

## Regenerating

The figure is produced by two scripts kept outside the plugin package, since
they are documentation tooling and are not shipped in the plugin zip:

    docs/figures/build/fig_fixture.py   # builds a demo export to screenshot
    docs/figures/build/make_figure.py   # screenshots it and draws the annotations

They need Playwright and a Chromium build, and network access for the
OpenStreetMap tiles:

    python3 -m pip install playwright
    python3 docs/figures/build/fig_fixture.py
    python3 docs/figures/build/make_figure.py

`make_figure.py` reads the control positions out of the live page rather than
hard-coding them, so most UI changes are picked up automatically. Coordinates
that anchor a badge to a specific control are listed at the top of the file
and may need adjusting if a panel is restructured.
