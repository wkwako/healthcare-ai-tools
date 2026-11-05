import json
import re
import time
import anthropic
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import monitoring
from denial_validator import *
from prior_auth_checker import MODEL, summarize_fhir_record, judge_criteria

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

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

@app.get("/prior-auth-checker", response_class=HTMLResponse)
async def prior_auth_checker(request: Request):
    return templates.TemplateResponse(request, "prior-auth-checker.html")

#what the user sees for each decision the tool returns
DECISION_LABELS = {"covered": "Covered", "denied": "Not covered", "insufficient information": "Insufficient information"}

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
            lines[match.group(1)] = (name + match.group(2)).strip().rstrip(":")
    return lines

def respond(request, info, row):
    """Saves the request's monitoring row, then renders the page. The row's id goes on the page so feedback on the
    decision can be matched to it."""
    info |= {"request_id": monitoring.log_request(row), "feedback_enabled": monitoring.FEEDBACK_ENABLED,
             "feedback_choices": monitoring.FEEDBACK_CHOICES}
    return templates.TemplateResponse(request, "prior-auth-checker.html", info)

@app.post("/prior-auth-checker", response_class=HTMLResponse)
async def check_prior_auth(request: Request, file: UploadFile = File(...), order: str = Form(...)):
    order = order.strip().upper()
    info = {"filename": file.filename, "order": order}
    #the monitoring row, filled in as the request goes; never the filename, which can contain the patient's name
    row = {"order_code": order, "model": MODEL}

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
    row |= {"status": "ok", "duration_seconds": round(time.perf_counter() - started, 1),
            "candidates": [f"L{c['lcd_id']}" for c in result["candidates"]],
            "selected_policy": result["selected_policy"], "decision": result["decision"],
            "criteria": [{"criterion": c["criterion"], "verdict": c["verdict"]} for c in result["criteria"]],
            "criteria_count": len(result["criteria"])}
    row |= monitoring.test_case_score(contents, order, result)

    evidence = evidence_lines(summary)
    for criterion in result["criteria"]:
        criterion["evidence_text"] = [evidence.get(tag.strip("[]"), tag) for tag in criterion["evidence"]]
    titles = {f"L{c['lcd_id']}": c["title"] for c in result["candidates"]}
    info |= {"result": result,
             "warnings": warnings,
             "decision_label": DECISION_LABELS[result["decision"]],
             "policy_title": titles.get(result["selected_policy"], "")}
    return respond(request, info, row)

@app.post("/prior-auth-checker/feedback", response_class=HTMLResponse)
async def prior_auth_feedback(request: Request, request_id: int = Form(...), feedback: str = Form(...)):
    saved = monitoring.FEEDBACK_ENABLED and monitoring.record_feedback(request_id, feedback)
    return templates.TemplateResponse(request, "prior-auth-checker.html", {"feedback_saved": saved})

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