"""Session profile summaries, using existing raw vectors and wheel functions."""
from collections import Counter
import colorsys
import math

import numpy as np

from .scent_map import (SECTION_ORDER, contrast_text_color, interp_color_from_position,
                        radius_to_hsl, safe_eval)

# Profile-only display palette. Map coordinates/colors and artifact hashes do not
# depend on this module. Change this one tuple to tune all profile backgrounds.
PROFILE_PASTEL = (70., 85.)  # saturation %, lightness %
LOW_RESULTANT_THRESHOLD = .05


def hsl_hex(hue, saturation, lightness):
    rgb = colorsys.hls_to_rgb((hue % 360) / 360, lightness / 100, saturation / 100)
    return '#' + ''.join(f'{round(v * 255):02X}' for v in rgb)


def pastel_colors(hue, pastel=None):
    saturation, lightness = PROFILE_PASTEL if pastel is None else pastel
    background = hsl_hex(hue, saturation, lightness)
    foreground = contrast_text_color(background)
    if contrast_ratio(background, foreground) < 4.5:
        foreground = max(('#000000', '#FFFFFF'), key=lambda color: contrast_ratio(background, color))
    return dict(background=background, foreground=foreground,
                contrast=contrast_ratio(background, foreground),
                hsl=[round(hue, 2), float(saturation), float(lightness)])


def contrast_ratio(background, foreground):
    """WCAG ratio for diagnostics; selection uses the shared contrast function."""
    def luminance(color):
        values = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
        return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))
    lo, hi = sorted([luminance(background), luminance(foreground)])
    return (hi + .05) / (lo + .05)


def summarize_profile(accord_rows, note_values, section_angles, pastel=None):
    """Equal fragrance weights: L1-normalize each mapped row, then average.

    Unknown/unmapped accords cannot define a wheel position and contribute only
    their notes. Notes are multi-hot per layer, accumulating across layers and
    fragrances, exactly like build_note_matrix's 1/2/3 weighting.
    """
    rows = np.asarray(accord_rows, dtype=np.float64)
    if rows.ndim != 2 or rows.shape[1] != len(SECTION_ORDER) or not 1 <= len(rows) <= 3:
        raise ValueError('A profile requires one to three aligned 14-section vectors.')
    if len(note_values) != len(rows) or not np.isfinite(rows).all() or (rows < 0).any():
        raise ValueError('Invalid profile vectors/notes.')
    totals = rows.sum(axis=1)
    mapped = totals > 0
    mean = (rows[mapped] / totals[mapped, None]).mean(axis=0) if mapped.any() else np.zeros(14)
    top = sorted(range(len(mean)), key=lambda i: (-mean[i], i))
    sections = [{'section': SECTION_ORDER[i], 'percent': float(mean[i] * 100)}
                for i in top if mean[i] > 0][:3]
    centers = {name: float(section_angles[name]['center']) for name in SECTION_ORDER}
    vx = sum(float(w) * math.sin(math.radians(centers[name])) for name, w in zip(SECTION_ORDER, mean))
    vy = sum(float(w) * math.cos(math.radians(centers[name])) for name, w in zip(SECTION_ORDER, mean))
    radius = min(1., math.hypot(vx, vy))
    angle = math.degrees(math.atan2(vx, vy)) % 360 if mapped.any() else None
    hue, chroma = interp_color_from_position(angle, centers) if angle is not None else (0., 1.)
    saturation, lightness = radius_to_hsl(radius)
    # Match compute_scent_map's stored precision and the app's HSL->RGB rounding.
    map_hsl = [round(hue, 2), round(saturation * chroma * 100, 1), round(lightness * 100, 1)]
    map_background = hsl_hex(*map_hsl)
    color_section = None
    if angle is None:
        display_hue, color_source = 232., 'unmapped'
    elif radius < LOW_RESULTANT_THRESHOLD:
        # Near cancellation, tiny numerical changes can rotate angle wildly.
        # Prefer the largest mean section; ties use fixed SECTION_ORDER, so
        # reordering the same signatures never changes the chosen family.
        peak = float(mean.max())
        representative = next(i for i, value in enumerate(mean) if abs(value - peak) <= 1e-12)
        color_section = SECTION_ORDER[representative]
        display_hue, _ = interp_color_from_position(centers[color_section], centers)
        color_source = 'dominant_section'
    else:
        display_hue, color_source = hue, 'wheel_angle'
    colors = pastel_colors(display_hue, pastel)
    notes = Counter()
    for value in note_values:
        parsed = safe_eval(value) if isinstance(value, str) else value
        for layer, weight in [('Top', 1), ('Middle', 2), ('Base', 3)]:
            items = parsed.get(layer, []) if isinstance(parsed, dict) else []
            names = {str(item.get('name', '')).strip().lower() for item in items
                     if isinstance(item, dict)} if isinstance(items, list) else set()
            for name in names - {'', 'n/a', 'na', 'none', 'null'}:
                notes[name] += weight
    top_notes = [{'name': name, 'weight': int(weight)}
                 for name, weight in sorted(notes.items(), key=lambda item: (-item[1], item[0]))[:5]]
    return dict(sections=sections, notes=top_notes, mean_vector=mean.tolist(),
                angle=angle, radius=radius, map_hsl=map_hsl, map_background=map_background,
                display_hue=float(display_hue), color_source=color_source, color_section=color_section,
                **colors,
                unmapped_count=int((~mapped).sum()), signature_count=len(rows))
