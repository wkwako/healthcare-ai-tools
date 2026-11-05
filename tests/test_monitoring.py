import sqlite3
from datetime import date
import pytest
import analyze_monitoring
import monitoring
from monitoring import validate_bundle, patient_profile, log_request, record_feedback

TODAY = date(2026, 6, 1)

def make_bundle(birth="1955-03-02", gender="male", extra=()):
    """Helper function that returns a minimal valid bundle: one patient and one condition about them"""
    patient = {"resourceType": "Patient", "id": "p1", "gender": gender, "birthDate": birth, "address": [{"state": "MA"}]}
    condition = {"resourceType": "Condition", "id": "c1", "subject": {"reference": "urn:uuid:p1"},
                 "onsetDateTime": "2025-01-15T10:00:00Z"}
    return {"resourceType": "Bundle", "entry": [{"resource": r} for r in (patient, condition, *extra)]}

@pytest.fixture(autouse=True)
def temporary_db(tmp_path, monkeypatch):
    """Points the monitoring database at a temporary file, so tests never touch data/monitoring.db"""
    monkeypatch.setattr(monitoring, "db_path", tmp_path / "monitoring.db")

def test_valid_bundle_passes():
    """Tests that a minimal, valid bundle has no errors or warnings"""
    assert validate_bundle(make_bundle(), TODAY) == ([], [])

def test_not_a_bundle_fails():
    """Tests that JSON that isn't a FHIR Bundle is an error"""
    errors, _ = validate_bundle({"resourceType": "Patient"}, TODAY)
    assert errors

def test_missing_patient_fails():
    """Tests that a bundle without a Patient resource is an error"""
    bundle = make_bundle()
    bundle["entry"] = bundle["entry"][1:]
    errors, _ = validate_bundle(bundle, TODAY)
    assert errors

def test_future_birth_date_fails():
    """Tests that a birth date after today is an error"""
    errors, _ = validate_bundle(make_bundle(birth="2030-01-01"), TODAY)
    assert errors

def test_future_resource_warns():
    """Tests that a resource dated after today is a warning, but the record can still be judged"""
    later = {"resourceType": "Observation", "id": "o1", "subject": {"reference": "urn:uuid:p1"},
             "effectiveDateTime": "2027-01-01"}
    errors, warnings = validate_bundle(make_bundle(extra=[later]), TODAY)
    assert not errors
    assert any("in the future" in w for w in warnings)

def test_other_patient_reference_warns():
    """Tests that a resource about a different patient is a warning"""
    stranger = {"resourceType": "Observation", "id": "o1", "subject": {"reference": "Patient/p2"},
                "effectiveDateTime": "2025-02-01"}
    _, warnings = validate_bundle(make_bundle(extra=[stranger]), TODAY)
    assert any("different patient" in w for w in warnings)

def test_profile_is_de_identified():
    """Tests that the profile holds an age band and state, not the birth date or id"""
    profile = patient_profile(make_bundle())
    assert profile == {"gender": "male", "age_band": "65-69", "state": "MA", "resource_count": 2}

def test_age_band_groups_90_and_older():
    """Tests that ages 90 and over share one band, as HIPAA Safe Harbor requires"""
    assert monitoring.age_band(89) == "85-89"
    assert monitoring.age_band(97) == "90+"

def test_feedback_is_saved_once():
    """Tests that feedback is saved on a logged request, and a second submission doesn't overwrite it"""
    request_id = log_request({"status": "ok", "order_code": "E0601", "validation_warnings": []})
    assert record_feedback(request_id, "unsure")
    assert not record_feedback(request_id, "correct")
    with sqlite3.connect(monitoring.db_path) as conn:
        assert conn.execute("SELECT feedback FROM requests WHERE id = ?", (request_id,)).fetchone() == ("unsure",)

def test_unknown_feedback_is_rejected():
    """Tests that a feedback value other than the buttons' isn't saved"""
    request_id = log_request({"status": "ok", "order_code": "E0601"})
    assert not record_feedback(request_id, "<script>")

def test_new_columns_are_added_to_an_old_table():
    """Tests that a database made before a column was added gets the column, and keeps its rows"""
    with sqlite3.connect(monitoring.db_path) as conn:
        conn.execute("CREATE TABLE requests (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL)")
        conn.execute("INSERT INTO requests (created_at, status) VALUES ('2026-01-01', 'ok')")
    assert log_request({"status": "ok", "criteria": [{"criterion": "I.A", "verdict": "met"}]}) == 2

def test_wrong_criteria_lists_disagreements():
    """Tests that analysis finds the test-case criteria whose verdict didn't match the answer key"""
    log_request({"status": "ok", "test_case": "case_001", "order_code": "E0601", "scored_criteria": [
        {"criterion": "I.A", "expected": "met", "got": "met"},
        {"criterion": "I.B", "expected": "not met", "got": "met"}]})
    wrong = analyze_monitoring.wrong_criteria()
    assert wrong[["criterion", "expected", "got"]].values.tolist() == [["I.B", "not met", "met"]]

def test_no_feedback_on_failed_requests():
    """Tests that feedback can't be given on a request that has no decision"""
    request_id = log_request({"status": "invalid order", "order_code": "XYZ"})
    assert not record_feedback(request_id, "correct")
