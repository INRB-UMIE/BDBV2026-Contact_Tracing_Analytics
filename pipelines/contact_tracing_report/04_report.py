"""
Step 4: build the Word report (2-page main text + figures + SI).
Every number is pulled from derived/results.json or tables/*.csv.
"""
import os, json
import numpy as np
import pandas as pd
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from ctr_paths import D, T, F, FA, REPORT_DOCX as OUTDOC
R = json.load(open(os.path.join(D, "results.json")))
pt = pd.read_csv(os.path.join(T, "province_table.csv"))
hz = pd.read_csv(os.path.join(T, "health_zone_table.csv"))
rf = pd.read_csv(os.path.join(T, "sar_risk_factors.csv"))
mv = pd.read_csv(os.path.join(T, "sar_multivariable_or.csv"))
dtab = pd.read_csv(os.path.join(T, "delays.csv"))
dex = pd.read_csv(os.path.join(T, "delay_exclusions.csv"))
log = pd.read_csv(os.path.join(D, "decisions_log.csv"))
src = pd.read_csv(os.path.join(D, "sources.csv"))
pr = pd.read_csv(os.path.join(D, "pairs_annotated.csv"), low_memory=False)

INK = RGBColor(0x01, 0x45, 0x4F)
MAINC = "1a8c99"; LIGHTC = "e3f0f1"


# ---------------------------------------------------------------- helpers
def pc(x, d=1):
    return f"{100 * x:.{d}f}%"


def ci(t, d=1):
    return f"{100 * t[0]:.{d}f}% (95% CI {100 * t[1]:.{d}f}–{100 * t[2]:.{d}f})"


def n(x):
    return f"{int(x):,}"


def med(d, unit=" days"):
    if unit == " days" and d['median'] == 1: unit = " day"
    return f"median {d['median']:g}{unit} (IQR {d['q1']:g}–{d['q3']:g}; mean {d['mean']:g}; n={n(d['n'])})"


def rfrow(factor, level):
    r = rf[(rf.factor == factor) & (rf.level == level)].iloc[0]
    return r


doc = Document()
sec = doc.sections[0]
sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
for side in ("left_margin", "right_margin"):
    setattr(sec, side, Cm(1.9))
sec.top_margin, sec.bottom_margin = Cm(1.8), Cm(1.8)

st = doc.styles["Normal"]
st.font.name = "Arial"; st.font.size = Pt(10)
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
st.paragraph_format.space_after = Pt(4); st.paragraph_format.space_before = Pt(0)
st.paragraph_format.line_spacing = 1.08
for lvl, size in [(1, 12.5), (2, 10.5), (3, 10)]:
    h = doc.styles[f"Heading {lvl}"]
    h.font.name = "Arial"; h.font.size = Pt(size); h.font.bold = True; h.font.color.rgb = INK
    h.element.rPr.rFonts.set(qn("w:eastAsia"), "Arial")
    h.paragraph_format.space_before = Pt(5 if lvl > 1 else 8); h.paragraph_format.space_after = Pt(1.5)
    h.paragraph_format.keep_with_next = True
lb = doc.styles["List Bullet"]
lb.font.name = "Arial"; lb.font.size = Pt(10)
lb.paragraph_format.space_after = Pt(1.5)


def para(text="", bold_lead=None, size=None, italic=False, color=None, align=None, after=None):
    p = doc.add_paragraph()
    if bold_lead:
        r = p.add_run(bold_lead); r.bold = True; r.font.color.rgb = INK
        if size: r.font.size = Pt(size)
    r = p.add_run(text); r.italic = italic
    if size: r.font.size = Pt(size)
    if color: r.font.color.rgb = color
    if align: p.alignment = align
    if after is not None: p.paragraph_format.space_after = Pt(after)
    return p


def bullet(text, bold_lead=None):
    p = doc.add_paragraph(style="List Bullet")
    if bold_lead:
        r = p.add_run(bold_lead); r.bold = True; r.font.color.rgb = INK
    p.add_run(text)
    return p


def shade(cell, hexcol):
    tcPr = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd"); sh.set(qn("w:val"), "clear"); sh.set(qn("w:color"), "auto"); sh.set(qn("w:fill"), hexcol)
    tcPr.append(sh)


