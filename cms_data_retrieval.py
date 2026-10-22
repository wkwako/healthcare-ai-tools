import requests
import json
from pathlib import Path
import html
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

base = "https://api.coverage.cms.gov"

TOKEN_LIFETIME = timedelta(hours=1)
token_cache = {"token": None, "created_at": None}

def get_license_agreement_token():
    """Requests a new token and records when it was generated"""
    url = "/v1/metadata/license-agreement"
    complete_url = base + url
    response = requests.get(complete_url)
    response.raise_for_status()

    token_cache["token"] = response.json()["data"][0]["Token"]
    token_cache["created_at"] = datetime.now()

    return token_cache["token"]

def get_token():
    """Returns the stored token, or a new one if it's missing or an hour old"""
    created_at = token_cache["created_at"]
    if created_at is None or datetime.now() - created_at >= TOKEN_LIFETIME:
        return get_license_agreement_token()

    return token_cache["token"]

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
        headers = {"Authorization": f"Bearer {get_token()}"}

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

BLOCK_TAGS = ["p", "li", "div", "ol", "ul", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6"]
EMPHASIS_TAGS = ["strong", "b", "u"]
ROMAN_NUMERALS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]

def list_label(n, list_type):
    """Turns a list position into the label the policy uses, e.g. 3 + "A" -> "C." """
    if list_type in ("A", "a"):
        label = chr(ord("A") + n - 1)
    elif list_type in ("I", "i") and n <= len(ROMAN_NUMERALS):
        label = ROMAN_NUMERALS[n - 1]
    else:
        label = str(n)
    if list_type in ("a", "i"):
        label = label.lower()
    return label + "."

#placeholder characters marking where bold/underlined text starts and ends
EMPHASIS_START, EMPHASIS_END = "\x02", "\x03"

def strip_emphasis(line, depth):
    """Removes emphasis markers from a line and reports whether all its words were emphasized.
    depth carries over between lines, since a <strong> can span a <br>"""
    chars = []
    all_emphasized = True
    for ch in line:
        if ch == EMPHASIS_START:
            depth += 1
        elif ch == EMPHASIS_END:
            depth = max(depth - 1, 0)
        else:
            chars.append(ch)
            if ch.isalnum() and depth == 0:
                all_emphasized = False
    return "".join(chars), all_emphasized, depth

def is_heading(line, all_emphasized):
    """Part B MAC policies mark headings in bold (Covered Indications);
    DME MAC policies use all-caps lines (INITIAL COVERAGE:)"""
    letters = [c for c in line if c.isalpha()]
    if len(letters) < 4 or len(line) >= 100:
        return False
    return all_emphasized or line.upper() == line

def clean_html(raw):
    soup = BeautifulSoup(html.unescape(raw), "html.parser")

    for tag in soup.find_all(EMPHASIS_TAGS):
        tag.insert(0, EMPHASIS_START)
        tag.append(EMPHASIS_END)

    #restore the list labels criteria refer to (e.g. "criteria A - C")
    for ol in soup.find_all("ol"):
        n = int(ol.get("start", 1))
        for li in ol.find_all("li", recursive=False):
            li.insert(0, list_label(n, ol.get("type", "1")) + " ")
            n += 1
    for li in soup.select("ul > li"):
        li.insert(0, "- ")

    #newlines only between blocks, so inline tags don't split sentences
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for cell in soup.find_all(["td", "th"]):
        cell.append(" | ")
    for block in soup.find_all(BLOCK_TAGS):
        block.insert_before("\n")
        block.append("\n")

    lines = []
    label = ""
    depth = 0
    for line in soup.get_text().splitlines():
        line, all_emphasized, depth = strip_emphasis(line, depth)
        line = " ".join(line.split()).rstrip(" |")
        if not line:
            continue
        #a list item whose text sits in its own <p> leaves its label on a line alone
        if re.fullmatch(r"-|\w{1,4}\.", line):
            label += line + " "
            continue
        line, label = label + line, ""
        if is_heading(line, all_emphasized):
            line = "## " + line
        lines.append(line)
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

if __name__ == "__main__":
    # re-download raw files
    # get_lcd_info()

    # creates clean files
    clean_data()
