"""
Step 3: figures, styled to mirror lshtm_theme() in
BDBV2026-Processing_Code/pipelines/contact_tracing_pipeline/3-pairs-plots.R
(ggplot theme_bw + LSHTM dark-teal ink, faint grid, ink-filled facet strips,
legend at bottom, bold titles, muted left-aligned captions).
"""
import os, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker
from matplotlib.patches import Polygon as MplPoly
from matplotlib.collections import PatchCollection
from matplotlib.colors import LinearSegmentedColormap, LogNorm, Normalize

from ctr_paths import (D, T, F, FA, geo_file, CUT_LABEL, FU_WINDOW_END, ONSET_END, WK_END, LAST_FULL_WEEK,
                       FIRST_ONSET_WEEK, FIRST_FULL_WEEK, LAST_COMPLETE_MONTH, MONTHS_COMPLETE, MONTHS_FU,
                       month_abbr, month_name, fmt_day)

GEO = geo_file()

# ---------------- LSHTM theme (python port) ----------------
INK, MAIN, LIGHT, MUTED, ALERT = "#01454f", "#1a8c99", "#e3f0f1", "#a3b9bc", "#e0703f"
SUB, GRID = "#4a7378", "#e6eef0"
BASE = 8.5  # scaled down from 12pt for A4 multi-panel figures
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans"], "font.size": BASE,
    "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
    "axes.edgecolor": INK, "axes.linewidth": 0.5, "axes.facecolor": "white",
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.4, "axes.axisbelow": True,
    "axes.titleweight": "bold", "axes.titlesize": BASE * 1.05, "axes.titlelocation": "left",
    "axes.titlecolor": INK, "axes.labelsize": BASE, "xtick.labelsize": BASE * .85, "ytick.labelsize": BASE * .85,
    "legend.frameon": False, "legend.fontsize": BASE * .85, "legend.title_fontsize": BASE * .9,
    "figure.facecolor": "white", "savefig.dpi": 300, "savefig.bbox": "tight",
    "xtick.major.width": 0.5, "ytick.major.width": 0.5,
})
CMAP = LinearSegmentedColormap.from_list("lshtm", ["#cfe6e8", MAIN, INK])
CAP = f"Data cut {CUT_LABEL}; person-level after ID harmonisation."


def strip(ax, text):
    """ink-filled facet strip with white bold text (strip.background in lshtm_theme)"""
    ax.set_title("")
    ax.text(0.5, 1.0, text, transform=ax.transAxes, ha="center", va="bottom", color="white",
            fontweight="bold", fontsize=BASE * .9,
            bbox=dict(boxstyle="square,pad=0.3", fc=INK, ec=INK, lw=1.5))


def tag(ax, letter, title):
    ax.set_title(f"{letter}  {title}", loc="left", pad=6)


def caption(fig, text, y=-0.01):
    """grey caption at the bottom-left, wrapped to the figure width"""
    import textwrap
    width = int(fig.get_figwidth() * 19)
    text = "\n".join(textwrap.fill(line, width) for line in text.split("\n"))
    fig.text(0.01, y, text, color=MUTED, fontsize=BASE * .75, ha="left", va="top")


def legend_bottom(ax, ncol=3, **kw):
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=ncol, **kw)


def date_axis(ax):
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))


R = json.load(open(os.path.join(D, "results.json")))
cases = pd.read_csv(os.path.join(D, "cases_annotated.csv"), low_memory=False,
                    parse_dates=["onset", "notification", "case_date", "wk_notif"])
src = pd.read_csv(os.path.join(D, "sources.csv"), parse_dates=["first_reg", "notification"])
pr = pd.read_csv(os.path.join(D, "pairs_annotated.csv"), low_memory=False, parse_dates=["registration", "last_contact"])
wk = pd.read_csv(os.path.join(T, "weekly_national.csv"), index_col=0, parse_dates=True)
hzt = pd.read_csv(os.path.join(T, "health_zone_table.csv"))
dl = pd.read_csv(os.path.join(D, "delays_long.csv"))
dtab = pd.read_csv(os.path.join(T, "delays.csv"))
rf = pd.read_csv(os.path.join(T, "sar_risk_factors.csv"))
fuw = pd.read_csv(os.path.join(T, "followup_visits_weekly.csv"), parse_dates=["wk"])
# LAST_FULL_WEEK comes from ctr_paths (Monday of the last complete week before the cut)

# ---------------- geometry ----------------
geo = json.load(open(GEO))
polys = {}
for f in geo["features"]:
    g = f["geometry"]
    rings = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    polys[f["properties"]["nom"]] = (f["properties"]["province"], [np.array(r[0]) for r in rings])
AFFECTED = ["Ituri", "Nord-Kivu", "Haut-Uele", "Bas-Uele", "Tshopo", "Sud-Kivu"]


def draw_map(ax, values, cmap=CMAP, norm=None, label="", missing="#f4f4f4", highlight_zero=None, cax=None):
    pats, cols = [], []
    for nm, (prov, rings) in polys.items():
        v = values.get(nm, np.nan)
        for r in rings:
            pats.append(MplPoly(r, closed=True))
            if np.isnan(v):
                cols.append(matplotlib.colors.to_rgba(missing))
            else:
                cols.append(cmap(norm(v)))
    pc = PatchCollection(pats, facecolor=cols, edgecolor="#c8d6d8", linewidth=0.15)
    ax.add_collection(pc)
    # province outline: draw edges of affected-province zones slightly darker
    ax.set_xlim(23.0, 31.4); ax.set_ylim(-3.2, 5.2)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    sm = matplotlib.cm.ScalarMappable(norm=norm, cmap=cmap)
    cb = plt.colorbar(sm, cax=cax, orientation="horizontal") if cax is not None else plt.colorbar(sm, ax=ax, orientation="horizontal", fraction=0.04, pad=0.02, aspect=30)
    cb.set_label(label, fontsize=BASE * .8); cb.outline.set_edgecolor(INK); cb.outline.set_linewidth(0.4)
    cb.ax.tick_params(labelsize=BASE * .75)
    return ax


def label_hz(ax, names):
    for nm in names:
        if nm not in polys: continue
        r = max(polys[nm][1], key=len)
        x, y = r[:, 0].mean(), r[:, 1].mean()
        ax.annotate(nm, (x, y), xytext=(x + 1.0, y + 0.5), fontsize=BASE * .65, color=INK,
                    arrowprops=dict(arrowstyle="-", color=INK, lw=0.4))


# =============================================================== FIGURE 1
from matplotlib.lines import Line2D
REDS = LinearSegmentedColormap.from_list("cases_red", ["#fde4d8", "#f4a582", "#d6604d", "#b2182b", "#67000d"])
cases_hz = cases.groupby("health_zone").size()
CASE_NORM = LogNorm(1, cases_hz.max())
ct_zones = set(src.health_zone.dropna()) & set(polys)


def zone_colour(hz):
    return REDS(CASE_NORM(cases_hz.get(hz, 1)))


def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return 100 * p, 100 * max(0, c - h), 100 * min(1, c + h)


def hbar(ax, d, title, letter, rename):
    s = pd.Series({rename.get(k, k): v[1] for k, v in d.items() if k != "unknown" or v[1] > 1})
    s = s.sort_values()
    ax.barh(s.index, s.values, color=[MUTED if i == "Unknown" else MAIN for i in s.index], height=0.7)
    for i, v in enumerate(s.values):
        ax.text(v + 1, i, f"{v:.0f}%", va="center", fontsize=BASE * .68)
    ax.set_xlim(0, max(s.values) * 1.4); ax.set_xlabel("% of contacts"); ax.grid(axis="y", visible=False)
    ax.tick_params(axis="y", labelsize=BASE * .72)
    tag(ax, letter, title)

