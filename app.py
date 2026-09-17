"""Interactive PRISM Scent Map. Run with: streamlit run app.py."""

from html import escape
from pathlib import Path
import math
import colorsys
import ast
import os
import zlib
from io import BytesIO

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.scent_map import ACCORD_TO_SECTION, COLOR_HUE_ANCHOR, compute_scent_map
from src.storage_data import DataLoadError, StorageClient


DATA_PATH = Path(__file__).resolve().parent / "data" / "processed" / "fragella_processed.csv"
BACKGROUND = "#fafaf8"


def hsl_to_css(hue: float, saturation: float, lightness: float) -> str:
    """Convert HSL in degrees/percent/percent to a Plotly CSS color."""
    return f"hsl({hue % 360:.2f}, {saturation:.1f}%, {lightness:.1f}%)"


def data_settings() -> dict:
    """Use remote storage by default; local development is an explicit opt-in."""
    source = os.environ.get("SCENT_DATA_SOURCE", "supabase").strip().lower()
    if source == "local":
        path = Path(os.environ.get("SCENT_CSV_PATH", str(DATA_PATH)))
        if not path.is_absolute():
            path = DATA_PATH.parents[2] / path
        try:
            revision = path.stat().st_mtime_ns
        except OSError:
            raise DataLoadError("로컬 CSV를 찾을 수 없습니다. SCENT_CSV_PATH를 확인하세요.") from None
        return {"source": source, "csv_path": str(path), "version": str(revision)}
    if source != "supabase":
        raise DataLoadError("SCENT_DATA_SOURCE는 supabase 또는 local이어야 합니다.")
    try:
        settings = {
            "source": source,
            "url": str(st.secrets.get("SUPABASE_URL", "")).strip(),
            "service_key": str(st.secrets.get("SUPABASE_SERVICE_KEY", "")).strip(),
            "bucket": str(st.secrets.get("SUPABASE_BUCKET", "prism-data")).strip(),
            "object_path": str(st.secrets.get("SUPABASE_OBJECT_PATH", "fragella_processed.csv.gz")).strip(),
            "version": str(st.secrets.get("SCENT_DATA_VERSION", "1")),
        }
    except Exception:
        # Do not display a TOML parser error, which could quote a secret line.
        raise DataLoadError("Secrets를 읽을 수 없습니다. .streamlit/secrets.toml 또는 Cloud Secrets 설정을 확인하세요.") from None
    return settings


@st.cache_data(ttl=86400, max_entries=2, show_spinner=False)
def load_scent_map(
    source: str, csv_path: str = "", url: str = "", service_key: str = "",
    bucket: str = "prism-data", object_path: str = "fragella_processed.csv.gz",
    version: str = "1",
) -> tuple[pd.DataFrame, dict]:
    """Share one download/calculation per settings across sessions for 24 hours.

    All arguments participate in the cache key, including credentials and version.
    No CSV bytes are persisted to disk by the app.
    """
    if source == "supabase":
        csv_input = BytesIO(StorageClient(url, service_key, bucket, object_path).download())
    elif source == "local":
        csv_input = csv_path
    else:
        raise DataLoadError("SCENT_DATA_SOURCE는 supabase 또는 local이어야 합니다.")
    try:
        raw_df = pd.read_csv(csv_input, compression="gzip" if source == "supabase" else "infer")
    except (OSError, ValueError, EOFError, zlib.error, pd.errors.ParserError):
        raise DataLoadError("CSV를 읽을 수 없습니다. 파일 경로, gzip 압축 상태, 인코딩 및 CSV 형식을 확인하세요.") from None
    required = {"Name", "Brand", "Main Accords", "Main Accords Percentage"}
    if not required.issubset(raw_df.columns):
        raise DataLoadError("CSV에 Name, Brand, Main Accords, Main Accords Percentage 컬럼이 필요합니다.")
    try:
        df, section_angles = compute_scent_map(raw_df)
    except ZeroDivisionError:
        raise DataLoadError("지도에 배치할 수 있는 accord가 CSV에 없습니다.") from None
    df["plot_color"] = [
        hsl_to_css(h, s, l)
        for h, s, l in zip(
            df["scent_map_hue"],
            df["scent_map_saturation"],
            df["scent_map_lightness"],
        )
    ]
    # Escape CSV text so names and accords remain literal in Plotly hover labels.
    labels = df[["Name", "Brand", "Main Accords"]].fillna("").astype(str)
    df["hover_text"] = [
        f"{escape(name)}<br>{escape(brand)}<br>Accords: {escape(accords)}"
        for name, brand, accords in labels.itertuples(index=False, name=None)
    ]
    return df, section_angles


