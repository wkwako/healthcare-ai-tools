"""Test case family for hypoglossal nerve stimulation (L38307 and the five LCDs with the same criteria), the held-out
policy: its levers, the patient timeline they shape, and the verdict rules that turn lever settings into the answer
key. Shared machinery lives in case_builder.py; the cases themselves are in cases.py with policy="hgns".

Every case tells the same story, with each lever changing one part of it:
  polysomnogram (PSG) -> CPAP trial -> sleep physician's HGNS consultation (the first one) -> surgeon's consultation
  (BMI, airway exam, contraindication screen) -> drug-induced sleep endoscopy (DISE) -> implant order (CPT 64582)
"""
import re
from datetime import date, timedelta

from case_builder import RecordBuilder, concept, iso, load_checklist, decide, decision_explanation, save_case

CHECKLIST_NAME = "L38307"
checklist = load_checklist(CHECKLIST_NAME)

ORDER = "64582"
ORDER_TEXT = "Implantation of hypoglossal nerve neurostimulator system"
CPT = "http://www.ama-assn.org/go/cpt"
SLEEP_PHYSICIAN = {"display": "Sleep medicine physician"}
SURGEON = {"display": "Otolaryngologist (implanting surgeon)"}
TECHNOLOGIST = {"display": "Sleep center technologist"}

PSG_TIMING = ("recent", "old")
CPAP_RESULTS = ("intolerant", "failed", "tolerated", None)
DISE_FINDINGS = ("no collapse", "collapse", None)
SCREENS = ("clear", "heart failure", None)
#conditions that are (or could be read as) contraindications; base patients must have none, so a case's
#contraindication verdict comes only from its levers
CONTRAINDICATIONS = re.compile(r"heart failure|myocardial|arrhythm|atrial fib|chronic obstructive|emphysema|pulmonary hypertension"
                               r"|valv|dystrophy|amyotrophic|sclerosis|parkinson|stroke|cerebrovascular|pregnan|schizo|bipolar"
                               r"|narcolepsy|restless|sleep apnea|epilep|seizure|dementia|alzheimer", re.I)

def exact_age(birth_date, day):
    """Age in whole years on a day, the way the patient summary computes it"""
    birth = date.fromisoformat(birth_date)
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))

def expected_verdicts(age, bmi, psg, central, ahi, cpap, sdm, dise, tonsils, screen):
    """The answer key's verdict and explanation for each criterion, from the lever settings alone"""
    verdicts = {}
    verdicts["Covered Indications.1"] = (("met", f"The patient is {age}, at least 22.") if age >= 22
                                         else ("not met", f"The patient is {age}, under 22."))
    verdicts["Covered Indications.2"] = (("met", f"BMI {bmi} is below 35.") if bmi < 35
                                         else ("not met", f"BMI {bmi} is 35 or more."))
    verdicts["Covered Indications.3"] = {
        "recent": ("met", "The PSG was a few months before the first HGNS consultation, within 24 months."),
        "old": ("not met", "The only PSG was more than 24 months before the first HGNS consultation."),
    }[psg]
    verdicts["Covered Indications.4"] = (
        ("insufficient information", "The PSG reports the AHI but not the share of central and mixed apneas.") if central is None
        else ("met", f"Central and mixed apneas are {central}% of the AHI, under 25%.") if central < 25
        else ("not met", f"Central and mixed apneas are {central}% of the AHI, 25% or more."))
    verdicts["Covered Indications.5"] = (("met", f"AHI {ahi} is within 15 to 65.") if 15 <= ahi <= 65
                                         else ("not met", f"AHI {ahi} is outside 15 to 65."))
    if cpap is None:
        verdicts["Covered Indications.6"] = ("insufficient information", "No CPAP use is recorded, but the record doesn't say a "
                                             "CPAP was never tried.")
    elif cpap == "tolerated":
        verdicts["Covered Indications.6"] = ("not met", "The CPAP download shows regular use with a low residual AHI: neither "
                                             "failure nor intolerance.")
    elif not sdm:
        verdicts["Covered Indications.6"] = ("insufficient information", f"CPAP {'intolerance' if cpap == 'intolerant' else 'failure'} "
                                             "is documented, but no shared decision making conversation is.")
    else:
        verdicts["Covered Indications.6"] = ("met", ("CPAP intolerance (under 4 hours a night, fewer than 5 nights a week)" if cpap == "intolerant"
                                                     else "CPAP failure (residual AHI above 15 despite use)")
                                             + ", with shared decision making documented by the sleep physician and the surgeon.")
    verdicts["Covered Indications.7"] = {
        "no collapse": ("met", "DISE shows no complete concentric collapse at the soft palate."),
        "collapse": ("not met", "DISE shows complete concentric collapse at the soft palate."),
        None: ("insufficient information", "No DISE is recorded."),
    }[dise]
    verdicts["Covered Indications.8"] = (
        ("insufficient information", "No airway exam with tonsil size is documented.") if tonsils is None
        else ("met", f"Tonsils are size {tonsils}; no compromising anatomy.") if tonsils <= 2
        else ("not met", f"Tonsils are size {tonsils}, which would compromise the device."))

    found = ([f"BMI {bmi}"] if bmi >= 35 else []) + ([f"central and mixed apneas {central}% of the AHI"] if central is not None and central >= 25 else []) \
            + (["NYHA class III heart failure"] if screen == "heart failure" else [])
    if found:
        verdicts["Limitations.3"] = ("not met", f"Contraindication present: {', '.join(found)}.")
    elif screen is None:
        verdicts["Limitations.3"] = ("insufficient information", "No contraindication screen is documented.")
    elif central is None:
        verdicts["Limitations.3"] = ("insufficient information", "The screen found no contraindications, but the share of central "
                                     "and mixed apneas (one of them) isn't reported.")
    else:
        verdicts["Limitations.3"] = ("met", "The surgeon's contraindication screen found none.")
    return {cid: verdicts[cid] for cid in checklist["orders"][ORDER]["criteria"]}

