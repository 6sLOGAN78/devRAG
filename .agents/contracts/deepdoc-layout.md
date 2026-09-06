# DeepDoc Layout Contract

## Layout Recognition Pipeline
```text
Page Image
    ↓
LayoutRecognizer (YOLOv8 DocLayNet)
    ↓
LayoutRegion[] (header, footer, title, paragraph/text, figure, table, unknown)
    ↓
OCR TextBlock[] (from OcrEngine)
    ↓
Spatial Correlation (Intersection over Area)
    ↓
Reading Order (Top-bottom / Multi-column X-clustering)
    ↓
PageNode (containing layout-enriched TextBlocks)
```

## Model
- **Model name**: YOLOv8 Document Layout Analysis (`vaivTA/yolov8n_doclaynet`)
- **Model source**: HuggingFace Hub
- **Weights location**: `assets/layout/yolov8_layout.pt`
- **Runtime requirements**: `ultralytics`, `torch` (CPU enabled), OpenCV

## Supported Layout Classes
The model's native DocLayNet classes are mapped to DeepDoc classes as follows:
- `Page-header` -> `header`
- `Page-footer` -> `footer`
- `Title`, `Section-header` -> `title`
- `Text`, `List-item`, `Caption`, `Footnote` -> `paragraph/text`
- `Picture`, `Formula` -> `figure`
- `Table` -> `table`
- Unmapped/Unknown -> `unknown`

## Bounding Box Convention
Coordinates are standardized to a pixel-based origin tracking from the top-left corner `(0, 0)` using the format `[xmin, ymin, xmax, ymax]`. This seamlessly matches the 04-02 OCR representation.

## OCR Correlation
OCR blocks are assigned to a layout region using **Intersection over Area (IoA)** relative to the OCR block's area. If a block's area overlaps a layout region by more than a configurable threshold (`iou_threshold = 0.5`), it is assigned to that region.
If an OCR block does not intersect with any layout region (or falls below the threshold), its `layout_type` is marked as `unknown` and its metadata preserves its original detection.

## Reading Order
1. **Header/Footer**: Headers are extracted and placed at the top of the reading order (sorted by Y). Footers are placed at the bottom.
2. **Multi-Column Main Content**: Main content regions are clustered by their X-center coordinates relative to their widths. Regions falling into the same horizontal band are clustered into a column.
3. Columns are then sorted Left-to-Right.
4. Within each column, layout regions are sorted Top-to-Bottom.
5. Within each layout region, assigned OCR `TextBlock`s are sorted Top-to-Bottom.
6. Finally, `unknown` (unassigned) OCR blocks are appended to the main content (or fallback top-to-bottom).

## Failure Handling
- **Layout detection fails**: Raises `ParsingFailureError` capturing the inference exception.
- **OCR has no matching layout**: The `TextBlock` layout_type becomes `unknown`. Text is never lost.
- **Low confidence detection**: Regions below the `confidence_threshold` (default 0.5) are completely ignored during inference.
- **No regions detected**: The layout parser returns an empty array, and all OCR blocks gracefully become `unknown` and are sorted top-to-bottom.
