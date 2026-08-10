# Demo maps

Real InterMap exports, published through GitHub Pages so they can be opened in
a browser without downloading anything.

| File | What it shows |
|---|---|
| `sydney-cbd-soil-landscapes.html` | Seven map views over categorised soil landscape polygons and a clipped hillshade, with a full drawing title block. Public data, Sydney CBD. |

## Adding another demo

1. Export the map from QGIS as usual.
2. Drop the `.html` file in this folder with a short, lower-case, hyphenated
   name — that name becomes the public URL.
3. Add a card for it in `docs/index.html`.

Two things to check before committing:

- **Size.** GitHub rejects any file over 100 MB and warns above 50 MB, and a
  Pages site is capped at 1 GB. Exports embed their raster data, so a big
  hillshade or orthophoto grows the file quickly — keep a demo under ~20 MB so
  it stays quick to open.
- **Content.** The file is public the moment it is pushed. Check the title
  block, the layer names and the attribute tables for client or project detail
  that should not leave the office.

## Publishing

Pages serves this repository's `docs/` folder on the default branch — see
*Settings → Pages* (Source: *Deploy from a branch*, Branch: `main`, Folder:
`/docs`). `docs/.nojekyll` is there so the files are served exactly as
committed rather than being run through Jekyll.
