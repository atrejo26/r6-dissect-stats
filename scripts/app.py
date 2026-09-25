"""
app.py
======
Streamlit dashboard for the R6 T1 telemetry tool.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from metrics_engine import compute_match_metrics, leaderboard_rows
from parser import parse_replay, load_demo_match, r6_dissect_available, ReplayParseError, raw_shape_preview

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
    st.caption("Upload a `.rec` replay to generate a full T1-style performance report.")
    if r6_dissect_available():
        st.success("r6-dissect detected on PATH", icon="✅")
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
    st.markdown('<div class="upload-zone">', unsafe_allow_html=True)
    uploaded = st.file_uploader("Drop a .rec replay file here", type=["rec"], label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

    if uploaded is not None:
        with st.spinner("Parsing replay..."):
            try:
                with tempfile.TemporaryDirectory() as td:
                    tmp_path = Path(td) / uploaded.name
                    tmp_path.write_bytes(uploaded.getbuffer())
                    match, raw = parse_replay(str(tmp_path))
            except ReplayParseError as e:
                error = str(e)

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

display_df = df.drop(columns=["Team"]).rename(columns={"Rating": "Rating ▼"})
event = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)

selected_player = None
if event and event.selection and event.selection.get("rows"):
    idx = event.selection["rows"][0]
    selected_player = display_df.iloc[idx]["Player"]

st.caption("Or pick a player directly:")
cols = st.columns(5)
for i, name in enumerate(stats.keys()):
    if cols[i % 5].button(name, use_container_width=True, key=f"btn_{name}"):
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
