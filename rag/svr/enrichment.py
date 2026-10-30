"""Bounded configured-model requests for ingestion; no source or response logging."""
import json
import unicodedata
from dataclasses import dataclass

from rag.chunking.errors import ChunkTooLong
from rag.chunking.resume import MAX_INPUT_CHARS, MAX_INPUT_TOKENS
from rag.nlp.token_count import count_tokens
from rag.parsers.errors import FileTooLarge
from rag.prompts.enrichment import ENRICHMENT_SYSTEM, RESUME_SYSTEM, enrichment_prompt, resume_prompt
from rag.svr.failure import TaskFailure

ENRICHMENT_BATCH = 8
MAX_ENRICHED_CHUNKS = 64
MAX_ENRICHMENT_RESPONSE = 16 * 1024
MAX_ENRICHMENT_INPUT = 32 * 1024
ENRICHMENT_OUTPUT_TOKENS = 4096


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
        payload = json.loads(raw)
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


def resume_completion(bundle, texts):
    if len(texts) > 128 or sum(len(s) for s in texts) > MAX_INPUT_CHARS or sum(count_tokens(s) for s in texts) > MAX_INPUT_TOKENS:
        raise FileTooLarge()
    prompt = resume_prompt(texts)
    if count_tokens(RESUME_SYSTEM) + count_tokens(prompt) + 2048 + 64 > bundle.context_tokens:
        raise ChunkTooLong()
    return bundle.chat(RESUME_SYSTEM,[{"role":"user","content":prompt}],{"temperature":0,"max_tokens":2048})
