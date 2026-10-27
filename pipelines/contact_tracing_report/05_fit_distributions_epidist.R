#!/usr/bin/env Rscript
# =============================================================================
# 05_fit_distributions_epidist.R
#
# Parametric fits for the SERIAL INTERVAL and INCUBATION PERIOD (BDBV, DRC,
# data cut = CT_REPORT_DATE): a pre-specified MAIN analysis per quantity plus three
# sensitivity analyses each (2 x 2 designs), comparing up to five families:
#   lognormal, gamma, Weibull -> epidist (primarycensored marginal model)
#   negative binomial         -> brms (integer delay, truncated)
#   normal                    -> brms (only where SIs can be negative)
# PRIMARY FAMILY FOR REPORTING: gamma (pre-specified; others shown in the SI).
#
# ----------------------------- ANALYSIS DESIGN --------------------------------
# Cut-off: observations are restricted to those whose INFECTOR's onset was at least
# 42 days before the data cut (on/before CUTOFF = data cut - 42 days). The model-based
# right-truncation adjustment (obs_date = data cut) is kept in ALL fits, since
# 42 days is shorter than the longest delays considered and the reporting /
# linkage lag uses up part of the window.
#
# Serial interval (first event = infector onset):
#               | cut-off     | no cut-off
#   -5 to 60 d  | MAIN        | Sensitivity 2
#   0 to 60 d   | Sens. 3     | Sensitivity 1
#
# Incubation period (first event = end of the exposure window):
#                                         | cut-off | no cut-off
#   uniform window: infection between     | MAIN    | Sensitivity 2
#   source onset and min(last exposure,   |         |
#   contact onset)                        |         |
#   last exposure -> onset (1-42 d)       | Sens. 1 | Sensitivity 3
#
# ------------------------------ MODELLING NOTES -------------------------------
#   * Daily interval censoring of both events (epidist default windows of 1 day).
#   * Right truncation: obs_date = DATA_CUT for every row (epidist adjusts the
#     likelihood); NB / normal use brms trunc(ub = DATA_CUT - first date).
#   * Negative SIs: positive-support families (lognormal, gamma, Weibull, NB)
#     are fitted to SI + SHIFT (SHIFT = 6 for SIs from -5 d, so the fitted
#     lower bound is -6 d) and all location summaries are shifted back; SD is
#     unaffected. A normal distribution is added as a shift-free check.
#   * Uniform-window incubation: infection (primary event) is uniformly
#     distributed between the source's onset and the earlier of the last
#     exposure and the contact's own onset. This is handled exactly in the
#     likelihood via epidist's primary-event window (pdate_lwr, pdate_upr),
#     i.e. it integrates over the uniform window rather than drawing dates.
#     Requires the source's onset to be known. If the last exposure was BEFORE
#     the source's onset, the window collapses to the exposure date (i.e. the
#     last exposure is taken as the transmission date). NB cannot use a
#     primary window, so it is not fitted here.
#     Last-exposure incubation is a lower bound; the uniform window is likely an
#     upper-leaning estimate if infectiousness peaks late in illness.
#   * LOO: epidist aggregates identical observations; pointwise log-lik is
#     expanded back to one value per observation (loo_per_obs()). Treat ELPD
#     differences < ~2 SE as no difference. LOO only compares families within
#     an analysis (different analyses use different data).
#   * Non-converged fits (Rhat >= 1.05, bulk ESS <= 400 or > 1% divergent
#     transitions) are flagged and dropped from comparisons.
#   * "Found infinite values in the data" warnings are expected (epidist sets
#     relative observation times far from the data cut to Inf).
#
# All paths below are relative to OUT_ROOT = <this repo>/outputs/<CT_REPORT_DATE>
# (same resolution as ctr_paths.py: BDBV_DATA_ROOT or sibling BDBV2026-Processed_Sensitive_Data;
#  CT_REPORT_DATE default = most recent data/<YYYY-MM-DD>/ with both inputs; CT_REPORT_OUT overrides the folder).
# Inputs (02_analysis.py): derived/epidist_inputs/serial_interval_pairs.csv,
#                          derived/epidist_inputs/incubation_cases.csv
# Outputs:
#   derived/epidist_fits/<analysis>_<datahash>/<family>.rds  cached fits + LOO (hash of the data/settings)
#   tables/distribution_fits_summary.csv                 every analysis x family
#   tables/distribution_fits_loo_compare.csv
#   tables/distribution_fits_main_gamma.csv              manuscript table
#   tables/distribution_fits_sensitivity_comparison.csv  long format, all families
#   figures/figS_distribution_fits_<analysis>.png        data vs fitted, per analysis
#   tables/distribution_fits_families_main.csv          all families on the main-analysis data
#   figures/figS_sensitivity_serial_interval.png         gamma: main vs sensitivity (SI)
#   figures/figS_sensitivity_incubation.png              gamma: main vs sensitivity (incubation)
#   figures/figS_distribution_families_main.png          families compared on main-analysis data
#
# Run from anywhere:  Rscript pipelines/contact_tracing_report/05_fit_distributions_epidist.R
# Ignore caches:     REFIT=TRUE Rscript pipelines/contact_tracing_report/05_fit_distributions_epidist.R
# =============================================================================

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(tidyr)
  library(ggplot2)
  library(brms)
  library(epidist)
  library(primarycensored)
  library(posterior)
  library(loo)
})

