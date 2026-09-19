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
