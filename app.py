"""Interactive PRISM Scent Map. Run with: streamlit run app.py."""

from html import escape
from pathlib import Path
import math
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


def build_figure(df: pd.DataFrame, section_angles: dict) -> go.Figure:
    """Render every computed perfume in one WebGL trace."""
    fig = go.Figure(
        go.Scattergl(
            x=df["scent_map_x"],
            y=df["scent_map_y"],
            mode="markers",
            marker=dict(color=df["plot_color"], size=4, opacity=1),
            hovertext=df["hover_text"],
            hoverinfo="text",
            showlegend=False,
        )
    )

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
        title="PRISM Scent Map",
        autosize=True,
        height=800,
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=BACKGROUND,
        margin=dict(l=30, r=30, t=70, b=30),
        showlegend=False,
        hovermode="closest",
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
    st.set_page_config(layout="wide", page_title="PRISM Scent Map")
    st.title("PRISM Scent Map")
    try:
        df, section_angles = load_scent_map(**data_settings())
    except DataLoadError as exc:
        st.error(str(exc))
        st.stop()
    fig = build_figure(df, section_angles)
    st.plotly_chart(
        fig,
        use_container_width=True,
        theme=None,
        config={"scrollZoom": True, "displaylogo": False, "responsive": True},
    )


if __name__ == "__main__":
    main()
