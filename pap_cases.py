"""Test case family for the PAP policy (L33718): its levers, the patient timeline they shape, and the verdict
rules that turn lever settings into the answer key. Shared machinery lives in case_builder.py; the cases
themselves are in cases.py with policy="pap".
"""
import re
from datetime import timedelta

from case_builder import RecordBuilder, SNOMED, concept, iso, load_checklist, decide, decision_explanation, save_case

CHECKLIST_NAME = "L33718"
checklist = load_checklist(CHECKLIST_NAME)

ORDERS = {
    "E0601": "Continuous positive airway pressure (CPAP) device",
    "E0470": "Bi-level respiratory assist device without backup rate",
    "E0471": "Bi-level respiratory assist device with backup rate",
}
#how each test type is described in the record; None means the record never says what kind of test it was
TEST_TYPES = {
    "Type I": {"name": "Attended in-laboratory polysomnography (Type I sleep study)", "home": False, "index": "AHI"},
    "Type II": {"name": "Unattended full polysomnography (Type II sleep study)", "home": True, "index": "AHI"},
    "Type III": {"name": "Home sleep apnea test (Type III, 4-channel)", "home": True, "index": "RDI"},
    "Type IV": {"name": "Home sleep apnea test (Type IV, 3-channel with airflow)", "home": True, "index": "RDI"},
    "oximetry": {"name": "Overnight home pulse oximetry", "home": True, "index": None},
    None: {"name": "Sleep study", "home": None, "index": "AHI"},
}
INDEX_NAMES = {"AHI": "Apnea-hypopnea index (AHI)", "RDI": "Respiratory disturbance index (RDI)"}
VISITS = ("before", "after", "telehealth", None)
SYMPTOMS = ("daytime sleepiness", "hypertension", None)
CPAP_TRIALS = ("failed", "succeeded", None)
#conditions that satisfy I.B.2's list b (or a), so a "no symptoms" case can't use a base patient who has one
SYMPTOM_CONDITIONS = re.compile(r"hypertension|ischemic heart|myocardial|stroke|cerebrovascular|insomnia|depress"
                                r"|bipolar|mood|dementia|alzheimer|cognitive", re.I)
COPD_CONDITIONS = re.compile(r"chronic obstructive|emphysema|chronic bronchitis", re.I)
SUPPLIER = {"display": "Commonwealth Home Respiratory Supply"}

