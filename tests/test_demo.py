import json
import pytest
import demo
from monitoring import validate_bundle

COMBINATIONS = [(case_id, order) for case_id in demo.PATIENTS for order in demo.ORDERS]

@pytest.mark.parametrize("case_id", demo.PATIENTS)
def test_demo_patient_is_valid(case_id):
    """Tests that each demo patient is a readable FHIR bundle whose answer key is for one of the demo orders"""
    errors, _ = validate_bundle(json.loads(demo.patient_path(case_id).read_text(encoding="utf-8")))
    assert not errors
    assert demo.answer_key(case_id)["order"]["code"] in demo.ORDERS

@pytest.mark.parametrize("case_id, order", COMBINATIONS)
def test_demo_result_is_current(case_id, order):
    """Tests that every patient/order combination has a result judged with the current model, prompts and schema.
    If this fails after changing the pipeline, run python demo.py to judge the out-of-date combinations again."""
    result = demo.cached_result(case_id, order)
    assert result is not None, f"no result for {case_id} with {order}: run python demo.py"
    assert demo.is_current(result, case_id), f"{case_id} with {order} is out of date: run python demo.py"
