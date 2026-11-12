# Decision log

- Chose a local retrieval-and-tool architecture to remain offline and zero-cost.
- Kept human approval for transfers and fraud workflows because those are business-critical decisions.
- Added prompt sanitization and a strict role matrix to reduce prompt-injection risk.
- Used a tamper-evident audit log so support and operations teams can verify what happened.
