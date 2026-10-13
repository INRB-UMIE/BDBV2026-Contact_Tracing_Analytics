"""
Step 2: all statistics for the contact-tracing report (data cut 9 Oct 2026).
Reads derived/ from 01_harmonise.py. Writes derived/results.json + tables/*.csv
"""
import os, json
import numpy as np
import pandas as pd

from ctr_paths import D, T, REPORT_DATE

DATA_DATE = pd.Timestamp(REPORT_DATE)
FU_DAYS = 21
MAX_DELAY = 60  # from Processing_Code nowcasting config

dcols = ["onset", "notification", "investigation", "sample_date", "result_date", "reporting", "case_date", "hospital_admission"]
P = pd.read_csv(os.path.join(D, "persons.csv"), parse_dates=dcols, low_memory=False).set_index("person_id")
pr = pd.read_csv(os.path.join(D, "pairs.csv"), low_memory=False,
                 parse_dates=["registration", "last_contact", "first_fu", "last_fu"] + ["src_" + c for c in dcols] + ["con_" + c for c in dcols])
fu = pd.read_csv(os.path.join(D, "followups.csv"), low_memory=False, parse_dates=["followup_date", "registration_date", "last_contact_with_source_date"])
R = {}


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan, np.nan)
    p = k / n
    den = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return (p, max(0, c - h), min(1, c + h))


def dsum(x):
    x = pd.Series(x).dropna()
    if len(x) == 0:
        return dict(n=0, mean=np.nan, median=np.nan, q1=np.nan, q3=np.nan)
    return dict(n=int(len(x)), mean=round(float(x.mean()), 1), median=float(x.median()),
                q1=float(x.quantile(.25)), q3=float(x.quantile(.75)))


def week(s):
    return s.dt.to_period("W-SUN").dt.start_time


# ------------------------------------------------------------------ Section 2
cases = P[P.is_case].copy()
src_ids = set(pr.source_case_person_id)
con_ids = set(pr.contact_person_id)
cases["is_source"] = cases.index.isin(src_ids)
cases["is_contact"] = cases.index.isin(con_ids)
src = pr.groupby("source_case_person_id").agg(
    n_contacts=("contact_person_id", "size"), first_reg=("registration", "min"),
    province=("src_province", "first"), health_zone=("src_health_zone", "first"),
    classification=("src_classification", "first"), notification=("src_notification", "first"),
    onset=("src_onset", "first"), in_ll=("src_in_ll", "first"))
src["classification"] = src.classification.fillna("not in linelist")

R["n_cases"] = int(len(cases))
R["n_confirmed"] = int((cases.classification == "confirmed_case").sum())
R["n_probable"] = int((cases.classification == "probable_case").sum())
R["n_case_deaths"] = int(cases.died.sum())
R["n_source"] = int(len(src))
R["n_source_confirmed"] = int(src.classification.isin(["confirmed_case", "probable_case"]).sum())
R["source_class"] = src.classification.value_counts().to_dict()
R["n_contacts"] = int(len(con_ids))
R["n_pairs"] = int(len(pr))
R["n_contacts_multi_source"] = int((pr.groupby("contact_person_id").size() > 1).sum())
R["pct_cases_source"] = wilson(cases.is_source.sum(), len(cases))
R["pct_cases_contact"] = wilson(cases.is_contact.sum(), len(cases))
R["contacts_per_source"] = dsum(src.n_contacts)
R["sources_1_contact"] = wilson((src.n_contacts == 1).sum(), len(src))
R["sources_ge50"] = int((src.n_contacts >= 50).sum())
top10 = src.n_contacts.sort_values(ascending=False)
R["share_contacts_top10pct_sources"] = float(top10.iloc[: int(np.ceil(len(src) * .1))].sum() / top10.sum())

for col, key in [("relationship_to_case", "rel"), ("case_circumstances", "setting"), ("contact_type", "exposure")]:
    vc = pr[col].value_counts()
    R[key] = {k: [int(v), round(100 * v / len(pr), 1)] for k, v in vc.items()}

