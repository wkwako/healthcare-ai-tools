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

@app.get("/denial-validator", response_class=HTMLResponse)
async def denial_validator(request: Request):
    return templates.TemplateResponse(request, "denial-validator.html")

@app.post("/denial-validator", response_class=HTMLResponse)
async def check_835(request: Request, file: UploadFile=File(...)):
    contents = await file.read()
    text = contents.decode("utf-8")

    segments = get_segments(text)

    #ISA/IEA, GS/GE, ST/SE envelope check
    result, err_msg = structure_check(segments)
    print (result, err_msg)

    #TODO: make get_element more user friendly?
    info_dict = create_info_dict(segments)
    print (info_dict)
    print (get_element("CLP", 1, info_dict))

    info = {"filename": file.filename, "segment_count": len(segments)}

    return templates.TemplateResponse(request, "denial-validator.html", info)