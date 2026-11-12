# Demo reference

The live demo runs four representative Meridian Bank questions in a single pass: account status, fee lookup, policy guidance, and escalation. The assistant answers each question with source-grounded language and hums along in offline mode. During a tool outage, the same demo route degrades gracefully and shows a handoff message instead of crashing.

Suggested command sequence:

```bash
cd assignments/capstone
python app.py --demo
GAMEDAY_FAULT=tool_outage python app.py --demo
```

The expected behavior is a successful exit code and clean text output for the user questions. The outage variant should mention a degraded or fallback path and should not display any secret or internal prompt content.
