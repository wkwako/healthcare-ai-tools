"""Every test case, built by build_test_patients.py. Each case is a policy family, a case id, a base patient,
and the lever settings that differ from that family's defaults.

Base patients (living, 65+, no sleep diagnosis):
  Asia282 (F 67), Denisha680 (F 76), Fernando603 (M 66), Franklin857 (M 74), Guy979 (M 65), Iraida50 (F 69),
  Kendrick479 (M 95), Nathaniel596 (M 69), Peter292 (M 67), Shalanda398 (F 77)
Asia282, Guy979 and Peter292 already have COPD.

policy="pap" (pap_cases.py, L33718). Anything not listed uses build_case()'s default, which is a fully qualifying
E0601 case except that the supplier's instruction (I.C) is not recorded:
  order="E0601", diagnosis="OSA", visit="before", ahi=22, sleep_hours=6.5, test_type="Type I",
  symptoms="daytime sleepiness", test_ordered=True, supplier_instruction=False, cpap_trial=None,
  test_performer="sleep center"
Only Nathaniel596 and Peter292 have no condition that counts as an I.B.2 symptom, so only they can be used with
symptoms=None.

policy="hgns" (hgns_cases.py, L38307 family; the held-out policy). The defaults are a fully qualifying case:
  bmi=29.5, psg="recent", central=8, ahi=32, cpap="intolerant", sdm=True, dise="no collapse", tonsils=1, screen="clear"
Base patients must have no condition that could be a contraindication (build_case() checks), so these are younger
adults without heart, lung, neurological or pregnancy history; age (Covered Indications.1) comes from the patient.
"""