# ------------------------------- paths ---------------------------------------
resolve_script_dir <- function() {
  f <- sub("^--file=", "", grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE))
  if (length(f)) return(dirname(normalizePath(f[1])))
  if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
    p <- rstudioapi::getSourceEditorContext()$path
    if (nzchar(p)) return(dirname(normalizePath(p)))
  }
  getwd()
}
code_root <- normalizePath(file.path(resolve_script_dir(), "..", ".."), mustWork = FALSE)
resolve_data_root <- function() {
  env <- Sys.getenv("BDBV_DATA_ROOT", unset = "")
  if (nzchar(env)) {
    if (!dir.exists(file.path(env, "data"))) stop("BDBV_DATA_ROOT='", env, "' has no data/ folder", call. = FALSE)
    return(normalizePath(env))
  }
  for (nm in c("BDBV2026-Processed_Sensitive_Data", "BDBV2026-Contact_Tracing_Analysis")) {
    cand <- file.path(dirname(code_root), nm)
    if (dir.exists(file.path(cand, "data"))) return(normalizePath(cand))
  }
  stop("Could not find BDBV2026-Processed_Sensitive_Data next to ", code_root, "; set BDBV_DATA_ROOT.", call. = FALSE)
}
data_root   <- resolve_data_root()
latest_cut <- function(root) {
  req <- c("dhis2_processed_linelist_ctsafe.csv", "contact_tracing_combined_ctsafe.csv")
  cuts <- sort(list.files(file.path(root, "data"), pattern = "^\\d{4}-\\d{2}-\\d{2}$"))
  cuts <- cuts[vapply(cuts, function(d) all(file.exists(file.path(root, "data", d, req))), logical(1))]
  if (!length(cuts)) stop("No data/<YYYY-MM-DD>/ folder with both input files under ", root, call. = FALSE)
  tail(cuts, 1)
}
REPORT_DATE <- Sys.getenv("CT_REPORT_DATE", unset = "")
if (!nzchar(REPORT_DATE)) REPORT_DATE <- latest_cut(data_root)
OUT_ROOT    <- Sys.getenv("CT_REPORT_OUT", unset = file.path(code_root, "outputs", REPORT_DATE))
message("Reading/writing under: ", OUT_ROOT)

# ------------------------------- settings ------------------------------------
DATA_CUT     <- as.Date(REPORT_DATE)
CUTOFF_DAYS  <- 42L
CUTOFF       <- DATA_CUT - CUTOFF_DAYS          # derived from the data cut (28 Aug for the 9 Oct cut)
SI_MAX       <- 60L
SI_NEG_MIN   <- -5L                              # negatives kept down to -5 d
SI_NEG_SHIFT <- 6L                               # SI + 6 >= 1 for positive-support families
INC_MIN      <- 1L                               # last-exposure definition: onset >= 1 d after
INC_MAX      <- 42L
INC_WIN_MAX_FROM_SOURCE <- 60L                   # window definition: onset <= 60 d after source onset
CHAINS       <- 4L
CORES        <- min(4L, max(1L, parallel::detectCores() - 1L))
ITER         <- 2000L
SEED         <- 20261009L                       # kept fixed so cached fits stay reproducible
BACKEND      <- if (requireNamespace("cmdstanr", quietly = TRUE)) "cmdstanr" else "rstan"
REFIT        <- toupper(Sys.getenv("REFIT", "FALSE")) == "TRUE"
N_PLOT_DRAWS <- 200L
PRIMARY_FAMILY <- "gamma"

IN_DIR  <- file.path(OUT_ROOT, "derived", "epidist_inputs")
FIT_DIR <- file.path(OUT_ROOT, "derived", "epidist_fits")
TAB_DIR <- file.path(OUT_ROOT, "tables")
FIG_DIR <- file.path(OUT_ROOT, "figures")                 # manuscript figures (S6-S8)
FIG_ADD <- file.path(FIG_DIR, "additional")               # per-analysis fit plots
dir.create(FIG_ADD, recursive = TRUE, showWarnings = FALSE)
if (!file.exists(file.path(IN_DIR, "serial_interval_pairs.csv")))
  stop("Inputs not found in ", IN_DIR, " -- run 01_harmonise.py and 02_analysis.py first.", call. = FALSE)
for (d in c(FIT_DIR, TAB_DIR, FIG_DIR)) dir.create(d, recursive = TRUE, showWarnings = FALSE)

# ---------------------- LSHTM theme (copied from 3-pairs-plots.R) -----------
COLOR_INK <- "#01454f"; COLOR_MAIN <- "#1a8c99"; COLOR_LIGHT <- "#e3f0f1"
COLOR_MUTED <- "#a3b9bc"; COLOR_ALERT <- "#e0703f"
lshtm_theme <- function(base_size = 12) {
  theme_bw(base_size = base_size) +
    theme(
      panel.border = element_rect(colour = COLOR_INK, fill = NA, linewidth = 0.5),
      panel.background = element_rect(fill = "white"),
      panel.grid.major = element_line(colour = "#e6eef0", linewidth = 0.4),
      panel.grid.minor = element_blank(),
      text = element_text(colour = COLOR_INK), axis.text = element_text(colour = COLOR_INK),
      axis.title = element_text(colour = COLOR_INK), axis.ticks = element_line(colour = COLOR_INK),
      plot.title = element_text(colour = COLOR_INK, face = "bold"),
      plot.subtitle = element_text(colour = "#4a7378", size = rel(0.85)),
      plot.caption = element_text(colour = COLOR_MUTED, hjust = 0, size = rel(0.75)),
      plot.title.position = "plot", plot.caption.position = "plot",
      strip.text.x = element_text(colour = "white", face = "bold"),
      strip.text.y = element_text(colour = "white", face = "bold", angle = 270),
      strip.background = element_rect(colour = COLOR_INK, fill = COLOR_INK, linewidth = 1.5),
      legend.position = "bottom",
      legend.title = element_text(colour = COLOR_INK, face = "bold"),
      legend.text = element_text(colour = COLOR_INK)
    )
}
theme_set(lshtm_theme())
FAMILY_COLS <- c(lognormal = COLOR_MAIN, gamma = COLOR_INK, weibull = "#c9a227",
                 negbinomial = COLOR_ALERT, normal = "#7a5c99")

