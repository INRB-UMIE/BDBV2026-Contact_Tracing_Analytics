#!/usr/bin/env bash
# Run the contact-tracing report pipeline end to end.
#   ./run_report.sh            # Python steps only (uses cached distribution fits, if any)
#   ./run_report.sh --fit      # also run the R distribution fitting (epidist/brms; slow)
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
$PY 04_report.py
echo "Done. Outputs: $($PY -c 'import ctr_paths; print(ctr_paths.OUT_ROOT)')"
