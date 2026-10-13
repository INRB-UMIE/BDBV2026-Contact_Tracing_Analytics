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
  CT_REPORT_DATE  data cut / export folder to use (default 2026-10-09)
  CT_REPORT_OUT   override the output folder
                  (default CODE_ROOT/outputs/<DATE>, i.e. this repo's outputs/ folder)

NOTE: derived/ contains person-level (de-identified) outbreak data and is git-ignored.
Aggregate tables, figures and Word files in outputs/ are committed.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CODE_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
REPORT_DATE = os.environ.get("CT_REPORT_DATE", "2026-10-09")


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
DATA_DIR = os.path.join(DATA_ROOT, "data", REPORT_DATE)


def geo_file():
    """Health-zone GeoJSON (only needed by the figure scripts)."""
    root = _resolve("BDBV_GEO_ROOT", ["BDBV2026-Data"], os.path.join("build", "drc_health_zones.geojson"))
    return os.path.join(root, "build", "drc_health_zones.geojson")


OUT_ROOT = os.environ.get("CT_REPORT_OUT", os.path.join(CODE_ROOT, "outputs", REPORT_DATE))
D = os.path.join(OUT_ROOT, "derived")      # person/pair-level intermediate files
T = os.path.join(OUT_ROOT, "tables")
F = os.path.join(OUT_ROOT, "figures")                 # figures used in the manuscript (Fig 1-4, S1-S8)
FA = os.path.join(F, "additional")                   # everything else (alternative versions, extra panels)
REPORT_DOCX = os.path.join(OUT_ROOT, f"BDBV_contact_tracing_report_{REPORT_DATE}.docx")
for _d in (D, T, F, FA):
    os.makedirs(_d, exist_ok=True)

if not os.path.isdir(DATA_DIR):
    raise FileNotFoundError(f"No data folder for CT_REPORT_DATE={REPORT_DATE}: {DATA_DIR}")
