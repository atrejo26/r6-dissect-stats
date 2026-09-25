"""
parser.py
=========
Reads Rainbow Six Siege replay files (.rec) and normalizes them into the
internal schema used by metrics_engine.py.

IMPORTANT ENGINEERING NOTE
---------------------------
The .rec binary format is proprietary and undocumented by Ubisoft, reverse
-engineered by the community and shifting with game patches. This module
shells out to r6-dissect (https://github.com/redraskal/r6-dissect), the
actively maintained Go CLI, rather than re-deriving the byte layout in
Python.

SCHEMA (verified against dissect v0.24.x source -- header.go, feedback.go,
stats.go, match.go -- and the project's own published example output):

Single `.rec` file (one round) -> r6-dissect emits ONE round object at the
JSON root:
    {
      "gameVersion": str, "codeVersion": int, "timestamp": str,
      "matchType": {"name": str, "id": int},
      "map": {"name": str, "id": int},
      "gamemode": {"name": str, "id": int},
      "site": str, "roundNumber": int, "matchID": str,
      "teams": [
        {"name": str, "score": int, "won": bool,
         "winCondition": str, "role": "Attack"|"Defense"},
        {...}
      ],
      "players": [
        {"id": int, "username": str, "teamIndex": 0|1,
         "operator": {"name": str, "id": int}, ...}
      ],
      "matchFeedback": [
        {"type": {"name": "Kill"|"Death"|"DefuserPlantStart"|"DefuserPlantComplete"|
                          "DefuserDisableStart"|"DefuserDisableComplete"|
                          "LocateObjective"|"OperatorSwap"|"Battleye"|
                          "PlayerLeave"|"Other", "id": int},
         "username": str, "target": str, "headshot": bool,
         "time": "M:SS", "timeInSeconds": float, "message": str}
      ],
      "stats": [                     # may or may not be present depending
        {"username": str, "score": int, "kills": int, "died": bool,   # on installed r6-dissect version -- treated as optional
         "assists": int, "headshots": int, "headshotPercentage": float,
         "1vX": int}                 # clutch size won this round, omitted if 0
      ]
    }

A whole match FOLDER (multiple .rec files) -> r6-dissect wraps the same
per-round object shape inside a "rounds" list, plus a match-level "stats"
summary:
    {"rounds": [ <round object as above>, ... ], "stats": [ PlayerMatchStats, ... ]}

Notably: `map`, `matchType`, `gamemode`, and each matchFeedback `type` are
OBJECTS ({"name","id"}), not plain strings -- a naive `.get("map")` used as
a display string will render the whole dict. This module extracts
`.get("name")` from all four.

`matchFeedback` is consumed in array order, which is r6-dissect's own
chronological append order; `timeInSeconds` is kept only for display and
for bounding the trade-detection window (via absolute time delta), since
whether that clock counts up or down is not confirmed and array order is
the reliable chronological signal.

When present, per-round `stats` (kills/deaths/assists/headshots/clutch
size) come directly from r6-dissect's own computation and are trusted as
authoritative in metrics_engine.py, overriding what we'd otherwise derive
by replaying `matchFeedback` ourselves. `matchFeedback` is still needed to
derive entry kills/deaths, trades, and plant/defuse credit, none of which
appear in `stats`.

Falls back to a bundled synthetic sample match (sample_data.py) if the CLI
isn't installed, so the dashboard is runnable/demoable without it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class ReplayParseError(Exception):
    pass


def _find_r6_dissect() -> str | None:
    """Locate the CLI: $R6_DISSECT_BIN, then PATH, then the binary built at
    this repo's root (`go build` there), then `go install`'s default dir."""
    candidates = [
        os.environ.get("R6_DISSECT_BIN"),
        shutil.which("r6-dissect"),
        str(Path(__file__).resolve().parent.parent / "r6-dissect"),
        str(Path.home() / "go" / "bin" / "r6-dissect"),
    ]
    for c in candidates:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return None


R6_DISSECT_BIN = _find_r6_dissect()

_ANSI = re.compile(r"\x1b\[[0-9;]*m")  # r6-dissect's log output is colorized

# a full match is ~6-14 MB per round; allow generous time per round file
_SECONDS_PER_ROUND = 60


def r6_dissect_available() -> bool:
    return R6_DISSECT_BIN is not None


def _run_r6_dissect(rec_path: Path, num_rounds: int = 1) -> dict[str, Any]:
    """Shell out to the r6-dissect CLI and return its parsed JSON. `rec_path`
    may be a single .rec file or a folder of them (a whole match)."""
    if not r6_dissect_available():
        raise ReplayParseError(
            "r6-dissect executable not found. Build it at the repo root with "
            "`go build`, put it on PATH, or set R6_DISSECT_BIN to its path "
            "(see README) -- or run the app in demo mode."
        )
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "out.json"
        cmd = [R6_DISSECT_BIN, str(rec_path), "-o", str(out_path)]
        timeout = 60 + _SECONDS_PER_ROUND * num_rounds
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ReplayParseError(f"r6-dissect timed out after {timeout}s on {rec_path.name}.")
        if proc.returncode != 0:
            label = rec_path.name if rec_path.is_file() else "the match folder"
            raise ReplayParseError(f"r6-dissect failed on {label}: {_ANSI.sub('', proc.stderr).strip()}")
        if not out_path.exists():
            raise ReplayParseError("r6-dissect produced no output file.")
        return json.loads(out_path.read_text())


def _extract_name(field: Any, default: str = "") -> str:
    """map / matchType / gamemode all serialize as {"name": ..., "id": ...}."""
    if isinstance(field, dict):
        return field.get("name", default) or default
    if isinstance(field, str) and field:
        return field
    return default


def _display_map_name(name: str) -> str:
    """r6-dissect names reworked maps with a season suffix and no spaces
    ("VillaY10", "KafeDostoyevsky") -> "Villa", "Kafe Dostoyevsky"."""
    if name.startswith("Map("):  # unknown map id, newer than the r6-dissect build
        return name
    name = re.sub(r"Y\d+$", "", name)
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)


def _normalize_round(rs: dict[str, Any], idx: int) -> dict[str, Any]:
    teams = rs.get("teams") or [{}, {}]
    winner_team = 0
    win_condition = "unknown"
    for i, t in enumerate(teams[:2]):
        if t.get("won"):
            winner_team = i
            win_condition = t.get("winCondition", "unknown")
            break

    events: list[dict[str, Any]] = []
    for fb in rs.get("matchFeedback") or []:
        ftype = _extract_name(fb.get("type"))  # serialized as {"name": ..., "id": ...}
        t = fb.get("timeInSeconds", 0.0)
        if ftype == "Kill":
            killer, victim = fb.get("username"), fb.get("target")
            if killer:
                events.append({
                    "type": "kill", "time": t, "actor": killer, "target": victim,
                    "headshot": bool(fb.get("headshot", False)),
                })
            if victim:
                events.append({"type": "death", "time": t, "actor": victim, "killed_by": killer})
        elif ftype == "Death":
            # environmental / no-attributed-killer death (fall, bleed-out, etc.)
            victim = fb.get("username")
            if victim:
                events.append({"type": "death", "time": t, "actor": victim, "killed_by": None})
        elif ftype == "DefuserPlantComplete":
            actor = fb.get("username")
            if actor:
                events.append({"type": "plant", "time": t, "actor": actor})
        elif ftype == "DefuserDisableComplete":
            actor = fb.get("username")
            if actor:
                events.append({"type": "defuse", "time": t, "actor": actor})
        # OperatorSwap / Battleye / PlayerLeave / LocateObjective / Other: not needed for metrics

    round_stats = {}
    for s in (rs.get("stats") or []):
        uname = s.get("username")
        if not uname:
            continue
        round_stats[uname] = {
            "kills": s.get("kills", 0),
            "died": bool(s.get("died", False)),
            "assists": s.get("assists", 0),
            "headshots": s.get("headshots", 0),
            "onevx": s.get("1vX", 0),
        }

    return {
        "round_num": rs.get("roundNumber", idx + 1),
        # who was actually in this round -- players leave/rejoin in long matches
        "players": [p["username"] for p in (rs.get("players") or []) if p.get("username")],
        "winner_team": winner_team,
        "win_condition": win_condition,
        "site": rs.get("site", ""),
        "events": events,                    # matchFeedback array order == chronological
        "round_stats": round_stats or None,  # authoritative per-round stats, if present
    }


def normalize_from_r6_dissect(raw: dict[str, Any]) -> dict[str, Any]:
    """Adapt r6-dissect's JSON into our internal MatchData schema. Handles
    both the multi-round ("rounds": [...]) folder output and the flattened
    single-round-file output (see module docstring)."""
    if isinstance(raw.get("rounds"), list) and raw["rounds"]:
        round_sources = raw["rounds"]
    else:
        round_sources = [raw]

    team_of: dict[str, int] = {}
    team_names = ["Team A", "Team B"]
    for rs in round_sources:
        for i, t in enumerate((rs.get("teams") or [])[:2]):
            name = t.get("name")
            if name:
                team_names[i] = name
        for p in rs.get("players") or []:
            uname = p.get("username")
            if uname and uname not in team_of:
                team_of[uname] = p.get("teamIndex", 0)

    players = [{"name": n, "team": t, "operator_history": []} for n, t in team_of.items()]
    rounds = [_normalize_round(rs, idx) for idx, rs in enumerate(round_sources)]

    last_teams = (round_sources[-1].get("teams") or [{}, {}]) if round_sources else [{}, {}]
    score = [
        last_teams[0].get("score", 0) if len(last_teams) > 0 else 0,
        last_teams[1].get("score", 0) if len(last_teams) > 1 else 0,
    ]
    if score == [0, 0] and rounds:
        # fallback if the "score" field is absent on this r6-dissect version:
        # count rounds won directly from our own winner_team detection above.
        score = [
            sum(1 for r in rounds if r["winner_team"] == 0),
            sum(1 for r in rounds if r["winner_team"] == 1),
        ]

    map_name = _display_map_name(_extract_name(round_sources[0].get("map") if round_sources else None, "Unknown Map"))
    match_id = round_sources[0].get("matchID", "unknown") if round_sources else "unknown"

    return {
        "map": map_name,
        "match_id": match_id,
        "team_names": team_names,
        "final_score": score,
        "players": players,
        "rounds": rounds,
    }


def parse_replay(rec_file_path: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Main entry point: .rec path -> (normalized MatchData, raw JSON).
    The raw JSON is returned too so the UI can offer a debug view if the
    normalized result ever looks wrong again."""
    path = Path(rec_file_path)
    if not path.exists():
        raise ReplayParseError(f"File not found: {rec_file_path}")
    raw = _run_r6_dissect(path)
    return normalize_from_r6_dissect(raw), raw