RN = {"household": "Household", "hospital": "Hospital", "funeral": "Funeral", "workplace": "Workplace", "unknown": "Unknown",
      "direct_physical_contact": "Direct physical", "sleeping_in_the_same_home": "Slept same home",
      "contact_with_bodily_fluids": "Bodily fluids", "handling_contaminated_clothes_or_linen": "Linen/clothes",
      "neighbour": "Neighbour", "sibling": "Sibling", "child": "Child", "parent": "Parent", "spouse": "Spouse"}

def make_fig1(layout, outname):
    """layout: "main" (manuscript), "wide" (16:9: map | forest | C-F 2x2),
    "slide_map" (A + B only), "slide_contacts" (C-F in one row)."""
    if layout == "main":
        fig = plt.figure(figsize=(8.0, 8.4))
        cols = fig.add_gridspec(1, 2, width_ratios=[1.12, 1], wspace=0.08)
        left = cols[0].subgridspec(2, 1, height_ratios=[0.95, 1.05], hspace=0.3)
        small = left[1].subgridspec(2, 2, hspace=0.82, wspace=0.62, width_ratios=[0.8, 1])
        pos = dict(A=left[0], B=cols[1], C=small[0, 0], D=small[0, 1], E=small[1, 0], F=small[1, 1])
    elif layout == "wide":
        fig = plt.figure(figsize=(14.0, 5.9))
        g = fig.add_gridspec(1, 3, width_ratios=[1.7, 1, 1.1], wspace=0.5)
        small = g[2].subgridspec(2, 2, hspace=0.6, wspace=1.0)
        pos = dict(A=g[0], B=g[1], C=small[0, 0], D=small[0, 1], E=small[1, 0], F=small[1, 1])
    elif layout == "slide_map":
        fig = plt.figure(figsize=(11.5, 6.4))
        g = fig.add_gridspec(1, 2, width_ratios=[1.1, 1], wspace=0.12)
        pos = dict(A=g[0], B=g[1])
    elif layout == "slide_contacts":
        fig = plt.figure(figsize=(12.0, 3.0))
        g = fig.add_gridspec(1, 4, wspace=0.55, width_ratios=[0.8, 1, 1, 1])
        pos = dict(C=g[0], D=g[1], E=g[2], F=g[3])

    # ---- A: map of cases, CT zones outlined
    if "A" in pos:
        ax = fig.add_subplot(pos["A"]); tag(ax, "A", "Cases per health zone"); ax.set_title("A  Cases per health zone", loc="left", pad=16)
        ax.set_aspect("equal"); ax.set_anchor("N")
        cax = ax.inset_axes([0.0, -0.07, 1.0, 0.03])
        draw_map(ax, cases_hz.to_dict(), cmap=REDS, norm=CASE_NORM, label="Confirmed/probable cases (log scale)", cax=cax)
        outl = [MplPoly(r, closed=True) for nm in ct_zones for r in polys[nm][1]]
        ax.add_collection(PatchCollection(outl, facecolor="none", edgecolor=INK, linewidth=0.9, zorder=3))
        ax.set_xlim(23.2, 32.2); ax.set_ylim(-2.7, 5.0)   # cropped to affected zones (less empty map)
        LABELS = {  # zone: label position (lon, lat)
            "Mangala": (31.05, 2.75), "Bambu": (31.05, 2.42), "Nizi": (31.05, 2.09), "Bunia": (31.05, 1.76),
            "Lita": (31.05, 1.43), "Rwampara": (31.05, 1.10), "Nyankunde": (31.05, 0.77),
            "Beni": (31.05, 0.30), "Katwa": (31.05, -0.15), "Butembo": (30.4, -0.75), "Musienene": (27.9, -0.75),
            "Mongbwalu": (29.3, 3.3), "Komanda": (28.2, 0.55), "Isiro": (26.4, 3.35), "Wamba": (26.1, 2.25), "Nia Nia": (26.6, 0.85)}
        for nm, (tx, ty) in LABELS.items():
            if nm not in polys: continue
            r = max(polys[nm][1], key=len); x, y = r[:, 0].mean(), r[:, 1].mean()
            ax.annotate(nm, (x, y), xytext=(tx, ty), fontsize=BASE * .58, color=INK, va="center",
                        ha="left" if tx > x else "right",
                        bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.75),
                        arrowprops=dict(arrowstyle="-", color=INK, lw=0.35, shrinkA=0, shrinkB=0), zorder=5)
        ax.set_anchor("N")
        ax.legend(handles=[matplotlib.patches.Patch(facecolor="white", edgecolor=INK, lw=1.1, label="Zone with contact-tracing records")],
                  loc="lower left", fontsize=BASE * .72, frameon=True, framealpha=0.9, edgecolor="white")


    # ---- B: forest plot, % cases with contacts listed by zone x month
    if "B" in pos:
        ax = fig.add_subplot(pos["B"]); tag(ax, "B", "% of cases with contacts listed, by month of onset")
        MPAL = ["#a3b9bc", MAIN, INK, "#c9a227", ALERT, "#7a5c99", "#5b8c5a", "#a8322d", "#d17fa8"]
        months = [(m, month_abbr(m), MPAL[i % len(MPAL)]) for i, m in enumerate(MONTHS_COMPLETE)]   # complete months only
        cc = cases.copy(); cc["m"] = cc.case_date.dt.to_period("M").astype(str)
        zones = cases_hz[cases_hz >= 50].sort_values(ascending=False).index.tolist()


        offs = np.linspace(-0.3, 0.3, len(months))
        for i, hz in enumerate(zones):
            y = -i
            if i % 2 == 0:
                ax.axhspan(y - 0.5, y + 0.5, color="#f6f9f9", lw=0, zorder=0)
            for (m, lab, col), dy in zip(months, offs):
                sub = cc[(cc.health_zone == hz) & (cc.m == m)]
                if len(sub) < 5:
                    continue
                p, lo, hi = wilson(sub.is_source.sum(), len(sub))
                ax.plot([lo, hi], [y - dy] * 2, color=col, lw=0.9, zorder=2)
                ax.plot(p, y - dy, "o", ms=3.8, mfc=col, mec="white", mew=0.4, zorder=3)
        nat = 100 * R["pct_cases_source"][0]
        ax.axvline(nat, color=INK, ls=":", lw=1)
        ax.text(nat + 0.8, 0.85, f"National {nat:.1f}%", fontsize=BASE * .82, color=INK, va="bottom")
        ax.set_yticks([-i for i in range(len(zones))])
        ax.set_yticklabels([f"{z} ({cases_hz[z]:,})" for z in zones], fontsize=BASE * .85)
        ax.yaxis.tick_right()
        ax.tick_params(axis="x", labelsize=BASE * .9)
        # ranking cue: subtitle under the panel title
        ax.text(0.0, 1.012, "Health zones ranked by number of cases (in brackets), highest first ↓",
                transform=ax.transAxes, ha="left", va="bottom", fontsize=BASE * .8, color=SUB)
        ax.set_title("B  % of cases with contacts listed, by month of onset", loc="left", pad=16)
        ax.set_ylim(-len(zones) + 0.4, 1.3); ax.set_xlim(-1, 101)
        ax.set_xlabel("% of cases with ≥1 contact listed (95% CI)", fontsize=BASE * .95); ax.grid(axis="y", visible=False)
        ax.legend(handles=[Line2D([], [], marker="o", color=col, lw=0.9, ms=4.5, label=lab) for _, lab, col in months],
                  ncol=5 if layout == "wide" else 3, fontsize=BASE * .82, title="Month of onset",
                  **(dict(loc="upper center", bbox_to_anchor=(0.5, -0.09)) if layout == "wide" else dict(loc="upper right")),
                  title_fontsize=BASE * .82, frameon=True, framealpha=0.95, edgecolor=GRID)


    # ---- C: contacts per source
    if "C" in pos:
        ax = fig.add_subplot(pos["C"]); tag(ax, "C", "Contacts per source")
        bins = [1, 2, 11, 31, 61, 100000]
        lab = ["1", "2-10", "11-30", "31-60", ">60"]
        cnt = pd.cut(src.n_contacts, bins, right=False, labels=lab).value_counts().reindex(lab)
        ax.bar(range(len(lab)), cnt.values, color=MAIN, width=0.8)
        ax.set_xticks(range(len(lab))); ax.set_xticklabels(lab, rotation=40, ha="right", fontsize=BASE * .72)
        ax.set_ylabel("Source cases"); ax.set_xlabel("Contacts listed"); ax.grid(axis="x", visible=False)



    if "D" in pos:
        hbar(fig.add_subplot(pos["D"]), R["setting"], "Setting", "D", RN)
        hbar(fig.add_subplot(pos["E"]), R["exposure"], "Exposure", "E", RN)
        hbar(fig.add_subplot(pos["F"]), R["rel"], "Relationship", "F", RN)
    trunc = f"B: zones with ≥50 cases; 95% CI; {month_name(LAST_COMPLETE_MONTH)} right-truncated."
    capnote = {"main": trunc, "wide": trunc,
               "slide_map": trunc, "slide_contacts": "C: source cases; D–F: all source–contact pairs."}[layout]
    caption(fig, f"Data cut {CUT_LABEL}. " + capnote, y={"main": 0.035, "wide": 0.02, "slide_map": 0.02, "slide_contacts": -0.12}[layout])
    fig.savefig(outname); plt.close(fig)


