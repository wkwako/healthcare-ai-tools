import json
import os
import re
import time
import anthropic
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import demo
import monitoring
from denial_validator import get_segments, structure_check, balance_check
from prior_auth_checker import MODEL, summarize_fhir_record, judge_criteria

#uploads are off unless ALLOW_UPLOADS=1 (e.g. in .env on your own machine), so visitors to the deployed site can only
#use the demo patients: no real patient data can reach it, and it never calls the model
ALLOW_UPLOADS = os.getenv("ALLOW_UPLOADS") == "1"

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

#every tool, for the toolbar on each page and the cards on the homepage
TOOLS = [
    {"name": "Prior Authorization Checker", "short_name": "Prior Auth", "path": "/prior-auth-checker", "ready": True,
     "description": "Finds the Medicare policy that governs an order, then checks each of its criteria against a "
                    "patient record, citing the evidence it used."},
    {"name": "835 Denial Validator", "short_name": "Denial Validator", "path": "/denial-validator", "ready": True,
     "description": "Checks an 835 remittance file's envelope structure, and that its payments, adjustments and "
                    "provider-level adjustments balance."},
    {"name": "835 Denial Explainer", "short_name": "Denial Explainer", "path": "/denials-explainer", "ready": False,
     "description": "Explains the denials in an 835 remittance file in plain language."},
    {"name": "Medicare Policy Assistant", "short_name": "Policy Assistant", "path": "/medicare-policy-assistant",
     "ready": False, "description": "Answers questions about Medicare coverage policies, citing the policy text."},
]
templates.env.globals["tools"] = TOOLS

#when a browser sends a GET request to "/", run home() and send back whatever it returns
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "index.html")

@app.get("/denials-explainer", response_class=HTMLResponse)
async def denials_explainer(request: Request):
    return templates.TemplateResponse(request, "denials-explainer.html")

@app.get("/medicare-policy-assistant", response_class=HTMLResponse)
async def medicare_policy_assistant(request: Request):
    return templates.TemplateResponse(request, "medicare-policy-assistant.html")

def render(request, info):
    """The prior auth checker page, with the demo choices and the upload form if uploads are allowed"""
    info |= {"demo_patients": demo.PATIENTS, "demo_orders": demo.ORDERS, "allow_uploads": ALLOW_UPLOADS}
    return templates.TemplateResponse(request, "prior-auth-checker.html", info)

@app.get("/prior-auth-checker", response_class=HTMLResponse)
async def prior_auth_checker(request: Request):
    return render(request, {})

#what the user sees for each decision the tool returns
DECISION_LABELS = {"covered": "Covered", "denied": "Not covered", "insufficient information": "Insufficient information"}

def readable_units(text):
    """Synthea writes count units in UCUM's annotation syntax, e.g. "91 {events}"; shows them as "91 events".
    "{#}" only means a count, so it's dropped."""
    return re.sub(r" ?\{([^}]*)\}", lambda m: "" if m.group(1) == "#" else " " + m.group(1), text)

def evidence_lines(summary):
    """Maps each evidence tag (R12) to the summary text it labels, so cited evidence can be shown to the user.
    Observation lines hold several tagged values, so each value keeps the measurement name in front of it."""
    lines = {}
    for line in summary.splitlines():
        #each tagged value runs until the next tag ("; [R13] ...") or the end of the line
        matches = list(re.finditer(r"\[(R\d+)\] (.*?)(?=; \[R\d+\]|$)", line))
        if not matches:
            continue
        name = line[:matches[0].start()]
        for match in matches:
            lines[match.group(1)] = readable_units(name + match.group(2)).strip().rstrip(":")
    return lines

def respond(request, info, row):
    """Saves the request's monitoring row, then renders the page. The row's id goes on the page so feedback on the
    decision can be matched to it."""
    info |= {"request_id": monitoring.log_request(row), "feedback_enabled": monitoring.FEEDBACK_ENABLED,
             "feedback_choices": monitoring.FEEDBACK_CHOICES}
    return render(request, info)

def show_result(request, info, row, result, summary, warnings, key):
    """Fills in the monitoring row and the page from a result, for a demo patient or an upload. key is the answer key
    of the test case the patient is, if any, to score the result against."""
    row |= {"status": "ok",
            "candidates": [f"L{c['lcd_id']}" for c in result["candidates"]],
            "selected_policy": result["selected_policy"], "decision": result["decision"],
            "criteria": [{"criterion": c["criterion"], "verdict": c["verdict"]} for c in result["criteria"]],
            "criteria_count": len(result["criteria"])}
    row |= monitoring.test_case_score(key, info["order"], result)

    evidence = evidence_lines(summary)
    for criterion in result["criteria"]:
        criterion["evidence_text"] = [evidence.get(tag.strip("[]"), tag) for tag in criterion["evidence"]]
    titles = {f"L{c['lcd_id']}": c["title"] for c in result["candidates"]}
    info |= {"result": result,
             "warnings": warnings,
             "decision_label": DECISION_LABELS[result["decision"]],
             "policy_title": titles.get(result["selected_policy"], "")}
    return respond(request, info, row)

