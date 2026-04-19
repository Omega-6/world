"""
VEX Worlds 2026 Research Division - Team Stats Builder
Event: RE-V5RC-26-4025 (Research Division)
Season: V5RC 2025-2026 Push Back (ID 197)

Pulls season-wide stats from RobotEvents + TrueSkill from vrc-data-analysis.
Outputs:
  - Worlds2026_Research_Division_Stats.csv
  - Worlds2026_Research_Division_WinRate.png (wins vs total games scatter)
"""

import re
import requests
import pandas as pd
import concurrent.futures
import time
import matplotlib.pyplot as plt


def natural_key(num):
    m = re.match(r"(\d+)(.*)", str(num))
    return (int(m.group(1)), m.group(2)) if m else (0, str(num))

# ---------- CONFIG ----------
ROBOTEVENTS_API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIzIiwianRpIjoiMWU4OWE4NTUzMjNjNmE2MGExZGY4NDY2YWE3MTExNDk0NDY0NzlmOTQzMmQxYzFkMjM5YjkxNTNjNDM5NWVkNzlmOTFjMzJkNGFjY2Y3YTEiLCJpYXQiOjE3NzY1NjY1NjMuNzQ4NjQ4OSwibmJmIjoxNzc2NTY2NTYzLjc0ODY1MDEsImV4cCI6MjcyMzMzNzc2My43NDIxODg5LCJzdWIiOiIxNTYzMjYiLCJzY29wZXMiOltdfQ.rK-xf3VKfU89pnxZDOwOJD9Jfa_JMovWAq7d8SnUqutuHE51_VEYQPbs6aejfSy9IsTE2sSaPwCA62HKPTk-ybROBsGn8ARRpO3Sdub3HjPPioQlrUa6jOz_Ayhn_Ss-3PxEG0iPcN_G6mAGOFDdzjLyKzRehLU_ijetKjTmtNnMNgj5Um9z0gAPuovhCVLjObEkAlipzTM5SA4BDR1irhfhPmmsyJe59zEW02o6kT2vVqS-STJDriyxAzW6RuUd82McwtMRNgN8C4X8vXbAgPjx1XVlNtTTroRpR09a4U5VbFXU1ec30eV8vNZo0UgqusX-lTQBV_sSspkAFkxY1LpHt-rLTY9unlbcy6ilMMkApM_KcVU3p-j1qpoFwMiWFfYYrQCbL-vYsIpRoo42GQs3CcN9ZrvMAjAs95wAXurJzLYD2Q3_9cRax-mY11nL5SQoFHXhwppSPNno-U8HL9xo7tHl9D2WMzWF3Jb-ddyOiYDknofWPQXL82jLs3f4Ra7g7K4fIfnG53ZiSJy3BOjOFGBnGng3SY0b4zdVT9EWBbZO6sjhMunJhSlVlf9hPfE9NTJfvTjKUvoAIDdOKZxHnOCJcdlU_fmm6L72I9k_Igw4dihw7X_LVtlYdQ8j9acO3sk5umBof9huFs34bV2qFkfShX7sCwEgs_RH-qo"
SEASON_ID = 197  # V5RC Push Back 2025-2026
OUTPUT_CSV = "Worlds2026_Research_Division_Stats.csv"
OUTPUT_HISTORY_CSV = "Worlds2026_Research_Division_History.csv"
OUTPUT_AWARDS_CSV = "Worlds2026_Research_Division_Awards.csv"
OUTPUT_PNG = "Worlds2026_Research_Division_WinRate.png"

# Team list parsed from RE-V5RC-26-4025 PDF (Research Division, 86 teams)
TEAMS = [
    "12Z", "81Z", "169X", "291Z", "344E", "526C", "727G", "901Z", "1022W", "1104V",
    "1412J", "1585B", "1727K", "1791V", "2011F", "2115P", "2147Z", "2360C", "2501S", "2602K",
    "2815Z", "3134G", "3204A", "3588X", "3796D", "4142C", "4588B", "4886W", "5155E", "5691A",
    "6008G", "6210M", "6403Z", "7110A", "7262A", "7486A", "7862W", "8076X", "8448X", "8894X",
    "9061X", "9189X", "9784A", "10102Z", "11101K", "11753A", "12914X", "13722A", "14895D", "16099B",
    "17280A", "18908H", "20132B", "21052A", "22532V", "26455A", "29204B", "32092G", "34001B", "36930X",
    "39792E", "43141Z", "44077T", "46366A", "51548B", "54001A", "56448A", "59735X", "62629K", "64040B",
    "66954A", "69580A", "71909X", "74403W", "76502A", "78634E", "80080X", "81988B", "84443F", "87867C",
    "91142A", "95071V", "96789Z", "98115A", "98601C", "99750A"
]

