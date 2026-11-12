"""Capstone R4 - tracing and evaluation metrics."""
from __future__ import annotations
import json
import math
import time
import uuid

from harness.text import HashingEmbedder, cosine, tokenize


def _nearest_rank(values, percentile):
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(1, math.ceil((percentile / 100.0) * len(ordered))) - 1
    return float(ordered[min(idx, len(ordered) - 1)])


def context_precision(retrieved, gold):
    retrieved = list(retrieved)
    gold_set = set(gold)
    if not gold_set:
        return 0.0
    relevant = []
    for idx, doc_id in enumerate(retrieved, start=1):
        if doc_id in gold_set:
            relevant.append(sum(1 for x in retrieved[:idx] if x in gold_set) / idx)
    return sum(relevant) / len(relevant) if relevant else 0.0


def context_recall(retrieved, gold):
    if not gold:
        return 0.0
    gold_set = set(gold)
    return len(set(retrieved) & gold_set) / len(gold_set)


def faithfulness(answer, contexts, threshold=0.6):
    if not answer or not contexts:
        return 0.0
    context_tokens = set(tokenize(" ".join(contexts)))
    sentences = [s.strip() for s in answer.replace("\n", ". ").split(".") if s.strip()]
    counted = 0
    supported = 0
    for sentence in sentences:
        toks = tokenize(sentence)
        if not toks:
            continue
        counted += 1
        overlap = sum(1 for t in toks if t in context_tokens)
        if overlap / len(toks) >= threshold:
            supported += 1
    if counted == 0:
        return 0.0
    return supported / counted


def answer_relevance(question, answer):
    if not answer:
        return 0.0
    emb = HashingEmbedder()
    qv = emb.embed(question)
    av = emb.embed(answer)
    return float(cosine(qv, av))


def tool_call_accuracy(expected, actual):
    if not expected and not actual:
        return 1.0
    if not expected or not actual:
        return 0.0

    def matches(exp, act):
        if act.get("name") != exp.get("name"):
            return False
        actual_args = act.get("args") or {}
        return all(actual_args.get(key) == value for key, value in (exp.get("args") or {}).items())

    # Longest common subsequence rewards correct calls in order while penalising extras.
    rows, cols = len(expected), len(actual)
    scores = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(1, rows + 1):
        for j in range(1, cols + 1):
            if matches(expected[i - 1], actual[j - 1]):
                scores[i][j] = scores[i - 1][j - 1] + 1
            else:
                scores[i][j] = max(scores[i - 1][j], scores[i][j - 1])
    return scores[rows][cols] / max(rows, cols)


def run_eval(system_fn, dataset, clock=time.perf_counter, usd_per_1k_tokens=0.002):
    per_sample = []
    latencies = []
    tokens_in_total = 0
    tokens_out_total = 0
    metric_values = {"context_precision": [], "context_recall": [], "faithfulness": [], "answer_relevance": [], "tool_call_accuracy": []}

    for sample in dataset:
        start = clock()
        result = system_fn(sample["question"])
        end = clock()
        latencies.append((end - start) * 1000.0)
        tokens_in_total += int(result.get("tokens_in", 0))
        tokens_out_total += int(result.get("tokens_out", 0))
        gold_docs = sample.get("gold_docs") or []
        retrieved_ids = result.get("retrieved_ids") or []
        if gold_docs:
            metric_values["context_precision"].append(context_precision(retrieved_ids, gold_docs))
            metric_values["context_recall"].append(context_recall(retrieved_ids, gold_docs))
        if result.get("contexts"):
            metric_values["faithfulness"].append(faithfulness(result.get("answer") or "", result.get("contexts") or []))
        if result.get("answer"):
            metric_values["answer_relevance"].append(answer_relevance(sample["question"], result["answer"]))
        if "expected_tool_calls" in sample:
            metric_values["tool_call_accuracy"].append(tool_call_accuracy(sample["expected_tool_calls"], result.get("tool_calls") or []))
        per_sample.append({
            "id": sample.get("id"),
            "question": sample.get("question"),
            "latency_ms": (end - start) * 1000.0,
            "answer": result.get("answer") or "",
            "retrieved_ids": retrieved_ids,
            "tool_calls": result.get("tool_calls") or [],
            "tokens_in": int(result.get("tokens_in", 0)),
            "tokens_out": int(result.get("tokens_out", 0)),
        })

    metrics = {}
    for key, values in metric_values.items():
        if values:
            metrics[key] = sum(values) / len(values)
    metrics = {k: v for k, v in metrics.items() if v is not None}
    return {
        "n": len(dataset),
        "metrics": metrics,
        "latency_ms": {"p50": _nearest_rank(latencies, 50), "p95": _nearest_rank(latencies, 95)},
        "tokens": {"in": tokens_in_total, "out": tokens_out_total},
        "sim_cost_usd": ((tokens_in_total + tokens_out_total) / 1000.0) * usd_per_1k_tokens,
        "per_sample": per_sample,
    }