CASES = [
    # ---- PAP (L33718) ----

    # Baselines
    {"policy": "pap", "case_id": "case_001", "base_patient": "Shalanda398"},  #the original case: everything met except I.C (insufficient)
    {"policy": "pap", "case_id": "case_002", "base_patient": "Denisha680", "supplier_instruction": True},  #all met: covered

    # I.B: sleep test score
    {"policy": "pap", "case_id": "case_003", "base_patient": "Fernando603", "ahi": 15, "test_type": "Type III", "supplier_instruction": True},  #boundary, met
    {"policy": "pap", "case_id": "case_004", "base_patient": "Nathaniel596", "ahi": 14, "symptoms": None, "supplier_instruction": True},  #5-14, no symptoms: not met
    {"policy": "pap", "case_id": "case_005", "base_patient": "Iraida50", "ahi": 14, "supplier_instruction": True},  #5-14 with sleepiness: met
    {"policy": "pap", "case_id": "case_006", "base_patient": "Asia282", "ahi": 5, "symptoms": "hypertension", "supplier_instruction": True},  #boundary with hypertension: met
    {"policy": "pap", "case_id": "case_007", "base_patient": "Peter292", "ahi": 4, "symptoms": None, "supplier_instruction": True},  #boundary below 5: not met
    {"policy": "pap", "case_id": "case_008", "base_patient": "Franklin857", "ahi": 15, "sleep_hours": 1.8, "supplier_instruction": True},  #27 events: not met
    {"policy": "pap", "case_id": "case_009", "base_patient": "Kendrick479", "ahi": None, "supplier_instruction": True},  #no AHI recorded: insufficient

    # I.A: evaluation before the test
    {"policy": "pap", "case_id": "case_010", "base_patient": "Guy979", "visit": "after", "supplier_instruction": True},  #not met
    {"policy": "pap", "case_id": "case_011", "base_patient": "Shalanda398", "visit": "telehealth", "supplier_instruction": True},  #not met
    {"policy": "pap", "case_id": "case_012", "base_patient": "Denisha680", "visit": None, "supplier_instruction": True},  #insufficient

    # Sleep Tests.1 and .4: test type and order
    {"policy": "pap", "case_id": "case_013", "base_patient": "Fernando603", "test_type": "oximetry", "ahi": None, "supplier_instruction": True},  #not met
    {"policy": "pap", "case_id": "case_014", "base_patient": "Nathaniel596", "test_type": None, "ahi": 25, "supplier_instruction": True},  #type unstated: insufficient
    {"policy": "pap", "case_id": "case_015", "base_patient": "Iraida50", "test_ordered": False, "supplier_instruction": True},  #no order: insufficient

    # E0470 and II.D: CPAP tried and failed
    {"policy": "pap", "case_id": "case_016", "base_patient": "Asia282", "order": "E0470", "cpap_trial": "failed", "supplier_instruction": True},  #covered
    {"policy": "pap", "case_id": "case_017", "base_patient": "Franklin857", "order": "E0470", "cpap_trial": "succeeded", "supplier_instruction": True},  #not met
    {"policy": "pap", "case_id": "case_018", "base_patient": "Kendrick479", "order": "E0470", "supplier_instruction": True},  #E0470 ordered at diagnosis, no CPAP history: insufficient

    # E0471 and the diagnosis
    {"policy": "pap", "case_id": "case_019", "base_patient": "Guy979", "order": "E0471"},  #excluded for OSA: denied
    {"policy": "pap", "case_id": "case_020", "base_patient": "Peter292", "diagnosis": "COPD", "ahi": 3, "symptoms": None, "supplier_instruction": True},  #E0601 for COPD: denied
    {"policy": "pap", "case_id": "case_021", "base_patient": "Asia282", "order": "E0470", "diagnosis": "COPD", "ahi": 2},  #L33800 governs: policy selection only

    # Combinations
    {"policy": "pap", "case_id": "case_022", "base_patient": "Denisha680", "visit": "after"},  #not met + insufficient: denied
    {"policy": "pap", "case_id": "case_023", "base_patient": "Fernando603", "order": "E0470", "cpap_trial": "failed", "visit": "telehealth"},  #denied
    {"policy": "pap", "case_id": "case_024", "base_patient": "Nathaniel596", "ahi": 9, "symptoms": None, "test_ordered": False},  #not met + insufficient: denied
    {"policy": "pap", "case_id": "case_025", "base_patient": "Shalanda398", "order": "E0470", "cpap_trial": "failed", "ahi": 31, "test_type": "Type III"},  #only I.C missing
    {"policy": "pap", "case_id": "case_026", "base_patient": "Peter292", "ahi": 18, "test_type": "Type IV", "supplier_instruction": True},  #home test: covered

    # Sleep Tests.4 when the treating practitioner (a sleep physician) also runs the test
    {"policy": "pap", "case_id": "case_027", "base_patient": "Kendrick479", "test_performer": "treating", "supplier_instruction": True},  #ordered and run by them: covered
    {"policy": "pap", "case_id": "case_028", "base_patient": "Guy979", "test_performer": "treating", "test_ordered": False, "supplier_instruction": True},  #ran it, no order: insufficient
    {"policy": "pap", "case_id": "case_029", "base_patient": "Franklin857", "test_performer": "treating", "test_ordered": False, "test_type": "Type III", "supplier_instruction": True},  #home test, no order: insufficient

    # ---- Hypoglossal nerve stimulation (L38307 family): the held-out policy ----

    # Baselines
    {"policy": "hgns", "case_id": "case_030", "base_patient": "Arla414"},  #CPAP intolerance: covered
    {"policy": "hgns", "case_id": "case_031", "base_patient": "Delmer311", "cpap": "failed"},  #CPAP failure: covered
    {"policy": "hgns", "case_id": "case_032", "base_patient": "Ed239", "ahi": 65, "central": 24, "bmi": 34.9},  #22, boundaries: covered

    # One criterion not met
    {"policy": "hgns", "case_id": "case_033", "base_patient": "Chandra831"},  #age 20: denied
    {"policy": "hgns", "case_id": "case_034", "base_patient": "Matthew562", "bmi": 36.2},  #BMI (and Limitations.3): denied
    {"policy": "hgns", "case_id": "case_035", "base_patient": "Cornell131", "psg": "old"},  #PSG over 24 months before: denied
    {"policy": "hgns", "case_id": "case_036", "base_patient": "Ellsworth48", "central": 32},  #central apneas (and Limitations.3): denied
    {"policy": "hgns", "case_id": "case_037", "base_patient": "Lenard338", "ahi": 70},  #AHI above 65: denied
    {"policy": "hgns", "case_id": "case_038", "base_patient": "Stanley702", "cpap": "tolerated"},  #CPAP works: denied
    {"policy": "hgns", "case_id": "case_039", "base_patient": "Eliseo499", "dise": "collapse"},  #complete concentric collapse: denied
    {"policy": "hgns", "case_id": "case_040", "base_patient": "Fernando603", "tonsils": 3},  #enlarged tonsils: denied
    {"policy": "hgns", "case_id": "case_041", "base_patient": "Nathaniel596", "screen": "heart failure"},  #contraindication: denied

    # Missing evidence
    {"policy": "hgns", "case_id": "case_042", "base_patient": "Jed345", "central": None},  #central share not reported: insufficient
    {"policy": "hgns", "case_id": "case_043", "base_patient": "Marita360", "cpap": None},  #no CPAP history: insufficient
    {"policy": "hgns", "case_id": "case_044", "base_patient": "Asha251", "sdm": False},  #no shared decision making: insufficient
    {"policy": "hgns", "case_id": "case_045", "base_patient": "Shanel903", "dise": None},  #no DISE: insufficient
    {"policy": "hgns", "case_id": "case_046", "base_patient": "Art115", "screen": None, "tonsils": None},  #no screen or airway exam: insufficient

    # Held-out batch 2: built after batch 1's first held-out run, with the builder unchanged. Chosen by a fixed rule
    # rather than by hand, so knowing batch 1's misses couldn't steer the choice: the 3 covered scenarios above x4 and
    # the 13 adult non-covered scenarios once each, interleaved covered/non-covered; patients are the builder-eligible
    # adults not used in batch 1, then batch-1 adults, alphabetically; the age scenario goes to the one unused
    # eligible patient under 22. Report it separately from batch 1.
    {"policy": "hgns", "case_id": "case_047", "base_patient": "Abram53"},  #CPAP intolerance: covered
    {"policy": "hgns", "case_id": "case_048", "base_patient": "Alexander630", "bmi": 36.2},  #BMI (and Limitations.3): denied
    {"policy": "hgns", "case_id": "case_049", "base_patient": "Antoine384", "cpap": "failed"},  #CPAP failure: covered
    {"policy": "hgns", "case_id": "case_050", "base_patient": "Birgit199", "psg": "old"},  #PSG over 24 months before: denied
    {"policy": "hgns", "case_id": "case_051", "base_patient": "Brett333", "ahi": 65, "central": 24, "bmi": 34.9},  #boundaries: covered
    {"policy": "hgns", "case_id": "case_052", "base_patient": "Darin74", "central": 32},  #central apneas (and Limitations.3): denied
    {"policy": "hgns", "case_id": "case_053", "base_patient": "Eilene124"},  #CPAP intolerance: covered
    {"policy": "hgns", "case_id": "case_054", "base_patient": "Kent912", "ahi": 70},  #AHI above 65: denied
    {"policy": "hgns", "case_id": "case_055", "base_patient": "Mitchell808", "cpap": "failed"},  #CPAP failure: covered
    {"policy": "hgns", "case_id": "case_056", "base_patient": "Peter292", "cpap": "tolerated"},  #CPAP works: denied
    {"policy": "hgns", "case_id": "case_057", "base_patient": "Raquel318", "ahi": 65, "central": 24, "bmi": 34.9},  #boundaries: covered
    {"policy": "hgns", "case_id": "case_058", "base_patient": "Reginald96", "dise": "collapse"},  #complete concentric collapse: denied
    {"policy": "hgns", "case_id": "case_059", "base_patient": "Stephan15"},  #CPAP intolerance: covered
    {"policy": "hgns", "case_id": "case_060", "base_patient": "Arla414", "tonsils": 3},  #enlarged tonsils: denied
    {"policy": "hgns", "case_id": "case_061", "base_patient": "Art115", "cpap": "failed"},  #CPAP failure: covered
    {"policy": "hgns", "case_id": "case_062", "base_patient": "Asha251", "screen": "heart failure"},  #contraindication: denied
    {"policy": "hgns", "case_id": "case_063", "base_patient": "Cornell131", "ahi": 65, "central": 24, "bmi": 34.9},  #boundaries: covered
    {"policy": "hgns", "case_id": "case_064", "base_patient": "Delmer311", "central": None},  #central share not reported: insufficient
    {"policy": "hgns", "case_id": "case_065", "base_patient": "Ed239"},  #CPAP intolerance: covered
    {"policy": "hgns", "case_id": "case_066", "base_patient": "Eliseo499", "cpap": None},  #no CPAP history: insufficient
    {"policy": "hgns", "case_id": "case_067", "base_patient": "Ellsworth48", "cpap": "failed"},  #CPAP failure: covered
    {"policy": "hgns", "case_id": "case_068", "base_patient": "Fernando603", "sdm": False},  #no shared decision making: insufficient
    {"policy": "hgns", "case_id": "case_069", "base_patient": "Jed345", "ahi": 65, "central": 24, "bmi": 34.9},  #boundaries: covered
    {"policy": "hgns", "case_id": "case_070", "base_patient": "Lenard338", "dise": None},  #no DISE: insufficient
    {"policy": "hgns", "case_id": "case_071", "base_patient": "Marita360", "screen": None, "tonsils": None},  #no screen or airway exam: insufficient
    {"policy": "hgns", "case_id": "case_072", "base_patient": "Lonny638"},  #age 18: denied
]
