"""Encode approved artwork as a multi-resolution Windows icon."""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

def fitted_artwork(source):
    # Ignore almost invisible pixels outside the actual mark when fitting it.
    bounds = source.getchannel('A').point(lambda value: 255 if value >= 32 else 0).getbbox()
    if bounds is None:
        raise ValueError('Icon artwork is empty')
    mark = source.crop(bounds)
    side = max(mark.size)
    canvas = Image.new('RGBA', (side, side))
    canvas.alpha_composite(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
    return canvas

def main():
    source = fitted_artwork(Image.open(ROOT / 'assets/geoforma_logo_map_pen.png').convert('RGBA'))
    source.save(ROOT / 'assets/geoforma_map_pen.ico', sizes=[(s, s) for s in SIZES])
    sheet = Image.new('RGB', (640, 220), '#f3f4f6')
    draw = ImageDraw.Draw(sheet)
    for row, background in enumerate(('#f3f4f6', '#20242b')):
        draw.rectangle((0, row * 110, 640, (row + 1) * 110), fill=background)
        for index, size in enumerate(SIZES[:7]):
            mark = source.resize((size, size), Image.Resampling.LANCZOS)
            x, y = 25 + index * 87, row * 110 + 12
            sheet.paste(mark, (x, y), mark)
            draw.text((x, row * 110 + 85), f'{size}px', fill='#8395a6')
    sheet.save(ROOT / 'assets/geoforma_icon_preview.png')
    with Image.open(ROOT / 'assets/geoforma_map_pen.ico') as icon:
        assert icon.ico.sizes() == {(s, s) for s in SIZES}
    print('ICO verified:', SIZES)

if __name__ == '__main__':
    main()
