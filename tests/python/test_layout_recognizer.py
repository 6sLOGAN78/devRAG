import pytest
from pathlib import Path
from deepdoc.vision.layout_recognizer import LayoutRecognizer, LayoutRegion, get_intersection_over_area, build_structured_page
from deepdoc.models import TextBlock
from unittest.mock import MagicMock, patch

def test_intersection_over_area():
    # block is fully inside region
    block = [10, 10, 20, 20]
    region = [0, 0, 30, 30]
    assert get_intersection_over_area(block, region) == 1.0
    
    # block is 50% inside region
    block = [10, 10, 30, 20]
    region = [0, 0, 20, 30]
    assert get_intersection_over_area(block, region) == 0.5
    
    # no overlap
    block = [10, 10, 20, 20]
    region = [30, 30, 40, 40]
    assert get_intersection_over_area(block, region) == 0.0

@patch("deepdoc.vision.layout_recognizer.cv2.imread")
@patch("ultralytics.YOLO")
def test_layout_recognizer_mocked(MockYolo, mock_imread, tmp_path):
    # Mock valid image path
    test_img = tmp_path / "dummy.png"
    test_img.write_text("fake image")
    mock_imread.return_value = "fake_image_array"

    mock_model_instance = MagicMock()
    mock_model_instance.names = {0: "Page-header", 1: "Text"}
    
    class MockBox:
        def __init__(self, cls_id, conf, xyxy):
            self.cls = [MagicMock(item=lambda: cls_id)]
            self.conf = [MagicMock(item=lambda: conf)]
            self.xyxy = [MagicMock(tolist=lambda: xyxy)]
            
    class MockResult:
        def __init__(self, boxes):
            self.boxes = boxes

    mock_model_instance.return_value = [
        MockResult([
            MockBox(0, 0.9, [0, 0, 100, 20]),
            MockBox(1, 0.8, [0, 20, 100, 100]),
            MockBox(1, 0.2, [0, 0, 10, 10]) # low conf
        ])
    ]
    MockYolo.return_value = mock_model_instance

    with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.is_file", return_value=True):
        recognizer = LayoutRecognizer(model_path="dummy.pt", confidence_threshold=0.5)
        # inject mock bypassing the model check
        recognizer._model = mock_model_instance
        regions = recognizer.detect(test_img)

    assert len(regions) == 2
    assert regions[0].label == "header"
    assert regions[1].label == "paragraph/text"

def test_build_structured_page_multi_column():
    # Column 1
    r1 = LayoutRegion(label="paragraph/text", bbox=[10, 50, 110, 150], confidence=0.9)
    r2 = LayoutRegion(label="paragraph/text", bbox=[10, 160, 110, 260], confidence=0.9)
    
    # Column 2
    r3 = LayoutRegion(label="paragraph/text", bbox=[120, 50, 220, 150], confidence=0.9)
    
    # Header
    r4 = LayoutRegion(label="header", bbox=[0, 0, 300, 40], confidence=0.9)
    
    regions = [r1, r2, r3, r4]
    
    # OCR Blocks
    b1 = TextBlock(text="col1_top", bbox=[20, 60, 100, 140])
    b2 = TextBlock(text="col1_bot", bbox=[20, 170, 100, 250])
    b3 = TextBlock(text="col2", bbox=[130, 60, 210, 140])
    b4 = TextBlock(text="head", bbox=[10, 10, 290, 30])
    b5 = TextBlock(text="unmatched", bbox=[0, 300, 300, 310])
    
    # Notice we pass OCR blocks out of order
    blocks = [b3, b1, b5, b2, b4]
    
    page = build_structured_page(1, blocks, regions)
    
    assert page.page_number == 1
    assert len(page.blocks) == 5
    
    # Expected reading order: header -> col1_top -> col1_bot -> col2 -> unmatched
    assert page.blocks[0].text == "head"
    assert page.blocks[1].text == "col1_top"
    assert page.blocks[2].text == "col1_bot"
    assert page.blocks[3].text == "col2"
    assert page.blocks[4].text == "unmatched"
    
    assert page.blocks[0].metadata["layout_type"] == "header"
    assert page.blocks[4].metadata["layout_type"] == "unknown"

def test_real_multi_column():
    # We create a dummy multi column logic via a fixture image or just run logic
    pass

