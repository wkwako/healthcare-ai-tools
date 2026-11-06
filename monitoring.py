"""Monitoring for the prior authorization checker: one SQLite row per request to /prior-auth-checker.

Each row records what was asked and what happened, without PHI:
- a de-identified patient profile: gender, 5-year age band, state and resource count. Never names, ids, exact dates
  or the uploaded filename, since Synthea filenames contain the patient's name.
- whether the record passed validation (validate_bundle), and the problems found
- whether the patient was a demo patient (with a precomputed result) or an upload
- the order, the policies retrieval offered, the selected policy, each criterion's verdict, the decision and how long
  the analysis took. Not the model's explanations: in real use they quote dates and values from the record.
- for uploads that are one of the evaluation's test cases, how the result scored against its answer key
- the user's feedback on the decision ("Was this decision right?"), if feedback is enabled

The database is data/monitoring.db, or the path in the MONITORING_DB environment variable.
Set FEEDBACK_ENABLED=0 to turn the feedback buttons off. analyze_monitoring.py reads the database for analysis.
"""
import hashlib
import json
import logging
import os
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from functools import cache
from pathlib import Path

from evaluate import cases_path, file_fingerprint, load_answer_keys, score_against_answer_key
from prior_auth_checker import resource_date

logger = logging.getLogger(__name__)

db_path = Path(os.getenv("MONITORING_DB", Path(__file__).parent / "data" / "monitoring.db"))
FEEDBACK_ENABLED = os.getenv("FEEDBACK_ENABLED", "1") != "0"
#the feedback buttons: the value saved, then the button's label
FEEDBACK_CHOICES = {"correct": "Yes", "incorrect": "No", "unsure": "I don't know"}

CREATE_TABLE = """CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,       --UTC, ISO 8601
    status TEXT NOT NULL,           --ok, invalid choice, invalid order, invalid record or failed
    source TEXT,                    --demo (a demo patient, with a precomputed result) or upload
    demo_patient TEXT,              --the demo patient's case id
    order_code TEXT,
    gender TEXT,
    age_band TEXT,                  --e.g. "65-69"; "90+" for 90 and older, as HIPAA Safe Harbor requires
    state TEXT,
    resource_count INTEGER,
    validation_errors TEXT,         --JSON list: problems that stopped the analysis
    validation_warnings TEXT,       --JSON list: problems the analysis ran despite
    error TEXT,                     --why the analysis failed, for status "failed"
    model TEXT,
    candidates TEXT,                --JSON list of the LCD ids retrieval offered, e.g. ["L33718", "L38307"]
    selected_policy TEXT,
    criteria TEXT,                  --JSON list of {"criterion", "verdict"}, one per criterion the model judged
    decision TEXT,
    criteria_count INTEGER,
    duration_seconds REAL,
    feedback TEXT,                  --correct, incorrect or unsure
    feedback_at TEXT,
    test_case TEXT,                 --the rest are only filled in when the upload is a known test case
    policy_correct INTEGER,
    expected_decision TEXT,
    decision_correct INTEGER,
    criteria_correct INTEGER,
    criteria_scored INTEGER,
    scored_criteria TEXT            --JSON list of {"criterion", "expected", "got"}, one per answer-key criterion
)"""

def connect():
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(CREATE_TABLE)
    #CREATE TABLE IF NOT EXISTS leaves an existing table as it was, so add any columns added to it since
    existing = {row[1] for row in conn.execute("PRAGMA table_info(requests)")}
    for column, kind in re.findall(r"^\s+(\w+) (TEXT|INTEGER|REAL)", CREATE_TABLE, re.M):
        if column not in existing:
            conn.execute(f"ALTER TABLE requests ADD COLUMN {column} {kind}")
    return conn

def log_request(row):
    """Saves one request's row (a dict of column: value) and returns its id. Logging must never break the page,
    so a database error is logged and None is returned instead."""
    row = {"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")} | {
        column: json.dumps(value) if isinstance(value, list) else value for column, value in row.items()}
    #the column names come from this code, never from the user, so it's safe to put them in the SQL
    sql = f"INSERT INTO requests ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})"
    try:
        with closing(connect()) as conn, conn:
            return conn.execute(sql, list(row.values())).lastrowid
    except sqlite3.Error:
        logger.exception("Couldn't save the monitoring row")
        return None

def record_feedback(request_id, feedback):
    """Saves the user's feedback on a request's decision. Each request takes feedback once, so a resubmitted form
    doesn't overwrite it. Returns whether it was saved."""
    if feedback not in FEEDBACK_CHOICES:
        return False
    try:
        with closing(connect()) as conn, conn:
            cursor = conn.execute(
                "UPDATE requests SET feedback = ?, feedback_at = ? WHERE id = ? AND status = 'ok' AND feedback IS NULL",
                (feedback, datetime.now(timezone.utc).isoformat(timespec="seconds"), request_id))
            return cursor.rowcount == 1
    except sqlite3.Error:
        logger.exception("Couldn't save the feedback")
        return False

