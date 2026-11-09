"""Generate a Windows .ico using Pillow in the GitHub Actions build."""
from pathlib import Path
from PIL import Image, ImageDraw

target = Path(__file__).parent / "assets" / "heerlen.ico"
target.parent.mkdir(parents=True, exist_ok=True)
im = Image.new("RGBA", (256, 256), (3, 12, 27))
d = ImageDraw.Draw(im)
d.rounded_rectangle((15, 15, 241, 241), radius=49,
                    fill=(6, 24, 45), outline=(22, 214, 255), width=9)
d.arc((50, 58, 205, 214), 155, 385, fill=(55, 239, 127), width=18)
d.rounded_rectangle((105, 102, 151, 186), radius=19, fill=(22, 214, 255))
d.ellipse((104, 175, 152, 218), fill=(22, 214, 255))
d.line([(128, 206), (128, 225)], fill=(239, 249, 255), width=8)
im.save(target, format="ICO", sizes=[(16, 16), (24, 24), (32, 32),
                                      (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"Windows pictogram aangemaakt: {target}")