# ------------------------------- data ----------------------------------------
si_raw <- read_csv(file.path(IN_DIR, "serial_interval_pairs.csv"), show_col_types = FALSE) |>
  mutate(across(c(infector_onset, infectee_onset), as.Date))
inc_raw <- read_csv(file.path(IN_DIR, "incubation_cases.csv"), show_col_types = FALSE) |>
  mutate(across(c(source_onset, last_exposure, onset), as.Date))

# serial interval: first event = infector onset
si_all <- si_raw |>
  transmute(pdate = infector_onset, sdate = infectee_onset, end_first = infector_onset,
            delay = as.integer(sdate - pdate)) |>
  filter(!is.na(delay))

# incubation, last-exposure definition: first event = last exposure
# cut-off (all incubation analyses) = INFECTOR onset on/before CUTOFF, as for the SI
inc_pt_all <- inc_raw |>
  transmute(pdate = last_exposure, sdate = onset, end_first = source_onset,
            delay = as.integer(sdate - pdate)) |>
  filter(!is.na(delay))

# incubation, uniform-window definition: infection uniform in
# [source onset, min(last exposure, contact onset)]; pdate_upr is exclusive (+1 day)
# If the last exposure was BEFORE the source's onset, the window collapses to the
# exposure date (transmission date = last exposure).
inc_win_all <- inc_raw |>
  filter(!is.na(source_onset), !is.na(last_exposure), !is.na(onset)) |>
  mutate(pre_onset_exposure = last_exposure < source_onset,
         win_start = if_else(pre_onset_exposure, last_exposure, source_onset),
         win_end = if_else(pre_onset_exposure, last_exposure, pmin(last_exposure, onset))) |>
  transmute(pdate = win_start, pdate_upr = win_end + 1, sdate = onset, end_first = source_onset,
            pre_onset_exposure,
            delay_from_source = as.integer(sdate - source_onset), # onset - infector onset
            delay = as.integer(sdate - pdate),                 # onset - window start
            delay_from_end = as.integer(sdate - win_end),      # onset - window end
            win_len = as.integer(win_end - win_start))

make_si <- function(neg, cut) {
  lo <- if (neg) SI_NEG_MIN else 0L
  keep <- si_all$delay >= lo & si_all$delay <= SI_MAX & (!cut | si_all$end_first <= CUTOFF)
  keep <- keep %in% TRUE   # NA (e.g. missing infector onset) -> excluded
  list(data = si_all[keep, ], n_excluded = sum(!keep), shift = if (neg) SI_NEG_SHIFT else 0L,
       families = c("lognormal", "gamma", "weibull", "negbinomial", if (neg) "normal"),
       window = FALSE,
       rule = sprintf("SI %d to %d d%s", lo, SI_MAX, if (cut) sprintf("; infector onset <= %s", format(CUTOFF, "%d %b")) else "; no cut-off"))
}
make_inc_pt <- function(cut) {
  keep <- inc_pt_all$delay >= INC_MIN & inc_pt_all$delay <= INC_MAX & (!cut | inc_pt_all$end_first <= CUTOFF)
  keep <- keep %in% TRUE   # NA (e.g. missing infector onset under the cut-off) -> excluded
  list(data = inc_pt_all[keep, ], n_excluded = sum(!keep), shift = 0L,
       families = c("lognormal", "gamma", "weibull", "negbinomial"), window = FALSE,
       rule = sprintf("last exposure -> onset, %d to %d d%s", INC_MIN, INC_MAX,
                      if (cut) sprintf("; infector onset <= %s", format(CUTOFF, "%d %b")) else "; no cut-off"))
}
make_inc_win <- function(cut) {
  n_in <- nrow(inc_raw)
  # infectee onset after infector onset (>= 1 d) and <= 60 d after it; onset after the
  # window start (>= 1 d) and no more than 42 d after the window end (last exposure)
  keep <- inc_win_all$win_len >= 0 & inc_win_all$delay >= 1 &
    inc_win_all$delay_from_source >= 1 & inc_win_all$delay_from_source <= INC_WIN_MAX_FROM_SOURCE &
    inc_win_all$delay_from_end >= 0 & inc_win_all$delay_from_end <= INC_MAX &
    (!cut | inc_win_all$end_first <= CUTOFF)
  keep <- keep %in% TRUE
  list(data = inc_win_all[keep, ], n_excluded = n_in - sum(keep), shift = 0L,
       families = c("lognormal", "gamma", "weibull"), window = TRUE,
       rule = sprintf("infection uniform in [source onset, min(last exposure, onset)] (= last exposure if before source onset)%s",
                      if (cut) sprintf("; infector onset <= %s", format(CUTOFF, "%d %b")) else "; no cut-off"))
}

