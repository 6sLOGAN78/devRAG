"""Deterministic, source-bound recursive summary hierarchy.

Small corpora use stable nearest-neighbour pairs. Larger corpora require the
approved native UMAP/GMM clusterer; there is no silent clustering fallback.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

MAX_LEAVES = 256
MAX_LEVELS = 3
MAX_SUMMARIES = 64
MAX_CLUSTER = 8
MAX_CONTEXT_CHARS = 12_000
MAX_SUMMARY_CHARS = 2_000


class RaptorError(ValueError):
    """The source, clusterer or model cannot produce a safe hierarchy."""


@dataclass(frozen=True)
class Leaf:
    chunk_id: str
    doc_id: str
    text: str
    vector: tuple[float, ...]


@dataclass(frozen=True)
class Summary:
    chunk_id: str
    level: int
    text: str
    vector: tuple[float, ...]
    child_ids: tuple[str, ...]
    leaf_ids: tuple[str, ...]


NativeCluster = Callable[[list[list[float]], int], list[list[int]]]
Summarize = Callable[[list[str], int], str]
Embed = Callable[[list[str]], list[list[float]]]


def _vectors(vectors: Sequence[Sequence[float]]) -> list[tuple[float, ...]]:
    if not 2 <= len(vectors) <= MAX_LEAVES:
        raise RaptorError("the source count is outside RAPTOR bounds")
    dimension = len(vectors[0])
    if not 2 <= dimension <= 4096:
        raise RaptorError("the source vector dimension is invalid")
    rows = []
    for vector in vectors:
        if len(vector) != dimension or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
            raise RaptorError("the source vectors are invalid")
        norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if norm <= 0 or not math.isfinite(norm):
            raise RaptorError("the source vectors are invalid")
        rows.append(tuple(float(value) / norm for value in vector))
    return rows


def _validate_groups(groups: object, size: int) -> list[list[int]]:
    if not isinstance(groups, list) or not 1 <= len(groups) <= MAX_SUMMARIES:
        raise RaptorError("native clustering returned invalid groups")
    clean = []
    for group in groups:
        if not isinstance(group, list) or not 2 <= len(group) <= MAX_CLUSTER or any(type(i) is not int or not 0 <= i < size for i in group):
            raise RaptorError("native clustering returned invalid groups")
        clean.append(sorted(group))
    if sorted(i for group in clean for i in group) != list(range(size)):
        raise RaptorError("native clustering lost or duplicated a source")
    return sorted(clean, key=lambda group: group[0])


def cluster_vectors(vectors: Sequence[Sequence[float]], *, seed: int = 42, native: NativeCluster | None = None) -> list[list[int]]:
    """Partition every input exactly once; use native seeded UMAP/GMM above eight."""
    normalized = _vectors(vectors)
    if len(normalized) > 8:
        if native is None:
            raise RaptorError("native RAPTOR clustering is unavailable")
        return _validate_groups(native([list(row) for row in normalized], seed), len(normalized))
    remaining = set(range(len(normalized)))
    groups: list[list[int]] = []
    while len(remaining) >= 2:
        first = min(remaining)
        remaining.remove(first)
        second = max(remaining, key=lambda i: (sum(a * b for a, b in zip(normalized[first], normalized[i], strict=True)), -i))
        remaining.remove(second)
        groups.append(sorted([first, second]))
    if remaining:
        groups[-1].append(remaining.pop())
    return _validate_groups(groups, len(normalized))


def build_hierarchy(leaves: Sequence[Leaf], generation: str, summarize: Summarize, embed: Embed,
                    *, native: NativeCluster | None = None, seed: int = 42) -> list[Summary]:
    """Summarize and embed each level; every node retains the exact original leaf IDs."""
    if not isinstance(generation, str) or len(generation) != 64 or any(ch not in "0123456789abcdef" for ch in generation):
        raise RaptorError("the generation digest is invalid")
    if len({leaf.chunk_id for leaf in leaves}) != len(leaves) or any(not leaf.text.strip() or len(leaf.text) > MAX_CONTEXT_CHARS for leaf in leaves):
        raise RaptorError("the source leaves are invalid")
    frontier: list[Leaf | Summary] = list(leaves)
    created: list[Summary] = []
    for level in range(1, MAX_LEVELS + 1):
        if len(frontier) < 2:
            break
        groups = cluster_vectors([row.vector for row in frontier], seed=seed, native=native)
        if len(created) + len(groups) > MAX_SUMMARIES:
            raise RaptorError("the summary count exceeds RAPTOR bounds")
        drafts: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
        for group in groups:
            children = [frontier[i] for i in group]
            texts = [child.text for child in children]
            if sum(len(text) for text in texts) > MAX_CONTEXT_CHARS:
                raise RaptorError("a summary context exceeds RAPTOR bounds")
            answer = summarize(texts, level)
            if not isinstance(answer, str) or not 1 <= len(answer.strip()) <= MAX_SUMMARY_CHARS:
                raise RaptorError("the summary model returned invalid text")
            child_ids = tuple(child.chunk_id for child in children)
            leaf_ids = tuple(sorted({leaf_id for child in children for leaf_id in ((child.chunk_id,) if isinstance(child, Leaf) else child.leaf_ids)}))
            drafts.append((answer.strip(), child_ids, leaf_ids))
        vectors = embed([draft[0] for draft in drafts])
        if not isinstance(vectors, list) or len(vectors) != len(drafts):
            raise RaptorError("the embedding model returned invalid vectors")
        normalized = _vectors(vectors) if len(vectors) >= 2 else _vectors([vectors[0], vectors[0]])[:1]
        next_level = []
        for (text, child_ids, leaf_ids), vector in zip(drafts, normalized, strict=True):
            digest = hashlib.sha256(f"{generation}:{level}:{','.join(child_ids)}".encode()).hexdigest()[:32]
            next_level.append(Summary(f"raptor_{digest}", level, text, vector, child_ids, leaf_ids))
        created.extend(next_level)
        frontier = next_level
    return created
