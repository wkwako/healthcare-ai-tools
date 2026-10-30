"""Runs test cases through the prior authorization checker and scores them against their answer keys.

    python evaluate.py                     #every case; judges only cases without a saved result
    python evaluate.py case_001 case_004   #just these cases
    python evaluate.py --rejudge case_004  #ignore the saved result and call the model again
    python evaluate.py --runs 5            #judge each case 5 times, to measure run-to-run variance

Each case costs two model calls (~15-20k input tokens, ~20-40 seconds). Results are saved to
data/eval_results/<model>/, so rerunning rescores saved results instead of paying for new calls. A case is judged again
automatically if its patient file changed since its result was saved (e.g. it was rebuilt), or if the model,
prompts or output schema did.

Repeat runs are independent samples of the same cases: run 1 is saved in data/eval_results/<model>/ itself, and
runs 2, 3, ... in run_2/, run_3/, ... beneath it, each cached the same way. analyze_results.py reports across them.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import prior_auth_checker
from prior_auth_checker import summarize_fhir_record, judge_criteria, score_against_answer_key

cases_path = Path(__file__).parent / "data" / "modified_patient_data"
#one folder per model, so results from different models are kept side by side for comparison
results_path = Path(__file__).parent / "data" / "eval_results" / prior_auth_checker.MODEL

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

def pipeline_fingerprint():
    """Changes whenever the model, prompts or output schema change, since any of those can change a verdict"""
    p = prior_auth_checker
    parts = [p.MODEL, p.SYNTHETIC_DATA_NOTE, p.SELECT_SYSTEM, p.JUDGE_SYSTEM, json.dumps(p.JUDGE_SCHEMA, sort_keys=True)]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()

def is_current(result, key):
    """Whether a saved result was judged on this patient file with this pipeline"""
    return (result.get("patient_file_sha256") == file_fingerprint(cases_path / key["patient_file"])
            and result.get("pipeline_sha256") == pipeline_fingerprint())

def run_path(run=1):
    """Where a run's results are saved: run 1 in results_path itself, repeat runs in run_2/, run_3/, ..."""
    return results_path if run == 1 else results_path / f"run_{run}"

def saved_runs():
    """The run numbers that have a results folder"""
    return [1] + sorted(int(p.name.removeprefix("run_")) for p in results_path.glob("run_*") if p.is_dir())

def get_result(key, rejudge=False, run=1):
    """The tool's result for a case in a given run: the saved one, or a new judge_criteria() run (which is then
    saved). A saved result is only reused if neither the patient file nor the pipeline (model, prompts, schema) has
    changed since it was judged; otherwise it is judged again."""
    folder = run_path(run)
    saved = folder / f"{key['case_id']}_result.json"
    patient_file = cases_path / key["patient_file"]
    if saved.exists() and not rejudge:
        result = json.loads(saved.read_text(encoding="utf-8"))
        if is_current(result, key):
            return result
        print(f"{key['case_id']}: the patient file or pipeline changed since the saved result, judging again")
    summary, refs = summarize_fhir_record(patient_file)
    result = judge_criteria(summary, key["order"]["code"], refs) | {
        "patient_file_sha256": file_fingerprint(patient_file), "pipeline_sha256": pipeline_fingerprint()}
    folder.mkdir(parents=True, exist_ok=True)
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
    for cid in score["omitted_restatements"]:
        print(f"    (left out, not scored: restates another criterion) {cid}")

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
    print(f"  Left out, not scored: {sum(len(s['omitted_restatements']) for s in judged)}"
          " (criteria that only restate one the model judged)")
    evidence = [c for c in criteria if c["correct"] and c["evidence_expected"]]
    #grounded: the verdict rests on at least one right resource; the full count also rewards citing every duplicate
    print(f"  Grounded verdicts: {rate(sum(c['evidence_cited'] > 0 for c in evidence), len(evidence))}"
          " of correct met/not met verdicts cite at least one answer-key resource")
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
    parser.add_argument("--runs", type=int, default=1, help="judge each case this many times (runs 1..N), to measure variance")
    args = parser.parse_args()

    keys = load_answer_keys(args.case_ids)
    for run in range(1, args.runs + 1):
        if args.runs > 1:
            print(f"\n==== RUN {run} ====")
        scores = []
        for key in keys:
            score = score_against_answer_key(get_result(key, args.rejudge, run), key)
            print_case(score)
            scores.append(score)
        print_summary(scores)

# python evaluate.py                     # every case
# python evaluate.py case_001 case_004   # just these
# python evaluate.py --rejudge case_004  # call the model again even if a saved result exists

