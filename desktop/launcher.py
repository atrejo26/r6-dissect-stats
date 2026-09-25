"""
launcher.py
===========
Entry point of the Windows app (R6MatchStats.exe, built by build.ps1 with
PyInstaller): starts the dashboard on this computer and opens it in the
default browser. Set R6_NO_BROWSER=1 to start it without opening a browser.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# the unpacked app, or the repo root when run from source (python desktop/launcher.py)
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
SCRIPTS = ROOT / "scripts"


def main() -> int:
    sys.path.insert(0, str(SCRIPTS))
    from app_info import APP_NAME, quiet_windows_connection_resets  # ships as a plain file next to app.py

    parser_exe = ROOT / "r6-dissect.exe"
    if parser_exe.is_file():
        os.environ["R6_DISSECT_BIN"] = str(parser_exe)
    os.environ["R6_DESKTOP"] = "1"
    quiet_windows_connection_resets()

    print(f"{APP_NAME} is starting and will open in your web browser.")
    print("Keep this window open while you use it. Close it to quit.\n")

    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit", "run", str(SCRIPTS / "app.py"),
        "--global.developmentMode=false",  # a PyInstaller build otherwise looks like a Streamlit dev checkout
        "--server.address=localhost",  # only this PC can reach the app
        "--server.headless=" + ("true" if os.environ.get("R6_NO_BROWSER") else "false"),
        "--server.fileWatcherType=none",
        "--server.maxUploadSize=2048",
        "--browser.gatherUsageStats=false",
        "--client.toolbarMode=minimal",  # no Streamlit developer menu (Deploy, Rerun, ...)
        "--theme.base=dark",
    ]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())
