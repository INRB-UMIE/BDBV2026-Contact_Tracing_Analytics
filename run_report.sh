#!/usr/bin/env bash
# Run the contact-tracing report pipeline end to end.
#   ./run_report.sh            # Python steps only (uses cached distribution fits, if any)
#   ./run_report.sh --fit      # also run the R distribution fitting (epidist/brms; slow)
# CT_REPORT_DATE defaults to the most recent data/<YYYY-MM-DD>/ folder.
# Settings via environment variables: CT_REPORT_DATE, BDBV_DATA_ROOT, BDBV_GEO_ROOT, CT_REPORT_OUT, REFIT
set -euo pipefail
cd "$(dirname "$0")/pipelines/contact_tracing_report"
PY=${PYTHON:-python3}

$PY 01_harmonise.py
$PY 02_analysis.py
if [[ "${1:-}" == "--fit" ]]; then
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
# 04_report.py (Word report) is no longer part of the standard run; run it by hand if ever needed.
echo "Done. Outputs: $($PY -c 'import ctr_paths; print(ctr_paths.OUT_ROOT)')"