# cache = folder name (reuses earlier fits where the data/settings are identical)
analyses <- list(
  si_main = c(make_si(neg = TRUE,  cut = TRUE),  list(quantity = "Serial interval", role = "Main",            cache = "si_main")),
  si_s1   = c(make_si(neg = FALSE, cut = FALSE), list(quantity = "Serial interval", role = "S1: no cut-off, no negatives", cache = "serial_interval")),
  si_s2   = c(make_si(neg = TRUE,  cut = FALSE), list(quantity = "Serial interval", role = "S2: no cut-off, negatives",    cache = "si_s2")),
  si_s3   = c(make_si(neg = FALSE, cut = TRUE),  list(quantity = "Serial interval", role = "S3: cut-off, no negatives",    cache = "si_s3")),
  inc_main = c(make_inc_win(cut = TRUE),  list(quantity = "Incubation period", role = "Main",                            cache = "inc_main")),
  inc_s1   = c(make_inc_pt(cut = TRUE),   list(quantity = "Incubation period", role = "S1: last exposure, cut-off",     cache = "inc_s1")),
  inc_s2   = c(make_inc_win(cut = FALSE), list(quantity = "Incubation period", role = "S2: uniform window, no cut-off", cache = "inc_s2")),
  inc_s3   = c(make_inc_pt(cut = FALSE),  list(quantity = "Incubation period", role = "S3: last exposure, no cut-off",  cache = "incubation"))
)
message("Cut-off: first event on/before ", CUTOFF, " (", CUTOFF_DAYS, " days before ", DATA_CUT, ")")
for (nm in names(analyses)) {
  a <- analyses[[nm]]
  message(sprintf("  %-9s %-34s n = %3d  (%s)", nm, a$role, nrow(a$data), a$rule))
}

# ------------------------------- fitting -------------------------------------
continuous_families <- list(
  lognormal = brms::lognormal(),
  gamma     = stats::Gamma(link = "log"),   # brms has no Gamma(); as in Processing_Code step 1
  weibull   = brms::weibull()
)

cached <- function(path, expr) {
  if (!REFIT && file.exists(path)) {
    out <- tryCatch(readRDS(path), error = function(e) NULL)
    if (!is.null(out)) return(out)
  }
  out <- force(expr)
  saveRDS(out, path)
  out
}

fit_epidist <- function(d, family, window) {
  dat <- d |> mutate(obs_date = DATA_CUT) |> as.data.frame()
  ld <- if (window) {
    epidist::as_epidist_linelist_data(dat, pdate_lwr = "pdate", pdate_upr = "pdate_upr",
                                      sdate_lwr = "sdate", obs_date = "obs_date")
  } else {
    epidist::as_epidist_linelist_data(dat, pdate_lwr = "pdate", sdate_lwr = "sdate", obs_date = "obs_date")
  }
  ld |>
    epidist::as_epidist_marginal_model() |>
    epidist::epidist(formula = mu ~ 1, family = family,
                     chains = CHAINS, cores = CORES, iter = ITER, seed = SEED,
                     backend = BACKEND, refresh = 0)
}

fit_negbin <- function(d) {
  d <- d |> mutate(max_delay = as.integer(DATA_CUT - pdate))  # right truncation bound
  brms::brm(
    brms::bf(delay | trunc(ub = max_delay) ~ 1),
    family = brms::negbinomial(), data = d,
    prior = c(brms::prior(normal(2, 1), class = "Intercept"),        # log mean ~ 7 days
              brms::prior(gamma(2, 0.2), class = "shape")),
    chains = CHAINS, cores = CORES, iter = ITER, seed = SEED, backend = BACKEND, refresh = 0
  )
}

fit_normal <- function(d) {
  d <- d |> mutate(cen = "interval", delay_upr = delay + 1,
                   max_delay = as.integer(DATA_CUT - pdate) + 1)
  brms::brm(
    brms::bf(delay | cens(cen, delay_upr) + trunc(ub = max_delay) ~ 1),
    family = gaussian(), data = d,
    prior = c(brms::prior(normal(20, 15), class = "Intercept"),
              brms::prior(normal(0, 15), class = "sigma")),
    chains = CHAINS, cores = CORES, iter = ITER, seed = SEED, backend = BACKEND, refresh = 0
  )
}

# ------------------------------ LOO per observation --------------------------
find_weights <- function(fit, n_obs) {
  dat <- fit$data
  if (nrow(dat) == n_obs) return(rep(1, n_obs))
  for (cand in c("n", "weight", "weights", "count")) {
    if (cand %in% names(dat) && isTRUE(all.equal(sum(dat[[cand]]), n_obs))) return(dat[[cand]])
  }
  for (cand in names(dat)) {
    v <- dat[[cand]]
    if (is.numeric(v) && all(v >= 1) && all(v == round(v)) && sum(v) == n_obs) return(v)
  }
  stop("Could not find the aggregation weight column in fit$data (columns: ",
       paste(names(dat), collapse = ", "), ")")
}

loo_per_obs <- function(fit, n_obs) {
  ll <- brms::log_lik(fit)
  w <- find_weights(fit, n_obs)
  idx <- rep(seq_along(w), times = w)
  ll_obs <- sweep(ll[, idx, drop = FALSE], 2, w[idx], "/")
  chain_id <- posterior::as_draws_df(fit)$.chain
  loo::loo(ll_obs, r_eff = loo::relative_eff(exp(ll_obs), chain_id = chain_id))
}

# --------------------------- derived quantities ------------------------------
get_draw <- function(dr, patterns) {
  for (p in patterns) {
    hit <- grep(p, names(dr), value = TRUE)
    if (length(hit)) return(dr[[hit[1]]])
  }
  stop("None of ", paste(patterns, collapse = ", "), " found in draws")
}

# natural-scale parameters per draw (epidist dpars are b_<dpar>_Intercept on log scale)
natural_params <- function(fit, fam) {
  dr <- posterior::as_draws_df(fit)
  b0 <- get_draw(dr, c("^b_Intercept$", "^b_mu_Intercept$"))
  switch(fam,
    lognormal   = tibble(meanlog = b0, sdlog = exp(get_draw(dr, c("^b_sigma_Intercept$", "^sigma$")))),
    gamma       = { k <- exp(get_draw(dr, c("^b_shape_Intercept$", "^shape$"))); tibble(shape = k, rate = k / exp(b0)) },
    weibull     = { k <- exp(get_draw(dr, c("^b_shape_Intercept$", "^shape$"))); tibble(shape = k, scale = exp(b0 - lgamma(1 + 1 / k))) },
    negbinomial = tibble(mu = exp(b0), size = get_draw(dr, c("^shape$", "^b_shape_Intercept$"))),
    normal      = tibble(mean = b0, sd = get_draw(dr, c("^sigma$"))),
    stop("unknown family ", fam))
}

