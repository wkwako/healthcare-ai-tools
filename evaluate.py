"""Runs test cases through the prior authorization checker and scores them against their answer keys.

    python evaluate.py                     #every case; judges only cases without a saved result
    python evaluate.py case_001 case_004   #just these cases
    python evaluate.py --rejudge case_004  #ignore the saved result and call the model again

Each case costs two model calls (~15-20k input tokens, ~20-40 seconds). Results are saved to
data/eval_results/, so rerunning rescores saved results instead of paying for new calls. A case whose patient
file changed since its result was saved (e.g. it was rebuilt) is judged again automatically.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from prior_auth_checker import summarize_fhir_record, judge_criteria, score_against_answer_key

cases_path = Path(__file__).parent / "data" / "modified_patient_data"
results_path = Path(__file__).parent / "data" / "eval_results"

def load_answer_keys(case_ids=None):
    keys = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(cases_path.glob("*_answer_key.json"))]
    if case_ids:
        missing = set(case_ids) - {k["case_id"] for k in keys}
        if missing:
            raise SystemExit(f"No answer key for: {', '.join(sorted(missing))}")
        keys = [k for k in keys if k["case_id"] in case_ids]
    return keys

def file_fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def get_result(key, rejudge=False):
    """The tool's result for a case: the saved one, or a new judge_criteria() run (which is then saved).
    A saved result is only reused if the patient file hasn't changed since it was judged; after a case is
    rebuilt, its evidence ids no longer match the old result, so it is judged again."""
    saved = results_path / f"{key['case_id']}_result.json"
    patient_file = cases_path / key["patient_file"]
    fingerprint = file_fingerprint(patient_file)
    if saved.exists() and not rejudge:
        result = json.loads(saved.read_text(encoding="utf-8"))
        if result.get("patient_file_sha256") == fingerprint:
            return result
        print(f"{key['case_id']}: the patient file changed since the saved result, judging again")
    summary, refs = summarize_fhir_record(patient_file)
    result = judge_criteria(summary, key["order"]["code"], refs) | {"patient_file_sha256": fingerprint}
    results_path.mkdir(exist_ok=True)
    saved.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result

def print_case(score):
    policy = score["policy"]
    line = f"{score['case_id']}  policy {policy['selected']:7} {'OK' if policy['correct'] else 'WRONG (accepted: ' + ', '.join(policy['accepted']) + ')'}"
    if "decision" not in score:
        print(line + "  (scored on policy selection only)")
        return
    decision = score["decision"]
    print(f"{line}  decision {decision['got']!r} {'OK' if decision['correct'] else 'WRONG, expected ' + repr(decision['expected'])}"
          f"  criteria {score['criteria_correct']}/{len(score['criteria'])}")
    for c in score["criteria"]:
        if not c["correct"]:
            print(f"    {c['criterion']}: got {c['got']!r}, expected {c['expected']!r}")
    for c in score["extra_criteria"]:
        print(f"    (extra, not scored) {c['criterion']}: {c['verdict']}")

def print_summary(scores):
    def rate(hits, total):
        return f"{hits}/{total} ({hits / total:.0%})" if total else "n/a"
    judged = [s for s in scores if "decision" in s]
    criteria = [c for s in judged for c in s["criteria"]]
    print("\nSUMMARY")
    print(f"  Policy selection:  {rate(sum(s['policy']['correct'] for s in scores), len(scores))}")
    print(f"  Decisions:         {rate(sum(s['decision']['correct'] for s in judged), len(judged))}")
    print(f"  Criteria verdicts: {rate(sum(c['correct'] for c in criteria), len(criteria))}")

    #abstention (step 16): when the record lacks evidence, did the model say so instead of guessing?
    should_abstain = [c for c in criteria if c["expected"] == "insufficient information"]
    print(f"  Abstention:        {rate(sum(c['got'] == 'insufficient information' for c in should_abstain), len(should_abstain))}"
          " of 'insufficient' criteria answered 'insufficient'")
    #the costly mistake: claiming a criterion is met when the record has no evidence for it
    guessed_met = [c for c in should_abstain if c["got"] == "met"]
    print(f"  Guessed 'met':     {len(guessed_met)} criteria answered 'met' with no evidence in the record")
    print(f"  Missing criteria:  {sum(c['got'] == 'missing' for c in criteria)} (in the answer key but not in the model's output)")
    print(f"  Extra criteria:    {sum(len(s['extra_criteria']) for s in judged)} (judged but not in the answer key)")
    evidence = [c for c in criteria if c["correct"] and c["evidence_expected"]]
    print(f"  Evidence cited:    {rate(sum(c['evidence_cited'] for c in evidence), sum(c['evidence_expected'] for c in evidence))}"
          " of answer-key evidence, on correct met/not met verdicts")

    confusion = Counter((s["decision"]["expected"], s["decision"]["got"]) for s in judged)
    print("\n  Decisions (expected -> got):")
    for (expected, got), n in sorted(confusion.items()):
        print(f"    {expected:26} -> {got:26} {n}{'' if expected == got else '  <-- wrong'}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score the prior authorization checker against the test cases.")
    parser.add_argument("case_ids", nargs="*", help="cases to run, e.g. case_001 (default: all)")
    parser.add_argument("--rejudge", action="store_true", help="call the model again even if a saved result exists")
    args = parser.parse_args()

    scores = []
    for key in load_answer_keys(args.case_ids):
        score = score_against_answer_key(get_result(key, args.rejudge), key)
        print_case(score)
        scores.append(score)
    print_summary(scores)

# python evaluate.py                     # every case
# python evaluate.py case_001 case_004   # just these
# python evaluate.py --rejudge case_004  # call the model again even if a saved result exists