def expected_verdicts(order, diagnosis, visit, ahi, events, test_type, symptoms, test_ordered, supplier_instruction, cpap_trial):
    """The answer key's verdict and explanation for each criterion, from the lever settings alone"""
    verdicts = {}
    verdicts["I.A"] = {
        "before": ("met", "In-person evaluation for OSA by the treating practitioner before the sleep test."),
        "after": ("not met", "The only in-person evaluation for OSA happened after the sleep test."),
        "telehealth": ("not met", "The evaluation before the sleep test was a telehealth (video) visit, not in person."),
        None: ("insufficient information", "No clinical evaluation for OSA is recorded."),
    }[visit]

    index = TEST_TYPES[test_type]["index"] or "AHI"
    if test_type == "oximetry":
        verdicts["I.B"] = ("not met", "The only sleep testing is overnight pulse oximetry, which reports no AHI or RDI.")
    elif ahi is None:
        verdicts["I.B"] = ("insufficient information", "A sleep study is recorded, but no AHI or RDI is.")
    elif ahi >= 15:
        verdicts["I.B"] = ("met", f"Path 1: {index} {ahi} (>= 15) with {events} events (>= 30).") if events >= 30 else \
                          ("not met", f"{index} {ahi} but only {events} events over a short recording; path 1 needs at least 30.")
    elif ahi >= 5:
        if events < 10:
            verdicts["I.B"] = ("not met", f"{index} {ahi} but only {events} events; path 2 needs at least 10.")
        elif symptoms:
            verdicts["I.B"] = ("met", f"Path 2: {index} {ahi} (5-14) with {events} events and documented {symptoms}.")
        else:
            verdicts["I.B"] = ("not met", f"{index} {ahi} (5-14) and the record documents none of the required symptoms or conditions "
                                          "(normal Epworth score, no hypertension, heart disease or stroke).")
    else:
        verdicts["I.B"] = ("not met", f"{index} {ahi} is below 5.")

    verdicts["Sleep Tests.1"] = (("met", f"The study is a {test_type} sleep test, a recognized type.") if test_type in ("Type I", "Type II", "Type III", "Type IV")
                                 else ("not met", "Overnight pulse oximetry is not a recognized sleep test type.") if test_type == "oximetry"
                                 else ("insufficient information", "The record never says what kind of sleep test was done."))
    verdicts["Sleep Tests.3"] = (verdicts["I.B"][0], "Restates I.B: " + verdicts["I.B"][1])
    verdicts["Sleep Tests.4"] = (("met", "The sleep test was ordered by the treating practitioner.") if test_ordered
                                 else ("insufficient information", "No order for the sleep test is recorded."))
    verdicts["I.C"] = (("met", "The supplier's instruction on device use and care is documented.") if supplier_instruction
                       else ("insufficient information", "Nothing shows the supplier instructed the patient; the order was only sent to a supplier."))
    verdicts["II.D"] = {
        "failed": ("met", "A CPAP (E0601) trial is documented as failing despite mask refitting and pressure adjustment."),
        "succeeded": ("not met", "The CPAP (E0601) trial is documented as effective, so it was not proven ineffective."),
        None: ("insufficient information", "No CPAP trial is recorded."),
    }[cpap_trial]
    verdicts["Initial Coverage"] = ("not met", "An E0471 is not covered when the primary diagnosis is OSA.")
    return {cid: verdicts[cid] for cid in checklist["orders"][order]["criteria"]}

