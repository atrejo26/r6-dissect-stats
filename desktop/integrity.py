"""Build manifest and startup checks for the packaged application files.

This detects accidental or unsophisticated changes to shipped assets. Because
the manifest ships alongside the app, it is not a substitute for a signed
installer or an antivirus engine.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ASSETS = (
    "r6-dissect.exe",
    "scripts/app.py",
    "scripts/app_info.py",
    "scripts/report.py",
    "scripts/download.py",
    "scripts/team_hub.py",
    "scripts/season_stats.py",
    "scripts/replay_watch.py",
    "scripts/parser.py",
    "scripts/metrics_engine.py",
    "scripts/sample_data.py",
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(root: Path, output: Path) -> None:
    hashes = {name: digest(root / name) for name in ASSETS}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_manifest(root: Path, manifest: Path) -> list[str]:
    if not manifest.is_file():
        return ["integrity manifest is missing"]
    try:
        hashes = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(hashes, dict) or set(hashes) != set(ASSETS):
            return ["integrity manifest has an unexpected file list"]
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ["integrity manifest could not be read"]
    changed = []
    for name, expected in hashes.items():
        path = root / name
        if not isinstance(expected, str) or len(expected) != 64 or not path.is_file():
            changed.append(name)
            continue
        try:
            if digest(path) != expected:
                changed.append(name)
        except OSError:
            changed.append(name)
    return changed


if __name__ == "__main__":
    import sys
    write_manifest(Path(sys.argv[1]), Path(sys.argv[2]))
