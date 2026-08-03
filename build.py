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
import datetime
import os
import subprocess
import zipfile

PLUGIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "intermap")
METADATA = os.path.join(PLUGIN_DIR, "metadata.txt")

EXCLUDE_DIRS = {"__pycache__"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
EXCLUDE_FILES = set()


def read_version():
    cfg = configparser.ConfigParser()
    cfg.read(METADATA)
    return cfg["general"]["version"].strip()


def git_commit():
    """Short commit hash of the tree being built, or '' outside a checkout."""
    repo = os.path.dirname(os.path.abspath(__file__))
    try:
        res = subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5)
        if res.returncode != 0:
            return ""
        commit = res.stdout.strip()
        dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain"],
                               capture_output=True, text=True, timeout=5)
        if dirty.returncode == 0 and dirty.stdout.strip():
            commit += "+"          # built from a modified working tree
        return commit
    except Exception:
        return ""


def build_stamp_source(version):
    """Contents of intermap/_build.json, identifying this build.

    Written into the zip rather than onto disk, so building never dirties the
    working tree. The plugin falls back to querying git when it is absent.

    JSON rather than a generated module: a .py stamp can be shadowed by a
    stale .pyc when consecutive builds are the same byte length.
    """
    import json as _json
    return _json.dumps({
        "version": version,
        "commit": git_commit(),
        "built": datetime.date.today().isoformat(),
    }, indent=2) + "\n"


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
            if os.path.basename(abs_path) == "_build.json":
                continue          # regenerated below; never ship a stale one
            zf.write(abs_path, rel)
        zf.writestr(os.path.join(os.path.basename(PLUGIN_DIR), "_build.json"),
                    build_stamp_source(version))

    size_kb = os.path.getsize(zip_path) / 1024
    stamp = git_commit() or "no-git"
    print(f"Built: {zip_path}  ({size_kb:.1f} KB)  [{version} {stamp}]")
    return zip_path


def main():
    parser = argparse.ArgumentParser(description="Build InterMap plugin release zip")
    parser.add_argument("--out-dir", default="dist", help="Output directory (default: dist/)")
    args = parser.parse_args()
    build(args.out_dir)


if __name__ == "__main__":
    main()
