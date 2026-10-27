"""
Step 1: harmonise the linelist + contact tracing (CT) data to
person level for the data cut CT_REPORT_DATE, logging every discrepancy and the decision taken.

Outputs (in ./derived/):
  persons.csv          one row per linelist person_id (harmonised)
  pairs.csv            one row per (source person, contact person) pair
  followups.csv        cleaned CT follow-up rows (one per pair x date)
  decisions_log.csv    counts of every harmonisation decision (for the SI)
"""
import os, sys
import numpy as np
import pandas as pd

from ctr_paths import DATA_DIR as DATA, D as OUT, REPORT_DATE, CUT_LABEL

DATA_DATE = pd.Timestamp(REPORT_DATE)
EPI_START = pd.Timestamp("2026-04-01")  # from Processing_Code qc config
log = []


def note(step, item, n, decision):
    log.append(dict(step=step, item=item, n=int(n), decision=decision))


def clean_date(s, name, step):
    d = pd.to_datetime(s, errors="coerce")
    bad = d.notna() & ((d < EPI_START) | (d > DATA_DATE))
    note(step, f"{name}: implausible date (<{EPI_START.date()} or >{DATA_DATE.date()})",
         bad.sum(), "set to missing")
    return d.mask(bad)


# =============================== LINELIST ====================================
ll = pd.read_csv(os.path.join(DATA, "dhis2_processed_linelist_ctsafe.csv"), low_memory=False)
note("linelist", "rows in linelist export", len(ll), "all alerts (cases, non-cases, unclassified)")
note("linelist", "distinct person_id", ll.person_id.nunique(), "unit of analysis = person_id")

# health zone fix: 'Bili' is ambiguous in shapefile; all rows are Bas-Uele
ll.loc[(ll.health_zone == "Bili") & (ll.province == "Bas-Uele"), "health_zone"] = "Bili (Bas-Uele)"
note("linelist", "health_zone 'Bili' (Bas-Uele)", (ll.health_zone == "Bili (Bas-Uele)").sum(),
     "renamed 'Bili (Bas-Uele)' to match shapefile")

date_cols = ["date_of_symptom_onset", "date_of_notification", "investigation_datetime",
             "date_of_sample_collection", "lab_analysis_date", "reporting_date"]
# Hospital admission: expected in exports from 10 Oct 2026 as 'hospital_admission_date'
# (older exports to 14 Jul had 'date_of_hospitalisation_start'). Absent -> all missing.
HOSP_COL = next((c for c in ["hospital_admission_date", "date_of_hospitalisation_start"] if c in ll.columns), None)
if HOSP_COL is None:
    ll["hospital_admission_date"] = pd.NaT
    note("linelist", "hospital admission date column not in this export", 0, "hospital admission delays left empty")
else:
    ll["hospital_admission_date"] = ll[HOSP_COL]
    date_cols.append("hospital_admission_date")
for c in date_cols:
    ll[c] = clean_date(ll[c], c, "linelist")

CLASS_RANK = {"confirmed_case": 4, "probable_case": 3, "suspected_case": 2, "not_a_case": 1}
ll["class_rank"] = ll.final_mve_case_classification.map(CLASS_RANK).fillna(0)
ll["n_nonmissing"] = ll.notna().sum(axis=1)
ll["died"] = (ll.type_of_alert.eq("death") | ll.sample_collection_status.eq("deceased"))

multi = ll.person_id.duplicated(keep=False)
note("linelist", "persons with >1 linelist row", ll.loc[multi, "person_id"].nunique(),
     "collapsed to one row per person (rules below)")
note("linelist", "multi-row persons including an 'undecided' ID match",
     ll.loc[multi & ll.person_id_status.eq("undecided"), "person_id"].nunique(),
     "kept as one person (person_id taken as given)")

# discrepancy counting on multi-row persons
mm = ll[multi]
def n_conflict(col):
    return int((mm.groupby("person_id")[col].nunique(dropna=True) > 1).sum())

note("linelist", "conflicting final classification",
     int((mm.groupby("person_id").final_mve_case_classification.apply(lambda s: s.fillna('blank').nunique()) > 1).sum()),
     "highest-ranked kept: confirmed > probable > suspected > not_a_case > blank (a positive lab result is treated as definitive)")