# national/provincial table
def prov_table(group_case, group_src, group_pair):
    rows = []
    for prov in sorted(set(cases[group_case].dropna())):
        c = cases[cases[group_case] == prov]
        s = src[src[group_src] == prov]
        q = pr[pr[group_pair] == prov]
        qe = q[q.eligible] if "eligible" in q else q
        rows.append(dict(area=prov, cases=len(c), deaths=int(c.died.sum()),
                         pct_cases_source=100 * c.is_source.mean(), pct_cases_prev_contact=100 * c.prev_contact.mean(),
                         source_cases=len(s), contacts=q.contact_person_id.nunique(),
                         med_contacts=s.n_contacts.median() if len(s) else np.nan,
                         pct_fu_complete=(100 * q.loc[q.fu_ff_eligible.astype(bool), "fu_ff_complete"].astype(bool).mean()
                                          if q.fu_ff_eligible.astype(bool).any() else np.nan),
                         fu_n=int(q.fu_ff_eligible.astype(bool).sum()),
                         sar_k=int(qe.secondary_case.sum()), sar_n=len(qe)))
    return pd.DataFrame(rows)

# ------------------------------------------------------------------ Section 4 (needed for table)
reg_con = pr.groupby("contact_person_id").registration.min()
cases["contact_reg"] = reg_con.reindex(cases.index)
cases["prev_contact"] = cases.is_contact & (cases.contact_reg <= cases.notification)
R["n_cases_prev_contact"] = int(cases.prev_contact.sum())
R["pct_cases_prev_contact"] = wilson(cases.prev_contact.sum(), len(cases))
R["n_cases_contact_any_time"] = int(cases.is_contact.sum())
R["n_cases_contact_registered_after_notif"] = int((cases.is_contact & ~cases.prev_contact).sum())

# follow-up completeness for pairs whose 21-day window has finished
pr["window_end"] = pr.last_contact + pd.Timedelta(days=FU_DAYS)
pr["window_closed"] = pr.window_end <= DATA_DATE
pr["fu_complete"] = pr.n_fu_with_result / FU_DAYS
pr.loc[~pr.window_closed, "fu_complete"] = np.nan
pr["fu_complete"] = pr.fu_complete.clip(upper=1)
pc = pr[pr.window_closed]
R["fu_pairs_window_closed"] = int(len(pc))
R["fu_days_recorded"] = dsum(pc.n_fu_days)
R["fu_days_with_result"] = dsum(pc.n_fu_with_result)
R["fu_pct_ge1"] = wilson((pc.n_fu_with_result >= 1).sum(), len(pc))
R["fu_pct_ge15"] = wilson((pc.n_fu_with_result >= 15).sum(), len(pc))
R["fu_pct_zero"] = wilson((pc.n_fu_with_result == 0).sum(), len(pc))

# result completeness of follow-up rows, by week of visit
fu["wk"] = week(fu.followup_date)
fuw = fu.dropna(subset=["wk"]).groupby("wk").agg(visits=("followup_result", "size"),
                                                  pct_result=("followup_result", lambda s: 100 * s.notna().mean()))
fuw.to_csv(os.path.join(T, "followup_visits_weekly.csv"))
R["result_missing_pre_sep14"] = float(100 - fu[fu.followup_date < "2026-09-14"].followup_result.notna().mean() * 100)
R["result_missing_post_sep14"] = float(100 - fu[fu.followup_date >= "2026-09-14"].followup_result.notna().mean() * 100)

