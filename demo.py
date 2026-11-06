"""The demo: five of the evaluation's test patients and five orders that visitors pick from, instead of uploading a
record. Uploads are off unless ALLOW_UPLOADS=1 (see main.py), so no real patient data reaches the deployed site, and
every patient/order result is judged ahead of time by this script, so the site never calls the model:

    python demo.py             #copies the demo patients and judges every combination without a current result
    python demo.py --rejudge   #judges every combination again

Patients, answer keys and results are saved in data/demo/, which is committed (unlike the other test cases), so a
deployed copy has them. A result is out of date once the model, prompts or schema change, or the patient file is
rebuilt; tests/test_demo.py fails until this script is run again.
"""
import argparse
import json
import shutil
from pathlib import Path

from evaluate import cases_path, file_fingerprint, load_answer_keys, pipeline_fingerprint
from prior_auth_checker import summarize_fhir_record, judge_criteria

demo_path = Path(__file__).parent / "data" / "demo"

#each was judged right in all 5 evaluation runs; together they cover every decision for both tested orders
PATIENTS = {
    "case_005": "Obstructive sleep apnea (AHI 14) with daytime sleepiness",
    "case_004": "Obstructive sleep apnea (AHI 14) with no daytime symptoms",
    "case_030": "Moderate to severe sleep apnea, unable to tolerate CPAP",
    "case_035": "Moderate to severe sleep apnea, unable to tolerate CPAP, sleep study from over two years ago",
    "case_042": "Moderate to severe sleep apnea, unable to tolerate CPAP, sleep study without a central apnea count",
}
#tested: the orders the evaluation's test cases were built for (E0470 and E0471 have only a few cases each)
ORDERS = {
    "E0601": {"label": "CPAP device", "tested": True},
    "64582": {"label": "Hypoglossal nerve stimulator implant", "tested": True},
    "E0470": {"label": "Bi-level PAP device, without backup rate", "tested": False},
    "E0471": {"label": "Bi-level PAP device, with backup rate", "tested": False},
    "E1390": {"label": "Oxygen concentrator", "tested": False},
}

def patient_path(case_id):
    return demo_path / "patients" / f"{case_id}.json"

def answer_key(case_id):
    return json.loads((demo_path / "patients" / f"{case_id}_answer_key.json").read_text(encoding="utf-8"))

def result_path(case_id, order):
    return demo_path / "results" / f"{case_id}_{order}.json"

def is_current(result, case_id):
    """Whether a saved result was judged on this patient file with this pipeline (model, prompts, schema)"""
    return (result.get("patient_file_sha256") == file_fingerprint(patient_path(case_id))
            and result.get("pipeline_sha256") == pipeline_fingerprint())

def cached_result(case_id, order):
    """The saved result for a demo patient and order, or None if there isn't one. The site shows it even if it's out
    of date, rather than calling the model."""
    path = result_path(case_id, order)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

def copy_patients():
    """Copies each demo patient's file and answer key from the built test cases, named by case id. Skipped where the
    test cases aren't built, so the committed copies are used as they are."""
    if not cases_path.exists():
        return
    (demo_path / "patients").mkdir(parents=True, exist_ok=True)
    for key in load_answer_keys(list(PATIENTS)):
        shutil.copyfile(cases_path / key["patient_file"], patient_path(key["case_id"]))
        key["patient_file"] = patient_path(key["case_id"]).name
        (demo_path / "patients" / f"{key['case_id']}_answer_key.json").write_text(
            json.dumps(key, indent=2, ensure_ascii=False), encoding="utf-8")

def build(rejudge=False):
    """Judges every patient/order combination that has no current result, and saves the results"""
    copy_patients()
    (demo_path / "results").mkdir(parents=True, exist_ok=True)
    for case_id in PATIENTS:
        summary, refs = summarize_fhir_record(patient_path(case_id))
        for order in ORDERS:
            saved = cached_result(case_id, order)
            if saved and is_current(saved, case_id) and not rejudge:
                continue
            print(f"Judging {case_id} with {order}...")
            result = judge_criteria(summary, order, refs) | {
                "patient_file_sha256": file_fingerprint(patient_path(case_id)), "pipeline_sha256": pipeline_fingerprint()}
            result_path(case_id, order).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  {result['selected_policy']}: {result['decision']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copy the demo patients and judge every patient/order combination.")
    parser.add_argument("--rejudge", action="store_true", help="judge every combination again, even if current")
    build(parser.parse_args().rejudge)
