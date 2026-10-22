"""
PRISM Scent Map 좌표·색상 계산 로직.
"""

import ast
import colorsys
import math
import pandas as pd


# ---------------------------------------------------------------------------
# 1. 14섹션 순서 (Michael Edwards Fragrance Wheel 순서, 시계방향, Soft Amber=12시 기준)
# ---------------------------------------------------------------------------
SECTION_ORDER = [
    "Floral Amber", "Soft Amber", "Amber", "Woody Amber",  # Ambery Notes
    "Woods", "Mossy Woods", "Dry Woods",  # Woody Notes
    "Aromatic", "Citrus", "Water", "Green", "Fruity",  # Fresh Notes
    "Floral", "Soft Floral",  # Floral Notes
]

# accord -> 섹션 매핑
WHEEL_MAPPING = {
    "Floral": ["floral", "white floral", "rose", "yellow floral", "tuberose"],
    "Soft Floral": ["iris", "violet", "aldehydic", "soapy"],
    "Floral Amber": ["musky", "animalic", "beeswax", "oily"],
    "Soft Amber": ["sweet", "vanilla", "caramel", "honey", "lactonic", "almond", "powdery", "gourmand",
                   "nutty", "cacao", "chocolate", "coffee", "rum", "whiskey", "wine", "champagne",
                   "vodka", "alcohol", "coca-cola", "sake", "bitter"],
    "Amber": ["amber", "balsamic"],
    "Woody Amber": ["warm spicy", "soft spicy", "cinnamon", "oud"],
    "Woods": ["woody", "conifer", "terpenic"],
    "Mossy Woods": ["mossy", "earthy", "smoky"],
    "Dry Woods": ["leather", "patchouli", "tobacco"],
    "Aromatic": ["aromatic", "herbal", "lavender", "camphor", "fresh spicy", "anis", "savory"],
    "Citrus": ["citrus", "sour"],
    "Water": ["aquatic", "ozonic", "marine", "fresh", "salty"],
    "Green": ["green", "cannabis"],
    "Fruity": ["fruity", "tropical", "coconut", "cherry", "pear"],
}
ACCORD_TO_SECTION = {a: s for s, accs in WHEEL_MAPPING.items() for a in accs}

# 축 계산에서 제외 (태그/필터 전용) — 미네랄/합성 계열, 14섹션 어디에도 안 맞음
AXIS_EXCLUDED_ACCORDS = {
    "metallic", "mineral", "sand", "clay", "asphault", "gasoline", "rubber",
    "plastic", "vinyl", "hot iron", "industrial glue", "tennis ball", "paper",
    "bacon", "milky",
}

STRENGTH_WEIGHT = {"Dominant": 8, "Prominent": 4, "Moderate": 2, "Subtle": 1}

# 색상용 hue 앵커 (Michael Edwards Fragrance Wheel 원본 라벨 색조 기준)
COLOR_HUE_ANCHOR = {
    'Floral': 4,
    'Soft Floral': 333,
    'Floral Amber': 328,
    'Soft Amber': 326,
    'Amber': 350,
    'Woody Amber': 21,
    'Woods': 33,
    'Mossy Woods': 160,
    'Dry Woods': 53,
    'Aromatic': 245,
    'Citrus': 49,
    'Water': 196,
    'Green': 111,
    'Fruity': 24,
}

