from deepdoc.models import DocumentStructure, PageNode, TextBlock, TableBlock
from deepdoc.chunker import GeneralChunker

doc = DocumentStructure(document_id="complex-doc-123")

# Page 1
page1 = PageNode(page_number=1)
page1.blocks.append(TextBlock(text="Annual Report", metadata={"layout_type": "header"}, bbox=[0,0,10,10]))
page1.blocks.append(TextBlock(text="This is the introduction.", bbox=[0,20,10,20]))
page1.blocks.append(TextBlock(text="It spans multiple lines.", bbox=[0,30,10,30]))
page1.blocks.append(TableBlock(rows=[["Metric", "Value"], ["Revenue", "100"]], columns=2, bbox=[0,50,100,100]))
page1.blocks.append(TextBlock(text="Page 1", metadata={"layout_type": "footer"}, bbox=[0,90,10,90]))
doc.pages.append(page1)

# Page 2
page2 = PageNode(page_number=2)
page2.blocks.append(TextBlock(text="Annual Report", metadata={"layout_type": "header"}, bbox=[0,0,10,10]))
page2.blocks.append(TextBlock(text="Section 2", metadata={"layout_type": "title"}, bbox=[0,20,10,20]))
page2.blocks.append(TextBlock(text="More text here.", bbox=[0,30,10,30]))
page2.blocks.append(TextBlock(text="Page 2", metadata={"layout_type": "footer"}, bbox=[0,90,10,90]))
doc.pages.append(page2)

chunker = GeneralChunker(max_tokens=50) # small limit to force chunking
chunks = chunker.chunk(doc)

print("Generated Chunks:", len(chunks))
for c in chunks:
    print(f"\n--- Chunk {c.chunk_index} ---")
    print(f"Content Type: {c.content_type}")
    print(f"Pages: {c.page_numbers}")
    print(f"BBoxes: {len(c.source_regions)}")
    print(f"Text:\n{c.text}")