@st.cache_data(show_spinner=False)
def prepare_view(df: pd.DataFrame, section_angles: dict) -> pd.DataFrame:
    """Prepare display labels and geographical wheel sectors only."""
    view = df.copy()

    def all_accords(value):
        try:
            accords = ast.literal_eval(value) if isinstance(value, str) else value
        except (ValueError, SyntaxError):
            accords = []
        if not isinstance(accords, list):
            accords = []
        return ", ".join(str(a) for a in accords) or "정보 없음"

    def format_notes(value):
        try:
            notes = ast.literal_eval(value) if isinstance(value, str) else value
        except (ValueError, SyntaxError):
            notes = {}
        if not isinstance(notes, dict):
            return []
        lines = []
        for layer in ("Top", "Middle", "Base"):
            items = notes.get(layer)
            if not isinstance(items, list):
                continue
            names = [str(item.get("name", "")).strip() for item in items
                     if isinstance(item, dict) and str(item.get("name", "")).strip()]
            if names:
                lines.append(f"<b>{layer}:</b> {escape(', '.join(names))}")
        return lines

    def wrap_csv(values, per_line=5):
        chunks = [values[i:i + per_line] for i in range(0, len(values), per_line)]
        return "<br>".join(", ".join(chunk) for chunk in chunks)

    view["all_accords"] = view["Main Accords"].map(all_accords)
    def parse_accords(value):
        try:
            parsed = ast.literal_eval(value) if isinstance(value, str) else value
        except (ValueError, SyntaxError):
            return []
        return parsed if isinstance(parsed, list) else []

    view["accord_values"] = view["Main Accords"].map(parse_accords)
    view["accord_values"] = view["accord_values"].map(lambda value: value if isinstance(value, list) else [])
    view["note_lines"] = view["Notes"].map(format_notes)
    tooltips = []
    for name, brand, gender, accords, note_lines in view[
        ["Name", "Brand", "Gender", "all_accords", "note_lines"]
    ].fillna("").itertuples(index=False, name=None):
        subtitle = str(brand).strip()
        lines = [f"<b>{escape(str(name))}</b>"]
        if subtitle:
            lines.append(f"<span style='font-size:12px'>{escape(subtitle)}</span>")
        if accords and accords != "정보 없음":
            accord_values = [escape(value.strip()) for value in str(accords).split(",")]
            lines.extend(["", f"<b>Accords:</b> {wrap_csv(accord_values)}"])
        if note_lines and accords and accords != "정보 없음":
            lines.append("")
        lines.extend(note_lines)
        tooltips.append("<br>".join(lines))
    view["tooltip"] = tooltips
    # Use the existing coordinates, avoiding rounded-angle boundary ambiguity.
    angles = pd.Series(
        [math.degrees(math.atan2(x, y)) % 360
         for x, y in zip(view["scent_map_x"], view["scent_map_y"])], index=view.index,
    )
    view["map_section"] = ""
    for section, limits in section_angles.items():
        view.loc[(angles >= limits["start"]) & (angles < limits["end"]), "map_section"] = section
    return view


