"""Changelog window, and the check that pops it up after an update."""
import html

from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
)

from .dialog.constants import _SETTINGS_KEY, _PURPLE
from . import version_info

_LAST_SEEN_KEY = f"{_SETTINGS_KEY}/last_seen_build"


def _commits_html(since_commit=None):
    """Individual pushes, newest first, under the released-version summary.

    The version entries say what a release is for; this says what actually
    landed and when. `since_commit` marks everything newer than the build the
    user last had, so an update shows exactly what it brought.
    """
    commits = version_info.commit_log()
    if not commits:
        return ""

    parts = ["<h3 class='current'>Recent pushes</h3>"]
    marking = bool(since_commit) and any(
        c.get("commit") == since_commit for c in commits)
    last_date = None
    for c in commits:
        commit = c.get("commit", "")
        if marking and commit == since_commit:
            marking = False       # reached the build they already had
            parts.append("<p class='seen'>&mdash; already installed &mdash;</p>")
        date = c.get("date", "") or ""
        if date != last_date:
            parts.append("<p class='cdate'>{}</p>".format(html.escape(date)))
            last_date = date
        parts.append(
            "<p class='commit'>{}<span class='sha'>{}</span> {}</p>".format(
                "<span class='new'>NEW</span> " if marking else "",
                html.escape(commit), html.escape(c.get("subject", ""))))
    return "".join(parts)


def _changelog_html(highlight=None, since_commit=None):
    entries = version_info.changelog_entries()
    stamp = version_info.build_stamp()

    parts = [
        "<style>"
        "  body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 12px; color: #222; }"
        f" h3 {{ color: {_PURPLE}; font-size: 13px; margin: 16px 0 3px; }}"
        "  h3.current { margin-top: 4px; }"
        f" h4 {{ color: {_PURPLE}; font-size: 12px; margin: 10px 0 3px; }}"
        "  .new { background: #FFF3C4; border-radius: 3px; padding: 1px 6px;"
        "         font-size: 10px; font-weight: 700; color: #7A5B00; }"
        "  p { margin: 0 0 4px; line-height: 1.5; }"
        "  .meta { color: #6B7280; font-size: 11px; }"
        "  .cdate { color: #6B7280; font-size: 10px; font-weight: 700;"
        "           margin: 8px 0 2px; }"
        "  .commit { margin: 0 0 2px 10px; line-height: 1.45; }"
        "  .sha { color: #6B7280; font-family: Consolas, monospace;"
        "         font-size: 11px; margin-right: 6px; }"
        "  .seen { color: #9AA0AA; font-size: 10px; margin: 8px 0 2px; }"
        "</style>"
    ]

    if stamp:
        parts.append(
            "<p class='meta'>Build {} &middot; {}</p>".format(
                html.escape(stamp.get("commit", "")),
                html.escape(stamp.get("date", "") or "")))

    # Pushes first: what landed most recently is what someone opening this
    # window after an update wants to see. The release notes below say what a
    # version is for, which is the slower-moving half of the story.
    parts.append(_commits_html(since_commit))

    if not entries:
        parts.append("<p>No changelog entries found in metadata.txt.</p>")
    else:
        parts.append("<h3>Release notes</h3>")

    for idx, (ver, text) in enumerate(entries):
        badge = " <span class='new'>NEW</span>" if ver == highlight else ""
        cls = ""
        parts.append("<h4{}>{}{}</h4>".format(cls, html.escape(ver), badge))
        # Entries are written as semicolon-separated clauses; one line each
        # reads far better than a single dense paragraph.
        for clause in [c.strip() for c in text.split(";") if c.strip()]:
            parts.append("<p>&bull; {}</p>".format(html.escape(clause)))

    return "".join(parts)


class ChangelogDialog(QDialog):
    """Scrollable changelog. `highlight` marks one version as new."""

    def __init__(self, parent=None, highlight=None, updated_from=None,
                 since_commit=None):
        super().__init__(parent)
        self.setWindowTitle("InterMap — what's new")
        self.setMinimumSize(560, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        if updated_from:
            head = QLabel("Updated from <b>v{}</b> to <b>v{}</b>".format(
                html.escape(updated_from), html.escape(version_info.version())))
        else:
            head = QLabel("InterMap <b>{}</b>".format(
                html.escape(version_info.version_label())))
        head.setTextFormat(Qt.TextFormat.RichText)
        head.setStyleSheet(f"font-size: 14px; color: {_PURPLE};")
        layout.addWidget(head)

        body = QTextBrowser()
        body.setOpenExternalLinks(True)
        body.setHtml(_changelog_html(highlight=highlight,
                                     since_commit=since_commit))
        layout.addWidget(body, 1)

        row = QHBoxLayout()
        row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        layout.addLayout(row)


def show_changelog(parent=None):
    """Open the changelog on demand (the header version button)."""
    ChangelogDialog(parent).exec()


def check_for_update(parent=None):
    """Show the changelog once when the installed version has changed.

    Records the current version either way, so a fresh install is recorded
    silently and only a genuine update pops up. Never raises — this runs on
    the path that opens the plugin.
    """
    try:
        current = version_info.install_identity()
        if current.startswith("?"):
            return False
        settings = QSettings()
        previous = settings.value(_LAST_SEEN_KEY, "", type=str)
        settings.setValue(_LAST_SEEN_KEY, current)
        if not previous or previous == current:
            return False          # first install, or nothing changed
        # Identity carries the build commit; the heading should show versions,
        # and the commit marks where the user's previous build stopped.
        prev_version, _, prev_commit = previous.partition("+")
        ChangelogDialog(parent, highlight=version_info.version(),
                        updated_from=prev_version,
                        since_commit=prev_commit or None).exec()
        return True
    except Exception:
        return False
