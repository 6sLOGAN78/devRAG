from reportlab.pdfgen import canvas
c = canvas.Canvas("tests/fixtures/sample.pdf")
c.drawString(100, 750, "Integration Test Document")
c.drawString(100, 700, "This is a test paragraph for the ingestion pipeline.")
c.save()
