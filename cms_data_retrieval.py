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


