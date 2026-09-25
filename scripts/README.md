# R6 T1 Match Lab

Upload a Rainbow Six Siege `.rec` replay, get a T1-style performance report:
KDA, entry kills/deaths, trades, plants/defuses, clutches, KOST, and a
SiegeGG-style Rating — in a dark, sortable dashboard with a per-player
round-by-round modal.

## Architecture

```
.rec file
   │
   ▼
parser.py            → shells out to the r6-dissect CLI, normalizes its
                        JSON into our internal MatchData schema
   │
   ▼
metrics_engine.py     → pure-Python stats engine: KDA, entries, trades,
                         clutches, KOST, and the z-scored Rating
   │
   ▼
app.py (Streamlit)    → upload zone, scorecard, sortable leaderboard,
                         per-player round-breakdown modal
```

`sample_data.py` ships a hand-built 9-round demo match so you can run the
whole dashboard with zero external dependencies and no real replay file.

## Why r6-dissect instead of a from-scratch binary parser

The `.rec` format is undocumented by Ubisoft and has been reverse-engineered
by the community; it also shifts with game patches. Re-deriving the byte
layout in Python (the old "dissect-r6"-style approach) means you're
re-reverse-engineering it yourself and re-breaking on every Siege update.
**r6-dissect** (https://github.com/redraskal/r6-dissect) is the actively
maintained Go implementation the competitive-stats community already
relies on, and it ships a CLI that emits structured JSON. `parser.py` shells
out to that CLI and adapts its JSON into a stable internal schema — so if a
future r6-dissect release renames a field, you only touch the adapter
function (`normalize_from_r6_dissect`), not the metrics engine or UI.

## Setup

### 1. Install r6-dissect (for parsing real `.rec` files)

Download a prebuilt binary from the project's GitHub Releases page and put
it on your `PATH`, or build from source with Go installed:

```bash
go install github.com/redraskal/r6-dissect/cmd/r6-dissect@latest
```

Verify it's discoverable:

```bash
r6-dissect --version
```

If it's not on `PATH`, the dashboard will detect that and automatically
fall back to Demo Mode with a warning banner — it won't crash.

### 2. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run the dashboard

```bash
streamlit run app.py
```

Open the printed local URL. Toggle **Demo Mode** in the sidebar to explore
the UI immediately without a replay file, or drop a `.rec` file onto the
upload zone once r6-dissect is installed.

## Metric definitions (matches public T1 stat-site conventions)

| Metric | Definition |
|---|---|
| Entry Kill/Death | The first kill/death event of the round |
| Trade | A death where a teammate kills that player's killer within 5s |
| KOST | % of rounds with a Kill, Objective (plant/defuse), Survival, or Trade |
| Clutch (1vX) | Winning a round as the last player alive on your team, sized by opponents alive at that moment |
| Rating | KPR, DPR, entry differential, KOST, multi-kills, and clutches, z-scored against the 10 players in the match and centered at 1.00 |

**Rating caveat:** SiegeGG's exact rating formula isn't published. The
formula here is a transparent, from-scratch replica built from the same
public ingredients they cite — treat it as a strong approximation, not a
guaranteed byte-for-byte match to their number.

**Assists caveat:** true assist attribution needs the damage-event log
(non-lethal damage contribution), which isn't in the internal schema here.
The field is present and wired through the UI/engine at 0 so it's a
one-line change once a damage-capable data source is plugged into
`parser.py`.

## Troubleshooting: stats showing as 0

If a real `.rec` upload ever comes back with every player at 0 again, expand
**🔍 Parser debug info** in the sidebar after uploading. It shows the raw
JSON's top-level keys, whether it parsed as a single-round file or a
multi-round match folder, the `map` field's raw value, and a sample of the
first few `matchFeedback` events — enough to spot a schema drift without a
screenshot round-trip. `parser.py`'s `normalize_from_r6_dissect()` is the
one function that would need updating if a future r6-dissect release
changes field names.

## Extending

- **Swap the parser backend:** replace the body of `parse_replay()` in
  `parser.py` with any other JSON-emitting Siege replay tool; keep
  `normalize_from_r6_dissect`'s output shape as your target schema.
- **Real assists:** if your parser exposes damage events, add an
  `"assist"` event type in the normalizer and extend `_process_round` in
  `metrics_engine.py` to award assists (e.g., last non-killer to damage
  the victim within N seconds).
- **Multi-match history:** wrap `compute_match_metrics` in a loop over
  several parsed replays and aggregate `PlayerStats` across matches for a
  season-long leaderboard.
