import pytest
from pathlib import Path
from denial_validator import *

def test_valid_file_passes():
    text = "ISA*00~GS*HP~ST*835*0001~BPR*I~SE*3*0001~GE*1*1~IEA*1*1~"
    ok, msg = structure_check(get_segments(text))
    assert ok

def test_missing_se_fails():
    text = "ISA*00~GS*HP~ST*835*0001~BPR*I~GE*1*1~IEA*1*1~"
    ok, msg = structure_check(get_segments(text))
    assert not ok

@pytest.fixture(scope="module")
def sample_835():
    path = Path(__file__).parent / "data" / "sample.835"
    return path.read_text()

def test_sample_passes(sample_835):
    ok, msg = structure_check(get_segments(sample_835))
    assert ok

def test_missing_se_fails(sample_835):
    segments = get_segments(sample_835)
    segments = [s for s in segments if not s.startswith("SE*")]
    ok, msg = structure_check(segments)
    assert not ok