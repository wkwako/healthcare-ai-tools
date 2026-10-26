"""Shared machinery for building synthetic prior authorization test cases, used by every policy family module
(pap_cases.py, ...). Nothing here is specific to one policy.

A family module's build_case() starts a RecordBuilder from a base patient, appends its resources, works out the
expected verdicts from its lever settings, and calls save_case(). validate_case() then checks the result.

Verdict principle used throughout: "not met" when the record shows something that fails the rule,
"insufficient information" when the record says nothing about it.
"""
import base64
import json
import random
import re
import uuid
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

data_path = Path(__file__).parent / "data"
patient_path = data_path / "patient_data"
out_path = data_path / "modified_patient_data"
criteria_path = data_path / "criteria"

SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"
HCPCS = "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets"
ENCOUNTER_CLASS = "http://terminology.hl7.org/CodeSystem/v3-ActCode"

def concept(text, system=None, code=None):
    """A CodeableConcept; codes only where Synthea already uses them, otherwise text only rather than a guessed code"""
    result = {"text": text}
    if system:
        result["coding"] = [{"system": system, "code": code, "display": text}]
    return result

def iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S+00:00")

def load_checklist(name):
    """A policy's criteria checklist from data/criteria, e.g. load_checklist("L33718")"""
    return json.loads((criteria_path / f"{name}.json").read_text(encoding="utf-8"))

def base_patient_file(name):
    """Finds a patient file in data/patient_data by its first name token, e.g. "Shalanda398" """
    matches = list(patient_path.glob(f"{name}_*.json"))
    if len(matches) != 1:
        raise ValueError(f"expected one patient file for {name}, found {len(matches)}")
    return matches[0]

