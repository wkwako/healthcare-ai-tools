import pytest
from pathlib import Path
from denial_validator import *

def load_and_check_file(name):
    path = Path(__file__).parent / "sample_835s" / name
    text = path.read_text()
    segments = get_segments(text)
    ok, msg = structure_check(segments)
    return ok, msg

def test_valid_file_passes():
    ok, msg = load_and_check_file("valid.835")
    assert ok

def test_missing_st_fails():
    ok, msg = load_and_check_file("one_missing_st.835")
    assert not ok

def test_empty_file():
    text = ""
    ok, msg = structure_check(get_segments(text))
    assert not ok

@pytest.fixture(scope="module")
def valid_835():
    path = Path(__file__).parent / "sample_835s" / "valid.835"
    return path.read_text()

def test_missing_se_fails(valid_835):
    segments = get_segments(valid_835)
    segments = [s for s in segments if not s.startswith("SE*")]
    ok, msg = structure_check(segments)
    assert not ok

def test_all_missing_st_fails(valid_835):
    segments = get_segments(valid_835)
    segments = [s for s in segments if not s.startswith("ST*")]
    ok, msg = structure_check(segments)
    assert not ok

def test_missing_isa_fails(valid_835):
    segments = get_segments(valid_835)
    segments = [s for s in segments if not s.startswith("ISA*")]
    ok, msg = structure_check(segments)
    assert not ok

def test_missing_iea_fails(valid_835):
    segments = get_segments(valid_835)
    segments = [s for s in segments if not s.startswith("IEA*")]
    ok, msg = structure_check(segments)
    assert not ok

def test_lower_segment_count(valid_835):
    segments = get_segments(valid_835)
    segments = [s for s in segments if not s.startswith("NM1*")]
    ok, msg = structure_check(segments)
    assert not ok

def test_higher_segment_count(valid_835):
    segments = get_segments(valid_835)
    segments.insert(20,"Extra line")
    ok, msg = structure_check(segments)
    assert not ok