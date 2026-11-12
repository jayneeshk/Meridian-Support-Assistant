"""Optional offline knowledge graph extraction and retrieval."""
from __future__ import annotations

import json
import re

import networkx as nx
from pydantic import BaseModel, Field, ValidationError

from harness.corpus import load_corpus


class Entity(BaseModel):
    name: str
    type: str
    aliases: list[str] = Field(default_factory=list)


class Triple(BaseModel):
    head: str
    relation: str
    tail: str


class Extraction(BaseModel):
    entities: list[Entity]
    triples: list[Triple]


def _extract_json(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.I | re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("model output did not contain a complete JSON object")
    return text[start:end + 1]


def extract_triples(text, doc_id, llm, max_retries=2):
    prompt = (
        "Extract entities and factual triples from the document text below. "
        "Return JSON with entities (name, type, aliases) and triples (head, relation, tail). "
        "Use canonical entity names where possible.\n"
        f"DOC_ID: {doc_id}\n"
        f"TEXT:\n{text}"
    )
    last_error = "extraction failed"
    for _ in range(max(0, int(max_retries)) + 1):
        try:
            raw = llm.complete(prompt)
            data = json.loads(_extract_json(raw))
            validated = Extraction.model_validate(data)
            return {
                "entities": [entity.model_dump() for entity in validated.entities],
                "triples": [triple.model_dump() for triple in validated.triples],
            }
        except (ValueError, TypeError, json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
    return {"entities": [], "triples": [], "error": last_error}


def build_graph(corpus_dir, llm):
    graph = nx.MultiDiGraph()
    aliases = {}
    pending_triples = []

    for doc in load_corpus(corpus_dir):
        extracted = extract_triples(doc.text, doc.doc_id, llm)
        if extracted.get("error"):
            continue
        for entity in extracted["entities"]:
            canonical = entity["name"].strip()
            if not canonical:
                continue
            graph.add_node(canonical, type=entity["type"], aliases=list(entity.get("aliases") or []))
            aliases[canonical.casefold()] = canonical
            for alias in entity.get("aliases") or []:
                aliases[alias.casefold()] = canonical
        pending_triples.extend((triple, doc.doc_id) for triple in extracted["triples"])

    def canonicalize(name):
        value = name.strip()
        return aliases.get(value.casefold(), value)

    for triple, source_doc in pending_triples:
        head = canonicalize(triple["head"])
        tail = canonicalize(triple["tail"])
        if head not in graph:
            graph.add_node(head, type="Fact", aliases=[])
        if tail not in graph:
            graph.add_node(tail, type="Fact", aliases=[])
        if graph.has_edge(head, tail):
            if any(data.get("relation") == triple["relation"] for data in graph.get_edge_data(head, tail).values()):
                continue
        graph.add_edge(head, tail, relation=triple["relation"], source_doc=source_doc)
    return graph


def graph_retrieve(graph, question, hops=3):
    q = question.casefold()
    seeds = set()
    for name, attrs in graph.nodes(data=True):
        candidates = [name, *(attrs.get("aliases") or [])]
        if any(re.search(r"(?<!\w)" + re.escape(candidate.casefold()) + r"(?!\w)", q) for candidate in candidates if candidate):
            seeds.add(name)
    if not seeds:
        return []

    distances = {node: 0 for node in seeds}
    frontier = set(seeds)
    for distance in range(1, max(0, int(hops)) + 1):
        next_frontier = set()
        for node in frontier:
            next_frontier.update(graph.predecessors(node))
            next_frontier.update(graph.successors(node))
        next_frontier -= distances.keys()
        for node in next_frontier:
            distances[node] = distance
        frontier = next_frontier
        if not frontier:
            break

    evidence = []
    for head, tail, _, attrs in graph.edges(keys=True, data=True):
        if head in distances and tail in distances and min(distances[head], distances[tail]) < max(1, int(hops)):
            evidence.append({
                "head": head,
                "relation": attrs["relation"],
                "tail": tail,
                "source_doc": attrs["source_doc"],
            })
    return evidence
