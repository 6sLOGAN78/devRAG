"""Native entry points selected only by the isolated service."""

from deepdoc.ocr import OCR


class NativeRuntime(OCR):
    capabilities = ["ocr", "pdf"]

    def process_pdf(self, operation, content, options):
        from deepdoc.pdf_service import process

        return process(operation, content, options, self)
