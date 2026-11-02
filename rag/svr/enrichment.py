"""Bounded configured-model requests for ingestion; no source or response logging."""
import json
import math
import unicodedata
from dataclasses import dataclass

from rag.chunking.errors import ChunkTooLong
from rag.chunking.resume import MAX_INPUT_CHARS, MAX_INPUT_TOKENS
from rag.nlp.token_count import count_tokens
from rag.parsers.errors import FileTooLarge
from rag.prompts.enrichment import (CONTROLLED_TAG_SYSTEM, ENRICHMENT_SYSTEM, GENERATED_METADATA_SYSTEM,
                                    RESUME_SYSTEM, controlled_tag_prompt, enrichment_prompt,
                                    generated_metadata_prompt, resume_prompt)
from rag.parsers.tags import tag_label
from rag.svr.failure import TaskFailure

ENRICHMENT_BATCH = 8
MAX_ENRICHED_CHUNKS = 64
MAX_ENRICHMENT_RESPONSE = 16 * 1024
MAX_ENRICHMENT_INPUT = 32 * 1024
ENRICHMENT_OUTPUT_TOKENS = 4096
MAX_GENERATED_METADATA_BYTES = 16 * 1024


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate model key")
        result[key] = value
    return result


@dataclass(frozen=True)
class EnrichedFeatures:
    keywords: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()


def _phrases(raw: object, limit: int, max_chars: int) -> tuple[str, ...]:
    if not isinstance(raw, list) or len(raw) > limit:
        raise TaskFailure("embed", "provider_refused")
    out = []
    seen = set()
    for phrase in raw:
        if not isinstance(phrase, str):
            raise TaskFailure("embed", "provider_refused")
        cleaned = " ".join(unicodedata.normalize("NFKC", phrase).split())
        if not cleaned or len(cleaned) > max_chars or any(unicodedata.category(char) == "Cc" for char in cleaned):
            raise TaskFailure("embed", "provider_refused")
        key = cleaned.casefold()
        if key not in seen:
            out.append(cleaned)
            seen.add(key)
    return tuple(out)


def parse_enrichment(raw: str, count: int, keywords: int, questions: int) -> tuple[EnrichedFeatures, ...]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_ENRICHMENT_RESPONSE:
        raise TaskFailure("embed", "provider_refused")
    try:
        payload = json.loads(raw, object_pairs_hook=_strict_object)
    except (ValueError, TypeError, RecursionError):
        raise TaskFailure("embed", "provider_refused") from None
    if not isinstance(payload, dict) or set(payload) != {"items"} or not isinstance(payload["items"], list) or len(payload["items"]) != count:
        raise TaskFailure("embed", "provider_refused")
    result = []
    for index, item in enumerate(payload["items"]):
        if not isinstance(item, dict) or set(item) != {"index", "keywords", "questions"} or type(item["index"]) is not int or item["index"] != index:
            raise TaskFailure("embed", "provider_refused")
        result.append(EnrichedFeatures(_phrases(item["keywords"], keywords, 96), _phrases(item["questions"], questions, 240)))
    return tuple(result)


def enrichment_completion(bundle, texts: list[str], keywords: int, questions: int) -> tuple[EnrichedFeatures, ...]:
    if not 1 <= len(texts) <= ENRICHMENT_BATCH or type(keywords) is not int or not 0 <= keywords <= 32 or type(questions) is not int or not 0 <= questions <= 16 or not (keywords or questions):
        raise TaskFailure("embed", "provider_refused")
    prompt = enrichment_prompt(texts, keywords, questions)
    if len(prompt.encode("utf-8")) > MAX_ENRICHMENT_INPUT:
        raise FileTooLarge()
    if count_tokens(ENRICHMENT_SYSTEM) + count_tokens(prompt) + ENRICHMENT_OUTPUT_TOKENS + 64 > bundle.context_tokens:
        raise ChunkTooLong()
    response = bundle.chat(ENRICHMENT_SYSTEM, [{"role": "user", "content": prompt}], {"temperature": 0, "max_tokens": ENRICHMENT_OUTPUT_TOKENS})
    return parse_enrichment(response, len(texts), keywords, questions)


def parse_controlled_tags(raw: str, count: int, allowed: list[str]) -> tuple[tuple[str, ...], ...]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_ENRICHMENT_RESPONSE or not 1 <= count <= ENRICHMENT_BATCH or not 1 <= len(allowed) <= 128:
        raise TaskFailure("embed", "provider_refused")
    try:
        payload = json.loads(raw, object_pairs_hook=_strict_object)
    except (ValueError, TypeError, RecursionError):
        raise TaskFailure("embed", "provider_refused") from None
    if not isinstance(payload, dict) or set(payload) != {"items"} or not isinstance(payload["items"], list) or len(payload["items"]) != count:
        raise TaskFailure("embed", "provider_refused")
    accepted = set(allowed)
    result = []
    for index, item in enumerate(payload["items"]):
        if not isinstance(item, dict) or set(item) != {"index", "tags"} or type(item["index"]) is not int or item["index"] != index or not isinstance(item["tags"], list) or len(item["tags"]) > 32:
            raise TaskFailure("embed", "provider_refused")
        try:
            labels = [tag_label(label) for label in item["tags"]]
        except ValueError:
            raise TaskFailure("embed", "provider_refused") from None
        if any(label not in accepted for label in labels):
            raise TaskFailure("embed", "provider_refused")
        result.append(tuple(sorted(set(labels))))
    return tuple(result)


