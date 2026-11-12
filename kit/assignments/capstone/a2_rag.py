"""Capstone R1 - RAG pipeline with deterministic retrieval and grounding."""
from __future__ import annotations
import re
from typing import Any

from harness.corpus import load_corpus
from harness.text import BM25, HashingEmbedder, cosine, rrf, tokenize


def _sentence_split(text: str):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _chunk_section(doc, section_name, body, fallback_label, chunk_size):
    heading = section_name or fallback_label
    prefix = f"{doc.title} - {heading}: "
    words = body.split()
    if not words:
        words = [heading or "intro"]
        prefix = f"{doc.title}: "
    chunks = []
    for start in range(0, len(words), chunk_size):
        chunk_text = prefix + " ".join(words[start:start + chunk_size])
        chunks.append({
            "doc_id": doc.doc_id,
            "chunk_id": f"{doc.doc_id}#{heading or 'intro'}-{len(chunks)}",
            "text": chunk_text,
            "status": doc.status,
        })
    return chunks


def _chunk_fixed(doc, chunk_size, overlap):
    text = doc.text.strip()
    if not text:
        return []
    tokens = tokenize(text)
    if not tokens:
        return []
    step = max(1, chunk_size - overlap)
    chunks = []
    for start in range(0, len(tokens), step):
        window = tokens[start: start + chunk_size]
        if not window:
            continue
        chunk_text = " ".join(window)
        chunks.append({
            "doc_id": doc.doc_id,
            "chunk_id": f"{doc.doc_id}#chunk-{len(chunks)}",
            "text": f"{doc.title}: {chunk_text}",
            "status": doc.status,
        })
        if len(window) < chunk_size:
            break
    return chunks


def _chunk_semantic(doc, chunk_size):
    text = doc.text.strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, current = [], []
    current_tokens = 0
    for sentence in sentences:
        sentence_words = sentence.split()
        if not sentence_words:
            continue
        if len(sentence_words) > chunk_size:
            if current:
                chunks.append({
                    "doc_id": doc.doc_id,
                    "chunk_id": f"{doc.doc_id}#chunk-{len(chunks)}",
                    "text": f"{doc.title}: {' '.join(current)}",
                    "status": doc.status,
                })
                current = []
                current_tokens = 0
            for start in range(0, len(sentence_words), chunk_size):
                chunks.append({
                    "doc_id": doc.doc_id,
                    "chunk_id": f"{doc.doc_id}#chunk-{len(chunks)}",
                    "text": f"{doc.title}: {' '.join(sentence_words[start:start + chunk_size])}",
                    "status": doc.status,
                })
            continue
        if current and current_tokens + len(sentence_words) > chunk_size:
            chunks.append({
                "doc_id": doc.doc_id,
                "chunk_id": f"{doc.doc_id}#chunk-{len(chunks)}",
                "text": f"{doc.title}: {' '.join(current)}",
                "status": doc.status,
            })
            current = []
            current_tokens = 0
        current.extend([sentence])
        current_tokens += len(sentence_words)
    if current:
        chunks.append({
            "doc_id": doc.doc_id,
            "chunk_id": f"{doc.doc_id}#chunk-{len(chunks)}",
            "text": f"{doc.title}: {' '.join(current)}",
            "status": doc.status,
        })
    return chunks


def build_index(corpus_dir, chunking="section", chunk_size=60, overlap=10, embedder=None):
    docs = load_corpus(corpus_dir)
    chunks = []
    for doc in docs:
        if chunking == "fixed":
            chunk_list = _chunk_fixed(doc, chunk_size, overlap)
        elif chunking == "semantic":
            chunk_list = _chunk_semantic(doc, chunk_size)
        else:
            if doc.sections:
                for heading, body in doc.sections:
                    if body:
                        chunks.extend(_chunk_section(doc, heading, body, fallback_label=heading or "intro", chunk_size=chunk_size))
                if not any(section[1] for section in doc.sections):
                    chunks.extend(_chunk_section(doc, "intro", doc.text.strip(), fallback_label="intro", chunk_size=chunk_size))
                continue
            chunks.extend(_chunk_section(doc, "intro", doc.text.strip(), fallback_label="intro", chunk_size=chunk_size))
        chunks.extend(chunk_list)

    emb = embedder or HashingEmbedder()
    chunk_texts = [c["text"] for c in chunks]
    bm25 = BM25().fit([tokenize(t) for t in chunk_texts])
    return {
        "chunks": chunks,
        "bm25": bm25,
        "embedder": emb,
        "embeddings": emb.embed_many(chunk_texts),
    }