def safe_eval(x):
    """문자열로 저장된 리스트/딕셔너리를 파이썬 객체로 파싱. 실패 시 None."""
    try:
        return ast.literal_eval(x)
    except (ValueError, SyntaxError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 2. 섹션별 각도 배정 (sqrt 비례 분할)
# ---------------------------------------------------------------------------
def compute_section_angles(normalized_accords_series):
    """섹션별 향수 수를 세고, sqrt 비례로 시작각/끝각/중심각을 계산."""
    section_counts = {s: 0 for s in SECTION_ORDER}
    for lst in normalized_accords_series:
        hit = {ACCORD_TO_SECTION[a] for a in lst if a in ACCORD_TO_SECTION}
        for s in hit:
            section_counts[s] += 1

    sqrt_total = sum(math.sqrt(c) for c in section_counts.values())
    angles = {}
    cursor = 0.0
    for s in SECTION_ORDER:
        width = 360 * math.sqrt(section_counts[s]) / sqrt_total
        start, end = cursor, cursor + width
        angles[s] = {
            "start": start, "end": end, "center": (start + end) / 2,
            "width": width, "count": section_counts[s],
        }
        cursor = end
    return angles


# ---------------------------------------------------------------------------
# 3. 개별 향수 위치(각도·반경) — 가중 원형 평균
# ---------------------------------------------------------------------------
def compute_fragrance_position(normalized_accords, strength_dict, section_center):
    """반환: (최종각도, R, 사용된 accord 개수). 배치 불가 시 (None, None, 0)."""
    vx, vy, total_w, used = 0.0, 0.0, 0.0, 0
    for a in normalized_accords:
        section = ACCORD_TO_SECTION.get(a)
        if section is None:
            continue
        w = STRENGTH_WEIGHT.get(strength_dict.get(a), 1)
        rad = math.radians(section_center[section])
        vx += w * math.sin(rad)
        vy += w * math.cos(rad)
        total_w += w
        used += 1

    if total_w == 0:
        return None, None, 0

    mx, my = vx / total_w, vy / total_w
    angle = math.degrees(math.atan2(mx, my)) % 360
    R = math.sqrt(mx ** 2 + my ** 2)
    return angle, R, used


# ---------------------------------------------------------------------------
# 4. 색상(hue) — 별도 계산 없이, 위치 각도를 그대로 색상용 앵커 사이에서 보간
#    (위치 R 하나만 쓰므로, "위치는 애매한데 색은 확실하다" 같은 모순이 없음)
# ---------------------------------------------------------------------------
def interp_color_from_position(position_angle, section_center):
    """
    position_angle: compute_fragrance_position()이 반환한 최종 위치 각도
    section_center: {섹션명: 위치용 중심각도} (compute_section_angles() 결과 기반)
    반환: (hue (0~360), RGB chroma (0~1))
    """
    anchors = sorted(section_center.items(), key=lambda x: x[1])
    n = len(anchors)
    for i in range(n):
        s1, a1 = anchors[i]
        s2, a2 = anchors[(i + 1) % n]
        span = (a2 - a1) % 360
        if span == 0:
            span = 360
        rel = (position_angle - a1) % 360
        if rel <= span:
            t = rel / span
            h1, h2 = COLOR_HUE_ANCHOR[s1], COLOR_HUE_ANCHOR[s2]
            rgb1 = colorsys.hls_to_rgb((h1 % 360) / 360, 0.5, 1.0)
            rgb2 = colorsys.hls_to_rgb((h2 % 360) / 360, 0.5, 1.0)
            rgb = tuple(v1 + (v2 - v1) * t for v1, v2 in zip(rgb1, rgb2))
            hue, _, _ = colorsys.rgb_to_hls(*rgb)
            chroma = max(rgb) - min(rgb)
            return (hue * 360) % 360, chroma
    return COLOR_HUE_ANCHOR[anchors[0][0]], 1.0


def radius_to_hsl(R, min_saturation=0.03, max_lightness=0.92, min_lightness=0.5):
    """위치 R(0~1) 하나로 saturation까지 결정. R이 낮을수록(여러 계열이 섞일수록) 채도도 낮춤."""
    if R is None:
        R = 0
    saturation = min_saturation + (1 - min_saturation) * (R ** 3.0)
    lightness = max_lightness - (max_lightness - min_lightness) * (R ** 1.5)
    return saturation, lightness


# ---------------------------------------------------------------------------
# 5. 전체 파이프라인 — DataFrame 하나로 좌표/색상 컬럼 전부 계산
# ---------------------------------------------------------------------------
def compute_scent_map(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    df: 'Main Accords', 'Main Accords Percentage' 컬럼을 가진 DataFrame
    반환: (scent_map_* 컬럼이 추가된 DataFrame, 섹션별 각도 정보 dict)
    """
    df = df.copy()
    normalized_accords = df["Main Accords"].apply(safe_eval).apply(lambda x: x if isinstance(x, list) else [])
    strength_dicts = df["Main Accords Percentage"].apply(safe_eval).apply(
        lambda x: x if isinstance(x, dict) else {}
    )

    # 배치 불가(모든 accord가 미매핑) 행 제외
    def has_any_placeable(lst):
        return any(a in ACCORD_TO_SECTION for a in lst)

    placeable_mask = normalized_accords.apply(has_any_placeable)
    df = df.loc[placeable_mask].reset_index(drop=True)
    normalized_accords = normalized_accords.loc[placeable_mask].reset_index(drop=True)
    strength_dicts = strength_dicts.loc[placeable_mask].reset_index(drop=True)

    section_angles = compute_section_angles(normalized_accords)
    section_center = {s: v["center"] for s, v in section_angles.items()}

    angles, radii, hues, sats, lights, x_coords, y_coords = [], [], [], [], [], [], []
    for accs, strengths in zip(normalized_accords, strength_dicts):
        angle, R, _ = compute_fragrance_position(accs, strengths, section_center)

        if angle is not None:
            hue, chroma = interp_color_from_position(angle, section_center)
            sat, light = radius_to_hsl(R)
            sat *= chroma
        else:
            hue, sat, light = None, None, None

        angles.append(round(angle, 2) if angle is not None else None)
        radii.append(round(R, 4) if R is not None else None)
        hues.append(round(hue, 2) if hue is not None else None)
        sats.append(round(sat * 100, 1) if sat is not None else None)
        lights.append(round(light * 100, 1) if light is not None else None)

        if angle is not None and R is not None:
            x_coords.append(R * math.sin(math.radians(angle)))
            y_coords.append(R * math.cos(math.radians(angle)))
        else:
            x_coords.append(None)
            y_coords.append(None)

    df["scent_map_angle"] = angles
    df["scent_map_radius"] = radii
    df["scent_map_hue"] = hues
    df["scent_map_saturation"] = sats
    df["scent_map_lightness"] = lights
    df["scent_map_x"] = x_coords
    df["scent_map_y"] = y_coords

    return df, section_angles



def get_coordinates(ids, df):
    """Select existing finite coordinates, preserving DataFrame row order."""
    return df.loc[df['_id'].isin(ids)].dropna(subset=['scent_map_x', 'scent_map_y']).copy()


def build_highlight_trace(coords_df, ranks, scores=None, marker_size=None, show_rank=True, white_width=1):
    """Reuse prepared detail HTML; ranks and optional scores are keyed by ID."""
    import plotly.graph_objects as go
    from html import escape
    values = [ranks[identifier] for identifier in coords_df['_id']]
    colors = coords_df['marker_rgb'].tolist() if 'marker_rgb' in coords_df else coords_df['plot_color'].tolist()
    return go.Scattergl(
        x=coords_df['scent_map_x'], y=coords_df['scent_map_y'], mode='markers',
        marker=dict(size=[marker_size if marker_size is not None else recommendation_marker_size(rank) for rank in values], color=colors,
                    symbol='circle', opacity=1, line=dict(color='#ffffff', width=white_width)),
        hovertext=[row['tooltip'] if 'tooltip' in coords_df else
              f"<b>{escape(str(row['Name']))}</b><br>{escape(str(row['Brand']))}"
              for _, row in coords_df.iterrows()],
        customdata=[[rank, float(scores[identifier]) if scores is not None else None]
                    for identifier, rank in zip(coords_df['_id'], values)],
        hovertemplate=("%{hovertext}"
                       + ("<br><br><b>Rank:</b> %{customdata[0]}" if show_rank else "")
                       + ("<br><b>Similarity:</b> %{customdata[1]:.4f}" if scores is not None else "")
                       + "<extra></extra>"),
        hoverlabel=dict(align='left', bgcolor=colors,
                        font=dict(size=14, family='Georgia, Times New Roman, serif',
                                  color=[contrast_text_color(color) for color in colors])),
        name='Recommendations' if show_rank else 'Search matches', showlegend=False,
    )


def compute_zoom_range(coords_df, padding=0.15):
    """Return Plotly axis updates; give singleton/coincident points a usable span."""
    if padding < 0:
        raise ValueError('padding must be nonnegative')
    ranges = {}
    for axis in ('x', 'y'):
        values = coords_df[f'scent_map_{axis}'].dropna()
        if values.empty:
            limits = [-1.35, 1.35]
        else:
            low, high = float(values.min()), float(values.max())
            span = max(high - low, 0.1)
            midpoint = (low + high) / 2
            limits = [midpoint - span * (0.5 + padding), midpoint + span * (0.5 + padding)]
        ranges[f'{axis}axis'] = dict(range=limits, autorange=False)
    return ranges



def recommendation_marker_size(rank):
    """Linear pixel diameters: rank 1 is 27.9, rank 10 is 18; no text-size clamp."""
    return 27.9 - (min(10, max(1, rank)) - 1) * (9.9 / 9)


def contrast_text_color(color):
    """Choose white/charcoal by WCAG contrast against the actual opaque fill."""
    if color.startswith('rgb('):
        rgb = [float(v.strip()) / 255 for v in color[4:-1].split(',')]
    elif color.startswith('hsl('):
        h, sat, light = [float(v.strip().rstrip('%')) for v in color[4:-1].split(',')]
        rgb = colorsys.hls_to_rgb((h % 360) / 360, light / 100, sat / 100)
    elif color.startswith('#') and len(color) == 7:
        rgb = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
    else:
        raise ValueError(f'Unsupported marker color: {color!r}')

    def luminance(values):
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
        return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    background = luminance(rgb)
    charcoal = luminance((44 / 255, 44 / 255, 42 / 255))
    white_contrast = 1.05 / (background + 0.05)
    dark_contrast = (max(background, charcoal) + 0.05) / (min(background, charcoal) + 0.05)
    return '#2c2c2a' if dark_contrast >= white_contrast else '#ffffff'


def rank_text_color(color):
    """Compatibility wrapper; rank and tooltip colors share the same WCAG rule."""
    return contrast_text_color(color)


def build_highlight_number_trace(coords_df, ranks, scores=None):
    """Text-only rank layer; original marker fill remains completely visible."""
    trace = build_highlight_trace(coords_df, ranks, scores)
    trace.mode = 'text'
    colors = [rank_text_color(color) for color in trace.marker.color]
    trace.text = [str(ranks[i]) for i in coords_df['_id']]
    trace.textposition = 'middle center'
    trace.textfont = dict(family='Georgia, Times New Roman, serif', size=13, color=colors, weight='bold')
    return trace


def build_rank_decorations(coords_df, ranks, background='#fafaf8', marker_size=None, white_width=2, charcoal_width=1.5):
    """Outer charcoal outline; the filled marker already supplies the white ring.

    Keep the outline adjacent to the marker's white stroke, without a second
    detached white ring that can look like an empty halo at small sizes.
    """
    shapes = []
    for row in coords_df.to_dict('records'):
        x, y = float(row['scent_map_x']), float(row['scent_map_y'])
        diameter = marker_size if marker_size is not None else recommendation_marker_size(ranks[row['_id']])
        ring = diameter / 2 + white_width / 2 + charcoal_width / 2
        shapes.append(dict(type='circle', xref='x', yref='y', xsizemode='pixel', ysizemode='pixel',
                           xanchor=x, yanchor=y, x0=-ring, x1=ring, y0=-ring, y1=ring,
                           line=dict(color='#2c2c2a', width=charcoal_width),
                           fillcolor='rgba(0,0,0,0)', layer='above'))
    return shapes, [], coords_df[['scent_map_x','scent_map_y']].copy()



def separate_recommendation_points(coords_df, ranks, plot_width=420, plot_height=490, marker_size=None, axis_ranges=None):
    """Separate colliding highlight copies in estimated screen pixels only.

    Original rows and cached background are never mutated. Spacing is for the
    initial view; browser-only zoom/resize does not rerun this arrangement.
    """
    view = coords_df.copy(deep=True)
    zoom = axis_ranges if axis_ranges is not None else compute_zoom_range(coords_df, padding=0.35)
    if len(view) < 2:
        return view, zoom
    scale = min(plot_width / (zoom['xaxis']['range'][1]-zoom['xaxis']['range'][0]),
                plot_height / (zoom['yaxis']['range'][1]-zoom['yaxis']['range'][0]))
    points = [(float(row.scent_map_x)*scale, float(row.scent_map_y)*scale)
              for row in view.itertuples()]
    sizes = [(marker_size if marker_size is not None else recommendation_marker_size(ranks[i]))+4 for i in view['_id']]
    parent = list(range(len(points)))
    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for i in range(len(points)):
        for j in range(i):
            if math.dist(points[i],points[j]) < (sizes[i]+sizes[j])/2+3:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(len(points)):
        groups.setdefault(find(i), []).append(i)
    rendered = list(points)
    for group in sorted(groups.values(), key=lambda g: min(ranks[view.iloc[i]['_id']] for i in g)):
        if len(group) == 1:
            continue
        group.sort(key=lambda i: ranks[view.iloc[i]['_id']])
        cx = sum(points[i][0] for i in group)/len(group)
        cy = sum(points[i][1] for i in group)/len(group)
        gap = max(sizes[i] for i in group)+3
        radius = max(gap/(2*math.sin(math.pi/len(group))),
                     max(math.dist(points[i], (cx,cy)) for i in group))
        # Rotate first, then grow only if this cluster would hit another point.
        chosen = None
        for attempt in range(1200):
            r = radius + (attempt//12)*3
            phase = (attempt%12)*math.pi/6
            candidates = [(cx+r*math.cos(phase+2*math.pi*k/len(group)),
                           cy+r*math.sin(phase+2*math.pi*k/len(group))) for k in range(len(group))]
            if all(math.dist(pos,rendered[j]) >= (sizes[i]+sizes[j])/2+3
                   for i,pos in zip(group,candidates) for j in range(len(points)) if j not in group):
                chosen = candidates
                break
        if chosen is None:
            raise ValueError('Could not separate recommendation highlights within the search radius.')
        for i,pos in zip(group,chosen):
            rendered[i] = pos
    for i,(original,pos) in enumerate(zip(points,rendered)):
        if original != pos:
            view.iloc[i,view.columns.get_loc('scent_map_x')] = pos[0]/scale
            view.iloc[i,view.columns.get_loc('scent_map_y')] = pos[1]/scale
    return view, zoom
