import pytest
from policy_store import chroma_path, query_policies

#these tests search the built Chroma store, which is gitignored, so they skip
#anywhere it hasn't been built (e.g. CI). Build it with: python policy_store.py
pytestmark = [
    pytest.mark.retrieval,
    pytest.mark.skipif(not chroma_path.exists(), reason="vector store not built"),
]

PAP_POLICY = 33718
HNS_POLICIES = {38276, 38307, 38310, 38385, 38387, 38398, 38528}

def get_policy_ranking(query):
    """Helper function that returns the LCD ids for a query, best match first, each listed once"""
    ranking = []
    for result in query_policies(query, n_results=50):
        if result["lcd_id"] not in ranking:
            ranking.append(result["lcd_id"])
    return ranking

def test_cpap_with_code_finds_pap_policy():
    """Tests that a CPAP query with its order code puts the PAP policy in the top 3
    (the same query without the code is test_cpap_without_code_finds_pap_policy)"""
    ranking = get_policy_ranking("E0601 CPAP coverage criteria")
    assert PAP_POLICY in ranking[:3]

def test_cpap_code_alone_finds_pap_policy():
    """Tests that the bare order code puts the PAP policy in the top 3"""
    ranking = get_policy_ranking("E0601")
    assert PAP_POLICY in ranking[:3]

def test_bilevel_code_finds_pap_policy():
    """Tests that a bi-level order after CPAP failure puts the PAP policy in the top 3"""
    ranking = get_policy_ranking("E0470 bi-level device after E0601 CPAP failed")
    assert PAP_POLICY in ranking[:3]

def test_oxygen_with_pap_finds_pap_policy():
    """Tests that oxygen with PAP therapy ranks the PAP policy first"""
    ranking = get_policy_ranking("home oxygen with PAP therapy")
    assert ranking[0] == PAP_POLICY

def test_hns_query_finds_hns_policy():
    """Tests that a hypoglossal nerve stimulation query ranks an HNS policy first"""
    ranking = get_policy_ranking("hypoglossal nerve stimulation BMI requirement")
    assert ranking[0] in HNS_POLICIES

@pytest.mark.xfail(reason="known weakness: the PAP policy rarely says 'CPAP', so a query without the code misses it")
def test_cpap_without_code_finds_pap_policy():
    """Tests that a plain-English CPAP query puts the PAP policy in the top 3"""
    ranking = get_policy_ranking("CPAP coverage criteria")
    assert PAP_POLICY in ranking[:3]
