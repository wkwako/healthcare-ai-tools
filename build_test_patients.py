"""Builds and validates every test case in cases.py.

    python build_test_patients.py

Each case names its policy family; FAMILIES maps that name to the module with the family's levers, timeline and
verdict rules. To add a family: write <family>_cases.py with a build_case(case_id, base_patient, **levers)
that returns case_builder.save_case(...), add it here, and add cases with that policy to cases.py.
"""
from collections import Counter

import pap_cases
from case_builder import validate_case
from cases import CASES

FAMILIES = {
    "pap": pap_cases,
}

def build_all(cases):
    """Builds and validates each case, printing one line per case; returns the answer keys"""
    keys = []
    decisions = Counter()
    for case in cases:
        settings = dict(case)
        family = settings.pop("policy")
        if family not in FAMILIES:
            raise ValueError(f"{case['case_id']}: unknown policy family {family!r} (known: {', '.join(FAMILIES)})")
        key = FAMILIES[family].build_case(**settings)
        problems = validate_case(key)
        decisions[key["expected_decision"] or "policy only"] += 1
        status = "OK" if not problems else "PROBLEMS: " + "; ".join(problems)
        print(f"{key['case_id']} {family:4} {key['order']['code']} {str(key['expected_decision']):26} {status}")
        keys.append(key)
    print(dict(decisions))
    return keys

if __name__ == "__main__":
    build_all(CASES)