# source notification -> first contact registered
src["notif_to_reg"] = (src.first_reg - src.notification).dt.days
src["onset_to_reg"] = (src.first_reg - src.onset).dt.days
ok = src.notif_to_reg.between(-MAX_DELAY, MAX_DELAY)
R["notif_to_first_contact"] = dsum(src.loc[ok, "notif_to_reg"])
R["notif_to_first_contact_neg"] = int((src.loc[ok, "notif_to_reg"] < 0).sum())
R["notif_to_first_contact_le2"] = wilson((src.loc[ok, "notif_to_reg"] <= 2).sum(), ok.sum())
src["reg_month"] = src.first_reg.dt.to_period("M").astype(str)
R["notif_to_first_contact_by_month"] = {m: dsum(g.loc[g.notif_to_reg.between(-MAX_DELAY, MAX_DELAY), "notif_to_reg"]) for m, g in src.groupby("reg_month")}
R["notif_to_first_contact_by_prov"] = {m: dsum(g.loc[g.notif_to_reg.between(-MAX_DELAY, MAX_DELAY), "notif_to_reg"]) for m, g in src.groupby("province")}
R["contacts_per_source_by_prov"] = {m: dsum(g.n_contacts) for m, g in src.groupby("province")}
R["contacts_per_source_by_month"] = {m: dsum(g.n_contacts) for m, g in src.groupby("reg_month")}

# weekly series
cases["wk_notif"] = week(cases.notification.fillna(cases.case_date))
src["wk"] = week(src.first_reg)
first_reg_con = pr.groupby("contact_person_id").registration.min()
wk = pd.DataFrame({
    "new_cases": cases.groupby("wk_notif").size(),
    "new_cases_prev_contact": cases[cases.prev_contact].groupby("wk_notif").size(),
    "new_cases_contact_after": cases[cases.is_contact & ~cases.prev_contact].groupby("wk_notif").size(),
    "new_cases_became_source": cases[cases.is_source].groupby("wk_notif").size(),
    "new_source_cases": src.groupby("wk").size(),
    "new_contacts": week(first_reg_con).value_counts(),
}).fillna(0).sort_index()
wk = wk[wk.index >= "2026-04-27"]
wk["pct_prev_contact"] = 100 * wk.new_cases_prev_contact / wk.new_cases.replace(0, np.nan)
wk["pct_became_source"] = 100 * wk.new_cases_became_source / wk.new_cases.replace(0, np.nan)
wk.to_csv(os.path.join(T, "weekly_national.csv"))

# per health zone weekly (top zones)
top_hz = cases.health_zone.value_counts().head(6).index.tolist()
R["top_hz"] = top_hz
pr["wk_reg"] = week(pr.registration)
hzw = []
for hz in top_hz:
    c = cases[cases.health_zone == hz]
    q = pr[pr.src_health_zone == hz].sort_values("registration").drop_duplicates("contact_person_id")
    s = src[src.health_zone == hz]
    d = pd.DataFrame({"new_cases": c.groupby("wk_notif").size(),
                      "new_cases_became_source": c[c.is_source].groupby("wk_notif").size(),
                      "new_cases_prev_contact": c[c.prev_contact].groupby("wk_notif").size(),
                      "new_contacts": q.groupby("wk_reg").size(),
                      "new_source_cases": s.groupby("wk").size()}).fillna(0)
    d["health_zone"] = hz
    hzw.append(d)
hzw = pd.concat(hzw).rename_axis("week").reset_index()
hzw = hzw[hzw.week >= "2026-04-27"]
hzw.to_csv(os.path.join(T, "weekly_top_hz.csv"), index=False)

