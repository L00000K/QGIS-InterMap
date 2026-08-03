"""Tests for version reporting and changelog parsing.

metadata.txt is the single source of truth for both, so these lock in that the
header label and the what's-new window can always be built from it.
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "qgis_mock"))
sys.path.insert(0, os.path.dirname(_HERE))


class VersionInfoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from intermap import version_info
        cls.vi = version_info

    def test_version_matches_metadata(self):
        import configparser
        cfg = configparser.ConfigParser(interpolation=None)
        cfg.read(os.path.join(os.path.dirname(_HERE), "intermap", "metadata.txt"),
                 encoding="utf-8")
        self.assertEqual(self.vi.version(), cfg["general"]["version"].strip())

    def test_version_label_starts_with_v(self):
        self.assertTrue(self.vi.version_label().startswith("v"))

    def test_changelog_parses_every_entry(self):
        entries = self.vi.changelog_entries()
        self.assertTrue(entries, "no changelog entries parsed from metadata.txt")
        for ver, text in entries:
            self.assertTrue(text.strip(), "empty changelog text for %s" % ver)
            for part in ver.split("."):
                self.assertTrue(part.isdigit(), "bad version token %r" % ver)

    def test_newest_changelog_entry_is_current_version(self):
        # The header badge and the update popup both surface the top entry, so
        # a release with no changelog line would show the previous one as new.
        entries = self.vi.changelog_entries()
        self.assertEqual(entries[0][0], self.vi.version())

    def test_changelog_newest_first(self):
        def key(v):
            return [int(p) for p in v.split(".")]
        versions = [key(v) for v, _ in self.vi.changelog_entries()]
        self.assertEqual(versions, sorted(versions, reverse=True))

    def test_build_stamp_shape(self):
        # None is valid (no _build.py and not a checkout); a dict must be whole.
        stamp = self.vi.build_stamp()
        if stamp is not None:
            self.assertIn("commit", stamp)
            self.assertIn("date", stamp)

    def test_module_imports_without_qgis_runtime(self):
        # version_info is imported while building the header, so it must not
        # pull in anything heavier than the standard library.
        import intermap.version_info as vi
        self.assertFalse(hasattr(vi, "QSettings"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
