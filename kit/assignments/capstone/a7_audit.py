"""Capstone R7 - tamper-evident audit log."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from a7_guard import redact_pii


class AuditLog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entries = []
        self._reload()

    def _reload(self):
        self._entries = []
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            self._entries.append(entry)

    def _redact_args(self, value):
        if isinstance(value, dict):
            return {
                k: v if isinstance(v, str) and k.lower().endswith(("_hash", "_digest")) else self._redact_args(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self._redact_args(v) for v in value]
        if isinstance(value, str):
            return redact_pii(value)
        return value

    def _hash_entry(self, entry):
        payload = {k: v for k, v in entry.items() if k != "hash"}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def append(self, trace_id, user, tool, args, sources, outcome):
        self._reload()
        seq = len(self._entries)
        now = datetime.now(timezone.utc).isoformat()
        prev_hash = self._entries[-1]["hash"] if self._entries else "0" * 64
        entry = {
            "seq": seq,
            "ts": now,
            "trace_id": trace_id,
            "user": user,
            "tool": tool,
            "args": self._redact_args(args),
            "sources": list(sources or []),
            "outcome": outcome,
            "prev_hash": prev_hash,
        }
        entry["hash"] = self._hash_entry(entry)
        self._entries.append(entry)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
        return entry

    def entries(self):
        self._reload()
        return [dict(e) for e in self._entries]

    def verify(self):
        entries = self.entries()
        for idx, entry in enumerate(entries):
            recomputed = self._hash_entry(entry)
            if recomputed != entry.get("hash"):
                return {"ok": False, "first_bad": idx, "entries": len(entries)}
            if idx != entry.get("seq"):
                return {"ok": False, "first_bad": idx, "entries": len(entries)}
            if idx == 0:
                if entry.get("prev_hash") != "0" * 64:
                    return {"ok": False, "first_bad": idx, "entries": len(entries)}
            else:
                if entry.get("prev_hash") != entries[idx - 1].get("hash"):
                    return {"ok": False, "first_bad": idx, "entries": len(entries)}
        return {"ok": True, "first_bad": None, "entries": len(entries)}
