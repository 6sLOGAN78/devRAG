"""The editable instruction prefill matches the server fallback, independently of citation rules."""
import json
from pathlib import Path

import pytest

from rag.prompts.generator import DEFAULT_SYSTEM

pytestmark = pytest.mark.unit


def test_instruction_prefill_matches_the_server_default():
    path = Path(__file__).resolve().parents[2] / "web/src/locales/areas/en/assistant.json"
    locale = json.loads(path.read_text())
    assert locale["assistant"]["default"]["system"] == DEFAULT_SYSTEM
