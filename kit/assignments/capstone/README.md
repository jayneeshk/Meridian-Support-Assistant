# Meridian Support Assistant

The Meridian Support Assistant helps bank staff answer policy, account-status, and fee questions using a grounded offline retrieval layer. It is designed for frontline support teams, branch operators, and payments analysts who need fast and auditable responses without exposing customer data. The assistant does not initiate money movement on its own, it does not disclose hidden prompts, and it does not allow untrusted data to bypass the bank's approval process.

The system combines a retrieval-augmented policy index, workflow-safe tools, least-privilege role checks, and a tamper-evident audit trail. A lurking prompt injection in a policy document is stripped before retrieval and answer generation. The tool layer validates account IDs, fee types, and escalation flows before performing business actions. In every request, the assistant records a trace and a chained audit entry so a supervisor can verify what was seen, what was used, and what was blocked.

This solution intentionally stays offline. All retrieval and evaluation happen against the provided Meridian Bank corpus and local harness data, so the app can run on a laptop with no cloud or paid account. It keeps the human in the loop for approvals, fraud escalations, and all risk-bearing decisions. The app is designed to degrade gracefully during outages by handing off to a person instead of crashing or leaking data.

## Run it

From ``assignments/capstone`` run the main demo, the outage simulation, and the public tests:

```bash
python app.py --demo
GAMEDAY_FAULT=tool_outage python app.py --demo
python -m pytest -q
python -m autograde.run --capstone --root ..
python eval_gate.py reports/eval_after.json --min faithfulness=0.7 --max latency_p95_ms=500
```

## Layout

- ``a2_rag.py``: document chunking, retrieval, citation selection.
- ``a4_tools.py``: account lookup, fee calculations, escalation, and policy search wrappers.
- ``a4_agent.py``: routing logic for status, fee, policy, and escalation requests.
- ``a7_guard.py``: injection detection, sanitization, PII redaction, and authorization.
- ``a7_audit.py``: hash-chained audit logging and verification.
- ``a7_resilience.py``: retry, timeout budget, and circuit breakers.
- ``a6_evals.py``: metrics, tracing, and evaluation utilities.
- ``eval_gate.py``: CI-ready pass/fail gate for evaluation reports.
- ``docs/``: architecture, runbook, governance, business case.
- ``reports/``: baseline and post-change evaluation artifacts.
- ``traces/``: exported JSONL spans.
- ``audit/``: append-only tamper-evident audit log.

## Design choices

The retrieval stack supports fixed, section-based, and sentence-aware chunking. Chunk sizes are bounded while section headings and document titles remain attached for context. Retrieval can use BM25, deterministic dense hashing, or reciprocal-rank fusion; superseded documents are excluded by default, with an explicit option to include them for comparison. Answers cite the sources of the selected supporting sentences, and unsupported questions abstain. The request path is ordered deliberately: role checks, retrieval, context sanitization, tool validation, and then a grounded answer. This reduces the chance that an untrusted snippet can influence the model or that a user can trigger a real action without authorization.

## Evaluate

The evaluation dataset mixes account-status questions, fee questions, and policy questions with hidden attack prompts. Baseline and after reports show whether quality improved and whether safety and latency stayed within the agreed thresholds. The metrics measure faithfulness, context recall, answer relevance, and tool-call accuracy, but they do not replace a human risk review for operational changes, new policy areas, or sanctions exceptions.

## Operate

For live health checks, read ``docs/runbook.md``. A healthy system shows a passing evaluation gate, app demo success, an audit log that verifies, and no failed circuit-breaker or tool-outage warnings in the trace output.