make_fig1("main", os.path.join(F, "fig1_data_summary.png"))                      # manuscript Figure 1
make_fig1("wide", os.path.join(FA, "fig1_data_summary_wide.png"))                # 16:9, one slide
make_fig1("slide_map", os.path.join(FA, "fig1_slide1_map_contacts_listed.png"))  # 2-slide version: A + B
make_fig1("slide_contacts", os.path.join(FA, "fig1_slide2_contacts.png"))         # 2-slide version: C-F

# =============================================================== FIGURE 2
# delay colours (shared across panels)
DCOL = {"Notified": MAIN, "Hospitalised": "#7a5c99", "Sample taken": INK, "Lab result": "#c9a227",
        "Contacts registered\non database": ALERT, "First contact\nfollowed up": "#a8322d",
        "Last contact with\nany contact": "#5b8c5a"}
conf = cases[cases.classification == "confirmed_case"].copy()
if "hospital_admission" not in conf:
    conf["hospital_admission"] = pd.NaT
for c in ["sample_date", "result_date", "hospital_admission"]:
    conf[c] = pd.to_datetime(conf[c])
conf["src_reg"] = conf.person_id.map(src.set_index("source_case_person_id").first_reg)
pr_fu = pd.read_csv(os.path.join(D, "pairs_annotated.csv"), low_memory=False, usecols=["source_case_person_id", "first_fu", "last_contact"], parse_dates=["first_fu", "last_contact"])
conf["first_fu"] = conf.person_id.map(pr_fu.groupby("source_case_person_id").first_fu.min())
# latest recorded last-exposure date across all of the source case's contacts
conf["src_last_contact"] = conf.person_id.map(pr_fu.groupby("source_case_person_id").last_contact.max())
STEPS_ALL = [("Notified", "notification", (0, 60)), ("Hospitalised", "hospital_admission", (0, 60)),
         ("Sample taken", "sample_date", (0, 60)), ("Lab result", "result_date", (0, 60)),
         ("Last contact with\nany contact", "src_last_contact", (-60, 60)),
         ("First contact\nfollowed up", "first_fu", (-60, 60)), ("Contacts registered\non database", "src_reg", (-60, 60))]


HAS_HOSP = conf.hospital_admission.notna().sum() > 0
STEPS = [st for st in STEPS_ALL if HAS_HOSP or st[0] != "Hospitalised"]


# ONSET_END (cut - 26 days) and WK_END (last onset week ending on/before ONSET_END) come from ctr_paths


def delay(df, col, lim, start="onset"):
    d = (df[col] - df[start]).dt.days
    return d[d.between(*lim)]


fig = plt.figure(figsize=(7.4, 3.5))
gs = fig.add_gridspec(1, 2, width_ratios=[1.12, 1], wspace=0.32)
L = [gs[0]]; Rg = [gs[1]]

# ---- A: journey
ax = fig.add_subplot(L[0]); tag(ax, "A", "Patient journey: days since symptom onset")
gap = 0.62
for i, (lab, col, lim) in enumerate(STEPS):
    d = delay(conf[conf.onset <= ONSET_END], col, lim)   # onset on/before ONSET_END (right truncation)
    y = -i * gap
    c = DCOL[lab]
    q1, md, q3, mn = d.quantile(.25), d.median(), d.quantile(.75), d.mean()
    ax.plot([q1, q3], [y, y], color=c, lw=7, solid_capstyle="butt", alpha=.35)
    ax.plot(md, y, "o", color=c, ms=6, mec="white", mew=0.6)
    ax.plot(mn, y, "D", color=c, ms=4, mfc="white", mew=1.2)
    ax.text(q3 + 0.7, y, f"median {md:g} (IQR {q1:g}–{q3:g})\nmean {mn:.1f}; n={len(d):,}", va="center", fontsize=BASE * .7, color=INK)
ax.axvline(0, color=INK, lw=0.8)
ax.set_yticks([-i * gap for i in range(len(STEPS))])
ax.set_yticklabels([s[0] for s in STEPS])
for t, (lab, _, _) in zip(ax.get_yticklabels(), STEPS):
    t.set_color(DCOL[lab]); t.set_fontweight("bold")
ax.set_ylim(-(len(STEPS) - 1) * gap - 0.35, 0.35); ax.set_xlim(-1, 34)
ax.set_xlabel("Days since onset (confirmed cases)"); ax.grid(axis="y", visible=False)
ax.text(0.98, 0.97, "Last contact / followed up / registered:\nsource cases only", transform=ax.transAxes, ha="right", va="top",
        fontsize=BASE * .68, color=SUB)
ax.plot([], [], "o", color=INK, label="Median"); ax.plot([], [], "D", mfc="white", mec=INK, label="Mean")
ax.plot([], [], color=INK, lw=7, alpha=.35, label="IQR")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=3, fontsize=BASE * .72)

BC = [("Onset → notification", "Notified")] + ([("Onset → hospital admission", "Hospitalised")] if HAS_HOSP else []) + \
     [("Onset → lab result", "Lab result"), ("Onset → first contacts listed", "Contacts registered\non database")]

# ---- B: by month
ax = fig.add_subplot(Rg[0]); tag(ax, "B", "Median delay by week of onset")
conf["wk_onset"] = conf.onset.dt.to_period("W-SUN").dt.start_time
BCOL = {"Onset → notification": "notification", "Onset → hospital admission": "hospital_admission",
        "Onset → lab result": "result_date", "Onset → first contacts listed": "src_reg"}
for k, lab in BC:
    col = BCOL[k]; lim = (-60, 60) if col == "src_reg" else (0, 60)
    dd = (conf[col] - conf.onset).dt.days
    tmp = pd.DataFrame({"wk": conf.wk_onset, "d": dd})[dd.between(*lim)]
    tmp = tmp[(tmp.wk >= FIRST_ONSET_WEEK) & (tmp.wk <= WK_END)]
    g = tmp.groupby("wk").d.agg(n="size", med="median", q1=lambda x: x.quantile(.25), q3=lambda x: x.quantile(.75))
    g = g[g.n >= 5]
    c = DCOL[lab]
    ax.fill_between(g.index, g.q1, g.q3, color=c, alpha=.15, lw=0)
    ax.plot(g.index, g.med, "-o", color=c, ms=2.5, lw=1.2, label=k.replace("first contacts listed", "contacts registered"))