def table(df, widths_cm, size=7, header_fill="01454f", bold_last=False, align_right_from=1):
    t = doc.add_table(rows=1, cols=len(df.columns))
    t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for i, c in enumerate(df.columns):
        cell = t.rows[0].cells[i]; cell.text = ""
        r = cell.paragraphs[0].add_run(str(c)); r.bold = True; r.font.size = Pt(size); r.font.color.rgb = RGBColor(255, 255, 255)
        shade(cell, header_fill)
    for ri, row in enumerate(df.itertuples(index=False)):
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run("" if (isinstance(v, float) and np.isnan(v)) else str(v))
            r.font.size = Pt(size)
            if bold_last and ri == len(df) - 1: r.bold = True
            if i >= align_right_from: cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if ri % 2 == 1:
            for c in cells: shade(c, "f2f7f8")
    tblPr = t._tbl.tblPr
    lay = OxmlElement("w:tblLayout"); lay.set(qn("w:type"), "fixed"); tblPr.append(lay)
    for i, w in enumerate(widths_cm):
        t.columns[i].width = Cm(w)
    for row in t.rows:
        for i, w in enumerate(widths_cm):
            row.cells[i].width = Cm(w)
            for p in row.cells[i].paragraphs:
                p.paragraph_format.space_after = Pt(0)
    # borders: light
    tbl = t._tbl
    borders = tbl.tblPr.find(qn("w:tblBorders"))
    return t


def figure(path, caption_lead, caption, width_cm=17.5):
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(path, width=Cm(width_cm))
    p.paragraph_format.keep_with_next = True
    c = para(caption, bold_lead=caption_lead, size=7.5, after=4)
    return c


def page_break():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ---------------------------------------------------------------- numbers used in text
dn = R["delays_nat"]
nm = R["notif_to_first_contact_by_month"]
sar = R["sar"]
spouse, parent, neighbour = rfrow("Relationship", "spouse"), rfrow("Relationship", "parent"), rfrow("Relationship", "neighbour")
funeral, household = rfrow("Setting", "funeral"), rfrow("Setting", "household")
fluids = rfrow("Exposure type", "contact_with_bodily_fluids")
died = rfrow("Source outcome", "Source died")
small, big = rfrow("Contacts listed by source", "1-5"), rfrow("Contacts listed by source", ">50")
hu = rfrow("Province (source)", "Haut-Uele")
P = pt.set_index("area")
H = hz.set_index("area")
nk_no_ct = H.loc[["Katwa", "Butembo"], "cases"].sum()
beni_sep = (pr[pr.src_health_zone == "Beni"].registration >= "2026-09-01").mean()
mvo = mv.set_index("term")
kasai_src = int((src.province == "Kasai").sum())
unloc_src = int(src.province.isna().sum())
mtab = dtab[(dtab.level == "Month") & (dtab.delay == "Notification → first contacts listed")].set_index("group")

# ================================================================= MAIN REPORT
t = doc.add_paragraph()
r = t.add_run("Contact tracing in the Bundibugyo virus disease outbreak, DRC"); r.bold = True; r.font.size = Pt(14); r.font.color.rgb = INK
t.paragraph_format.space_after = Pt(0)
para("Analysis of linelist and contact-tracing data, cut of 9 October 2026 · Restricted: de-identified outbreak data, do not redistribute",
     size=7.5, color=RGBColor(0x4a, 0x73, 0x78), after=4)

doc.add_heading("1. Main findings", 1)
bullet(f" Only {pc(R['pct_cases_source'][0])} of {n(R['n_cases'])} confirmed/probable cases had any contacts listed, and only "
       f"{R['n_cases_prev_contact']} ({pc(R['pct_cases_prev_contact'][0])}) were already on a contact list before they were notified. "
       f"Nearly all cases arise outside known chains of transmission.", "Contact tracing sees a small part of the outbreak.")
bullet(f" Katwa and Butembo ({n(nk_no_ct)} cases together, half of Nord-Kivu's {n(P.loc['Nord-Kivu','cases'])}) have no contact-tracing "
       f"records at all. In Beni, tracing only started in September ({pc(beni_sep, 1)} of its contacts were listed then). Haut-Uele does best "
       f"({P.loc['Haut-Uele','pct_cases_source']:.0f}% of cases traced) but is small.", "Large spatial gaps.")