# ------------------------------------------------------------------ Section 3
c = cases[cases.classification == "confirmed_case"].copy()
c["src_reg"] = src.first_reg.reindex(c.index)
delays = {
    "Onset → notification": ("onset", "notification"),
    "Notification → sample": ("notification", "sample_date"),
    "Sample → lab result": ("sample_date", "result_date"),
    "Onset → sample": ("onset", "sample_date"),
    "Onset → lab result": ("onset", "result_date"),
    "Notification → first contacts listed": ("notification", "src_reg"),
    "Onset → first contacts listed": ("onset", "src_reg"),
    "Onset → hospital admission": ("onset", "hospital_admission"),
}
drows, excl = [], []
c["month"] = c.case_date.dt.to_period("M").astype(str).where(c.case_date.notna())  # NaN (dropped by groupby) on every pandas version
long = []
for name, (a, b) in delays.items():
    d = (c[b] - c[a]).dt.days
    valid = d.between(0, MAX_DELAY) if "contacts" not in name else d.between(-MAX_DELAY, MAX_DELAY)
    excl.append(dict(delay=name, n_both_dates=int(d.notna().sum()), n_excluded=int((d.notna() & ~valid).sum()),
                     n_negative=int((d < 0).sum()), n_gt60=int((d > MAX_DELAY).sum())))
    s = dsum(d[valid]); s["delay"] = name; s["level"] = "National"; s["group"] = "All"
    drows.append(s)
    for g, gg in c.groupby("province"):
        s = dsum(d[valid & (c.province == g)]); s.update(delay=name, level="Province", group=g); drows.append(s)
    for g, gg in c.groupby("month"):
        s = dsum(d[valid & (c.month == g)]); s.update(delay=name, level="Month", group=g); drows.append(s)
    long.append(pd.DataFrame({"delay": name, "days": d[valid], "month": c.month[valid], "province": c.province[valid]}))
dtab = pd.DataFrame(drows)[["delay", "level", "group", "n", "mean", "median", "q1", "q3"]]
dtab.to_csv(os.path.join(T, "delays.csv"), index=False)
pd.DataFrame(excl).to_csv(os.path.join(T, "delay_exclusions.csv"), index=False)
pd.concat(long).to_csv(os.path.join(D, "delays_long.csv"), index=False)
R["delays_nat"] = {r["delay"]: {k: r[k] for k in ["n", "mean", "median", "q1", "q3"]} for r in drows if r["level"] == "National"}
R["delay_exclusions"] = excl
R["onset_to_notif_by_month"] = {r["group"]: r["median"] for r in drows if r["level"] == "Month" and r["delay"] == "Onset → notification"}

# ------------------------------------------------------------------ Section 5
# eligible pairs for SAR: source is linelist confirmed/probable case, follow-up window closed
# Follow-up window = 21 days from FIRST FOLLOW-UP (irrespective of exposure date).
# SAR denominator: contacts of confirmed/probable sources whose first follow-up was on or
# before 18 Sep 2026 (9 Oct data cut - 21 days), i.e. whose 21-day follow-up had ended.
# Contacts with no follow-up rows start at their registration date.
FU_WINDOW_START_MAX = DATA_DATE - pd.Timedelta(days=21)
pr["fu_window_start"] = pr.first_fu.fillna(pr.registration)
pr["eligible_lastexp"] = pr.src_is_case.astype("boolean").fillna(False).astype(bool) & pr.window_closed  # previous definition
pr["eligible"] = pr.src_is_case.astype("boolean").fillna(False).astype(bool) & (pr.fu_window_start <= FU_WINDOW_START_MAX)
R["sar_prev_def_lastexp"] = wilson(pr.loc[pr.eligible_lastexp, "secondary_case"].sum(), int(pr.eligible_lastexp.sum()))
E = pr[pr.eligible].copy()
k, n = E.secondary_case.sum(), len(E)
R["sar_eligible_pairs"] = int(n)
R["sar_secondary"] = int(k)
R["sar"] = wilson(k, n)
R["sar_strict"] = wilson(E.secondary_strict.sum(), n)            # sensitivity: excl. CT 'case_validated'
R["sar_with_cv"] = R["sar"]                                        # main includes CT 'case_validated'
R["sar_upper"] = wilson(E.secondary_upper.sum(), n)                # sensitivity: + CT 'became suspected case'
R["sar_sens_validated"] = R["sar_strict"]                          # (04_report.py: now = strict sensitivity)
R["sar_ll_only"] = wilson(E.sec_ll.sum(), n)
R["sar_all_pairs"] = wilson(pr.secondary_case.sum(), len(pr))
# per source case: proportion of sources with >=1 secondary case among contacts
sE = E.groupby("source_case_person_id").secondary_case.any()
R["sources_with_secondary"] = wilson(sE.sum(), len(sE))

