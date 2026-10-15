"""
Step 11: distribution of secondary cases per source case (offspring distribution), to look at
superspreading.

Population: the SAR denominator. Source cases are confirmed/probable linelist cases with >=1
eligible pair (contact's first follow-up, or registration if none, on/before data cut - 21 days).
Source cases with zero secondary cases are included.
Secondary case: main SAR definition (linelist confirmed/probable, or CT 'case confirmed' /
'case validated'; linelist not_a_case overrides). The 'excluding case validated' definition is
shown alongside.

Note: these are secondary cases found among *listed* contacts, so they are a lower bound on each
case's true number of onward infections (incomplete listing and follow-up).

Writes:
  figures/figS9_offspring_distribution.png   (manuscript Fig S9: A secondary cases per source; B per-source attack rate)
  tables/offspring_distribution.csv, tables/offspring_source_attack_rate.csv
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches

from ctr_paths import D, T, F, FA

INK, MAIN, LIGHT, MUTED, ALERT, SUB, GRID = "#01454f", "#1a8c99", "#e3f0f1", "#a3b9bc", "#e0703f", "#4a7378", "#e6eef0"
BASE = 8.5
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Liberation Sans", "Helvetica", "DejaVu Sans"], "font.size": BASE, "text.color": INK, "axes.labelcolor": INK,
    "xtick.color": INK, "ytick.color": INK, "axes.edgecolor": INK, "axes.linewidth": 0.5,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.4, "axes.axisbelow": True,
    "axes.titleweight": "bold", "axes.titlesize": BASE * 1.05, "axes.titlelocation": "left", "axes.titlecolor": INK,
    "legend.frameon": False, "figure.facecolor": "white", "savefig.dpi": 300, "savefig.bbox": "tight",
})

pr = pd.read_csv(os.path.join(D, "pairs_annotated.csv"), low_memory=False)
E = pr[pr.eligible.astype(bool)].copy()

DEFS = [("Main (incl. 'case validated')", "secondary_case", INK),
        ("Excl. 'case validated'", "secondary_strict", MUTED)]
SMALL = 5     # sources with fewer eligible contacts than this are hatched in B (proportions unstable)
PSTEP = 5     # B: bin width in percentage points; bins centred on 0, 5, 10, ... 100
n_con = E.groupby("source_case_person_id").size()
KS = {lab: E[col].fillna(False).astype(bool).groupby(E.source_case_person_id).sum() for lab, col, _ in DEFS}
KMAX = int(max(k.max() for k in KS.values()))

rows, prow, per_def = [], [], {}
for lab, k in KS.items():
    s = k.sort_values(ascending=False)
    top10 = s.iloc[:int(round(0.1 * len(s)))].sum() / s.sum()
    per_def[lab] = dict(n_src=len(k), n_sec=int(k.sum()), mean=k.mean(), var=k.var(), pct0=100 * (k == 0).mean(), top10=100 * top10,
                        n_ge5=int((k >= 5).sum()), sec_ge5=int(k[k >= 5].sum()))
    for v in range(KMAX + 1):                                   # every integer, no grouping
        n = int((k == v).sum())
        rows.append(dict(definition=lab, secondary_cases=v, source_cases=n, pct_source_cases=100 * n / len(k)))
    pct = 100 * k / n_con
    centre = (np.round(pct / PSTEP) * PSTEP).astype(int)          # nearest multiple of PSTEP
    for c0 in range(0, 101, PSTEP):
        m = centre == c0
        prow.append(dict(definition=lab, attack_rate_bin_centre_pct=c0,
                         bin=f"{max(c0 - PSTEP / 2, 0):g}–{min(c0 + PSTEP / 2, 100):g}%",
                         source_cases=int(m.sum()), source_cases_lt5_contacts=int((m & (n_con < SMALL)).sum())))
tab = pd.DataFrame(rows); ptab = pd.DataFrame(prow)
tab.to_csv(os.path.join(T, "offspring_distribution.csv"), index=False)
ptab.to_csv(os.path.join(T, "offspring_source_attack_rate.csv"), index=False)
for lab, v in per_def.items():
    print(lab, {a: round(float(b), 2) for a, b in v.items()})


# ---- overdispersion
# (1) Negative binomial fit to secondary cases per source (offspring distribution):
#     mean m (MLE = sample mean; 95% CI by bootstrap over source cases) and dispersion k
#     (MLE by profile likelihood over a fine grid; 95% CI = log-likelihood within 1.92 of max).
#     Small k = more superspreading (k -> infinity is Poisson). Also t80 = share of source cases
#     expected to generate 80% of secondary cases under the fitted NB (Lloyd-Smith et al. 2005).
# (2) Beta-binomial fit to k_i secondary cases out of n_i eligible contacts per source: mean
#     attack rate mu and intra-cluster correlation rho (0 = contacts independent, i.e. binomial).
#     This version accounts for sources listing different numbers of contacts.
from math import lgamma
LG = np.vectorize(lgamma)
rng = np.random.default_rng(20261009)


def nb_ll(x, m, k):
    return (LG(x + k) - LG(k) - LG(x + 1) + k * np.log(k / (k + m)) + x * np.log(m / (k + m))).sum()


def bb_ll(x, n, mu, rho):
    a = mu * (1 - rho) / rho; b = (1 - mu) * (1 - rho) / rho
    return (LG(n + 1) - LG(x + 1) - LG(n - x + 1) + LG(x + a) + LG(n - x + b) - LG(n + a + b) + LG(a + b) - LG(a) - LG(b)).sum()


def ci_from(grid, ll):
    ok = grid[ll >= ll.max() - 1.92]
    return grid[ll.argmax()], ok.min(), ok.max()


disp = []
for lab, k in KS.items():
    x = k.values.astype(float); n_ = n_con.reindex(k.index).values.astype(float)
    m = x.mean(); m_lo, m_hi = np.percentile([rng.choice(x, len(x)).mean() for _ in range(2000)], [2.5, 97.5])
    kg = np.exp(np.linspace(np.log(0.01), np.log(20), 1500))
    kh, k_lo, k_hi = ci_from(kg, np.array([nb_ll(x, m, kk) for kk in kg]))
    ll_pois = (x * np.log(m) - m - LG(x + 1)).sum()
    xs = np.arange(0, 2000)
    pm = np.exp(LG(xs + kh) - LG(kh) - LG(xs + 1) + kh * np.log(kh / (kh + m)) + xs * np.log(m / (kh + m)))
    t80 = np.interp(0.8, np.cumsum((xs * pm)[::-1]) / (xs * pm).sum(), np.cumsum(pm[::-1]))
    # beta-binomial: profile over rho, maximising over mu at each rho
    mug = np.linspace(0.002, 0.08, 157); rhog = np.exp(np.linspace(np.log(1e-4), np.log(0.95), 200))
    LL = np.array([[bb_ll(x, n_, mu, r) for mu in mug] for r in rhog])
    rh, r_lo, r_hi = ci_from(rhog, LL.max(axis=1))
    mu_h, mu_lo, mu_hi = ci_from(mug, LL.max(axis=0))
    disp.append(dict(definition=lab, n_source_cases=len(x), mean_secondary_per_source=m, mean_lo=m_lo, mean_hi=m_hi,
                     nb_k=kh, nb_k_lo=k_lo, nb_k_hi=k_hi, lrt_nb_vs_poisson=2 * (nb_ll(x, m, kh) - ll_pois),
                     t80_pct_sources_for_80pct_cases=100 * t80, empirical_top10pct_sources_pct_cases=per_def[lab]["top10"],
                     betabinom_mean_attack_rate=mu_h, bb_mu_lo=mu_lo, bb_mu_hi=mu_hi, betabinom_icc_rho=rh, bb_rho_lo=r_lo, bb_rho_hi=r_hi))
DISP = pd.DataFrame(disp)
DISP.to_csv(os.path.join(T, "offspring_dispersion.csv"), index=False)
print(DISP.round(3).T.to_string())


def logy(ax):
    ax.set_yscale("symlog", linthresh=1); ax.set_ylim(0, 600 * 2.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.grid(axis="x", visible=False)


def labels(ax, xx, yy, c):
    for xi, yi in zip(xx, yy):
        if yi > 0:
            ax.text(xi, yi, f"{yi:,}", ha="center", va="bottom", fontsize=BASE * .58, color=c if c != MUTED else SUB)


fig, axes = plt.subplots(2, 1, figsize=(8.6, 6.6), gridspec_kw=dict(hspace=0.45))
# ---- A: secondary cases per source, one bar per integer
ax = axes[0]; x = np.arange(KMAX + 1); w = 0.42
for j, (lab, _, c) in enumerate(DEFS):
    y = tab[tab.definition == lab].source_cases.values
    xx = x + (j - 0.5) * w
    ax.bar(xx, y, width=w, color=c, label=lab); labels(ax, xx, y, c)
logy(ax); ax.set_xlim(-0.7, KMAX + 0.7); ax.set_xticks(x)
ax.set_xlabel("Secondary cases among listed contacts"); ax.set_ylabel("Source cases (log scale)")
ax.set_title("A  Source cases by number of secondary cases")

# ---- B: per-source attack rate, linear 0-100% axis
ax = axes[1]; wb = PSTEP * 0.42
for j, (lab, _, c) in enumerate(DEFS):
    d = ptab[ptab.definition == lab]
    xx = d.attack_rate_bin_centre_pct.values + (j - 0.5) * wb
    few = d.source_cases_lt5_contacts.values
    big = d.source_cases.values - few
    ax.bar(xx, big, width=wb, color=c, label=lab)
    ax.bar(xx, few, bottom=big, width=wb, color="white", edgecolor=c, hatch="////", lw=0.6)   # <5 contacts: stripes
    labels(ax, xx, d.source_cases.values, c)
h, l = ax.get_legend_handles_labels()
h.append(matplotlib.patches.Patch(facecolor="white", edgecolor=SUB, hatch="////", lw=0.6)); l.append(f"of which <{SMALL} eligible contacts")
logy(ax); ax.set_xlim(-PSTEP, 100 + PSTEP); ax.set_xticks(range(0, 101, 10))
ax.set_xlabel("% of the source case's eligible contacts who became cases"); ax.set_ylabel("Source cases (log scale)")
ax.set_title("B  Source cases by their own attack rate"); ax.grid(axis="x", visible=False)
m = per_def[DEFS[0][0]]; s_ = per_def[DEFS[1][0]]
dm, ds = DISP.iloc[0], DISP.iloc[1]
axes[0].text(0.98, 0.97, f"Main: {m['n_src']} source cases, {m['n_sec']} secondary cases; {m['pct0']:.0f}% had none\n"
                         f"Negative binomial: mean {dm.mean_secondary_per_source:.2f} ({dm.mean_lo:.2f}–{dm.mean_hi:.2f}), "
                         f"dispersion k = {dm.nb_k:.2f} ({dm.nb_k_lo:.2f}–{dm.nb_k_hi:.2f})\n"
                         f"top 10% of source cases → {m['top10']:.0f}% of secondary cases\n"
                         f"Excl. 'case validated': mean {ds.mean_secondary_per_source:.2f}, k = {ds.nb_k:.2f} ({ds.nb_k_lo:.2f}–{ds.nb_k_hi:.2f}); top 10% → {s_['top10']:.0f}%",
             transform=axes[0].transAxes, ha="right", va="top", fontsize=BASE * .66, color=INK)
axes[1].legend(h, l, loc="upper right", fontsize=BASE * .72)
fig.text(0.01, 0.0, "Data cut 9 Oct 2026. Source cases = confirmed/probable cases with ≥1 contact whose follow-up window closed by 18 Sep 2026 (SAR denominator). "
         "Secondary cases found among listed contacts only (a lower bound). B: secondary cases ÷ eligible contacts of each source, in 5-point bins centred on 0, 5, …, 100%; hatched = sources with <5 eligible contacts. Log y-axis.",
         color=MUTED, fontsize=BASE * .7, ha="left", va="top", wrap=True)
fig.savefig(os.path.join(F, "figS9_offspring_distribution.png")); plt.close(fig)
