"""
Standalone version of Figure 3A: weekly new cases by prior contact-tracing
status, shown as proportions of that week's cases (100% stacked bars).
Same LSHTM styling as 03_figures.py.
"""
import os, json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import PercentFormatter

from ctr_paths import D, T, F, FA
INK, MAIN, MUTED, ALERT, GRID = "#01454f", "#1a8c99", "#a3b9bc", "#e0703f", "#e6eef0"
BASE = 9
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans"], "font.size": BASE,
    "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
    "axes.edgecolor": INK, "axes.linewidth": 0.5, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.4, "axes.axisbelow": True, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.titlecolor": INK, "legend.frameon": False,
    "savefig.dpi": 300, "savefig.bbox": "tight", "figure.facecolor": "white",
})

R = json.load(open(os.path.join(D, "results.json")))
wk = pd.read_csv(os.path.join(T, "weekly_national.csv"), index_col=0, parse_dates=True)
w = wk[(wk.index >= "2026-05-11")].copy()          # first week with >=20 cases
never = w.new_cases - w.new_cases_prev_contact - w.new_cases_contact_after
p_never = 100 * never / w.new_cases
p_after = 100 * w.new_cases_contact_after / w.new_cases
p_prev = 100 * w.new_cases_prev_contact / w.new_cases

fig, ax = plt.subplots(figsize=(7.2, 3.4))
ax.bar(w.index, p_never, width=6, color=MUTED, label="Never on a contact list")
ax.bar(w.index, p_after, bottom=p_never, width=6, color=MAIN, label="Listed as contact after notification")
ax.bar(w.index, p_prev, bottom=p_never + p_after, width=6, color=ALERT, label="Known contact before notification")
for x, nn in zip(w.index, w.new_cases):
    ax.text(x, 101, f"{int(nn)}", ha="center", va="bottom", fontsize=BASE * .62, color="#4a7378")
last = pd.Timestamp("2026-10-05")
ax.axvspan(last - pd.Timedelta(days=3.5), last + pd.Timedelta(days=3.5), color=GRID, alpha=.8, lw=0, zorder=0)
ax.set_ylim(0, 108)
ax.yaxis.set_major_formatter(PercentFormatter())
ax.xaxis.set_major_locator(mdates.MonthLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
ax.set_ylabel("% of new cases (week of notification)"); ax.grid(axis="x", visible=False)
ax.set_title("New cases per week, by prior contact-tracing status (proportion of cases)", pad=14)
ax.text(0, 1.015, "Numbers above bars = cases notified that week", transform=ax.transAxes, fontsize=BASE * .7, color="#4a7378")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3, fontsize=BASE * .85)
fig.text(0.01, -0.06, f"Data cut 9 Oct 2026; person-level after ID harmonisation. Overall: {100*R['pct_cases_prev_contact'][0]:.1f}% known contacts "
         f"before notification, {100*R['pct_cases_contact'][0]:.1f}% on a contact list at any time. Shaded: incomplete last week.",
         color=MUTED, fontsize=BASE * .72, ha="left", va="top", wrap=True)
out = os.path.join(FA, "fig3A_ct_status_proportions.png")
fig.savefig(out); print(out)
print(pd.DataFrame({"n": w.new_cases, "never": p_never, "after": p_after, "prev": p_prev}).round(1).to_string())