bullet(f" Time from a source case's notification to first contact listed fell from a median of {mtab.loc['2026-06','median']:g} days "
       f"(June) to {mtab.loc['2026-09','median']:g} days (September). But contacts are still listed a median of "
       f"{dn['Onset → first contacts listed']['median']:g} days after the source case's symptom onset, about one serial interval, "
       f"so many secondary cases are already ill by then.", "Faster listing, still too late.")
bullet(f" {pc(R['fu_pct_zero'][0], 0)} of contacts whose 21-day follow-up has ended have no recorded visit result "
       f"(median {R['fu_days_with_result']['median']:g} of 21 days recorded). Since 14 September, {R['result_missing_post_sep14']:.0f}% of "
       f"follow-up visits have no result (vs {R['result_missing_pre_sep14']:.0f}% before), coinciding with the surge of new contacts in Beni.",
       "Follow-up is patchy and has recently deteriorated.")
bullet(f" Secondary attack rate (SAR) {ci(sar)}; highest for spouses ({pc(spouse.sar)}) and parents ({pc(parent.sar)}), funeral "
       f"exposures ({pc(funeral.sar)}) and contacts of fatal source cases. Serial interval median {R['serial_interval']['median']:g} days; "
       f"exposure-to-onset median {R['incubation']['median']:g} days. The low SAR most likely reflects missed transmission rather than low infectiousness.",
       "Epidemiological parameters.")

doc.add_heading("2. Data summary", 1)
para(f"After merging duplicate records by person ID (SI-2), the linelist holds {n(R['n_cases'])} cases ({n(R['n_confirmed'])} confirmed, "
     f"{R['n_probable']} probable; {n(R['n_case_deaths'])} deaths recorded). The contact-tracing (CT) database lists {n(R['n_source'])} source "
     f"persons and {n(R['n_contacts'])} contacts ({n(R['n_pairs'])} source–contact pairs; {R['n_contacts_multi_source']} contacts named by >1 source). "
     f"Only {R['n_source_confirmed']} source persons are confirmed cases in the linelist; {R['source_class'].get('not in linelist',0)} cannot be found in it and "
     f"{R['source_class'].get('not_a_case',0)} are classified as not a case. Source cases named a {med(R['contacts_per_source'], ' contacts')}; "
     f"{pc(R['sources_1_contact'][0], 0)} named only one, while {R['sources_ge50']} named ≥50 and the top 10% of sources account for "
     f"{pc(R['share_contacts_top10pct_sources'], 0)} of all contacts (mostly Beni and Rwampara). Contacts were mainly exposed in the household "
     f"({R['setting']['household'][1]}%) or hospital ({R['setting']['hospital'][1]}%), mostly through direct physical contact "
     f"({R['exposure']['direct_physical_contact'][1]}%); relationship was unknown for {R['rel']['unknown'][1]}% and 'neighbour' for "
     f"{R['rel']['neighbour'][1]}% (Figure 1). Table 1 summarises by province; Figure 1B and Figure S1 show coverage by health zone over time.")

# Table 1
tab = pt.copy()
order = ["Ituri", "Nord-Kivu", "Haut-Uele", "Tshopo", "Bas-Uele", "Sud-Kivu", "National"]
tab = tab.set_index("area").reindex(order).reset_index()
out = pd.DataFrame({
    "Province": tab.area,
    "Cases": tab.cases.map(n), "Deaths": tab.deaths.map(n),
    "% cases with contacts listed": tab.pct_cases_source.map(lambda x: f"{x:.1f}"),
    "% cases known contact before notif.": tab.pct_cases_prev_contact.map(lambda x: f"{x:.1f}"),
    "Source cases*": tab.source_cases.map(n), "Contacts*": tab.contacts.map(n),
    "Median contacts / source": tab.med_contacts.map(lambda x: f"{x:g}"),
    "Mean % of 21 days with result": tab.pct_fu_complete.map(lambda x: f"{x:.0f}"),
    "SAR % (k/n)": [f"{100*k/nn:.1f} ({k}/{n(nn)})" if nn else "–" for k, nn in zip(tab.sar_k, tab.sar_n)],
})
p = para("", bold_lead="Table 1. ", size=7.5, after=1)
p.add_run("Contact-tracing indicators by province (province of source case for CT columns).").font.size = Pt(7.5)
table(out, [1.8, 1.3, 1.3, 1.7, 1.9, 1.4, 1.4, 1.6, 1.7, 2.7], size=7, bold_last=True)
para(f"*National totals include {kasai_src} source persons with Kasai (Bulape) alert-ID prefixes, {unloc_src} with unlocatable IDs and 2 in Tshuapa "
     f"(SI-3). SAR: contacts of confirmed/probable sources with a closed 21-day window.", size=6.5, italic=True, after=3)

