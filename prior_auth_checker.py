from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic()

def summarize_fhir_record():
    pass

#retrieve the policy (get top 3-5 matching chunks) - already done in policy_store.query_policies()?

def judge_critiera():
    pass