for c, rule in [("date_of_symptom_onset", "earliest plausible date kept (first-reported symptoms)"),
                ("date_of_notification", "earliest kept (first time health authorities were notified)"),
                ("date_of_sample_collection", "taken from the primary record (highest classification, then most complete); earliest if primary missing"),
                ("lab_analysis_date", "taken from the primary record; earliest if primary missing"),
                ("sex", "primary record value; missing filled from other rows"),
                ("age", "primary record value; missing filled from other rows"),
                ("health_zone", "primary record value (zone of the confirmed/primary alert)"),
                ("hospital_admission_date", "earliest plausible admission date kept (first admission)"),
                ("type_of_alert", "person counted as died if ANY row is a death alert or sample status 'deceased'")]:
    note("linelist", f"conflicting {c}", n_conflict(c), rule)

ll = ll.sort_values(["person_id", "class_rank", "n_nonmissing"], ascending=[True, False, False])
prim = ll.drop_duplicates("person_id", keep="first").set_index("person_id")
g = ll.groupby("person_id")
persons = pd.DataFrame(index=prim.index)
persons["alert_id"] = prim.alert_id
persons["n_ll_rows"] = g.size()
persons["classification"] = prim.final_mve_case_classification.fillna("blank")
persons["province"] = prim.province
persons["health_zone"] = prim.health_zone
persons["sex"] = prim.sex.fillna(g.sex.first())
persons["age"] = prim.age.fillna(g.age.first())
persons["died"] = g.died.any()
persons["onset"] = g.date_of_symptom_onset.min()
persons["notification"] = g.date_of_notification.min()
persons["investigation"] = g.investigation_datetime.min()
persons["sample_date"] = prim.date_of_sample_collection.fillna(g.date_of_sample_collection.min())
persons["result_date"] = prim.lab_analysis_date.fillna(g.lab_analysis_date.min())
persons["reporting"] = g.reporting_date.min()
persons["hospital_admission"] = pd.to_datetime(g.hospital_admission_date.min())
bad = persons.hospital_admission < persons.onset - pd.Timedelta(days=30)
note("linelist", "hospital admission >30 days before onset", bad.sum(), "admission date set to missing")
persons.loc[bad, "hospital_admission"] = pd.NaT
persons["is_case"] = persons.classification.isin(["confirmed_case", "probable_case"])
note("linelist", "cases (confirmed + probable persons)", persons.is_case.sum(),
     "case definition used throughout; suspected (n=%d) excluded" % (persons.classification == "suspected_case").sum())

# a result date before sample date is implausible
bad = persons.result_date < persons.sample_date
note("linelist", "lab analysis date before sample date", bad.sum(), "lab analysis date set to missing")
persons.loc[bad, "result_date"] = pd.NaT

# Case date for epi curves: onset; fallback notification
persons["case_date"] = persons.onset.fillna(persons.notification)
note("linelist", "cases with no onset date", (persons.is_case & persons.onset.isna()).sum(),
     "date of notification used for epi curve timing")

# =============================== CONTACT TRACING ==============================
ct = pd.read_csv(os.path.join(DATA, "contact_tracing_combined_ctsafe.csv"), low_memory=False)
note("CT", "rows in combined CT file (all exports, incl. aged-out contacts)", len(ct),
     f"combined file used (processed file holds only contacts current on {CUT_LABEL})")

# --- recode raw codes that escaped mapping
recode = {
    "case_circumstances": {"2.Hôpital": "hospital", "1.Foyer": "household"},
    "relationship_to_case": {"Inconnue": "unknown", "Epoux/ Épouse": "spouse"},
    "contact_type": {"1.Contact physique direct": "direct_physical_contact",
                     "MVE-005": "unknown", "1": "unknown", "2": "unknown"},
    "followup_result": {"Non Cas": "not_a_case", "Confirmé": "case_confirmed", "DB": "other_result"},
}
for col, m in recode.items():
    for k, v in m.items():
        n = (ct[col] == k).sum()
        if n:
            note("CT", f"{col} raw value '{k}'", n,
                 f"recoded to '{v}'" + (" (code not in data dictionary)" if v in ("unknown", "other_result") else ""))
    ct[col] = ct[col].replace(m)
for col in ["case_circumstances", "relationship_to_case", "contact_type"]:
    note("CT", f"{col} missing", ct[col].isna().sum(), "set to 'unknown'")
    ct[col] = ct[col].fillna("unknown")

for c in ["registration_date", "last_contact_with_source_date", "followup_date"]:
    ct[c] = clean_date(ct[c], c, "CT")

selfp = ct.source_case_person_id == ct.contact_person_id
note("CT", "rows where source person = contact person (self-pairs)", selfp.sum(), "dropped (ID-matching error)")
ct = ct[~selfp]