dist_fns <- list(
  lognormal   = list(q = function(p, x) qlnorm(p, x$meanlog, x$sdlog),
                     mean = function(x) exp(x$meanlog + x$sdlog^2 / 2),
                     sd = function(x) sqrt(expm1(x$sdlog^2)) * exp(x$meanlog + x$sdlog^2 / 2),
                     cdf = function(v, x) plnorm(v, x$meanlog, x$sdlog), pdist = plnorm,
                     args = function(x) list(meanlog = x$meanlog, sdlog = x$sdlog)),
  gamma       = list(q = function(p, x) qgamma(p, x$shape, x$rate),
                     mean = function(x) x$shape / x$rate,
                     sd = function(x) sqrt(x$shape) / x$rate,
                     cdf = function(v, x) pgamma(v, x$shape, x$rate), pdist = pgamma,
                     args = function(x) list(shape = x$shape, rate = x$rate)),
  weibull     = list(q = function(p, x) qweibull(p, x$shape, x$scale),
                     mean = function(x) x$scale * exp(lgamma(1 + 1 / x$shape)),
                     sd = function(x) x$scale * sqrt(pmax(exp(lgamma(1 + 2 / x$shape)) - exp(2 * lgamma(1 + 1 / x$shape)), 0)),
                     cdf = function(v, x) pweibull(v, x$shape, x$scale), pdist = pweibull,
                     args = function(x) list(shape = x$shape, scale = x$scale)),
  negbinomial = list(q = function(p, x) qnbinom(p, size = x$size, mu = x$mu),
                     mean = function(x) x$mu,
                     sd = function(x) sqrt(x$mu + x$mu^2 / x$size),
                     cdf = function(v, x) pnbinom(floor(v) - 1, size = x$size, mu = x$mu), pdist = NULL, args = NULL),
  normal      = list(q = function(p, x) qnorm(p, x$mean, x$sd),
                     mean = function(x) x$mean, sd = function(x) x$sd,
                     cdf = function(v, x) pnorm(v, x$mean, x$sd), pdist = NULL, args = NULL)
)

ci_txt <- function(v, digits = 2) {
  q <- quantile(v, c(.5, .025, .975), na.rm = TRUE)
  sprintf(paste0("%.", digits, "f (%.", digits, "f-%.", digits, "f)"), q[1], q[2], q[3])
}

summarise_fit <- function(fit, fam, loo_obj, a, key) {
  par <- natural_params(fit, fam); f <- dist_fns[[fam]]; sh <- a$shift
  q <- function(v) quantile(v, c(0.5, 0.025, 0.975), na.rm = TRUE)
  stat <- function(v, nm) setNames(as.list(q(v)), paste0(nm, c("", "_lo", "_hi")))
  diag <- posterior::summarise_draws(posterior::as_draws(fit), "rhat", "ess_bulk")
  n_div <- tryCatch({ np <- brms::nuts_params(fit); sum(np$Parameter == "divergent__" & np$Value > 0) },
                    error = function(e) NA_integer_)
  params <- paste(vapply(names(par), function(p) paste(p, ci_txt(par[[p]], 3)), ""), collapse = "; ")
  if (sh != 0) params <- paste0(params, sprintf("  [fitted to delay + %d]", sh))
  as_tibble(c(
    list(analysis = key, quantity = a$quantity, role = a$role, rule = a$rule, family = fam,
         n = nrow(a$data), n_excluded = a$n_excluded, shift = sh),
    stat(f$mean(par) - sh, "mean"), stat(f$q(0.5, par) - sh, "median"), stat(f$sd(par), "sd"),
    stat(f$q(0.025, par) - sh, "q025"), stat(f$q(0.95, par) - sh, "q95"), stat(f$q(0.975, par) - sh, "q975"),
    list(parameters = params,
         elpd_loo = loo_obj$estimates["elpd_loo", "Estimate"],
         se_elpd_loo = loo_obj$estimates["elpd_loo", "SE"],
         n_pareto_k_high = sum(loo_obj$diagnostics$pareto_k > 0.7),
         max_rhat = max(diag$rhat, na.rm = TRUE), min_ess_bulk = min(diag$ess_bulk, na.rm = TRUE),
         n_divergent = n_div)
  ))
}

# daily probabilities implied by each draw, for plots (on the fitted, shifted scale)
#  - point-primary analyses: double-censored PMF (primarycensored), truncated at D
#  - window analyses: PMF of the delay itself, P(d <= X < d + 1)
pmf_draws <- function(fit, fam, days, D, window) {
  par <- natural_params(fit, fam); f <- dist_fns[[fam]]
  idx <- round(seq(1, nrow(par), length.out = min(N_PLOT_DRAWS, nrow(par))))
  out <- lapply(idx, function(i) {
    x <- par[i, ]
    p <- if (fam == "negbinomial") {
      dnbinom(days, size = x$size, mu = x$mu) / pnbinom(D - 1, size = x$size, mu = x$mu)
    } else if (fam == "normal") {
      (pnorm(days + 1, x$mean, x$sd) - pnorm(days, x$mean, x$sd)) / pnorm(D, x$mean, x$sd)
    } else if (window) {
      f$cdf(days + 1, x) - f$cdf(days, x)
    } else {
      a <- f$args(x)
      tryCatch(do.call(primarycensored::dprimarycensored,
                       c(list(x = days, pdist = f$pdist, pwindow = 1, swindow = 1, D = D), a)),
               error = function(e) (f$cdf(days + 1, x) - f$cdf(days, x)) / f$cdf(D, x))
    }
    tibble(draw = i, day = days, p = p)
  })
  bind_rows(out) |> group_by(day) |>
    summarise(med = median(p), lo = quantile(p, .025), hi = quantile(p, .975), .groups = "drop") |>
    mutate(family = fam)
}