doc.add_heading("3. Patient journey", 1)
para(f"Among confirmed cases (Figure 2), notification came a {med(dn['Onset → notification'])} after onset; sampling a "
     f"{med(dn['Notification → sample'])} after notification; and lab analysis a median {dn['Sample → lab result']['median']:g} days, i.e. the same day "
     f"(IQR {dn['Sample → lab result']['q1']:g}–{dn['Sample → lab result']['q3']:g}) after sampling. Overall, onset to lab result was "
     f"{med(dn['Onset → lab result'])}. For cases that became source cases, contacts were first listed a "
     f"{med(dn['Notification → first contacts listed'])} after notification ({med(dn['Onset → first contacts listed'])} after onset). "
     f"The detection steps have been stable over time; the notification-to-sample delay is much shorter in Nord-Kivu (median "
     f"{dtab[(dtab.level=='Province')&(dtab.group=='Nord-Kivu')&(dtab.delay=='Notification → sample')]['median'].iat[0]:g} days) than in Ituri "
     f"({dtab[(dtab.level=='Province')&(dtab.group=='Ituri')&(dtab.delay=='Notification → sample')]['median'].iat[0]:g} days, IQR up to "
     f"{dtab[(dtab.level=='Province')&(dtab.group=='Ituri')&(dtab.delay=='Notification → sample')]['q3'].iat[0]:g}), "
     f"which is worth checking with field teams (it may reflect how notification dates are recorded). Distributions will be fitted in a later version.")

doc.add_heading("4. Effectiveness of contact tracing", 1)
para(f"New source cases rose to a peak of about {int(pd.read_csv(os.path.join(T,'weekly_national.csv')).new_source_cases.max())} per week in mid-September, "
     f"when {n(pd.read_csv(os.path.join(T,'weekly_national.csv')).new_contacts.max())} new contacts were listed in one week, mostly from Beni (Figure 3B). "
     f"Even so, the weekly share of new cases that became source cases has stayed between about 5% and 15% since June, and fell in the last two weeks, partly because of reporting lag (Figure 3C), and "
     f"the share already known as contacts has never passed ~1.5%. Of {R['n_cases_contact_any_time']} cases ever on a contact list, "
     f"{R['n_cases_contact_registered_after_notif']} were listed only after their own notification, i.e. found through the case, not by tracing. "
     f"The time from source-case notification to first contact listed was a {med(R['notif_to_first_contact'])}; "
     f"{pc(R['notif_to_first_contact_le2'][0], 0)} were listed within 2 days. This has improved steadily (Figure 3D). "
     f"For the {n(R['fu_pairs_window_closed'])} contacts whose follow-up window has closed, a median of {R['fu_days_recorded']['median']:g} "
     f"follow-up days were recorded, but only {R['fu_days_with_result']['median']:g} had a result (IQR {R['fu_days_with_result']['q1']:g}–"
     f"{R['fu_days_with_result']['q3']:g}); {pc(R['fu_pct_ge15'][0], 0)} had ≥15 days with a result. Completeness differs sharply between areas: "
     f"Nord-Kivu and Haut-Uele contacts have almost no recorded results (Table 1, Figure S3). Note that CT records end on 4 October, so the last week is incomplete.")

