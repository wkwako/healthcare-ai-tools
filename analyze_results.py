"""Confusion matrices and charts from the saved eval results, one set per checklist, so the development policy
(L33718) and the held-out policy (L38307) are reported separately. Makes no model calls.

    python analyze_results.py                     #every checklist
    python analyze_results.py --checklist L38307  #just the held-out policy
    python analyze_results.py case_030 case_031   #just these cases (still split by checklist)

Prints each confusion matrix and saves one figure per checklist to data/eval_results/<model>/figures/.
Only current results are counted (see collect_results.py); stale and missing cases are reported and skipped.

With repeat runs (evaluate.py --runs N), it also prints each run's scores with their mean and range, and lists the
cases whose decision changed between runs. The matrices and chart pool every run's results.

Confusion matrix colors: each row is one expected verdict, and each cell's share of that row is colored by whether
it's good or bad. A correct cell (on the diagonal) runs gray to blue as its share grows; an error cell runs gray to
red. So a good matrix is a blue diagonal on gray, and red marks where the errors went.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  #write files only; no window
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from collect_results import collect
from evaluate import load_answer_keys, results_path, saved_runs
from prior_auth_checker import DECISIONS, VERDICTS

criteria_path = Path(__file__).parent / "data" / "criteria"
figures_path = results_path / "figures"

#diverging red <-> blue around a neutral gray: negative = error share, positive = correct share
RED, GRAY, BLUE = "#d03b3b", "#f0efec", "#1c5cab"
BAR = "#3987e5"
INK, INK_SECONDARY, SURFACE = "#0b0b0b", "#52514e", "#fcfcfb"
GOODNESS = LinearSegmentedColormap.from_list("goodness", [RED, GRAY, BLUE])
SHORT = {"insufficient information": "insufficient", "not applicable": "n/a"}


def checklist_name(key):
    return Path(key["checklist"]).stem

def split_label(name):
    checklist = json.loads((criteria_path / f"{name}.json").read_text(encoding="utf-8"))
    return f"{name} ({'held-out' if 'held_out' in checklist else 'development'})"

def confusion(pairs, labels):
    """Rows are expected labels, columns predicted labels; keeps only rows that occur, and columns that occur or
    match a row"""
    counts = Counter(pairs)
    rows = [l for l in labels if any(e == l for e, _ in pairs)]
    cols = [l for l in labels if l in rows or any(p == l for _, p in pairs)]
    return rows, cols, [[counts[(r, c)] for c in cols] for r in rows]

def false_approvals(pairs):
    """The costly errors: 'covered' or 'met' when the answer key says otherwise. A wrong 'insufficient' only sends the
    user to look for more documentation, so it isn't counted."""
    return sum(1 for e, p in pairs if p in ("covered", "met") and e != p)

def print_matrix(title, rows, cols, matrix):
    width = max(len(SHORT.get(l, l)) for l in rows + cols) + 2
    print(f"\n  {title} (rows: expected, columns: predicted)")
    print("  " + " " * width + "".join(f"{SHORT.get(c, c):>{width}}" for c in cols))
    for r, counts in zip(rows, matrix):
        print("  " + f"{SHORT.get(r, r):<{width}}" + "".join(f"{n:>{width}}" for n in counts))

def plot_matrix(ax, title, rows, cols, matrix):
    shares = [[n / sum(counts) for n in counts] for counts in matrix]
    signed = [[s if r == c else -s for s, c in zip(row_shares, cols)] for r, row_shares in zip(rows, shares)]
    ax.imshow(signed, cmap=GOODNESS, vmin=-1, vmax=1)
    for i, counts in enumerate(matrix):
        for j, n in enumerate(counts):
            strong = abs(signed[i][j]) > 0.55
            ax.text(j, i, f"{n}\n{shares[i][j]:.0%}" if n else "0", ha="center", va="center", fontsize=9,
                    color=SURFACE if strong else (INK if n else INK_SECONDARY))
    ax.set_xticks(range(len(cols)), [SHORT.get(c, c) for c in cols], fontsize=9, color=INK_SECONDARY)
    #row totals, since a small row makes a big percentage
    ax.set_yticks(range(len(rows)), [f"{SHORT.get(r, r)}\n(n={sum(counts)})" for r, counts in zip(rows, matrix)],
                  fontsize=9, color=INK_SECONDARY)
    ax.set_xlabel("Predicted", fontsize=9, color=INK_SECONDARY)
    ax.set_ylabel("Expected", fontsize=9, color=INK_SECONDARY)
    ax.set_title(title, fontsize=11, color=INK, loc="left")
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    #a surface-colored grid between cells
    ax.set_xticks([x - 0.5 for x in range(1, len(cols))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(rows))], minor=True)
    ax.grid(which="minor", color=SURFACE, linewidth=2)
    ax.tick_params(which="minor", length=0)

