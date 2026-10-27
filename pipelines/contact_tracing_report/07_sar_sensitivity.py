"""
Step 7: SAR sensitivity analyses + Nyankunde 'case validated' analysis.
Reads derived/ from 01-02. Writes:
  tables/sar_sensitivity.csv              main SAR + sensitivity analyses (Wilson + source-clustered bootstrap CIs)
  tables/nyankunde_cluster_summary.csv    description of the Nyankunde May-June hospital cluster
  tables/nyankunde_sar_by_definition.csv  SAR in Nyankunde by period x secondary-case definition
  figures/figS4_sar_sensitivity.png
  figures/figS5_nyankunde_case_validated.png

Sensitivity analyses (manuscript):
  Main    linelist confirmed/probable OR CT 'case_confirmed' OR CT 'case_validated'
  SAR-1   excluding CT 'case_validated'
  SAR-5   linelist confirmed/probable cases only (no CT outcomes)
  SAR-6   main definition, excluding the Nyankunde cluster
Nyankunde cluster = source case in Nyankunde health zone, hospital exposure, contact registered
on/before 30 June 2026 (59 of the 64 eligible 'case_validated' contacts fall in it).
"""
import os, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker

from ctr_paths import D, T, F, FA, CUT_LABEL, FU_WINDOW_END, fmt_day

INK, MAIN, LIGHT, MUTED, ALERT, SUB, GRID = "#01454f", "#1a8c99", "#e3f0f1", "#a3b9bc", "#e0703f", "#4a7378", "#e6eef0"
BASE = 8.5
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans"], "font.size": BASE, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK, "axes.edgecolor": INK, "axes.linewidth": 0.5,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.4, "axes.axisbelow": True,
    "axes.titleweight": "bold", "axes.titlesize": BASE * 1.05, "axes.titlelocation": "left", "axes.titlecolor": INK,
    "legend.frameon": False, "figure.facecolor": "white", "savefig.dpi": 300, "savefig.bbox": "tight",
})
CAP = f"Data cut {CUT_LABEL}; person-level after ID harmonisation."
CLUSTER_END = pd.Timestamp("2026-06-30")   # fixed: end of the Nyankunde hospital cluster (not cut-dependent)
LATE = f"Jul-{FU_WINDOW_END:%b}"            # later Nyankunde period, up to the SAR window end ("Jul-Sep" for the 9 Oct cut)
N_BOOT = 2000
rng = np.random.default_rng(20261009)

pr = pd.read_csv(os.path.join(D, "pairs_annotated.csv"), low_memory=False,
                 parse_dates=["registration", "last_contact", "first_fu", "con_notification"])
fu = pd.read_csv(os.path.join(D, "followups.csv"), low_memory=False, parse_dates=["followup_date"])
cases = pd.read_csv(os.path.join(D, "cases_annotated.csv"), low_memory=False, parse_dates=["notification"])
E = pr[pr.eligible.astype(bool)].copy()

E["nyk_cluster"] = (E.src_health_zone.eq("Nyankunde") & E.case_circumstances.eq("hospital")
                    & (E.registration <= CLUSTER_END))
DEFS = {"main": "secondary_case", "strict": "secondary_strict", "linelist": "sec_ll"}


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan,) * 3
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0, c - h), min(1, c + h)


def boot(df, col):
    a = df.groupby("source_case_person_id")[col].agg(["sum", "size"]).values
    if len(a) < 2:
        return (np.nan, np.nan)
    i = rng.integers(0, len(a), (N_BOOT, len(a)))
    b = a[i, 0].sum(1) / a[i, 1].sum(1)
    return tuple(np.percentile(b, [2.5, 97.5]))


def sar_row(label, analysis, df, col):
    k, n = int(df[col].astype(bool).sum()), len(df)
    p, lo, hi = wilson(k, n)
    blo, bhi = boot(df.assign(**{col: df[col].astype(bool)}), col)
    return dict(analysis=analysis, label=label, n_pairs=n, n_sources=df.source_case_person_id.nunique(), k=k,
                sar=100 * p, wilson_lo=100 * lo, wilson_hi=100 * hi, boot_lo=100 * blo, boot_hi=100 * bhi)


