"""
Path resolution for the contact-tracing report pipeline.

This repo (BDBV2026-Contact_Tracing_Analytics) holds code only. Inputs and outputs
live in sibling repos, mirroring BDBV2026-Processing_Code/pipelines/0-setup.R:

  CODE_ROOT  this repo
  DATA_ROOT  BDBV2026-Processed_Sensitive_Data   (data/<DATE>/ inputs, outputs/<DATE>/ results)
  GEO_ROOT   BDBV2026-Data                       (build/drc_health_zones.geojson)

Each root is resolved in this order:
  1. environment variable (BDBV_DATA_ROOT / BDBV_GEO_ROOT) if set
  2. a sibling folder of CODE_ROOT with one of the known repo names

Other settings (environment variables):
  CT_REPORT_DATE  data cut / export folder to use (default: the most recent data/<YYYY-MM-DD>/
                  folder that has both input files)
  CT_REPORT_OUT   override the output folder
                  (default CODE_ROOT/outputs/<DATE>, i.e. this repo's outputs/ folder)
  CT_PERSON_REGISTRY  'confirmed' (default) or 'candidates'.
                  confirmed : person IDs exactly as they are in the linelist / CT exports
                              (issued from data/person_registry.csv). No registry file is opened.
                  candidates: registry sensitivity analysis. IDs are re-issued from the
                              candidate_person_id column of data/person_registry_with_candidates.csv
                              (every algorithm-suggested match accepted). That file is only READ;
                              neither registry file is ever modified. Outputs go to
                              outputs/<DATE>/registry_candidates/ so main results are untouched.

NOTE: derived/ contains person-level (de-identified) outbreak data and is git-ignored.
Aggregate tables, figures and Word files in outputs/ are committed.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def _resolve(env_var, known_names, must_contain):
    override = os.environ.get(env_var, "")
    if override:
        if not os.path.exists(os.path.join(override, must_contain)):
            raise FileNotFoundError(f"{env_var} is set to '{override}' but '{must_contain}' was not found there.")
        return os.path.abspath(override)
    parent = os.path.dirname(CODE_ROOT)
    for nm in known_names:
        cand = os.path.join(parent, nm)
        if os.path.exists(os.path.join(cand, must_contain)):
            return cand
    raise FileNotFoundError(
        f"Could not find any of {known_names} next to {CODE_ROOT} (looking for '{must_contain}'). "
        f"Clone the repos side by side or set {env_var}.")


DATA_ROOT = _resolve("BDBV_DATA_ROOT",
                     ["BDBV2026-Processed_Sensitive_Data", "BDBV2026-Contact_Tracing_Analysis"], "data")
REQUIRED_INPUTS = ("dhis2_processed_linelist_ctsafe.csv", "contact_tracing_combined_ctsafe.csv")


def latest_cut(data_root=None):
    """Most recent data/<YYYY-MM-DD>/ folder containing all REQUIRED_INPUTS."""
    base = os.path.join(data_root or DATA_ROOT, "data")
    cuts = sorted(d for d in os.listdir(base)
                  if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)
                  and all(os.path.exists(os.path.join(base, d, f)) for f in REQUIRED_INPUTS))
    if not cuts:
        raise FileNotFoundError(f"No data/<YYYY-MM-DD>/ folder with {REQUIRED_INPUTS} under {base}")
    return cuts[-1]


REPORT_DATE = os.environ.get("CT_REPORT_DATE", "") or latest_cut()
DATA_DIR = os.path.join(DATA_ROOT, "data", REPORT_DATE)


def geo_file():
    """Health-zone GeoJSON (only needed by the figure scripts)."""
    root = _resolve("BDBV_GEO_ROOT", ["BDBV2026-Data"], os.path.join("build", "drc_health_zones.geojson"))
    return os.path.join(root, "build", "drc_health_zones.geojson")


# --- person registry used for person IDs (see docstring) ----------------------
PERSON_REGISTRY = (os.environ.get("CT_PERSON_REGISTRY", "") or "confirmed").strip().lower()
if PERSON_REGISTRY not in ("confirmed", "candidates"):
    raise ValueError(f"CT_PERSON_REGISTRY must be 'confirmed' or 'candidates', not '{PERSON_REGISTRY}'")
CANDIDATE_REGISTRY_FILE = os.path.join(DATA_ROOT, "data", "person_registry_with_candidates.csv")
CANDIDATE_SUBDIR = "registry_candidates"

MAIN_OUT_ROOT = os.path.join(CODE_ROOT, "outputs", REPORT_DATE)   # confirmed-registry results for this cut
OUT_ROOT = os.environ.get("CT_REPORT_OUT", "") or (
    os.path.join(MAIN_OUT_ROOT, CANDIDATE_SUBDIR) if PERSON_REGISTRY == "candidates" else MAIN_OUT_ROOT)
if PERSON_REGISTRY == "candidates" and os.path.abspath(OUT_ROOT) == os.path.abspath(MAIN_OUT_ROOT):
    raise ValueError("CT_PERSON_REGISTRY=candidates would overwrite the main outputs; pick another CT_REPORT_OUT.")
D = os.path.join(OUT_ROOT, "derived")      # person/pair-level intermediate files
T = os.path.join(OUT_ROOT, "tables")
F = os.path.join(OUT_ROOT, "figures")                 # figures used in the manuscript (Fig 1-4, S1-S8)
FA = os.path.join(F, "additional")                   # everything else (alternative versions, extra panels)
REPORT_DOCX = os.path.join(OUT_ROOT, f"BDBV_contact_tracing_report_{REPORT_DATE}.docx")
for _d in (D, T, F, FA):
    os.makedirs(_d, exist_ok=True)

if not os.path.isdir(DATA_DIR):
    raise FileNotFoundError(f"No data folder for CT_REPORT_DATE={REPORT_DATE}: {DATA_DIR}")


# =============================================================================
# Dates. Everything that depends on the data cut is derived from CT_REPORT_DATE
# here, so no script needs editing for a new cut. For the 9 Oct 2026 cut these
# give exactly the dates that used to be hard-coded (shown in brackets).
# =============================================================================
import pandas as _pd


def monday(ts):
    """Monday of the week containing ts (weeks start on Monday)."""
    ts = _pd.Timestamp(ts)
    return (ts - _pd.Timedelta(days=ts.weekday())).normalize()


def fmt_day(ts, year=True):
    """'9 Oct 2026' (or '9 Oct'), without a leading zero."""
    ts = _pd.Timestamp(ts)
    return f"{ts.day} {ts:%b}" + (f" {ts.year}" if year else "")


def fmt_day_long(ts, year=True):
    """'9 October 2026' (or '9 October')."""
    ts = _pd.Timestamp(ts)
    return f"{ts.day} {ts:%B}" + (f" {ts.year}" if year else "")


def month_range(start, end):
    """['2026-05', ..., end] as 'YYYY-MM' strings (inclusive)."""
    return [str(p) for p in _pd.period_range(_pd.Period(start, "M"), _pd.Period(end, "M"), freq="M")]


# --- derived from the data cut ------------------------------------------------
CUT = _pd.Timestamp(REPORT_DATE)                      # data cut                     (9 Oct)
CUT_LABEL = fmt_day(CUT)                              # '9 Oct 2026' for captions
CUT_LABEL_LONG = fmt_day_long(CUT)                    # '9 October 2026' for report text
FU_WINDOW_END = CUT - _pd.Timedelta(days=21)          # first follow-up on/before -> day 21 reached by the cut (18 Sep)
ONSET_END = CUT - _pd.Timedelta(days=26)              # Fig 2: last onset date used (>=26 days to cut) (13 Sep)
# Fig 2B: last onset week that ends on or before ONSET_END                      (7 Sep)
WK_END = monday(ONSET_END) if ONSET_END.weekday() == 6 else monday(ONSET_END) - _pd.Timedelta(days=7)
LAST_FULL_WEEK = monday(CUT) - _pd.Timedelta(days=7)  # last complete week before the cut's week (28 Sep)
CUT_WEEK = monday(CUT)                                # the (incomplete) week of the cut (5 Oct)
CUT42 = CUT - _pd.Timedelta(days=42)                  # serial interval / incubation infector-onset cut-off (28 Aug)

# --- fixed epidemiological dates (do NOT depend on the cut) -------------------
FIRST_MONTH = "2026-05"                     # first month shown in monthly panels
FIRST_ONSET_WEEK = _pd.Timestamp("2026-05-04")   # first onset week drawn in Fig 2B / Fig S1
FIRST_FULL_WEEK = _pd.Timestamp("2026-05-11")    # first week with >=20 cases (weekly panels)
RESULT_ENTRY_CHANGE = _pd.Timestamp("2026-09-14")  # follow-up results start going missing (before/after comparison)

# --- month lists ----------------------------------------------------------------
LAST_COMPLETE_MONTH = str((CUT.to_period("M") - 1))          # last calendar month fully before the cut ('2026-09')
MONTHS_COMPLETE = month_range(FIRST_MONTH, LAST_COMPLETE_MONTH)      # May .. Sep
MONTHS_FU = month_range(FIRST_MONTH, FU_WINDOW_END)                  # by month of first follow-up: May .. Sep (Sep = 1-18 Sep)
MONTH_ORDER = month_range(FIRST_MONTH, CUT)                          # every month up to the cut (ordering only)


def month_abbr(m):
    """'2026-09' -> 'Sep'."""
    return _pd.Period(m, "M").strftime("%b")


def month_name(m):
    """'2026-09' -> 'September'."""
    return _pd.Period(m, "M").strftime("%B")


def ct_last_registration(registration_dates):
    """Last CT registration date in the data (capped at the cut). Was hard-coded as 4 Oct for the 9 Oct cut."""
    d = _pd.to_datetime(registration_dates).dropna()
    d = d[d <= CUT]
    return d.max().normalize() if len(d) else CUT