ax.set_ylim(bottom=0); ax.set_xlim(FIRST_ONSET_WEEK - pd.Timedelta(days=3), WK_END + pd.Timedelta(days=7))
date_axis(ax); ax.set_ylabel("Days (median, IQR)"); ax.legend(fontsize=BASE * .62, loc="upper right")
caption(fig, CAP + " Delays from onset outside 0–60 days excluded (−60 to 60 for contact dates)." + f"\nA: onset on or before {fmt_day(ONSET_END, False)} (≥26 days to data cut); last contact = latest last-exposure date among the source case's contacts.\nB: weeks with ≥5 cases; onset weeks to {WK_END.day}–{fmt_day(WK_END + pd.Timedelta(days=6), False)} only (≥26 days follow-up to data cut).", y=-0.06)
fig.savefig(os.path.join(F, "fig2_patient_journey.png")); plt.close(fig)

# ---- Supplementary: delays by province + known contacts
fig = plt.figure(figsize=(7.4, 3.2))
gs = fig.add_gridspec(1, 2, wspace=0.3)
ax = fig.add_subplot(gs[1]); tag(ax, "B", "Median delay by province")
provs = ["Ituri", "Nord-Kivu", "Haut-Uele", "Tshopo"]
pv = dtab[(dtab.level == "Province") & dtab.group.isin(provs)]
bw = 0.8 / len(BC)
for j, (k, lab) in enumerate(BC):
    d = pv[pv.delay == k].set_index("group").reindex(provs)
    x = np.arange(len(provs)) + (j - (len(BC) - 1) / 2) * bw
    ax.bar(x, d["median"], width=bw, color=DCOL[lab], label=k.replace("first contacts listed", "contacts registered"))
    ax.errorbar(x, d["median"], yerr=[d["median"] - d.q1, d.q3 - d["median"]], fmt="none", ecolor=SUB, lw=0.6, capsize=1.5)
ax.set_xticks(range(len(provs))); ax.set_xticklabels(provs, fontsize=BASE * .8); ax.set_ylabel("Days since onset\n(median, IQR)"); ax.grid(axis="x", visible=False)
ax.set_ylim(0, ax.get_ylim()[1] * 1.3); ax.legend(fontsize=BASE * .58, loc="upper left", ncol=1)

# ---- D: known contacts vs others
ax = fig.add_subplot(gs[0]); tag(ax, "A", "Known contacts vs other confirmed cases")
grp = [("Known contact\nbefore notification", conf.prev_contact.astype(bool)), ("Not a known\ncontact", ~conf.prev_contact.astype(bool))]
pos, data, cols, ticks = [], [], [], []
for gi, (gname, mask) in enumerate(grp):
    for j, (lab, col) in enumerate([("Notified", "notification"), ("Lab result", "result_date")]):
        v = delay(conf[mask], col, (0, 60))
        data.append(v.values); pos.append(gi * 3 + j); cols.append(DCOL[lab])
        ax.text(gi * 3 + j, -2.6, f"n={len(v):,}", ha="center", va="top", fontsize=BASE * .6, color=SUB)
    ticks.append(gi * 3 + 0.5)
bp = ax.boxplot(data, positions=pos, widths=0.7, patch_artist=True, showfliers=False,
                medianprops=dict(color="white", lw=1.5), whiskerprops=dict(color=INK, lw=0.6), capprops=dict(color=INK, lw=0.6))
for patch, c in zip(bp["boxes"], cols):
    patch.set_facecolor(c); patch.set_edgecolor(INK); patch.set_linewidth(0.5)
ax.set_xticks(ticks); ax.set_xticklabels([g[0] for g in grp], fontsize=BASE * .75)
ax.set_ylim(-5, ax.get_ylim()[1] * 1.3); ax.set_ylabel("Days since onset"); ax.grid(axis="x", visible=False)
ax.legend(handles=[matplotlib.patches.Patch(color=DCOL["Notified"], label="Onset → notification"),
                   matplotlib.patches.Patch(color=DCOL["Lab result"], label="Onset → lab result")],
          fontsize=BASE * .62, loc="upper center", ncol=2)
caption(fig, CAP + " Confirmed cases; delays from onset outside 0–60 days excluded (−60 to 60 for contacts registered).", y=0.0)
fig.savefig(os.path.join(FA, "delays_province_knowncontacts.png")); plt.close(fig)

