# Business case: Meridian Bank support automation

**Stakeholder:** Support operations manager. **Process today:** branch staff and support analysts spend significant time answering repetitive questions about account status, fee rules, and approvals. Teams handle many low-risk requests manually, even when the answer is already present in a policy library. The dispatch path can take several minutes, and it introduces rework because the same question may be answered differently across teams.

## What the assistant does, and what stays human
The assistant answers policy-based questions, summarizes active fee information, and checks account status within the permitted role matrix. It also records the source documents used to answer the question, which makes coaching and review easier. What stays with a person is any step involving action on funds, fraud escalations, and exceptions that require a manager or analyst sign-off. The business rules for untrusted requests and dual control remain explicit and enforced by the system's authorization layer.

## Contradictions and policy gaps to resolve first
The stakeholder wants faster support, but bank policy still requires human enforcement for any transfer or fraud decision. A few operational questions are only answered in informal guidance, not in the formal written policy, so a human must confirm the final interpretation when the answer is ambiguous. Until those decisions are formalized, the assistant remains conservative and asks for approval instead of taking action.

## Metrics and assumptions
| Measure | Baseline | Target | Assumption |
|---|---|---|---|
| Time per routine policy request | 6-10 minutes | 1-2 minutes | Indexing and retrieval remain local and fast |
| Rework on policy answers | high | 30% lower | Similar questions are resolved from the same source set |
| Volume handled without human review | not measured | 60% | Most issues are low-risk and policy-driven |

## ROI as a range
A low estimate assumes a modest reduction in manual support work: 5-10 hours saved per week by the current support team. A high estimate assumes the assistant handles a large share of routine account and policy questions while freeing staff for escalations. The value comes from shorter turnaround times, lower rework, and more consistent source-backed answers.

## Weakest claim and pilot
The weakest assumption is that the policy corpus is clean and complete enough to answer real operational questions without a large human review backlog. A small pilot in a single support queue for fee and policy questions, limited to read-only tasks and with a two-week stop/go review, would test this without exposing the bank to unnecessary risk.