def age_on(birth, day):
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))

def reference_id(reference):
    """The id a FHIR reference points to: "urn:uuid:abc" and "Patient/abc" both give "abc" """
    return reference.rsplit(":", 1)[-1].rsplit("/", 1)[-1]

def validate_bundle(bundle, today=None):
    """Checks that an upload is a usable FHIR patient bundle. Returns (errors, warnings): an error means the tool
    can't read the record at all, and a warning means it can, but something looks wrong that may affect the result."""
    if not isinstance(bundle, dict) or bundle.get("resourceType") != "Bundle":
        return ["The file isn't a FHIR Bundle."], []
    entries = bundle.get("entry")
    if not isinstance(entries, list) or not entries:
        return ["The bundle has no entries."], []
    resources = [entry.get("resource") if isinstance(entry, dict) else None for entry in entries]
    if not all(isinstance(r, dict) and r.get("resourceType") and r.get("id") for r in resources):
        return ["Some entries are missing a resource, a resource type or an id."], []
    patients = [r for r in resources if r["resourceType"] == "Patient"]
    if len(patients) != 1:
        return [f"The bundle should hold exactly one Patient resource, but it holds {len(patients)}."], []
    patient = patients[0]
    try:
        birth = date.fromisoformat(patient.get("birthDate", ""))
    except (TypeError, ValueError):
        return ["The patient has no valid birth date."], []
    today = today or date.today()
    if birth > today:
        return ["The patient's birth date is in the future."], []
    dates = [d for d in map(resource_date, resources) if d]
    if not dates:
        return ["No resource in the bundle has a date."], []

    warnings = []
    if patient.get("gender") not in ("male", "female", "other", "unknown"):
        warnings.append("The patient has no gender recorded.")
    if patient.get("deceasedDateTime") or patient.get("deceasedBoolean"):
        warnings.append("The patient is recorded as deceased.")
    duplicates = len(resources) - len({r["id"] for r in resources})
    if duplicates:
        warnings.append(f"Resources that share an id with another resource: {duplicates}.")
    #resources should all be about this patient: one pointing at someone else means records were mixed together
    others = sum(1 for r in resources
                 if reference_id((r.get("subject") or r.get("patient") or {}).get("reference", patient["id"])) != patient["id"])
    if others:
        warnings.append(f"Resources that refer to a different patient: {others}.")
    out_of_range = sum(1 for d in dates if d < birth.isoformat() or d > today.isoformat())
    if out_of_range:
        warnings.append(f"Resources dated before the patient's birth or in the future: {out_of_range}.")
    return [], warnings

def age_band(age):
    return "90+" if age >= 90 else f"{age // 5 * 5}-{age // 5 * 5 + 4}"

def patient_profile(bundle):
    """De-identified facts about a validated bundle's patient, for the monitoring row"""
    resources = [entry["resource"] for entry in bundle["entry"]]
    patient = next(r for r in resources if r["resourceType"] == "Patient")
    #age as of the record's latest date, the same date the patient summary uses
    as_of = date.fromisoformat(max(d for d in map(resource_date, resources) if d))
    address = (patient.get("address") or [{}])[0]
    return {"gender": patient.get("gender"), "age_band": age_band(age_on(date.fromisoformat(patient["birthDate"]), as_of)),
            "state": address.get("state"), "resource_count": len(resources)}

@cache
def test_cases():
    """Maps each test case's patient file hash to its answer key. Read once per server start, so restart the server
    after rebuilding cases. Empty where the cases aren't built (they're gitignored, so a deployed copy has none)."""
    if not cases_path.exists():
        return {}
    return {file_fingerprint(cases_path / key["patient_file"]): key for key in load_answer_keys()}

def find_test_case(contents):
    """The answer key of the test case an upload (its raw bytes) is a copy of, or None"""
    return test_cases().get(hashlib.sha256(contents).hexdigest())

def test_case_score(key, order, result):
    """If there's a test case's answer key and the order is the one the case was built for, how the result scored
    against it, as monitoring columns; {} otherwise"""
    if not key or key["order"]["code"] != order:
        return {}
    score = score_against_answer_key(result, key)
    row = {"test_case": key["case_id"], "policy_correct": score["policy"]["correct"]}
    if "decision" in score:     #cases scored on policy selection only have no decision or criteria
        row |= {"expected_decision": score["decision"]["expected"], "decision_correct": score["decision"]["correct"],
                "criteria_correct": score["criteria_correct"], "criteria_scored": len(score["criteria"]),
                "scored_criteria": [{k: c[k] for k in ("criterion", "expected", "got")} for c in score["criteria"]]}
    return row
