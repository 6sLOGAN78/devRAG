"""Query builder: a question becomes a safe, boosted, synonym-expanded text query (RETR-02, RETR-03 Partial; R-196).

Only tokenizer output is ever joined into the query text, so no search operator, quote, wildcard or field name can survive
from user input (T-05-02-01). Term weighting is left to BM25 IDF because ``simple_query_string`` cannot boost single terms
(RETR-03 Partial, R-203). Nothing here logs the question.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from common.doc_store.doc_store_base import MatchTextExpr
from common.settings import RetrievalSettings
from rag.nlp.tokenizer import tokenize

FIELDS: list[str] = [
    "title_tks^10",
    "title_sm_tks^5",
    "important_kwd^30",
    "important_tks^20",
    "question_tks^20",
    "content_ltks^2",
    "content_sm_ltks",
]

MAX_QUESTION_CHARS = 20000  # bound the tokenizer's input; only 64 tokens are kept anyway
MAX_TOKENS = 64

# English function words, dropped from Latin tokens only. Written for this project.
STOPWORDS = frozenset(
    """a about above after again all also am an and any are as at be because been before being below between both but by
    can could did do does doing down during each few for from further had has have having he her here hers him his how i if
    in into is it its just me more most my no nor not of off on once only or other our out over own same she should so some
    such than that the their them then there these they this those through to too under until up very was we were what when
    where which while who whom why will with would you your""".split()
)


class _Synonyms(Protocol):
    def lookup_many(self, terms: list[str]) -> dict[str, list[str]]: ...


@dataclass(frozen=True)
class QueryPlan:
    tokens: tuple[str, ...]  # used for term similarity
    expanded: tuple[str, ...]  # tokens plus synonyms, used in the text clause
    msm_percent: int = 30
    msm_retry_percent: int = 10

    @property
    def empty(self) -> bool:
        return not self.tokens

    def text_expr(self, top_k: int, retry: bool = False) -> MatchTextExpr:
        if self.empty:
            raise ValueError("an empty plan has no text expression")
        percent = self.msm_retry_percent if retry else self.msm_percent
        return MatchTextExpr(list(FIELDS), " ".join(self.expanded), top_k, {"minimum_should_match": f"{percent}%"})


def _is_latin(token: str) -> bool:
    return token.isascii()


class QueryBuilder:
    def __init__(self, synonyms: _Synonyms | None, settings: RetrievalSettings) -> None:
        self._synonyms = synonyms
        self._settings = settings

    def build(self, question: str) -> QueryPlan:
        raw = list(dict.fromkeys(tokenize(question[:MAX_QUESTION_CHARS])))
        kept = [t for t in raw if not (_is_latin(t) and t in STOPWORDS)]
        tokens = tuple((kept or raw)[:MAX_TOKENS])
        return QueryPlan(
            tokens=tokens,
            expanded=self._expand(tokens),
            msm_percent=self._settings.msm_percent,
            msm_retry_percent=self._settings.msm_retry_percent,
        )

    def _expand(self, tokens: tuple[str, ...]) -> tuple[str, ...]:
        if self._synonyms is None or not tokens:
            return tokens
        terms = [t for t in tokens if _is_latin(t) and t not in STOPWORDS]
        if not terms:
            return tokens
        found = self._synonyms.lookup_many(terms)
        expanded = list(tokens)
        seen = set(tokens)
        for term in terms:
            for synonym in found.get(term, []):
                for piece in tokenize(synonym):
                    if piece not in seen:
                        seen.add(piece)
                        expanded.append(piece)
        return tuple(expanded)
