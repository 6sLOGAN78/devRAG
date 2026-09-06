# DeepDoc Table Structure Contract

## Pipeline
```text
Table Region (Image Crop from Phase 04-03)
     ↓
TableStructureRecognizer (Table Transformer)
     ↓
Table Grid (Rows, Columns, Spanning Cells)
     ↓
OCR TextBlocks (from Phase 04-02)
     ↓
Cell Mapping (Intersection over Area)
     ↓
TableStructure (Canonical Representation)
     ├── to_markdown()
     └── to_html()
```

## Model
- **Model Name**: Table Transformer for Object Detection (Structure Recognition)
- **Version**: `microsoft/table-transformer-structure-recognition`
- **Source**: HuggingFace Hub
- **License**: MIT
- **Runtime**: `transformers`, `torch`, `timm`
- **Device**: CPU (default)
- **Weights Cache**: `assets/table`

## Coordinate System
- Bounding boxes strictly follow `[xmin, ymin, xmax, ymax]`.
- Output table cells use **page-level coordinates**.
- Because the TSR model processes an isolated cropped table region, bounding box coordinates generated during inference are mathematically translated back into absolute page coordinates. This allows seamless correlation with `TextBlock` OCR boxes.

## Cell Assignment (OCR Mapping)
- Unmodified OCR `TextBlock` instances from Phase 04-02 are geometrically correlated with `TableCell` bounds.
- We utilize an **Intersection over Area (IoA)** evaluation.
- An OCR block is assigned to the `TableCell` displaying the highest overlap area relative to the OCR block's total area.
- If an OCR block overlaps multiple cells roughly equally, the assignment prioritizes the cell encompassing the highest absolute intersection value.
- Within a single cell containing multiple OCR blocks, blocks are joined conservatively following top-to-bottom spatial sorting.
- Empty cells remain correctly empty and structurally preserved. Unassigned OCR blocks falling outside structured layout bounds are omitted from the canonical Table representations (to avoid hallucinated column insertions).

## Financial Data Preservation
- All textual values, including commas, decimal places, parantheses for negatives (e.g. `(500.00)`), and currency signs are fully preserved as extracted by the OCR engine.
- No arithmetic logic or float casting occurs during TSR parsing.

## Merged Cells
- The model detects natively spanned layouts via class label `5: 'table spanning cell'`.
- Spanning cells are projected onto the standard row/column grid, merging affected underlying standard cells.
- The top-left cell inside the span receives `row_span > 1` or `column_span > 1`.
- The merged underlying cells are flagged inactive, preserving canonical geometry.

## Serialization
- **Markdown**: Useful for simple embedding pipelines. Cannot faithfully reproduce `colspan`/`rowspan`. Merged header information simply populates the initial cell position in standard markdown grid formatting.
- **HTML**: Structurally richest format. Faithfully uses `colspan` and `rowspan` DOM properties, providing flawless reproduction of deeply merged enterprise financial tables.

## Constraints
- No structural chunking is applied at this tier. The structured table remains globally instantiated for chunking pipelines in future stages.
- No Database ORM properties exist inside TSR logic.
