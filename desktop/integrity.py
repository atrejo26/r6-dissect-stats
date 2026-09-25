"""
integrity.py
============
AppIntegrity checks the Windows app's folder against the list of files it was
built with (_internal/manifest.json, which build.ps1 writes right after
PyInstaller). Every listed file must be there and unchanged (same SHA-256),
and nothing else may have been added, so a planted DLL, a swapped library or
an edited script is caught. The launcher runs the check every time the app
starts and refuses to run a copy that fails it.

    python desktop/integrity.py create dist/R6MatchStats    (build.ps1 does this)
    python desktop/integrity.py verify "%LOCALAPPDATA%/Programs/R6 Match Stats"

What it can't catch: someone replacing R6MatchStats.exe itself, since that's
the file doing the checking. For that, users can compare the installer's
SHA-256 with the one published on the release before running it.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import sys
from pathlib import Path

MANIFEST = "_internal/manifest.json"
# added to the folder by the installer, after the build
ALLOWED_EXTRAS = ("unins*.exe", "unins*.dat")


class AppIntegrity:
    def __init__(self, app_dir: str | Path):
        self.app_dir = Path(app_dir)
        self.manifest = self.app_dir / MANIFEST

    def _files(self):
        for path in sorted(self.app_dir.rglob("*")):
            if path.is_file() and path != self.manifest:
                yield path.relative_to(self.app_dir).as_posix(), path

    @staticmethod
    def _sha256(path: Path) -> str:
        with open(path, "rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()

    def create(self) -> int:
        """Write the manifest for the folder as it is now; returns how many files it lists."""
        files = {rel: {"size": path.stat().st_size, "sha256": self._sha256(path)} for rel, path in self._files()}
        self.manifest.write_text(json.dumps({"files": files}, indent=1, sort_keys=True), encoding="utf-8")
        return len(files)

    def verify(self) -> list[str]:
        """Problems with the folder, one line each; an empty list means it's intact."""
        try:
            expected = json.loads(self.manifest.read_text(encoding="utf-8"))["files"]
        except (OSError, ValueError, KeyError):
            return [f"the list of the app's files ({MANIFEST}) is missing or unreadable"]
        problems = []
        seen = set()
        for rel, path in self._files():
            seen.add(rel)
            want = expected.get(rel)
            if want is None:
                if not any(fnmatch.fnmatch(rel, pattern) for pattern in ALLOWED_EXTRAS):
                    problems.append(f"unexpected file: {rel}")
            elif path.stat().st_size != want["size"] or self._sha256(path) != want["sha256"]:
                problems.append(f"changed file: {rel}")
        problems += [f"missing file: {rel}" for rel in sorted(set(expected) - seen)]
        return problems


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("create", "verify"):
        print(__doc__)
        return 2
    check = AppIntegrity(argv[2])
    if argv[1] == "create":
        print(f"Listed {check.create()} files in {check.manifest}")
        return 0
    problems = check.verify()
    print("\n".join(problems) or "All files are intact.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