E["reg_month"] = E.registration.dt.to_period("M").astype(str)
E["source_died"] = np.where(E.src_died.astype("boolean").fillna(False), "Source died", "Source survived/unknown")
E["src_age_grp"] = pd.cut(E.src_age, [-1, 14, 29, 44, 59, 200], labels=["0-14", "15-29", "30-44", "45-59", "60+"]).astype(str)
E["n_contacts_src"] = E.groupby("source_case_person_id").contact_person_id.transform("size")
E["src_size_grp"] = pd.cut(E.n_contacts_src, [0, 5, 15, 50, 10000], labels=["1-5", "6-15", "16-50", ">50"]).astype(str)

factors = {"contact_type": "Exposure type", "case_circumstances": "Setting", "relationship_to_case": "Relationship",
           "src_province": "Province (source)", "reg_month": "Month listed", "source_died": "Source outcome",
           "src_size_grp": "Contacts listed by source"}
def pick_ref(series, y):
    """Reference level: 'unknown' where it exists and has >=1 secondary case (so ratios are
    estimable); otherwise the most common level."""
    v = series.fillna("unknown")
    if (v == "unknown").any() and y[v == "unknown"].sum() > 0:
        return "unknown"
    return v.value_counts().index[0]


def risk_table(outcome):
    rf = []
    for col, lab in factors.items():
        vc = E[col].fillna("unknown")
        ref = pick_ref(E[col], E[outcome])
        kr, nr = E.loc[vc == ref, outcome].sum(), (vc == ref).sum()
        for lev in vc.value_counts().index:
            m = vc == lev
            kk, nn = E.loc[m, outcome].sum(), m.sum()
            p, lo, hi = wilson(kk, nn)
            if lev == ref:
                rr, rl, rh = 1.0, np.nan, np.nan
            elif kk == 0 or kr == 0:
                rr, rl, rh = np.nan, np.nan, np.nan
            else:
                rr = (kk / nn) / (kr / nr)
                se = np.sqrt(1 / kk - 1 / nn + 1 / kr - 1 / nr)
                rl, rh = rr * np.exp(-1.96 * se), rr * np.exp(1.96 * se)
            rf.append(dict(factor=lab, level=lev, n=int(nn), k=int(kk), sar=p, lo=lo, hi=hi, rr=rr, rr_lo=rl, rr_hi=rh, ref=lev == ref))
    rf = pd.DataFrame(rf)

    return rf


rf = risk_table("secondary_case")
rf.to_csv(os.path.join(T, "sar_risk_factors.csv"), index=False)                     # main (incl. CT case_validated)
risk_table("secondary_strict").to_csv(os.path.join(T, "sar_risk_factors_strict.csv"), index=False)  # sensitivity: without CV


# multivariable logistic regression (IRLS), cluster-naive SEs
def logit(df, y, cols):
    X = pd.get_dummies(df[cols].fillna("unknown"), drop_first=False).astype(float)
    # drop reference = most common level of each factor
    drop = []
    for col in cols:
        ref = pick_ref(df[col], df[y])
        drop.append(f"{col}_{ref}")
    X = X.drop(columns=drop)
    # drop sparse columns (no events) to avoid separation
    keep = [cname for cname in X.columns if df.loc[X[cname] == 1, y].sum() >= 1]
    X = X[keep]
    X.insert(0, "const", 1.0)
    yv = df[y].astype(float).values
    Xv = X.values
    b = np.zeros(Xv.shape[1])
    for _ in range(50):
        eta = Xv @ b
        mu = 1 / (1 + np.exp(-eta))
        W = mu * (1 - mu)
        H = Xv.T @ (Xv * W[:, None]) + 1e-8 * np.eye(len(b))
        step = np.linalg.solve(H, Xv.T @ (yv - mu))
        b += step
        if np.max(np.abs(step)) < 1e-8:
            break
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    out = pd.DataFrame({"term": X.columns, "OR": np.exp(b), "lo": np.exp(b - 1.96 * se), "hi": np.exp(b + 1.96 * se)})
    return out[out.term != "const"]

