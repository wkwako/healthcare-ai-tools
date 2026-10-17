import requests
import json
from pathlib import Path

base = "https://api.coverage.cms.gov"

def get_license_agreement_token():
    url = "/v1/metadata/license-agreement"
    complete_url = base + url
    response = requests.get(complete_url)

    return response.json()

#print (get_license_agreement_token())

token = "60dc4ed9-1ab6-4529-a042-022a77eb53ba"
headers = {"Authorization": f"Bearer {token}"}


def build_contractor_name_dict():
    r = requests.get(base + "/v1/reports/local-coverage-final-lcds")
    r.raise_for_status()

    rows = r.json()["data"]
    contractors_dict = {}
    for row in rows:
        lcd_id = row["document_id"]
        name = row["contractor_name_type"].splitlines()[0]
        contractors_dict.setdefault(lcd_id, []).append(name)

    return contractors_dict

def get_lcd_documents():
    url = base + "/v1/data/lcd/"
    lcd_path = Path(__file__).parent / "data"
    params = {}
    lines = Path(lcd_path / "lcd_list.txt").read_text().splitlines()
    contractors_dict = build_contractor_name_dict()
    for lcdid in lines:
        params["lcdid"] = lcdid
        r = requests.get(url, headers=headers, params=params)
        r_contract = requests.get(url + "contractor", headers=headers, params=params)
        r.raise_for_status()
        r_contract.raise_for_status()
        text = r.json()
        text["contractor"] = r_contract.json()
        save_path = Path(__file__).parent / "data" / "lcd" / "raw" / f"L{lcdid}.json"

        with save_path.open("w", encoding="utf-8") as f:
            json.dump(text, f)
        break
            



