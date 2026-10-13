"""
Step 8 (exploratory): Sankey of follow-up retention by health zone.

x = day of follow-up (day 1 = first recorded follow-up); each column stacks the contacts
still under follow-up on that day, coloured by health zone of the source case. A contact is
'still followed' on day d if a follow-up RESULT was recorded on day d or later (so contacts
only ever leave; nobody returns). Contacts leave to:
  grey  'Not followed up' -- after their last recorded result (or from day 1 if none)
  coral 'Became a case'   -- secondary cases, at the day they were detected
Population: closed windows (first follow-up on/before data cut - 21 days), as for Figure 3D.
Writes figures/figS2_followup_sankey.png (daily status; manuscript Fig S2), figures/additional/followup_sankey_retention.png and tables/followup_retention_by_day.csv
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path

from ctr_paths import D, T, F, FA

INK, MUTED, ALERT, SUB = "#01454f", "#a3b9bc", "#e0703f", "#4a7378"
NOFU, CASE = "#d9dedf", "#f2b79c"
PAL = ["#01454f", "#1a8c99", "#c9a227", "#7a5c99", "#5b8c5a", "#a8322d", "#d17fa8", "#4f6d9a", "#8c8c8c"]
BASE = 8.5
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans"], "font.size": BASE, "text.color": INK, "axes.labelcolor": INK,
                     "xtick.color": INK, "ytick.color": INK, "axes.edgecolor": INK, "axes.linewidth": 0.5,
                     "figure.facecolor": "white", "savefig.dpi": 300, "savefig.bbox": "tight"})
N_DAYS, N_ZONES = 21, 8

pr = pd.read_csv(os.path.join(D, "pairs_annotated.csv"), low_memory=False,
                 parse_dates=["fu_start", "last_result_date", "detect_date"])
p = pr[pr.fu_ff_eligible.astype(bool)].copy()
p["last_day"] = ((p.last_result_date - p.fu_start).dt.days + 1).fillna(0).clip(lower=0, upper=N_DAYS).astype(int)
p["case_day"] = ((p.detect_date - p.fu_start).dt.days + 1).where(p.secondary_case.astype(bool))
# exit day = first day NOT followed; cases leave at detection if that is within the window
p["exit_day"] = p.last_day + 1
p["exit_to"] = "nofu"
is_case = p.case_day.notna() & (p.case_day <= N_DAYS)
p.loc[is_case, "exit_day"] = p.loc[is_case, "case_day"].clip(lower=1).astype(int)
p.loc[is_case, "exit_to"] = "case"
p.loc[p.exit_day > N_DAYS, "exit_to"] = "completed"

top = p.src_health_zone.value_counts().head(N_ZONES).index.tolist()
p["zone"] = np.where(p.src_health_zone.isin(top), p.src_health_zone, "Other")
zones = top + ["Other"]
col = dict(zip(zones, PAL))

days = np.arange(1, N_DAYS + 1)
# counts[d][zone] = still followed on day d ; nofu[d], case[d] cumulative leavers before day d
ret = pd.DataFrame({z: [((p.zone == z) & (p.exit_day > d)).sum() for d in days] for z in zones}, index=days)
nofu = pd.Series([((p.exit_to == "nofu") & (p.exit_day <= d)).sum() for d in days], index=days)
case = pd.Series([((p.exit_to == "case") & (p.exit_day <= d)).sum() for d in days], index=days)
tab = ret.copy(); tab["Not followed up (cum.)"] = nofu; tab["Became a case (cum.)"] = case
tab.index.name = "followup_day"; tab.to_csv(os.path.join(T, "followup_retention_by_day.csv"))
total = len(p)

# --------------------------------------------------------------------- draw
fig, ax = plt.subplots(figsize=(9.2, 5.2))
W = 0.36                       # column width
GAP = total * 0.006            # gap between blocks


def stack(d):
    """y-ranges of blocks in column d (bottom->top): not followed, became case, zones (last zone on top)."""
    y, out = 0.0, {}
    for key, h in [("nofu", nofu[d]), ("case", case[d])] + [(z, ret.loc[d, z]) for z in reversed(zones)]:
        out[key] = (y, y + h); y += h + (GAP if h > 0 else 0)
    return out


def ribbon(x0, y0a, y0b, x1, y1a, y1b, color, alpha=0.45):
    if y0b - y0a <= 0 and y1b - y1a <= 0:
        return
    xm = (x0 + x1) / 2
    verts = [(x0, y0a), (xm, y0a), (xm, y1a), (x1, y1a), (x1, y1b), (xm, y1b), (xm, y0b), (x0, y0b), (x0, y0a)]
    codes = [Path.MOVETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.LINETO, Path.CURVE4, Path.CURVE4, Path.CURVE4, Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(verts, codes), fc=color, ec="none", alpha=alpha, lw=0))


stacks = {d: stack(d) for d in days}
for d in days:
    for key, (a, b) in stacks[d].items():
        if b > a:
            c = NOFU if key == "nofu" else CASE if key == "case" else col[key]
            ax.add_patch(plt.Rectangle((d - W / 2, a), W, b - a, fc=c, ec="none"))
for d in days[:-1]:
    s0, s1 = stacks[d], stacks[d + 1]
    # grey/coral blocks carry over (old leavers at bottom of the same block)
    for key in ("nofu", "case"):
        a0, b0 = s0[key]; a1, _ = s1[key]
        ribbon(d + W / 2, a0, b0, d + 1 - W / 2, a1, a1 + (b0 - a0), NOFU if key == "nofu" else CASE, 0.6)
    fill_nofu = s1["nofu"][0] + (s0["nofu"][1] - s0["nofu"][0])
    fill_case = s1["case"][0] + (s0["case"][1] - s0["case"][0])
    for z in zones:
        a0, b0 = s0[z]
        stay = ret.loc[d + 1, z]
        leave_n = ((p.zone == z) & (p.exit_day == d + 1) & (p.exit_to == "nofu")).sum()
        leave_c = ((p.zone == z) & (p.exit_day == d + 1) & (p.exit_to == "case")).sum()
        # within the source block: stayers on top, leavers below
        a1 = s1[z][0]
        ribbon(d + W / 2, b0 - stay, b0, d + 1 - W / 2, a1, a1 + stay, col[z])
        y = a0
        if leave_n:
            ribbon(d + W / 2, y, y + leave_n, d + 1 - W / 2, fill_nofu, fill_nofu + leave_n, col[z], 0.18)
            fill_nofu += leave_n; y += leave_n
        if leave_c:
            ribbon(d + W / 2, y, y + leave_c, d + 1 - W / 2, fill_case, fill_case + leave_c, ALERT, 0.5)
            fill_case += leave_c; y += leave_c

# contacts with no result at all: shown as an initial grey block at day 1 (exit_day==1)
ymax = max(max(b for _, b in s.values()) for s in stacks.values())
ax.set_xlim(0.4, N_DAYS + 3.6); ax.set_ylim(0, ymax * 1.02)
ax.set_xticks(days); ax.set_xlabel("Day of follow-up (day 1 = first recorded follow-up)")
ax.set_ylabel("Contacts"); ax.spines[["top", "right"]].set_visible(False)
# labels at day 21
s = stacks[N_DAYS]
lab = [(z, s[z], col[z], f"{z}  {ret.loc[N_DAYS, z]:,}/{(p.zone == z).sum():,} ({100 * ret.loc[N_DAYS, z] / (p.zone == z).sum():.0f}%)") for z in zones]
lab += [("case", s["case"], ALERT, f"Became a case  {case[N_DAYS]:,}"),
        ("nofu", s["nofu"], SUB, f"Not followed up  {nofu[N_DAYS]:,} ({100 * nofu[N_DAYS] / total:.0f}%)")]
step = ymax * 0.04
items = sorted(lab, key=lambda r: -(r[1][0] + r[1][1]) / 2)   # top to bottom
ys, prev = [], ymax * 0.97 + step
for key, (a, b), c, txt in items:
    y = min((a + b) / 2, prev - step); ys.append(y); prev = y
for (key, (a, b), c, txt), y in zip(items, ys):
    ax.annotate(txt, ((N_DAYS + W / 2), (a + b) / 2), xytext=(N_DAYS + 0.7, y), va="center", fontsize=BASE * .8, color=c,
                fontweight="bold" if key not in ("nofu", "case") else "normal",
                arrowprops=dict(arrowstyle="-", color=c, lw=0.4))
ax.set_title(f"Follow-up retention over 21 days, by health zone of source case (n = {total:,} contacts with a closed window)",
             loc="left", fontweight="bold", fontsize=BASE * 1.05, color=INK, pad=12)
fig.text(0.01, -0.02, "Data cut 9 Oct 2026. A contact is 'still followed' on day d if a follow-up result was recorded on day d or later. "
         "Day 21 labels: still followed / contacts (%). Contacts with no recorded result leave before day 1.",
         color=MUTED, fontsize=BASE * .72, ha="left", va="top", wrap=True)
fig.savefig(os.path.join(FA, "followup_sankey_retention.png")); plt.close(fig)
print(tab.loc[[1, 7, 14, 21]].to_string())


# =====================================================================================
# Version 2: daily status, including contacts who are missed and then 'back again'.
# State of each contact on day d (d = 1..21, day 1 = first follow-up):
#   seen    -- a follow-up RESULT recorded on that day
#   missed  -- no result that day (contact may be seen again later)
#   case    -- detected as a case on or before that day (absorbing)
# Each health zone has its own coloured 'seen' block and its own grey 'missed' block, so
# flows never cross zones: seen->seen, seen->missed (drop), missed->seen (back again),
# missed->missed.
# =====================================================================================
fu = pd.read_csv(os.path.join(D, "followups.csv"), low_memory=False, parse_dates=["followup_date"],
                 usecols=["source_case_person_id", "contact_person_id", "followup_date", "followup_result"])
K = ["source_case_person_id", "contact_person_id"]
p2 = p[K + ["zone", "fu_start", "case_day"]].reset_index(drop=True)
p2["pid"] = np.arange(len(p2))
r = fu.dropna(subset=["followup_result", "followup_date"]).merge(p2, on=K)
r["day"] = (r.followup_date - r.fu_start).dt.days + 1
r = r[r.day.between(1, N_DAYS)]
S = np.zeros((len(p2), N_DAYS), dtype=np.int8)            # 0 missed, 1 seen, 2 case
S[r.pid.values, r.day.values.astype(int) - 1] = 1
cd = p2.case_day.values
for i in np.where(~np.isnan(cd))[0]:
    if cd[i] <= N_DAYS:
        S[i, max(int(cd[i]), 1) - 1:] = 2
zone_arr = p2.zone.values

# counts per day/zone/state and flows per day/zone/(from,to)
cnt = {(d, z, s): int(((zone_arr == z) & (S[:, d - 1] == s)).sum()) for d in days for z in zones for s in (0, 1, 2)}
flows = {}
for d in days[:-1]:
    a, b = S[:, d - 1], S[:, d]
    for z in zones:
        m = zone_arr == z
        for s0 in (0, 1, 2):
            for s1 in (0, 1, 2):
                flows[(d, z, s0, s1)] = int((m & (a == s0) & (b == s1)).sum())
back = {d: sum(flows[(d - 1, z, 0, 1)] for z in zones) for d in days[1:]}
tab2 = pd.DataFrame({
    "seen": [sum(cnt[(d, z, 1)] for z in zones) for d in days],
    "missed": [sum(cnt[(d, z, 0)] for z in zones) for d in days],
    "case": [sum(cnt[(d, z, 2)] for z in zones) for d in days],
    "back_again_from_previous_day": [0] + [back[d] for d in days[1:]]}, index=days)
tab2.index.name = "followup_day"
tab2.to_csv(os.path.join(T, "followup_daily_status_by_day.csv"))
ever_back = int(((S[:, :-1] == 0) & (S[:, 1:] == 1)).any(axis=1).sum())
print(tab2.loc[[1, 2, 7, 14, 21]].to_string()); print("contacts ever 'back again':", ever_back)

fig, ax = plt.subplots(figsize=(9.4, 5.6))
GAP2 = total * 0.004
MISS_ALPHA = 0.55


def stack2(d):
    """bottom->top: missed blocks (one per zone), [big gap], seen blocks (one per zone), [gap], became a case."""
    y, out = 0.0, {}
    for z in reversed(zones):
        h = cnt[(d, z, 0)]; out[(z, 0)] = (y, y + h); y += h          # shared grey block: no gaps between zones
    y += GAP2 * 6
    for z in reversed(zones):
        h = cnt[(d, z, 1)]; out[(z, 1)] = (y, y + h); y += h + GAP2   # constant gap -> equal column heights
    y += GAP2 * 3
    y0 = y
    for z in reversed(zones):                                          # became a case, split by zone
        h = cnt[(d, z, 2)]; out[(z, 2)] = (y, y + h); y += h
    out[("case",)] = (y0, y)
    return out


st = {d: stack2(d) for d in days}
for d in days:
    for key, (a, b) in st[d].items():
        if b <= a:
            continue
        if key == ("case",):
            continue                      # drawn as its per-zone parts
        elif key[1] == 2:
            continue                      # became a case: drawn below as one shared coral block
        elif key[1] == 0:
            continue                      # missed: drawn below as one shared grey block
        else:
            c = col[key[0]]
        ax.add_patch(plt.Rectangle((d - W / 2, a), W, b - a, fc=c, ec="none"))
    m = [v for k, v in st[d].items() if k != ("case",) and k[1] == 0]
    lo, hi = min(v[0] for v in m), max(v[1] for v in m)
    ax.add_patch(plt.Rectangle((d - W / 2, lo), W, hi - lo, fc="#c9d0d2", ec="none"))
    ca_, cb_ = st[d][("case",)]
    if cb_ > ca_:
        ax.add_patch(plt.Rectangle((d - W / 2, ca_), W, cb_ - ca_, fc=CASE, ec="none"))

for d in days[:-1]:
    def miss_range(stk):
        m = [v for k, v in stk.items() if k != ("case",) and k[1] == 0]
        return min(v[0] for v in m), max(v[1] for v in m)
    out_ptr = {k: v[1] for k, v in st[d].items() if k == ("case",) or k[1] == 1}   # fill blocks top-down
    in_ptr = {k: v[1] for k, v in st[d + 1].items() if k == ("case",) or k[1] == 1}
    out_ptr["miss"] = miss_range(st[d])[1]; in_ptr["miss"] = miss_range(st[d + 1])[1]

    def flow(k0, k1, n, c, al):
        if not n:
            return
        y0b = out_ptr[k0]; out_ptr[k0] = y0b - n
        y1b = in_ptr[k1]; in_ptr[k1] = y1b - n
        ribbon(d + W / 2, y0b - n, y0b, d + 1 - W / 2, y1b - n, y1b, c, al)


    for z in zones:                                   # seen -> seen (stay), top of both blocks
        flow((z, 1), (z, 1), flows[(d, z, 1, 1)], col[z], 0.45)
    for z in zones:                                   # seen -> not followed (drop), top of shared grey
        flow((z, 1), "miss", flows[(d, z, 1, 0)], col[z], 0.15)
    for z in zones:                                   # not followed -> seen (back again)
        flow("miss", (z, 1), flows[(d, z, 0, 1)], col[z], 0.8)
    for z in zones:                                   # -> became a case
        flow((z, 1), ("case",), flows[(d, z, 1, 2)], col[z], 0.6)    # zone-coloured flows into the shared case block (true scale)
        flow("miss", ("case",), flows[(d, z, 0, 2)], col[z], 0.6)
    flow("miss", "miss", sum(flows[(d, z, 0, 0)] for z in zones), NOFU, 0.9)   # one merged grey ribbon
    # earlier cases carry over as one coral ribbon (new arrivals sit on top)
    a0, b0 = st[d][("case",)]
    if b0 > a0:
        a1 = st[d + 1][("case",)][0]
        ribbon(d + W / 2, a0, b0, d + 1 - W / 2, a1, a1 + (b0 - a0), CASE, 0.6)

ymax2 = max(max(b for _, b in s.values()) for s in st.values())
ax.set_xlim(0.4, N_DAYS + 3.8); ax.set_ylim(0, ymax2 * 1.02)
ax.set_xticks(days); ax.set_xlabel("Day of follow-up (day 1 = first recorded follow-up)")
ax.set_yticks([]); ax.spines[["top", "right", "left"]].set_visible(False)
# section labels at left
s1 = st[1]
seen_top = max(v[1] for k, v in s1.items() if k != ("case",) and k[1] == 1)
seen_bot = min(v[0] for k, v in s1.items() if k != ("case",) and k[1] == 1)
miss_top = max(v[1] for k, v in s1.items() if k != ("case",) and k[1] == 0)
miss_bot = min(v[0] for k, v in s1.items() if k != ("case",) and k[1] == 0)
ax.text(0.45, (seen_top + seen_bot) / 2, "Seen\n(result\nrecorded)", ha="right", va="center", fontsize=BASE * .8, fontweight="bold")
ax.text(0.45, (miss_top + miss_bot) / 2, "Not\nfollowed\nup that day", ha="right", va="center", fontsize=BASE * .8, color=SUB, fontweight="bold")
# zone labels at day 21 (seen share) + totals
s21 = st[N_DAYS]
items = []
for z in zones:
    nz = int((zone_arr == z).sum())
    a, b = s21[(z, 1)]
    items.append((z, (a + b) / 2, col[z], f"{z}  seen day 21: {cnt[(N_DAYS, z, 1)]:,}/{nz:,} ({100 * cnt[(N_DAYS, z, 1)] / nz:.0f}%)"))
ca, cb = s21[("case",)]
case_by_zone = sorted(((cnt[(N_DAYS, z, 2)], z) for z in zones if cnt[(N_DAYS, z, 2)]), reverse=True)
items.append(("case", (ca + cb) / 2, ALERT, f"Became a case: {tab2.case.iloc[-1]:,}"))
items.sort(key=lambda r: -r[1])
prev = ymax2 + ymax2 * 0.04
for z, y, c, txt in items:
    yl = min(y, prev - ymax2 * 0.04); prev = yl
    ax.annotate(txt, (N_DAYS + W / 2, y), xytext=(N_DAYS + 0.7, yl), va="center", fontsize=BASE * .75, color=c,
                fontweight="normal" if z == "case" else "bold",
                arrowprops=dict(arrowstyle="-", color=c, lw=0.4))
ax.set_title(f"Daily follow-up status by health zone of source case (n = {total:,} contacts with a closed window)",
             loc="left", fontweight="bold", fontsize=BASE * 1.05, color=INK, pad=12)
fig.text(0.01, -0.01, f"Data cut 9 Oct 2026. Seen = a follow-up result recorded that day. Coloured ribbons from the shared grey (not followed up) block back to the "
         f"coloured blocks = contacts seen again after a missed day ({ever_back:,} contacts at least once). "
         "Contacts with no result on any day stay grey throughout.", color=MUTED, fontsize=BASE * .72, ha="left", va="top", wrap=True)
fig.savefig(os.path.join(F, "figS2_followup_sankey.png")); plt.close(fig)
