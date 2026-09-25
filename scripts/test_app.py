"""Tests for the Streamlit pages (app.py, report.py, download.py) and app_info.py.
Run from the repo root:  python -m unittest discover -s scripts"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

import app_info
import parser as replay_parser

APP = str(Path(__file__).with_name("app.py"))


def run_app(local_visitor: bool = True, **env: str) -> AppTest:
    # AppTest has no real visitor IP, and no replay folder is auto-detected,
    # so nothing gets parsed unless a test asks for it
    with mock.patch.dict(os.environ, env), \
            mock.patch.object(app_info, "is_loopback", return_value=local_visitor), \
            mock.patch.object(replay_parser, "find_replay_folders", return_value=[]):
        at = AppTest.from_file(APP, default_timeout=60)
        at.run()
    return at


class TestReportPage(unittest.TestCase):
    def test_local_visitor_can_read_folders(self):
        at = run_app()
        self.assertFalse(at.exception)
        self.assertEqual(at.radio[0].options, ["Folder or zip on this computer", "Upload", "From the replays/ folder"])

    def test_public_site_only_takes_uploads(self):
        at = run_app(R6_HOSTED="1")
        self.assertFalse(at.exception)
        self.assertEqual(len(at.radio), 0)  # no folder paths on a public server
        self.assertEqual(len(at.text_input), 0)

    def test_remote_visitor_only_uploads_even_off_a_known_host(self):
        at = run_app(local_visitor=False)
        self.assertEqual(len(at.radio), 0)
        self.assertEqual(len(at.text_input), 0)

    def test_windows_app_has_no_replays_folder_option(self):
        at = run_app(R6_DESKTOP="1")
        self.assertEqual(at.radio[0].options, ["Folder or zip on this computer", "Upload"])

    def test_demo_match_renders_both_scoreboards(self):
        at = run_app(R6_HOSTED="1")
        at.toggle[0].set_value(True).run()
        self.assertFalse(at.exception)
        tables = [m.value for m in at.markdown if 'class="pl"' in m.value]
        self.assertEqual(len(tables), 2)
        self.assertIn("Team Liquid", tables[0])


class TestDownloadPage(unittest.TestCase):
    def test_download_link(self):
        at = run_app(R6_HOSTED="1")
        at.switch_page("download.py").run()
        self.assertFalse(at.exception)
        links = [b.proto.url for b in at.get("link_button")]
        self.assertIn(app_info.WINDOWS_DOWNLOAD_URL, links)
        self.assertTrue(app_info.WINDOWS_DOWNLOAD_URL.endswith("/releases/latest/download/" + app_info.WINDOWS_ASSET))


class TestAppInfo(unittest.TestCase):
    def test_loopback(self):
        for ip in (None, "127.0.0.1", "::1", "::ffff:127.0.0.1"):
            self.assertTrue(app_info.is_loopback(ip), ip)
        for ip in ("10.0.0.5", "::ffff:34.12.1.9", "2001:db8::1", "not an ip"):
            self.assertFalse(app_info.is_loopback(ip), ip)

    def test_repo_override(self):
        with mock.patch.dict(os.environ, {"R6_GITHUB_REPO": "someone/r6-stats"}):
            self.assertEqual(app_info.github_repo(), "someone/r6-stats")


if __name__ == "__main__":
    unittest.main()
