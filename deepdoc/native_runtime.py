"""Native entry points selected only by the isolated service."""

from deepdoc.ocr import OCR


class NativeRuntime(OCR):
    capabilities = ["ocr", "pdf", "layout"]

    def __init__(self, runtime):
        super().__init__(runtime)
        # Load the implemented backend before advertising readiness.
        runtime.session("layout.onnx")

    def layout_image(self, content):
        from dataclasses import asdict

        from PIL import Image

        from deepdoc.geometry import LABELS
        from deepdoc.ocr import decode_image

        decoded = decode_image(content)
        height, width = decoded.shape[:2]
        regions = self.layout(Image.fromarray(decoded[:, :, ::-1]), (width, height))
        return {"schema_version": 1, "width": width, "height": height,
                "regions": [{**asdict(region), "label": LABELS[region.label_id]} for region in regions]}

    def layout(self, image, page_size):
        from deepdoc.layout import Layout

        return Layout(self.runtime).detect(image, page_size)

    def process_pdf(self, operation, content, options):
        from deepdoc.pdf_service import process

        return process(operation, content, options, self)
