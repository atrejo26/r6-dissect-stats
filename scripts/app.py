"""
app.py
======
Streamlit dashboard: drop in a match's replay (.zip of the match folder,
the round .rec files, or a folder path) and get an R6 Pro League-style
scoreboard for every player.

Run with:  streamlit run scripts/app.py   (from the repo root)
"""

from __future__ import annotations

import html
import json
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from metrics_engine import PRO_LEAGUE_COLUMNS, compute_match_metrics, leaderboard_rows, pro_league_rows
from parser import (
    ReplayParseError, collect_rec_files, extract_zip_recs, group_by_match, load_demo_match,
    parse_match, r6_dissect_available, raw_shape_preview,
)

if __name__ == "__main__":
    from streamlit import runtime

    if not runtime.exists():
        # started with `python app.py` (e.g. VS Code's Run button) -- relaunch
        # under `streamlit run` from the repo root, where .streamlit/config.toml lives
        import os
        import sys

        from streamlit.web import cli as stcli

        os.chdir(Path(__file__).resolve().parent.parent)
        sys.argv = ["streamlit", "run", str(Path(__file__).resolve())]
        sys.exit(stcli.main())

REPO_ROOT = Path(__file__).resolve().parent.parent
REPLAYS_DIR = REPO_ROOT / "replays"


def _collect_uploads(uploaded, td: Path) -> list[str]:
    import zipfile

    paths = []
    for up in uploaded:
        if up.name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(up) as zf:
                    paths += extract_zip_recs(zf, td / Path(up.name).stem)
            except zipfile.BadZipFile as e:
                raise ReplayParseError(f"{up.name} is not a valid zip file ({e}).") from e
        else:
            dest = td / "uploaded" / Path(up.name).name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(up.getbuffer())
            paths.append(str(dest))
    return paths


def _load_source(sig, collect) -> dict:
    """Find the matches in a source once per source: collect(workdir) -> .rec paths.
    Zips/uploads are extracted into a workdir that lives as long as the source is
    selected, so each match can be parsed only when it's picked."""
    state = st.session_state.get("source")
    if state and state["sig"] == sig:
        return state
    if state:
        shutil.rmtree(state["workdir"], ignore_errors=True)
    workdir = tempfile.mkdtemp(prefix="r6-match-")
    state = {"sig": sig, "workdir": workdir, "parsed": {}}
    try:
        state["groups"] = group_by_match(collect(Path(workdir)))
        if not state["groups"]:
            state["error"] = "No .rec replay files found."
    except ReplayParseError as e:
        state["error"] = str(e)
    st.session_state["source"] = state
    return state


st.set_page_config(page_title="R6 Match Stats", page_icon="🎯", layout="wide")

# ---------------------------------------------------------------- styling --
st.markdown("""
<style>
:root { --bg:#0d1117; --panel:#151b23; --row:#1a212b; --border:#232b36; --accent:#ff5c1a;
        --dim:#8b949e; --text:#f0f3f6; --pos:#3fb950; --neg:#f85149; }
.stApp { background-color: var(--bg); }
section[data-testid="stSidebar"] { background-color: var(--panel); }
h1, h2, h3, h4 { color: var(--text) !important; letter-spacing: -0.02em; }
.scorecard { background:var(--panel); border:1px solid var(--border); border-radius:14px;
             padding:20px 28px; margin-bottom:18px; display:flex; align-items:center;
             justify-content:space-between; gap:16px; flex-wrap:wrap; }
.team-name { font-size:1.15rem; color:var(--text); font-weight:700; }
.score-big { font-size:2.6rem; font-weight:800; color:var(--accent); }
.map-pill { display:inline-block; background:#1f2733; color:var(--dim); border-radius:999px;
            padding:4px 14px; font-size:0.8rem; font-weight:600; border:1px solid var(--border); }
.pl-wrap { overflow-x:auto; margin-bottom:22px; border:1px solid var(--border); border-radius:10px; }
table.pl { width:100%; border-collapse:collapse; font-size:0.9rem; color:var(--text);
           font-variant-numeric: tabular-nums; }
table.pl caption { caption-side:top; text-align:left; padding:10px 14px; font-weight:700;
                   font-size:1.05rem; background:var(--panel); color:var(--text); }
table.pl caption .won { color:var(--accent); margin-left:8px; }
table.pl th { background:var(--panel); color:var(--dim); font-weight:600; text-align:center;
              padding:8px 10px; white-space:nowrap; border-top:1px solid var(--border); }
table.pl td { padding:9px 10px; text-align:center; white-space:nowrap; border-top:1px solid var(--border); }
table.pl tr:nth-child(even) td { background:var(--row); }
table.pl th:first-child, table.pl td:first-child { text-align:left; font-weight:600; }
table.pl td.eps { color:var(--accent); font-weight:800; }
.pos { color:var(--pos); } .neg { color:var(--neg); }
</style>
""", unsafe_allow_html=True)


