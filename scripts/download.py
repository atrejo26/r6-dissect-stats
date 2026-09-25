"""
download.py
===========
The "Get the Windows app" page: download link, install steps, and where Siege
keeps its replays.
"""

from __future__ import annotations

import streamlit as st

from app_info import APP_NAME, APP_VERSION, RELEASES_URL, WINDOWS_ASSET, WINDOWS_DOWNLOAD_URL, is_windows_app

st.title("Get the Windows app")

if is_windows_app():
    st.success(f"You're using the Windows app, version {APP_VERSION}.", icon="✅")
    st.link_button("Check for a newer version", RELEASES_URL)
else:
    st.write(
        f"{APP_NAME} also runs as an app on your PC. It reads your Siege replays straight from the "
        "game's folder, so there's nothing to zip or upload, and your replays never leave your computer."
    )
    st.link_button("⬇ Download for Windows", WINDOWS_DOWNLOAD_URL, type="primary")
    st.caption(f"{WINDOWS_ASSET} · Windows 10 or 11 (64-bit) · about 85 MB · "
               f"[release notes and older versions]({RELEASES_URL})")

if is_windows_app():
    st.subheader("Update")
    st.markdown(
        f"Download **{WINDOWS_ASSET}** from the newest release, close this app (close its black "
        "window), then delete the old **R6MatchStats** folder and extract the new zip in its place."
    )
else:
    st.subheader("Install and run")
    st.markdown(
        f"1. Download **{WINDOWS_ASSET}** above.\n"
        "2. Right-click the downloaded zip and choose **Extract All...**, then **Extract**.\n"
        "3. Open the extracted **R6MatchStats** folder and double-click **R6MatchStats.exe**.\n"
        "4. If Windows shows **Windows protected your PC**, click **More info**, then **Run anyway**. "
        "The app isn't code-signed, so Windows doesn't recognize it yet.\n"
        "5. A black window opens, then the app opens in your web browser. Keep the black window open "
        "while you use the app. Close it when you're done."
    )
    st.caption("Nothing to install: to remove the app, delete the R6MatchStats folder.")

st.subheader("Where are my replays?")
st.markdown(
    "Siege saves each match you play in a **MatchReplay** folder inside the game's install folder, "
    "one folder per match. The app finds it automatically for Steam and Ubisoft Connect installs. "
    "Otherwise, paste the path. The usual places are:\n"
    "- Steam: `C:\\Program Files (x86)\\Steam\\steamapps\\common\\Tom Clancy's Rainbow Six Siege\\MatchReplay`\n"
    "- Ubisoft Connect: `C:\\Program Files (x86)\\Ubisoft\\Ubisoft Game Launcher\\games\\"
    "Tom Clancy's Rainbow Six Siege\\MatchReplay`\n\n"
    "No replays there? Make sure **Match Replay** is turned on in the game's options, then play a match."
)
