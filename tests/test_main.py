import json
import re
import sqlite3
import pytest
from fastapi.testclient import TestClient
import demo
import main
import monitoring
from main import readable_units, evidence_lines

#the demo patients built for an order the tool was evaluated on, so each has an answer key to check the page against
TESTED = [case_id for case_id in demo.PATIENTS if demo.ORDERS[demo.answer_key(case_id)["order"]["code"]]["tested"]]

client = TestClient(main.app)

@pytest.fixture(autouse=True)
def temporary_db(tmp_path, monkeypatch):
    """Points the monitoring database at a temporary file, so tests never touch data/monitoring.db"""
    monkeypatch.setattr(monitoring, "db_path", tmp_path / "monitoring.db")

def logged_rows():
    with sqlite3.connect(monitoring.db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute("SELECT * FROM requests")]

def check_demo(case_id, order):
    return client.post("/prior-auth-checker/demo", data={"patient": case_id, "order": order})

def test_readable_units():
    """Tests that UCUM annotation units lose their braces, and that a bare count unit is dropped"""
    assert readable_units("Total apnea and hypopnea events: 2026-03-24: 91 {events}") == \
        "Total apnea and hypopnea events: 2026-03-24: 91 events"
    assert readable_units("Number of nights: 3 {#}") == "Number of nights: 3"
    assert readable_units("Heart rate: 72 /min") == "Heart rate: 72 /min"

def test_evidence_lines_keep_the_measurement_name():
    """Tests that each tagged value on an observation line is shown with the measurement's name"""
    lines = evidence_lines("Epworth score: [R4] 2026-01-02: 17 {score}; [R5] 2026-03-01: 12 {score}")
    assert lines == {"R4": "Epworth score: 2026-01-02: 17 score", "R5": "Epworth score: 2026-03-01: 12 score"}

@pytest.mark.parametrize("path", ["/", "/denials-explainer", "/medicare-policy-assistant", "/denial-validator",
                                  "/prior-auth-checker"])
def test_pages_load(path):
    assert client.get(path).status_code == 200

@pytest.mark.parametrize("case_id", TESTED)
def test_demo_shows_the_expected_decision(case_id):
    """Tests that each tested demo patient's page shows the decision in its answer key, and logs it as scored"""
    key = demo.answer_key(case_id)
    page = check_demo(case_id, key["order"]["code"])
    assert page.status_code == 200
    assert main.DECISION_LABELS[key["expected_decision"]] in page.text
    assert "{events}" not in page.text and "{score}" not in page.text
    [row] = logged_rows()
    assert row["status"] == "ok" and row["source"] == "demo" and row["test_case"] == case_id
    assert row["decision_correct"] == 1

def test_monitoring_row_has_no_patient_name():
    """Tests that nothing in a demo request's monitoring row contains the patient's name"""
    case_id = TESTED[0]
    check_demo(case_id, demo.answer_key(case_id)["order"]["code"])
    patient = next(entry["resource"] for entry in json.loads(demo.patient_path(case_id).read_text(encoding="utf-8"))["entry"]
                   if entry["resource"]["resourceType"] == "Patient")
    names = patient["name"][0]["given"] + [patient["name"][0]["family"]]
    [row] = logged_rows()
    assert not any(name in str(value) for name in names for value in row.values())

def test_unknown_demo_choice_is_rejected():
    page = check_demo("case_999", "E0601")
    assert "Pick one of the listed patients and orders." in page.text
    assert logged_rows()[0]["status"] == "invalid choice"

def test_uploads_are_off_by_default(monkeypatch):
    """Tests that the deployed site turns uploads away before reading the file, so no record reaches it"""
    monkeypatch.setattr(main, "ALLOW_UPLOADS", False)
    page = client.post("/prior-auth-checker", data={"order": "E0601"},
                       files={"file": ("patient.json", b"{}", "application/json")})
    assert "Uploads are turned off" in page.text
    assert logged_rows()[0]["status"] == "invalid choice"

def test_feedback_on_a_demo_result_is_saved():
    case_id = TESTED[0]
    page = check_demo(case_id, demo.answer_key(case_id)["order"]["code"])
    request_id = re.search(r'name="request_id" value="(\d+)"', page.text).group(1)
    page = client.post("/prior-auth-checker/feedback", data={"request_id": request_id, "feedback": "unsure"})
    assert "your feedback was saved" in page.text
    assert logged_rows()[0]["feedback"] == "unsure"
