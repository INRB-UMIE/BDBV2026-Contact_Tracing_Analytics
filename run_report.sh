#!/usr/bin/env bash
# Run the contact-tracing report pipeline end to end.
#   ./run_report.sh                    # Python steps only (uses cached distribution fits, if any)
#   ./run_report.sh --fit              # also run the R distribution fitting (epidist/brms; slow)
#   ./run_report.sh --candidates       # registry sensitivity analysis: rerun every step with person IDs
#                                      # re-issued from person_registry_with_candidates.csv (read-only),
#                                      # outputs in outputs/<DATE>/registry_candidates/, then compare with
#                                      # the main run (14_registry_sensitivity.py). Run the main pipeline first.
#   ./run_report.sh --candidates --fit # same, including the R fits for the candidate run
# CT_REPORT_DATE defaults to the most recent data/<YYYY-MM-DD>/ folder.
# Settings via environment variables: CT_REPORT_DATE, BDBV_DATA_ROOT, BDBV_GEO_ROOT, CT_REPORT_OUT, REFIT,
# CT_PERSON_REGISTRY (set automatically by --candidates)
set -euo pipefail
cd "$(dirname "$0")/pipelines/contact_tracing_report"
PY=${PYTHON:-python3}

FIT=0; CANDIDATES=0
for a in "$@"; do
  case "$a" in
    --fit) FIT=1 ;;
    --candidates) CANDIDATES=1 ;;
    *) echo "Unknown option: $a (use --fit and/or --candidates)"; exit 1 ;;
  esac
done
if [[ $CANDIDATES == 1 ]]; then
  export CT_PERSON_REGISTRY=candidates
else
  export CT_PERSON_REGISTRY=${CT_PERSON_REGISTRY:-confirmed}
fi

$PY 01_harmonise.py
$PY 02_analysis.py
if [[ $FIT == 1 ]]; then
  Rscript 05_fit_distributions_epidist.R
fi
$PY 03_figures.py
$PY 06_fig3A_proportions.py
$PY 07_sar_sensitivity.py
$PY 08_followup_sankey.py
$PY 09_table1.py
$PY 10_table2.py
$PY 11_offspring_distribution.py
$PY 12_si5_risk_factors.py
$PY 13_dashboard_tables.py
if [[ $CT_PERSON_REGISTRY == candidates ]]; then
  $PY 14_registry_sensitivity.py
fi
# 04_report.py (Word report) is no longer part of the standard run; run it by hand if ever needed.
echo "Done. Outputs: $($PY -c 'import ctr_paths; print(ctr_paths.OUT_ROOT)')"
