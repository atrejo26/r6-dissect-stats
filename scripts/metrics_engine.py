"""
metrics_engine.py
==================
Computes T1-style competitive metrics from a normalized MatchData dict
(see parser.py). Formulas follow the public definitions used by
competitive R6 stat sites (SiegeGG, Stats.cc):

- Entry kill/death: the FIRST kill/death of the round (whole round, not
  per-site attacker/defender split).
- Trade: a death is "traded" if a teammate of the dead player kills that
  player's killer within TRADE_WINDOW_SECONDS afterward.
- KOST: percent of rounds where a player got a Kill, an Objective
  (plant/defuse), Survived, or was Traded.
- Clutch: winning a round as the last player alive on your team while
  1+ enemies are still alive, sized 1v1..1v5 by opponents alive at that
  moment.
- Rating: a from-scratch approximation of SiegeGG's "Rating" stat --
  NOT their exact proprietary formula (never published), but built from
  the same public ingredients they cite: KPR, DPR, entry differential,
  KOST, multi-kills, and clutches, z-scored against the match and
  recentered at 1.00. Treat this as a best-effort replica, not a byte-
  for-byte match to SiegeGG's own number.

AUTHORITATIVE VS. DERIVED STATS: r6-dissect computes kills, deaths,
assists, headshots, and clutch size (1vX) per round itself (from the
replay's own internal round-end scoreboard, not just the kill feed) and
exposes them via each round's "stats" list. When parser.py's normalizer
finds that data, this engine trusts it over anything we'd derive by
replaying "events" ourselves -- it's more reliable, and it's the only
source of real assist numbers (assist attribution needs damage data we
don't otherwise have). "events" (the kill feed) is still needed for
things "stats" doesn't carry at all: entry kills/deaths, trades, and
plant/defuse credit. The bundled demo match (sample_data.py) has no
"stats" data, so those fields are derived from its events instead --
this is why assists show as 0 in demo mode but populate correctly for
real parsed replays.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TRADE_WINDOW_SECONDS = 5.0


@dataclass
class RoundBreakdown:
    round_num: int
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    survived: bool = True
    entry_kill: bool = False
    entry_death: bool = False
    traded: bool = False
    planted: bool = False
    defused: bool = False
    clutch: str | None = None  # e.g. "1v2"
    headshots: int = 0
    assists: int = 0
    kost: bool = False

    def summary(self) -> str:
        bits = []
        if self.kills:
            bits.append(f"{self.kills}K")
        if self.assists:
            bits.append(f"{self.assists}A")
        if self.deaths:
            bits.append("died")
        else:
            bits.append("survived")
        if self.entry_kill:
            bits.append("entry kill")
        if self.entry_death:
            bits.append("entry death")
        if self.traded:
            bits.append("traded")
        if self.planted:
            bits.append("planted")
        if self.defused:
            bits.append("defused")
        if self.clutch:
            bits.append(f"clutched {self.clutch}")
        return ", ".join(bits) if bits else "no impact"


@dataclass
class PlayerStats:
    name: str
    team: int
    rounds_played: int = 0
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    headshots: int = 0
    entry_kills: int = 0
    entry_deaths: int = 0
    trades: int = 0
    plants: int = 0
    defuses: int = 0
    kost_rounds: int = 0
    clutches: dict = field(default_factory=lambda: {i: 0 for i in range(1, 6)})
    multikill_rounds: int = 0
    round_breakdown: list = field(default_factory=list)
    rating: float = 1.0

    @property
    def kd(self) -> float:
        return self.kills / self.deaths if self.deaths else float(self.kills)

    @property
    def kda(self) -> float:
        return (self.kills + self.assists) / self.deaths if self.deaths else float(self.kills + self.assists)

    @property
    def kost_pct(self) -> float:
        return 100.0 * self.kost_rounds / self.rounds_played if self.rounds_played else 0.0

    @property
    def kpr(self) -> float:
        return self.kills / self.rounds_played if self.rounds_played else 0.0

    @property
    def dpr(self) -> float:
        return self.deaths / self.rounds_played if self.rounds_played else 0.0

    @property
    def total_clutches(self) -> int:
        return sum(self.clutches.values())


def _team_of(players: list[dict]) -> dict[str, int]:
    return {p["name"]: p["team"] for p in players}


def _process_round(rnd: dict, team_of: dict[str, int], stats: dict[str, PlayerStats]) -> None:
    # Event list is consumed in the order the parser emitted it, which is
    # r6-dissect's own chronological append order (see parser.py). We do
    # NOT sort by "time" here: whether that clock counts up or down from
    # the parser isn't confirmed, and array order is the reliable signal.
    events = rnd["events"]
    round_num = rnd["round_num"]
    winner_team = rnd["winner_team"]

    alive = {0: set(), 1: set()}
    for name, t in team_of.items():
        alive[t].add(name)

    rb = {name: RoundBreakdown(round_num=round_num) for name in team_of}
    first_kill_seen = False
    kill_events = []       # (idx, time, killer, victim, headshot)
    death_meta = []        # (idx, time, victim, killer) for trade detection

    clutch_candidate = None   # name currently alone vs opponents
    clutch_size = None

    for idx, e in enumerate(events):
        actor = e.get("actor")
        if actor is not None and actor not in rb:
            continue  # unknown/unrostered player in the feed -- skip rather than crash

        if e["type"] == "kill":
            kill_events.append((idx, e["time"], actor, e.get("target"), e.get("headshot", False)))
            rb[actor].kills += 1
            if e.get("headshot"):
                rb[actor].headshots += 1
            if not first_kill_seen:
                rb[actor].entry_kill = True
                first_kill_seen = True

        elif e["type"] == "death":
            victim, killer = actor, e.get("killed_by")
            rb[victim].deaths += 1
            rb[victim].survived = False
            if not death_meta:
                rb[victim].entry_death = True
            death_meta.append((idx, e["time"], victim, killer))
            vt = team_of[victim]
            alive[vt].discard(victim)

            # clutch tracking: check right after this death whether either
            # team has been reduced to exactly one alive player, with the
            # other team still having survivors.
            for t in (0, 1):
                other = 1 - t
                if clutch_candidate is None and len(alive[t]) == 1 and len(alive[other]) >= 1:
                    clutch_candidate = next(iter(alive[t]))
                    clutch_size = len(alive[other])

        elif e["type"] == "plant":
            rb[actor].planted = True
        elif e["type"] == "defuse":
            rb[actor].defused = True

    # trade detection: a death is traded if a teammate of the victim kills
    # that victim's killer afterward (later in feed order), within
    # TRADE_WINDOW_SECONDS of real time (absolute delta -- the clock
    # direction convention doesn't matter for a duration).
    for (d_idx, dtime, victim, killer) in death_meta:
        if killer is None or victim not in team_of or killer not in team_of:
            continue
        victim_team = team_of[victim]
        for (k_idx, ktime, ke_killer, ke_target, _hs) in kill_events:
            if ke_target != killer or k_idx <= d_idx:
                continue
            if abs(ktime - dtime) > TRADE_WINDOW_SECONDS:
                continue
            if team_of.get(ke_killer) == victim_team and ke_killer != victim:
                rb[victim].traded = True
                break

    # credit the clutch only if the clutch candidate's team actually won
    # the round and that player survived to the end.
    if clutch_candidate is not None and rb[clutch_candidate].survived:
        if team_of[clutch_candidate] == winner_team:
            size = min(max(clutch_size, 1), 5)
            rb[clutch_candidate].clutch = f"1v{size}"

    # r6-dissect computes kills/deaths/assists/headshots/clutch size per
    # round itself, from the replay's own round-end scoreboard -- trust
    # that over what we just derived from the feed, when it's available.
    round_stats = rnd.get("round_stats")
    if round_stats:
        for name, r in rb.items():
            auth = round_stats.get(name)
            if not auth:
                continue
            r.kills = auth["kills"]
            r.deaths = 1 if auth["died"] else 0
            r.survived = not auth["died"]
            r.headshots = auth["headshots"]
            r.assists = auth["assists"]
            if auth["onevx"]:
                r.clutch = f"1v{min(max(auth['onevx'], 1), 5)}"

    # finalize KOST + accumulate into overall stats
    for name, r in rb.items():
        r.kost = bool(r.kills or r.planted or r.defused or r.survived or r.traded)
        s = stats[name]
        s.rounds_played += 1
        s.kills += r.kills
        s.deaths += r.deaths
        s.assists += r.assists
        s.headshots += r.headshots
        s.plants += 1 if r.planted else 0
        s.defuses += 1 if r.defused else 0
        s.entry_kills += 1 if r.entry_kill else 0
        s.entry_deaths += 1 if r.entry_death else 0
        s.trades += 1 if r.traded else 0
        s.kost_rounds += 1 if r.kost else 0
        if r.kills >= 2:
            s.multikill_rounds += 1
        if r.clutch:
            size = int(r.clutch[-1])
            s.clutches[size] += 1
        s.round_breakdown.append(r)


def _compute_ratings(stats: dict[str, PlayerStats]) -> None:
    """z-score-normalize the key ingredients across the 10 players in this
    match and recenter around 1.00, mirroring how competitive ratings are
    presented (roughly 0.6 - 1.4 range, 1.00 = match-average performance).
    """
    players = list(stats.values())
    n = len(players)
    if n == 0:
        return

    def avg(vals):
        return sum(vals) / len(vals) if vals else 0.0

    def std(vals, mean):
        if len(vals) < 2:
            return 1.0
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        return var ** 0.5 or 1.0

    kpr_vals = [p.kpr for p in players]
    dpr_vals = [p.dpr for p in players]
    kost_vals = [p.kost_pct for p in players]
    entry_diff_vals = [(p.entry_kills - p.entry_deaths) / p.rounds_played if p.rounds_played else 0.0 for p in players]
    multikill_vals = [p.multikill_rounds / p.rounds_played if p.rounds_played else 0.0 for p in players]
    clutch_vals = [p.total_clutches / p.rounds_played if p.rounds_played else 0.0 for p in players]

    kpr_mean, kpr_sd = avg(kpr_vals), std(kpr_vals, avg(kpr_vals))
    dpr_mean, dpr_sd = avg(dpr_vals), std(dpr_vals, avg(dpr_vals))
    kost_mean, kost_sd = avg(kost_vals), std(kost_vals, avg(kost_vals))
    ed_mean, ed_sd = avg(entry_diff_vals), std(entry_diff_vals, avg(entry_diff_vals))
    mk_mean, mk_sd = avg(multikill_vals), std(multikill_vals, avg(multikill_vals))
    cl_mean, cl_sd = avg(clutch_vals), std(clutch_vals, avg(clutch_vals))

    # weights: kills and entries matter most for T1 "impact" ratings,
    # deaths penalize, KOST rewards consistent round presence.
    W_KPR, W_DPR, W_KOST, W_ENTRY, W_MULTI, W_CLUTCH = 0.30, 0.22, 0.20, 0.16, 0.07, 0.05

    for p in players:
        z_kpr = (p.kpr - kpr_mean) / kpr_sd
        z_dpr = (p.dpr - dpr_mean) / dpr_sd   # higher deaths -> positive z -> subtract
        z_kost = (p.kost_pct - kost_mean) / kost_sd
        z_entry = ((p.entry_kills - p.entry_deaths) / p.rounds_played - ed_mean) / ed_sd if p.rounds_played else 0.0
        z_multi = (p.multikill_rounds / p.rounds_played - mk_mean) / mk_sd if p.rounds_played else 0.0
        z_clutch = (p.total_clutches / p.rounds_played - cl_mean) / cl_sd if p.rounds_played else 0.0

        composite = (
            W_KPR * z_kpr
            - W_DPR * z_dpr
            + W_KOST * z_kost
            + W_ENTRY * z_entry
            + W_MULTI * z_multi
            + W_CLUTCH * z_clutch
        )
        # recenter at 1.00, ~0.15 rating points per composite std-dev unit
        p.rating = round(1.00 + 0.15 * composite, 3)


def compute_match_metrics(match: dict) -> dict[str, PlayerStats]:
    """Main entry point. Returns {player_name: PlayerStats}."""
    team_of = _team_of(match["players"])
    stats = {name: PlayerStats(name=name, team=t) for name, t in team_of.items()}

    for rnd in match["rounds"]:
        _process_round(rnd, team_of, stats)

    _compute_ratings(stats)
    return stats


def leaderboard_rows(stats: dict[str, PlayerStats]) -> list[dict]:
    """Flattened rows ready for a dataframe/table, sorted by rating desc."""
    rows = []
    for s in stats.values():
        rows.append({
            "Player": s.name,
            "Team": s.team,
            "Rating": s.rating,
            "K": s.kills,
            "D": s.deaths,
            "A": s.assists,
            "K/D": round(s.kd, 2),
            "Entry K": s.entry_kills,
            "Entry D": s.entry_deaths,
            "Plants": s.plants,
            "Defuses": s.defuses,
            "Clutches": s.total_clutches,
            "KOST%": round(s.kost_pct, 1),
            "HS%": round(100 * s.headshots / s.kills, 1) if s.kills else 0.0,
        })
    rows.sort(key=lambda r: r["Rating"], reverse=True)
    return rows
