# Governance summary

Meridian Bank uses the support assistant under a clear governance model. The assistant is approved for read-only policy support, account-status lookup for permitted roles, and fee lookups in standard cases. It is not approved to initiate transfers or approve exceptions without a human sign-off. The access model is defined in the authorization matrix and is enforced before any tool call is attempted.

The project keeps all data synthetic and offline. The retrieval index is local, the policy corpus is a fictional bank dataset, and all user-facing outputs are filtered for PII before being written to logs or shown back to a user. In addition, the app captures traces and audit entries in a tamper-evident form so that records can be reviewed after the fact.

Governance responsibilities are split between operations, product, and compliance review. Operations checks that the app stays online and meets the evaluation thresholds. Product checks that the routing logic matches the policy and business process. Compliance reviews the audit trail and the human-in-the-loop boundaries for unusual or high-risk requests.

The expected control posture is conservative. When a question falls outside the known policy space or the tool layer is unavailable, the assistant hands the request to a person rather than guessing. This keeps the service aligned with the risk profile of a regulated bank support process while still enabling faster answers for common requests.
