# Conversation memory design

## Short-term and long-term memory

The conversation window is short-term memory: recent user and assistant turns are kept verbatim, in order, while they fit the configured token budget. Pinned facts are persistent context and are included in every system message. Older conversational turns are summarized rather than retained verbatim, which provides a compact continuity mechanism without treating the transcript as an unlimited store.

## Episodic and semantic information

The running summary is episodic memory: it records what happened earlier in the current conversation. Pinned key-value facts are semantic memory: stable information such as an account identifier or preferred language that must remain available across turns. This implementation does not infer or persist new long-term facts automatically; callers explicitly pin the facts they are authorized to preserve.

## Budget and summarization

The memory manager estimates prompt size with the harness token counter. It drops the oldest turns first until the system context and newest verbatim turns fit. When a turn leaves the active window, the summarizer updates the running summary. The summary is not recomputed when `get_context()` is repeated without new changes, and recent turns remain in chronological order.

## Privacy and retention

Callers should pin only the minimum non-sensitive facts needed for the active task. Conversation memory is in-process and is not written to the audit log or disk. It should be discarded when the conversation ends, and callers must not pin passwords, payment-card data, authentication secrets, or unnecessary personal details. The production policy should define an explicit retention period before any persistent memory is introduced.