def build_case(case_id, base_patient, bmi=29.5, psg="recent", central=8, ahi=32, cpap="intolerant", sdm=True,
               dise="no collapse", tonsils=1, screen="clear"):
    """Copies base_patient (a name like "Arla414"), appends this case's resources, and writes the patient file and
    answer key to data/modified_patient_data. The defaults make a fully qualifying case. Lever settings:
      bmi: BMI at the surgeon's consultation (the latest BMI in the record)
      psg: "recent" (a few months before the first HGNS consultation) or "old" (more than 24 months before; it then
           falls outside the summary's 2-year window, so the consultation note carries its date and results)
      central: central and mixed apneas as a percent of the AHI, or None (not reported)
      ahi: the PSG's AHI
      cpap: "intolerant" (rarely used, under 4 hours), "failed" (residual AHI over 15 despite use), "tolerated"
            (used, working), or None (no CPAP history)
      sdm: whether the sleep physician and the surgeon document shared decision making with the patient
      dise: "no collapse", "collapse" (complete concentric collapse at the soft palate), or None (no DISE)
      tonsils: tonsil size 0-4 on the surgeon's exam, or None (no airway exam documented)
      screen: the surgeon's contraindication screen: "clear", "heart failure" (finds NYHA class III heart failure),
              or None (no screen documented)
    Age comes from the base patient. Returns the answer key."""
    levers = {"bmi": bmi, "psg": psg, "central": central, "ahi": ahi, "cpap": cpap, "sdm": sdm, "dise": dise,
              "tonsils": tonsils, "screen": screen}
    if psg not in PSG_TIMING or cpap not in CPAP_RESULTS or dise not in DISE_FINDINGS or screen not in SCREENS \
            or tonsils not in (0, 1, 2, 3, 4, None):
        raise ValueError(f"{case_id}: unknown lever setting in {levers}")

    record = RecordBuilder(base_patient, case_id)
    if record.conditions(CONTRAINDICATIONS):
        raise ValueError(f"{case_id}: {base_patient} has a possible contraindication "
                         f"({record.conditions(CONTRAINDICATIONS)[0]['code']['coding'][0]['display']})")
    rng, patient = record.rng, record.patient
    evidence = {cid: [] for cid in checklist["orders"][ORDER]["criteria"]}
    def cite(criteria, *resource_ids):
        for cid in criteria:
            evidence[cid].extend(resource_ids)
    pronoun = "She" if patient["gender"] == "female" else "He"
    def age_on(moment):
        return exact_age(patient["birthDate"], moment.date())

    # 1. The polysomnogram, and the OSA diagnosis from it
    night = (record.last_date() + timedelta(days=rng.randint(14, 60))).replace(hour=21, minute=30, second=0)
    morning = night + timedelta(hours=8, minutes=15)
    psg_name = "Attended in-laboratory polysomnography (Type I sleep study)"
    psg_enc = record.encounter(night, 495, psg_name, "Suspected obstructive sleep apnea", "Polysomnography encounter",
                               performer=TECHNOLOGIST)
    sleep_hours = round(rng.uniform(5.8, 7.2), 1)
    events = round(ahi * sleep_hours)
    nadir = rng.randint(76, 86)
    ahi_id = record.observation(psg_enc, morning, "Apnea-hypopnea index (AHI)", f"AHI {ahi}", ahi, "/h")
    central_id = (record.observation(psg_enc, morning, "Central and mixed apneas, percent of total AHI", f"Central and mixed {central}%",
                                     central, "%") if central is not None else None)
    results = [ahi_id] + ([central_id] if central_id else []) + [
        record.observation(psg_enc, morning, "Total sleep time", f"{sleep_hours} hours", sleep_hours, "h"),
        record.observation(psg_enc, morning, "Oxygen saturation nadir during sleep", f"SpO2 nadir {nadir}%", nadir, "%")]
    severity = "Severe" if ahi >= 30 else "Moderate" if ahi >= 15 else "Mild"
    central_text = (f" Central and mixed apneas are {central}% of the total AHI." if central is not None else "")
    psg_summary = f"AHI {ahi} events/hour ({events} events over {sleep_hours} hours of sleep).{central_text}"
    psg_report = record.add({
        "resourceType": "DiagnosticReport", "status": "final", "category": [concept("Sleep study")],
        "code": concept(f"{psg_name} report"), "subject": record.patient_ref,
        "effectivePeriod": {"start": iso(night), "end": iso(morning)},
        "issued": iso(morning + timedelta(days=rng.randint(1, 2), hours=4)),
        "performer": [record.organization], "result": [record.ref(r) for r in results], "encounter": record.ref(psg_enc),
        "conclusion": f"{psg_name}. {severity} obstructive sleep apnea. {psg_summary} SpO2 nadir {nadir}%.",
    }, "Polysomnography report")
    dx_id = record.condition(psg_enc, morning + timedelta(days=2), "Obstructive sleep apnea", "Obstructive sleep apnea diagnosis")

    # 2. The sleep physician's HGNS consultation, the first one, with the CPAP trial's device download
    consult = record.daytime(night + timedelta(days=rng.randint(120, 160) if psg == "recent" else rng.randint(880, 960)))
    consult_enc = record.encounter(consult, 45, "Consultation", "Evaluation for hypoglossal nerve stimulation",
                                   "Sleep medicine HGNS consultation", type_code=None, performer=SLEEP_PHYSICIAN)
    cpap_ids, cpap_text, cpap_short = [], "", ""
    if cpap:
        cpap_start = record.daytime(morning + timedelta(days=rng.randint(14, 28)))
        cpap_ids.append(record.add({
            "resourceType": "Device", "status": "active" if cpap == "tolerated" else "inactive",
            "type": concept("Home continuous positive airway pressure unit (physical object)", "http://snomed.info/sct", "702172008"),
            "patient": record.patient_ref, "manufactureDate": iso(cpap_start - timedelta(days=120)),
            "distinctIdentifier": str(rng.randint(10**7, 10**8)),
        }, "CPAP device"))
        if cpap == "intolerant":
            nights, hours, residual = rng.randint(6, 12), round(rng.uniform(1.5, 3.0), 1), rng.randint(3, 8)
            cpap_text = (f"Started CPAP on {cpap_start.date()}. Despite mask refitting (nasal pillows, then a full-face mask), heated "
                         f"humidification and pressure adjustment, the device download shows use on {nights} of the last 30 nights, "
                         f"averaging {hours} hours on nights used. {pronoun} reports mask discomfort and waking with the mask off, and "
                         f"cannot tolerate CPAP.")
            cpap_short = "intolerant of CPAP despite mask and pressure changes"
        elif cpap == "failed":
            nights, hours, residual = rng.randint(27, 30), round(rng.uniform(5.5, 7.0), 1), rng.randint(17, 28)
            cpap_text = (f"Started CPAP on {cpap_start.date()}. The device download shows use on {nights} of the last 30 nights, "
                         f"averaging {hours} hours a night, but residual AHI remains {residual} events/hour despite pressure "
                         f"retitration and a mask refit. CPAP has failed to control the apnea.")
            cpap_short = "CPAP has failed to control the apnea despite regular use"
        else:
            nights, hours, residual = rng.randint(27, 30), round(rng.uniform(6.0, 7.2), 1), rng.randint(1, 4)
            cpap_text = (f"Started CPAP on {cpap_start.date()}. The device download shows use on {nights} of the last 30 nights, "
                         f"averaging {hours} hours a night, with residual AHI {residual} events/hour. Snoring has resolved and "
                         f"{pronoun.lower()} feels rested, but asks about an implant to avoid wearing a mask.")
            cpap_short = "uses CPAP regularly with good control but would prefer not to wear a mask"
        cpap_ids += [
            record.observation(consult_enc, consult, "CPAP nights used in last 30 days (device download)", f"{nights} of 30 nights", nights, "{nights}"),
            record.observation(consult_enc, consult, "Average CPAP use on nights used (device download)", f"{hours} hours", hours, "h"),
            record.observation(consult_enc, consult, "Residual AHI on CPAP (device download)", f"Residual AHI {residual}", residual, "/h")]
    else:
        cpap_text = f"{pronoun} asks about treatment options for sleep apnea, including an implanted nerve stimulator."
    sdm_text = ("Shared decision making: discussed with the patient the CPAP trial, the remaining options (further CPAP adjustment, an "
                "oral appliance, airway surgery, hypoglossal nerve stimulation) and the risks and benefits of each. "
                + (f"The patient is {cpap_short}, and chooses to pursue HGNS evaluation." if cpap
                   else "The patient chooses to pursue HGNS evaluation.") if sdm else "")
    psg_date = night.date()
    #the tool is for Medicare patients, but younger base patients' Synthea notes name a private insurer, so the new notes
    #state the current coverage in Synthea's wording (Medicare under 65 is through disability)
    coverage = "Patient currently has Medicare." + (" Entitled through disability." if age_on(consult) < 65 else "")
    sleep_note = record.note(consult_enc, consult, f"""
{consult.date()}

# Chief Complaint
Evaluation for hypoglossal nerve stimulation.

# History of Present Illness
{base_patient} is a {age_on(consult)} year-old {patient['gender']} with {severity.lower()} obstructive sleep apnea diagnosed by attended polysomnography on {psg_date}: {psg_summary} {cpap_text}
{coverage}

# Assessment and Plan
Obstructive sleep apnea. {sdm_text} Referred to otolaryngology for evaluation for a hypoglossal nerve stimulator.
""", "Sleep medicine consultation note", author=SLEEP_PHYSICIAN)

    # 3. The surgeon's consultation: BMI, airway exam, contraindication screen
    ent = record.daytime(consult + timedelta(days=rng.randint(14, 35)))
    ent_enc = record.encounter(ent, 40, "Consultation", "Evaluation for hypoglossal nerve stimulator implant",
                               "Otolaryngology HGNS consultation", type_code=None, performer=SURGEON)
    bmi_id = record.observation(ent_enc, ent, "Body mass index (BMI) [Ratio]", f"BMI {bmi}", bmi, "kg/m2", category="vital-signs")
    hf_id = None
    if screen == "heart failure":
        hf_id = record.condition(ent_enc, ent - timedelta(days=rng.randint(400, 1500)), "Chronic heart failure, NYHA class III",
                                 "Heart failure diagnosis")
    exam = (f"Oropharynx: tonsils size {tonsils} (Brodsky scale){', enlarged' if tonsils >= 3 else ''}. Mallampati class II."
            if tonsils is not None else "")
    pregnancy = "not pregnant and not planning pregnancy; " if patient["gender"] == "female" else ""
    screen_text = {
        "clear": ("Contraindication screen: no neuromuscular disease, hypoglossal nerve palsy, severe restrictive or obstructive "
                  "pulmonary disease, pulmonary arterial hypertension, severe valvular heart disease or heart failure; no myocardial "
                  "infarction or severe arrhythmia in the past 6 months; blood pressure controlled; no serious mental illness and no "
                  f"other sleep disorder; {pregnancy}no implanted devices and no anticipated need for MRI; able to operate the sleep "
                  "remote; no condition affecting neurological control of the upper airway."),
        "heart failure": ("Contraindication screen: chronic heart failure, NYHA class III, which is a contraindication to hypoglossal "
                          "nerve stimulation."),
        None: "",
    }[screen]
    ent_sdm = ("Shared decision making: reviewed the CPAP history, the alternatives and the implant's risks and benefits with the "
               "patient, who wishes to proceed." if sdm else "")
    plan = "Drug-induced sleep endoscopy to assess the pattern of airway collapse." if dise else "Plan hypoglossal nerve stimulator implant."
    ent_note = record.note(ent_enc, ent, f"""
{ent.date()}

# Chief Complaint
Evaluation for a hypoglossal nerve stimulator implant, referred by sleep medicine.

# History of Present Illness
{base_patient} is a {age_on(ent)} year-old {patient['gender']} with obstructive sleep apnea, AHI {ahi} on polysomnography from {psg_date}.{' ' + pronoun + ' is ' + cpap_short + '.' if cpap else ''}
{coverage}

# Physical Exam
BMI {bmi} kg/m2. Neck supple, no masses. {exam}

# Assessment and Plan
Obstructive sleep apnea. {screen_text} {ent_sdm} {plan}
""", "Otolaryngology consultation note", author=SURGEON)

    # 4. Drug-induced sleep endoscopy, then the implant order
    order_enc, order_time = ent_enc, ent + timedelta(minutes=40)
    if dise:
        scope = record.daytime(ent + timedelta(days=rng.randint(14, 28)))
        dise_enc = record.encounter(scope, 45, "Drug-induced sleep endoscopy", "Evaluation for hypoglossal nerve stimulator implant",
                                    "DISE encounter", performer=SURGEON)
        dise_proc = record.procedure(dise_enc, scope, 30, "Drug-induced sleep endoscopy", "DISE procedure", performer=SURGEON)
        velum = ("complete concentric collapse at the soft palate" if dise == "collapse" else
                 "partial anteroposterior collapse at the soft palate; no complete concentric collapse")
        dise_report = record.add({
            "resourceType": "DiagnosticReport", "status": "final", "category": [concept("Endoscopy")],
            "code": concept("Drug-induced sleep endoscopy report"), "subject": record.patient_ref,
            "effectiveDateTime": iso(scope), "issued": iso(scope + timedelta(hours=2)), "performer": [SURGEON],
            "encounter": record.ref(dise_enc),
            "conclusion": f"Drug-induced sleep endoscopy. Velum: {velum}. Oropharynx: partial lateral wall collapse. Tongue base: "
                          f"partial anteroposterior collapse. Epiglottis: no collapse.",
        }, "DISE report")
        cite(["Covered Indications.7"], dise_proc, dise_report)
        order_enc, order_time = dise_enc, scope + timedelta(hours=2)
    order_id = record.add({
        "resourceType": "ServiceRequest", "status": "active", "intent": "order",
        "code": concept(ORDER_TEXT, CPT, ORDER), "subject": record.patient_ref, "encounter": record.ref(order_enc),
        "authoredOn": iso(order_time), "requester": SURGEON, "reasonReference": [record.ref(dx_id)],
    }, f"{ORDER} order")

    #evidence: a PSG more than 2 years old isn't in the summary, so the consultation note stands in for its results
    psg_evidence = [psg_report] if psg == "recent" else [sleep_note]
    cite(["Covered Indications.1"], sleep_note, ent_note)
    cite(["Covered Indications.2"], bmi_id, ent_note)
    cite(["Covered Indications.3"], *psg_evidence, consult_enc, sleep_note)
    cite(["Covered Indications.4"], *([central_id] if psg == "recent" else []), *psg_evidence)
    cite(["Covered Indications.5"], *([ahi_id] if psg == "recent" else []), *psg_evidence)
    cite(["Covered Indications.6"], *cpap_ids, sleep_note, *([ent_note] if sdm else []))
    cite(["Covered Indications.8"], ent_note)
    cite(["Limitations.3"], ent_note, *([hf_id] if hf_id else []), *([bmi_id] if bmi >= 35 else []),
         *((([central_id] if psg == "recent" else []) + psg_evidence) if central is not None and central >= 25 else []))

    age = age_on(order_time)
    criteria = {cid: {"verdict": verdict, "evidence": list(dict.fromkeys(evidence[cid])) if verdict != "insufficient information" else [],
                      "explanation": text}
                for cid, (verdict, text) in expected_verdicts(age, bmi, psg, central, ahi, cpap, sdm, dise, tonsils, screen).items()}
    decision = decide(criteria)
    return save_case(record, case_id, {
        "levers": levers,
        "order": {"code": ORDER, "description": ORDER_TEXT, "date": order_time.date().isoformat(), "resource_id": order_id},
        "governing_policies": checklist["family"]["accepted"],
        "accepted_policies": checklist["family"]["accepted"],
        "checklist": f"data/criteria/{CHECKLIST_NAME}.json",
        "criteria": criteria,
        "expected_decision": decision,
        "decision_explanation": decision_explanation(criteria, decision),
    })
