"""Collects the saved eval results into two flat tables of answer key vs prediction. Makes no model calls.

    python collect_results.py              #every case with an answer key
    python collect_results.py case_002     #just these cases

Writes decisions.csv (one row per case) and criteria.csv (one row per answer-key criterion) to
data/eval_results/<model>/, the inputs for a confusion matrix later. Each row has a status:
  current  the result was judged on the patient file as it is now
  stale    the patient file or pipeline (model, prompts, schema) changed since; rerun evaluate.py for this case
  missing  no saved result yet; run evaluate.py for this case
Stale and missing cases are written with their status so they're visible, but should be left out of any metrics.
"""
import argparse
import csv
import json

from evaluate import results_path, run_path, load_answer_keys, is_current
from prior_auth_checker import score_against_answer_key

DECISION_COLUMNS = ["case_id", "status", "order", "accepted_policies", "selected_policy", "policy_correct",
                    "expected_decision", "predicted_decision", "decision_correct", "criteria_correct", "criteria_total"]
CRITERIA_COLUMNS = ["case_id", "status", "order", "criterion", "expected", "predicted", "correct",
                    "evidence_expected", "evidence_cited"]

def load_saved_result(key, run=1):
    """The saved result for a run (see evaluate.run_path) and whether it's current, stale or missing"""
    saved = run_path(run) / f"{key['case_id']}_result.json"
    if not saved.exists():
        return None, "missing"
    result = json.loads(saved.read_text(encoding="utf-8"))
    return result, "current" if is_current(result, key) else "stale"

def collect(keys, run=1):
    decisions, criteria = [], []
    for key in keys:
        result, status = load_saved_result(key, run)
        row = {"case_id": key["case_id"], "status": status, "order": key["order"]["code"],
               "accepted_policies": " ".join(key["accepted_policies"]), "expected_decision": key["expected_decision"]}
        if result is None:
            decisions.append(row)
            continue
        score = score_against_answer_key(result, key)
        row |= {"selected_policy": score["policy"]["selected"], "policy_correct": score["policy"]["correct"]}
        if "decision" in score:  #policy-only cases have no decision or criteria to compare
            row |= {"predicted_decision": score["decision"]["got"], "decision_correct": score["decision"]["correct"],
                    "criteria_correct": score["criteria_correct"], "criteria_total": len(score["criteria"])}
            criteria += [{"case_id": key["case_id"], "status": status, "order": row["order"], "criterion": c["criterion"],
                          "expected": c["expected"], "predicted": c["got"], "correct": c["correct"],
                          "evidence_expected": c["evidence_expected"], "evidence_cited": c["evidence_cited"]}
                         for c in score["criteria"]]
        decisions.append(row)
    return decisions, criteria

def write_csv(path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tabulate saved eval results against the answer keys.")
    parser.add_argument("case_ids", nargs="*", help="cases to include, e.g. case_002 (default: all)")
    args = parser.parse_args()

    decisions, criteria = collect(load_answer_keys(args.case_ids))
    results_path.mkdir(parents=True, exist_ok=True)
    write_csv(results_path / "decisions.csv", DECISION_COLUMNS, decisions)
    write_csv(results_path / "criteria.csv", CRITERIA_COLUMNS, criteria)

    for row in decisions:
        if row["status"] == "missing":
            print(f"{row['case_id']}  {row['order']}  missing")
            continue
        print(f"{row['case_id']}  {row['order']}  {row['status']:7}  policy {row['selected_policy']:7} "
              f"{'OK' if row['policy_correct'] else 'WRONG'}  expected {str(row['expected_decision']):26} "
              f"predicted {str(row.get('predicted_decision')):26} {'' if row.get('decision_correct', True) else '<-- wrong'}")
    counts = {s: sum(r["status"] == s for r in decisions) for s in ("current", "stale", "missing")}
    print(f"\n{counts}. Wrote decisions.csv ({len(decisions)} rows) and criteria.csv ({len(criteria)} rows) to {results_path}")