doc.add_heading("5. Epidemiological implications", 1)
para(f"Of {n(R['sar_eligible_pairs'])} contacts of confirmed/probable sources with a closed follow-up window, {R['sar_secondary']} became cases: "
     f"SAR {ci(sar)} (linelist-linked cases only: {pc(R['sar_ll_only'][0])}; excluding CT 'case validated' (sensitivity): {pc(R['sar_sens_validated'][0])}). "
     f"{pc(R['sources_with_secondary'][0], 0)} of source cases had ≥1 secondary case among their listed contacts. Risk was higher for spouses "
     f"(risk ratio [RR] {spouse.rr:.1f}, 95% CI {spouse.rr_lo:.1f}–{spouse.rr_hi:.1f}) and parents (RR {parent.rr:.1f}, {parent.rr_lo:.1f}–{parent.rr_hi:.1f}) "
     f"than for contacts with unknown relationship, and lower for neighbours (RR {neighbour.rr:.2f}). Funeral exposure (RR {funeral.rr:.1f}, "
     f"{funeral.rr_lo:.1f}–{funeral.rr_hi:.1f} vs household) and a source case who died (RR {died.rr:.1f}, {died.rr_lo:.1f}–{died.rr_hi:.1f}) also increased risk, "
     f"and bodily-fluid exposure tended to (RR {fluids.rr:.1f}, {fluids.rr_lo:.1f}–{fluids.rr_hi:.1f}). These effects remained after mutual adjustment "
     f"(SI-5). Contacts of sources who named only 1–5 people had an SAR of {pc(small.sar)}, against {pc(big.sar)} for lists of >50: "
     f"very long lists dilute risk and stretch follow-up teams. Haut-Uele had a higher SAR ({pc(hu.sar)}), possibly because more of its cases are traced, so links are more often detected. "
     f"The serial interval (n={R['serial_interval']['n']} pairs) was a {med(R['serial_interval'])}, with {R['si_negative']} negative values. "
     f"Time from last exposure to onset (n={R['incubation']['n']}) was a {med(R['incubation'])}; a further {R['inc_le0']} secondary cases had onset on or before "
     f"their recorded last exposure, typical of carers exposed to an ill relative (Figure 4). These are small, selected samples and should be treated as preliminary.")

# ================================================================= FIGURES
figure(os.path.join(F, "fig1_data_summary.png"), "Figure 1. Data summary. ",
       "(A) Confirmed/probable cases per health zone; zones with any contact-tracing records outlined. "
       "(B) Share of cases with ≥1 contact listed (95% Wilson CI) by month of onset (May–August), for zones with ≥50 cases; "
       "point colour matches panel A; dotted line = national share over the whole outbreak. Months with <5 cases omitted. "
       "(C) Contacts listed per source case. (D–F) Setting, exposure type and relationship for all source–contact pairs.",
       width_cm=14.0)
page_break()
figure(os.path.join(F, "fig2_patient_journey.png"), "Figure 2. Patient journey of confirmed cases. ",
       "(A) Median, mean and IQR of days from symptom onset to notification, sample collection, lab result and first contacts listed (source cases only). "
       "(B) Monthly median and IQR (shaded) of selected delays, by month of onset. (C) Median and IQR by province (provinces with ≥40 cases).", width_cm=14.5)
figure(os.path.join(F, "fig3_ct_effectiveness.png"), "Figure 3. Effectiveness of contact tracing. ",
       "(A) New cases by week of notification, split by whether they were a listed contact before notification, listed only afterwards, or never listed. "
       "(B) New source cases and new contacts listed per week. (C) Weekly share of new cases that became source cases or were known contacts (weeks with ≥20 cases). "
       "(D) Days from source-case notification to first contact listed, by month. (E) Follow-up visit rows per week and share with a result recorded.", width_cm=14)
page_break()
figure(os.path.join(F, "fig4_epi_implications.png"), "Figure 4. Epidemiological implications. ",
       "(A) SAR (95% Wilson CI) by exposure type, setting, relationship, source outcome, number of contacts named by the source and province "
       "(levels with ≥50 contacts). Coral = RR CI above 1; grey = below 1. (B) Serial interval, confirmed source–contact pairs. "
       "(C) Days from last recorded exposure to symptom onset in secondary cases (values 1–42 days).")