def parse_match(rec_paths: list[str]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Parse a whole match (one .rec per round) -> (MatchData, raw JSON,
    warnings). The files are handed to r6-dissect as one folder, which it
    reads in filename order (R01, R02, ...). If a single corrupt/unsupported
    round makes that fail, each round is parsed on its own instead and the
    bad ones are skipped, so one broken file doesn't lose the whole match."""
    paths = [Path(p) for p in rec_paths]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise ReplayParseError(f"File(s) not found: {', '.join(missing)}")
    if not paths:
        raise ReplayParseError("No .rec files to parse.")
    if len(paths) == 1:
        match, raw = parse_replay(str(paths[0]))
        return match, raw, []

    warnings: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        for p in paths:
            (folder / p.name).symlink_to(p.resolve())
        try:
            raw = _run_r6_dissect(folder, num_rounds=len(paths))
            return normalize_from_r6_dissect(raw), raw, warnings
        except ReplayParseError as e:
            warnings.append(f"Whole-match parse failed, parsing rounds individually. ({e})")

    rounds = []
    for p in sorted(paths, key=lambda p: p.name):
        try:
            rounds.append(_run_r6_dissect(p))
        except (ReplayParseError, json.JSONDecodeError) as e:
            warnings.append(f"Skipped {p.name}: {e}")
    if not rounds:
        raise ReplayParseError("Every round failed to parse:\n" + "\n".join(warnings))
    raw = {"rounds": rounds}
    return normalize_from_r6_dissect(raw), raw, warnings


def load_demo_match() -> dict[str, Any]:
    """Loads the bundled synthetic sample match (see sample_data.py)."""
    from sample_data import SAMPLE_MATCH
    return SAMPLE_MATCH


def raw_shape_preview(raw: dict[str, Any], max_items: int = 3) -> dict[str, Any]:
    """Small, safe-to-render summary of the raw parser JSON for a debug
    panel -- top-level keys plus a peek at the first round's shape, so a
    schema mismatch can be diagnosed from the UI instead of a screenshot."""
    is_multi = bool(isinstance(raw.get("rounds"), list) and raw["rounds"])
    first_round = raw["rounds"][0] if is_multi else raw
    if not isinstance(first_round, dict):
        first_round = {}
    # r6-dissect can emit null for list fields, so `or []` rather than a .get() default
    players = first_round.get("players") or []
    feedback = first_round.get("matchFeedback") or []
    return {
        "top_level_keys": sorted(raw.keys()),
        "shape": "multi-round (folder)" if is_multi else "single-round (file)",
        "num_rounds": len(raw["rounds"]) if is_multi else 1,
        "first_round_keys": sorted(first_round.keys()),
        "map_field": first_round.get("map"),
        "num_players": len(players),
        "num_matchFeedback": len(feedback),
        "sample_matchFeedback": feedback[:max_items],
        "has_stats": bool(first_round.get("stats")),
    }
