# Code Overview
data folder: contains fake patient files (not on GitHub), LCD documents, criteria, evaluation results, and the Chroma vector database.

.github folder: Contains automated workflow actions (tests via pytest) that run on pushing to GitHub.

`cases.py`: Contains patient cases that will be built out by `build_cases.py`. Contains only data, no logic.

`build_cases.py`: For each test case in `cases.py`, picks the family module (LCN), then builds and validate the patient.

`hgns_cases.py`/`pap_cases.py`: The policy-specific part of building test cases: details what to add to the record, and the correct verdict for each criterion.

`record_builder.py`: Contains tools that assist with test patient building, like copying patient files, adding FHIR resources, saving records, validation, etc.

`cms_data_retrieval.py`: Uses CMS's RESTful API to download and clean raw LCD files.

`collect_results.py`: Collects the saved eval results into two flat tables of answer key vs prediction for easier analysis.

`denial_validator.py`: Performs structure and balance checks against 835s (remittance files).

`evaluate.py`: Evaluates the prior authorization pipeline's functionality, which is split into four categories: policy selection (LCD file selection), decisions (covered/not covered/insufficient information determination), criteria verdicts (individual criteria selection as part of a policy), and evidence cited (referencing the correct part of the patient record's resources for each determination). Each patient case holds its ground truth in an answer key; categories are reported as the percentage the model's verdict matched the answer key's values.

`analyze_results.py`: Analyzes stored json results from evaluation runs, and produces a confusion matrix of results.

`main.py`: Contains FastAPI code for running the website.

`policy_store.py`: Turns cleaned LCD files into chunks with ids and metadata for Chroma (for the later policy retrieval step).

`prior_auth_checker.py`: Builds the patient summary, retrieves policy passages, selects the LCD, and judges the order's criteria.

# Project Overview

I created a webapp that hosts a suite of 835-focused healthcare tools, like checking the structure and balance of 835s, and predicting if an order is covered under Medicare. The entirety of this file is focused on this second tool; other tools are detailed in the appendices.

# Prior Authorization Checker Tool

Given a patient FHIR file and an order, the tool predicts if the order is covered under Medicare. The result can be one of three values: "covered", "not covered," or "insufficient information," if there isn't enough information in the patient file to make a clear determination.

# Background

### Medicare

Medicare is a federal health insurance program for people at least 65 years old, and for younger people with certain disabilities.

### FHIR files

Fast Healthcare Interoperability Resources (FHIR) are files representing patient data created from standardized building blocks, including data like Patient (personal information), Observation (lab results), and Encounters (doctor vists). The files use json format, which makes them computationally easy to parse.

### LCD files

An order is only covered under Medicare if certain criteria are met. For example, an MRI may only be covered if their doctor deems it medically necessary, and other diagnostic tests failed to identify the issue (this is just an example -- this may not be representative of all MRIs). The criteria determining coverage for each medical item, procedure, or technology, are available in national coverage determination (NCD) files. Typically, one NCD will exist for each item, procedure, or technology. However, local contractors, called Medicare Administrative Contractors (MACs), can specify additional requirements in their own files, local coverage determinations (LCDs). LCDs must yield to NCDs and cannot override them.

### 835 remittance files

835s files are delimiter-separated files sent by payers to indicate a remittance (a payment). They contain patient, payer, and payment information, but may include partial or full denials as well.

# Architecture

-FastAPI

# Evaluation

# Limitations
- using cheap model
- don't have a ton of data
- patient data is clean
- not real patient data

### Pipeline

# Results

# Future Work
- deploy to web (Azure)
- increase accuracy