def marker_rgb(color: str) -> str:
    """Convert existing CSS HSL to equivalent RGB for WebGL rendering only."""
    if not color.startswith("hsl("):
        return color
    h, s, l = (float(part.strip().rstrip("%")) for part in color[4:-1].split(","))
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, l / 100, s / 100)
    return f"rgb({round(r * 255)}, {round(g * 255)}, {round(b * 255)})"


def darker_border(color: str) -> str:
    """Return a slightly darker RGB border without changing the marker color."""
    if not color.startswith("rgb("):
        return color
    values = [int(part.strip()) for part in color[4:-1].split(",")]
    return "rgb({0}, {1}, {2})".format(*(max(0, round(value * 0.72)) for value in values))


def contrast_text_color(color: str) -> str:
    """Choose black/white text from RGB relative luminance (threshold 128)."""
    if not color.startswith("rgb("):
        return "#000000"
    r, g, b = (int(part.strip()) for part in color[4:-1].split(","))
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "#000000" if luminance >= 128 else "#FFFFFF"


def build_figure(df: pd.DataFrame, section_angles: dict, query: str = "") -> go.Figure:
    """Keep accord colors; enlarge and outline search matches."""
    if query.strip():
        needle = query.strip()
        matched = (df["Name"].fillna("").str.contains(needle, case=False, regex=False) |
                   df["Brand"].fillna("").str.contains(needle, case=False, regex=False))
    else:
        matched = pd.Series(False, index=df.index)
    fig = go.Figure()
    point_colors = df["plot_color"].map(marker_rgb).tolist()
    point_borders = [darker_border(color) for color in point_colors]
    point_text_colors = [contrast_text_color(color) for color in point_colors]
    fig.add_trace(go.Scattergl(
        x=df["scent_map_x"], y=df["scent_map_y"], mode="markers",
        marker=dict(color=point_colors, size=5, opacity=1),
        hovertext=df["tooltip"], hovertemplate="%{hovertext}<extra></extra>",
        hoverlabel=dict(align="left", bgcolor=point_colors, bordercolor=point_borders,
                        font=dict(size=14, color=point_text_colors, family="Georgia, Times New Roman, serif")),
        showlegend=False,
    ))
    if matched.any():
        found = df.loc[matched]
        found_colors = found["plot_color"].map(marker_rgb).tolist()
        found_borders = [darker_border(color) for color in found_colors]
        found_text_colors = [contrast_text_color(color) for color in found_colors]
        fig.add_trace(go.Scattergl(
            x=found["scent_map_x"], y=found["scent_map_y"], mode="markers",
            marker=dict(color=found_colors, size=12, opacity=1,
                        line=dict(color="#252525", width=2)),
            hovertext=found["tooltip"], hovertemplate="%{hovertext}<extra></extra>",
            hoverlabel=dict(align="left", bgcolor=found_colors, bordercolor=found_borders,
                            font=dict(size=14, color=found_text_colors, family="Georgia, Times New Roman, serif")),
            showlegend=False,
        ))

    for section, angles in section_angles.items():
        # The original calculation uses x=sin(angle), y=cos(angle).
        start = math.radians(angles["start"])
        fig.add_shape(
            type="line", x0=0, y0=0,
            x1=math.sin(start), y1=math.cos(start),
            line=dict(color="#d8d8d5", width=1, dash="solid"),
            layer="below",
        )
        center = math.radians(angles["center"])
        fig.add_annotation(
            x=1.15 * math.sin(center),
            y=1.15 * math.cos(center),
            text=f"<b>{escape(section)}</b>",
            showarrow=False,
            xanchor="center", yanchor="middle",
            font=dict(size=14, color=hsl_to_css(COLOR_HUE_ANCHOR[section], 75, 40)),
        )

    fig.update_layout(
        autosize=True,
        height=720,
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        margin=dict(l=55, r=55, t=35, b=35),
        showlegend=False,
        hovermode="closest",
        hoverdistance=20,
        hoverlabel=dict(align="left", font=dict(size=14, family="Georgia, Times New Roman, serif")),
        dragmode="zoom",
        uirevision="prism-scent-map",
        xaxis=dict(visible=False, range=[-1.45, 1.45], constrain="domain"),
        yaxis=dict(
            visible=False, range=[-1.35, 1.35],
            scaleanchor="x", scaleratio=1, constrain="domain",
        ),
    )
    return fig


