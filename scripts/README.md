# R6 Match Stats

Give it a Rainbow Six Siege match replay (a `.zip` of the match folder, the
folder itself, or its round `.rec` files) and it builds an **R6 Pro
League-style scoreboard**: one row per player, split by team, with the same
12 columns as the official R6 Esports match page.

| Player | EPS | KD (+/-) | Entry | KOST | KPR | HS | SRV | Clutches | Multikills | Objectives | Dead for trade kill | Trade kills |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Player1 | 116 | 8-2 (+6) | 4-0 (+4) | 100% | 1.14 | 62% | 71% | 0 | 1 | 0 | 1 | 0 |

It comes as a web dashboard (`app.py`) and a command-line tool
(`match_stats.py`). Both can also export CSV/JSON.

## Quick start (Windows)

From the repo root, in PowerShell:

```powershell
# 1. build the replay parser (needs Go 1.23+: https://go.dev/dl/)
go build -o r6-dissect.exe .

# 2. install the Python dependencies (Python 3.10+)
python -m venv .venv
.venv\Scripts\python -m pip install -r scripts\requirements.txt

# 3a. open the dashboard (http://localhost:8501)
.venv\Scripts\python -m streamlit run scripts\app.py

# 3b. ...or print the scoreboard in the terminal
cd scripts
..\.venv\Scripts\python match_stats.py "C:\Users\you\Downloads\Match-2026-09-23_19-19-11-23660.zip"
```

On macOS/Linux, use `go build` (it produces `r6-dissect`), `source
.venv/bin/activate`, and forward slashes.

## Using the dashboard

Pick a **Replay source**:

- **Upload**: drop the match's `.zip`, or every `.rec` file from the match folder.
- **Folder or zip on this computer**: paste a path. This can be one match
  folder, a `.zip`, or your whole `MatchReplay` folder
  (`...\steamapps\common\Tom Clancy's Rainbow Six Siege\MatchReplay`). With
  several matches you get a picker, and each match is parsed only when you pick it.
- **From the replays/ folder**: copy matches into `replays/` at the repo
  root. Use this on GitHub Codespaces, where browser uploads over ~50 MB fail.

Below the scoreboards you'll find CSV/JSON downloads and a round-by-round
breakdown for each player. The **Use demo match** toggle loads a built-in
sample match, so you can try the dashboard without a replay.

## Command line

```
python match_stats.py SOURCE [--csv stats.csv] [--json stats.json]
```

`SOURCE` is a `.zip`, a match folder, a single `.rec`, or a folder of many
matches (each one gets its own scoreboard). `--csv` writes the numeric stats
(one row per player per match), and `--json` writes the scoreboards.

## Stat definitions

| Column | Meaning |
|---|---|
| EPS | Performance score, where 100 is the average player in this match. Ubisoft hasn't published its EPS formula, so this one is built from the same kind of inputs: kills and deaths per round, KOST, entry differential, multikills, clutches, objectives and trade kills, each compared against the other players in the match. |
| KD (+/-) | kills-deaths (difference) |
| Entry | opening kills-opening deaths. The opening duel is the round's first death. |
| KOST | % of rounds with a **K**ill, **O**bjective, **S**urvival or **T**raded death |
| KPR | kills per round |
| HS | headshot kills / kills |
| SRV | % of rounds survived |
| Clutches | rounds won as the team's last player alive against 1+ enemies |
| Multikills | rounds with 2+ kills |
| Objectives | defuser plants + defuser disables |
| Dead for trade kill | this player's deaths that a teammate avenged within 10 s |
| Trade kills | kills on an enemy who had killed a teammate within the previous 10 s |

Team kills never count as kills, but the victim still gets a death.

### Known limitations

- **Objectives:** replays from the current game version (Y11S3) no longer
  record *who* planted or disabled the defuser, only that it happened. A
  plant or disable is credited only when exactly one player on that side was
  alive; otherwise it isn't credited to anyone. Older replays name the player.
- **EPS** is a close stand-in, not Ubisoft's exact number.
- Rounds that ended without a score change (an abandoned match) have no
  winner, so they give no clutch.

## Architecture

```
.zip / folder / .rec
   │  parser.collect_rec_files + group_by_match   (unzip, split into matches)
   ▼
r6-dissect (Go CLI, repo root)  →  JSON per round
   │  parser.normalize_from_r6_dissect             (stable internal schema)
   ▼
metrics_engine.compute_match_metrics  →  PlayerStats per player
   │  metrics_engine.pro_league_rows               (the 12 display columns)
   ▼
app.py (Streamlit)  /  match_stats.py (CLI)
```

`parser.py` finds the r6-dissect binary via `$R6_DISSECT_BIN`, then `PATH`,
then `r6-dissect.exe` (Windows) or `r6-dissect` at the repo root, then
`~/go/bin`. If a future r6-dissect release renames JSON fields, only
`normalize_from_r6_dissect` needs updating.

**Season-long stats:** `season_stats.py` (`StatsManager`) logs tracked
players' rounds into SQLite across a season without double-counting. See
[SEASON_STATS.md](SEASON_STATS.md) and `example_season_stats.py`.

## Tests

```bash
cd scripts
python -m unittest          # metrics engine, replay-file handling, season stats
cd ..
go test ./...               # the Go replay parser
```

## Troubleshooting

- **"r6-dissect not found"**: build it at the repo root (step 1), or set
  `R6_DISSECT_BIN` to its full path.
- **Every stat is 0 / "no player data"**: expand **Parser debug info** in the
  sidebar to see what r6-dissect returned. Practice sessions and matches that
  ended during prep have no kill feed.
- **A map shows as `Map(123...)`**: the map is newer than this r6-dissect
  build; add its ID to `dissect/header.go` and re-run `stringer -type=Map`.