def plot_criterion_accuracy(ax, criteria):
    """Share of cases where each criterion's verdict was right, in checklist order"""
    by_criterion = {}
    for c in criteria:
        by_criterion.setdefault(c["criterion"], []).append(c["correct"])
    names = list(by_criterion)
    rates = [sum(v) / len(v) for v in by_criterion.values()]
    y = range(len(names))
    ax.barh(y, rates, color=BAR, height=0.6)
    for i, (rate, v) in enumerate(zip(rates, by_criterion.values())):
        ax.text(rate + 0.02, i, f"{sum(v)}/{len(v)}", va="center", fontsize=8, color=INK_SECONDARY)
    ax.set_yticks(list(y), names, fontsize=8, color=INK_SECONDARY)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.15)
    ax.set_xticks([0, 0.5, 1], ["0%", "50%", "100%"], fontsize=8, color=INK_SECONDARY)
    ax.set_title("Criterion accuracy", fontsize=11, color=INK, loc="left")
    ax.tick_params(length=0)
    ax.grid(axis="x", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_visible(False)

def print_runs(runs):
    """Each run's scores, then their mean and range; runs maps run number -> (decisions, criteria)"""
    def rate(rows, field):
        return sum(bool(r[field]) for r in rows) / len(rows)
    lines = {run: (rate(d, "decision_correct"), rate(c, "correct"),
                   false_approvals([(r["expected_decision"], r["predicted_decision"]) for r in d]),
                   false_approvals([(r["expected"], r["predicted"]) for r in c]), len(d))
             for run, (d, c) in runs.items()}
    print(f"\n  {'run':>5} {'cases':>6} {'decisions':>10} {'criteria':>9} {'false covered':>14} {'false met':>10}")
    for run, (dec, crit, fc, fm, n) in lines.items():
        print(f"  {run:>5} {n:>6} {dec:>10.0%} {crit:>9.0%} {fc:>14} {fm:>10}")
    if len(lines) > 1:
        columns = list(zip(*lines.values()))
        for title, pick in (("mean", lambda v: sum(v) / len(v)), ("min", min), ("max", max)):
            dec, crit, fc, fm = (pick(columns[i]) for i in range(4))
            print(f"  {title:>5} {'':>6} {dec:>10.0%} {crit:>9.0%} {fc:>14.1f} {fm:>10.1f}")

def print_unstable(runs):
    """Cases whose predicted decision differed between runs"""
    by_case = {}
    for decisions, _ in runs.values():
        for d in decisions:
            by_case.setdefault(d["case_id"], (d["expected_decision"], []))[1].append(SHORT.get(d["predicted_decision"], d["predicted_decision"]))
    unstable = {case: v for case, v in by_case.items() if len(set(v[1])) > 1}
    print(f"\n  Decision changed between runs: {len(unstable)} of {len(by_case)} cases")
    for case, (expected, got) in unstable.items():
        print(f"    {case}  expected {SHORT.get(expected, expected):12} got {', '.join(got)}")

def analyze(name, keys):
    label = split_label(name)
    runs, skipped = {}, Counter()
    for run in saved_runs():
        decisions, criteria = collect(keys, run)
        skipped[run] = sum(d["status"] != "current" for d in decisions)
        decisions = [d for d in decisions if d["status"] == "current" and d.get("predicted_decision")]
        if decisions:
            runs[run] = (decisions, [c for c in criteria if c["status"] == "current"])
    skip_text = ", ".join(f"run {run}: {n}" for run, n in skipped.items() if n and run in runs)
    print(f"\n==== {label}: {len(runs)} run(s)" + (f" (cases skipped, not current: {skip_text})" if skip_text else ""))
    if not runs:
        return
    print_runs(runs)
    if len(runs) > 1:
        print_unstable(runs)

    #the matrices and chart pool every run
    decisions = [row for run_decisions, _ in runs.values() for row in run_decisions]
    criteria = [row for _, run_criteria in runs.values() for row in run_criteria]
    decision_pairs = [(d["expected_decision"], d["predicted_decision"]) for d in decisions]
    criterion_pairs = [(c["expected"], c["predicted"]) for c in criteria]
    decision_matrix = confusion(decision_pairs, DECISIONS)
    criterion_matrix = confusion(criterion_pairs, VERDICTS + ["missing"])
    pooled = f", all {len(runs)} runs pooled" if len(runs) > 1 else ""
    print_matrix(f"Decisions{pooled}", *decision_matrix)
    print_matrix(f"Criteria verdicts{pooled}", *criterion_matrix)
    print(f"\n  False approvals (the costly errors){pooled}: {false_approvals(decision_pairs)} decisions 'covered', "
          f"{false_approvals(criterion_pairs)} criteria 'met'")

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), facecolor=SURFACE,
                             gridspec_kw={"width_ratios": [1, 1.25, 1.1]})
    for ax in axes:
        ax.set_facecolor(SURFACE)
    unit = "judgments" if len(runs) > 1 else "cases"
    plot_matrix(axes[0], f"Decisions ({len(decisions)} {unit})", *decision_matrix)
    plot_matrix(axes[1], f"Criteria verdicts ({len(criteria)})", *criterion_matrix)
    plot_criterion_accuracy(axes[2], criteria)
    runs_text = f", {len(runs)} runs pooled" if len(runs) > 1 else ""
    fig.suptitle(f"{label}, {results_path.name}{runs_text}", x=0.01, ha="left", fontsize=13, color=INK)
    fig.tight_layout()
    figures_path.mkdir(parents=True, exist_ok=True)
    out = figures_path / f"{name}.png"
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    print(f"  Saved {out}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Confusion matrices and charts from saved eval results, per checklist.")
    parser.add_argument("case_ids", nargs="*", help="cases to include, e.g. case_030 (default: all)")
    parser.add_argument("--checklist", help="only cases scored against this checklist, e.g. L38307")
    args = parser.parse_args()

    by_checklist = {}
    for key in load_answer_keys(args.case_ids):
        by_checklist.setdefault(checklist_name(key), []).append(key)
    if args.checklist:
        if args.checklist not in by_checklist:
            raise SystemExit(f"No cases use checklist {args.checklist} (found: {', '.join(by_checklist)})")
        by_checklist = {args.checklist: by_checklist[args.checklist]}
    for name, keys in by_checklist.items():
        analyze(name, keys)