def fast_figure(view: pd.DataFrame, template: dict, query: str) -> go.Figure:
    """Use validated static layout with trusted, precomputed point arrays.

    Only internally generated, precomputed point properties use this path.
    Plotly's _validate switch avoids revalidating every CSS color on reruns.
    Return a Figure: Streamlit revalidates plain dictionaries independently.
    """
    def trace(rows, highlight=False):
        marker = dict(color=rows["marker_rgb"].tolist(), size=12 if highlight else 5, opacity=1)
        if highlight:
            marker["line"] = dict(color="#252525", width=2)
        return dict(type="scattergl", mode="markers", x=rows["scent_map_x"].tolist(),
                    y=rows["scent_map_y"].tolist(), marker=marker,
                    hovertext=rows["tooltip"].tolist(), hovertemplate="%{hovertext}<extra></extra>",
                    hoverlabel=dict(align="left", bgcolor=rows["marker_rgb"].tolist(),
                                    bordercolor=rows["marker_border"].tolist(),
                                    font=dict(size=14, color=rows["marker_text"].tolist(),
                                              family="Georgia, Times New Roman, serif")), showlegend=False)
    traces = [trace(view)]
    if query.strip():
        mask = (view.Name.fillna("").str.contains(query.strip(), case=False, regex=False) |
                view.Brand.fillna("").str.contains(query.strip(), case=False, regex=False))
        if mask.any():
            traces.append(trace(view.loc[mask], True))
    return go.Figure(data=traces, layout=template["layout"], _validate=False)


def accord_filter(options: list[str]) -> list[str]:
    """Search/select here; render removable chips outside the search columns."""
    if "accord_selector" not in st.session_state:
        st.session_state.accord_selector = st.session_state.get("selected_accords", [])
    selected = st.multiselect(
        "Accord 검색 및 추가", options,
        key="accord_selector",
        help="accord를 검색해 선택하세요. 선택된 accord 중 하나라도 포함한 향수가 표시됩니다.",
    )
    st.session_state.selected_accords = list(selected)
    # Native-chip CSS lives in the first, unconditional HTML element in main().
    return selected


def remove_accord(accord: str) -> None:
    """Callbacks run before widget creation, so widget state can safely change."""
    updated = [value for value in st.session_state.get("accord_selector", []) if value != accord]
    st.session_state.accord_selector = updated
    st.session_state.selected_accords = list(updated)


def render_accord_chips(selected: list[str]) -> None:
    """Render each accord as one content-sized removal button."""
    if not selected:
        return
    # Streamlit 1.37 does not expose the widget key as a button DOM attribute.
    # A hidden, accord-specific marker scopes CSS to the actual button.
    rules = []
    for accord in selected:
        section = ACCORD_TO_SECTION[accord]
        color = marker_rgb(hsl_to_css(COLOR_HUE_ANCHOR[section], 75, 40))
        text_color = contrast_text_color(color)
        chip_class = "prism-chip-" + accord.replace(" ", "-")
        marker = f":is([data-testid='element-container'], [data-testid='stElementContainer']):has(.{chip_class})"
        button = f"{marker} + div button"
        rules.extend([
            f"{marker} {{display:none!important;}}",
            f"{button} {{display:inline-flex!important;width:auto!important;min-width:0!important;min-height:2rem!important;padding:0.2rem 0.7rem!important;border-radius:999px!important;border:1px solid {color}!important;background-color:{color}!important;color:{text_color}!important;white-space:nowrap;}}",
            f"{button}:hover {{filter:brightness(0.92);}}",
        ])
        # Buttons are direct siblings in the shared flex container; no
        # full-width per-accord Streamlit container can force a separate row.
        st.markdown(f"<span class='{chip_class}' hidden></span>", unsafe_allow_html=True)
        st.button(f"{accord} ×", key=f"remove_accord_{accord}",
                  use_container_width=False,
                  on_click=remove_accord, args=(accord,))
    st.markdown("<style>" + "".join(rules) + "</style>", unsafe_allow_html=True)


