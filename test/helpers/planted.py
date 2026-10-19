"""Planted-fact corpus for the retrieval and chat proofs (plan 05-01, D-07).

Accuracy is proved by facts that exist only in the planted documents: each fact is a rare token plus a numeric answer that appears in
exactly one paragraph (TXT) or one page (PDF), so a correct answer or a correct citation can be checked by looking for the answer keyword
and the chunk that holds the token. No LLM judge is involved.

``planted_txt`` makes six paragraphs of exactly ``PARAGRAPH_TOKENS`` tokens separated by blank lines, so with the default chunk budget each
paragraph is one chunk (the same sizing rule as ``test.helpers.ingest.paragraphs``). ``planted_pdf`` makes three short text pages.
"""
from __future__ import annotations

from dataclasses import dataclass

from rag.nlp.token_count import count_tokens
from test.helpers.pdf_files import text_pdf

PARAGRAPH_TOKENS = 300


@dataclass(frozen=True)
class Fact:
    token: str  # rare token that names the subject and appears in exactly one paragraph or page
    question: str  # asks for the answer and contains the token
    keywords: tuple[str, ...]  # the token and the answer; a correct answer contains the answer keyword


FACTS: tuple[Fact, ...] = (
    Fact("Zorblax-4417", "At what coolant temperature does the Zorblax-4417 reactor run?", ("Zorblax-4417", "612")),
    Fact("Quenthar-9082", "How deep is the ice found by the Quenthar-9082 glacier survey?", ("Quenthar-9082", "87")),
    Fact("Plimsby-3356", "How many sourdough loaves does the Plimsby-3356 bakery sell each weekend?", ("Plimsby-3356", "1450")),
    Fact("Drevonic-7721", "How many listeners attended the premiere of the Drevonic-7721 orchestra?", ("Drevonic-7721", "2300")),
    Fact("Wexmoor-5509", "What is the orbital period of the comet recorded by the Wexmoor-5509 telescope?", ("Wexmoor-5509", "41")),
    Fact("Hallowick-2864", "How many bicycles can the Hallowick-2864 ferry carry?", ("Hallowick-2864", "36")),
)

_SENTENCES: tuple[str, ...] = (
    "The Zorblax-4417 reactor at the Vellmoor station runs at a coolant temperature of 612 degrees.",
    "The Quenthar-9082 glacier survey measured an ice depth of 87 meters near Ostrava Ridge.",
    "The Plimsby-3356 bakery on Harrow Lane sells exactly 1450 sourdough loaves each weekend.",
    "The Drevonic-7721 orchestra premiered its symphony in Kelmarsh before 2300 listeners.",
    "The Wexmoor-5509 telescope recorded a comet with an orbital period of 41 years.",
    "The Hallowick-2864 ferry carries 36 bicycles across Tarnwater Strait.",
)

PDF_FACTS: dict[int, Fact] = {
    1: Fact("Brantwell-6130", "How tall is the Brantwell-6130 lighthouse?", ("Brantwell-6130", "52")),
    2: Fact("Oskarine-8847", "How many kilograms of quinces did the Oskarine-8847 orchard harvest?", ("Oskarine-8847", "9100")),
    3: Fact("Tyrmoth-2275", "How many handwritten maps does the Tyrmoth-2275 archive store?", ("Tyrmoth-2275", "730")),
}

_PDF_PAGES: dict[int, list[str]] = {
    1: ["The Brantwell-6130 lighthouse stands 52 meters", "above Corvane Bay."],
    2: ["The Oskarine-8847 orchard harvested 9100", "kilograms of quinces."],
    3: ["The Tyrmoth-2275 archive stores 730", "handwritten maps of Dunmere."],
}


def _paragraph(sentence: str) -> str:
    text = sentence
    while count_tokens(text) < PARAGRAPH_TOKENS:
        text += " the"
    assert count_tokens(text) == PARAGRAPH_TOKENS, "the fact sentence alone is longer than the paragraph budget"
    return text


def planted_txt() -> bytes:
    """Six paragraphs, one planted fact each, separated by blank lines."""
    return "\n\n".join(_paragraph(s) for s in _SENTENCES).encode("utf-8")


def planted_pdf() -> bytes:
    """A three-page text PDF with a different planted fact on each page."""
    return text_pdf([_PDF_PAGES[page] for page in sorted(_PDF_PAGES)])


def off_topic_question() -> str:
    """A question that shares no word with the TXT or the PDF."""
    return "Which volcano erupted beneath Iceland yesterday?"