@app.post("/prior-auth-checker/demo", response_class=HTMLResponse)
async def check_demo(request: Request, patient: str = Form(...), order: str = Form(...)):
    """A demo patient and order: shows the result judged ahead of time by demo.py, without calling the model"""
    info = {"patient": patient, "order": order}
    row = {"source": "demo", "demo_patient": patient, "order_code": order, "model": MODEL}
    result = demo.cached_result(patient, order) if patient in demo.PATIENTS and order in demo.ORDERS else None
    if result is None:
        info["error"] = "Pick one of the listed patients and orders."
        return respond(request, info, row | {"status": "invalid choice"})

    bundle = json.loads(demo.patient_path(patient).read_text(encoding="utf-8"))
    errors, warnings = monitoring.validate_bundle(bundle)
    row |= {"validation_errors": errors, "validation_warnings": warnings} | monitoring.patient_profile(bundle)
    summary, _ = summarize_fhir_record(bundle)
    key = demo.answer_key(patient)
    info["built_for"] = key["order"]["code"]
    #warnings are logged but not shown: the only ones the demo patients have are dates the case builder put after
    #today, which visitors can't do anything about
    return show_result(request, info, row, result, summary, [], key)

@app.post("/prior-auth-checker", response_class=HTMLResponse)
async def check_prior_auth(request: Request, file: UploadFile = File(...), order: str = Form(...)):
    order = order.strip().upper()
    info = {"filename": file.filename, "order": order}
    #the monitoring row, filled in as the request goes; never the filename, which can contain the patient's name
    row = {"source": "upload", "order_code": order, "model": MODEL}

    if not ALLOW_UPLOADS:
        info["error"] = "Uploads are turned off on this site. Pick one of the demo patients instead."
        return respond(request, info, row | {"status": "invalid choice"})
    if not re.fullmatch(r"[A-Z0-9]{5}", order):
        info["error"] = "The order should be a 5-character HCPCS or CPT code, such as E0601."
        return respond(request, info, row | {"status": "invalid order"})
    contents = await file.read()
    try:
        bundle = json.loads(contents)
    except (json.JSONDecodeError, UnicodeDecodeError):
        info["error"] = "That file isn't valid JSON. Upload a FHIR bundle exported from Synthea."
        return respond(request, info, row | {"status": "invalid record", "validation_errors": ["The file isn't valid JSON."]})
    errors, warnings = monitoring.validate_bundle(bundle)
    row |= {"validation_errors": errors, "validation_warnings": warnings}
    if errors:
        info["error"] = "That file doesn't look like a FHIR patient bundle: " + " ".join(errors)
        return respond(request, info, row | {"status": "invalid record"})
    row |= monitoring.patient_profile(bundle)
    try:
        summary, refs = summarize_fhir_record(bundle)
    except (KeyError, StopIteration, TypeError, ValueError) as e:
        #a bundle that passed validation but still couldn't be summarized: validate_bundle is missing a check
        info["error"] = "That file doesn't look like a FHIR patient bundle the tool can read."
        return respond(request, info, row | {"status": "invalid record", "error": f"summary failed: {e!r}"})

    #judge_criteria blocks for ~30 seconds, so it runs in a worker thread to keep the server responsive
    started = time.perf_counter()
    try:
        result = await run_in_threadpool(judge_criteria, summary, order, refs)
    except (anthropic.APIError, RuntimeError) as e:
        info["error"] = f"The analysis failed: {e}"
        return respond(request, info, row | {"status": "failed", "error": str(e),
                                             "duration_seconds": round(time.perf_counter() - started, 1)})
    row["duration_seconds"] = round(time.perf_counter() - started, 1)
    return show_result(request, info, row, result, summary, warnings, monitoring.find_test_case(contents))

@app.post("/prior-auth-checker/feedback", response_class=HTMLResponse)
async def prior_auth_feedback(request: Request, request_id: int = Form(...), feedback: str = Form(...)):
    saved = monitoring.FEEDBACK_ENABLED and monitoring.record_feedback(request_id, feedback)
    return render(request, {"feedback_saved": saved})

@app.get("/denial-validator", response_class=HTMLResponse)
async def denial_validator(request: Request):
    return templates.TemplateResponse(request, "denial-validator.html")

@app.post("/denial-validator", response_class=HTMLResponse)
async def check_835(request: Request, file: UploadFile=File(...)):
    contents = await file.read()
    text = contents.decode("utf-8")

    segments = get_segments(text)

    #ISA/IEA, GS/GE, ST/SE envelope check
    structure_result, structure_err_msg = structure_check(segments)

    #balance and PLB adjustments check
    balance_result, balance_err_msg = balance_check(segments)

    info = {"filename": file.filename,
            "segment_count": len(segments),
            "structure_result": structure_result,
            "structure_err_msg": structure_err_msg,
            "balance_result": balance_result,
            "balance_err_msg": balance_err_msg}

    return templates.TemplateResponse(request, "denial-validator.html", info)