def _signed_cell(text: str) -> str:
    """Color the "(+4)" / "(-2)" part of a KD or Entry cell."""
    text = html.escape(text)
    if "(+" in text:
        return text.replace("(+", '<span class="pos">(+').replace(")", ")</span>")
    if "(-" in text:
        return text.replace("(-", '<span class="neg">(-').replace(")", ")</span>")
    return text


def scoreboard_html(team_name: str, won: bool, rows: list[dict]) -> str:
    head = "".join(f"<th>{html.escape(c)}</th>" for c in ("Player",) + PRO_LEAGUE_COLUMNS)
    body = []
    for r in rows:
        cells = [f"<td>{html.escape(r['Player'])}</td>", f'<td class="eps">{r["EPS"]}</td>']
        for c in PRO_LEAGUE_COLUMNS[1:]:
            v = str(r[c])
            cells.append(f"<td>{_signed_cell(v) if c in ('KD (+/-)', 'Entry') else html.escape(v)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    badge = '<span class="won">WIN</span>' if won else ""
    return (f'<div class="pl-wrap"><table class="pl"><caption>{html.escape(team_name)}{badge}</caption>'
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>")


# ------------------------------------------------------------- sidebar ----
with st.sidebar:
    st.markdown("### 🎯 R6 Match Stats")
    st.caption("Drop in a match replay (a `.zip` of the match folder, or its round `.rec` files) "
               "for a Pro League-style scoreboard.")
    if r6_dissect_available():
        st.success("r6-dissect found", icon="✅")
    else:
        st.warning("r6-dissect not found, so real replays can't be parsed. "
                   "See the README to build it, or use the demo match below.", icon="⚠️")
    demo_mode = st.toggle("Use demo match (no file needed)", value=not r6_dissect_available())
    st.divider()
    st.caption("EPS · KD (+/-) · Entry · KOST · KPR · HS · SRV · Clutches · Multikills · "
               "Objectives · Dead for trade kill · Trade kills")

st.title("Match Report")

# ------------------------------------------------------------- input -------
match = raw = None
parse_warnings: list[str] = []

if demo_mode:
    match = load_demo_match()
    st.caption("Showing the bundled demo match. Turn off demo mode in the sidebar to load a real replay.")
else:
    source = st.radio(
        "Replay source",
        ["Upload", "Folder or zip on this computer", "From the replays/ folder"],
        horizontal=True,
        help="On GitHub Codespaces, browser uploads over ~50 MB fail with HTTP 413; "
             "put big matches in replays/ instead.",
    )
    picked = None  # (cache signature, collect(tempdir) -> .rec paths)
    if source == "Upload":
        uploaded = st.file_uploader(
            "Drop the match's .zip (or every .rec file from the match folder)",
            type=["zip", "rec"], accept_multiple_files=True,
        )
        if uploaded:
            sig = ("upload",) + tuple((u.name, u.size, u.file_id) for u in uploaded)
            picked = (sig, lambda td, u=uploaded: _collect_uploads(u, td))
    elif source == "Folder or zip on this computer":
        typed = st.text_input(
            "Path to a match folder, a .zip, or your whole MatchReplay folder",
            placeholder=r"C:\Program Files (x86)\Steam\steamapps\common\Tom Clancy's Rainbow Six Siege\MatchReplay",
        ).strip().strip('"')
        if typed:
            p = Path(typed).expanduser()
            if not p.exists():
                st.error(f"Not found: {p}")
            else:
                picked = (("path", str(p), p.stat().st_mtime), lambda td, c=p: collect_rec_files(c, td))
    else:
        REPLAYS_DIR.mkdir(exist_ok=True)
        choices = sorted(
            [p for p in REPLAYS_DIR.iterdir()
             if (p.is_dir() and any(p.rglob("*.rec"))) or p.suffix.lower() in (".zip", ".rec")],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        st.caption(f"Copy a match folder or its `.zip` into `{REPLAYS_DIR}`, then pick it here.")
        if not choices:
            st.info(f"No matches in `{REPLAYS_DIR}` yet.")
        else:
            chosen = st.selectbox("Match", choices, format_func=lambda p: p.name + ("/" if p.is_dir() else ""))
            picked = (("path", str(chosen), chosen.stat().st_mtime), lambda td, c=chosen: collect_rec_files(c, td))

    if picked is not None:
        state = _load_source(*picked)
        if "error" in state:
            st.error(state["error"])
            st.stop()
        names = list(state["groups"])
        if len(names) > 1:
            name = st.selectbox(f"{len(names)} matches found", names, index=len(names) - 1)
        else:
            name = names[0]
        if name not in state["parsed"]:
            with st.spinner(f"Parsing {name}... long matches can take a minute."):
                try:
                    state["parsed"][name] = parse_match(state["groups"][name])
                except ReplayParseError as e:
                    state["parsed"][name] = e
        result = state["parsed"][name]
        if isinstance(result, ReplayParseError):
            st.error(f"{name}: {result}")
            st.stop()
        match, raw, parse_warnings = result
        for w in parse_warnings:
            st.warning(w, icon="⚠️")
        with st.sidebar:
            with st.expander("🔍 Parser debug info"):
                st.json(raw_shape_preview(raw))

if match is None:
    st.info("Load a replay above, or turn on the demo match in the sidebar.")
    st.stop()

# ------------------------------------------------------------ compute ------
stats = compute_match_metrics(match)
rows = pro_league_rows(stats)
team_names = match["team_names"]
score = match["final_score"]

if not stats:
    st.warning("This replay has no player data (it may be a practice session or a match "
               "that ended before it started).", icon="⚠️")
    st.stop()
if not any(s.kills for s in stats.values()):
    st.warning("Parsed, but no kills were found. Expand **Parser debug info** in the sidebar "
               "to see what r6-dissect returned.", icon="⚠️")

# ------------------------------------------------------------ scorecard ---
st.markdown(
    f'<div class="scorecard">'
    f'<div class="team-name">{html.escape(team_names[0])}</div>'
    f'<div style="text-align:center"><span class="score-big">{score[0]}</span>'
    f'<span style="color:#8b949e;font-size:1.6rem"> : </span><span class="score-big">{score[1]}</span><br>'
    f'<span class="map-pill">{html.escape(match["map"])} · {len(match["rounds"])} round{"s" if len(match["rounds"]) != 1 else ""}</span></div>'
    f'<div class="team-name" style="text-align:right">{html.escape(team_names[1])}</div>'
    f'</div>', unsafe_allow_html=True)

# ------------------------------------------------------------ scoreboards -
for team_idx, team_name in enumerate(team_names[:2]):
    team_rows = [r for r in rows if r["Team"] == team_idx]
    if team_rows:
        won = score[team_idx] > score[1 - team_idx]
        st.markdown(scoreboard_html(team_name, won, team_rows), unsafe_allow_html=True)

numeric = pd.DataFrame(leaderboard_rows(stats))
numeric.insert(1, "Team Name", [team_names[t] for t in numeric["Team"]])
c1, c2, _ = st.columns([1, 1, 2])
c1.download_button("⬇ CSV", numeric.to_csv(index=False).encode("utf-8"),
                   file_name=f"{match['match_id']}_stats.csv", mime="text/csv")
c2.download_button("⬇ JSON", json.dumps({
    "map": match["map"], "match_id": match["match_id"], "teams": team_names,
    "score": score, "players": rows}, indent=2, ensure_ascii=False).encode("utf-8"),
    file_name=f"{match['match_id']}_stats.json", mime="application/json")

# ------------------------------------------------------------ breakdown ---
st.subheader("Round-by-round")
player = st.selectbox("Player", [r["Player"] for r in rows])
s = stats[player]
for col, (label, value) in zip(st.columns(3) + st.columns(3), (
    ("EPS", s.eps),
    ("K-D-A", f"{s.kills}-{s.deaths}-{s.assists}"),
    ("Entry K-D", f"{s.entry_kills}-{s.entry_deaths}"),
    ("KOST", f"{s.kost_pct:.0f}%"),
    ("Plants-Defuses", f"{s.plants}-{s.defuses}"),
    ("Traded-Trade kills", f"{s.trades}-{s.trade_kills}"),
)):
    col.metric(label, value)
for i, rb in enumerate(s.round_breakdown, 1):
    st.markdown(f"**{'🟢' if rb.survived else '🔴'} Round {i}** — {rb.summary()}")

with st.expander("Stat definitions"):
    st.markdown(
        "- **EPS**: performance score centered on 100 (match average). Ubisoft hasn't published "
        "its EPS formula; this one combines KPR, deaths, KOST, entry differential, multikills, "
        "clutches, objectives and trade kills, weighted against everyone in this match.\n"
        "- **KD (+/-)**: kills-deaths (difference). **Entry**: opening kills-opening deaths.\n"
        "- **KOST**: % of rounds with a Kill, Objective, Survival or Traded death. "
        "**KPR**: kills per round. **HS**: headshot kills %. **SRV**: % of rounds survived.\n"
        "- **Clutches**: rounds won as the team's last player alive vs 1+ enemies. "
        "**Multikills**: rounds with 2+ kills.\n"
        "- **Objectives**: defuser plants + disables. Recent Siege replays don't record who "
        "planted or disabled the defuser, so it's only credited when a single player on that side "
        "was alive.\n"
        "- **Dead for trade kill**: deaths a teammate avenged within 10 s. "
        "**Trade kills**: kills that avenged a teammate within 10 s."
    )
