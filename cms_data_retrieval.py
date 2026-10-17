import requests
import json
from pathlib import Path
import html
from bs4 import BeautifulSoup

base = "https://api.coverage.cms.gov"

def get_license_agreement_token():
    url = "/v1/metadata/license-agreement"
    complete_url = base + url
    response = requests.get(complete_url)

    return response.json()

#print (get_license_agreement_token())

token = "88876fbb-a199-4133-81af-12a641d8af4d"
headers = {"Authorization": f"Bearer {token}"}

def build_contractor_name_dict():
    """Builds a dictionary of lcdid:[contractor] key:value pairs"""
    r = requests.get(base + "/v1/reports/local-coverage-final-lcds")
    r.raise_for_status()
    rows = r.json()["data"]
    contractors_dict = {}
    for row in rows:
        lcd_id = row["document_id"]
        name = row["contractor_name_type"].splitlines()[0]
        contractors_dict.setdefault(lcd_id, []).append(name)

    return contractors_dict

def get_lcd_info():
    url = base + "/v1/data/lcd/"
    lcd_path = Path(__file__).parent / "data"
    params = {}
    lines = Path(lcd_path / "lcd_list.txt").read_text().splitlines()
    contractors_dict = build_contractor_name_dict()
    for lcdid in lines:
        params["lcdid"] = lcdid

        #get general lcd information
        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
        text = r.json()
        ver = text["data"][0]["lcd_version"]
        sub_params = {"lcdid": lcdid, "ver": ver}

        sub_endpoints = ["related-documents", "related-ncd-documents",
                 "primary-jurisdiction", "hcpc-code"]

        for name in sub_endpoints:
            sub = requests.get(url + name, headers=headers, params=sub_params)
            sub.raise_for_status()
            text[name.replace("-", "_")] = sub.json()

        #add info to main json file before saving it
        text["contractor"] = contractors_dict[int(lcdid)]

        save_path = Path(__file__).parent / "data" / "lcd" / "raw" / f"L{lcdid}.json"
        with save_path.open("w", encoding="utf-8") as f:
            json.dump(text, f)

        #one file, remove after testing
        #break
            
get_lcd_info()

def clean_html(raw):
    text = BeautifulSoup(html.unescape(raw), "html.parser").get_text("\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)

def clean_data():
    input_path = Path(__file__).parent / "data" / "lcd" / "raw"
    output_path = Path(__file__).parent / "data" / "lcd" / "clean"

    files = [item for item in input_path.iterdir() if item.is_file()]
    for file in files:
        raw = json.loads(file.read_text(encoding="utf-8"))
        lcd = raw["data"][0]

        cleaned = {
            "lcd_id": lcd["lcd_id"],
            "version": lcd["lcd_version"],
            "title": lcd["title"],
            "status": lcd["status"],
            "contractors": raw["contractor"],
            "sections": {
                "indication": clean_html(lcd["indication"]),
                "associated_info": clean_html(lcd["associated_info"]),
            },
        }

        with (output_path / file.name).open("w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2)

    return cleaned