HEADERS = {"Authorization": f"Bearer {ROBOTEVENTS_API_KEY}", "Accept": "application/json"}


def re_get(url, max_tries=5):
    """GET with 429-aware backoff. Returns parsed JSON or None."""
    for attempt in range(max_tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 0)) or (2 ** attempt + 1)
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600:
                time.sleep(2 ** attempt)
                continue
            return None
        except Exception:
            time.sleep(2 ** attempt)
    return None


def batch_resolve_teams(team_nums):
    """One-shot lookup for all V5RC team IDs. Returns {num: (id, name)}."""
    from urllib.parse import urlencode
    out = {}
    # RE caps query-string length; chunk to be safe
    CHUNK = 40
    for i in range(0, len(team_nums), CHUNK):
        chunk = team_nums[i:i + CHUNK]
        params = [("number[]", n) for n in chunk] + [("program[]", 1), ("per_page", 250)]
        url = "https://www.robotevents.com/api/v2/teams?" + urlencode(params)
        for attempt in range(3):
            try:
                r = requests.get(url, headers=HEADERS, timeout=30)
                if r.status_code == 200:
                    for t in r.json().get("data", []):
                        prog = t.get("program", {}) or {}
                        if prog.get("id") != 1:
                            continue
                        num = t.get("number")
                        if num in out:
                            continue
                        out[num] = (t.get("id"), t.get("team_name", ""))
                    break
                if r.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                print(f"  [resolve HTTP {r.status_code}] chunk {i}-{i+len(chunk)}")
                break
            except Exception as e:
                print(f"  [resolve err] {e}")
                time.sleep(2 ** attempt)
    return out


ROUND_LABEL = {3: "R16", 4: "QF", 5: "SF", 6: "F"}


def fetch_playoff_depth(team_id):
    """Return {event_id: deepest_round_label} using the matches endpoint.
    Round labels: 'R16', 'QF', 'SF', 'F'. (Qual-only events are omitted.)
    'Champ' is applied later by crosschecking awards."""
    data = re_get(f"https://www.robotevents.com/api/v2/teams/{team_id}/matches?season%5B%5D={SEASON_ID}&per_page=250")
    if not data:
        return {}
    best = {}  # event_id -> max round (int)
    for m in data.get("data", []):
        rnd = m.get("round")
        if not rnd or rnd < 3:  # skip practice(1) and qualification(2)
            continue
        eid = (m.get("event") or {}).get("id")
        if eid is None:
            continue
        if rnd > best.get(eid, 0):
            best[eid] = rnd
    return {eid: ROUND_LABEL[r] for eid, r in best.items() if r in ROUND_LABEL}


def fetch_rankings(team_id, event_dates=None):
    """Sum season totals, plus return per-event history rows."""
    wins = losses = ties = events = rank_sum = 0
    history = []
    data = re_get(f"https://www.robotevents.com/api/v2/teams/{team_id}/rankings?season%5B%5D={SEASON_ID}&per_page=250")
    if data:
        for rk in data.get("data", []):
            w = rk.get("wins", 0) or 0
            l = rk.get("losses", 0) or 0
            t = rk.get("ties", 0) or 0
            rank = rk.get("rank", 0) or 0
            wins += w; losses += l; ties += t; rank_sum += rank; events += 1
            ev = rk.get("event", {}) or {}
            ev_id = ev.get("id")
            total_m = w + l + t
            history.append({
                "event_id": ev_id,
                "event_name": ev.get("name", "Unknown"),
                "event_date": (event_dates or {}).get(ev_id, ""),
                "rank": rank,
                "wins": w,
                "losses": l,
                "ties": t,
                "matches": total_m,
                "winrate_pct": round((w / total_m) * 100, 1) if total_m else 0.0,
            })
    avg_rank = round(rank_sum / events, 2) if events else 0.0
    total = wins + losses + ties
    winrate = round((wins / total) * 100, 1) if total else 0.0
    return {
        "avg_qual_rank": avg_rank,
        "events_attended": events,
        "total_matches": total,
        "total_wins": wins,
        "total_losses": losses,
        "total_ties": ties,
        "winrate_pct": winrate,
    }, history


def fetch_all_event_dates():
    """One-shot: build {event_id: start_date} for the whole V5RC season."""
    dates = {}
    page = 1
    while True:
        data = re_get(f"https://www.robotevents.com/api/v2/events?season%5B%5D={SEASON_ID}&per_page=250&page={page}")
        if not data:
            break
        for ev in data.get("data", []):
            dates[ev.get("id")] = (ev.get("start") or "")[:10]
        meta = data.get("meta", {})
        if meta.get("current_page", 0) >= meta.get("last_page", 0):
            break
        page += 1
    return dates