def controlled_tag_completion(bundle, texts: list[str], allowed: list[str]) -> tuple[tuple[str, ...], ...]:
    if not 1 <= len(texts) <= ENRICHMENT_BATCH or not 1 <= len(allowed) <= 128:
        raise TaskFailure("embed", "provider_refused")
    prompt = controlled_tag_prompt(texts, allowed)
    if len(prompt.encode("utf-8")) > MAX_ENRICHMENT_INPUT:
        raise FileTooLarge()
    if count_tokens(CONTROLLED_TAG_SYSTEM) + count_tokens(prompt) + ENRICHMENT_OUTPUT_TOKENS + 64 > bundle.context_tokens:
        raise ChunkTooLong()
    response = bundle.chat(CONTROLLED_TAG_SYSTEM, [{"role": "user", "content": prompt}], {"temperature": 0, "max_tokens": ENRICHMENT_OUTPUT_TOKENS})
    return parse_controlled_tags(response, len(texts), allowed)


def _metadata_value(value: object, kind: str) -> object:
    if kind == "string" and isinstance(value, str) and len(value) <= 4096 and all(unicodedata.category(char) != "Cc" or char in "\t\n" for char in value):
        return value
    if kind == "number" and type(value) in {int, float}:
        try:
            if len(str(value)) <= 64 and math.isfinite(value):
                return value
        except (OverflowError, ValueError):
            pass
    if kind == "boolean" and type(value) is bool:
        return value
    if kind == "string_array" and isinstance(value, list) and len(value) <= 32 and all(isinstance(item, str) and len(item) <= 4096 and all(unicodedata.category(char) != "Cc" or char in "\t\n" for char in item) for item in value):
        return value
    raise TaskFailure("embed", "provider_refused")


def parse_generated_metadata(raw: str, schema: list[dict], *, require_required: bool = True) -> dict[str, object]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_GENERATED_METADATA_BYTES or not 1 <= len(schema) <= 32:
        raise TaskFailure("embed", "provider_refused")
    try:
        payload = json.loads(raw, object_pairs_hook=_strict_object)
    except (ValueError, TypeError, RecursionError):
        raise TaskFailure("embed", "provider_refused") from None
    if not isinstance(payload, dict) or set(payload) != {"metadata"} or not isinstance(payload["metadata"], dict):
        raise TaskFailure("embed", "provider_refused")
    declared = {field["name"]: field for field in schema}
    supplied = payload["metadata"]
    if set(supplied) - set(declared) or (require_required and any(field.get("required") and name not in supplied for name, field in declared.items())):
        raise TaskFailure("embed", "provider_refused")
    result = {name: _metadata_value(value, declared[name]["type"]) for name, value in supplied.items()}
    if len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > MAX_GENERATED_METADATA_BYTES:
        raise TaskFailure("embed", "provider_refused")
    return dict(sorted(result.items()))


def generated_metadata_completion(bundle, texts: list[str], schema: list[dict]) -> dict[str, object]:
    if not 1 <= len(texts) <= ENRICHMENT_BATCH or not 1 <= len(schema) <= 32:
        raise TaskFailure("embed", "provider_refused")
    prompt = generated_metadata_prompt(texts, schema)
    if len(prompt.encode("utf-8")) > MAX_ENRICHMENT_INPUT:
        raise FileTooLarge()
    if count_tokens(GENERATED_METADATA_SYSTEM) + count_tokens(prompt) + ENRICHMENT_OUTPUT_TOKENS + 64 > bundle.context_tokens:
        raise ChunkTooLong()
    response = bundle.chat(GENERATED_METADATA_SYSTEM, [{"role": "user", "content": prompt}], {"temperature": 0, "max_tokens": ENRICHMENT_OUTPUT_TOKENS})
    return parse_generated_metadata(response, schema, require_required=False)


def resume_completion(bundle, texts):
    if len(texts) > 128 or sum(len(s) for s in texts) > MAX_INPUT_CHARS or sum(count_tokens(s) for s in texts) > MAX_INPUT_TOKENS:
        raise FileTooLarge()
    prompt = resume_prompt(texts)
    if count_tokens(RESUME_SYSTEM) + count_tokens(prompt) + 2048 + 64 > bundle.context_tokens:
        raise ChunkTooLong()
    return bundle.chat(RESUME_SYSTEM,[{"role":"user","content":prompt}],{"temperature":0,"max_tokens":2048})
