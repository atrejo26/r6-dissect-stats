# PyInstaller spec for the Windows app: dist/R6MatchStats/R6MatchStats.exe.
# Build with desktop/build.ps1, which builds r6-dissect.exe and stamps build/repo.txt first.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent

# The app ships as plain files, because Streamlit runs app.py (and its pages) from disk.
APP_FILES = ["app.py", "report.py", "download.py", "app_info.py", "parser.py", "metrics_engine.py", "sample_data.py"]
datas = [(str(ROOT / "scripts" / name), "scripts") for name in APP_FILES]
if (ROOT / "build" / "repo.txt").is_file():
    datas.append((str(ROOT / "build" / "repo.txt"), "scripts"))
datas += collect_data_files("streamlit") + copy_metadata("streamlit")

hiddenimports = (
    collect_submodules("streamlit")
    # uvicorn and websockets load their protocol modules by name at runtime
    + collect_submodules("uvicorn")
    + collect_submodules("websockets")
    # standard library modules the app files use, which PyInstaller can't see in plain files
    + ["csv", "dataclasses", "html", "ipaddress", "json", "shutil", "subprocess", "tempfile", "zipfile"]
)

a = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    binaries=[(str(ROOT / "r6-dissect.exe"), ".")],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="R6MatchStats", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="R6MatchStats")
