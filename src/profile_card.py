"""Pillow-only profile card renderer; loaded only by the profile page."""
from io import BytesIO
from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

PERIWINKLE = '#6E7BC9'


def serif_font(size, bold=False, font_dirs=None):
    """Windows -> Linux serif fonts -> Pillow's readable built-in fallback.

    Explicit font_dirs is also useful for testing Linux-like and fontless hosts
    without installing anything or changing the system font configuration.
    """
    names = (['georgiab.ttf', 'timesbd.ttf', 'DejaVuSerif-Bold.ttf', 'LiberationSerif-Bold.ttf']
             if bold else ['georgia.ttf', 'times.ttf', 'DejaVuSerif.ttf', 'LiberationSerif-Regular.ttf'])
    directories = font_dirs if font_dirs is not None else [
        Path(os.environ.get('WINDIR', 'C:/Windows'))/'Fonts',
        Path('/usr/share/fonts/truetype/dejavu'),
        Path('/usr/share/fonts/truetype/liberation2'),
        Path('/usr/share/fonts/truetype/liberation'),
        Path('/usr/local/share/fonts'),
    ]
    for directory in directories:
        for name in names:
            path = Path(directory)/name
            if not path.is_file():
                continue  # Pillow otherwise searches the OS again by basename.
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                pass
    if font_dirs is None:
        for name in names[2:]:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Older Pillow still has a safe, if smaller, final fallback.
        return ImageFont.load_default()


def _wrap(text, font, width):
    words = str(text or '').split()
    lines, line = [], ''
    for word in words:
        candidate = f'{line} {word}'.strip()
        if font.getlength(candidate) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
            line = ''
        for character in word:
            if line and font.getlength(line + character) > width:
                lines.append(line)
                line = ''
            line += character
    if line:
        lines.append(line)
    return lines


def _mix(color, other, amount):
    left = [int(color[i:i+2], 16) for i in (1, 3, 5)]
    right = [int(other[i:i+2], 16) for i in (1, 3, 5)]
    return tuple(round(a * (1-amount) + b * amount) for a, b in zip(left, right))


def render_card_png(profile, signatures, bottle_images, font_dirs=None):
    """Render exactly the image displayed in-app and offered for download.

    All wording is English; names/brands/notes remain original catalog text.
    Bad/missing image bytes are treated as a missing bottle, never a failed card.
    """
    if not 1 <= len(signatures) <= 3 or len(signatures) != len(bottle_images):
        raise ValueError('A profile card requires 1–3 signatures and aligned images.')
    width, margin = 1200, 64
    fg, bg = profile['foreground'], profile['background']
    font = lambda size, bold=False: serif_font(size, bold, font_dirs)
    name_font, brand_font, body_font = font(28, True), font(25), font(28)
    cell_width = min(340, (width - 2*margin - 24*(len(signatures)-1)) // len(signatures))
    prepared = [(_wrap(row['name'], name_font, cell_width-8),
                 _wrap(row['brand'], brand_font, cell_width-8)) for row in signatures]
    signature_bottom = 400 + max(len(names)*32 + len(brands)*29 for names, brands in prepared)
    accord_y = signature_bottom + 32
    notes_y = accord_y + 42 + max(1, len(profile['sections']))*50 + 18
    note_text = '  /  '.join(note['name'] for note in profile['notes']) or 'No note information available'
    note_lines = _wrap(note_text, font(29), width-2*margin)
    footer_y = notes_y + 43 + len(note_lines)*36 + 22
    image = Image.new('RGB', (width, footer_y + 55), bg)
    draw = ImageDraw.Draw(image)
    draw.text((margin, 30), 'PRISM', fill=fg, font=font(34, True))
    draw.line((margin, 78, width-margin, 78), fill=PERIWINKLE, width=5)
    draw.text((margin, 100), 'My Scent Profile', fill=fg, font=font(52, True))
    draw.text((margin, 180), 'SIGNATURE COLLECTION', fill=fg, font=font(24, True))
    group_width = cell_width*len(signatures) + 24*(len(signatures)-1)
    start_x = (width-group_width)//2
    for i, (row, data, lines) in enumerate(zip(signatures, bottle_images, prepared)):
        left = start_x + i*(cell_width+24)
        center = left + cell_width/2
        box = (int(center-94), 220, int(center+94), 380)
        draw.rounded_rectangle(box, radius=18, fill='#FFFFFF', outline=PERIWINKLE, width=2)
        bottle = None
        if data:
            try:
                with Image.open(BytesIO(data)) as opened:
                    if opened.width*opened.height <= 16_000_000:
                        bottle = ImageOps.contain(ImageOps.exif_transpose(opened).convert('RGBA'), (166, 140))
            except (OSError, ValueError, Image.DecompressionBombError):
                pass
        if bottle is not None:
            image.paste(bottle, (round(center-bottle.width/2), 230+(140-bottle.height)//2), bottle)
        else:
            # Quiet bottle silhouette, shared by the on-screen card and PNG.
            ghost = _mix('#FFFFFF', PERIWINKLE, .20)
            draw.rounded_rectangle((center-32, 274, center+32, 346), radius=9, fill=ghost)
            draw.rectangle((center-13, 258, center+13, 275), fill=ghost)
            draw.rounded_rectangle((center-18, 247, center+18, 259), radius=3,
                                   fill=_mix('#FFFFFF', PERIWINKLE, .32))
        y = 400
        for text in lines[0]:
            draw.text((center, y), text, anchor='mt', fill=fg, font=name_font)
            y += 32
        for text in lines[1]:
            draw.text((center, y+2), text, anchor='mt', fill=fg, font=brand_font)
            y += 29
    draw.text((margin, accord_y), 'YOUR ACCORD BALANCE', fill=fg, font=font(26, True))
    track = _mix(bg, fg, .16)
    for i, section in enumerate(profile['sections']):
        y = accord_y + 42 + i*50
        draw.text((margin, y), section['section'], fill=fg, font=body_font)
        draw.text((width-margin, y), f"{section['percent']:.1f}%", anchor='rt', fill=fg, font=font(28, True))
        bar_y = y + 33
        draw.rounded_rectangle((margin, bar_y, width-margin, bar_y+6), radius=4, fill=track)
        end = margin + round((width-2*margin)*section['percent']/100)
        if end > margin:
            draw.rounded_rectangle((margin, bar_y, end, bar_y+6), radius=4, fill=PERIWINKLE)
    if not profile['sections']:
        draw.text((margin, accord_y+42), 'No wheel-mapped accord information', fill=fg, font=body_font)
    draw.text((margin, notes_y), 'NOTES YOU GRAVITATE TOWARD', fill=fg, font=font(26, True))
    for i, line in enumerate(note_lines):
        draw.text((margin, notes_y+43+i*36), line, fill=fg, font=font(29))
    draw.line((margin, footer_y-14, width-margin, footer_y-14), fill=track, width=2)
    draw.text((margin, footer_y), 'A portrait of your fragrance taste', fill=fg, font=font(23))
    draw.text((width-margin, footer_y), f"{len(signatures)} SIGNATURE" + ('S' if len(signatures)>1 else ''),
              anchor='rt', fill=fg, font=font(23, True))
    buffer = BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()