# ------------------------------------------------------------- SAR sensitivity
rows = [
    sar_row("Main: linelist + CT 'case confirmed' + CT 'case validated'", "Main", E, "secondary_case"),
    sar_row("Excluding CT 'case validated'", "SAR-1", E, "secondary_strict"),
    sar_row("Linelist confirmed/probable cases only", "SAR-5", E, "sec_ll"),
    sar_row("Main definition, excluding Nyankunde May-June hospital cluster", "SAR-6", E[~E.nyk_cluster], "secondary_case"),
]
sens = pd.DataFrame(rows)
sens.round(3).to_csv(os.path.join(T, "sar_sensitivity.csv"), index=False)
print(sens.round(2).to_string())

fig, ax = plt.subplots(figsize=(7.2, 2.6))
for i, r in enumerate(sens.itertuples()):
    y = -i
    col = INK if r.analysis == "Main" else ALERT
    ax.plot([r.boot_lo, r.boot_hi], [y, y], color=col, lw=1.2, alpha=.45, solid_capstyle="butt")
    ax.plot([r.wilson_lo, r.wilson_hi], [y, y], color=col, lw=2.3, solid_capstyle="round")
    ax.plot(r.sar, y, "s" if r.analysis == "Main" else "o", color=col, ms=5, mec="white", mew=0.5, zorder=3)
    ax.text(r.boot_hi + 0.08, y, f"{r.sar:.1f}% ({r.k}/{r.n_pairs:,})", va="center", fontsize=BASE * .8)
ax.axvline(sens.sar.iloc[0], color=INK, ls=":", lw=0.8)
ax.set_yticks([-i for i in range(len(sens))])
ax.set_yticklabels([f"{a}: {l}" if a != "Main" else l for a, l in zip(sens.analysis, sens.label)], fontsize=BASE * .82)
ax.set_xlim(0, max(sens.boot_hi) + 1.6); ax.set_ylim(-len(sens) + 0.4, 0.6)
ax.set_xlabel("Secondary attack rate, %"); ax.grid(axis="y", visible=False)
ax.set_title("Secondary attack rate: main vs sensitivity analyses", pad=6)
ax.plot([], [], color=INK, lw=2.3, solid_capstyle="round", label="95% CI (Wilson)"); ax.plot([], [], color=INK, lw=1.2, alpha=.45, label="95% CI (bootstrap by source case)")
ax.legend(loc="lower right", ncol=1, fontsize=BASE * .75, frameon=True, framealpha=.95, edgecolor=GRID)
fig.text(0.01, -0.12, CAP + f" Denominator: contacts of confirmed/probable source cases whose first follow-up was on or before {fmt_day(FU_WINDOW_END)}.",
         color=MUTED, fontsize=BASE * .72, ha="left", va="top", wrap=True)
fig.savefig(os.path.join(F, "figS4_sar_sensitivity.png")); plt.close(fig)