def navigate(page: str) -> None:
    st.session_state.current_page = page


def render_navigation() -> None:
    marker = ":is([data-testid='element-container'], [data-testid='stElementContainer']):has(.prism-nav-marker)"
    nav_button = f"{marker} + div button"
    logo_button = f":is([data-testid='element-container'], [data-testid='stElementContainer']):has(.prism-logo-marker) + div button"
    menu_list = "[data-testid='stVerticalBlock']:has(.prism-menu-list):not(:has([data-testid='stVerticalBlock'] .prism-menu-list))"
    menu_button = f"{menu_list} button"
    st.markdown(
        "<style>"
        "[data-baseweb='tag'], [data-baseweb*='tag'], [data-testid*='MultiSelectTag'], [class*='st-key-accord_selector'] [data-baseweb='tag'], [data-baseweb='tag'] span[title], [role='button'][aria-label*='close by backspace'], [aria-label*=', close by backspace'] {display:none!important;visibility:hidden!important;opacity:0!important;animation:none!important;transition:none!important;}"
        "html, body, [data-testid='stAppViewContainer'], [data-testid='stAppViewContainer'] * {font-family:Georgia,'Times New Roman',serif!important;}"
        "[data-baseweb='menu'], [data-baseweb='menu'] *, [data-baseweb='popover'], [data-baseweb='popover'] *, [data-baseweb='tooltip'], [data-baseweb='tooltip'] *, [role='listbox'], [role='listbox'] *, [role='option'], [role='tooltip'], [role='tooltip'] * {font-family:Georgia,'Times New Roman',serif!important;}"
        f"{marker} {{display:none!important;}}"
        f"{nav_button} {{background:transparent!important;border:0!important;box-shadow:none!important;border-radius:0!important;color:#333!important;padding:0.5rem 0.15rem!important;}}"
        f"{nav_button} p {{font-family:Georgia,'Times New Roman',serif!important;font-size:clamp(16px,1.8vw,22px)!important;font-weight:600;}}"
        f"{nav_button}[kind='primary'], {nav_button}:hover {{color:#000!important;}}"
        f"{nav_button}[kind='primary'] p {{font-weight:800!important;}}"
        f"{nav_button}:focus-visible {{outline:1px solid currentColor!important;outline-offset:3px;}}"
        f"{logo_button} {{color:#000!important;margin-bottom:1.4rem;}}"
        f"{logo_button} p {{font-size:36px!important;font-weight:700!important;letter-spacing:0.02em;}}"
        f"{menu_list} {{position:relative;display:flex!important;flex-direction:row!important;flex-wrap:wrap!important;justify-content:center;align-items:center;gap:0.5rem 2.5rem!important;margin-bottom:1rem;width:100%!important;box-sizing:border-box;}}"
        f"{menu_list}::after {{content:'';position:absolute;left:50%;margin-left:-50vw;bottom:0;width:100vw;height:1px;background:#D0D0D0;pointer-events:none;}}"
        f"{menu_list} > div, {menu_list} [data-testid='stButton'] {{width:max-content!important;max-width:100%;flex:0 0 auto!important;}}"
        f"{menu_list} > div:has(.prism-menu-list) {{display:none!important;}}"
        f"{menu_button} {{position:relative;white-space:nowrap;padding-bottom:0.75rem!important;}}"
        f"{menu_button}::after {{content:'';position:absolute;left:0.15rem;right:0.15rem;bottom:0;height:2px;background:transparent;z-index:1;}}"
        f"{menu_button}[kind='primary']::after {{background:linear-gradient(90deg,#6E7BC9,#8F99D8);}}"
        "</style>", unsafe_allow_html=True,
    )
    _, header, _ = st.columns([1, 8, 1])
    with header:
        _, logo, _ = st.columns([1, 1, 1])
        with logo:
            st.markdown("<span class='prism-nav-marker prism-logo-marker' hidden></span>", unsafe_allow_html=True)
            st.button("PRISM", key="nav_home", use_container_width=True,
                      on_click=navigate, args=("home",))
        menus = [
            ("recommendation", "Perfume Recommendation"),
            ("scent_map", "Interactive Scent Map"),
            ("profile", "My Profile"),
        ]
        with st.container():
            st.markdown("<span class='prism-menu-list' hidden></span>", unsafe_allow_html=True)
            for page, label in menus:
                st.markdown("<span class='prism-nav-marker' hidden></span>", unsafe_allow_html=True)
                st.button(label, key=f"nav_{page}", use_container_width=False,
                          type="primary" if st.session_state.current_page == page else "secondary",
                          on_click=navigate, args=(page,))