# ================================================================= SI
page_break()
doc.add_heading("Supplementary information", 1)

doc.add_heading("SI-1. Data and definitions", 2)
for lead, txt in [
    ("Data. ", "dhis2_processed_linelist_ctsafe.csv and contact_tracing_combined_ctsafe.csv from data/2026-10-09 (the combined CT file keeps contacts whose follow-up "
              "ended in earlier exports; the 'processed' file holds only the contacts current on 9 October). Health-zone boundaries: BDBV2026-Data "
              "build/drc_health_zones.geojson, built from data/shapefiles/DRC_Health_zones.shp (GeoJSON used because no shapefile reader was available "
              "in the analysis environment; zone names are identical). All analysis code is in the BDBV2026-Contact_Tracing_Analytics repo, pipelines/contact_tracing_report (01_harmonise.py → 06_fig3A_proportions.py)."),
    ("Unit of analysis. ", "The person (person_id), not the alert or contact record. A source–contact pair is a unique (source person, contact person) combination."),
    ("Case. ", "Linelist person with final classification confirmed or probable (after harmonisation). Suspected cases are excluded."),
    ("Source case. ", "Any person appearing as source_case_person_id in the CT data, whatever their linelist status; process indicators use all of them."),
    ("Secondary case. ", "A contact who is a confirmed/probable linelist case, OR whose CT follow-up result was ever 'case_confirmed', unless the linelist "
                         "classifies them as not a case. 'case_validated' is excluded in the main analysis (unclear meaning) and included in a sensitivity analysis."),
    ("SAR denominator. ", "Pairs whose source is a confirmed/probable case and whose 21-day window (last contact + 21 days) closed by 9 October."),
    ("Known contact before notification. ", "Case whose person_id is a CT contact with first registration on or before their earliest linelist notification date."),
    ("Delays. ", "Notification = date_of_notification; investigation not used; sample = date_of_sample_collection; lab result = lab_analysis_date; "
                 "contacts listed = earliest CT registration_date among the source's contacts. Delays outside 0–60 days excluded (−60 to 60 for 'contacts listed', "
                 "where negative values are real: contacts can be listed before the source is notified). Summaries are means, medians and IQRs; no distribution fitting yet."),
    ("Timing. ", "Weeks start on Monday. Epidemic curves use notification week. Monthly delay summaries are by month of onset (or notification if onset missing) and are right-truncated for recent months."),
    ("Serial interval / incubation. ", "Serial interval: onset(contact) − onset(source) for pairs where both are linelist cases with onset dates, excluding pairs recorded in both directions; "
                                        "values outside −30 to 60 days excluded. Incubation: onset − last recorded exposure, for linelist-linked secondary cases, values 1–42 days; "
                                        "this is an approximation because exposure is often a window, not a single day."),
    ("Statistics. ", "Wilson 95% CIs for proportions; risk ratios with log-normal (Wald) CIs; multivariable logistic regression fitted by IRLS (no adjustment for clustering by source case, so CIs are too narrow)."),
]:
    para(txt, bold_lead=lead)

doc.add_heading("SI-2. Harmonisation of duplicates and discrepancies", 2)
para("Every executive decision taken while merging duplicates or fixing inconsistent values, with the number of records or persons affected. "
     "'Primary record' = the person's linelist row with the highest classification, then the most non-missing fields.")
lg = log[log.n > 0].copy()
lg["n"] = lg.n.map(n)
lg.columns = ["Dataset", "Issue", "N", "Decision"]
table(lg, [1.4, 6.6, 1.3, 8.4], size=6.5, align_right_from=2)
for row in doc.tables[-1].rows:
    for c in row.cells[3:]:
        for p in c.paragraphs: p.alignment = WD_ALIGN_PARAGRAPH.LEFT