# --------------------------------- run ---------------------------------------
all_summ <- list(); all_cmp <- list(); main_plot <- list()
for (key in names(analyses)) {
  a <- analyses[[key]]
  # fit on the shifted scale: moving the first event earlier by `shift` days
  # adds `shift` to every delay and to the truncation window
  d <- a$data |> mutate(pdate = pdate - a$shift, delay = delay + a$shift)
  message("\n==== ", key, " [", a$quantity, " | ", a$role, "]: n = ", nrow(d), " ====")
  if (nrow(d) < 15) { message("  too few observations, skipping"); next }
  # cache folder is keyed on the exact data + settings, so changed inclusion criteria never
  # silently re-use old fits (old folders are simply ignored)
  sig_file <- tempfile(fileext = ".csv")
  write.csv(cbind(d, .shift = a$shift, .window = a$window, .cut = as.character(DATA_CUT)), sig_file, row.names = FALSE)
  sig <- substr(unname(tools::md5sum(sig_file)), 1, 10)
  out_dir <- file.path(FIT_DIR, paste0(a$cache, "_", sig)); dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
  message("  cache: ", basename(out_dir))

  fits <- list()
  for (fam in intersect(a$families, names(continuous_families))) {
    message("  fitting ", fam, " (epidist", if (a$window) ", uniform primary window", ")")
    fits[[fam]] <- tryCatch(
      cached(file.path(out_dir, paste0(fam, ".rds")), fit_epidist(d, continuous_families[[fam]], a$window)),
      error = function(e) { message("    FAILED: ", conditionMessage(e)); NULL })
  }
  if ("negbinomial" %in% a$families) {
    message("  fitting negbinomial (brms, truncated)")
    fits[["negbinomial"]] <- tryCatch(cached(file.path(out_dir, "negbinomial.rds"), fit_negbin(d)),
                                      error = function(e) { message("    FAILED: ", conditionMessage(e)); NULL })
  }
  if ("normal" %in% a$families) {
    message("  fitting normal (brms, interval-censored, truncated)")
    fits[["normal"]] <- tryCatch(cached(file.path(out_dir, "normal.rds"), fit_normal(d)),
                                 error = function(e) { message("    FAILED: ", conditionMessage(e)); NULL })
  }
  fits <- Filter(Negate(is.null), fits)
  if (!length(fits)) next

  loos <- lapply(names(fits), function(fam)
    cached(file.path(out_dir, paste0(fam, "_loo_obs.rds")), loo_per_obs(fits[[fam]], nrow(d))))
  names(loos) <- names(fits)

  summ <- bind_rows(lapply(names(fits), function(fam) summarise_fit(fits[[fam]], fam, loos[[fam]], a, key)))
  if (length(loos) > 1) {
    cmp <- unclass(loo::loo_compare(loos))
    cmp_tab <- tibble(analysis = key, family = rownames(cmp),
                      elpd_diff = as.numeric(cmp[, "elpd_diff"]), se_diff = as.numeric(cmp[, "se_diff"]),
                      elpd_loo = as.numeric(cmp[, "elpd_loo"]), se_elpd_loo = as.numeric(cmp[, "se_elpd_loo"]))
  } else {
    cmp_tab <- tibble(analysis = key, family = names(loos), elpd_diff = 0, se_diff = 0,
                      elpd_loo = summ$elpd_loo, se_elpd_loo = summ$se_elpd_loo)
  }
  summ <- summ |> left_join(cmp_tab |> select(family, elpd_diff, se_diff), by = "family") |>
    arrange(desc(elpd_diff))
  print(summ |> select(family, n, mean, mean_lo, mean_hi, median, sd, q95, elpd_diff, se_diff, max_rhat, n_divergent))
  all_summ[[key]] <- summ; all_cmp[[key]] <- cmp_tab

  # ---- plot: observed vs fitted daily probabilities (original scale)
  days <- 0:(max(d$delay) + 5)
  D <- max(as.integer(DATA_CUT - d$pdate)) + 1
  pm <- bind_rows(lapply(names(fits), function(fam) pmf_draws(fits[[fam]], fam, days, D, a$window)))
  obs <- if (a$window) {
    # infection date unknown: show onset minus window midpoint as an approximate observed delay
    d |> mutate(day = floor(delay - (pmax(as.integer(pdate_upr - pdate) - 1L, 0L)) / 2)) |> count(day) |> mutate(prop = n / sum(n))
  } else {
    d |> count(day = delay) |> mutate(prop = n / sum(n))
  }
  pm <- pm |> mutate(day = day - a$shift); obs <- obs |> mutate(day = day - a$shift)
  if (a$role == "Main") main_plot[[key]] <- list(pm = pm, obs = obs, a = a, summ = summ)
  # fitted daily probabilities of the primary family for the main analyses (used by Figure 4, 03_figures.py)
  if (a$role == "Main" && PRIMARY_FAMILY %in% pm$family) {
    write_csv(pm |> filter(family == PRIMARY_FAMILY) |> select(day, med, lo, hi),
              file.path(TAB_DIR, paste0("fitted_pmf_main_", if (a$quantity == "Serial interval") "serial_interval" else "incubation", ".csv")))
  }
  lab <- summ |> transmute(family, strip = sprintf("%s%s\nmean %.1f d (%.1f-%.1f); dELPD %.1f (SE %.1f)",
                                                   family, if_else(family == PRIMARY_FAMILY, " (primary)", ""),
                                                   mean, mean_lo, mean_hi, elpd_diff, se_diff))
  pm <- pm |> left_join(lab, by = "family"); pm$strip <- factor(pm$strip, levels = lab$strip)
  g <- ggplot() +
    geom_col(data = tidyr::crossing(obs, strip = levels(pm$strip)) |> mutate(strip = factor(strip, levels(pm$strip))),
             aes(day + 0.5, prop), fill = COLOR_LIGHT, colour = COLOR_MUTED, width = 1, linewidth = 0.2) +
    geom_ribbon(data = pm, aes(day + 0.5, ymin = lo, ymax = hi, fill = family), alpha = 0.25) +
    geom_line(data = pm, aes(day + 0.5, med, colour = family), linewidth = 0.8) +
    geom_vline(xintercept = 0, colour = COLOR_MUTED, linewidth = 0.3) +
    facet_wrap(~strip, ncol = 2) +
    scale_colour_manual(values = FAMILY_COLS, guide = "none") +
    scale_fill_manual(values = FAMILY_COLS, guide = "none") +
    labs(title = paste0(a$quantity, ": ", a$role),
         subtitle = paste0(sprintf("n = %d; %s; truncation-adjusted at %s", nrow(d), a$rule, format(DATA_CUT, "%d %b %Y")),
                           if (a$shift != 0) sprintf("\nPositive-support families fitted to delay + %d and shifted back", a$shift) else ""),
         x = "Days", y = "Proportion",
         caption = paste0(if (a$window) "Bars: onset minus midpoint of the infection window (approximate). Lines: fitted incubation PMF. " else "Bars: observed. ",
                          "Lines/ribbons: posterior median and 95% CrI. Panels ordered by LOO-ELPD."))
  ggsave(file.path(FIG_ADD, paste0("distribution_fits_", key, ".png")), g,
         width = 9, height = if (length(fits) > 4) 8.5 else 6, dpi = 300, bg = "white")
}

