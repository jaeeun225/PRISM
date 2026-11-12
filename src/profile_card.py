"""Pillow-only profile card renderer; loaded only by the profile page."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
import os
import logging
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter, ImageChops

PERIWINKLE = '#6E7BC9'


def serif_font(size, bold=False, font_dirs=None):
    directories = None if font_dirs is None else tuple(str(path) for path in font_dirs)
    return _serif_font_cached(size, bold, directories)


@lru_cache(maxsize=1)
def _warn_bundled_font():
    logging.getLogger(__name__).warning('Bundled Gelasio font unavailable; using system serif fallback.')


@lru_cache(maxsize=64)
def _serif_font_cached(size, bold=False, font_dirs=None):
    """Bundled Gelasio -> Windows/Linux serif -> Pillow fallback, cached by size/weight.

    Explicit font_dirs restricts system fallbacks for tests; bundled fonts still
    have priority without depending on the system font configuration.
    """
    bundled = Path(__file__).resolve().parents[1]/'assets/fonts'/('Gelasio-Bold.ttf' if bold else 'Gelasio-Regular.ttf')
    try:
        return ImageFont.truetype(str(bundled), size)
    except (OSError, ValueError):
        _warn_bundled_font()
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


PROFILE_FONT_VERSION = 'josefin-sans-signature-tint-v3'
PROFILE_BACKGROUND_WHITE_MIX = .60  # Keep 40% of the calculated personal color.


@lru_cache(maxsize=1)
def _warn_card_font():
    logging.getLogger(__name__).warning('Bundled Josefin Sans unavailable; using existing font fallback.')


@lru_cache(maxsize=64)
def _card_font_cached(size, bold, font_dirs):
    path = Path(__file__).resolve().parents[1]/'assets/fonts'/('JosefinSans-Bold.ttf' if bold else 'JosefinSans-Regular.ttf')
    try:
        # These official static faces use lining figures by default (no onum/lnum substitution).
        return ImageFont.truetype(str(path), size)
    except (OSError, ValueError):
        _warn_card_font()
        return serif_font(size, bold, font_dirs)


def card_font(size, bold=False, font_dirs=None):
    directories = None if font_dirs is None else tuple(str(path) for path in font_dirs)
    return _card_font_cached(size, bold, directories)


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


def balanced_name_lines(value, font, width):
    """Balance two complete lines; fall back to existing wrapping/ellipsis for long names."""
    value = ' '.join(str(value or '').split())
    if font.getlength(value) <= width:
        return [value] if value else []
    words = value.split()
    candidates = []
    for split in range(1, len(words)):
        left, right = ' '.join(words[:split]), ' '.join(words[split:])
        lw, rw = font.getlength(left), font.getlength(right)
        if max(lw, rw) <= width:
            orphan = 1 if len(words) >= 4 and min(split, len(words)-split) == 1 else 0
            candidates.append(((orphan, abs(lw-rw), abs(split-(len(words)-split))), [left,right]))
    return min(candidates, key=lambda pair: pair[0])[1] if candidates else _wrap(value,font,width)


def section_bar_color(section):
    """Same anchor, saturation and lightness as app.py section labels/pills."""
    import colorsys
    from .scent_map import COLOR_HUE_ANCHOR
    rgb = colorsys.hls_to_rgb(COLOR_HUE_ANCHOR[section] / 360, .40, .75)
    return '#' + ''.join(f'{round(channel*255):02x}' for channel in rgb)


def trim_bottle_image(source):
    """Trim only near-white outer margins, retaining faint detail and safety padding."""
    rgba = source.convert('RGBA')
    white = Image.new('RGBA', rgba.size, '#FFFFFF')
    white.alpha_composite(rgba)
    rgb = white.convert('RGB')
    w, h = rgb.size
    # Non-white/lightly colored backgrounds are left alone, rather than segmented.
    if any(min(rgb.getpixel(p)) < 245 for p in [(0,0),(w-1,0),(0,h-1),(w-1,h-1)]):
        return rgba
    difference = ImageChops.difference(rgb, Image.new('RGB', rgb.size, '#FFFFFF'))
    bounds = difference.point(lambda value: 255 if value > 5 else 0).getbbox()
    if not bounds or (bounds[2]-bounds[0])*(bounds[3]-bounds[1]) < w*h*.005:
        return rgba
    padding = max(8, round(max(w,h)*.035))
    left, top, right, bottom = bounds
    return rgba.crop((max(0,left-padding), max(0,top-padding),
                      min(w,right+padding), min(h,bottom+padding)))


def profile_card_date():
    try:
        seoul = ZoneInfo('Asia/Seoul')
    except ZoneInfoNotFoundError:
        seoul = timezone(timedelta(hours=9))
    today = datetime.now(seoul)
    months = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
    return f'{months[today.month - 1]} {today.day}, {today.year}'


def render_card_png(profile, signatures, bottle_images, font_dirs=None, orientation='horizontal', created_on=None):
    """Signature Tint: the existing profile color on a white-leaning editorial card."""
    from .profile_labels import display_name
    if not 1 <= len(signatures) <= 3 or len(signatures) != len(bottle_images):
        raise ValueError('A profile card requires 1–3 signatures and aligned images.')
    if orientation not in ('horizontal', 'vertical'):
        raise ValueError('Unknown card orientation')
    vertical = orientation == 'vertical'
    w, h = (1000, 1750) if vertical else (1750, 1000)
    # Presentation only: never mutate the calculated profile or its palette.
    bg = _mix(profile['background'], '#FFFFFF', PROFILE_BACKGROUND_WHITE_MIX)
    ink, muted, hairline = '#1A1A1A', '#6B6B72', '#D6D6DA'
    image = Image.new('RGB', (w, h), bg)
    d = ImageDraw.Draw(image)
    font = lambda size, bold=False: card_font(size, bold, font_dirs)
    d.rectangle((0, 0, w-1, h-1), outline=_mix(profile['background'], hairline, .62), width=1)

    def text(x, y, value, size=28, bold=False, anchor=None, fill=ink):
        d.text((x, y), value, font=font(size, bold), fill=fill, anchor=anchor)

    def limited(value, size, width, count=2, bold=False):
        lines = _wrap(value, font(size, bold), width)
        if len(lines) > count:
            lines = lines[:count]
            tail = lines[-1]
            while tail and font(size, bold).getlength(tail+'…') > width:
                tail = tail[:-1]
            lines[-1] = tail+'…'
        return lines

    def tracked(value, x, y, size, spacing, centered=False, fill=ink):
        face = font(size)
        length = sum(face.getlength(c) for c in value) + spacing*max(0, len(value)-1)
        left = x-length/2 if centered else x
        for c in value:
            d.text((left, y), c, font=face, fill=fill, anchor='lt')
            left += face.getlength(c)+spacing

    def label(value, x, y, width, centered=False):
        tracked(value, x+width/2 if centered else x, y, 21, 3, centered)
        d.line((x, y+40, x+width, y+40), fill=hairline, width=1)

    mark_size, brand_gap = 70, 12
    brand_face = font(33)
    brand_width = brand_face.getlength('PRISM')
    brand_x = round((w-mark_size-brand_gap-brand_width)/2) if vertical else 70
    mark_y, title_y = (95, 225) if vertical else (61, 140)
    with Image.open(Path(__file__).resolve().parents[1]/'assets'/'logo_mark.png') as logo:
        mark = logo.convert('RGBA').resize((mark_size, mark_size), Image.Resampling.LANCZOS)
        image.paste(mark, (brand_x, mark_y), mark)
    _, glyph_top, _, glyph_bottom = brand_face.getbbox('PRISM')
    brand_y = mark_y+(mark_size-glyph_top-glyph_bottom)/2
    d.text((brand_x+mark_size+brand_gap, brand_y), 'PRISM', font=brand_face, fill=ink)
    text(w/2 if vertical else 70, title_y, 'My Scent Profile', 56, False, 'mt' if vertical else None)
    left, region = (70, 860) if vertical else (70, 865)
    n = len(signatures)
    box_w, box_h, gap = 250, 312, 28
    if n == 3 and 3*265+2*gap <= region:
        box_w, box_h = 265, round(265*1.25)
    name_lines = []
    for row in signatures:
        # Reuse the existing display-label helper; raw names and IDs are untouched.
        value = display_name(row['name'], row['brand'])
        lines = balanced_name_lines(value, font(30), box_w+4)
        name_lines.append(lines if len(lines) <= 2 else limited(value, 30, box_w+4, 2))
    name_height = max(((len(lines)-1)*37+font(30).getbbox(lines[-1], anchor='mt')[3]
                       if lines else 0) for lines in name_lines)
    group_height = box_h+28+38+name_height
    notes = ' · '.join(item['name'] for item in profile['notes']) or 'No note information available'
    iw = 830 if vertical else 635
    note_lines = limited(notes, 29, iw, 3)
    note_height = ((len(note_lines)-1)*40+font(29).getbbox(note_lines[-1], anchor='mt')[3]) if note_lines else 0
    accord_height = 74+(len(profile['sections'])-1)*120+63 if profile['sections'] else 40
    if vertical:
        title_bottom = d.textbbox((w/2, title_y), 'My Scent Profile', font=font(56), anchor='mt')[3]
        # Equal breaks between the title, collection, accord balance and notes.
        available = h-110-title_bottom-(80+group_height)-accord_height-(70+note_height)
        section_gap = available/3
        signature_y = round(title_bottom+section_gap)
        bottle_y = signature_y+80
        iy = round(bottle_y+group_height+section_gap)
        ny = round(iy+accord_height+section_gap)
        label('SIGNATURE COLLECTION', 70, signature_y, 860, True)
        ix = 85
    else:
        label('SIGNATURE COLLECTION', 70, 250, 865)
        bottle_y = round(290+(900-290-group_height)/2)
        d.line((985, 250, 985, 900), fill=hairline, width=1)
        ix, iy, ny = 1045, 250, 740
    start = left+(region-(box_w*n+gap*(n-1)))/2
    for i, (row, data) in enumerate(zip(signatures, bottle_images)):
        x = round(start+i*(box_w+gap)); cx = x+box_w/2
        d.rectangle((x, bottle_y, x+box_w, bottle_y+box_h), fill='#FFFFFF', outline=hairline, width=1)
        bottle = None
        if data:
            try:
                with Image.open(BytesIO(data)) as source:
                    if source.width*source.height <= 16_000_000:
                        trimmed = trim_bottle_image(ImageOps.exif_transpose(source))
                        bottle = ImageOps.contain(trimmed, (round(box_w*.85), round(box_h*.85)))
            except (OSError, ValueError, Image.DecompressionBombError):
                pass
        if bottle is not None:
            image.paste(bottle, (round(cx-bottle.width/2), round(bottle_y+(box_h-bottle.height)/2)), bottle)
        else:
            ghost = _mix('#FFFFFF', muted, .20)
            cy = bottle_y+box_h/2
            d.rounded_rectangle((cx-42, cy-25, cx+42, cy+65), radius=12, fill=ghost)
            d.rectangle((cx-17, cy-48, cx+17, cy-24), fill=ghost)
            d.rounded_rectangle((cx-23, cy-60, cx+23, cy-46), radius=4, fill=ghost)
        brand_y = bottle_y+box_h+28
        brand = ' '.join(str(row['brand'] or '').upper().split())
        while brand and sum(font(20).getlength(c) for c in brand)+2*(len(brand)-1) > box_w:
            brand = brand[:-2].rstrip('…')+'…'
        tracked(brand, cx, brand_y, 20, 2, True, muted)
        for j, line in enumerate(name_lines[i]):
            text(cx, brand_y+38+j*37, line, 30, False, 'mt')
    label('YOUR ACCORD BALANCE', ix, iy, iw, vertical)
    for i, item in enumerate(profile['sections']):
        y = iy+74+i*120
        text(ix, y+30, item['section'], 30, False, 'ls')
        text(ix+iw, y+30, f"{item['percent']:.1f}%", 30, True, 'rs')
        d.rectangle((ix, y+49, ix+iw, y+63), fill='#F0F0F2')
        end = ix+max(12, round(iw*item['percent']/100))
        d.rectangle((ix, y+49, end, y+63), fill=section_bar_color(item['section']))
    label('NOTES YOU GRAVITATE TOWARD', ix, ny, iw, vertical)
    for i, line in enumerate(note_lines):
        text(ix+iw/2 if vertical else ix, ny+70+i*40, line, 29, False, 'mt' if vertical else None)
    d.text((w-70, h-58), created_on or profile_card_date(), font=font(19), fill=muted, anchor='rs')
    buffer = BytesIO(); image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()
