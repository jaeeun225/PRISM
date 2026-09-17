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

from src.scent_map import COLOR_HUE_ANCHOR, compute_scent_map
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


@st.cache_data(ttl=86400, max_entries=2, show_spinner="향수 데이터를 불러오고 지도를 계산하고 있습니다…")
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
    matched = df["Name"].fillna("").str.contains(query.strip(), case=False, regex=False) if query.strip() else pd.Series(False, index=df.index)
    fig = go.Figure()
    point_colors = df["plot_color"].map(marker_rgb).tolist()
    point_borders = [darker_border(color) for color in point_colors]
    point_text_colors = [contrast_text_color(color) for color in point_colors]
    fig.add_trace(go.Scattergl(
        x=df["scent_map_x"], y=df["scent_map_y"], mode="markers",
        marker=dict(color=point_colors, size=5, opacity=1),
        hovertext=df["tooltip"], hovertemplate="%{hovertext}<extra></extra>",
        hoverlabel=dict(bgcolor=point_colors, bordercolor=point_borders,
                        font=dict(size=16, color=point_text_colors)),
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
            hoverlabel=dict(bgcolor=found_colors, bordercolor=found_borders,
                            font=dict(size=16, color=found_text_colors)),
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
        hoverlabel=dict(font=dict(size=16)),
        dragmode="zoom",
        uirevision="prism-scent-map",
        xaxis=dict(visible=False, range=[-1.45, 1.45], constrain="domain"),
        yaxis=dict(
            visible=False, range=[-1.35, 1.35],
            scaleanchor="x", scaleratio=1, constrain="domain",
        ),
    )
    return fig


def main() -> None:
    st.set_page_config(layout="wide", page_title="PRISM Scent Map", page_icon="◉")
    st.title("PRISM Scent Map")
    st.write("각 점은 향수 한 개를 나타내며, 위치는 주요 accord 조합에 따라 결정됩니다. "
             "점에 마우스를 올려 이름과 주요 향을 확인하세요.")
    try:
        df, section_angles = load_scent_map(**data_settings())
    except DataLoadError as exc:
        st.error(str(exc))
        st.stop()
    display_columns = ["Name", "Brand", "Gender", "Main Accords", "Notes", "scent_map_x", "scent_map_y", "plot_color"]
    view = prepare_view(df[display_columns], section_angles)
    left, right = st.columns([1, 2])
    with left:
        query = st.text_input("향수 이름 검색", placeholder="예: Dior, Sauvage, No. 5",
                              help="이름 일부로 검색합니다. 일치하는 점의 크기와 테두리를 강조합니다.")
    with right:
        selected = st.multiselect("향 계열 섹션", list(section_angles), default=list(section_angles),
                                   help="지도에서 점이 위치한 구역을 기준으로 필터링합니다. 선택하지 않은 구역의 점은 숨깁니다.")
    visible = view.loc[view["map_section"].isin(selected)]
    count = int(visible["Name"].fillna("").str.contains(query.strip(), case=False, regex=False).sum()) if query.strip() else None
    status = f"표시 중 **{len(visible):,} / {len(view):,}개**"
    if count is not None:
        status += f" · 검색 결과 **{count:,}개**"
    st.markdown(status)
    st.caption("마우스 휠: 확대·축소  ·  드래그: 영역 확대  ·  더블클릭: 전체 보기  ·  검색어 입력 후 Enter")
    if not selected:
        st.info("표시할 향 계열 섹션을 하나 이상 선택해 주세요.")
    elif count == 0:
        st.info("선택한 섹션에서 일치하는 향수를 찾지 못했습니다. 검색어나 섹션을 변경해 보세요.")
    fig = build_figure(visible, section_angles, query)
    st.plotly_chart(
        fig, use_container_width=True, theme=None,
        config={"scrollZoom": True, "displaylogo": False, "responsive": True,
                "staticPlot": False, "displayModeBar": True},
    )


if __name__ == "__main__":
    main()
