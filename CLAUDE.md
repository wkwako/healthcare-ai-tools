The web application: a suite of healthcare ai-related tools to build domain and tool knowledge (unit tests, CI/CD, RAG, Chroma, sqlite3, AWS/Azure, etc.)

Tool #1: A basic denial structure/balance validator. This is complete.
Tool #2: A prior authorization checker. Given a synthetic patient record (FHIR, from Synthea) and an order, it finds the relevant Medicare coverage policy, then judges each criterion as met, not met, or insufficient information, citing evidence from the record.

The corpus: about 25 Medicare LCDs around obstructive sleep apnea: PAP devices, sleep studies, polysomnography, hypoglossal nerve stimulation, sleep apnea surgery, and oxygen, plus a few loosely related distractors. It’s frozen as a saved ID list so evaluation results stay comparable.

What’s novel:
1. Retrieval is a real task. The tool has to find the right policy among similar-sounding ones, and ignore distractors, rather than being handed it.
2. Cross-document reasoning. Policies depend on each other and on patient history. For example, nerve stimulation requires that PAP was tried first, and the bi-level device requires that the standard device failed.
3. Abstention. The tool should answer “insufficient information” when the record lacks evidence, rather than guessing “met.”
4. Evaluation that separates where it fails. Retrieval is scored on its own (did it find the right policy?), and so is reasoning (given the right policy, was the verdict right?). This is paired with a comparison of handing the LLM the correct policy versus making it retrieve the policy.
5. Controlled ground truth. Synthetic patients are edited to meet, fail, or lack each criterion, so the correct answers are known by construction. One held-out policy is reserved for testing whether it generalizes.

Steps:
Phase 1: Policy data
1. Finish the download script. Fetch each LCD in your frozen ID list, with its contractors, related documents, and related NCDs, and save the raw JSON.
2. Write the cleaning script. Turn each raw file into a clean JSON with metadata (ID, version, title, status, contractors, related IDs) and HTML-free text sections.
3. Spot-check the cleaned files. Open a few, including L33718, and confirm the criteria text reads correctly and nothing important was dropped.

Phase 2: Vector store
4. Decide how to chunk. Split each policy into pieces small enough to retrieve precisely, ideally along section boundaries, so a chunk doesn’t mix unrelated rules.
5. Load into Chroma. Embed each chunk and store it with metadata (LCD ID, title, section), so results can be cited and filtered.
6. Sanity-check retrieval by hand. Try a few queries like “CPAP coverage criteria” and confirm the PAP policy ranks above the distractors.

Phase 3: Test cases
7. Generate base patients with Synthea. Create a small set of FHIR patients to use as realistic starting points.
8. Write the PAP criteria checklist. List each criterion from L33718 as a discrete item (AHI threshold, prior evaluation, symptoms for AHI 5–14, and so on) to serve as your answer-key structure.
9. Build case variants and the answer key. Edit each base patient so each criterion is met, not met, or missing, and record the correct verdict as you make each edit. Pair each case with an order like E0601.
10. Validate the cases. Check that each edited record contains exactly what the answer key says, before any model sees it.

Phase 4: The pipeline
11. Set up the LLM API. Get an API key, store it in .env, and make one test call.
12. Prepare the patient summary. Convert a FHIR record into a compact text summary of the relevant facts (diagnoses, sleep tests, visits), so the LLM isn’t overwhelmed by the full record.
13. Retrieve the policy. Given the order and patient summary, query Chroma and return the top matching policy chunks.
14. Judge the criteria. Have the LLM extract the criteria from the retrieved policy and give a verdict for each (met / not met / insufficient), with cited evidence, as structured JSON.

Phase 5: Evaluation
15. Score retrieval. Measure how often the correct policy appears in the top results (recall@k), separately from everything else.
16. Score the verdicts. Compare each criterion’s verdict against the answer key, tracking accuracy and how often the model correctly said “insufficient” instead of guessing.
17. Run the comparison. Repeat the evaluation with the correct policy handed directly to the LLM, to measure how much retrieval costs.
18. Test the held-out policy. Build a few cases for a policy you didn’t develop with, to check whether the pipeline generalizes.

Phase 6: Web app and write-up
19. Add the FastAPI page. A form to upload a patient record and enter an order, with results showing each verdict and its evidence.
20. Write the README. Describe the tool, the evaluation design, and the results, including any null or disappointing findings, as you did in your other projects.