mv = logit(E, "secondary_case", ["contact_type", "case_circumstances", "relationship_to_case", "src_province", "source_died", "reg_month"])
mv.to_csv(os.path.join(T, "sar_multivariable_or.csv"), index=False)

# serial interval (both onsets, both cases, not reciprocal)
recip = set(zip(pr.contact_person_id, pr.source_case_person_id))
si = pr[pr.src_is_case.astype("boolean").fillna(False) & pr.sec_ll].copy()
si["recip"] = [(a, b) in recip for a, b in zip(si.source_case_person_id, si.contact_person_id)]
si = si[~si.recip]
si["si"] = (si.con_onset - si.src_onset).dt.days
R["si_pairs_with_dates"] = int(si.si.notna().sum())
siv = si.si[si.si.between(-30, 60)]
R["serial_interval"] = dsum(siv)
R["si_negative"] = int((siv < 0).sum())
R["si_excluded_extreme"] = int(si.si.notna().sum() - len(siv))
si[["source_case_person_id", "contact_person_id", "si", "src_health_zone"]].to_csv(os.path.join(D, "serial_interval_pairs.csv"), index=False)

# incubation lower bound: onset - last exposure, linelist secondary cases
# same infector rules as the serial interval: source confirmed/probable in linelist,
# infectee confirmed/probable in linelist, pairs recorded in both directions excluded
inc = pr[pr.src_is_case.astype("boolean").fillna(False) & pr.sec_ll].copy()
inc = inc[[(a, b) not in recip for a, b in zip(inc.source_case_person_id, inc.contact_person_id)]]
inc["inc"] = (inc.con_onset - inc.last_contact).dt.days
R["inc_with_dates"] = int(inc.inc.notna().sum())
incv = inc.inc[inc.inc.between(1, 42)]
R["incubation"] = dsum(incv)
R["inc_le0"] = int((inc.inc <= 0).sum())
R["inc_gt42"] = int((inc.inc > 42).sum())
inc[["contact_person_id", "inc"]].to_csv(os.path.join(D, "incubation.csv"), index=False)

# ---- inputs for 05_fit_distributions_epidist.R (one row per pair / secondary case, dates only)
EPI = os.path.join(D, "epidist_inputs"); os.makedirs(EPI, exist_ok=True)
si.assign(setting=si.case_circumstances)[[
    "source_case_person_id", "contact_person_id", "src_onset", "con_onset", "si", "setting", "src_province", "src_health_zone"]].rename(
    columns={"src_onset": "infector_onset", "con_onset": "infectee_onset"}).dropna(subset=["infector_onset", "infectee_onset"]).to_csv(
    os.path.join(EPI, "serial_interval_pairs.csv"), index=False, date_format="%Y-%m-%d")
inc.assign(setting=inc.case_circumstances)[[
    "source_case_person_id", "contact_person_id", "src_onset", "last_contact", "registration", "con_onset", "inc", "setting", "src_province"]].rename(
    columns={"con_onset": "onset", "last_contact": "last_exposure", "src_onset": "source_onset"}).dropna(subset=["last_exposure", "onset"]).to_csv(
    os.path.join(EPI, "incubation_cases.csv"), index=False, date_format="%Y-%m-%d")

# unlocated / outside
R["src_unlocated"] = int(src.province.isna().sum())

# monthly SAR
R["sar_by_month"] = {r.level: [r.k, r.n, r.sar, r.lo, r.hi] for r in rf[rf.factor == "Month listed"].itertuples()}

