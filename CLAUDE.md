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