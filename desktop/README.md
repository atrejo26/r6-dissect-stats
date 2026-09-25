# Windows app

`R6MatchStats.exe` is the Streamlit dashboard (`scripts/app.py`) packaged with
Python, its libraries and `r6-dissect.exe`, so it runs on a PC without
installing anything. It starts the dashboard on the PC itself (only reachable
from that PC) and opens it in the default browser, and it finds the game's
MatchReplay folder on its own.

## Build

From the repo root, in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File desktop\build.ps1
```

This needs Python 3.10+ (it uses `.venv` if there is one) and Go 1.23+, or an
already built `r6-dissect.exe` at the repo root. It produces:

- `dist\R6MatchStats\R6MatchStats.exe` (run it to try the build)
- `dist\R6MatchStats-Windows.zip` (what users download)

GitHub builds the same zip for every published release with the **Windows
app** workflow (`.github/workflows/windows-app.yaml`).

## Files

- `launcher.py` is the entry point: it points the app at the bundled
  `r6-dissect.exe`, marks it as the Windows app, and starts Streamlit.
- `R6MatchStats.spec` tells PyInstaller what to bundle. The app files ship as
  plain files, because Streamlit runs `app.py` and its pages from disk.
- `build.ps1` builds `r6-dissect.exe`, runs PyInstaller, and zips the result.
  It also writes `build\repo.txt` with the GitHub repo, which the app's
  **Check for a newer version** button links to.

Set `R6_NO_BROWSER=1` before starting `R6MatchStats.exe` to keep it from
opening a browser tab (useful for testing).