def fetch_awards(team_id):
    data = re_get(f"https://www.robotevents.com/api/v2/teams/{team_id}/awards?season%5B%5D={SEASON_ID}&per_page=250")
    return len(data.get("data", [])) if data else 0


def fetch_skills(team_id):
    """Max driver + programming scores across the season."""
    driver = prog = 0
    data = re_get(f"https://www.robotevents.com/api/v2/teams/{team_id}/skills?season%5B%5D={SEASON_ID}&per_page=250")
    if data:
        for s in data.get("data", []):
            score = s.get("score", 0) or 0
            if s.get("type") == "driver" and score > driver:
                driver = score
            elif s.get("type") == "programming" and score > prog:
                prog = score
    return driver, prog


TRUESKILL_ENABLED = True  # flipped off by probe_trueskill if service is down


def probe_trueskill():
    """One-shot health check for vrc-data-analysis. Disables TS fetches if down."""
    global TRUESKILL_ENABLED
    try:
        r = requests.get("https://vrc-data-analysis.com/v1/team/81Z", timeout=8)
        if r.status_code == 200 and r.json().get("trueskill") is not None:
            print("TrueSkill source: vrc-data-analysis.com OK")
            return
        print(f"TrueSkill source returned {r.status_code} — skipping TS columns (set to 0)")
    except Exception as e:
        print(f"TrueSkill source unreachable ({e.__class__.__name__}) — skipping TS columns (set to 0)")
    TRUESKILL_ENABLED = False


def fetch_awards_detailed(team_id, event_dates):
    """Return (count, list of per-award dicts)."""
    data = re_get(f"https://www.robotevents.com/api/v2/teams/{team_id}/awards?season%5B%5D={SEASON_ID}&per_page=250")
    rows = []
    if data:
        for a in data.get("data", []):
            ev = a.get("event", {}) or {}
            rows.append({
                "Event Date": event_dates.get(ev.get("id"), ""),
                "Event Name": ev.get("name", ""),
                "Event ID": ev.get("id"),
                "Award": a.get("title", ""),
            })
    return len(rows), rows


def fetch_trueskill(team_num):
    if not TRUESKILL_ENABLED:
        return 0, 0.0
    try:
        r = requests.get(f"https://vrc-data-analysis.com/v1/team/{team_num}", timeout=10)
        if r.status_code == 200:
            d = r.json()
            return d.get("trueskill_ranking", 0) or 0, round(d.get("trueskill", 0) or 0, 2)
    except Exception:
        pass
    return 0, 0.0


def process(team_num, tid, tname, event_dates):
    history_rows = []
    award_rows = []
    row = {
        "Team Number": team_num,
        "Team Name": tname or "",
        "Avg Qual Rank": 0.0,
        "Events Attended": 0,
        "Total Awards": 0,
        "Total Matches": 0,
        "Total Wins": 0,
        "Total Losses": 0,
        "Total Ties": 0,
        "Winrate %": 0.0,
        "Combined Skills": 0,
        "Driver Skills": 0,
        "Programming Skills": 0,
        "TrueSkill Ranking": 0,
        "TrueSkill Score": 0.0,
    }
    if tid is None:
        print(f"  [WARN] could not resolve {team_num}")
        ts_rank, ts_score = fetch_trueskill(team_num)
        row["TrueSkill Ranking"] = ts_rank
        row["TrueSkill Score"] = ts_score
        return row, history_rows, award_rows

    ranks, history = fetch_rankings(tid, event_dates)
    depth_by_event = fetch_playoff_depth(tid)
    awards, award_details = fetch_awards_detailed(tid, event_dates)
    # Build event_id -> depth override from awards:
    # "Tournament Champions" -> "Champ", "Finalists" -> "F" (already covered by matches but safe).
    for a in award_details:
        title = (a.get("Award") or "").lower()
        eid = a.get("Event ID")
        if eid is None:
            continue
        if "tournament champion" in title:
            depth_by_event[eid] = "Champ"
        elif "tournament finalist" in title and depth_by_event.get(eid) != "Champ":
            depth_by_event[eid] = "F"
    for h in history:
        h["Team Number"] = team_num
        h["Playoff Depth"] = depth_by_event.get(h.get("event_id"), "Qual")
        history_rows.append(h)
    for a in award_details:
        a["Team Number"] = team_num
        award_rows.append(a)
    driver, prog = fetch_skills(tid)
    ts_rank, ts_score = fetch_trueskill(team_num)

    row.update({
        "Avg Qual Rank": ranks["avg_qual_rank"],
        "Events Attended": ranks["events_attended"],
        "Total Awards": awards,
        "Total Matches": ranks["total_matches"],
        "Total Wins": ranks["total_wins"],
        "Total Losses": ranks["total_losses"],
        "Total Ties": ranks["total_ties"],
        "Winrate %": ranks["winrate_pct"],
        "Combined Skills": driver + prog,
        "Driver Skills": driver,
        "Programming Skills": prog,
        "TrueSkill Ranking": ts_rank,
        "TrueSkill Score": ts_score,
    })
    return row, history_rows, award_rows


