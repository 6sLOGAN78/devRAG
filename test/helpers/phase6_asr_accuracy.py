"""The explicitly accepted spelling equivalence applies only to test evaluation."""

import re


def assert_audio_facts(text):
    # User approval: 06-16-SPELLING-ACCEPTANCE.json. Never rewrite source transcripts.
    value = re.sub(r"\blight house\b", "lighthouse", text.lower())
    height, separator, calibration = value.partition("calibration")
    assert separator and re.search(r"\blighthouse\b", height)
    assert re.search(r"\b(?:fifty two|52)\b(?!\.\d)", height)
    assert re.search(r"\b(?:seventy three|73)\b(?!\.\d)", calibration)
