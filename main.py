from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from denial_validator import *

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