# Runbook - Meridian Support Assistant

## 1. What this system does
The Meridian Support Assistant helps staff answer routine bank questions using a local set of policy documents and validated business tools. It supports account-status checks, fee lookups, and safe policy guidance while keeping users within the authorization matrix. It never performs money movement or disclosures without the appropriate human approval path.

## 2. Start / stop / health check
Run the demo from the assignment folder to confirm the app loads and responds correctly. A healthy system shows a printed answer for each prompt, an exported trace, and a valid audit log. If you need to stop the service, terminate the Python process and revert to the last stable build. Use the evaluation gate to confirm the current regression status before a release.

## 3. Dashboards and signals
Monitor the evaluation gate, trace export, and audit verification results every time the system changes. The first signals to check are latency p95, cost per request, faithfulness, tool-call accuracy, and the circuit-breaker state. If a tool outage event occurs, the app should log a degraded mode and route the issue to a human.

## 4. Troubleshooting guide
| Symptom | Likely root cause | How to confirm | Fix |
|---|---|---|---|
| Retrieval answer is weak or off-topic | index drift or poor chunking | inspect the trace and the retrieved document IDs | reindex and verify the chunking strategy |
| App crashes under a forced outage | degraded-mode path not loaded | run with GAMEDAY_FAULT=tool_outage | check the outage branch and ensure fallback is safe |
| Audit check fails | edited or deleted log entry | run AuditLog.verify() on the audit file | restore from the last known-good log or regenerate from trusted traces |
| PII appears in output | redaction missed a pattern | search the log for names, email, or phone fragments | update the redaction rules and re-run the demo |

## 5. Escalation
Escalate to the platform owner when a trace shows repeated failures, a circuit breaker is stuck open, or a business action is outside the allowed policy set. Use a severity-based response: low for read-only issues, medium for missed policy answers, and high for anything that touches fraud, money movement, or a broken approval gate.

## 6. Rollback and safe-mode
If a release looks risky, revert to the previous stable build and run the offline app demo again. In a live emergency, force the system into human approval and disable the risky tool path until the cause is diagnosed. The safest fallback is to turn off automatic execution, preserve the trace, and route the request to a real agent.

## 7. Known issues and limitations
This system is intentionally conservative for money movement. It can answer support questions from the local corpus but cannot replace formal legal or compliance review for sanctions, fraud investigations, or exceptional exceptions. Real production deployment should include a broader dataset, stronger monitoring, and an explicit human sign-off policy.