class RecordBuilder:
    """A copy of a base patient's Synthea bundle that new resources are appended to, in Synthea's format.
    Seeded by the case id, so rebuilding a case gives identical files: the same dates, values and resource ids."""

    def __init__(self, base_patient, case_id):
        self.source = base_patient_file(base_patient)
        self.bundle = json.loads(self.source.read_text(encoding="utf-8"))
        self.original_entry_count = len(self.bundle["entry"])
        self.rng = random.Random(case_id)
        #ids get their own generator so adding a resource doesn't shift the case's dates and values
        self.id_rng = random.Random(f"{case_id}-ids")
        self.added = []
        self.resources = [e["resource"] for e in self.bundle["entry"]]
        patient_entry = next(e for e in self.bundle["entry"] if e["resource"]["resourceType"] == "Patient")
        self.patient = patient_entry["resource"]
        self.patient_ref = {"reference": patient_entry["fullUrl"]}
        self.practitioner, self.organization, self.location = self.find_treating_practitioner()

    def find_treating_practitioner(self):
        """The patient's most frequent ambulatory clinician, with the organization and location they see them at"""
        encounters = [r for r in self.resources if r["resourceType"] == "Encounter" and r["class"]["code"] == "AMB"
                      and any("individual" in p for p in r.get("participant", []))]
        counts = Counter(p["individual"]["reference"] for r in encounters for p in r["participant"] if "individual" in p)
        reference = counts.most_common(1)[0][0]
        encounter = next(r for r in reversed(encounters)
                         if any(p.get("individual", {}).get("reference") == reference for p in r["participant"]))
        individual = next(p["individual"] for p in encounter["participant"] if p.get("individual", {}).get("reference") == reference)
        return individual, encounter["serviceProvider"], encounter["location"][0]["location"]

    def last_date(self):
        return max(datetime.fromisoformat(r["period"]["start"]) for r in self.resources if r["resourceType"] == "Encounter")

    def age_on(self, moment):
        return moment.year - int(self.patient["birthDate"][:4])

    def daytime(self, day, hour_range=(9, 16)):
        """A random clinic-hours time on the given day"""
        return day.replace(hour=self.rng.randint(*hour_range), minute=self.rng.choice((0, 15, 30, 45)), second=0)

    def conditions(self, pattern):
        """The base patient's conditions whose name matches a regex"""
        return [r for r in self.resources if r["resourceType"] == "Condition" and pattern.search(r["code"]["coding"][0]["display"])]

    def add(self, resource, description):
        #from a seeded generator rather than uuid4(), so ids are the same on every rebuild
        resource["id"] = str(uuid.UUID(int=self.id_rng.getrandbits(128), version=4))
        self.bundle["entry"].append({"fullUrl": f"urn:uuid:{resource['id']}", "resource": resource,
                                     "request": {"method": "POST", "url": resource["resourceType"]}})
        self.added.append({"id": resource["id"], "resourceType": resource["resourceType"], "description": description})
        return resource["id"]

    def ref(self, resource_id):
        return {"reference": f"urn:uuid:{resource_id}"}

    def encounter(self, start, minutes, type_text, reason, description, setting="AMB", type_code=None):
        end = start + timedelta(minutes=minutes)
        resource = {
            "resourceType": "Encounter", "status": "finished",
            "class": {"system": ENCOUNTER_CLASS, "code": setting},
            "type": [concept(type_text, SNOMED, type_code) if type_code else concept(type_text)],
            "subject": self.patient_ref,
            "participant": [{"type": [concept("primary performer", "http://terminology.hl7.org/CodeSystem/v3-ParticipationType", "PPRF")],
                             "period": {"start": iso(start), "end": iso(end)}, "individual": self.practitioner}],
            "period": {"start": iso(start), "end": iso(end)},
            "reasonCode": [concept(reason)],
            "serviceProvider": self.organization,
        }
        if setting == "AMB":
            resource["location"] = [{"location": self.location}]
        return self.add(resource, description)

    def note(self, encounter_id, when, text, description):
        """Synthea stores each note twice (DiagnosticReport + DocumentReference); returns the DocumentReference id,
        the copy the patient summary shows"""
        data = base64.b64encode(text.strip().encode("utf-8")).decode("ascii")
        note_type = [{"system": LOINC, "code": "34117-2", "display": "History and physical note"},
                     {"system": LOINC, "code": "51847-2", "display": "Evaluation + Plan note"}]
        report_id = self.add({
            "resourceType": "DiagnosticReport", "status": "final",
            "category": [{"coding": note_type}], "code": {"coding": note_type},
            "subject": self.patient_ref, "encounter": self.ref(encounter_id),
            "effectiveDateTime": iso(when), "issued": iso(when), "performer": [self.practitioner],
            "presentedForm": [{"contentType": "text/plain; charset=utf-8", "data": data}],
        }, description + " (note)")
        return self.add({
            "resourceType": "DocumentReference", "status": "current",
            "identifier": [{"system": "urn:ietf:rfc:3986", "value": f"urn:uuid:{report_id}"}],
            "type": {"coding": note_type},
            "category": [concept("Clinical Note", "http://hl7.org/fhir/us/core/CodeSystem/us-core-documentreference-category", "clinical-note")],
            "subject": self.patient_ref, "date": iso(when), "author": [self.practitioner], "custodian": self.organization,
            "content": [{"attachment": {"contentType": "text/plain; charset=utf-8", "data": data}}],
            "context": {"encounter": [self.ref(encounter_id)], "period": {"start": iso(when), "end": iso(when)}},
        }, description + " (note, document copy)")

    def observation(self, encounter_id, when, text, description, quantity=None, unit=None, integer=None, category="procedure"):
        resource = {
            "resourceType": "Observation", "status": "final",
            "category": [concept(category.capitalize(), "http://terminology.hl7.org/CodeSystem/observation-category", category)],
            "code": concept(text), "subject": self.patient_ref,
            "effectiveDateTime": iso(when), "issued": iso(when),
        }
        if encounter_id:
            resource["encounter"] = self.ref(encounter_id)
        if integer is not None:
            resource["valueInteger"] = integer
        else:
            resource["valueQuantity"] = {"value": quantity, "unit": unit, "system": "http://unitsofmeasure.org", "code": unit}
        return self.add(resource, description)

    def condition(self, encounter_id, when, text, description, system=None, code=None):
        resource = {
            "resourceType": "Condition",
            "clinicalStatus": concept("Active", "http://terminology.hl7.org/CodeSystem/condition-clinical", "active"),
            "verificationStatus": concept("Confirmed", "http://terminology.hl7.org/CodeSystem/condition-ver-status", "confirmed"),
            "category": [concept("Encounter Diagnosis", "http://terminology.hl7.org/CodeSystem/condition-category", "encounter-diagnosis")],
            "code": concept(text, system, code), "subject": self.patient_ref,
            "onsetDateTime": iso(when), "recordedDate": iso(when),
        }
        if encounter_id:
            resource["encounter"] = self.ref(encounter_id)
        return self.add(resource, description)

    def procedure(self, encounter_id, start, minutes, text, description, system=None, code=None, performer=None):
        resource = {
            "resourceType": "Procedure", "status": "completed",
            "code": concept(text, system, code), "subject": self.patient_ref,
            "performedPeriod": {"start": iso(start), "end": iso(start + timedelta(minutes=minutes))},
        }
        if encounter_id:
            resource["encounter"] = self.ref(encounter_id)
        if performer:
            resource["performer"] = [{"actor": performer}]
        return self.add(resource, description)

    def device_request(self, encounter_id, when, code, code_text, status, reason_id, description):
        """An order for a device, coded with its HCPCS code"""
        return self.add({
            "resourceType": "DeviceRequest", "status": status, "intent": "order",
            "codeCodeableConcept": concept(code_text, HCPCS, code),
            "subject": self.patient_ref, "encounter": self.ref(encounter_id), "authoredOn": iso(when),
            "requester": self.practitioner, "reasonReference": [self.ref(reason_id)],
        }, description)

