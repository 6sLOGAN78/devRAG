from PIL import Image, ImageDraw, ImageFont

# A financial table with a merged header
img = Image.new('RGB', (800, 300), color=(255, 255, 255))
d = ImageDraw.Draw(img)

# Table boundary
d.rectangle([50, 50, 750, 250], outline=(0,0,0), width=2)

# Row lines
d.line([(50, 100), (750, 100)], fill=(0,0,0), width=2)
d.line([(50, 150), (750, 150)], fill=(0,0,0), width=1)
d.line([(50, 200), (750, 200)], fill=(0,0,0), width=1)

# Column lines (only below header)
d.line([(300, 100), (300, 250)], fill=(0,0,0), width=1)
d.line([(525, 100), (525, 250)], fill=(0,0,0), width=1)

# Texts
# Header (merged over the columns)
d.text((350, 70), "Financial Results 2024", fill=(0,0,0))

# Subheaders
d.text((60, 120), "Metric", fill=(0,0,0))
d.text((310, 120), "Q1", fill=(0,0,0))
d.text((535, 120), "Q2", fill=(0,0,0))

# Data Row 1
d.text((60, 170), "Revenue", fill=(0,0,0))
d.text((310, 170), "$ 1,250.50", fill=(0,0,0))
d.text((535, 170), "$ 1,400.00", fill=(0,0,0))

# Data Row 2
d.text((60, 220), "Net Income", fill=(0,0,0))
d.text((310, 220), "(500.00)", fill=(0,0,0))
d.text((535, 220), "$ 150.00", fill=(0,0,0))

img.save('tests/fixtures/financial_table.png')