def main() -> None:
    st.set_page_config(layout="wide", page_title="PRISM", page_icon="◉")
    # Inject the multiselect chrome rules before any widgets are rendered so
    # reruns do not briefly reveal the native selected capsules.
    st.html(
        "<style id='prism-native-chip-visibility'>"
        "[data-baseweb='tag'], [data-testid='stMultiSelectTag'] "
        "{display:none!important;visibility:hidden!important;opacity:0!important;animation:none!important;transition:none!important;background:#6E7BC9!important;color:#FFFFFF!important;border:1px solid #5967B5!important;border-radius:999px!important;padding:0.2rem 0.7rem!important;font-family:Georgia,'Times New Roman',serif!important;}"
        "[data-baseweb='tag'] *, [data-testid='stMultiSelectTag'] * {font-family:Georgia,'Times New Roman',serif!important;color:#FFFFFF!important;}"
        "[data-baseweb='select'] input::placeholder {opacity:1!important;color:#8a8a8a!important;font-family:Georgia,'Times New Roman',serif!important;}"
        "[data-baseweb='select'] input[placeholder] {min-width:8rem!important;}"
        "[data-baseweb='select'] > div:first-child {position:relative;}"
        "[data-baseweb='select'] > div:first-child::before {content:'Choose an option';position:absolute;left:10px;top:50%;transform:translateY(-50%);color:#8a8a8a;font-family:Georgia,'Times New Roman',serif;font-size:inherit;line-height:inherit;white-space:nowrap;pointer-events:none;z-index:2;}"
        "[data-baseweb='select'] > div:first-child:focus-within::before {content:none;}"
        "[data-baseweb='select'] input[placeholder]::placeholder {color:transparent!important;}"
        "</style>",
    )
    if "current_page" not in st.session_state:
        st.session_state.current_page = "home"
    render_navigation()
    if st.session_state.current_page == "scent_map":
        render_scent_map()


@st.cache_resource(show_spinner=False)
def get_display_cache(settings_key: tuple) -> dict:
    """Build the prepared view and full figure once per process, shared by sessions."""
    settings = dict(settings_key)
    df, section_angles = load_scent_map(**settings)
    columns = ["Name", "Brand", "Gender", "Main Accords", "Notes", "scent_map_x", "scent_map_y", "plot_color"]
    view = prepare_view(df[columns], section_angles)
    view["marker_rgb"] = view.plot_color.map(marker_rgb)
    view["marker_border"] = view.marker_rgb.map(darker_border)
    view["marker_text"] = view.marker_rgb.map(contrast_text_color)
    template = build_figure(view.iloc[:0], section_angles).to_plotly_json()
    full_figure = fast_figure(view, template, "")
    return {"view": view, "template": template, "full_figure": full_figure, "section_angles": section_angles}


