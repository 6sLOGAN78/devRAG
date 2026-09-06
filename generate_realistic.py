from PIL import Image, ImageDraw, ImageFont

img = Image.new('RGB', (800, 1000), color = (255, 255, 255))
d = ImageDraw.Draw(img)

# Header
d.rectangle([50, 50, 750, 100], fill=(200, 200, 200))
d.text((60, 60), "Annual Report 2024 - Header", fill=(0,0,0))

# Col 1
d.rectangle([50, 120, 380, 800], outline=(0,0,0), width=2)
d.text((60, 130), "Column 1 Text Line 1", fill=(0,0,0))
d.text((60, 160), "Column 1 Text Line 2", fill=(0,0,0))
d.text((60, 190), "Column 1 Text Line 3", fill=(0,0,0))

# Col 2
d.rectangle([420, 120, 750, 800], outline=(0,0,0), width=2)
d.text((430, 130), "Column 2 Text Line 1", fill=(0,0,0))
d.text((430, 160), "Column 2 Text Line 2", fill=(0,0,0))
d.text((430, 190), "Column 2 Text Line 3", fill=(0,0,0))

img.save('tests/fixtures/multi_column_sample.png')