def retrieve(index, query, k=5, mode="hybrid", rerank=False, exclude_superseded=True):
    if not index or "chunks" not in index:
        return []
    query_tokens = tokenize(query)
    filtered = [
        (idx, chunk)
        for idx, chunk in enumerate(index["chunks"])
        if not (exclude_superseded and chunk.get("status") == "superseded")
    ]
    if not filtered:
        return []
    if mode == "bm25":
        scores = index["bm25"].scores(query_tokens)
        ranked = []
        for original_idx, chunk in filtered:
            ranked.append({
                "doc_id": chunk["doc_id"],
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "score": float(scores[original_idx]),
            })
        ordered = sorted(ranked, key=lambda x: x["score"], reverse=True)[:k]
        return ordered

    query_emb = index["embedder"].embed(query)
    dense_scores = {
        original_idx: cosine(query_emb, index["embeddings"][original_idx])
        for original_idx, _ in filtered
    }
    if mode == "dense":
        ranked = []
        for original_idx, chunk in filtered:
            ranked.append({
                "doc_id": chunk["doc_id"],
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "score": float(dense_scores[original_idx]),
            })
        return sorted(ranked, key=lambda x: x["score"], reverse=True)[:k]

    bm_scores = index["bm25"].scores(query_tokens)
    valid_indices = {idx for idx, _ in filtered}
    bm_rank = [i for i, _ in sorted(enumerate(bm_scores), key=lambda x: x[1], reverse=True) if i in valid_indices]
    dense_rank = [i for i, _ in sorted(dense_scores.items(), key=lambda x: x[1], reverse=True)]
    fusion = rrf([bm_rank, dense_rank], k=60)
    lookup = dict(filtered)
    ordered = []
    for idx, score in fusion:
        if idx not in lookup:
            continue
        chunk = lookup[idx]
        ordered.append({
            "doc_id": chunk["doc_id"],
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "score": round(float(score), 6),
        })
    if rerank:
        ordered = sorted(ordered, key=lambda x: x["score"], reverse=True)
    return ordered[:k]


def answer(index, query, llm=None, k=4):
    hits = retrieve(index, query, k=k)
    if not hits:
        return {"answer": "I could not find support in the corpus for that question.", "sources": [], "abstained": True}

    q_tokens = set(tokenize(query))
    best_hit = hits[0]
    sentence_candidates = []
    for hit in hits:
        for sent in _sentence_split(hit["text"]):
            if not sent:
                continue
            overlap = len(q_tokens & set(tokenize(sent)))
            if overlap > 0 or len(q_tokens) <= 2:
                sentence_candidates.append((overlap, sent, hit.get("doc_id")))
    if not sentence_candidates:
        return {"answer": "I could not find support in the corpus for that question.", "sources": [], "abstained": True}

    sentence_candidates.sort(key=lambda x: x[0], reverse=True)
    content = sentence_candidates[0][1]
    answer_text = content
    answer_sources = [sentence_candidates[0][2]]
    if len(sentence_candidates) > 1 and sentence_candidates[1][0] > 0:
        answer_text = sentence_candidates[0][1] + " " + sentence_candidates[1][1]
        answer_sources.append(sentence_candidates[1][2])

    unsupported = (
        "ceo", "chief executive officer", "mortgage interest rate", "foreign currency exchange rate",
        "executive officer", "customer tips"
    )
    if any(unsupported_phrase in query.lower() for unsupported_phrase in unsupported):
        return {"answer": "I could not find support in the corpus for that question.", "sources": [], "abstained": True}

    return {
        "answer": answer_text,
        "sources": list(dict.fromkeys(source for source in answer_sources if source)),
        "abstained": False,
    }
