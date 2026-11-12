# Game-day report

The game-day drill tested the system under a forced tool outage and confirmed the assistant degrades safely. The request path remained operational, but the tool layer was intentionally disabled to simulate a vendor or integration failure. The app responded with a degraded status message and passed the request to a human reviewer without crashing or exposing a partial answer. This outcome is the desired behavior because the bank must never proceed with a transfer or a fraud decision without an approved handoff.

The drill also checked that the retrieval layer, guardrails, and audit trail still behaved as expected. The retrieval path stayed available for harmless policy questions, the redaction layer handled the test prompts correctly, and the trace file continued to export to disk. The audit log remained verifiable and preserved the source documents associated with the degraded request.

The main lesson from the drill is that resilience and human review are as important as latency and accuracy. A degraded answer is acceptable when the system remains safe and transparent; a silent crash or a hallucinated action is not acceptable. We will keep this safe fallback as the default for any outage.
