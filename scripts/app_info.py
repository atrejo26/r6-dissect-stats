"""
app_info.py
===========
Name, version and links shared by the website, the Windows app and its build,
plus where the app is running (public website, Windows app, or a source checkout).
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import sys
from pathlib import Path

APP_NAME = "R6 Match Stats"
APP_VERSION = "1.0.0"

# the Windows app, as attached to each GitHub release by .github/workflows/windows-app.yaml
WINDOWS_ASSET = "R6MatchStats-Windows.zip"
DEFAULT_REPO = "julio208920/r6-dissect"

_HERE = Path(__file__).resolve().parent


def github_repo() -> str:
    """"owner/name" of the GitHub repository whose releases carry the Windows app:
    $R6_GITHUB_REPO, else the repo.txt the Windows build stamps next to this file,
    else this checkout's origin remote (so a fork links to its own releases)."""
    if os.environ.get("R6_GITHUB_REPO"):
        return os.environ["R6_GITHUB_REPO"].strip()
    stamped = _HERE / "repo.txt"
    if stamped.is_file() and stamped.read_text().strip():
        return stamped.read_text().strip()
    git_config = _HERE.parent / ".git" / "config"
    if git_config.is_file():
        origin = re.search(r'\[remote "origin"\][^\[]*?\burl\s*=\s*(\S+)', git_config.read_text())
        if origin:
            slug = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", origin.group(1))
            if slug:
                return slug.group(1)
    return DEFAULT_REPO


GITHUB_REPO = github_repo()
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
WINDOWS_DOWNLOAD_URL = f"{RELEASES_URL}/download/{WINDOWS_ASSET}"


def is_windows_app() -> bool:
    """Running as the packaged Windows app (desktop/launcher.py sets this)."""
    return os.environ.get("R6_DESKTOP") == "1"


def is_public_host() -> bool:
    """Running on a public web host: Streamlit Community Cloud (apps live under
    /mount/src), Hugging Face Spaces, or anywhere R6_HOSTED is set."""
    return bool(os.environ.get("R6_HOSTED") or os.environ.get("SPACE_ID")) or _HERE.as_posix().startswith("/mount/src/")


def is_loopback(ip: str | None) -> bool:
    """Whether a visitor's IP (st.context.ip_address) is this machine. Streamlit
    reports None for ::1 and 127.0.0.1, but IPv4 visitors on a dual-stack server
    show up as ::ffff:127.0.0.1."""
    if ip is None:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_loopback


def _drop_connection_resets(record: logging.LogRecord) -> bool:
    return not (record.exc_info and isinstance(record.exc_info[1], ConnectionResetError))


def quiet_windows_connection_resets() -> None:
    """On Windows, asyncio logs a scary but harmless ConnectionResetError traceback
    whenever a browser drops a connection (loading the page, refreshing, closing
    the tab). Call before the server starts to hide just those."""
    if sys.platform == "win32":
        logging.getLogger("asyncio").addFilter(_drop_connection_resets)  # no-op if already added
