import json
import re
import anthropic
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from denial_validator import *
from prior_auth_checker import summarize_fhir_record, judge_criteria

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

@app.post("/prior-auth-checker", response_class=HTMLResponse)
async def check_prior_auth(request: Request, file: UploadFile = File(...), order: str = Form(...)):
    order = order.strip().upper()
    info = {"filename": file.filename, "order": order}

    if not re.fullmatch(r"[A-Z0-9]{5}", order):
        info["error"] = "The order should be a 5-character HCPCS or CPT code, such as E0601."
        return templates.TemplateResponse(request, "prior-auth-checker.html", info)
    try:
        bundle = json.loads(await file.read())
        summary, refs = summarize_fhir_record(bundle)
    except (json.JSONDecodeError, UnicodeDecodeError):
        info["error"] = "That file isn't valid JSON. Upload a FHIR bundle exported from Synthea."
        return templates.TemplateResponse(request, "prior-auth-checker.html", info)
    except (KeyError, StopIteration, TypeError, ValueError):
        info["error"] = "That file doesn't look like a FHIR patient bundle (it needs a Patient resource)."
        return templates.TemplateResponse(request, "prior-auth-checker.html", info)

    #judge_criteria blocks for ~30 seconds, so it runs in a worker thread to keep the server responsive
    try:
        result = await run_in_threadpool(judge_criteria, summary, order, refs)
    except (anthropic.APIError, RuntimeError) as e:
        info["error"] = f"The analysis failed: {e}"
        return templates.TemplateResponse(request, "prior-auth-checker.html", info)

    evidence = evidence_lines(summary)
    for criterion in result["criteria"]:
        criterion["evidence_text"] = [evidence.get(tag.strip("[]"), tag) for tag in criterion["evidence"]]
    titles = {f"L{c['lcd_id']}": c["title"] for c in result["candidates"]}
    info |= {"result": result,
             "decision_label": DECISION_LABELS[result["decision"]],
             "policy_title": titles.get(result["selected_policy"], "")}
    return templates.TemplateResponse(request, "prior-auth-checker.html", info)

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