def make_graph(df):
    fig, ax = plt.subplots(figsize=(12, 8))
    x = df["Total Matches"]
    y = df["Total Wins"]
    colors = df["Winrate %"]
    sc = ax.scatter(x, y, c=colors, cmap="viridis", s=60, edgecolors="black", linewidths=0.5)

    max_m = max(x.max(), 1)
    ax.plot([0, max_m], [0, max_m], "r--", alpha=0.3, label="100% winrate")
    ax.plot([0, max_m], [0, max_m * 0.5], "gray", linestyle=":", alpha=0.3, label="50% winrate")

    # label notable teams (top 10 by wins)
    top = df.nlargest(10, "Total Wins")
    for _, r in top.iterrows():
        ax.annotate(r["Team Number"], (r["Total Matches"], r["Total Wins"]),
                    fontsize=7, xytext=(4, 4), textcoords="offset points")

    ax.set_xlabel("Total Matches Played (Season)")
    ax.set_ylabel("Total Wins")
    ax.set_title("Worlds 2026 Research Division — Wins vs Total Games (V5RC Push Back Season)")
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3)
    plt.colorbar(sc, ax=ax, label="Winrate %")
    plt.tight_layout()
    plt.savefig(OUTPUT_PNG, dpi=150)
    print(f"Graph saved -> {OUTPUT_PNG}")


def main():
    probe_trueskill()
    print(f"Resolving team IDs for {len(TEAMS)} teams...")
    id_map = batch_resolve_teams(TEAMS)
    missing = [t for t in TEAMS if t not in id_map]
    print(f"Resolved {len(id_map)}/{len(TEAMS)}. Missing: {missing if missing else 'none'}")

    print("Fetching season event calendar for dates...")
    event_dates = fetch_all_event_dates()
    print(f"  got {len(event_dates)} events")

    print(f"Processing stats...")
    start = time.time()
    rows = []
    history_all = []
    awards_all = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            ex.submit(process, t, *id_map.get(t, (None, None)), event_dates): t
            for t in TEAMS
        }
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            row, hist, awards = fut.result()
            rows.append(row)
            history_all.extend(hist)
            awards_all.extend(awards)
            print(f"  [{i:>2}/{len(TEAMS)}] {row['Team Number']:<8} "
                  f"W:{row['Total Wins']:<3} L:{row['Total Losses']:<3} "
                  f"evts:{len(hist)} awds:{len(awards)} TS:{row['TrueSkill Score']}")

    df = pd.DataFrame(rows)
    df["_sort"] = df["Team Number"].map(natural_key)
    df = df.sort_values("_sort").drop(columns="_sort").reset_index(drop=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nCSV saved -> {OUTPUT_CSV}  ({len(df)} teams, {time.time()-start:.1f}s)")

    hist_df = pd.DataFrame(history_all)
    if not hist_df.empty:
        hist_df = hist_df.rename(columns={
            "event_id": "Event ID", "event_name": "Event Name", "event_date": "Event Date",
            "rank": "Rank", "wins": "Wins", "losses": "Losses", "ties": "Ties",
            "matches": "Matches", "winrate_pct": "Winrate %",
        })
        hist_df["_sort_team"] = hist_df["Team Number"].map(natural_key)
        hist_df = hist_df.sort_values(["_sort_team", "Event Date"]).drop(columns="_sort_team").reset_index(drop=True)
        hist_df = hist_df[["Team Number", "Event Date", "Event Name", "Event ID",
                           "Rank", "Wins", "Losses", "Ties", "Matches", "Winrate %",
                           "Playoff Depth"]]
        hist_df.to_csv(OUTPUT_HISTORY_CSV, index=False)
        print(f"History saved -> {OUTPUT_HISTORY_CSV}  ({len(hist_df)} event rows)")

    awd_df = pd.DataFrame(awards_all)
    if not awd_df.empty:
        awd_df["_sort_team"] = awd_df["Team Number"].map(natural_key)
        awd_df = awd_df.sort_values(["_sort_team", "Event Date"]).drop(columns="_sort_team").reset_index(drop=True)
        awd_df = awd_df[["Team Number", "Event Date", "Event Name", "Event ID", "Award"]]
        awd_df.to_csv(OUTPUT_AWARDS_CSV, index=False)
        print(f"Awards saved -> {OUTPUT_AWARDS_CSV}  ({len(awd_df)} award rows)")

    make_graph(df)


if __name__ == "__main__":
    main()