dups = ct.duplicated(["source_case_person_id", "contact_person_id", "followup_date", "followup_result"])
note("CT", "duplicate follow-up rows (same pair, date, result; e.g. same contact under 2 IDs)", dups.sum(), "dropped")
ct = ct[~dups]

# reciprocal pairs
pp = set(zip(ct.source_case_person_id, ct.contact_person_id))
recip = {(a, b) for a, b in pp if (b, a) in pp}
note("CT", "pairs recorded in both directions (A->B and B->A)", len(recip) // 2,
     "kept; excluded from serial-interval estimate")

# --- pair level collapse
ctk = ct.copy()
ctk["export_order"] = ctk.ct_export.str.extract(r"(\d{8})")[0].pipe(pd.to_datetime, format="%d%m%Y", errors="coerce")
def mode_latest(df, col):
    """modal value; ties broken by the most recent export"""
    t = df.groupby(["source_case_person_id", "contact_person_id", col]).agg(n=("export_order", "size"), last=("export_order", "max")).reset_index()
    t = t[t[col] != "unknown"].sort_values(["n", "last"], ascending=False) if col != "x" else t
    return t.drop_duplicates(["source_case_person_id", "contact_person_id"]).set_index(["source_case_person_id", "contact_person_id"])[col]

gp = ctk.groupby(["source_case_person_id", "contact_person_id"])
pairs = gp.agg(
    n_rows=("contact_id", "size"),
    n_contact_ids=("contact_id", "nunique"),
    registration=("registration_date", "min"),
    last_contact=("last_contact_with_source_date", "max"),
    n_last_contact=("last_contact_with_source_date", "nunique"),
    n_reg=("registration_date", "nunique"),
    first_fu=("followup_date", "min"),
    last_fu=("followup_date", "max"),
    n_fu_days=("followup_date", "nunique"),
    contact_status=("contact_status", lambda s: "current" if (s == "current").any() else s.iloc[0]),
    source_alert_id=("source_case_alert_id", "first"),
)
fu_done = ctk[ctk.followup_result.notna()].groupby(["source_case_person_id", "contact_person_id"]).followup_date.nunique()
pairs["n_fu_with_result"] = fu_done.reindex(pairs.index).fillna(0).astype(int)

for col in ["contact_type", "relationship_to_case", "case_circumstances"]:
    nun = ctk[ctk[col] != "unknown"].groupby(["source_case_person_id", "contact_person_id"])[col].nunique()
    note("CT", f"pairs with conflicting {col}", (nun > 1).sum(),
         "most frequent non-unknown value kept; ties -> value in most recent export")
    pairs[col] = mode_latest(ctk, col).reindex(pairs.index).fillna("unknown")
note("CT", "pairs with conflicting last-contact date", (pairs.n_last_contact > 1).sum(),
     "latest date kept (follow-up clock runs from last exposure)")
note("CT", "pairs with conflicting registration date", (pairs.n_reg > 1).sum(), "earliest kept")
note("CT", "pairs with >1 contact_id (same person registered twice)", (pairs.n_contact_ids > 1).sum(),
     "merged into one pair via contact_person_id")

# final follow-up result: worst outcome observed (ever became case beats not_a_case)
RES_RANK = {"case_confirmed": 5, "case_validated": 4, "contact_became_suspected_case": 3,
            "other_result": 1, "recycled": 1, "not_a_case": 0}
r = ctk.dropna(subset=["followup_result"]).copy()
r["rk"] = r.followup_result.map(RES_RANK)
nres = r.groupby(["source_case_person_id", "contact_person_id"]).rk.nunique()
worst = r.sort_values("rk", ascending=False).drop_duplicates(["source_case_person_id", "contact_person_id"]).set_index(["source_case_person_id", "contact_person_id"]).followup_result
pairs["ct_worst_result"] = worst.reindex(pairs.index)
note("CT", "pairs whose follow-up results differ across visits", (nres > 1).sum(),
     "most severe result retained (confirmed > validated > suspected > other/recycled > not a case)")

pairs = pairs.reset_index()
# link to linelist
P = persons
pairs = pairs.merge(P.add_prefix("src_"), left_on="source_case_person_id", right_index=True, how="left")
pairs = pairs.merge(P.add_prefix("con_"), left_on="contact_person_id", right_index=True, how="left")
pairs["src_in_ll"] = pairs.src_alert_id.notna()
pairs["con_in_ll"] = pairs.con_alert_id.notna()