# --------------------------------- outputs -----------------------------------
summ_all <- bind_rows(all_summ) |>
  mutate(converged = max_rhat < 1.05 & min_ess_bulk > 400 &
           (is.na(n_divergent) | n_divergent < 0.01 * CHAINS * ITER / 2))
if (any(!summ_all$converged)) {
  message("\nNOT CONVERGED (dropped from comparisons): ",
          paste(summ_all$analysis[!summ_all$converged], summ_all$family[!summ_all$converged], sep = "/", collapse = ", "))
}
write_csv(summ_all |> mutate(across(where(is.numeric), ~ round(.x, 3))), file.path(TAB_DIR, "distribution_fits_summary.csv"))
write_csv(bind_rows(all_cmp), file.path(TAB_DIR, "distribution_fits_loo_compare.csv"))

fmt <- function(e, l, h) sprintf("%.1f (%.1f-%.1f)", e, l, h)

# manuscript table: primary family, main analyses
main_tab <- summ_all |>
  filter(role == "Main", family == PRIMARY_FAMILY) |>
  transmute(Quantity = quantity, Definition = rule, n,
            `Mean (95% CrI)` = fmt(mean, mean_lo, mean_hi),
            `Median (95% CrI)` = fmt(median, median_lo, median_hi),
            `SD (95% CrI)` = fmt(sd, sd_lo, sd_hi),
            `95th percentile (95% CrI)` = fmt(q95, q95_lo, q95_hi),
            `Gamma parameters (median, 95% CrI)` = parameters,
            converged)
write_csv(main_tab, file.path(TAB_DIR, "distribution_fits_main_gamma.csv"))
message("\nMAIN RESULTS (", PRIMARY_FAMILY, ")"); print(main_tab, width = Inf)

# sensitivity comparison: all converged fits, long format
cmp_long <- summ_all |>
  filter(converged) |>
  select(quantity, role, analysis, family, n, mean, mean_lo, mean_hi, median, median_lo, median_hi, q95, q95_lo, q95_hi, elpd_diff, se_diff) |>
  pivot_longer(c(mean, median, q95), names_to = "stat", values_to = "est") |>
  mutate(lo = case_when(stat == "mean" ~ mean_lo, stat == "median" ~ median_lo, TRUE ~ q95_lo),
         hi = case_when(stat == "mean" ~ mean_hi, stat == "median" ~ median_hi, TRUE ~ q95_hi),
         stat = factor(recode(stat, mean = "Mean", median = "Median", q95 = "95th percentile"),
                       levels = c("Mean", "Median", "95th percentile"))) |>
  select(quantity, role, analysis, family, n, stat, est, lo, hi, elpd_diff, se_diff)
write_csv(cmp_long |> mutate(across(where(is.numeric), ~ round(.x, 2))),
          file.path(TAB_DIR, "distribution_fits_sensitivity_comparison.csv"))

wide <- cmp_long |> filter(family == PRIMARY_FAMILY) |>
  mutate(txt = fmt(est, lo, hi)) |> select(quantity, role, n, stat, txt) |>
  pivot_wider(names_from = stat, values_from = txt) |> arrange(quantity, role)
message("\nSENSITIVITY (", PRIMARY_FAMILY, ")"); print(wide, n = Inf, width = Inf)

# figures: primary family, main vs sensitivity analyses -- one figure per quantity
role_levels <- rev(c("Main", "S1: no cut-off, no negatives", "S2: no cut-off, negatives", "S3: cut-off, no negatives",
                     "S1: last exposure, cut-off", "S2: uniform window, no cut-off", "S3: last exposure, no cut-off"))