def build_case(case_id, base_patient, order="E0601", diagnosis="OSA", visit="before", ahi=22, sleep_hours=6.5,
               test_type="Type I", symptoms="daytime sleepiness", test_ordered=True, supplier_instruction=False,
               cpap_trial=None):
    """Copies base_patient (a name like "Shalanda398"), appends this case's resources, and writes the patient file
    and answer key to data/modified_patient_data. Lever settings:
      order: "E0601", "E0470" or "E0471"
      diagnosis: "OSA", or "COPD" (no OSA diagnosis; needs ahi < 5 or None)
      visit: "before" (in person, before the test), "after", "telehealth", or None (no evaluation recorded)
      ahi, sleep_hours: the AHI/RDI (None = not recorded) and hours slept or recorded; events = ahi * sleep_hours
      test_type: "Type I" to "Type IV", "oximetry" (no AHI; needs ahi=None), or None (type never stated)
      symptoms: "daytime sleepiness" (high Epworth score), "hypertension" (the base patient's, or added), or None
                (normal Epworth score; the base patient must have no qualifying condition)
      test_ordered: whether the treating practitioner's order for the sleep test is recorded
      supplier_instruction: whether the supplier's instruction on device use and care is recorded
      cpap_trial: E0470 only: "failed", "succeeded", or None (no CPAP history)
    Returns the answer key."""
    levers = {"order": order, "diagnosis": diagnosis, "visit": visit, "ahi": ahi, "sleep_hours": sleep_hours,
              "test_type": test_type, "symptoms": symptoms, "test_ordered": test_ordered,
              "supplier_instruction": supplier_instruction, "cpap_trial": cpap_trial}
    if order not in ORDERS or visit not in VISITS or symptoms not in SYMPTOMS or cpap_trial not in CPAP_TRIALS \
            or test_type not in TEST_TYPES or diagnosis not in ("OSA", "COPD"):
        raise ValueError(f"{case_id}: unknown lever setting in {levers}")
    if test_type == "oximetry" and ahi is not None:
        raise ValueError(f"{case_id}: oximetry doesn't produce an AHI; use ahi=None")
    if diagnosis == "COPD" and ahi is not None and ahi >= 5:
        raise ValueError(f"{case_id}: a COPD (non-OSA) case needs ahi < 5 or None")
    if cpap_trial and order != "E0470":
        raise ValueError(f"{case_id}: cpap_trial only applies to E0470")

    record = RecordBuilder(base_patient, case_id)
    if symptoms is None and record.conditions(SYMPTOM_CONDITIONS):
        raise ValueError(f"{case_id}: symptoms=None, but {base_patient} has a qualifying condition "
                         f"({record.conditions(SYMPTOM_CONDITIONS)[0]['code']['coding'][0]['display']})")
    rng, patient = record.rng, record.patient
    evidence = {cid: [] for cid in checklist["orders"][order]["criteria"]}
    def cite(criteria, resource_id):
        for cid in criteria:
            if cid in evidence:
                evidence[cid].append(resource_id)

    start = record.daytime(record.last_date() + timedelta(days=rng.randint(14, 60)))
    epworth = rng.randint(11, 18) if symptoms == "daytime sleepiness" else rng.randint(3, 8)
    pronoun = "She" if patient["gender"] == "female" else "He"
    symptom_text = (f"{pronoun} reports dozing off while reading and watching television. Epworth Sleepiness Scale score is {epworth}."
                    if symptoms == "daytime sleepiness" else
                    f"Denies daytime sleepiness, fatigue, or trouble concentrating. Epworth Sleepiness Scale score is {epworth}.")
    age = record.age_on(start)

    #hypertension for I.B.2: reuse the base patient's diagnosis, or add one dated years back
    symptom_ids = []
    if symptoms == "hypertension":
        existing = record.conditions(re.compile("hypertension", re.I))
        symptom_ids = [existing[0]["id"]] if existing else [record.condition(
            None, start - timedelta(days=rng.randint(800, 4000)), "Essential hypertension", "Hypertension diagnosis")]

    # 1. Evaluation visit before the test (in person or by video), and the sleep test order
    eval_id = None
    order_time = start
    if visit in ("before", "telehealth"):
        telehealth = visit == "telehealth"
        eval_id = record.encounter(start, 40, "Telemedicine consultation with patient" if telehealth else "Encounter for problem (procedure)",
                                   "Snoring and possible sleep apnea", "Evaluation encounter (video)" if telehealth else "In-person evaluation encounter",
                                   setting="VR" if telehealth else "AMB", type_code=None if telehealth else "185347001")
        assessment = record.procedure(eval_id, start, 40, "Sleep apnea assessment (procedure)", "Sleep apnea assessment",
                                      SNOMED, "103750000")
        epworth_id = record.observation(eval_id, start, "Epworth Sleepiness Scale total score", f"Epworth score {epworth}",
                                        integer=epworth, category="survey")
        plan = "Ordered a sleep study." if test_ordered else "Discussed sleep testing."
        eval_note = record.note(eval_id, start, f"""
{start.date()}

# Chief Complaint
Loud snoring and possible pauses in breathing during sleep.

# History of Present Illness
{base_patient} is a {age} year-old {patient['gender']} seen {'by video visit' if telehealth else 'in person'} for evaluation of possible obstructive sleep apnea. A family member reports loud nightly snoring and pauses in breathing during sleep. {symptom_text}

# Physical Exam
{'Exam limited to what was visible on video.' if telehealth else f'BMI {rng.uniform(28, 36):.1f} kg/m2. Neck circumference {rng.randint(15, 18)} inches. Mallampati class {rng.choice(("II", "III", "IV"))} airway. Cardiopulmonary exam unremarkable.'}

# Assessment and Plan
Suspected obstructive sleep apnea. {plan}
""", "Evaluation note")
        cite(["I.A"], eval_id); cite(["I.A"], assessment); cite(["I.A"], eval_note)
        if symptoms == "daytime sleepiness":
            symptom_ids = [epworth_id, eval_note]
        elif symptoms is None:
            symptom_ids = [epworth_id]
        order_time = start + timedelta(minutes=40)

    test_info = TEST_TYPES[test_type]
    sleep_order = None
    if test_ordered:
        sleep_order = record.add({
            "resourceType": "ServiceRequest", "status": "completed", "intent": "order",
            "code": concept(test_info["name"]), "subject": record.patient_ref, "authoredOn": iso(order_time),
            "requester": record.practitioner, "reasonCode": [concept("Suspected obstructive sleep apnea")],
            **({"encounter": record.ref(eval_id)} if eval_id else {}),
        }, "Sleep study order from the treating practitioner")
        cite(["Sleep Tests.4"], sleep_order)

    # 2. The sleep test: an overnight encounter (in a lab, at home, or unstated) with its results and report
    night = (order_time + timedelta(days=rng.randint(7, 21))).replace(hour=21, minute=30, second=0)
    morning = night + timedelta(hours=8, minutes=15)
    setting = "HH" if test_info["home"] else "AMB"
    test_enc = None
    if test_info["home"] is not None:
        test_enc = record.encounter(night, 495, test_info["name"], "Suspected obstructive sleep apnea",
                                    "Overnight sleep test encounter", setting=setting)
    results = []
    index_name = INDEX_NAMES[test_info["index"]] if test_info["index"] else None
    events = round(ahi * sleep_hours) if ahi is not None else None
    time_label = "Total sleep time" if test_info["index"] == "AHI" and test_type else "Total recording time"
    if ahi is not None:
        results.append(record.observation(test_enc, morning, index_name, f"{test_info['index']} {ahi}", ahi, "/h"))
        results.append(record.observation(test_enc, morning, "Total apnea and hypopnea events", f"{events} events", events, "{events}"))
        results.append(record.observation(test_enc, morning, time_label, f"{sleep_hours} hours", sleep_hours, "h"))
    nadir = rng.randint(78, 88)
    results.append(record.observation(test_enc, morning, "Oxygen saturation nadir during sleep", f"SpO2 nadir {nadir}%", nadir, "%"))
    if test_type == "oximetry":
        minutes_low = rng.randint(10, 40)
        results.append(record.observation(test_enc, morning, "Time with oxygen saturation at or below 88%",
                                          f"{minutes_low} minutes at or below 88%", minutes_low, "min"))
        conclusion = f"Overnight pulse oximetry. SpO2 nadir {nadir}%, {minutes_low} minutes at or below 88%. No airflow or effort channels recorded."
    elif ahi is None:
        conclusion = f"{test_info['name']} completed. Scoring summary not included in this report. SpO2 nadir {nadir}%."
    else:
        severity = "Severe" if ahi >= 30 else "Moderate" if ahi >= 15 else "Mild" if ahi >= 5 else "No significant"
        hours_word = "hours of sleep" if time_label == "Total sleep time" else "hours of recording"
        kind = "obstructive sleep apnea" if diagnosis == "OSA" else "obstructive sleep apnea; nocturnal desaturation"
        conclusion = (f"{test_info['name']}. {severity} {kind}. {test_info['index']} {ahi} events/hour "
                      f"({events} events over {sleep_hours} {hours_word}). SpO2 nadir {nadir}%.")
    report = record.add({
        "resourceType": "DiagnosticReport", "status": "final", "category": [concept("Sleep study")],
        "code": concept(f"{test_info['name']} report"),
        "subject": record.patient_ref, "effectivePeriod": {"start": iso(night), "end": iso(morning)},
        "issued": iso(morning + timedelta(days=rng.randint(1, 2), hours=4)),
        "performer": [record.organization], "result": [record.ref(r) for r in results], "conclusion": conclusion,
        **({"encounter": record.ref(test_enc)} if test_enc else {}),
        **({"basedOn": [record.ref(sleep_order)]} if sleep_order else {}),
    }, "Sleep test report")
    cite(["I.B", "Sleep Tests.3"], report)
    for r in results[:2] if ahi is not None else results:
        cite(["I.B", "Sleep Tests.3"], r)
    cite(["Sleep Tests.1"], report)
    if ahi is not None and 5 <= ahi < 15:
        for r in symptom_ids:
            cite(["I.B", "Sleep Tests.3"], r)

    # 3. Follow-up: diagnosis and order (for visit="after", this is also the first evaluation for OSA)
    followup = record.daytime(morning + timedelta(days=rng.randint(5, 14)))
    fu_id = record.encounter(followup, 30, "Encounter for problem (procedure)", "Review of sleep study results",
                             "Follow-up encounter", type_code="185347001")
    if visit == "after":
        assessment = record.procedure(fu_id, followup, 30, "Sleep apnea assessment (procedure)", "Sleep apnea assessment",
                                      SNOMED, "103750000")
        epworth_id = record.observation(fu_id, followup, "Epworth Sleepiness Scale total score", f"Epworth score {epworth}",
                                        integer=epworth, category="survey")
        cite(["I.A"], fu_id); cite(["I.A"], assessment)
        if symptoms == "daytime sleepiness":
            symptom_ids += [epworth_id]
    elif visit is None and symptoms in ("daytime sleepiness", None):
        #no evaluation visit; the symptom score still has to live somewhere for I.B.2
        epworth_id = record.observation(fu_id, followup, "Epworth Sleepiness Scale total score", f"Epworth score {epworth}",
                                        integer=epworth, category="survey")
        symptom_ids += [epworth_id]

    if diagnosis == "OSA":
        dx_id = record.condition(fu_id, followup, "Obstructive sleep apnea", "Obstructive sleep apnea diagnosis")
        dx_text = "obstructive sleep apnea"
    else:
        existing = record.conditions(COPD_CONDITIONS)
        dx_id = existing[0]["id"] if existing else record.condition(
            fu_id, followup, "Chronic obstructive pulmonary disease", "COPD diagnosis")
        dx_text = "nocturnal hypoxemia related to chronic obstructive pulmonary disease, without significant obstructive sleep apnea"
    result_text = conclusion if ahi is not None or test_type == "oximetry" else "The study was completed; the scoring summary is not in the report."

    order_time = followup + timedelta(minutes=30)
    final_enc = fu_id
    if order == "E0470" and cpap_trial:
        #CPAP first; under 3 months, so switching to bi-level needs no new evaluation or sleep test
        first_order = record.device_request(fu_id, order_time, "E0601", ORDERS["E0601"], "completed", dx_id, "E0601 CPAP order (trial)")
        cpap_start = record.daytime(followup + timedelta(days=rng.randint(3, 7)))
        trial_days = rng.randint(35, 70)
        cpap_device = record.add({
            "resourceType": "Device", "status": "inactive",
            "type": concept("Home continuous positive airway pressure unit (physical object)", SNOMED, "702172008"),
            "patient": record.patient_ref, "manufactureDate": iso(cpap_start - timedelta(days=120)),
            "distinctIdentifier": str(rng.randint(10**7, 10**8)),
        }, "CPAP device used for the trial")
        review = record.daytime(cpap_start + timedelta(days=trial_days))
        review_id = record.encounter(review, 30, "Encounter for problem (procedure)", "CPAP trial follow-up",
                                     "CPAP trial review encounter", type_code="185347001")
        if cpap_trial == "failed":
            residual, usage = rng.randint(16, 26), round(rng.uniform(5.0, 6.5), 1)
            trial_text = (f"Started CPAP (E0601) on {cpap_start.date()}. Over {trial_days} days the device download shows average use of "
                          f"{usage} hours per night, but residual AHI remains {residual} events/hour. The mask was refitted (changed to a "
                          f"full-face mask) and pressure was retitrated, without improvement. Symptoms persist. CPAP has failed to meet "
                          f"therapeutic goals despite optimal therapy. Ordered a bi-level device without backup rate (E0470).")
        else:
            residual, usage = rng.randint(1, 4), round(rng.uniform(5.5, 7.0), 1)
            trial_text = (f"Started CPAP (E0601) on {cpap_start.date()}. Over {trial_days} days the device download shows average use of "
                          f"{usage} hours per night with residual AHI {residual} events/hour. Snoring has resolved and the patient feels "
                          f"better rested. The patient asks to try a bi-level device for comfort. Ordered a bi-level device without "
                          f"backup rate (E0470).")
        residual_id = record.observation(review_id, review, "Residual AHI on CPAP (device download)", f"Residual AHI {residual}", residual, "/h")
        usage_id = record.observation(review_id, review, "Average CPAP use per night (device download)", f"{usage} hours per night", usage, "h")
        review_note = record.note(review_id, review, f"""
{review.date()}

# Chief Complaint
Follow-up on CPAP therapy.

# History of Present Illness
{base_patient} is a {age} year-old {patient['gender']} with {dx_text}. {trial_text}
""", "CPAP trial review note")
        for r in (first_order, cpap_device, residual_id, usage_id, review_note):
            cite(["II.D"], r)
        final_enc, order_time = review_id, review + timedelta(minutes=30)

    plan = {
        "E0601": "Ordered a CPAP device (E0601) with heated humidifier and sent the order to a DME supplier.",
        "E0470": ("Will start CPAP (E0601) and reassess." if cpap_trial else
                  "Ordered a bi-level device without backup rate (E0470) and sent the order to a DME supplier."),
        "E0471": "Ordered a bi-level device with backup rate (E0471) and sent the order to a DME supplier.",
    }[order]
    fu_note = record.note(fu_id, followup, f"""
{followup.date()}

# Chief Complaint
Follow-up to review sleep study results.

# History of Present Illness
{base_patient} is a {age} year-old {patient['gender']} returning to review sleep testing from {night.date()}. {result_text}
{'' if visit != 'after' else 'This is the first visit to evaluate the sleep complaints: a family member reports loud snoring and pauses in breathing. ' + symptom_text}

# Assessment and Plan
{dx_text.capitalize()}. {plan}
""", "Follow-up note")
    if visit == "after":
        cite(["I.A"], fu_note)
        if symptoms == "daytime sleepiness":
            symptom_ids.append(fu_note)

    order_id = record.device_request(final_enc, order_time, order, ORDERS[order], "active", dx_id, f"{order} order")
    if supplier_instruction:
        taught = record.daytime(order_time + timedelta(days=rng.randint(2, 6)))
        instruction = record.procedure(None, taught, 45, f"Instruction on use and care of {ORDERS[order].lower()} by DME supplier",
                                       "Supplier instruction on device use and care", performer=SUPPLIER)
        cite(["I.C"], instruction)
    if order == "E0471":
        cite(["Initial Coverage"], dx_id)

    #answer key: verdicts from the levers, evidence from what was actually added
    if diagnosis == "COPD" and order != "E0601":
        accepted, criteria, decision = ["L33800"], {}, None
        explanation = "Not OSA, so the Respiratory Assist Devices LCD governs. It has no checklist yet: scored on policy selection only."
    else:
        accepted = [CHECKLIST_NAME]
        criteria = {cid: {"verdict": verdict, "evidence": evidence[cid] if verdict != "insufficient information" else [],
                          "explanation": text}
                    for cid, (verdict, text) in expected_verdicts(order, diagnosis, visit, ahi, events, test_type, symptoms,
                                                                  test_ordered, supplier_instruction, cpap_trial).items()}
        decision = decide(criteria)
        explanation = decision_explanation(criteria, decision)
    return save_case(record, case_id, {
        "levers": levers,
        "order": {"code": order, "description": ORDERS[order], "date": order_time.date().isoformat(), "resource_id": order_id},
        "governing_policies": accepted,
        "accepted_policies": accepted,
        "checklist": f"data/criteria/{CHECKLIST_NAME}.json",
        "criteria": criteria,
        "expected_decision": decision,
        "decision_explanation": explanation,
    })