# location of pair = source case's health zone; if source not in linelist, infer
# from the alert-id code (RDC-<PROV>-<ZONE>-...) using linelist alert ids
code = ll.assign(code=ll.alert_id.str.extract(r"^RDC-([A-Z]+-[A-Z]+)-")[0]).dropna(subset=["code"])
code_map = code.groupby("code").agg(province=("province", lambda s: s.mode().iat[0]), health_zone=("health_zone", lambda s: s.mode().iat[0]))
pairs["src_code"] = pairs.source_alert_id.str.extract(r"^RDC-([A-Z]+-[A-Z]+)-")[0]
miss = pairs.src_province.isna()
pairs.loc[miss, "src_province"] = pairs.loc[miss, "src_code"].map(code_map.province)
pairs.loc[miss, "src_health_zone"] = pairs.loc[miss, "src_code"].map(code_map.health_zone)
note("CT", "source persons not found in linelist", pairs.loc[~pairs.src_in_ll, "source_case_person_id"].nunique(),
     "kept as source cases; province/health zone inferred from alert-ID prefix (%d pairs still unlocated)" % pairs.src_province.isna().sum())

# Secondary case definition
pairs["sec_ll"] = pairs.con_is_case.astype("boolean").fillna(False).astype(bool)
ll_neg = pairs.con_classification.eq("not_a_case")
# MAIN definition (manuscript): secondary case = confirmed/probable in linelist, OR worst CT
# result 'case_confirmed' or 'case_validated', unless the linelist classifies them not_a_case.
# Caveat: CT 'case_validated' is concentrated in a Nyankunde May-June hospital cluster
# (recorded 16-25 May, ~4 days after exposure, 101/107 absent from linelist); a strict
# definition without it is kept as a sensitivity analysis.
pairs["sec_ct_confirmed"] = pairs.ct_worst_result.eq("case_confirmed") & ~ll_neg
pairs["sec_ct_validated"] = pairs.ct_worst_result.eq("case_validated") & ~ll_neg
pairs["sec_ct"] = pairs.sec_ct_confirmed | pairs.sec_ct_validated
pairs["secondary_case"] = pairs.sec_ll | pairs.sec_ct
# sensitivity definitions
pairs["secondary_with_cv"] = pairs.secondary_case                                       # alias (= main)
pairs["secondary_strict"] = pairs.sec_ll | pairs.sec_ct_confirmed                       # excludes CT 'case_validated'
pairs["secondary_upper"] = pairs.secondary_with_cv | (pairs.ct_worst_result.eq("contact_became_suspected_case") & ~ll_neg)
note("CT", "contacts confirmed/probable in linelist", pairs.sec_ll.sum(), "secondary case")
note("CT", "contacts confirmed/probable in linelist but CT outcome never updated (worst CT result 'not a case' or blank)",
     (pairs.sec_ll & (pairs.ct_worst_result.isna() | pairs.ct_worst_result.eq("not_a_case"))).sum(),
     "linelist classification wins (secondary case)")
note("CT", "contacts with CT result 'case_confirmed' but no linked linelist case", (pairs.sec_ct_confirmed & ~pairs.sec_ll).sum(),
     "counted as secondary case (CT team reports confirmation; linkage to linelist missing)")
note("CT", "contacts with CT result 'case_validated' but no linked linelist case", (pairs.sec_ct_validated & ~pairs.sec_ll).sum(),
     "counted as secondary case in main analysis (mostly Nyankunde May-June hospital cluster); excluded in strict sensitivity analysis")
note("CT", "contacts with CT result 'case_confirmed'/'case_validated' but linelist says not_a_case",
     (pairs.ct_worst_result.isin(["case_confirmed", "case_validated"]) & ll_neg).sum(),
     "NOT counted as secondary case (lab-based linelist classification wins)")
note("CT", "contacts with CT result 'contact_became_suspected_case' (not linelist-negative), not otherwise a secondary case",
     (pairs.secondary_upper & ~pairs.secondary_case).sum(),
     "NOT counted in main analysis; included in upper-bound sensitivity analysis")

# source cases that are not cases
note("CT", "source persons classified not_a_case in linelist",
     pairs.loc[pairs.src_classification.eq("not_a_case"), "source_case_person_id"].nunique(),
     "kept in CT process metrics; excluded from SAR/serial interval")

persons.to_csv(os.path.join(OUT, "persons.csv"))
pairs.to_csv(os.path.join(OUT, "pairs.csv"), index=False)
ctk.drop(columns=["export_order"]).to_csv(os.path.join(OUT, "followups.csv"), index=False)
pd.DataFrame(log).to_csv(os.path.join(OUT, "decisions_log.csv"), index=False)
print(pd.DataFrame(log).to_string())
print(len(persons), len(pairs))
