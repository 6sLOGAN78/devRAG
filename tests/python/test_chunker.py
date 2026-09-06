import pytest
from deepdoc.models import DocumentStructure, PageNode, TextBlock, TableBlock
from deepdoc.chunker import Chunk, TokenCounter, GeneralChunker, QAChunker, ManualChunker

def test_token_counter():
    counter = TokenCounter()
    assert counter.count("Hello world") > 0

def test_general_chunker_paragraphs():
    doc = DocumentStructure(document_id="doc1")
    page = PageNode(page_number=1)
    
    # 3 small blocks
    page.blocks.append(TextBlock(text="This is block 1.", block_id="b1", bbox=[0,0,10,10]))
    page.blocks.append(TextBlock(text="This is block 2.", block_id="b2", bbox=[10,10,20,20]))
    page.blocks.append(TextBlock(text="This is block 3.", block_id="b3", bbox=[20,20,30,30]))
    doc.pages.append(page)
    
    chunker = GeneralChunker(max_tokens=500)
    chunks = chunker.chunk(doc)
    
    # They should all merge into 1 chunk
    assert len(chunks) == 1
    assert chunks[0].text == "This is block 1.\n\nThis is block 2.\n\nThis is block 3."
    assert chunks[0].document_id == "doc1"
    assert chunks[0].page_numbers == [1]
    assert len(chunks[0].source_block_ids) == 3
    assert len(chunks[0].source_regions) == 3

def test_general_chunker_max_tokens():
    doc = DocumentStructure(document_id="doc2")
    page = PageNode(page_number=1)
    
    # Create blocks that will exceed 10 tokens
    page.blocks.append(TextBlock(text="This is a very long sentence that will exceed the limit.", block_id="b1"))
    page.blocks.append(TextBlock(text="This is another block.", block_id="b2"))
    doc.pages.append(page)
    
    chunker = GeneralChunker(max_tokens=10)
    chunks = chunker.chunk(doc)
    
    assert len(chunks) >= 2
    assert "exceed the limit." in chunks[0].text or "exceed the limit." in chunks[1].text
    
def test_general_chunker_header_footer():
    doc = DocumentStructure()
    page = PageNode(page_number=1)
    page.blocks.append(TextBlock(text="Header text", metadata={"layout_type": "header"}))
    page.blocks.append(TextBlock(text="Main content"))
    page.blocks.append(TextBlock(text="Footer text", metadata={"layout_type": "footer"}))
    doc.pages.append(page)
    
    chunker = GeneralChunker(max_tokens=500)
    chunks = chunker.chunk(doc)
    
    assert len(chunks) == 1
    assert "Header text" not in chunks[0].text
    assert "Footer text" not in chunks[0].text
    assert "Main content" in chunks[0].text

def test_general_chunker_table():
    doc = DocumentStructure()
    page = PageNode(page_number=1)
    page.blocks.append(TextBlock(text="Before table"))
    table = TableBlock(rows=[["H1", "H2"], ["A", "B"], ["C", "D"]], columns=2)
    page.blocks.append(table)
    page.blocks.append(TextBlock(text="After table"))
    doc.pages.append(page)
    
    chunker = GeneralChunker(max_tokens=500)
    chunks = chunker.chunk(doc)
    
    # Text -> Table -> Text -> 3 chunks
    assert len(chunks) == 3
    assert chunks[0].text == "Before table"
    assert chunks[1].content_type == "table"
    assert "H1 | H2" in chunks[1].text
    assert chunks[2].text == "After table"

def test_qa_chunker():
    doc = DocumentStructure()
    page = PageNode(page_number=1)
    page.blocks.append(TextBlock(text="Q: What is devRAG?"))
    page.blocks.append(TextBlock(text="A: It is a retrieval system."))
    doc.pages.append(page)
    
    chunker = QAChunker(max_tokens=500)
    chunks = chunker.chunk(doc)
    
    assert len(chunks) == 1
    assert chunks[0].content_type == "qa"
    assert "Q: What is devRAG?\nA: It is a retrieval system." in chunks[0].text

def test_manual_chunker():
    b1 = TextBlock(text="Block 1", block_id="b1")
    b2 = TextBlock(text="Block 2", block_id="b2")
    
    chunker = ManualChunker()
    chunks = chunker.chunk_blocks([[b1, b2]])
    assert len(chunks) == 1
    assert "Block 1\n\nBlock 2" in chunks[0].text
