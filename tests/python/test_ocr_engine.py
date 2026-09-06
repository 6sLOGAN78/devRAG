from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deepdoc.errors import InvalidInputError
from deepdoc.vision.ocr import OcrEngine


@patch("deepdoc.vision.ocr.cv2.imread")
@patch("paddleocr.PaddleOCR")
def test_ocr_engine_mocked(MockPaddleOCR, mock_imread, tmp_path):
    test_img = tmp_path / "dummy.png"
    test_img.write_text("fake image")
    
    mock_imread.return_value = "fake_image_array"

    mock_engine_instance = MagicMock()
    mock_result = [{
        'dt_polys': [[[10.0, 10.0], [100.0, 10.0], [100.0, 50.0], [10.0, 50.0]]],
        'rec_texts': ["Hello OCR"],
        'rec_scores': [0.99]
    }]
    mock_engine_instance.predict.return_value = mock_result
    MockPaddleOCR.return_value = mock_engine_instance

    engine = OcrEngine(use_gpu=False)
    engine._engine = mock_engine_instance
    blocks = engine.extract(test_img)

    assert len(blocks) == 1
    assert blocks[0].text == "Hello OCR"
    assert blocks[0].metadata["confidence"] == 0.99
    assert blocks[0].bbox == [10.0, 10.0, 100.0, 50.0]

@patch("paddleocr.PaddleOCR")
def test_ocr_engine_invalid_path(MockPaddleOCR):
    mock_engine_instance = MagicMock()
    MockPaddleOCR.return_value = mock_engine_instance
    engine = OcrEngine(use_gpu=False)
    engine._engine = mock_engine_instance
    with pytest.raises(InvalidInputError):
        engine.extract(Path("/path/to/nonexistent_image.png"))

def test_ocr_engine_real_image():
    img_path = Path("tests/fixtures/scanned_sample.png")
    if not img_path.exists():
        pytest.skip("Test image not generated yet")
        
    engine = OcrEngine(use_gpu=False)
    blocks = engine.extract(img_path)
    
    assert len(blocks) > 0
    text_content = " ".join([b.text for b in blocks])
    assert "Invoice" in text_content or "Amount" in text_content
    
    for b in blocks:
        assert len(b.bbox) == 4
        assert b.bbox[0] < b.bbox[2]
        assert b.bbox[1] < b.bbox[3]
        assert "confidence" in b.metadata
        assert "source" in b.metadata