# =============================================================== FIGURE 3
def make_fig3(d_mode, outname, wide=False):
    """wide=True: 16:9 slide layout (A over D on the left, B over C stacked on the right)."""
    if wide:
        fig = plt.figure(figsize=(11.5, 6.6))
        gs = fig.add_gridspec(2, 2, width_ratios=[1.55, 1], height_ratios=[1, 1.15], hspace=0.62, wspace=0.32)
        pos_a, pos_d = gs[0, 0], gs[1, 0]
        row2 = gs[:, 1].subgridspec(2, 1, hspace=0.75)
    else:
        fig = plt.figure(figsize=(7.4, 9.6) if d_mode == "heat" else (7.4, 8.6))
        gs = fig.add_gridspec(3, 2, height_ratios=[1.1, 1, 1.8 if d_mode == "heat" else 1.25], hspace=0.62, wspace=0.62)
        pos_a, pos_d = gs[0, :], gs[2, :]
        row2 = gs[1, :].subgridspec(1, 2, width_ratios=[1.15, 1], wspace=0.42)
    w = wk[wk.index >= FIRST_FULL_WEEK]
    ww = w[w.new_cases >= 20]

    # A: weekly cases (bars) + % known contact before notification (line, right axis)
    ax = fig.add_subplot(pos_a)
    ax.bar(w.index, w.new_cases, width=6, color=MUTED, label="New cases (week of notification)")
    ax.set_ylabel("New cases"); date_axis(ax); ax.grid(axis="x", visible=False)
    ax.axvspan(LAST_FULL_WEEK + pd.Timedelta(days=4), w.index.max() + pd.Timedelta(days=4), color="white", alpha=.6, lw=0, zorder=3)
    ax2 = ax.twinx()
    ax2.plot(ww.index, 100 * ww.new_cases_prev_contact / ww.new_cases, "-o", color=ALERT, ms=2.8, lw=1.4,
             label="% known contact before notification (right axis)")
    ax2.set_ylim(0, None); ax2.set_ylabel("% known contact\nbefore notification", color=ALERT); ax2.grid(False)
    ax2.tick_params(axis="y", colors=ALERT)
    ax.text(0.0, 1.02, f"Known contact before notification: {R['n_cases_prev_contact']} of {R['n_cases']:,} cases ({100*R['pct_cases_prev_contact'][0]:.1f}%).  "
            f"On a contact list at any time: {R['n_cases_contact_any_time']} ({100*R['pct_cases_contact'][0]:.1f}%)",
            transform=ax.transAxes, va="bottom", fontsize=BASE * .72, color=SUB)
    ax.set_title("A  New cases per week and share already known as contacts", loc="left", pad=16)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2, fontsize=BASE * .72)

    # B: % of new cases that became source cases
    ax = fig.add_subplot(row2[0]); tag(ax, "B", "% of new cases that became source cases" if not wide else "% of new cases that became source cases")
    ax.plot(ww.index, ww.pct_became_source, "-o", color=INK, ms=2.5, lw=1.2)
    ax.set_ylabel("% of new cases"); ax.set_ylim(0, None)
    ax.axvspan(LAST_FULL_WEEK - pd.Timedelta(days=10), ww.index.max() + pd.Timedelta(days=4), color=GRID, alpha=.8, lw=0)
    date_axis(ax)

    # C: follow-up visits with a result
    ax = fig.add_subplot(row2[1]); tag(ax, "C", "Follow-up visits with a recorded result" if not wide else "Follow-up visits with a recorded result")
    f = fuw[(fuw.wk >= FIRST_FULL_WEEK) & (fuw.wk <= LAST_FULL_WEEK)]
    ax.bar(f.wk, f.visits, width=6, color=LIGHT, edgecolor=MAIN, lw=0.4, label="Follow-up rows")
    ax.set_ylabel("Follow-up visits (rows)", color=MAIN); date_axis(ax); ax.grid(axis="x", visible=False)
    ax2 = ax.twinx(); ax2.plot(f.wk, f.pct_result, "-o", color=ALERT, ms=2.5, lw=1.2, label="% with result recorded")
    ax2.set_ylim(0, 100); ax2.set_ylabel("% with result", color=ALERT); ax2.grid(False)
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, fontsize=BASE * .7)

    # D: follow-up completeness (result recorded to day 21 after last exposure, or until detection for positives)
    if d_mode == 'heat':
        ax = fig.add_subplot(pos_d); tag(ax, "D", "Contacts fully followed up, by health zone and month of first follow-up")
        t21 = pd.read_csv(os.path.join(T, "fu21_complete_hz_month.csv"))
        mon = MONTHS_FU   # month of first follow-up; last month is partial (to FU_WINDOW_END)
        tot = t21.groupby("src_health_zone")[["n", "k"]].sum()
        zones21 = tot[tot.n >= 50].sort_values("n", ascending=False).index.tolist()
        K = t21.pivot_table(index="src_health_zone", columns="lc_month", values="k", aggfunc="sum").reindex(index=zones21, columns=mon)
        N = t21.pivot_table(index="src_health_zone", columns="lc_month", values="n", aggfunc="sum").reindex(index=zones21, columns=mon)
        P = (100 * K / N).where(N >= 10)
        allc = (100 * tot.k / tot.n).reindex(zones21)
        Pm = P.copy(); Pm["All"] = allc
        ax.imshow(Pm.values, aspect="auto", cmap=CMAP, vmin=0, vmax=100)
        for i in range(Pm.shape[0]):
            for j in range(Pm.shape[1]):
                v = Pm.values[i, j]
                nn = N.values[i, j] if j < len(mon) else tot.n.reindex(zones21).values[i]
                if np.isnan(v):
                    if not np.isnan(nn) and nn > 0:
                        ax.text(j, i, f"n={int(nn)}", ha="center", va="center", fontsize=BASE * .52, color=MUTED)
                else:
                    ax.text(j, i, f"{v:.0f}% ({int(nn)})", ha="center", va="center", fontsize=BASE * .58,
                            color="white" if v > 55 else INK, fontweight="bold" if j == len(mon) else "normal")
        ax.axvline(len(mon) - 0.5, color="white", lw=3)
        ax.set_xticks(range(len(mon) + 1)); ax.set_xticklabels([pd.Timestamp(m).strftime("%b") for m in mon] + ["All"])
        ax.set_yticks(range(len(zones21))); ax.set_yticklabels(zones21, fontsize=BASE * .7); ax.grid(False)
        for sp in ax.spines.values(): sp.set_color(INK)
        ax.text(0.0, 1.015, f"Overall {100*R['fu_adj_complete'][0]:.0f}% of {int(sum(v[1] for v in R['fu21_by_month'].values())):,} contacts whose first follow-up was on or before {fmt_day(FU_WINDOW_END, False)} (day 21 reached by the {fmt_day(FU_WINDOW_END + pd.Timedelta(days=21), False)} data cut). "
                f"{month_abbr(MONTHS_FU[-1])} = first follow-up 1–{fmt_day(FU_WINDOW_END, False)}.",
                transform=ax.transAxes, ha="left", va="bottom", fontsize=BASE * .68, color=SUB)
        ax.set_title("D  Contacts fully followed up, by health zone and month of first follow-up", loc="left", pad=15)

    else:
        import matplotlib.patheffects as pe
        ax = fig.add_subplot(pos_d)
        t21 = pd.read_csv(os.path.join(T, "fu21_complete_hz_month.csv"))
        mon = MONTHS_FU   # month of first follow-up; last month is partial (to FU_WINDOW_END)
        tot = t21.groupby("src_health_zone")[["n", "k"]].sum()
        zl = tot[tot.n >= 150].sort_values("n", ascending=False).index.tolist()[:9]
        K = t21.pivot_table(index="src_health_zone", columns="lc_month", values="k", aggfunc="sum").reindex(index=zl, columns=mon)
        N = t21.pivot_table(index="src_health_zone", columns="lc_month", values="n", aggfunc="sum").reindex(index=zl, columns=mon)
        P = (100 * K / N).where(N >= 10)
        pal = [INK, MAIN, ALERT, "#c9a227", "#7a5c99", "#a8322d", "#5b8c5a", "#a3b9bc", "#d17fa8"]
        x = np.arange(len(mon))
        ax.set_xlim(-0.15, len(mon) - 0.85); ax.set_ylim(-4, 104)
        ax.set_xticks(x); ax.set_xticklabels([pd.Timestamp(m).strftime("%b") for m in mon])
        ax.set_ylabel("% fully followed up"); ax.grid(axis="x", visible=False)
        nat = [100 * R["fu21_by_month"][m][0] / R["fu21_by_month"][m][1] for m in mon]
        ax.plot(x, nat, color=INK, lw=2.2, ls=(0, (1, 1.2)), zorder=4)
        fig.canvas.draw()
        placed = []
        rend = fig.canvas.get_renderer()
        def place(xs, ys, label, color, prefer):
            """geomtextpath-style inline label: text follows the local slope, line knocked out behind it.
            Tries positions along each segment and keeps the first whose box clears earlier labels."""
            segs = [j for j in range(len(xs) - 1) if not (np.isnan(ys[j]) or np.isnan(ys[j + 1]))]
            if not segs:
                return
            segs = sorted(segs, key=lambda j: abs(j - prefer))
            best = None
            for j in segs:
                d0, d1 = ax.transData.transform([(xs[j], ys[j]), (xs[j + 1], ys[j + 1])])
                ang = np.degrees(np.arctan2(d1[1] - d0[1], d1[0] - d0[0]))
                for f in (0.5, 0.35, 0.65, 0.25, 0.75):
                    xm, ym = xs[j] + f * (xs[j + 1] - xs[j]), ys[j] + f * (ys[j + 1] - ys[j])
                    t = ax.text(xm, ym, label, rotation=ang, rotation_mode="anchor", ha="center", va="center",
                                color=color, fontsize=BASE * .66, fontweight="bold", zorder=6,
                                path_effects=[pe.withStroke(linewidth=4.5, foreground="white")])
                    bb = t.get_window_extent(rend).expanded(1.08, 1.25)
                    if not any(bb.overlaps(q) for q in placed):
                        placed.append(bb); return
                    if best is None:
                        best = (xm, ym, ang)
                    t.remove()
            xm, ym, ang = best
            t = ax.text(xm, ym, label, rotation=ang, rotation_mode="anchor", ha="center", va="center", color=color,
                        fontsize=BASE * .66, fontweight="bold", zorder=6, path_effects=[pe.withStroke(linewidth=4.5, foreground="white")])
            placed.append(t.get_window_extent(rend))
        for i, z in enumerate(zl):
            ys = P.loc[z].values.astype(float)
            ax.plot(x, ys, "-o", color=pal[i], lw=1.3, ms=2.8, zorder=3, alpha=.9)
        for i, z in enumerate(zl):
            place(x, P.loc[z].values.astype(float), z, pal[i], prefer=i % (len(mon) - 1))
        place(x, np.array(nat), "All zones", INK, prefer=1)
        ax.text(0.0, 1.015, f"Overall {100*R['fu_adj_complete'][0]:.0f}% of {int(sum(v[1] for v in R['fu21_by_month'].values())):,} contacts; 9 zones with most contacts shown; months with <10 contacts omitted.",
                transform=ax.transAxes, ha="left", va="bottom", fontsize=BASE * .68, color=SUB)
        ax.set_title("D  Contacts fully followed up, by health zone and month of first follow-up", loc="left", pad=15)

    dnote = ("zones with ≥50 contacts; cells with <10 contacts show n only; (n) = contacts." if d_mode == "heat"
             else "9 zones with most contacts; months with <10 contacts omitted; dotted line = all zones.")
    caption(fig, CAP + " Shaded: incomplete recent data. Lines in A and B: weeks with ≥20 cases."
            "\nD: complete = result recorded to day 21 of follow-up (first follow-up = day 1) (secondary cases: followed up to detection);"
            "\n" + dnote, y=0.0 if wide else 0.075)
    fig.savefig(outname); plt.close(fig)