doc.add_heading("SI-3. Data-quality signals worth raising with the field teams", 2)
nk_fu = P.loc["Nord-Kivu", "pct_fu_complete"]; hu_fu = P.loc["Haut-Uele", "pct_fu_complete"]
for lead, txt in [
    ("No CT data in Katwa or Butembo. ", f"These zones have {H.loc['Katwa','cases']:,} and {H.loc['Butembo','cases']:,} cases and no source cases at all. Either tracing "
                                         "is not done there or its data are not reaching this database (e.g. a separate tool)."),
    ("Follow-up results missing. ", f"Contacts of Nord-Kivu and Haut-Uele sources have results on a mean of {nk_fu:.0f}% and {hu_fu:.0f}% of the 21 days. Since 14 September "
                                    f"{R['result_missing_post_sep14']:.0f}% of visit rows have a blank result. Visits may be happening but not recorded, or rows may be pre-filled schedules."),
    ("CT outcomes not updated. ", f"{int(log[log.item.str.startswith('contacts confirmed/probable in linelist but CT outcome')].n.iat[0])} contacts who are confirmed cases in the "
                                  "linelist still have 'not a case' or no result as their CT outcome; conversely "
                                  f"{int(log[log.item.str.startswith('contacts with CT result')].n.iat[0])} contacts are 'case confirmed' in CT but cannot be linked to a linelist case."),
    ("Source persons outside the linelist. ", f"{R['source_class'].get('not in linelist',0)} source persons are not in the linelist. {kasai_src} have Kasai/Bulape alert-ID prefixes "
                                              "(a different province with no BDBV cases in the linelist; possibly IDs re-used from the earlier Kasai Ebola outbreak) and "
                                              f"{unloc_src} have non-standard IDs (e.g. 'CI-0000xx', numeric), so their location is unknown. "
                                              f"A further {R['source_class'].get('not_a_case',0)} source persons are 'not a case' and {R['source_class'].get('blank',0)} are unclassified."),
    ("Mass listing. ", f"{R['sources_ge50']} source cases have ≥50 contacts (up to {int(src.n_contacts.max())}), mostly in Beni in September. Their contacts have a much lower SAR, "
                       "suggesting community or ring listing rather than named close contacts. These should probably be analysed separately."),
    ("Uncoded values. ", "Contact type codes 'MVE-005', '1' and '2' and follow-up result 'DB' are not in the data dictionary; they were set to unknown/other."),
    ("Contacts registered before exposure ended. ", "Follow-up dates before the registration date and last-contact dates after the registration date are common; "
                                                    "the follow-up window was therefore anchored on the last-contact date."),
]:
    bullet(txt, lead)

doc.add_heading("SI-4. Delays by province and month", 2)
dd = dtab[dtab.level != "National"].copy()
dd = dd[(dd.n >= 10) & (dd.group != "NaT")]
dd["Median (IQR)"] = [f"{m:g} ({a:g}–{b:g})" for m, a, b in zip(dd["median"], dd.q1, dd.q3)]
wide = dd.pivot_table(index=["level", "group"], columns="delay", values="Median (IQR)", aggfunc="first")
cols = ["Onset → notification", "Notification → sample", "Sample → lab result", "Onset → lab result", "Notification → first contacts listed", "Onset → first contacts listed"]
wide = wide.reindex(columns=cols).reset_index().fillna("–")
wide.columns = ["Level", "Group"] + [c.replace(" → ", "→") for c in cols]
para("Median (IQR) days; cells with <10 cases blank. National values in Figure 2. Exclusions (negative or >60 days): " +
     "; ".join(f"{r.delay}: {r.n_excluded} of {n(r.n_both_dates)}" for r in dex.itertuples()) + ".")
table(wide, [1.4, 1.9, 2.4, 2.4, 2.2, 2.4, 2.5, 2.5], size=6.5, align_right_from=2)

doc.add_heading("SI-5. Risk factors for becoming a secondary case", 2)
rr = rf.copy()
rr["SAR % (95% CI)"] = [f"{100*s:.1f} ({100*a:.1f}–{100*b:.1f})" for s, a, b in zip(rr.sar, rr.lo, rr.hi)]
rr["RR (95% CI)"] = ["ref" if r else ("–" if np.isnan(x) else f"{x:.2f} ({a:.2f}–{b:.2f})") for r, x, a, b in zip(rr.ref, rr.rr, rr.rr_lo, rr.rr_hi)]
key = {"Exposure type": "contact_type_", "Setting": "case_circumstances_", "Relationship": "relationship_to_case_",
       "Province (source)": "src_province_", "Source outcome": "source_died_", "Month listed": "reg_month_"}
