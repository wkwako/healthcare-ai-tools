import pytest
from pathlib import Path
from denial_validator import *

def load_and_check_file(name):
    """Helper function that loads a file and returns its segments"""
    path = Path(__file__).parent / "sample_835s" / name
    text = path.read_text()
    segments = get_segments(text)
    return segments

def test_valid_file_passes():
    """Tests that a valid file doesn't error"""
    segments = load_and_check_file("valid.835")
    ok, msg = structure_check(segments)
    assert ok

def test_missing_st_fails():
    """Tests that a missing ST segment errors"""
    segments = load_and_check_file("one_missing_st.835")
    ok, msg = structure_check(segments)
    assert not ok

def test_denial_balance():
    """Tests that a valid denial passes balance checks"""
    segments = load_and_check_file("valid.835")
    ok, msg = structure_check(segments)
    assert ok

def test_valid_multi_adjustment():
    """Tests that a valid file with multiple line-level adjustments passes balance tests"""
    segments = load_and_check_file("multi_adjustment.835")
    ok, msg = balance_check(segments)
    assert ok

def test_partial_payments():
    """Tests that a valid file with partial payments passes balance tests"""
    segments = load_and_check_file("partial_payments.835")
    ok, msg = balance_check(segments)
    assert ok

def test_multi_adjustment_mismatch1():
    """Tests that a file with multiple adjustments and a payment mismatch errors (CLP element too large)"""
    segments = load_and_check_file("multi_adjustment_mismatchCLP.835")
    ok, msg = balance_check(segments)
    assert not ok

def test_multi_adjustment_mismatch2():
    """Tests that a file with multiple adjustments and a payment mismatch errors (CAS element too large)"""
    segments = load_and_check_file("multi_adjustment_mismatchCAS.835")
    ok, msg = balance_check(segments)
    assert not ok

def test_partial_payment_mismatch1():
    """Tests that a file with a partial payment and a payment mismatch errors (CLP element too large)"""
    segments = load_and_check_file("partial_payments_mismatchCLP.835")
    ok, msg = balance_check(segments)
    assert not ok

def test_partial_payment_mismatch2():
    """Tests that a file with a partial payment and a payment mismatch errors (CAS element too large)"""
    segments = load_and_check_file("partial_payments_mismatchCAS.835")
    ok, msg = balance_check(segments)
    assert not ok

def test_valid_plb():
    """Tests a valid file with PLB adjustments, including multiple adjustments on the same line, multiple PLB segments, and negative amounts."""
    segments = load_and_check_file("valid_plbs.835")
    ok, msg = balance_check(segments)
    assert ok

def test_():
    """Tests PLBs for a file with an incorrect BPR02 element."""
    segments = load_and_check_file("plb_test_bpr02_mismatch.835")
    ok, msg = balance_check(segments)
    assert not ok

def test_empty_file():
    """Tests that an empty file errors"""
    text = ""
    ok, msg = structure_check(get_segments(text))
    assert not ok

@pytest.fixture(scope="module")
def valid_835():
    """Loads a valid 835, makes it globally accessible to pytest methods"""
    path = Path(__file__).parent / "sample_835s" / "valid.835"
    return path.read_text()

def test_missing_se_fails(valid_835):
    """Tests that a file with a missing SE segment errors"""
    segments = get_segments(valid_835)
    segments = [s for s in segments if not s.startswith("SE*")]
    ok, msg = structure_check(segments)
    assert not ok

def test_all_missing_st_fails(valid_835):
    """Tests that a file with all missing ST segments errors"""
    segments = get_segments(valid_835)
    segments = [s for s in segments if not s.startswith("ST*")]
    ok, msg = structure_check(segments)
    assert not ok

def test_missing_isa_fails(valid_835):
    """Tests that a file with a missing ISA segment errors"""
    segments = get_segments(valid_835)
    segments = [s for s in segments if not s.startswith("ISA*")]
    ok, msg = structure_check(segments)
    assert not ok

def test_missing_iea_fails(valid_835):
    """Tests that a file with a missing IEA segment errors"""
    segments = get_segments(valid_835)
    segments = [s for s in segments if not s.startswith("IEA*")]
    ok, msg = structure_check(segments)
    assert not ok

def test_lower_segment_count(valid_835):
    """Tests that a file with a segment missing in an ST/SE envelope errors"""
    segments = get_segments(valid_835)
    segments = [s for s in segments if not s.startswith("NM1*")]
    ok, msg = structure_check(segments)
    assert not ok

def test_higher_segment_count(valid_835):
    """Tests that a file with an extra segment in an ST/SE envelope errors"""
    segments = get_segments(valid_835)
    segments.insert(20,"Extra line")
    ok, msg = structure_check(segments)
    assert not ok