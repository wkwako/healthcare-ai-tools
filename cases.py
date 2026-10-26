"""Every test case, built by build_test_patients.py. Each case is a policy family, a case id, a base patient,
and the lever settings that differ from that family's defaults.

Base patients (living, 65+, no sleep diagnosis):
  Asia282 (F 67), Denisha680 (F 76), Fernando603 (M 66), Franklin857 (M 74), Guy979 (M 65), Iraida50 (F 69),
  Kendrick479 (M 95), Nathaniel596 (M 69), Peter292 (M 67), Shalanda398 (F 77)
Asia282, Guy979 and Peter292 already have COPD.

policy="pap" (pap_cases.py, L33718). Anything not listed uses build_case()'s default, which is a fully qualifying
E0601 case except that the supplier's instruction (I.C) is not recorded:
  order="E0601", diagnosis="OSA", visit="before", ahi=22, sleep_hours=6.5, test_type="Type I",
  symptoms="daytime sleepiness", test_ordered=True, supplier_instruction=False, cpap_trial=None
Only Nathaniel596 and Peter292 have no condition that counts as an I.B.2 symptom, so only they can be used with
symptoms=None.
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
    {"policy": "pap", "case_id": "case_018", "base_patient": "Kendrick479", "order": "E0470", "supplier_instruction": True},  #no CPAP history: insufficient

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
]
