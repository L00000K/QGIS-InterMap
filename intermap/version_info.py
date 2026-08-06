"""Plugin version, build stamp and changelog.

metadata.txt is the single source of truth for both the version and the
changelog, so there is nothing extra to keep in step when releasing.

The build stamp identifies the exact commit a build came from. It is written
into the zip by build.py; in a git checkout it is derived from git instead, so
a developer install still shows what it is running.
"""
import configparser
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_METADATA = os.path.join(_HERE, "metadata.txt")


def _general():
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(_METADATA, encoding="utf-8")
    return cfg["general"]


def version():
    """Version string from metadata.txt, or '?' if it cannot be read."""
    try:
        return _general().get("version", "").strip() or "?"
    except Exception:
        return "?"


def build_stamp():
    """{'commit', 'date', 'source'} for this build, or None if unavailable.

    source is 'build' for an installed zip stamped by build.py, or 'git' when
    running straight from a checkout. They are treated differently when
    deciding whether to show the what's-new window.
    """
    # A data file, not an importable module: a generated .py can be shadowed by
    # a stale .pyc when a new build happens to be the same byte length.
    try:
        with open(os.path.join(_HERE, "_build.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("commit"):
            return {"commit": data["commit"], "date": data.get("built", ""),
                    "source": "build"}
    except Exception:
        pass
    # Developer install straight from a checkout — ask git.
    try:
        import subprocess
        repo = os.path.dirname(_HERE)
        if os.path.isdir(os.path.join(repo, ".git")):
            res = subprocess.run(
                ["git", "-C", repo, "log", "-1", "--format=%h|%cs"],
                capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and "|" in res.stdout:
                commit, date = res.stdout.strip().split("|", 1)
                return {"commit": commit, "date": date, "source": "git"}
    except Exception:
        pass
    return None


def version_label():
    """Short label for the dialog header, e.g. 'v1.9.0 · 40675b6'."""
    label = "v" + version()
    stamp = build_stamp()
    if stamp and stamp.get("commit"):
        label += "  ·  " + stamp["commit"]
    return label


def install_identity():
    """String identifying this installation, for update detection.

    An installed zip includes its commit, so every new build counts as an
    update. A checkout does not — otherwise the hot-reload workflow would pop
    the changelog on every commit while developing.
    """
    stamp = build_stamp()
    if stamp and stamp.get("source") == "build" and stamp.get("commit"):
        return "{}+{}".format(version(), stamp["commit"])
    return version()


def commit_log(limit=40):
    """Commits behind this build, newest first: [{'commit','date','subject'}].

    An installed zip carries the list baked in by build.py, so it works with no
    checkout and no network. Running from a checkout, git is asked directly and
    the answer is always current.
    """
    try:
        with open(os.path.join(_HERE, "_build.json"), encoding="utf-8") as fh:
            commits = json.load(fh).get("commits") or []
        if commits:
            return commits[:limit]
    except Exception:
        pass
    try:
        import subprocess
        repo = os.path.dirname(_HERE)
        if os.path.isdir(os.path.join(repo, ".git")):
            res = subprocess.run(
                ["git", "-C", repo, "log", "--no-merges", "-n", str(limit),
                 "--format=%h\x1f%cs\x1f%s"],
                capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                out = []
                for line in res.stdout.splitlines():
                    parts = line.split("\x1f", 2)
                    if len(parts) == 3:
                        out.append({"commit": parts[0], "date": parts[1],
                                    "subject": parts[2]})
                return out
    except Exception:
        pass
    return []


def changelog_entries():
    """Parse metadata.txt's changelog into [(version, text)], newest first.

    Entries look like:
        changelog=
            1.9.0 - did a thing; did another thing
            1.8.0 - ...
    Continuation lines that do not start with a version are appended to the
    entry above, so wrapped text survives.
    """
    try:
        raw = _general().get("changelog", "") or ""
    except Exception:
        return []

    entries = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        head, sep, tail = line.partition(" - ")
        token = head.strip()
        is_version = sep and token and all(
            part.isdigit() for part in token.split(".") if part != "")
        if is_version:
            entries.append((token, tail.strip()))
        elif entries:
            entries[-1] = (entries[-1][0], (entries[-1][1] + " " + line).strip())
    return entries
