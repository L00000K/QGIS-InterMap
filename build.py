#!/usr/bin/env python3
"""
Build a QGIS-installable zip release of the InterMap plugin.

Usage:
    python3 build.py [--out-dir DIR]

Output:
    dist/intermap-<version>.zip  (default)

The zip contains an `intermap/` root folder so QGIS can install it directly
via Plugins → Install from ZIP.
"""

import argparse
import configparser
import os
import sys
import zipfile

PLUGIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intermap")
METADATA = os.path.join(PLUGIN_DIR, "metadata.txt")

EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
EXCLUDE_FILES = {"test_exporter_logic.py"}


def read_version():
    cfg = configparser.ConfigParser()
    cfg.read(METADATA)
    return cfg["general"]["version"].strip()


def iter_plugin_files(plugin_dir):
    for root, dirs, files in os.walk(plugin_dir):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for fname in sorted(files):
            if fname in EXCLUDE_FILES:
                continue
            if any(fname.endswith(s) for s in EXCLUDE_SUFFIXES):
                continue
            yield os.path.join(root, fname)


def build(out_dir):
    version = read_version()
    zip_name = f"intermap-{version}.zip"
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, zip_name)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for abs_path in iter_plugin_files(PLUGIN_DIR):
            # arcname keeps the `intermap/` prefix so QGIS sees the right folder
            rel = os.path.relpath(abs_path, os.path.dirname(PLUGIN_DIR))
            zf.write(abs_path, rel)

    size_kb = os.path.getsize(zip_path) / 1024
    print(f"Built: {zip_path}  ({size_kb:.1f} KB)")
    return zip_path


def main():
    parser = argparse.ArgumentParser(description="Build InterMap plugin release zip")
    parser.add_argument("--out-dir", default="dist", help="Output directory (default: dist/)")
    args = parser.parse_args()
    build(args.out_dir)


if __name__ == "__main__":
    main()
