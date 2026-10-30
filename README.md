![Private](https://img.shields.io/badge/Repository-Private-red)

# BDBV2026 — Contact Tracing Analytics

Code-only repo for the contact-tracing analysis and report for the Bundibugyo virus disease (BDBV) outbreak in the DRC (2026). Covers data harmonisation, the contact-tracing indicators, the patient-journey delays, secondary attack rate (SAR), and the serial-interval and incubation-period fits. **It contains no raw or person-level data**; aggregate results (tables, figures, reports) are committed under `outputs/`.

## Code / data split

As with [`BDBV2026-Processing_Code`](https://github.com/INRB-UMIE/BDBV2026-Processing_Code), inputs live in sibling repos (outputs are written to this repo's `outputs/` folder). Clone them side by side:

```
parent/
├── BDBV2026-Contact_Tracing_Analytics/   # this repo (code; results in outputs/<DATE>/)
├── BDBV2026-Processed_Sensitive_Data/    # inputs: data/<DATE>/
└── BDBV2026-Data/                        # health-zone boundaries: build/drc_health_zones.geojson
```

Paths are resolved in `pipelines/contact_tracing_report/ctr_paths.py` (Python) and at the top of `05_fit_distributions_epidist.R` (R), in this order:

1. Environment variables, if set: `BDBV_DATA_ROOT` (data repo) and `BDBV_GEO_ROOT` (BDBV2026-Data).
2. Otherwise, sibling folders with the names above.

| Variable | Default | Purpose |
|---|---|---|
| `CT_REPORT_DATE` | most recent `data/<DATE>/` | Which `data/<DATE>/` export to use; also the data cut used for the follow-up and truncation rules |
| `CT_REPORT_OUT` | `<this repo>/outputs/<DATE>` | Override the output folder |
| `REFIT` | `FALSE` | `TRUE` ignores cached distribution fits |
| `CT_PERSON_REGISTRY` | `confirmed` | `candidates` runs the person-registry sensitivity analysis (see below); set by `./run_report.sh --candidates` |

Outputs are written to `outputs/<DATE>/` in this repo (`derived/`, `tables/`, `figures/`, Word files). Aggregate outputs (`tables/`, `figures/`, Word files) are committed. **`derived/` is git-ignored**: it holds person-level (de-identified) outbreak data and fit caches, and must never be committed.

## Pipeline

```
pipelines/contact_tracing_report/
├── ctr_paths.py                     # path resolution (shared by all Python steps)
├── 01_harmonise.py                  # person-level linelist + CT pairs; every discrepancy decision -> derived/decisions_log.csv
├── 02_analysis.py                   # all statistics; tables/*.csv, derived/results.json, derived/epidist_inputs/
├── 03_figures.py                    # Figures 1-4 + supplementary figures (LSHTM theme)
├── 04_report.py                     # Word report (2-page main text + figures + SI)
├── 05_fit_distributions_epidist.R   # serial interval & incubation fits (epidist / brms), main + sensitivity analyses
├── 06_fig3A_proportions.py          # stand-alone variant of Figure 3A (proportions)
├── 07_sar_sensitivity.py            # SAR sensitivity analyses + Nyankunde 'case validated' analysis
├── 08_followup_sankey.py            # follow-up retention / daily-status Sankey plots by health zone
├── 09_table1.py                     # manuscript Table 1 (tables/table1.csv + table1.docx); needs the R fits from 05
├── 10_table2.py                     # manuscript Table 2: indicators by province (tables/table2_province.csv + table2.docx)
├── 11_offspring_distribution.py     # Fig S9: secondary cases per source (superspreading), negative binomial k, beta-binomial ICC
├── 12_si5_risk_factors.py          # SI-5 table: SAR, crude RR, adjusted OR by factor (bootstrap + Wilson/Wald CIs)
├── 13_dashboard_tables.py         # aggregate tables for the dashboard's Surveillance and Testing tab (tables/dashboard_*)
└── 14_registry_sensitivity.py     # person-registry sensitivity: confirmed vs candidate person IDs (run by --candidates)
```

Run everything from the repo root:

```bash
pip install -r requirements.txt
./run_report.sh          # Python steps (re-uses cached R fits)
./run_report.sh --fit    # also runs the R distribution fits (slow; needs epidist, brms, primarycensored, cmdstanr or rstan)
```

### Figures

`outputs/<DATE>/figures/` holds only the manuscript figures, named by figure number. Everything else goes to `figures/additional/`.

| File | Manuscript | Made by |
|---|---|---|
| `fig1_data_summary.png` | Figure 1 | 03 |
| `fig2_patient_journey.png` | Figure 2 | 03 |
| `fig3_ct_effectiveness.png` | Figure 3 (panel D as lines) | 03 |
| `fig4_epi_implications.png` | Figure 4 (SAR incl. 'case validated'; fitted gammas need 05) | 03 |
| `figS1_hz_timeseries.png` | Figure S1 | 03 |
| `figS2_followup_sankey.png` | Figure S2 | 08 |
| `figS3_followup_days_with_result.png` | Figure S3 | 03 |
| `figS4_sar_sensitivity.png` | Figure S4 | 07 |
| `figS5_nyankunde_case_validated.png` | Figure S5 | 07 |
| `figS6_distribution_families.png` | Figure S6 | 05 (R) |
| `figS7_serial_interval_sensitivity.png` | Figure S7 | 05 (R) |
| `figS8_incubation_sensitivity.png` | Figure S8 | 05 (R) |
| `figS9_offspring_distribution.png` | Figure S9 (secondary cases per source; overdispersion) | 11 |

Or run steps one at a time, e.g. `python3 pipelines/contact_tracing_report/02_analysis.py`. Run order: 01 → 02 → (05) → 03 → 06–13.

**R packages for step 05:** `dplyr`, `readr`, `tidyr`, `stringr`, `ggplot2`, `brms`, `epidist`, `primarycensored`, `posterior`, `loo`, plus `cmdstanr` (preferred) or `rstan`. The figures and fits use the same `lshtm_theme()` as `BDBV2026-Processing_Code/pipelines/contact_tracing_pipeline/3-pairs-plots.R`.

## Main definitions (manuscript)

- **SAR denominator:** source–contact pairs where the source is a confirmed or probable linelist case, and the contact's first follow-up (or, if there are none, their registration) was on or before the data cut minus 21 days.
- **SAR numerator:** the contact is a confirmed or probable linelist case, or has a CT result of `case_confirmed` or `case_validated`. A linelist classification of `not_a_case` overrides the CT result.
- **Serial interval:**
  - Pairs where both people are confirmed or probable linelist cases with onset dates.
  - The infector's onset is on or before the data cut minus 42 days.
  - The serial interval is between −5 and 60 days.
  - Pairs recorded in both directions are excluded.
- **Incubation:**
  - The same infector rules as the serial interval.
  - Infection is assumed uniform between the infector's onset and the earlier of the last exposure and the infectee's onset; the exposure date is used if it came before the infector's onset.
  - The infectee's onset is 1–60 days after the infector's, and no more than 42 days after the last exposure.

## Sensitivity analyses

| Metric | Analyses |
|---|---|
| SAR (`07`) | SAR-1 excluding CT `case_validated`; SAR-5 linelist cases only; SAR-6 excluding the Nyankunde May–June hospital cluster; plus a Nyankunde-specific analysis (cluster description, SAR by period × definition) |
| Serial interval (`05`) | 2 × 2: cut-off yes/no × negatives (−5 d) yes/no |
| Incubation (`05`) | 2 × 2: cut-off yes/no × uniform window / last exposure |
| Distribution families (`05`) | gamma, lognormal, Weibull, negative binomial, normal (serial interval); gamma, lognormal, Weibull (incubation), compared on the main-analysis data only |

Full decision log: `derived/decisions_log.csv` in the output folder.

### Person-registry sensitivity

Person IDs in the exports come from `person_registry.csv` (confirmed matches only). Links still waiting for review are therefore missing, and they can change the SAR (e.g. a contact who is also a linelist case under another ID). `person_registry_with_candidates.csv` gives an upper bound: its `candidate_person_id` groups IDs as if every match suggested by the algorithm (and not rejected) were accepted.

```bash
./run_report.sh                 # main run (confirmed IDs)         -> outputs/<DATE>/
./run_report.sh --candidates    # IDs re-issued from candidates    -> outputs/<DATE>/registry_candidates/
                                # then 14_registry_sensitivity.py  -> registry_candidates/tables/registry_sensitivity.csv
                                #                                     registry_candidates/figures/additional/registry_sensitivity.png
```

- In candidate mode, `01_harmonise.py` replaces `person_id`, `source_case_person_id` and `contact_person_id` with the `candidate_person_id` of each original ID (`alert_id`, `source_case_alert_id`, `contact_id`). If an original ID is missing from the registry, it falls back to the exported `person_id`. If neither is found, the run stops. Every later step runs unchanged.
- The registry files are only **read**, never written. The main run does not open either file.
- The run stops if the candidate grouping would split a confirmed person (it must only merge).
- Counts of re-issued IDs and the extra self-pairs (dropped) are in `registry_candidates/derived/decisions_log.csv`. The original IDs are kept in `*_person_id_confirmed` columns in the derived files.
- The registry is a single current file, not one per cut. For an older cut it also includes matches confirmed after that export; these rows are counted in the decision log ("exported person_id differs from the registry's current person_id").
- The R distribution fits (step 05) are skipped in the candidate run because they are slow; `--fit` is ignored there. The comparison covers the empirical serial-interval and incubation pairs (counts, mean, median) but not the fitted gamma distributions.

## Dates and new data cuts

No dates need editing for a new cut. By default the pipeline uses the most recent `data/<YYYY-MM-DD>/` folder that has both input files; set `CT_REPORT_DATE` to run an older cut.

All cut-dependent dates are worked out from the cut date in `ctr_paths.py` (the R script uses the same rules):

| Name | Rule | 9 Oct cut |
|---|---|---|
| `FU_WINDOW_END` | cut − 21 days (SAR denominator, follow-up completeness) | 18 Sep |
| `ONSET_END` | cut − 26 days (Fig 2 right truncation) | 13 Sep |
| `WK_END` | last onset week ending on/before `ONSET_END` (Fig 2B) | 7 Sep |
| `LAST_FULL_WEEK` | Monday of the last complete week before the cut | 28 Sep |
| `CUT42` | cut − 42 days (serial interval / incubation) | 28 Aug |
| CT registration end | last CT registration date in the data (step 02) | 4 Oct |
| Monthly panels | May up to the last complete month (or month of `FU_WINDOW_END` for follow-up panels) | May–Sep |

Fixed outbreak dates that do not change with the cut are kept as named constants: `FIRST_ONSET_WEEK` (4 May), `FIRST_FULL_WEEK` (11 May), `RESULT_ENTRY_CHANGE` (14 Sep, when follow-up results start going missing), and the Nyankunde cluster window in `07_sar_sensitivity.py`.

The Word report (`04_report.py`) is no longer part of `run_report.sh` and still contains 9 Oct wording.