# ------------------------------------------------------------- Nyankunde analysis
k2 = ["source_case_person_id", "contact_person_id"]
cv_rows = fu[fu.followup_result.eq("case_validated")]
cv_first = cv_rows.groupby(k2).followup_date.min().rename("cv_date")
P = pr.join(cv_first, on=k2)
Pcv = P[P.cv_date.notna()]                                  # all pairs ever 'case_validated' (any source)
Pny = Pcv[Pcv.src_health_zone.eq("Nyankunde")]
after = fu.join(cv_first, on=k2, how="inner")
after = after[after.followup_date > after.cv_date]
n_after = after.groupby(k2).ngroups
cl = P[P.src_health_zone.eq("Nyankunde") & P.case_circumstances.eq("hospital") & (P.registration <= CLUSTER_END)]
summary = pd.DataFrame([
    ("Pairs ever recorded 'case validated' (all sources)", len(Pcv)),
    ("  of which source in Nyankunde", len(Pny)),
    ("  of which source not located (non-standard ID)", int(Pcv.src_health_zone.isna().sum())),
    ("  of which hospital exposure", int(Pcv.case_circumstances.eq("hospital").sum())),
    ("  'case validated' recorded between", f"{Pcv.cv_date.min():%d %b} and {Pcv.cv_date.max():%d %b %Y}"),
    ("  median days from last exposure to 'case validated'", float((Pcv.cv_date - Pcv.last_contact).dt.days.median())),
    ("  median days from 'case validated' to CT registration", float((Pcv.registration - Pcv.cv_date).dt.days.median())),
    ("  found in linelist (any classification)", int(Pcv.con_in_ll.astype(bool).sum())),
    ("  confirmed/probable in linelist", int(Pcv.sec_ll.astype(bool).sum())),
    ("  with any follow-up row after 'case validated'", n_after),
    ("Cluster: Nyankunde source, hospital, registered <= 30 Jun - source cases", cl.source_case_person_id.nunique()),
    ("Cluster: contacts (pairs)", len(cl)),
    ("Cluster: eligible for SAR", int(cl.eligible.astype(bool).sum())),
    ("Eligible 'case validated' contacts inside cluster / total", f"{int(E.loc[E.nyk_cluster, 'sec_ct_validated'].sum())} / {int(E.sec_ct_validated.sum())}"),
    ("Nyankunde cases notified 15 May-30 Jun (linelist)", int(cases[cases.health_zone.eq("Nyankunde") & cases.notification.between("2026-05-15", "2026-06-30")].shape[0])),
], columns=["item", "value"])
summary.to_csv(os.path.join(T, "nyankunde_cluster_summary.csv"), index=False)
print(summary.to_string(index=False))

Eny = E[E.src_health_zone.eq("Nyankunde")].copy()
Eny["period"] = np.where(Eny.registration <= CLUSTER_END, "May-Jun", LATE)
groups = [("Nyankunde, May-Jun", Eny[Eny.period == "May-Jun"]), (f"Nyankunde, {LATE}", Eny[Eny.period == LATE]),
          ("Nyankunde cluster (hospital, May-Jun)", E[E.nyk_cluster]), ("All other zones/periods", E[~E.nyk_cluster]),
          ("National", E)]
dl = {"main": "Main (incl. 'case validated')", "strict": "Excl. 'case validated'", "linelist": "Linelist cases only"}
nyt = pd.DataFrame([dict(sar_row(dl[dn], g, df, col), group=g) for g, df in groups for dn, col in DEFS.items()])
nyt = nyt.drop(columns="analysis")[["group", "label", "n_pairs", "n_sources", "k", "sar", "wilson_lo", "wilson_hi", "boot_lo", "boot_hi"]]
nyt.round(3).to_csv(os.path.join(T, "nyankunde_sar_by_definition.csv"), index=False)
print(nyt.round(2).to_string())

fig = plt.figure(figsize=(7.4, 6.6))
gs = fig.add_gridspec(2, 2, width_ratios=[1, 1.15], height_ratios=[1, 0.9], wspace=0.95, hspace=0.7)
ax = fig.add_subplot(gs[0, 0])
ax.set_title("A  'Case validated' vs Nyankunde cases", pad=6)
days = pd.date_range("2026-05-10", "2026-07-05")
cvd = Pny.cv_date.value_counts().reindex(days, fill_value=0)
nc = cases[cases.health_zone.eq("Nyankunde")].notification.value_counts().reindex(days, fill_value=0)
ax.bar(days, nc.values, width=0.9, color=MUTED, label="Nyankunde cases notified (linelist)")
ax.bar(days, cvd.values, width=0.9, color=ALERT, alpha=.85, label="Contacts recorded 'case validated'")
ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0, interval=2)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
ax.set_ylabel("Per day"); ax.grid(axis="x", visible=False)
ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.18), ncol=1, fontsize=BASE * .75)
ax = fig.add_subplot(gs[0, 1])
ax.set_title("B  SAR by definition", pad=6)
gorder = [g for g, _ in groups]
colmap = {dl["main"]: INK, dl["strict"]: MAIN, dl["linelist"]: MUTED}
offs = {dl["main"]: 0.22, dl["strict"]: 0.0, dl["linelist"]: -0.22}
for r in nyt.itertuples():
    y = -gorder.index(r.group) + offs[r.label]
    ax.plot([r.boot_lo, r.boot_hi], [y, y], color=colmap[r.label], lw=1.0, alpha=.5, solid_capstyle="butt")    # bootstrap: thin
    ax.plot([r.wilson_lo, r.wilson_hi], [y, y], color=colmap[r.label], lw=2.3, solid_capstyle="round")          # Wilson: thick
    ax.plot(r.sar, y, "o", color=colmap[r.label], ms=4, mec="white", mew=0.4, zorder=3)
