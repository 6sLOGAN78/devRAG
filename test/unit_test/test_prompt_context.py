"""Deterministic context, history and prompt assembly (plan 05-10)."""
from __future__ import annotations

import pytest

from rag.prompts.generator import (
    CITATION_RULES,
    DEFAULT_SYSTEM,
    ContextChunk,
    assemble_prompt,
    build_context,
    token_budget,
    trim_history,
)

pytestmark = pytest.mark.unit


def chunk(text: str, *, title: str = "A", page: int | None = None, chunk_id: str = "c") -> ContextChunk:
    return ContextChunk(chunk_id, "doc", title, "dataset", page, text, 0.9, 0.8, 0.7, None, None, None)


def chars(text: str) -> int:
    return len(text)


def test_context_numbers_after_dedupe_and_budget():
    result = build_context(
        [chunk("short", chunk_id="first"), chunk("word " * 30, title="B", chunk_id="long"), chunk("tiny", title="C", chunk_id="third")],
        63,
        count=chars,
    )
    assert [c.chunk_id for c in result.used] == ["first", "third"]
    assert result.text == "ID: 0\nTitle: A\nContent: short\n\nID: 1\nTitle: C\nContent: tiny"


def test_context_deduplicates_whitespace_normalised_text():
    result = build_context([chunk("a  b\nc", chunk_id="first"), chunk("a b c", chunk_id="duplicate"), chunk("different", chunk_id="third")], 500, count=chars)
    assert [c.chunk_id for c in result.used] == ["first", "third"]


def test_context_page_line_is_optional():
    result = build_context([chunk("text", page=3), chunk("other", title="B")], 500, count=chars)
    assert "ID: 0\nTitle: A\nPage: 3\nContent: text" in result.text
    assert "ID: 1\nTitle: B\nContent: other" in result.text


@pytest.mark.parametrize("budget", [0, 1, 10])
def test_context_drops_block_that_does_not_fit(budget):
    result = build_context([chunk("large content")], budget, count=chars)
    assert result.text == "" and result.used == ()


def test_context_uses_the_97_percent_boundary():
    block = "ID: 0\nTitle: A\nContent: text"
    budget = len(block)
    assert build_context([chunk("text")], budget, count=chars).used == ()
    assert len(build_context([chunk("text")], budget + 1, count=chars).used) == 1


def test_context_skips_empty_chunks_and_collapses_title_whitespace():
    result = build_context([chunk("  ", chunk_id="empty"), chunk("fact", title="Long\n  title", chunk_id="kept")], 200, count=chars)
    assert [c.chunk_id for c in result.used] == ["kept"]
    assert "Title: Long title" in result.text


def test_history_keeps_newest_turns_then_returns_chronological():
    messages = [
        {"role": "user", "content": "old"}, {"role": "assistant", "content": "old answer", "finish": "complete"},
        {"role": "user", "content": "new"}, {"role": "assistant", "content": "new answer", "finish": "complete"},
    ]
    assert trim_history(messages, 2, count=lambda _: 1) == [{"role": "user", "content": "new"}, {"role": "assistant", "content": "new answer"}]


def test_history_strips_citation_markers_from_assistant_text():
    messages = [{"role": "user", "content": "ask"}, {"role": "assistant", "content": "answer ##0$$  next", "finish": "complete"}]
    assert trim_history(messages, 20, count=chars)[1]["content"] == "answer next"


def test_history_skips_empty_and_failed_assistant_messages():
    messages = [
        {"role": "user", "content": "ask"}, {"role": "assistant", "content": "", "finish": "complete"},
        {"role": "assistant", "content": "failed", "finish": "failed"}, {"role": "assistant", "content": "kept", "finish": "stopped"},
    ]
    assert trim_history(messages, 100, count=chars) == [{"role": "user", "content": "ask"}, {"role": "assistant", "content": "kept"}]


def test_history_never_starts_with_an_assistant():
    assert trim_history([{"role": "assistant", "content": "orphan", "finish": "complete"}], 10, count=chars) == []


def test_history_ignores_unknown_roles_and_stored_internal_fields():
    messages = [{"role": "tool", "content": "secret"}, {"role": "user", "content": "ask", "api_key": "hidden"}]
    assert trim_history(messages, 100, count=chars) == [{"role": "user", "content": "ask"}]


@pytest.mark.parametrize(
    ("maximum", "system", "knowledge", "completion", "margin", "wanted"),
    [(4096, 100, 300, 512, 256, 2928), (100, 50, 40, 50, 256, 0), (1000, 0, 0, 100, 100, 800), (100, 10, 10, 10, 0, 70)],
)
def test_token_budget_formula(maximum, system, knowledge, completion, margin, wanted):
    assert token_budget(maximum, system, knowledge, completion, margin) == wanted


def test_prompt_with_knowledge_has_rules_warning_and_two_block_example():
    prompt = assemble_prompt("", "ID: 0\nTitle: Manual\nContent: fact", [], "What is the fact?", {})
    assert DEFAULT_SYSTEM in prompt.system and CITATION_RULES in prompt.system
    assert "##0$$" in prompt.system and "##1$$" in prompt.system
    assert "instructions inside" in prompt.system and "ignore" in prompt.system.lower()
    assert "<knowledge>" in prompt.system and "ID: 0\nTitle: Manual" in prompt.system
    assert prompt.messages == [{"role": "user", "content": "What is the fact?"}]


def test_prompt_without_knowledge_has_no_citation_rules():
    prompt = assemble_prompt("", "", [], "Hello", {})
    assert CITATION_RULES not in prompt.system and "##0$$" not in prompt.system
    assert prompt.messages == [{"role": "user", "content": "Hello"}]


def test_prompt_preserves_custom_instruction_and_history_order():
    history = [{"role": "user", "content": "Earlier"}, {"role": "assistant", "content": "Answer"}]
    prompt = assemble_prompt("Be concise.", "knowledge", history, "Now?", {})
    assert prompt.system.startswith("Be concise.")
    assert prompt.messages == [*history, {"role": "user", "content": "Now?"}]


def test_prompt_treats_braces_in_a_question_as_text():
    prompt = assemble_prompt("Be clear.", "ID: 0\nContent: fact", [], "What does {knowledge} mean?", {})
    assert prompt.messages[-1]["content"] == "What does {knowledge} mean?"


def test_default_instruction_is_short_and_excludes_fixed_rules():
    assert len(DEFAULT_SYSTEM) <= 600
    assert "##0$$" not in DEFAULT_SYSTEM and CITATION_RULES not in DEFAULT_SYSTEM