def analyze_trace(path_or_spans):
    spans = path_or_spans
    if isinstance(path_or_spans, str):
        with open(path_or_spans, "r", encoding="utf-8") as fh:
            spans = [json.loads(line) for line in fh if line.strip()]
    if not spans:
        return {"total_ms": 0, "slowest_span": None, "slowest_ms": 0, "duplicate_calls": [], "total_tokens": 0, "span_count": 0}

    root = next((s for s in spans if s.get("parent_id") is None), None)
    if root is None:
        root = spans[0]
    total_ms = float(root.get("end_ms", 0.0) - root.get("start_ms", 0.0))
    children = [s for s in spans if s is not root]
    slowest = max(children, key=lambda s: (s.get("end_ms", 0.0) - s.get("start_ms", 0.0)), default=root)
    slowest_ms = float(slowest.get("end_ms", 0.0) - slowest.get("start_ms", 0.0)) if slowest is not root else 0.0

    counts = {}
    for s in children:
        if s.get("attrs", {}).get("input") is not None:
            key = (s.get("name"), json.dumps(s.get("attrs", {}).get("input"), sort_keys=True))
            counts[key] = counts.get(key, 0) + 1
    duplicate_calls = []
    by_name = {}
    for s in children:
        if s.get("attrs", {}).get("input") is not None:
            name = s.get("name")
            by_name[name] = by_name.get(name, 0) + 1
    for name, count in sorted(by_name.items(), key=lambda item: (-item[1], item[0])):
        if count > 1:
            duplicate_calls.append({"name": name, "count": count})

    total_tokens = sum(int(s.get("attrs", {}).get("tokens_in", 0)) + int(s.get("attrs", {}).get("tokens_out", 0)) for s in spans)
    return {"total_ms": total_ms, "slowest_span": slowest.get("name") if slowest is not root else None, "slowest_ms": slowest_ms, "duplicate_calls": duplicate_calls, "total_tokens": total_tokens, "span_count": len(spans)}


class Tracer:
    def __init__(self, clock=time.perf_counter):
        self.clock = clock
        self._base = self.clock()
        self.spans = []
        self._stack = []
        self._next_span_id = 0
        self.trace_id = uuid.uuid4().hex

    def span(self, name, **attrs):
        parent = self._stack[-1] if self._stack else None
        span_id = f"span-{self._next_span_id}"
        self._next_span_id += 1
        start_ms = (self.clock() - self._base) * 1000.0
        data = {"trace_id": self.trace_id, "span_id": span_id, "parent_id": parent["span_id"] if parent else None, "name": name, "start_ms": start_ms, "end_ms": None, "attrs": dict(attrs)}
        self.spans.append(data)
        self._stack.append(data)

        class _Scope:
            def __init__(self, tracer, span):
                self.tracer = tracer
                self.span = span

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                end_ms = (self.tracer.clock() - self.tracer._base) * 1000.0
                self.span["end_ms"] = end_ms
                if exc is not None:
                    self.span["attrs"]["error"] = exc.__class__.__name__
                self.tracer._stack.pop()
                return False

            def set(self, key, value):
                self.span["attrs"][key] = value

        scope = _Scope(self, data)
        return scope

    def to_jsonl(self, path):
        p = path
        if not hasattr(path, "write_text"):
            p = path
        with open(p, "w", encoding="utf-8") as fh:
            for s in self.spans:
                fh.write(json.dumps(s, sort_keys=True) + "\n")
