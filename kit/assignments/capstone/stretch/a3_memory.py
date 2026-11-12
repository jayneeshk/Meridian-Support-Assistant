"""Conversation memory with pinned facts and a bounded short-term window."""
from __future__ import annotations

from harness.text import count_tokens


class ConversationMemory:
    def __init__(self, max_tokens, summarizer):
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer")
        if not callable(summarizer):
            raise TypeError("summarizer must be callable")
        self.max_tokens = max_tokens
        self.summarizer = summarizer
        self._turns = []
        self._pins = {}
        self._dropped = []
        self._summary = ""
        self._context_cache = None

    def add(self, role, content):
        if role not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")
        self._turns.append({"role": role, "content": str(content)})
        self._context_cache = None

    def pin(self, key, value):
        if not isinstance(key, str) or not key.strip():
            raise ValueError("pin key must be a non-empty string")
        self._pins[key] = str(value)
        self._context_cache = None

    def _system_message(self):
        parts = ["Persistent facts:"] if self._pins else []
        parts.extend(f"{key}: {value}" for key, value in self._pins.items())
        if self._summary:
            parts.append(f"Summary of earlier turns: {self._summary}")
        return {"role": "system", "content": "\n".join(parts) or "Conversation context."}

    def get_context(self):
        if self._context_cache is not None:
            return [dict(message) for message in self._context_cache]

        dropped_now = []
        while True:
            system = self._system_message()
            candidate = [system, *self._turns]
            total = sum(count_tokens(message["content"]) for message in candidate)
            if total <= self.max_tokens or not self._turns:
                break
            dropped_now.append(self._turns.pop(0))

        if dropped_now:
            self._dropped.extend(dropped_now)
            self._summary = self.summarizer(list(self._dropped))
            system = self._system_message()
            while self._turns and sum(count_tokens(m["content"]) for m in [system, *self._turns]) > self.max_tokens:
                self._dropped.append(self._turns.pop(0))
                self._summary = self.summarizer(list(self._dropped))
                system = self._system_message()

        result = [self._system_message(), *self._turns]
        while self._turns and sum(count_tokens(m["content"]) for m in result) > self.max_tokens:
            self._dropped.append(self._turns.pop(0))
            self._summary = self.summarizer(list(self._dropped))
            result = [self._system_message(), *self._turns]
        self._context_cache = result
        return [dict(message) for message in result]
