"""Reads the web app's monitoring database (see monitoring.py) for analysis. Makes no model calls.

    python analyze_monitoring.py   #prints a summary of the logged requests

Each function returns a pandas DataFrame, for a closer look in a notebook or the Python shell:

    from analyze_monitoring import *
    wrong_decisions()                       #test-case requests whose decision didn't match the answer key
    wrong_criteria().criterion.value_counts()   #which criteria the model gets wrong most often
    feedback("incorrect")                   #requests a user said were wrong
    verdicts()                              #every judged criterion, for any upload
    warnings()                              #every validation warning
"""
import json
from contextlib import closing

import pandas as pd

import monitoring

#columns saved as JSON text (see monitoring.log_request), turned back into lists when loaded
JSON_COLUMNS = ["validation_errors", "validation_warnings", "candidates", "criteria", "scored_criteria"]

def load_requests(status=None, since=None):
    """Every logged request, newest first, optionally only one status ("ok", "invalid order", "invalid record",
    "failed") or only those on or after a date ("2026-11-01")"""
    sql, params = "SELECT * FROM requests WHERE 1 = 1", []
    if status:
        sql, params = sql + " AND status = ?", params + [status]
    if since:
        sql, params = sql + " AND created_at >= ?", params + [since]
    with closing(monitoring.connect()) as conn:
        df = pd.read_sql_query(sql + " ORDER BY id DESC", conn, params=params)
    for column in JSON_COLUMNS:
        df[column] = df[column].map(lambda text: json.loads(text) if text else [])
    df["created_at"] = pd.to_datetime(df["created_at"])
    return df

def explode(df, column, keep):
    """One row per item of a JSON list column (items that are dicts become columns), with the keep columns"""
    rows = df[keep + [column]].explode(column).dropna(subset=[column])
    if rows.empty:
        return rows
    items = rows[column]
    if isinstance(items.iloc[0], dict):
        return pd.concat([rows[keep].reset_index(drop=True), pd.DataFrame(items.tolist())], axis=1)
    return rows.rename(columns={column: column.removesuffix("s")}).reset_index(drop=True)

def wrong_decisions():
    """Test-case requests whose decision didn't match the answer key"""
    df = load_requests("ok")
    return df[df["decision_correct"] == 0][["id", "created_at", "test_case", "order_code", "selected_policy",
                                            "expected_decision", "decision", "criteria_correct", "criteria_scored"]]

def wrong_criteria():
    """One row per answer-key criterion the model got wrong, on test-case requests"""
    df = load_requests("ok")
    rows = explode(df[df["test_case"].notna()], "scored_criteria", ["id", "test_case", "order_code"])
    return rows[rows["expected"] != rows["got"]] if not rows.empty else rows

def verdicts():
    """One row per criterion the model judged, on every successful request (test case or not)"""
    return explode(load_requests("ok"), "criteria", ["id", "order_code", "selected_policy", "decision"])

def feedback(answer=None):
    """Requests that got feedback, optionally only one answer ("correct", "incorrect" or "unsure")"""
    df = load_requests("ok")
    df = df[df["feedback"].notna()]
    if answer:
        df = df[df["feedback"] == answer]
    return df[["id", "created_at", "order_code", "selected_policy", "decision", "feedback", "test_case",
               "decision_correct"]]

def warnings():
    """One row per validation warning, on any request"""
    return explode(load_requests(), "validation_warnings", ["id", "status", "order_code"])

def print_summary():
    df = load_requests()
    ok = df[df["status"] == "ok"]
    tested = ok[ok["test_case"].notna()]
    print(f"Requests: {len(df)}")
    print(df["status"].value_counts().to_string(header=False))
    print(f"\nDecisions ({len(ok)} judged):")
    print(ok["decision"].value_counts().to_string(header=False))
    print(f"\nMean analysis time: {ok['duration_seconds'].mean():.1f} seconds")
    print(f"Requests with validation warnings: {(df['validation_warnings'].map(len) > 0).sum()}")
    if len(tested):
        print(f"\nTest cases: {len(tested)} judged, {int(tested['decision_correct'].sum())} decisions correct, "
              f"{int(tested['criteria_correct'].sum())}/{int(tested['criteria_scored'].sum())} criteria correct")
        wrong = wrong_criteria()
        if len(wrong):
            print("Most often wrong criteria:")
            print(wrong.groupby(["criterion", "expected", "got"]).size().sort_values(ascending=False).head(10).to_string())
    print("\nFeedback:")
    print(ok["feedback"].value_counts().to_string(header=False) if ok["feedback"].notna().any() else "  none yet")

if __name__ == "__main__":
    print_summary()
