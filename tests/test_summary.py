import base64
import json
import re
from prior_auth_checker import summarize_fhir_record

def concept(text):
    return {"text": text}

def make_record():
    """Helper function that returns a small bundle with one of each resource the summary handles. Its latest date is
    2026-03-01, so with the default 2-year lookback the window starts 2024-03-01."""
    note = base64.b64encode(b"Patient reports loud snoring and daytime sleepiness.").decode()
    resources = [
        {"resourceType": "Patient", "id": "p1", "gender": "female", "birthDate": "1956-05-10"},
        #conditions are always included, however old
        {"resourceType": "Condition", "id": "old-condition", "code": concept("Hypertension"),
         "clinicalStatus": concept("Active"), "onsetDateTime": "2010-01-01"},
        {"resourceType": "MedicationRequest", "id": "active-med", "status": "active",
         "medicationCodeableConcept": concept("Lisinopril"), "authoredOn": "2025-01-01"},
        {"resourceType": "MedicationRequest", "id": "stopped-med", "status": "stopped",
         "medicationCodeableConcept": concept("Zolpidem"), "authoredOn": "2025-02-01"},
        #encounters are only included inside the window
        {"resourceType": "Encounter", "id": "old-visit", "type": [concept("Checkup")],
         "period": {"start": "2020-06-01"}},
        {"resourceType": "Encounter", "id": "new-visit", "type": [concept("Sleep evaluation")],
         "class": {"code": "AMB"}, "period": {"start": "2026-01-15"}},
        #four of the same measurement: only the latest three are kept
        *[{"resourceType": "Observation", "id": f"epworth-{i}", "code": concept("Epworth score"),
           "effectiveDateTime": f"2025-0{i}-01", "valueQuantity": {"value": 10 + i, "unit": "{score}"}}
          for i in range(1, 5)],
        {"resourceType": "DiagnosticReport", "id": "sleep-report", "code": concept("Sleep study"),
         "conclusion": "AHI 14 events per hour.", "effectiveDateTime": "2026-02-01"},
        {"resourceType": "DiagnosticReport", "id": "lab-panel", "code": concept("Lipid panel"),
         "effectiveDateTime": "2026-02-01"},
        {"resourceType": "DocumentReference", "id": "note", "date": "2026-03-01", "author": [{"display": "Dr. Lee"}],
         "content": [{"attachment": {"data": note}}]},
        #billing records are left out
        {"resourceType": "Claim", "id": "claim", "created": "2026-03-01"},
    ]
    return {"resourceType": "Bundle", "entry": [{"resource": r} for r in resources]}

def test_patient_line_uses_the_latest_date():
    """Tests that the patient's age is as of the record's latest date, and the window runs 2 years back from it"""
    summary, _ = summarize_fhir_record(make_record())
    assert "PATIENT: female, age 69 as of 2026-03-01" in summary
    assert "cover 2024-03-01 to 2026-03-01" in summary

def test_lookback_window():
    """Tests that old encounters are left out, but old conditions are kept"""
    summary, refs = summarize_fhir_record(make_record())
    assert "Sleep evaluation" in summary and "Checkup" not in summary
    assert "Hypertension" in summary
    assert "old-visit" not in refs.values()

def test_longer_lookback_includes_older_encounters():
    summary, _ = summarize_fhir_record(make_record(), lookback_years=10)
    assert "Checkup" in summary

def test_only_active_medications():
    summary, _ = summarize_fhir_record(make_record())
    assert "Lisinopril" in summary and "Zolpidem" not in summary

def test_skipped_types_are_left_out():
    _, refs = summarize_fhir_record(make_record())
    assert "claim" not in refs.values()

def test_latest_three_values_per_measurement():
    """Tests that repeated measurements share one line, with only the latest three values"""
    summary, refs = summarize_fhir_record(make_record())
    [line] = [line for line in summary.splitlines() if line.startswith("Epworth score:")]
    assert line.count("[R") == 3
    assert "2025-01-01" not in line and "2025-04-01: 14 {score}" in line
    assert "epworth-1" not in refs.values()

def test_reports_need_a_conclusion():
    """Tests that a report with written findings is included, and a lab panel without one is not"""
    summary, _ = summarize_fhir_record(make_record())
    assert "Sleep study: AHI 14 events per hour." in summary
    assert "Lipid panel" not in summary

def test_notes_are_decoded():
    summary, _ = summarize_fhir_record(make_record())
    assert "note by Dr. Lee:\nPatient reports loud snoring and daytime sleepiness." in summary

def test_every_tag_points_to_its_resource():
    """Tests that the tags in the summary are numbered in order, and refs maps each one to a resource id"""
    summary, refs = summarize_fhir_record(make_record())
    tags = re.findall(r"\[(R\d+)\]", summary)
    assert tags == [f"R{i}" for i in range(1, len(tags) + 1)]
    assert set(tags) == set(refs)
    ids = {entry["resource"]["id"] for entry in make_record()["entry"]}
    assert set(refs.values()) <= ids

def test_reads_a_file_path(tmp_path):
    """Tests that a path to a bundle gives the same summary as the parsed bundle"""
    path = tmp_path / "patient.json"
    path.write_text(json.dumps(make_record()), encoding="utf-8")
    assert summarize_fhir_record(path) == summarize_fhir_record(make_record())
