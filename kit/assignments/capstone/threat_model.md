# Threat model

This system treats prompt injection, unsafe tool execution, and data leakage as primary risks. The most dangerous path is a malicious snippet in a policy document instructing the model to reveal internal secrets or bypass approvals. The guardrail strips malicious lines before answer generation, and the policy layer keeps the assistant grounded to the safe subset of text.

Additional risks include accidental PII leakage into logs and unauthorized access to financial workflows. PII is redacted before writing logs, and tool permissions are limited by role. The system also records each request in a chained audit log to support investigation and review.