@st.fragment
def render_scent_map() -> None:
    try:
        settings = data_settings()
        settings_key = tuple(sorted(settings.items()))
        with st.spinner("향수 데이터를 불러오고 지도를 계산하고 있습니다..."):
            cached = get_display_cache(settings_key)
        view = cached["view"]
    except DataLoadError as exc:
        st.error(str(exc))
        st.stop()
    content_left, content_center, content_right = st.columns([1, 8, 1])
    with content_center:
        # 지도 제목과 설명은 추후 필요할 때 복원할 수 있도록 보존합니다.
        # st.title("PRISM Scent Map")
        # st.write("각 점은 향수 한 개를 나타내며, 위치는 주요 accord 조합에 따라 결정됩니다. "
        #          "점에 마우스를 올려 이름과 주요 향을 확인하세요.")
        left, right = st.columns([1, 2])
        with left:
            query = st.text_input("향수 이름 검색", placeholder="예: Dior, Sauvage, No. 5",
                                  help="이름 일부로 검색합니다. 일치하는 점의 크기와 테두리를 강조합니다.")
        with right:
            accord_options = sorted(ACCORD_TO_SECTION)
            if "selected_accords" not in st.session_state:
                st.session_state.selected_accords = []
            selected_accords = accord_filter(accord_options)
        # A dedicated wrapping flex container keeps pills on one line where
        # space permits, without changing the surrounding page layout.
        with st.container():
            st.markdown("<span class='prism-chip-list-marker'></span>", unsafe_allow_html=True)
            render_accord_chips(selected_accords)
            chip_list = "[data-testid='stVerticalBlock']:has(.prism-chip-list-marker):not(:has([data-testid='stVerticalBlock'] .prism-chip-list-marker))"
            st.markdown(
                "<style>"
                f"{chip_list} {{display:flex!important;flex-direction:row!important;flex-wrap:wrap!important;align-items:center;gap:0.5rem!important;}}"
                f"{chip_list} > div {{width:max-content!important;max-width:100%;flex:0 0 auto!important;min-width:0!important;}}"
                f"{chip_list} [data-testid='stButton'] {{width:max-content!important;max-width:100%;}}"
                f"{chip_list} > div:has(.prism-chip-list-marker), "
                f"{chip_list} > div:has(style) {{display:none!important;}}"
                "</style>", unsafe_allow_html=True,
            )
        if selected_accords:
            selected_set = set(selected_accords)
            accord_mask = view["accord_values"].map(lambda values: bool(selected_set.intersection(values)))
            visible = view.loc[accord_mask]
        else:
            visible = view
        if query.strip():
            needle = query.strip()
            search_mask = (visible["Name"].fillna("").str.contains(needle, case=False, regex=False) |
                           visible["Brand"].fillna("").str.contains(needle, case=False, regex=False))
            count = int(search_mask.sum())
        else:
            count = None
        status = f"표시 중 **{len(visible):,} / {len(view):,}개**"
        if count is not None:
            status += f" · 검색 결과 **{count:,}개**"
        st.markdown(status)
        st.caption("마우스 휠: 확대·축소  ·  드래그: 영역 확대  ·  더블클릭: 전체 보기  ·  검색어 입력 후 Enter")
        if count == 0:
            st.info("선택한 accord에서 일치하는 향수를 찾지 못했습니다. 검색어나 accord를 변경해 보세요.")
        if not selected_accords and not query.strip():
            fig = cached["full_figure"]
        else:
            fig = fast_figure(visible, cached["template"], query)
        st.plotly_chart(
            fig, use_container_width=True, theme=None,
            config={"scrollZoom": True, "displaylogo": False, "responsive": True,
                    "staticPlot": False, "displayModeBar": True},
        )


if __name__ == "__main__":
    main()