make_fig3('lines', os.path.join(F, 'fig3_ct_effectiveness.png'))            # manuscript Figure 3 (D as lines)
make_fig3('heat', os.path.join(FA, 'fig3_ct_effectiveness_heatmapD.png'))   # alternative: D as heatmap
make_fig3('lines', os.path.join(FA, 'fig3_ct_effectiveness_wide.png'), wide=True)   # 16:9 version for slides

# ---- Supplementary: source cases & contacts per source; notification -> first contact registered
fig = plt.figure(figsize=(7.4, 3.0))
gs = fig.add_gridspec(1, 2, wspace=0.55)
ax = fig.add_subplot(gs[0]); tag(ax, "A", "Source cases & contacts per source, by week")
sw = src.assign(wk=pd.to_datetime(src.wk)).dropna(subset=["wk"]).groupby("wk").n_contacts.agg(n="size", mean="mean", q1=lambda x: x.quantile(.25), q3=lambda x: x.quantile(.75))
sw = sw[(sw.index >= FIRST_FULL_WEEK) & (sw.index <= LAST_FULL_WEEK)]
ax.bar(sw.index, sw.n, width=6, color=LIGHT, edgecolor=MAIN, lw=0.4, label="New source cases")
ax.set_ylabel("New source cases", color=MAIN); date_axis(ax); ax.grid(axis="x", visible=False)
ax2 = ax.twinx(); sl = sw[sw.n >= 5]
ax2.fill_between(sl.index, sl.q1, sl.q3, color=ALERT, alpha=.18, lw=0, label="IQR")
ax2.plot(sl.index, sl["mean"], "-o", color=ALERT, ms=2.5, lw=1.2, label="Mean contacts per source")
ax2.set_ylim(0, None); ax2.set_ylabel("Contacts per source", color=ALERT); ax2.grid(False)
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, fontsize=BASE * .62)

ax = fig.add_subplot(gs[1]); tag(ax, "B", "Notification → first contact registered")
src["m"] = src.first_reg.dt.to_period("M").astype(str)
ms = MONTHS_COMPLETE
data = [src.loc[(src.m == m) & src.notif_to_reg.between(-60, 60), "notif_to_reg"].values for m in ms]
ax.boxplot(data, widths=0.55, patch_artist=True, showfliers=False, medianprops=dict(color=ALERT, lw=1.5),
           boxprops=dict(facecolor=LIGHT, edgecolor=INK, lw=0.6), whiskerprops=dict(color=INK, lw=0.6), capprops=dict(color=INK, lw=0.6))
ax.set_xticks(range(1, len(ms) + 1)); ax.set_xticklabels([pd.Timestamp(m).strftime("%b") + f"\n(n={len(d)})" for m, d in zip(ms, data)], fontsize=BASE * .75)
ax.set_ylabel("Days (by month of registration)"); ax.axhline(0, color=MUTED, lw=0.6); ax.grid(axis="x", visible=False)
caption(fig, CAP + " A: weeks of first contact registration; line shown for weeks with ≥5 source cases.", y=-0.17)
fig.savefig(os.path.join(FA, "source_cases_registration_delay.png")); plt.close(fig)

# =============================================================== FIGURE 4

# ---------------- fitted gamma overlays for Figure 4 (main-analysis data, as in 05_fit_distributions_epidist.R)
from math import lgamma
EPI = os.path.join(D, "epidist_inputs")
from ctr_paths import REPORT_DATE
CUT42 = pd.Timestamp(REPORT_DATE) - pd.Timedelta(days=42)          # infector onset cut-off (main analyses)


def main_si_pairs():
    """Main serial-interval pairs (SI-1): both linelist cases with onsets, not reciprocal,
    infector onset <= data cut - 42 d, SI -5 to 60 d. Used by Fig 4B (+ gamma fit) and 4C."""
    d = pd.read_csv(os.path.join(EPI, "serial_interval_pairs.csv"), parse_dates=["infector_onset", "infectee_onset"])
    d = d[d.si.between(-5, 60) & (d.infector_onset <= CUT42)].copy()
    d["case_circumstances"] = d.setting.fillna("unknown")
    return d


def main_si_data():
    return main_si_pairs().si.astype(float)


def main_inc_data():
    """Main incubation pairs; returns onset minus the midpoint of the exposure window (for display only)."""
    d = pd.read_csv(os.path.join(EPI, "incubation_cases.csv"), parse_dates=["source_onset", "last_exposure", "onset"])
    d = d.dropna(subset=["source_onset", "last_exposure", "onset"])
    pre = d.last_exposure < d.source_onset
    ws = d.source_onset.where(~pre, d.last_exposure)
    we = d[["last_exposure", "onset"]].min(axis=1).where(~pre, d.last_exposure)
    dl = (d.onset - ws).dt.days; ds = (d.onset - d.source_onset).dt.days; de = (d.onset - we).dt.days
    keep = (we >= ws) & (dl >= 1) & ds.between(1, 60) & de.between(0, 42) & (d.source_onset <= CUT42)
    mid = ws[keep] + (we[keep] - ws[keep]) / 2
    return ((d.onset[keep] - mid).dt.total_seconds() / 86400).astype(float)


def gamma_pdf(x, shape, rate):
    x = np.asarray(x, float); out = np.zeros_like(x); m = x > 0
    out[m] = np.exp(shape * np.log(rate) - lgamma(shape) + (shape - 1) * np.log(x[m]) - rate * x[m])
    return out


def fit_panel(ax, v, key, bins, xlim, ylab):
    ax.hist(v, bins=bins, density=True, color=LIGHT, edgecolor=MUTED, lw=0.5, label=f"Data (n={len(v)})")
    pmf_path = os.path.join(T, f"fitted_pmf_main_{key}.csv")
    gp = os.path.join(T, "distribution_fits_main_gamma.csv")
    q = "Serial interval" if key == "serial_interval" else "Incubation period"
    txt = ""
    if os.path.exists(gp):
        g = pd.read_csv(gp); g = g[g.Quantity == q]
        if len(g):
            g = g.iloc[0]
            txt = f"Gamma fit\nmean {g['Mean (95% CrI)']}\nmedian {g['Median (95% CrI)']}"
    if os.path.exists(pmf_path):                      # posterior median + 95% CrI from the R fit
        pm = pd.read_csv(pmf_path)
        ax.fill_between(pm.day + 0.5, pm.lo, pm.hi, color=INK, alpha=0.18, lw=0)
        ax.plot(pm.day + 0.5, pm.med, color=INK, lw=1.6, label="Fitted gamma")
    elif os.path.exists(gp) and len(g):               # fallback: density at the posterior-median parameters
        import re
        sh, rt = [float(x) for x in re.findall(r"shape ([\d.]+).*?rate ([\d.]+)", g["Gamma parameters (median, 95% CrI)"])[0]]
        shift = 6 if "delay + 6" in str(g["Gamma parameters (median, 95% CrI)"]) else 0
        xx = np.linspace(xlim[0], xlim[1], 400)
        ax.plot(xx, gamma_pdf(xx + shift, sh, rt), color=INK, lw=1.6, label="Fitted gamma (median parameters)")
    ax.set_xlim(*xlim); ax.set_ylabel(ylab); ax.grid(axis="x", visible=False)
    if txt:
        ax.text(0.97, 0.95, txt, transform=ax.transAxes, ha="right", va="top", fontsize=BASE * .68)
    ax.axvline(0, color=MUTED, lw=0.4)