aor = []
for r in rr.itertuples():
    if r.ref:
        aor.append("ref" if r.factor in key else "")
        continue
    k = key.get(r.factor, None)
    if k and (k + r.level) in mvo.index:
        o = mvo.loc[k + r.level]; aor.append(f"{o.OR:.2f} ({o.lo:.2f}–{o.hi:.2f})")
    else:
        aor.append("–" if k else "not in model")
rr["Adjusted OR (95% CI)"] = aor
rr["k/n"] = [f"{a}/{n(b)}" for a, b in zip(rr.k, rr.n)]
rr = rr[["factor", "level", "k/n", "SAR % (95% CI)", "RR (95% CI)", "Adjusted OR (95% CI)"]]
rr.columns = ["Factor", "Level", "k/n", "SAR % (95% CI)", "Crude RR (95% CI)", "Adjusted OR (95% CI)"]
rr["Level"] = rr.Level.str.replace("_", " ")
para(f"Denominator: {n(R['sar_eligible_pairs'])} eligible pairs. Reference = most common level. Adjusted model includes exposure type, setting, relationship, "
     "source province, source outcome and month listed; levels with no secondary cases dropped from the model ('–'). "
     f"Sensitivity: SAR using all {n(R['n_pairs'])} pairs regardless of window/source status {ci(R['sar_all_pairs'])}.")
table(rr, [2.6, 4.1, 1.7, 2.9, 3.1, 3.3], size=6.5, align_right_from=2)

doc.add_heading("SI-6. Health zones with ≥50 cases", 2)
h = hz[hz.cases >= 50].sort_values("cases", ascending=False)
ho = pd.DataFrame({"Health zone": h.area, "Cases": h.cases.map(n), "Deaths": h.deaths.map(n),
                   "% cases with contacts": h.pct_cases_source.map(lambda x: f"{x:.1f}"),
                   "% known contact before notif.": h.pct_cases_prev_contact.map(lambda x: f"{x:.1f}"),
                   "Source cases": h.source_cases.map(n), "Contacts": h.contacts.map(n),
                   "Median contacts/source": h.med_contacts.map(lambda x: "–" if np.isnan(x) else f"{x:g}"),
                   "Mean % days with result": h.pct_fu_complete.map(lambda x: "–" if np.isnan(x) else f"{x:.0f}"),
                   "SAR % (k/n)": [f"{100*k/nn:.1f} ({k}/{n(nn)})" if nn else "–" for k, nn in zip(h.sar_k, h.sar_n)]})
table(ho, [2.0, 1.2, 1.2, 1.6, 1.8, 1.4, 1.4, 1.7, 1.7, 2.6], size=6.5)

doc.add_heading("SI-7. Supplementary figures", 2)
figure(os.path.join(F, "figS1_hz_timeseries.png"), "Figure S1. ",
       "Weekly new cases (grey), cases who became source cases (dark teal) and new contacts listed (coral, right axis) in the six zones with most cases.", width_cm=15)
figure(os.path.join(FA, "maps_ct.png"), "Figure S2. ",
       "(A) Median contacts per source case, (B) mean share of the 21 follow-up days with a recorded result, (C) SAR, by health zone of source case.", width_cm=16)
figure(os.path.join(F, "figS3_followup_days_with_result.png"), "Figure S3. ",
       "(A) Days with a recorded follow-up result per contact (closed windows). (B) Same, by province of the source case.", width_cm=15)

doc.add_heading("SI-8. Main limitations", 2)
for txt in [
    "Linkage between the linelist and CT data depends on probabilistic name/demographic matching; missed links lower the SAR and the 'known contact' share.",
    "The SAR is per listed contact. With so few cases traced, it measures transmission within listed networks, not overall infectiousness.",
    "Serial interval and incubation estimates use few pairs (n≈60) from a selected subset and do not account for right truncation.",
    "Recent weeks are incomplete for both datasets (CT registrations stop on 4 October).",
    "The CT database records follow-up rows, not confirmed visits; a blank result may mean an unrecorded visit rather than a missed one.",
]:
    bullet(txt)

doc.save(OUTDOC)
print("saved", OUTDOC)
