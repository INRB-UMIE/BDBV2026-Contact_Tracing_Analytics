"""
Step 14: person-registry sensitivity analysis.

Compares the main run (person IDs from the CONFIRMED registry, as exported) with the run in
which person IDs were re-issued from the CANDIDATE registry (every algorithm-suggested match
accepted; see CT_PERSON_REGISTRY in ctr_paths.py). Run this after both runs exist:

    ./run_report.sh                 # main run      -> outputs/<DATE>/
    ./run_report.sh --candidates    # candidate run -> outputs/<DATE>/registry_candidates/ (calls this script)

Neither registry file is opened here; only the two runs' outputs are read.

Outputs (in the candidate run's folder):
  tables/registry_sensitivity.csv              confirmed vs candidate for the headline numbers (aggregate only)
  figures/additional/registry_sensitivity.png  SAR (all definitions) and offspring dispersion k, side by side

Settings: CT_MAIN_OUT overrides where the main (confirmed) run is read from (default outputs/<DATE>/).
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ctr_paths import OUT_ROOT, MAIN_OUT_ROOT, PERSON_REGISTRY, T, FA, CUT_LABEL

if PERSON_REGISTRY != "candidates":
    sys.exit("14_registry_sensitivity.py compares against the candidate run: set CT_PERSON_REGISTRY=candidates "
             "(or use ./run_report.sh --candidates).")

RUNS = {"confirmed": os.environ.get("CT_MAIN_OUT", "") or MAIN_OUT_ROOT, "candidates": OUT_ROOT}
for lab, root in RUNS.items():
    if not os.path.exists(os.path.join(root, "tables", "sar_sensitivity.csv")):
        sys.exit(f"No {lab} run found in {root} (tables/sar_sensitivity.csv missing). Run that pipeline first.")


def tab(run, name):
    p = os.path.join(RUNS[run], "tables", name)
    return pd.read_csv(p) if os.path.exists(p) else None


def results(run):
    p = os.path.join(RUNS[run], "derived", "results.json")
    return json.load(open(p)) if os.path.exists(p) else None


rows = []


def add(section, metric, conf, cand, unit=""):
    rows.append(dict(section=section, metric=metric, unit=unit, confirmed=conf, candidates=cand))


# ---- 1. what the candidate registry changed (from the candidate run's decision log) --------
dl = pd.read_csv(os.path.join(OUT_ROOT, "derived", "decisions_log.csv"))
for _, r in dl[dl["item"].str.contains("re-issued|differs from the registry", regex=True)].iterrows():
    add("ID re-issue (candidate run)", f"{r['step']}: {r['item']}", np.nan, r["n"], "rows")
dl_conf = os.path.join(RUNS["confirmed"], "derived", "decisions_log.csv")
selfp = "rows where source person = contact person (self-pairs)"
if os.path.exists(dl_conf):
    a = pd.read_csv(dl_conf).set_index("item").n
    add("ID re-issue (candidate run)", "CT rows dropped as self-pairs", a.get(selfp, np.nan),
        dl.set_index("item").n.get(selfp, np.nan), "rows")

# ---- 2. counts and process indicators (results.json; person-level run files) ---------------
R = {k: results(k) for k in RUNS}
if all(R.values()):
    for key, lab in [("n_cases", "Cases (confirmed + probable persons)"),
                     ("n_source", "Source persons (CT)"),
                     ("n_source_confirmed", "Source persons who are linelist cases"),
                     ("n_contacts", "Contact persons (CT)"),
                     ("n_pairs", "Source-contact pairs"),
                     ("n_contacts_multi_source", "Contacts listed under >1 source"),
                     ("n_cases_contact_any_time", "Cases who were ever a listed contact"),
                     ("n_cases_prev_contact", "Cases known as a contact before notification"),
                     ("sar_eligible_pairs", "SAR denominator (eligible pairs)"),
                     ("sar_secondary", "SAR numerator (secondary cases, main definition)"),
                     ("si_pairs_with_dates", "Case-case pairs with both onset dates"),
                     ("inc_with_dates", "Pairs with dates for incubation")]:
        add("Counts", lab, R["confirmed"].get(key), R["candidates"].get(key), "n")
    for key, lab in [("pct_cases_source", "% cases who are a CT source"),
                     ("pct_cases_contact", "% cases who were a listed contact"),
                     ("pct_cases_prev_contact", "% cases known as a contact before notification"),
                     ("sources_with_secondary", "% eligible sources with >=1 secondary case"),
                     ("fu21_complete", "% contacts with complete 21-day follow-up")]:
        c, k = R["confirmed"].get(key), R["candidates"].get(key)
        add("Indicators", lab, c[0] * 100 if c else np.nan, k[0] * 100 if k else np.nan, "%")
    for key, lab in [("serial_interval", "Serial interval, empirical"), ("incubation", "Incubation, empirical")]:
        c, k = R["confirmed"].get(key, {}), R["candidates"].get(key, {})
        add("Delays (empirical)", f"{lab}: n pairs", c.get("n"), k.get("n"), "n")
        add("Delays (empirical)", f"{lab}: mean", c.get("mean"), k.get("mean"), "days")
        add("Delays (empirical)", f"{lab}: median", c.get("median"), k.get("median"), "days")
else:
    print("NOTE: derived/results.json missing for one run (derived/ is not committed); "
          "counts section skipped - rerun the main pipeline locally to include it.")

# ---- 3. SAR, all definitions (tables/sar_sensitivity.csv) ---------------------------------
S = {k: tab(k, "sar_sensitivity.csv").set_index("analysis") for k in RUNS}
for an in S["confirmed"].index:
    c, k = S["confirmed"].loc[an], S["candidates"].loc[an] if an in S["candidates"].index else None
    if k is None:
        continue
    lab = c["label"] if str(c["label"]).startswith(an) else f"{an}: {c['label']}"
    add("SAR", lab, c["sar"], k["sar"], "%")
    add("SAR", f"{an}: bootstrap 95% CI", f"{c['boot_lo']:.2f}-{c['boot_hi']:.2f}", f"{k['boot_lo']:.2f}-{k['boot_hi']:.2f}", "%")
    add("SAR", f"{an}: k/n", f"{int(c['k'])}/{int(c['n_pairs'])}", f"{int(k['k'])}/{int(k['n_pairs'])}", "")

# ---- 4. offspring dispersion ------------------------------------------------------------
O = {k: tab(k, "offspring_dispersion.csv") for k in RUNS}
if all(x is not None for x in O.values()):
    for _, c in O["confirmed"].iterrows():
        k = O["candidates"][O["candidates"].definition == c.definition]
        if not len(k):
            continue
        k = k.iloc[0]
        add("Offspring", f"{c.definition}: mean secondary cases per source", c.mean_secondary_per_source, k.mean_secondary_per_source, "n")
        add("Offspring", f"{c.definition}: dispersion k (NB)", c.nb_k, k.nb_k, "")
        add("Offspring", f"{c.definition}: % sources causing 80% of cases", c.t80_pct_sources_for_80pct_cases, k.t80_pct_sources_for_80pct_cases, "%")

# ---- 5. fitted serial interval / incubation (only if the R fits exist for both runs) ---------
G = {k: tab(k, "distribution_fits_main_gamma.csv") for k in RUNS}
if all(x is not None for x in G.values()):
    for _, c in G["confirmed"].iterrows():
        k = G["candidates"][G["candidates"].Quantity == c.Quantity]
        if len(k):
            k = k.iloc[0]
            add("Fitted delays (gamma)", f"{c.Quantity}: n", c.n, k.n, "n")
            add("Fitted delays (gamma)", f"{c.Quantity}: mean (95% CrI)", c["Mean (95% CrI)"], k["Mean (95% CrI)"], "days")
else:
    add("Fitted delays (gamma)", "not compared: R fits missing for one run (use --fit)", np.nan, np.nan, "")

# ---- write table -------------------------------------------------------------------------
out = pd.DataFrame(rows)
num = pd.to_numeric(out.confirmed, errors="coerce"), pd.to_numeric(out.candidates, errors="coerce")
out["difference"] = (num[1] - num[0]).round(4)
out["pct_change"] = ((num[1] - num[0]) / num[0].replace(0, np.nan) * 100).round(1)
out.loc[out.unit.eq("%") | out.section.eq("ID re-issue (candidate run)"), "pct_change"] = np.nan
out.insert(0, "data_cut", CUT_LABEL)
out.to_csv(os.path.join(T, "registry_sensitivity.csv"), index=False)
print(out.to_string(index=False))

# ---- figure: SAR by definition + offspring k -------------------------------------------------
INK, MAIN, ALERT, GRID = "#01454f", "#1a8c99", "#e0703f", "#e6eef0"
plt.rcParams.update({"font.size": 8.5, "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK,
                     "ytick.color": INK, "axes.edgecolor": INK, "axes.linewidth": 0.5, "axes.grid": True,
                     "grid.color": GRID, "axes.axisbelow": True, "axes.titleweight": "bold",
                     "axes.titlelocation": "left", "legend.frameon": False, "savefig.dpi": 300, "savefig.bbox": "tight"})
COL = {"confirmed": MAIN, "candidates": ALERT}
LAB = {"confirmed": "Confirmed registry (main)", "candidates": "Candidate registry (all suggested matches)"}

fig, axes = plt.subplots(1, 2, figsize=(9, 3.2), gridspec_kw=dict(width_ratios=[1.4, 1]))
ax = axes[0]
an = list(S["confirmed"].index)
y = np.arange(len(an))
for j, run in enumerate(RUNS):
    s = S[run].reindex(an)
    yy = y + (-0.12 if j == 0 else 0.12)
    ax.errorbar(s.sar, yy, xerr=[s.sar - s.boot_lo, s.boot_hi - s.sar], fmt="o", color=COL[run], ms=4,
                capsize=2, lw=1, label=LAB[run])
ax.set_yticks(y, [f"{a}" for a in an]); ax.invert_yaxis()
ax.set_xlabel("SAR, % (95% CI, bootstrap by source)"); ax.set_title("Secondary attack rate")
ax.set_xlim(left=0)
fig.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=2, fontsize=7.5, bbox_to_anchor=(0.5, -0.04))

ax = axes[1]
if all(x is not None for x in O.values()):
    defs = list(O["confirmed"].definition)
    y = np.arange(len(defs))
    for j, run in enumerate(RUNS):
        o = O[run].set_index("definition").reindex(defs)
        yy = y + (-0.12 if j == 0 else 0.12)
        ax.errorbar(o.nb_k, yy, xerr=[o.nb_k - o.nb_k_lo, o.nb_k_hi - o.nb_k], fmt="o", color=COL[run], ms=4, capsize=2, lw=1)
    ax.set_yticks(y, defs); ax.invert_yaxis()
    ax.set_xlabel("Dispersion k (negative binomial, 95% CI)"); ax.set_title("Offspring dispersion")
else:
    ax.axis("off")
fig.suptitle(f"Person-registry sensitivity, data cut {CUT_LABEL}", x=0.01, ha="left", fontsize=9.5, fontweight="bold")
fig.tight_layout(rect=(0, 0.06, 1, 1))
fig.savefig(os.path.join(FA, "registry_sensitivity.png")); plt.close(fig)
print("Wrote", os.path.join(T, "registry_sensitivity.csv"), "and", os.path.join(FA, "registry_sensitivity.png"))
