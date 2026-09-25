"""
app.py
======
Streamlit dashboard for the R6 T1 telemetry tool.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from metrics_engine import compute_match_metrics, leaderboard_rows
from parser import parse_match, load_demo_match, r6_dissect_available, ReplayParseError, raw_shape_preview

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


def _extract_zip_recs(zf: zipfile.ZipFile, dest_dir: Path) -> list[str]:
    """Extract only the .rec files, flattened (zips usually wrap a match folder)."""
    paths = []
    for member in zf.infolist():
        name = Path(member.filename).name
        if member.is_dir() or not name.lower().endswith(".rec") or name.startswith("._"):
            continue  # "._x.rec" are macOS resource forks, not replays
        dest = dest_dir / name
        with zf.open(member) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out)
        paths.append(str(dest))
    return paths


def _collect_recs_from_path(p: Path, td: Path) -> list[str]:
    if p.is_dir():
        return sorted(str(f) for f in p.rglob("*.rec") if not f.name.startswith("._"))
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as zf:
            return sorted(_extract_zip_recs(zf, td))
    return [str(p)]


def _collect_recs_from_uploads(uploaded, td: Path) -> list[str]:
    paths = []
    for up in uploaded:
        if up.name.lower().endswith(".zip"):
            with zipfile.ZipFile(up) as zf:
                paths += _extract_zip_recs(zf, td)
        else:
            dest = td / Path(up.name).name
            dest.write_bytes(up.getbuffer())
            paths.append(str(dest))
    return sorted(set(paths))


st.set_page_config(page_title="R6 T1 Match Lab", page_icon="🎯", layout="wide")

# ---------------------------------------------------------------- styling --
st.markdown("""
<style>
:root {
    --bg: #0d1117;
    --panel: #151b23;
    --border: #232b36;
    --accent: #ff5c1a;
    --text-dim: #8b949e;
}
.stApp { background-color: var(--bg); }
section[data-testid="stSidebar"] { background-color: var(--panel); }
h1, h2, h3 { color: #f0f3f6 !important; letter-spacing: -0.02em; }
div[data-testid="stMetricValue"] { color: var(--accent); }
.scorecard {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 24px 28px;
    margin-bottom: 18px;
}
.team-name { font-size: 1.1rem; color: #f0f3f6; font-weight: 700; }
.score-big { font-size: 2.6rem; font-weight: 800; color: var(--accent); }
.map-pill {
    display:inline-block; background:#1f2733; color:var(--text-dim);
    border-radius: 999px; padding: 4px 14px; font-size: 0.8rem; font-weight:600;
    border: 1px solid var(--border);
}
.stDataFrame { border: 1px solid var(--border); border-radius: 10px; }
.upload-zone {
    border: 2px dashed var(--border); border-radius: 14px; padding: 10px;
    background: var(--panel);
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------- sidebar ----
with st.sidebar:
    st.markdown("### 🎯 R6 T1 Match Lab")
    st.caption("Upload a match's `.rec` replays (one per round), or a `.zip` of the match folder, to generate a full T1-style performance report.")
    if r6_dissect_available():
        st.success("r6-dissect found", icon="✅")
    else:
        st.warning("r6-dissect not found — real .rec parsing is disabled. "
                    "See README for install steps, or use Demo Mode below.", icon="⚠️")
    demo_mode = st.toggle("Use demo match (no file needed)", value=not r6_dissect_available())
    st.divider()
    st.caption("Metrics: KDA · Entry K/D · Trades · Plants/Defuses · Clutches · KOST · Rating")

# ------------------------------------------------------------- upload ------
st.title("Match Report")

match = None
raw = None
error = None

if demo_mode:
    match = load_demo_match()
    st.caption("Showing the bundled demo match. Turn off demo mode in the sidebar to upload a real `.rec` file.")
else:
    source = st.radio(
        "Replay source",
        ["From the replays/ folder", "Upload in browser"],
        horizontal=True,
        help="Large uploads through the browser fail with HTTP 413 on GitHub Codespaces "
             "(the port-forwarding proxy caps request size). Put big matches in replays/ instead.",
    )

    picked = None  # (cache signature, loader returning a list of .rec paths inside a temp dir)
    if source == "From the replays/ folder":
        REPLAYS_DIR.mkdir(exist_ok=True)
        choices = sorted(
            [p for p in REPLAYS_DIR.iterdir()
             if (p.is_dir() and any(p.rglob("*.rec"))) or p.suffix.lower() in (".zip", ".rec")],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        st.caption(
            f"Drag a match folder or its `.zip` into `{REPLAYS_DIR.relative_to(REPO_ROOT)}/` "
            "in the VS Code Explorer (no size limit), then pick it here."
        )
        if not choices:
            st.info(f"No matches in `{REPLAYS_DIR}` yet.")
        else:
            chosen = st.selectbox("Match", choices, format_func=lambda p: p.name + ("/" if p.is_dir() else ""))
            sig = ("path", str(chosen), chosen.stat().st_mtime)
            picked = (sig, lambda td, c=chosen: _collect_recs_from_path(c, td))
    else:
        st.markdown('<div class="upload-zone">', unsafe_allow_html=True)
        uploaded = st.file_uploader(
            "Drop every .rec file from the match folder here (or a .zip of the folder)",
            type=["rec", "zip"],
            accept_multiple_files=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)
        st.caption("On Codespaces, uploads over ~50 MB fail with HTTP 413; use the replays/ folder for those, "
                   "or upload the round `.rec` files individually instead of one big zip.")
        if uploaded:
            sig = ("upload",) + tuple((u.name, u.size, u.file_id) for u in uploaded)
            picked = (sig, lambda td, u=uploaded: _collect_recs_from_uploads(u, td))

    if picked is not None:
        sig, collect = picked
        cached = st.session_state.get("parsed_match")
        if cached and cached["sig"] == sig:
            match, raw, parse_warnings = cached["result"]
        else:
            with st.spinner("Parsing match... long matches can take a minute."):
                try:
                    with tempfile.TemporaryDirectory() as td:
                        rec_paths = collect(Path(td))
                        if not rec_paths:
                            raise ReplayParseError("No .rec files found.")
                        match, raw, parse_warnings = parse_match(rec_paths)
                    st.session_state["parsed_match"] = {"sig": sig, "result": (match, raw, parse_warnings)}
                except (ReplayParseError, zipfile.BadZipFile) as e:
                    error = str(e)
        if match is not None:
            for w in parse_warnings:
                st.warning(w, icon="⚠️")
            st.caption(f"Parsed {len(match['rounds'])} round(s).")

        if match is not None and sum(match["final_score"]) == 0 and not any(
            s.kills for s in compute_match_metrics(match).values()
        ):
            st.warning(
                "Parsed successfully, but every stat came back at 0 — this usually means the "
                "installed r6-dissect version's JSON shape doesn't match what this app expects. "
                "Expand **Parser debug info** in the sidebar and let me know what it shows.",
                icon="⚠️",
            )

    if raw is not None:
        with st.sidebar:
            with st.expander("🔍 Parser debug info"):
                st.json(raw_shape_preview(raw))

if error:
    st.error(error)
    st.stop()

if match is None:
    st.info("Upload a replay file, or toggle **Demo Mode** in the sidebar to explore the dashboard.")
    st.stop()

# ------------------------------------------------------------ compute ------
stats = compute_match_metrics(match)
rows = leaderboard_rows(stats)
df = pd.DataFrame(rows)

# ------------------------------------------------------------ scorecard ---
team_names = match["team_names"]
score = match["final_score"]

st.markdown('<div class="scorecard">', unsafe_allow_html=True)
c1, c2, c3 = st.columns([3, 2, 3])
with c1:
    st.markdown(f'<div class="team-name">{team_names[0]}</div>', unsafe_allow_html=True)
with c2:
    st.markdown(
        f'<div style="text-align:center">'
        f'<span class="score-big">{score[0]}</span>'
        f'<span style="color:#8b949e; font-size:1.6rem;"> : </span>'
        f'<span class="score-big">{score[1]}</span><br>'
        f'<span class="map-pill">{match["map"]}</span>'
        f'</div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="team-name" style="text-align:right">{team_names[1]}</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------------------------ leaderboard -
st.subheader("Leaderboard")
st.caption("Click a column header to sort. Select a player row for a round-by-round breakdown.")

selected_player = None
for team_idx, team_name in enumerate(team_names[:2]):
    st.markdown(f"#### {team_name}")
    team_df = df[df["Team"] == team_idx].drop(columns=["Team"]).rename(columns={"Rating": "Rating ▼"})
    team_df = team_df.reset_index(drop=True)
    if team_df.empty:
        st.caption("No players found for this team.")
        continue
    event = st.dataframe(
        team_df,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"leaderboard_team_{team_idx}",
    )
    if event and event.selection and event.selection.get("rows"):
        selected_player = team_df.iloc[event.selection["rows"][0]]["Player"]

    team_players = [s.name for s in stats.values() if s.team == team_idx]
    cols = st.columns(5)
    for i, name in enumerate(team_players):
        if cols[i % 5].button(name, width="stretch", key=f"btn_{name}"):
            selected_player = name


@st.dialog("Round-by-round breakdown", width="large")
def show_player_modal(player_name: str):
    s = stats[player_name]
    st.markdown(f"### {s.name}  ·  Rating **{s.rating}**")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("K / D", f"{s.kills} / {s.deaths}")
    m2.metric("Entry K / D", f"{s.entry_kills} / {s.entry_deaths}")
    m3.metric("KOST%", f"{s.kost_pct:.1f}%")
    m4.metric("Clutches", s.total_clutches)
    m5.metric("Plants / Defuses", f"{s.plants} / {s.defuses}")

    st.divider()
    for rb in s.round_breakdown:
        icon = "🟢" if rb.survived else "🔴"
        st.markdown(f"**{icon} Round {rb.round_num}** — {rb.summary()}")


if selected_player:
    show_player_modal(selected_player)

# ------------------------------------------------------------ footer -----
st.divider()
st.caption(
    "Rating is a from-scratch approximation built from KPR, DPR, entry differential, "
    "KOST, multi-kills and clutches, z-scored against this match's roster and centered at 1.00. "
    "It is not SiegeGG's exact proprietary formula."
)