# ------------------------------------------------------------------ Follow-up completeness (21 days post last exposure)
# Complete = a follow-up RESULT recorded on/after day 21 after last contact with the source.
# Positive contacts (secondary cases) are complete if followed (a result recorded) up to the date
# they were detected: earliest of CT 'case_confirmed' result date and linelist notification date.
KEYS = ["source_case_person_id", "contact_person_id"]
res = fu.dropna(subset=["followup_result", "followup_date"])
last_res = res.groupby(KEYS).followup_date.max().rename("last_result_date")
conf_res = res[res.followup_result.eq("case_confirmed")].groupby(KEYS).followup_date.min().rename("ct_confirmed_date")
pr = pr.drop(columns=[c for c in ["last_result_date", "ct_confirmed_date"] if c in pr]).join(last_res, on=KEYS).join(conf_res, on=KEYS)
pr["fu_last_day"] = (pr.last_result_date - pr.last_contact).dt.days
pr["detect_date"] = pr[["ct_confirmed_date", "con_notification"]].min(axis=1).where(pr.secondary_case)
pr["fu21_complete"] = np.where(
    pr.secondary_case,
    (pr.fu_last_day >= 21) | (pr.last_result_date >= pr.detect_date - pd.Timedelta(days=1)),
    pr.fu_last_day >= 21)
pr["fu21_complete"] = pr["fu21_complete"].astype(object)  # True/False, NaN = not eligible (newer pandas will not put NaN in a bool column)
pr.loc[~pr.window_closed, "fu21_complete"] = np.nan
pc = pr[pr.window_closed]
R["fu21_complete"] = wilson(pc.fu21_complete.astype(bool).sum(), len(pc))
R["fu21_complete_day20"] = float(((pc.fu_last_day >= 20) | (pc.secondary_case & (pc.last_result_date >= pc.detect_date - pd.Timedelta(days=1)))).mean())
R["fu21_no_result"] = int(pc.last_result_date.isna().sum())
# Adjusted version including open windows: required follow-up day = min(21, days observable to CT cut).
# CT cut = 4 Oct 2026 (last CT registration date; result entry thins out after this).
CT_CUT = pd.Timestamp("2026-10-04")
pr["fu_target_day"] = np.minimum(21, (CT_CUT - pr.last_contact).dt.days)
pr["fu_adj_eligible"] = pr.last_contact.notna() & (pr.fu_target_day >= 2)
pr["fu_adj_complete"] = np.where(
    pr.secondary_case,
    (pr.fu_last_day >= pr.fu_target_day) | (pr.last_result_date >= pr.detect_date - pd.Timedelta(days=1)),
    pr.fu_last_day >= pr.fu_target_day)
pr["fu_adj_complete"] = pr["fu_adj_complete"].astype(object)  # True/False, NaN = not eligible (newer pandas will not put NaN in a bool column)
pr.loc[~pr.fu_adj_eligible, "fu_adj_complete"] = np.nan
pa = pr[pr.fu_adj_eligible].assign(lc_month=lambda d: d.last_contact.dt.to_period("M").astype(str))
pa = pa.assign(fu_adj_complete=pa.fu_adj_complete.astype(bool))
R["fu_adj_complete"] = wilson(pa.fu_adj_complete.sum(), len(pa))
R["fu_adj_n_open"] = int((~pa.window_closed).sum())
t21 = pa.groupby(["src_province", "src_health_zone", "lc_month"]).fu_adj_complete.agg(n="size", k="sum").reset_index()
t21.to_csv(os.path.join(T, "fu21_complete_hz_month_lastexposure.csv"), index=False)   # previous definition (kept for reference)
R["fu_lastexp_complete"] = R["fu_adj_complete"]

