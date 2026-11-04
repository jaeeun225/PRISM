"""Pillow-only profile card renderer; loaded only by the profile page."""
from io import BytesIO
from pathlib import Path
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter, ImageChops

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
        left, region, bottle_y = 70, 860, 395
    else:
        label('SIGNATURE COLLECTION', 70, 250, 865)
        left, region, bottle_y = 70, 865, 315
        d.line((985, 250, 985, 900), fill=ornament, width=1)
    n = len(signatures)
    box_w, box_h, gap = 250, 312, 28
    if not vertical and n == 3 and 3*265+2*gap <= region:
        box_w, box_h = 265, round(265*1.25)
    name_lines = [limited(row['name'],30,box_w+4,2,True) for row in signatures]
    name_height = max(((len(lines)-1)*37 + font(30,True).getbbox(lines[-1],anchor='mt')[3]
                       if lines else 0) for lines in name_lines)
    group_height = box_h+28+38+name_height
    if not vertical:
        # One shared top coordinate, based on the tallest name in this selection.
        bottle_y = round(290+(900-290-group_height)/2)
    group_bottom = bottle_y+group_height
    start = left+(region-(box_w*n+gap*(n-1)))/2
    for i, (row, data) in enumerate(zip(signatures, bottle_images)):
        x = round(start+i*(box_w+gap)); cx=x+box_w/2
        box=(x,bottle_y,x+box_w,bottle_y+box_h)
        shadow = Image.new('RGBA', image.size)
        ImageDraw.Draw(shadow).rounded_rectangle(
            (x,bottle_y+3,x+box_w,bottle_y+box_h+3), radius=16, fill=(0,0,0,24))
        shadow = shadow.filter(ImageFilter.GaussianBlur(8))
        image.paste(shadow, (0,0), shadow)
        d.rounded_rectangle(box,radius=16,fill='#FFFFFF',outline=ornament,width=1)
        bottle=None
        if data:
            try:
                with Image.open(BytesIO(data)) as source:
                    if source.width*source.height <= 16_000_000:
                        trimmed = trim_bottle_image(ImageOps.exif_transpose(source))
                        bottle=ImageOps.contain(trimmed,(round(box_w*.85),round(box_h*.85)))
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
        brand_y=bottle_y+box_h+28
        brand = ' '.join(str(row['brand'] or '').upper().split())
        brand_size, spacing = 20, 2
        while brand and sum(font(brand_size).getlength(c) for c in brand)+spacing*(len(brand)-1) > box_w:
            brand = brand[:-2].rstrip('…')+'…'
        brand_width=sum(font(brand_size).getlength(c) for c in brand)+spacing*max(0,len(brand)-1)
        bx=cx-brand_width/2
        for char in brand:
            d.text((bx,brand_y+brand_size),char,font=font(brand_size),fill=fg,anchor='ls')
            bx+=font(brand_size).getlength(char)+spacing
        name_y=brand_y+38
        for j,line in enumerate(name_lines[i]):
            text(cx,name_y+j*37,line,30,True,'mt')
    ix, iy, iw = (85, round(group_bottom+70), 830) if vertical else (1045, 250, 635)
    label('YOUR ACCORD BALANCE',ix,iy,iw,vertical)
    for i,item in enumerate(profile['sections']):
        y=iy+74+i*120
        text(ix,y+30,item['section'],30,False,'ls')
        text(ix+iw,y+30,f"{item['percent']:.1f}%",30,True,'rs')
        d.rounded_rectangle((ix,y+49,ix+iw,y+63),radius=7,fill=_mix(bg,'#FFFFFF',.55))
        end=ix+max(12,round(iw*item['percent']/100))
        d.rounded_rectangle((ix,y+49,end,y+63),radius=7,fill=section_bar_color(item['section']))
    notes=' · '.join(item['name'] for item in profile['notes']) or 'No note information available'
    note_lines = limited(notes,29,iw,2)
    note_height = ((len(note_lines)-1)*40+font(29).getbbox(note_lines[-1],anchor='mt')[3]) if note_lines else 0
    ny = round(h-90-70-note_height) if vertical else 740
    label('NOTES YOU GRAVITATE TOWARD',ix,ny,iw,vertical)
    for i,line in enumerate(note_lines):
        text(ix+iw/2 if vertical else ix,ny+70+i*40,line,29,False,'mt' if vertical else None)
    buffer=BytesIO();image.save(buffer,format='PNG',optimize=True)
    return buffer.getvalue()