def decide(criteria):
    """The decision rule for policies whose criteria must all be met: any "not met" denies,
    otherwise any "insufficient information" is insufficient, otherwise covered"""
    verdicts = [c["verdict"] for c in criteria.values()]
    if "not met" in verdicts:
        return "denied"
    if "insufficient information" in verdicts:
        return "insufficient information"
    return "covered"

def decision_explanation(criteria, decision):
    if decision == "covered":
        return "Every applicable criterion is met."
    if decision == "denied":
        return f"Not met: {', '.join(cid for cid, c in criteria.items() if c['verdict'] == 'not met')}."
    return f"Insufficient information for: {', '.join(cid for cid, c in criteria.items() if c['verdict'] != 'met')}."

def save_case(record, case_id, policy_fields):
    """Writes the doctored record and its answer key to data/modified_patient_data. policy_fields holds what the
    family module decided (levers, order, accepted_policies, checklist, criteria, expected_decision, ...);
    this adds the fields every case has. Returns the answer key."""
    out_file = out_path / record.source.name.replace(".json", f"_{case_id}.json")
    key = {"case_id": case_id, "patient_file": out_file.name, "source_file": record.source.name,
           **policy_fields,
           "original_entry_count": record.original_entry_count, "added_resources": record.added}
    out_path.mkdir(exist_ok=True)
    out_file.write_text(json.dumps(record.bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_path / f"{case_id}_answer_key.json").write_text(json.dumps(key, indent=2, ensure_ascii=False), encoding="utf-8")
    return key

def validate_case(key):
    """Checks a built case (step 10): returns a list of problems, empty if it's sound"""
    from prior_auth_checker import summarize_fhir_record
    problems = []
    bundle = json.loads((out_path / key["patient_file"]).read_text(encoding="utf-8"))
    source = json.loads((patient_path / key["source_file"]).read_text(encoding="utf-8"))
    if bundle["entry"][:key["original_entry_count"]] != source["entry"]:
        problems.append("original entries were changed")
    urls = [e["fullUrl"] for e in bundle["entry"]]
    if len(urls) != len(set(urls)):
        problems.append("duplicate fullUrls")
    text = json.dumps(bundle)
    if key["case_id"] in text or "answer key" in text.lower():
        problems.append("the record mentions the case id or answer key")
    unresolved = set(re.findall(r'"reference": "(urn:uuid:[^"]+)"', text)) - set(urls)
    if unresolved:
        problems.append(f"{len(unresolved)} unresolved references")
    ids = {e["resource"]["id"] for e in bundle["entry"]}
    _, refs = summarize_fhir_record(bundle)
    visible = set(refs.values())
    for cid, criterion in key["criteria"].items():
        for resource_id in criterion["evidence"]:
            if resource_id not in ids:
                problems.append(f"{cid}: evidence {resource_id} is not in the record")
            elif resource_id not in visible:
                problems.append(f"{cid}: evidence {resource_id} is not in the patient summary")
        if criterion["verdict"] in ("met", "not met") and not criterion["evidence"]:
            problems.append(f"{cid}: '{criterion['verdict']}' with no evidence")
    if key["order"]["resource_id"] not in visible:
        problems.append("the order is not in the patient summary")
    return problems
