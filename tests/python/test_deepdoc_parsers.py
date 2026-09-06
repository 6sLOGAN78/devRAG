from pathlib import Path

import pytest
from pydantic import ValidationError

from deepdoc.errors import InvalidInputError
from deepdoc.models import DocumentStructure, PageNode, TextBlock
from deepdoc.parsers.md_parser import MarkdownParser
from deepdoc.parsers.txt_parser import TxtParser


def test_pydantic_models():
    # Valid structure
    block = TextBlock(text="Hello World", block_id="1")
    page = PageNode(page_number=1, blocks=[block])
    doc = DocumentStructure(source_path="/fake/path.txt", pages=[page])
    
    assert doc.pages[0].blocks[0].text == "Hello World"
    
    # Validation failure
    with pytest.raises(ValidationError):
        TextBlock(text=None) # type: ignore

def test_txt_parser(tmp_path: Path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("Hello World\n\nThis is a second paragraph.")
    
    parser = TxtParser()
    doc = parser.parse(test_file)
    
    assert doc.file_type == "txt"
    assert len(doc.pages) == 1
    assert len(doc.pages[0].blocks) == 2
    assert doc.pages[0].blocks[0].text == "Hello World"
    assert doc.pages[0].blocks[1].text == "This is a second paragraph."
    
def test_txt_parser_empty(tmp_path: Path):
    test_file = tmp_path / "empty.txt"
    test_file.write_text("")
    
    parser = TxtParser()
    doc = parser.parse(test_file)
    
    assert len(doc.pages[0].blocks) == 0
    
def test_invalid_input():
    parser = TxtParser()
    with pytest.raises(InvalidInputError):
        parser.parse(Path("/does/not/exist.txt"))

def test_md_parser(tmp_path: Path):
    test_file = tmp_path / "sample.md"
    test_file.write_text("# Heading 1\n\nSome paragraph text here.\n\n## Heading 2\n\nMore text.")
    
    parser = MarkdownParser()
    doc = parser.parse(test_file)
    
    assert doc.file_type == "markdown"
    assert len(doc.pages) == 1
    assert len(doc.pages[0].blocks) == 4
    
    assert doc.pages[0].blocks[0].text == "# Heading 1"
    assert doc.pages[0].blocks[0].style["type"] == "heading"
    assert doc.pages[0].blocks[0].style["level"] == 1
    
    assert doc.pages[0].blocks[1].text == "Some paragraph text here."
    assert doc.pages[0].blocks[1].style["type"] == "paragraph"