ax.set_yticks([-i for i in range(len(gorder))]); ax.set_yticklabels(gorder, fontsize=BASE * .8)
ax.set_xscale("symlog", linthresh=2); ax.set_xlim(0, 100)
ax.set_xticks([0, 1, 2, 5, 10, 20, 50, 100]); ax.set_xticklabels(["0", "1", "2", "5", "10", "20", "50", "100"])
ax.set_xlabel("SAR, % (95% CI: thick = Wilson, thin = bootstrap by source case)", fontsize=BASE * .85); ax.grid(axis="y", visible=False)
for lab, c in colmap.items():
    ax.plot([], [], "o-", color=c, ms=4, lw=1.1, label=lab)
ax.legend(loc="upper center", bbox_to_anchor=(0.3, -0.18), ncol=1, fontsize=BASE * .75)
# ---- C: secondary cases per source case, Nyankunde sources highlighted (cf. additional/offspring_distribution.png)
ax = fig.add_subplot(gs[1, :])
ax.set_title("C  Source cases by number of secondary cases, Nyankunde highlighted", pad=6)
OFF = [("Main (incl. 'case validated')", "secondary_case", INK, ALERT), ("Excl. 'case validated'", "secondary_strict", MUTED, "#f2b79c")]
ks = {lab: E[col].fillna(False).astype(bool).groupby(E.source_case_person_id).sum() for lab, col, _, _ in OFF}
is_ny = E.groupby("source_case_person_id").src_health_zone.first().eq("Nyankunde")
kmax = int(max(k.max() for k in ks.values())); xs = np.arange(kmax + 1); w = 0.42
orow = []
for j, (lab, _, c_oth, c_ny) in enumerate(OFF):
    k = ks[lab]; ny = is_ny.reindex(k.index).fillna(False)
    tot = np.array([(k == v).sum() for v in xs]); nyk = np.array([((k == v) & ny).sum() for v in xs])
    orow += [dict(definition=lab, secondary_cases=int(v), source_cases=int(t), nyankunde_source_cases=int(n)) for v, t, n in zip(xs, tot, nyk)]
    xx = xs + (j - 0.5) * w
    ax.bar(xx, tot - nyk, width=w, color=c_oth, label=f"{lab}: other zones")
    ax.bar(xx, nyk, bottom=tot - nyk, width=w, color=c_ny, label=f"{lab}: Nyankunde")
    for xi, t, n in zip(xx, tot, nyk):
        if t:
            ax.text(xi, t, f"{t:,}", ha="center", va="bottom", fontsize=BASE * .55, color=INK if j == 0 else SUB)
            if n:
                ax.text(xi, t * 2.1 if t > 1 else 2.6, f"{n}", ha="center", va="bottom", fontsize=BASE * .55, color=ALERT, fontweight="bold")
pd.DataFrame(orow).to_csv(os.path.join(T, "nyankunde_offspring_distribution.csv"), index=False)
ax.set_yscale("symlog", linthresh=1); ax.set_ylim(0, 600 * 6)
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
ax.set_xlim(-0.7, kmax + 0.7); ax.set_xticks(xs); ax.grid(axis="x", visible=False)
ax.set_xlabel("Secondary cases among listed contacts"); ax.set_ylabel("Source cases (log scale)")
ax.legend(loc="upper right", ncol=2, fontsize=BASE * .68)
fig.text(0.01, 0.0, CAP + " Cluster = source in Nyankunde, hospital exposure, contact registered on or before 30 Jun 2026. "
         "C: SAR-eligible source cases; dark labels = all source cases, coral labels = of which Nyankunde.",
         color=MUTED, fontsize=BASE * .72, ha="left", va="top", wrap=True)
fig.savefig(os.path.join(F, "figS5_nyankunde_case_validated.png")); plt.close(fig)
print("07 done")