sens_caption <- c(
  `Serial interval` = paste0("Main: SI -5 to 60 d, infector onset on/before ", format(CUTOFF, "%d %b %Y"),
                             ". Negatives: SI from -5 d (positive-support families fitted to SI + ", SI_NEG_SHIFT, "). ",
                             "Truncation adjustment at ", format(DATA_CUT, "%d %b %Y"), " kept in all fits."),
  `Incubation period` = paste0("Main: infection uniform between infector onset and the earlier of last exposure and infectee onset; ",
                               "infector onset on/before ", format(CUTOFF, "%d %b %Y"), ". Last exposure: exposure date taken as infection date. ",
                               "Truncation adjustment kept in all fits."))
for (q in c("Serial interval", "Incubation period")) {
  gdat <- cmp_long |> filter(family == PRIMARY_FAMILY, quantity == q) |>
    mutate(role = factor(role, levels = role_levels), is_main = role == "Main",
           lab = paste0(as.character(role), "  (n=", n, ")"))
  if (!nrow(gdat)) next
  g_cmp <- ggplot(gdat, aes(est, role, colour = is_main)) +
    geom_vline(data = gdat |> filter(is_main), aes(xintercept = est), colour = COLOR_INK, linetype = "dotted", linewidth = 0.4) +
    geom_pointrange(aes(xmin = lo, xmax = hi), size = 0.35, linewidth = 0.7) +
    facet_wrap(~stat, scales = "free_x", nrow = 1) +
    scale_colour_manual(values = c(`TRUE` = COLOR_INK, `FALSE` = COLOR_ALERT), guide = "none") +
    scale_y_discrete(labels = setNames(gdat$lab, gdat$role)) +
    labs(title = paste0(q, ": main vs sensitivity analyses"),
         subtitle = paste0(tools::toTitleCase(PRIMARY_FAMILY), " fits; posterior median and 95% CrI. Dotted line = main analysis."),
         x = "Days", y = NULL, caption = stringr::str_wrap(sens_caption[[q]], 150))
  ggsave(file.path(FIG_DIR, if (q == "Serial interval") "figS7_serial_interval_sensitivity.png" else "figS8_incubation_sensitivity.png"),
         g_cmp, width = 10, height = 3.6, dpi = 300, bg = "white")
}

# distribution families compared on the MAIN-analysis data only (LOO is only valid on identical data)
fam_tab <- summ_all |>
  filter(role == "Main") |>
  transmute(Quantity = quantity, Family = paste0(family, if_else(family == PRIMARY_FAMILY, " (primary)", "")), n,
            `Mean (95% CrI)` = fmt(mean, mean_lo, mean_hi),
            `Median (95% CrI)` = fmt(median, median_lo, median_hi),
            `95th percentile (95% CrI)` = fmt(q95, q95_lo, q95_hi),
            `dELPD (SE)` = sprintf("%.1f (%.1f)", elpd_diff, se_diff),
            converged) |>
  arrange(Quantity, desc(as.numeric(sub(" .*", "", `dELPD (SE)`))))
write_csv(fam_tab, file.path(TAB_DIR, "distribution_fits_families_main.csv"))
message("\nFAMILIES (main analysis data)"); print(fam_tab, width = Inf)

if (length(main_plot)) {
  pm_all <- bind_rows(lapply(main_plot, function(x) x$pm |> mutate(quantity = x$a$quantity))) |>
    semi_join(summ_all |> filter(role == "Main", converged) |> select(quantity, family), by = c("quantity", "family"))
  obs_all <- bind_rows(lapply(main_plot, function(x) x$obs |> mutate(quantity = x$a$quantity)))
  lab_all <- summ_all |> filter(role == "Main", converged) |>
    arrange(quantity, desc(elpd_diff)) |>
    group_by(quantity) |>
    summarise(txt = paste(sprintf("%-11s mean %4.1f  median %4.1f  95th %4.1f  dELPD %5.1f (%.1f)",
                                  family, mean, median, q95, elpd_diff, se_diff), collapse = "\n"), .groups = "drop")
  g_fam <- ggplot() +
    geom_col(data = obs_all, aes(day + 0.5, prop), fill = COLOR_LIGHT, colour = COLOR_MUTED, width = 1, linewidth = 0.2) +
    geom_ribbon(data = pm_all |> filter(family == PRIMARY_FAMILY), aes(day + 0.5, ymin = lo, ymax = hi), fill = COLOR_INK, alpha = 0.15) +
    geom_line(data = pm_all, aes(day + 0.5, med, colour = family, linewidth = family == PRIMARY_FAMILY)) +
    geom_text(data = lab_all, aes(x = Inf, y = Inf, label = txt), hjust = 1.02, vjust = 1.2, family = "mono", size = 2.4, colour = COLOR_INK) +
    geom_vline(xintercept = 0, colour = COLOR_MUTED, linewidth = 0.3) +
    facet_wrap(~quantity, scales = "free", ncol = 1) +
    scale_colour_manual(values = FAMILY_COLS, name = "Family") +
    scale_linewidth_manual(values = c(`TRUE` = 1.1, `FALSE` = 0.6), guide = "none") +
    labs(title = "Serial interval and incubation period: distribution families compared",
         subtitle = "Main-analysis data. Lines: posterior median daily probability (ribbon: 95% CrI for the primary family, gamma).",
         x = "Days", y = "Proportion",
         caption = stringr::str_wrap(paste0("dELPD = difference in LOO expected log predictive density from the best-fitting family (0 = best); ",
                          "differences < ~2 SE are not meaningful. Incubation bars: onset minus midpoint of the infection window (approximate). ",
                          "Negative binomial cannot use an infection window and normal only allows for negative serial intervals, so neither is fitted for incubation. ",
                          "Weibull fits that did not converge are not shown."), 140))
  ggsave(file.path(FIG_DIR, "figS6_distribution_families.png"), g_fam, width = 9, height = 8, dpi = 300, bg = "white")
}
message("\nDone.")