def make_fig4(c_mode, outname, rf=rf, sar_overall=None, sar_label="linelist cases + CT 'case confirmed'", layout="main"):
    """layout: "main" (manuscript), "wide" (16:9: A | B, D on top and C below),
    "slide_sar" (A only), "slide_timing" (B, C, D in one row)."""
    sar_overall = R["sar"][0] if sar_overall is None else sar_overall
    if layout == "main":
        fig = plt.figure(figsize=(7.2, 6.6))
        gs = fig.add_gridspec(3, 2, width_ratios=[1.45, 1], hspace=0.75, wspace=0.3)
        pos = dict(A=gs[:, 0], B=gs[0, 1], C=gs[1, 1], D=gs[2, 1])
    elif layout == "wide":
        fig = plt.figure(figsize=(12.5, 6.4))
        gs = fig.add_gridspec(2, 3, width_ratios=[1.3, 1, 1], hspace=0.55, wspace=0.3)
        pos = dict(A=gs[:, 0], B=gs[0, 1], D=gs[0, 2], C=gs[1, 1:])
    elif layout == "slide_sar":
        fig = plt.figure(figsize=(8.5, 6.4))
        gs = fig.add_gridspec(1, 1)
        pos = dict(A=gs[0, 0])
    elif layout == "slide_timing":
        fig = plt.figure(figsize=(12.5, 3.6))
        gs = fig.add_gridspec(1, 3, wspace=0.3)
        pos = dict(B=gs[0, 0], C=gs[0, 1], D=gs[0, 2])
    if "A" in pos:
        ax = fig.add_subplot(pos["A"]); tag(ax, "A", "Secondary attack rate (SAR) among contacts")
        ax.text(0.0, 1.012, f"Secondary cases {sar_label}; overall SAR {100*sar_overall:.1f}%", transform=ax.transAxes,
                ha="left", va="bottom", fontsize=BASE * .72, color=SUB)
        ax.set_title("A  Secondary attack rate (SAR) among contacts", loc="left", pad=15)
        show = rf[(rf.n >= 50) & ~rf.factor.isin(["Month listed"])].copy()
        order = ["Exposure type", "Setting", "Relationship", "Source outcome", "Contacts listed by source", "Province (source)"]
        y, yt, yl = 0, [], []
        XR = 15
        for bi, fac in enumerate(order):
            d = show[show.factor == fac]
            if fac == "Contacts listed by source":
                d = d.set_index("level").reindex(["1-5", "6-15", "16-50", ">50"]).reset_index()
            else:
                d = d.sort_values("sar")
            y_top = y + 0.5
            ax.text(XR - 0.2, y - 0.1, fac, fontweight="bold", fontsize=BASE * .8, va="bottom", ha="right")
            y -= 1
            for r in d.itertuples():
                # colour by the bootstrap-by-source CI of the risk ratio (the CI used in the text)
                # (bootstrap percentile CIs are unreliable for levels with <5 secondary cases: use the Wald CI there)
                clo, chi = (r.rr_boot_lo, r.rr_boot_hi) if r.k >= 5 else (r.rr_lo, r.rr_hi)
                col = ALERT if (clo > 1) else (MAIN if not (chi < 1) else MUTED)
                ax.plot([100 * r.boot_lo, 100 * r.boot_hi], [y, y], color=col, lw=1.0, alpha=.5, solid_capstyle="butt")   # bootstrap: thin
                ax.plot([100 * r.lo, 100 * r.hi], [y, y], color=col, lw=2.3, solid_capstyle="round")                      # Wilson: thick
                ax.plot(100 * r.sar, y, "s" if r.ref else "o", color=col, ms=4, mec="white", mew=0.4, zorder=3)
                yt.append(y); yl.append(f"{RN.get(r.level, r.level)}  ({r.k}/{r.n:,})")
                y -= 1
            if bi % 2 == 0:
                ax.axhspan(y + 0.5, y_top, color="#eef4f5", lw=0, zorder=0)
            y -= 0.4
        ax.axvline(100 * sar_overall, color=INK, ls="--", lw=0.7)
        ax.set_yticks(yt); ax.set_yticklabels(yl, fontsize=BASE * .72); ax.set_ylim(y + 0.5, 0.6)
        ax.set_xlabel("SAR, % (95% CI)"); ax.set_xlim(-0.3, XR); ax.grid(axis="y", visible=False)
        ax.plot([], [], "o", color=ALERT, label="Higher than reference"); ax.plot([], [], "o", color=MUTED, label="Lower than reference")
        ax.plot([], [], "s", color=MAIN, label="Reference group")
        ax.plot([], [], color=INK, lw=2.3, solid_capstyle="round", label="95% CI (Wilson)"); ax.plot([], [], color=INK, lw=1.0, alpha=.5, label="95% CI (bootstrap by source case)")
        ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.07), ncol=3, fontsize=BASE * .66)

    si = pd.read_csv(os.path.join(D, "serial_interval_pairs.csv"))   # all linked pairs (used by panel C)
    if "B" in pos:
        ax = fig.add_subplot(pos["B"]); tag(ax, "B", "Serial interval (onset to onset)")
        v = main_si_data()
        fit_panel(ax, v, "serial_interval", bins=np.arange(-6, 61, 3), xlim=(-7, 50), ylab="Proportion per day")
        ax.set_xlabel("Days")


    if "C" in pos:
        if c_mode == 'poly':
            sis = main_si_pairs()   # same 49 main-analysis pairs as panel B
            ax = fig.add_subplot(pos["C"]); tag(ax, "C", "Serial interval by setting")
            edges = np.arange(-15, 50, 5); mids = edges[:-1] + 2.5
            for setting, c in [("household", MAIN), ("hospital", ALERT)]:
                v = sis.loc[sis.case_circumstances == setting, "si"]
                h, _ = np.histogram(v.clip(-15, 44), bins=edges)
                ax.plot(mids, h / h.sum(), "-o", color=c, ms=2.5, lw=1.3, label=f"{setting.capitalize()} (n={len(v)}, median {v.median():g} d)")
                ax.axvline(v.median(), color=c, ls="--", lw=0.8)
            n_other = int((~sis.case_circumstances.isin(["household", "hospital"])).sum())
            ax.set_xlabel("Days (5-day bins)"); ax.set_ylabel("Proportion of pairs"); ax.set_ylim(0, ax.get_ylim()[1] * 1.55)
            ax.legend(fontsize=BASE * .6, loc="upper left", ncol=1, handlelength=1.5)
            ax.text(0.98, 0.70, f"Funeral/workplace\nnot shown (n={n_other})", transform=ax.transAxes, ha="right", va="top", fontsize=BASE * .58, color=SUB)


        else:
            # C (cumulative version): empirical cumulative distribution by setting
            sis = main_si_pairs()   # same 49 main-analysis pairs as panel B
            ax = fig.add_subplot(pos["C"]); tag(ax, "C", "Serial interval by setting (cumulative)")
            vals = {}
            for setting, c in [("household", MAIN), ("hospital", ALERT)]:
                v = np.sort(sis.loc[sis.case_circumstances == setting, "si"].values); vals[setting] = v
                xs = np.concatenate([[-16], v]); ys = np.concatenate([[0], np.arange(1, len(v) + 1) / len(v)])
                ax.step(xs, ys, where="post", color=c, lw=1.4, label=setting)
            ax.axhline(0.5, color=MUTED, ls=":", lw=0.8)
            _d = pd.read_csv(os.path.join(T, "serial_interval_by_setting.csv")).set_index("setting").loc["hospital - household"]
            dmed, lo, hi = _d["median"], _d.median_lo, _d.median_hi   # bootstrap CI, same numbers as the table
            n_other = int((~sis.case_circumstances.isin(["household", "hospital"])).sum())
            ax.text(0.98, 0.05, f"Hospital − household median:\n{dmed:+g} d (95% CI {lo:+.1f} to {hi:+.1f})\nFuneral/workplace not shown (n={n_other})", transform=ax.transAxes,
                    ha="right", va="bottom", fontsize=BASE * .62, color=INK)
            ax.set_xlim(-16, 60); ax.set_ylim(0, 1.02); ax.set_xlabel("Serial interval (days)"); ax.set_ylabel("Cumulative proportion")
            for (setting, c), (tx, ty) in zip([("household", MAIN), ("hospital", ALERT)], [(-15, 0.56), (30, 0.55)]):
                v = vals[setting]
                ax.text(tx, ty, f"{setting.capitalize()}\nn={len(v)}, median {np.median(v):g} d", color=c, fontsize=BASE * .62,
                        fontweight="bold", ha="left", va="bottom")


    if "D" in pos:
        ax = fig.add_subplot(pos["D"]); tag(ax, "D", "Incubation period (exposure to onset)")
        v = main_inc_data()
        fit_panel(ax, v, "incubation", bins=np.arange(0, 43, 2), xlim=(-1, 42), ylab="Proportion per day")
        ax.set_xlabel("Days")
    cap_a = (" A: dashed line = overall SAR; colour = risk ratio vs reference with 95% CI above/below 1 (bootstrap; Wald if <5 secondary cases)." if "A" in pos else "")
    cap_bd = (" B–D: main-analysis pairs (SI-1); C: median difference with bootstrap 95% CI. B, D: lines = fitted gamma (posterior median, 95% CrI), "
              "adjusted for censoring and right truncation; D bars = onset minus midpoint of exposure window.") if "B" in pos else ""
    caption(fig, CAP + cap_a + cap_bd, y={"main": 0.0, "wide": 0.0, "slide_sar": 0.0, "slide_timing": -0.08}[layout])
    fig.savefig(outname); plt.close(fig)



