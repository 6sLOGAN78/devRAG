"""Native entry points selected only by the isolated service."""

from deepdoc.ocr import OCR


class NativeRuntime(OCR):
    capabilities = ["ocr", "pdf", "layout", "images", "tsr"]

    def __init__(self, runtime):
        super().__init__(runtime)
        # Load the implemented backend before advertising readiness.
        runtime.session("layout.onnx")
        runtime.session("tsr.onnx")

    def layout_image(self, content):
        from dataclasses import asdict

        from PIL import Image

        from deepdoc.geometry import LABELS
        from deepdoc.ocr import decode_image

        decoded = decode_image(content)
        height, width = decoded.shape[:2]
        regions = self.layout(Image.fromarray(decoded[:, :, ::-1]), (width, height))
        return {"schema_version": 1, "width": width, "height": height, "regions": [{**asdict(region), "label": LABELS[region.label_id]} for region in regions]}

    def layout(self, image, page_size):
        from deepdoc.layout import Layout

        return Layout(self.runtime).detect(image, page_size)

    def table_tokens(self, image):
        import io

        from deepdoc.tables import TextToken

        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        return [TextToken(span["text"], tuple(span["box"])) for span in self.ocr(buffer.getvalue())["spans"]]

    def table_image(self, content):
        import math

        from PIL import Image

        from deepdoc.model_runtime import NativeError
        from deepdoc.ocr import decode_image
        from deepdoc.tables import parse_table

        decoded = decode_image(content)
        image = Image.fromarray(decoded[:, :, ::-1])
        regions = [r for r in self.layout(image, image.size) if r.label_id == 5]
        if len(regions) != 1:
            raise NativeError("table_selection_required")
        x0, top, x1, bottom = regions[0].box
        box = (math.floor(x0), math.floor(top), math.ceil(x1), math.ceil(bottom))
        cropped = image.crop(box)
        tokens = self.table_tokens(cropped)
        table = parse_table(self.runtime, cropped, tokens)
        return {"schema_version": 1, "width": image.width, "height": image.height, "source_box": box, "table": table.to_wire()}

    def normalize_image(self, content):
        from deepdoc.images import normalize_image
        from rag.parsers.assets import encode_asset

        return {"schema_version": 1, "image": encode_asset(normalize_image(content))}

    def process_pdf(self, operation, content, options):
        from deepdoc.pdf_service import process

        return process(operation, content, options, self)