# ---- CURRENT DEFINITION (13 Oct): complete = result recorded up to day 21 OF FOLLOW-UP,
# i.e. on/after first follow-up date + 20 days (first follow-up row = day 1), or up to the
# CT cut (4 Oct) if sooner. Start = first follow-up row (any row, with or without result);
# contacts with no follow-up rows start at registration (and are incomplete).
# Secondary cases: complete if followed up to detection (as before).
# Only contacts whose day 21 of follow-up had passed by the data cut are included
# (first follow-up on or before 18 Sep 2026 = 9 Oct - 21 days), so no shortened targets.
FU_START_MAX = DATA_DATE - pd.Timedelta(days=21)
pr["fu_start"] = pr.first_fu.fillna(pr.registration)
pr["fu_ff_target"] = 20
pr["fu_ff_eligible"] = pr.fu_start.notna() & (pr.fu_start <= FU_START_MAX)
pr["fu_ff_complete"] = (((pr.last_result_date - pr.fu_start).dt.days >= pr.fu_ff_target)
                        | (pr.secondary_case & (pr.last_result_date >= pr.detect_date - pd.Timedelta(days=1))))
pr["fu_ff_complete"] = pr["fu_ff_complete"].astype(object)  # True/False, NaN = not eligible (newer pandas will not put NaN in a bool column)
pr.loc[~pr.fu_ff_eligible, "fu_ff_complete"] = np.nan
pf = pr[pr.fu_ff_eligible].assign(fu_month=lambda d: d.fu_start.dt.to_period("M").astype(str),
                                  fu_ff_complete=lambda d: d.fu_ff_complete.astype(bool))
R["fu_adj_complete"] = wilson(pf.fu_ff_complete.sum(), len(pf))
R["fu_adj_n_open"] = 0
R["fu_ff_start_max"] = str(FU_START_MAX.date())
t21 = pf.groupby(["src_province", "src_health_zone", "fu_month"]).fu_ff_complete.agg(n="size", k="sum").reset_index().rename(columns={"fu_month": "lc_month"})
t21.to_csv(os.path.join(T, "fu21_complete_hz_month.csv"), index=False)
R["fu21_by_month"] = {m: [int(g.fu_ff_complete.sum()), int(len(g))] for m, g in pf.groupby("fu_month")}
R["fu21_by_prov"] = {m: [int(g.fu_ff_complete.sum()), int(len(g))] for m, g in pf.groupby("src_province")}

# (moved after follow-up completeness so pct_fu_complete = % fully followed up, 21 days from first follow-up)
# ------------------------------------------------------------------ provincial / HZ tables
# province of cases = linelist; of sources/pairs = source province
pt = prov_table("province", "province", "src_province")
nat = dict(area="National", cases=len(cases), deaths=int(cases.died.sum()),
           pct_cases_source=100 * cases.is_source.mean(), pct_cases_prev_contact=100 * cases.prev_contact.mean(),
           source_cases=len(src), contacts=pr.contact_person_id.nunique(), med_contacts=src.n_contacts.median(),
           pct_fu_complete=100 * pf.fu_ff_complete.mean(), fu_n=len(pf), sar_k=int(E.secondary_case.sum()), sar_n=len(E))
pt = pd.concat([pt, pd.DataFrame([nat])], ignore_index=True)
# include sources from provinces without cases
pt.to_csv(os.path.join(T, "province_table.csv"), index=False)

hz = prov_table("health_zone", "health_zone", "src_health_zone")
hz.to_csv(os.path.join(T, "health_zone_table.csv"), index=False)

cases.to_csv(os.path.join(D, "cases_annotated.csv"))
src.to_csv(os.path.join(D, "sources.csv"))
pr.to_csv(os.path.join(D, "pairs_annotated.csv"), index=False)


def conv(o):
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating,)): return float(o)
    if isinstance(o, tuple): return list(o)
    return str(o)

json.dump(R, open(os.path.join(D, "results.json"), "w"), indent=1, default=conv)
print(json.dumps(R, indent=1, default=conv)[:6000])
print(pt.round(1).to_string())
print(rf.round(3).to_string())
print(mv.round(2).to_string())