_sp = main_si_pairs(); _rng = np.random.default_rng(2026); _rows = []
for _st in ["household", "hospital"]:
    _v = _sp.loc[_sp.case_circumstances == _st, "si"].values
    _b = [np.median(_rng.choice(_v, len(_v))) for _ in range(5000)]
    _rows.append(dict(setting=_st, n_pairs=len(_v), median=np.median(_v), median_lo=np.percentile(_b, 2.5), median_hi=np.percentile(_b, 97.5), mean=_v.mean()))
_vh, _vo = (_sp.loc[_sp.case_circumstances == s_, "si"].values for s_ in ["household", "hospital"])
_b = [np.median(_rng.choice(_vo, len(_vo))) - np.median(_rng.choice(_vh, len(_vh))) for _ in range(5000)]
_rows.append(dict(setting="hospital - household", n_pairs=len(_vh) + len(_vo), median=np.median(_vo) - np.median(_vh),
                  median_lo=np.percentile(_b, 2.5), median_hi=np.percentile(_b, 97.5), mean=_vo.mean() - _vh.mean()))
_rows.append(dict(setting="other/unknown (not shown)", n_pairs=int((~_sp.case_circumstances.isin(["household", "hospital"])).sum())))
pd.DataFrame(_rows).to_csv(os.path.join(T, "serial_interval_by_setting.csv"), index=False)

make_fig4('cdf', os.path.join(F, 'fig4_epi_implications.png'), sar_label="incl. CT 'case validated'")   # manuscript Figure 4 (with CV)
for _lay, _fn in [("wide", "fig4_epi_implications_wide.png"), ("slide_sar", "fig4_slide1_sar.png"), ("slide_timing", "fig4_slide2_timing.png")]:
    make_fig4('cdf', os.path.join(FA, _fn), sar_label="incl. CT 'case validated'", layout=_lay)   # presentation versions
make_fig4('cdf', os.path.join(FA, 'fig4_epi_implications_withoutCV.png'), rf=pd.read_csv(os.path.join(T, "sar_risk_factors_strict.csv")),
          sar_overall=R["sar_strict"][0], sar_label="excl. CT 'case validated' (sensitivity)")

# =============================================================== SI FIGURES
# S1: weekly by health zone (facets with ink strips)
hzw = pd.read_csv(os.path.join(T, "weekly_top_hz.csv"), parse_dates=["week"])
fig, axs = plt.subplots(3, 2, figsize=(7.2, 6.4), sharex=True)
for ax, hz in zip(axs.flat, R["top_hz"]):
    d = hzw[(hzw.health_zone == hz) & (hzw.week >= FIRST_ONSET_WEEK)].set_index("week").sort_index()
    ax.bar(d.index, d.new_cases, width=6, color=MUTED, label="New cases")
    ax.bar(d.index, d.new_cases_became_source, width=6, color=INK, label="…of which became source cases")
    ax2 = ax.twinx(); ax2.plot(d.index, d.new_contacts, color=ALERT, lw=1.2, label="New contacts listed")
    ax2.grid(False); ax2.tick_params(labelsize=BASE * .7, colors=ALERT); ax2.set_ylim(0, max(10, d.new_contacts.max() * 1.05))
    strip(ax, hz); date_axis(ax); ax.grid(axis="x", visible=False)
axs[0, 0].set_ylabel("Cases"); axs[1, 0].set_ylabel("Cases"); axs[2, 0].set_ylabel("Cases")
h1, l1 = axs[0, 0].get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
fig.legend(h1 + h2, l1 + l2, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.03))
fig.tight_layout(rect=(0, 0.03, 1, 1))
caption(fig, CAP, y=-0.04)
fig.savefig(os.path.join(F, "figS1_hz_timeseries.png")); plt.close(fig)

# S2: SAR & follow-up completeness maps
fig = plt.figure(figsize=(7.2, 3.6))
ax = fig.add_subplot(1, 3, 1); tag(ax, "A", "Contacts per source case")
mz = src.groupby("health_zone").n_contacts.median()
draw_map(ax, mz.to_dict(), norm=LogNorm(1, max(mz.max(), 2)), label="Median contacts per source (log)")
ax = fig.add_subplot(1, 3, 2); tag(ax, "B", "Follow-up completeness")
fz = pr.groupby("src_health_zone").fu_complete.mean() * 100
draw_map(ax, fz.to_dict(), norm=Normalize(0, 100), label="Mean % of 21 days with a result")
ax = fig.add_subplot(1, 3, 3); tag(ax, "C", "Secondary attack rate")
E = pr[pr.eligible]
sz = E.groupby("src_health_zone").agg(k=("secondary_case", "sum"), n=("secondary_case", "size"))
sz = sz[sz.n >= 50]
draw_map(ax, (100 * sz.k / sz.n).to_dict(), norm=Normalize(0, 5), label="SAR % (zones ≥50 eligible contacts)")
caption(fig, CAP)
fig.savefig(os.path.join(FA, "maps_ct.png")); plt.close(fig)

# S3: follow-ups per contact distribution, by province
fig, axs = plt.subplots(1, 2, figsize=(7.2, 2.8))
pc = pr[pr.window_closed]
ax = axs[0]; tag(ax, "A", "Days with a recorded follow-up result")
ax.hist(pc.n_fu_with_result.clip(upper=25), bins=range(0, 27), color=MAIN, edgecolor="white", lw=0.3)
ax.axvline(21, color=ALERT, ls="--", lw=0.8); ax.text(21.3, ax.get_ylim()[1] * .9, "21 days", color=ALERT, fontsize=BASE * .7)
ax.set_xlabel("Days with result (closed windows)"); ax.set_ylabel("Contacts"); ax.grid(axis="x", visible=False)
ax = axs[1]; tag(ax, "B", "By province of source case")
provs = ["Ituri", "Nord-Kivu", "Haut-Uele", "Tshopo", "Bas-Uele"]
data = [pc.loc[pc.src_province == p, "n_fu_with_result"].values for p in provs]
ax.boxplot(data, widths=0.55, patch_artist=True, showfliers=False, medianprops=dict(color=ALERT, lw=1.5),
           boxprops=dict(facecolor=LIGHT, edgecolor=INK, lw=0.6), whiskerprops=dict(color=INK, lw=0.6), capprops=dict(color=INK, lw=0.6))
ax.set_xticks(range(1, len(provs) + 1)); ax.set_xticklabels([f"{p}\n(n={len(d):,})" for p, d in zip(provs, data)], fontsize=BASE * .7)
ax.set_ylabel("Days with result"); ax.grid(axis="x", visible=False)
fig.tight_layout()
caption(fig, CAP)
fig.savefig(os.path.join(F, "figS3_followup_days_with_result.png")); plt.close(fig)
print("figures done")
