"""
Step 13: aggregate tables for the dashboard's "Surveillance and Testing" tab.

The dashboard (BDBV2026-Epidemic_Dashboard) is public and must only ever read
AGGREGATE outputs from tables/. Three report panels are drawn in 03_figures.py
straight from person-level derived/ files, so they have no aggregate table; this
step writes one for each, reproducing the 03_figures.py computation:

  tables/dashboard_patient_journey.csv   Fig 2A  delay from onset per journey step
  tables/dashboard_delays_weekly.csv     Fig 2B  median/IQR delay by week of onset
  tables/dashboard_fu21_by_month.csv     Fig 3D  "All zones" line (fu21_by_month)
  tables/dashboard_meta.json             data cut, derived cut-offs, headline numbers

The cut-offs are derived from CT_REPORT_DATE in ctr_paths.py (shared with 03_figures.py):
  ONSET_END       = data cut - 26 days            (Fig 2A/2B right truncation)
  WK_END          = last Monday whose week ends on or before ONSET_END (Fig 2B)
  LAST_FULL_WEEK  = Monday of the week before the data cut's week (Fig 3 shading)

Run after 02_analysis.py. Needs derived/ (person-level) as input; writes
aggregate tables only.
"""
import json
import os

import pandas as pd

from ctr_paths import D, T, REPORT_DATE, CUT, ONSET_END, WK_END, LAST_FULL_WEEK, monday
from ctr_paths import FIRST_ONSET_WEEK as WK_START   # first onset week drawn in Fig 2B
MIN_WEEK_N = 5                             # Fig 2B: weeks with >= 5 cases

R = json.load(open(os.path.join(D, "results.json")))
cases = pd.read_csv(os.path.join(D, "cases_annotated.csv"), low_memory=False,
                    parse_dates=["onset", "notification"])
src = pd.read_csv(os.path.join(D, "sources.csv"), parse_dates=["first_reg"])
pr_fu = pd.read_csv(os.path.join(D, "pairs_annotated.csv"), low_memory=False,
                    usecols=["source_case_person_id", "first_fu", "last_contact"],
                    parse_dates=["first_fu", "last_contact"])

# --- same person-level frame as Figure 2 in 03_figures.py -----------------------
conf = cases[cases.classification == "confirmed_case"].copy()
if "hospital_admission" not in conf:
    conf["hospital_admission"] = pd.NaT
for c in ["sample_date", "result_date", "hospital_admission"]:
    conf[c] = pd.to_datetime(conf[c])
conf["src_reg"] = conf.person_id.map(src.set_index("source_case_person_id").first_reg)
conf["first_fu"] = conf.person_id.map(pr_fu.groupby("source_case_person_id").first_fu.min())
conf["src_last_contact"] = conf.person_id.map(pr_fu.groupby("source_case_person_id").last_contact.max())

# (id, label, column, valid range, source cases only?)
STEPS = [
    ("notified", "Notified", "notification", (0, 60), False),
    ("hospitalised", "Hospitalised", "hospital_admission", (0, 60), False),
    ("sample", "Sample taken", "sample_date", (0, 60), False),
    ("lab_result", "Lab result", "result_date", (0, 60), False),
    ("last_contact", "Last contact with any contact", "src_last_contact", (-60, 60), True),
    ("first_followed_up", "First contact followed up", "first_fu", (-60, 60), True),
    ("contacts_registered", "Contacts registered on database", "src_reg", (-60, 60), True),
]
if conf.hospital_admission.notna().sum() == 0:
    STEPS = [s for s in STEPS if s[0] != "hospitalised"]


def delays(df, col, lim):
    d = (df[col] - df.onset).dt.days
    return d[d.between(*lim)]


# --- Fig 2A ------------------------------------------------------------------
rows = []
early = conf[conf.onset <= ONSET_END]
for sid, label, col, lim, src_only in STEPS:
    d = delays(early, col, lim)
    if not len(d):
        continue
    rows.append({"step": sid, "label": label, "n": int(len(d)), "mean": round(d.mean(), 2),
                 "median": d.median(), "q1": d.quantile(.25), "q3": d.quantile(.75),
                 "min_days": lim[0], "max_days": lim[1], "source_cases_only": src_only})
pd.DataFrame(rows).to_csv(os.path.join(T, "dashboard_patient_journey.csv"), index=False)

# --- Fig 2B ------------------------------------------------------------------
conf["wk_onset"] = conf.onset.dt.to_period("W-SUN").dt.start_time
WEEKLY = [("notified", "notification", (0, 60)),
          ("lab_result", "result_date", (0, 60)),
          ("contacts_registered", "src_reg", (-60, 60))]
if any(s[0] == "hospitalised" for s in STEPS):
    WEEKLY.insert(1, ("hospitalised", "hospital_admission", (0, 60)))
out = []
for sid, col, lim in WEEKLY:
    dd = (conf[col] - conf.onset).dt.days
    tmp = pd.DataFrame({"wk": conf.wk_onset, "d": dd})[dd.between(*lim)]
    tmp = tmp[(tmp.wk >= WK_START) & (tmp.wk <= WK_END)]
    g = tmp.groupby("wk").d.agg(n="size", median="median",
                                q1=lambda x: x.quantile(.25), q3=lambda x: x.quantile(.75))
    g = g[g.n >= MIN_WEEK_N].reset_index()
    g.insert(0, "step", sid)
    out.append(g)
weekly = pd.concat(out, ignore_index=True) if out else pd.DataFrame(
    columns=["step", "wk", "n", "median", "q1", "q3"])
weekly["wk"] = pd.to_datetime(weekly["wk"]).dt.strftime("%Y-%m-%d")
weekly.to_csv(os.path.join(T, "dashboard_delays_weekly.csv"), index=False)

# --- Fig 3D "All zones" ------------------------------------------------------
fu = pd.DataFrame([{"month": m, "k": v[0], "n": v[1]} for m, v in sorted(R["fu21_by_month"].items())])
fu.to_csv(os.path.join(T, "dashboard_fu21_by_month.csv"), index=False)

# --- meta / headline numbers ------------------------------------------------------
meta = {
    "data_cut": CUT.strftime("%Y-%m-%d"),
    "onset_end": ONSET_END.strftime("%Y-%m-%d"),
    "onset_week_start": WK_START.strftime("%Y-%m-%d"),
    "onset_week_end": WK_END.strftime("%Y-%m-%d"),
    "last_full_week": LAST_FULL_WEEK.strftime("%Y-%m-%d"),
    "min_cases_per_week_lines": 20,
    "min_cases_per_week_delays": MIN_WEEK_N,
    "n_cases_contact_any_time": int(R.get("n_cases_contact_any_time", 0)),
    "fu21_contacts": int(fu.n.sum()) if len(fu) else 0,
    "fu21_complete": int(fu.k.sum()) if len(fu) else 0,
}
with open(os.path.join(T, "dashboard_meta.json"), "w") as fh:
    json.dump(meta, fh, indent=2)

print(f"dashboard tables written to {T} (cut {meta['data_cut']}, onset to {meta['onset_end']}, "
      f"weeks to {meta['onset_week_end']}, last full week {meta['last_full_week']})")
