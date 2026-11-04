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


def section_bar_color(section):
    """Same anchor, saturation and lightness as app.py section labels/pills."""
    import colorsys
    from .scent_map import COLOR_HUE_ANCHOR
    rgb = colorsys.hls_to_rgb(COLOR_HUE_ANCHOR[section] / 360, .40, .75)
    return '#' + ''.join(f'{round(channel*255):02x}' for channel in rgb)


def render_card_png(profile, signatures, bottle_images, font_dirs=None, orientation='horizontal'):
    if not 1 <= len(signatures) <= 3 or len(signatures) != len(bottle_images):
        raise ValueError('A profile card requires 1–3 signatures and aligned images.')
    if orientation not in ('horizontal', 'vertical'):
        raise ValueError('Unknown card orientation')
    vertical = orientation == 'vertical'
    w, h = (1000, 1750) if vertical else (1750, 1000)
    bg, fg = profile['background'], profile['foreground']
    image = Image.new('RGB', (w, h), bg)
    d = ImageDraw.Draw(image)
    font = lambda size, bold=False: serif_font(size, bold, font_dirs)
    ornament = _mix(bg, fg, .22)
    d.rounded_rectangle((35, 35, w-35, h-35), radius=25, outline=ornament, width=2)
    def text(x, y, value, size=28, bold=False, anchor=None):
        d.text((x, y), value, font=font(size, bold), fill=fg, anchor=anchor)
    def limited(value, size, width, count=2, bold=False):
        lines = _wrap(value, font(size, bold), width)
        if len(lines) > count:
            lines = lines[:count]
            tail = lines[-1]
            while tail and font(size, bold).getlength(tail+'…') > width:
                tail = tail[:-1]
            lines[-1] = tail+'…'
        return lines
    def label(value, x, y, width, centered=False):
        face = font(21, True)
        spacing = 3
        length = sum(face.getlength(c) for c in value) + spacing*(len(value)-1)
        left = x+(width-length)/2 if centered else x
        for c in value:
            d.text((left, y), c, font=face, fill=fg)
            left += face.getlength(c)+spacing
        d.line((x, y+40, x+width, y+40), fill=ornament, width=1)
    text(w/2 if vertical else 70, 85, 'PRISM', 33, True, 'mt' if vertical else None)
    text(w/2 if vertical else 70, 140, 'My Scent Profile', 64, True, 'mt' if vertical else None)
    if vertical:
        label('SIGNATURE COLLECTION', 70, 285, 860, True)
        left, region, bottle_y = 70, 860, 390
    else:
        label('SIGNATURE COLLECTION', 70, 250, 865)
        left, region, bottle_y = 70, 865, 335
        d.line((985, 250, 985, 825), fill=ornament, width=1)
    n = len(signatures)
    box_w, box_h, gap = 250, 270, 28
    start = left+(region-(box_w*n+gap*(n-1)))/2
    for i, (row, data) in enumerate(zip(signatures, bottle_images)):
        x = round(start+i*(box_w+gap)); cx=x+box_w/2
        box=(x,bottle_y,x+box_w,bottle_y+box_h)
        d.rounded_rectangle((x+3,bottle_y+4,x+box_w+3,bottle_y+box_h+4),radius=16,fill=ornament)
        d.rounded_rectangle(box,radius=16,fill='#FFFFFF',outline=ornament,width=1)
        bottle=None
        if data:
            try:
                with Image.open(BytesIO(data)) as source:
                    if source.width*source.height <= 16_000_000:
                        bottle=ImageOps.contain(ImageOps.exif_transpose(source).convert('RGBA'),(230,240))
            except (OSError, ValueError, Image.DecompressionBombError):
                pass
        if bottle is not None:
            image.paste(bottle,(round(cx-bottle.width/2),round(bottle_y+(box_h-bottle.height)/2)),bottle)
        else:
            ghost=_mix('#FFFFFF',PERIWINKLE,.20)
            cy=bottle_y+box_h/2
            d.rounded_rectangle((cx-42,cy-25,cx+42,cy+65),radius=12,fill=ghost)
            d.rectangle((cx-17,cy-48,cx+17,cy-24),fill=ghost)
            d.rounded_rectangle((cx-23,cy-60,cx+23,cy-46),radius=4,fill=ghost)
        name_y=bottle_y+box_h+24
        for j,line in enumerate(limited(row['name'],30,box_w+4,2,True)):
            text(cx,name_y+j*37,line,30,True,'mt')
        brand=limited(row['brand'],25,box_w,1)[0] if row['brand'] else ''
        text(cx,name_y+82,brand,25,False,'mt')
    ix, iy, iw = (85, 930, 830) if vertical else (1045, 250, 635)
    label('YOUR ACCORD BALANCE',ix,iy,iw,vertical)
    for i,item in enumerate(profile['sections']):
        y=iy+74+i*100
        text(ix,y,item['section'],30)
        text(ix+iw,y,f"{item['percent']:.1f}%",30,True,'rt')
        d.rounded_rectangle((ix,y+49,ix+iw,y+61),radius=6,fill='#E5E5E5',outline=ornament,width=1)
        end=ix+max(12,round(iw*item['percent']/100))
        d.rounded_rectangle((ix,y+49,end,y+61),radius=6,fill=section_bar_color(item['section']))
    ny = 1350 if vertical else 665
    label('NOTES YOU GRAVITATE TOWARD',ix,ny,iw,vertical)
    notes=' · '.join(item['name'] for item in profile['notes']) or 'No note information available'
    for i,line in enumerate(limited(notes,29,iw,2)):
        text(ix+iw/2 if vertical else ix,ny+70+i*40,line,29,False,'mt' if vertical else None)
    footer=h-130
    d.line((70,footer-24,w-70,footer-24),fill=ornament,width=1)
    # Same serif family, a restrained smaller caption instead of an extra font.
    text(70,footer,'A portrait of your fragrance taste',23)
    text(w-70,footer,f'{n} SIGNATURE'+('S' if n>1 else ''),23,True,'rt')
    buffer=BytesIO();image.save(buffer,format='PNG',optimize=True)
    return buffer.getvalue()
