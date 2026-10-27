import pytest

from test.helpers.chat_stream import read_stream

pytestmark = pytest.mark.unit


def test_collects_deltas_canonical_frame_ids_and_done():
    result = read_stream([
        ': keepalive', '',
        'data: {"code":0,"data":{"answer":"first ","session_id":"s","message_id":"m"}}', '',
        'data: {"code":0,"data":{"answer":"second"}}', '',
        'data: {"code":0,"data":{"answer":"canonical","final":true,"reference":{"chunks":[]}}}', '',
        'data: [DONE]', '', 'data: {"code":0,"data":{"answer":"late"}}', '',
    ])
    assert result.deltas_text == "first second"
    assert result.final["data"]["answer"] == "canonical"
    assert result.session_id == "s" and result.message_id == "m"
    assert result.done and len(result.frames) == 3


def test_multiline_data_and_utf8_bytes():
    result = read_stream([b'event: answer', b'data: {"code":0,', 'data: "data":{"answer":"你好"}}'.encode(), b'', b'data: [DONE]', b''])
    assert result.deltas_text == "你好" and result.done


def test_eof_without_done_remains_explicitly_incomplete():
    result = read_stream(['data: {"code":0,"data":{"answer":"partial"}}'])
    assert result.deltas_text == "partial"
    assert result.final is None and not result.done


def test_invalid_payloads_do_not_become_frames():
    result = read_stream(['data: not json', '', 'data: []', '', 'data: {"code":0,"data":null}', '', 'data: [DONE]', ''])
    assert result.frames == [] and result.done


def test_error_frame_is_retained_without_appending_its_sentence():
    result = read_stream([
        'data: {"code":0,"data":{"answer":"partial"}}', '',
        'data: {"code":502,"data":{"answer":"provider sentence","final":true,"reason":"provider_timeout"}}', '',
        'data: [DONE]', '',
    ])
    assert result.deltas_text == "partial"
    assert result.final["code"] == 502


def test_crlf_and_metadata_fields():
    result = read_stream(['id: 7\r', 'retry: 1000\r', 'data: {"code":0,"data":{"answer":"ok"}}\r', '\r', 'data: [DONE]\r', '\r'])
    assert result.deltas_text == "ok" and result.done
