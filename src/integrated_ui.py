"""Presentation-only helpers for the unified map. No artifact inputs changed."""
from copy import deepcopy
from html import escape
from functools import lru_cache
import base64, re, textwrap
from io import BytesIO
import plotly.graph_objects as go
import streamlit as st
from .scent_profile import pastel_colors, contrast_ratio, hsl_hex
from .scent_map import safe_eval, recommendation_marker_size


@lru_cache(maxsize=1)
def silhouette():
    from PIL import Image, ImageDraw
    image=Image.new('RGB',(52,68),'white');d=ImageDraw.Draw(image)
    d.rounded_rectangle((14,20,38,62),5,fill='#e8e5e9')
    d.rectangle((21,10,31,22),fill='#bdb8c4')
    d.rectangle((19,33,33,48),fill='#f8f7f9')
    stream=BytesIO();image.save(stream,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(stream.getvalue()).decode()


def image_source(row,api):
    from urllib.parse import quote,urlsplit,urlunsplit
    raw=row.get('Image URL')
    if isinstance(raw,str) and raw.startswith(('https://','http://')):
        try:
            parts=urlsplit(raw.replace('#','%23'))
            url=urlunsplit((parts.scheme,parts.netloc,quote(parts.path,safe='/%'),parts.query,''))
            if api.image_url_or_none(url):return url
        except ValueError:pass
    return silhouette()


def section_colors(section,api):
    if section not in api.COLOR_HUE_ANCHOR:return '#777777','#f3f3f4'
    hue=api.COLOR_HUE_ANCHOR[section]
    return api.marker_rgb(api.hsl_to_css(hue,75,40)),hsl_hex(hue,75,92)


def card_html(identifier,catalog,view,results,api):
    row=catalog.loc[catalog['_id']==identifier].iloc[0]
    location=view.loc[view['_id']==identifier]
    record=location.iloc[0] if not location.empty else None
    hue=float(record['scent_map_hue']) if record is not None else 232.
    palette=pastel_colors(hue,(70,94))
    edge=hsl_hex(hue,70,84)
    color=str(record['marker_rgb']) if record is not None else '#777777'
    match=next((r for r in results if r['id']==identifier),None)
    badges=(f'추천 {match["rank"]}위</span> <span>유사도 {match["final_score"]:.4f}' if match else '선택한 향수')
    picture=escape(image_source(row,api),quote=True)
    html=f'''<div class="prism-detail-card" style="background:{palette['background']};color:{palette['foreground']};border:1px solid {edge};border-radius:16px;box-shadow:0 3px 12px #38384b09;padding:26px 22px 24px;box-sizing:border-box">
    <div style="display:flex;gap:18px;align-items:center">
    <div style="background:white;border:1px solid {color};border-radius:12px;padding:8px;flex:0 0 104px"><img src="{picture}" style="width:104px;height:142px;object-fit:contain"></div>
    <div style="min-width:0;flex:1;padding-right:10px"><div style="font-size:23px;font-weight:bold;line-height:1.2;overflow-wrap:anywhere">{escape(str(row['Name']))}</div>
    <div style="font-size:14px;color:#61606b;margin:5px 0 10px">{escape(str(row['Brand']))}</div>
    <div style="height:2px;background:{color};margin-bottom:12px"></div><div class="prism-detail-badges"><span>{badges}</span></div></div></div>'''
    chips=[]
    if record is not None:
        for accord in record['accord_values']:
            outline,pale=section_colors(api.ACCORD_TO_SECTION.get(accord),api)
            chips.append(f'<span style="background:{pale};border:1px solid {outline};border-radius:16px;padding:3px 8px;display:inline-block;margin:2px;color:#2c2c2a;font-size:13px">{escape(accord)}</span>')
        html+='<div style="margin:14px 0 12px">'+''.join(chips)+'</div>'
        parsed=safe_eval(record['Notes']) if isinstance(record['Notes'],str) else record['Notes']
        html+='<div style="display:grid;grid-template-columns:52px 1fr;gap:8px 12px;font-size:14px;line-height:1.5">'
        for layer in ['Top','Middle','Base']:
            notes=[str(v['name']) for v in parsed.get(layer,[]) if isinstance(v,dict) and v.get('name')] if isinstance(parsed,dict) else []
            if notes:html+=f'<b style="color:#505b9c">{layer}</b><div>{escape(", ".join(notes))}</div>'
        html+='</div>'
    return html+'</div>',dict(hue=hue,background=palette['background'],foreground=palette['foreground'],contrast=contrast_ratio(palette['background'],palette['foreground']))


def detail_panel(identifier,catalog,view,results,api,close):
    with st.container(key='ui_detail'):
        st.button('×',key='ui_close',on_click=close,type='tertiary')
        html,_=card_html(identifier,catalog,view,results,api)
        st.markdown(html,unsafe_allow_html=True)


def markdown_text(value):
    return re.sub(r'([\\*\[\]_`])',r'\\\1',str(value)).replace('\n',' ')


def recommendation_rows(results,catalog,selected,api,select):
    lookup=catalog.set_index('_id')
    with st.container(height=326,border=False,key='ui_rows'):
        for result in results:
            row=lookup.loc[result['id']]
            label=f"![bottle]({image_source(row,api)}) **{result['rank']}. {markdown_text(result['name'])}**  \n{markdown_text(result['brand'])} **{result['final_score']:.4f}**"
            st.button(label,key='ui_rec_'+result['id'],width='stretch',
                      type='primary' if selected==result['id'] else 'secondary',
                      on_click=select,args=(result['id'],))


def shallow_figure(base):
    # Only the list owners and small layout are copied. Base trace payloads
    # are immutable here; callers must replace whole entries, never mutate.
    figure=object.__new__(go.Figure);figure.__dict__=base.__dict__.copy()
    figure._data=list(base._data);figure._data_objs=list(base._data_objs)
    figure._layout=deepcopy(base._layout)
    figure._layout_obj=go.Layout(figure._layout);figure._layout_obj._parent=figure
    return figure


def subset_figure(base,visible,reference,filters):
    figure=shallow_figure(base)
    payload=dict(base._data[0],x=visible.scent_map_x.tolist(),y=visible.scent_map_y.tolist())
    payload['marker']=dict(payload['marker'],color=visible.marker_rgb.tolist())
    payload['customdata']=None if reference else list(zip(visible['Name'],visible['Brand'],visible['_id']))
    trace=go.Scattergl(payload,_validate=False)
    figure._data[0]=trace.to_plotly_json()
    figure._data_objs[0]=trace;trace._parent=figure;trace._trace_ind=0
    figure._data_defaults=[{},*base._data_defaults[1:]]
    figure.update_layout(uirevision=str(reference)+str(filters))
    return figure


def overlay_figure(base,identifier,reference,view,results):
    if not identifier:return base
    figure=shallow_figure(base)
    location=view.loc[view['_id']==identifier]
    if location.empty:return figure
    row=location.iloc[0];x,y=float(row.scent_map_x),float(row.scent_map_y)
    for trace in reversed(base.data):
        if trace.customdata is not None and len(trace.customdata)==1 and trace.customdata[0][-1]==identifier:
            x,y=float(trace.x[0]),float(trace.y[0]);break
    match=next((r for r in results if r['id']==identifier),None)
    if match:
        figure.add_trace(go.Scattergl(x=[x],y=[y],mode='markers',marker=dict(symbol='circle-open',size=recommendation_marker_size(match['rank'])+6,color='#6E7BC9',line=dict(width=2)),hoverinfo='skip',showlegend=False))
    elif identifier!=reference:
        for diameter,color,width in [(13,'#2c2c2a',1.5),(10,'#ffffff',1)]:
            figure.add_trace(go.Scattergl(x=[x],y=[y],mode='markers',marker=dict(symbol='circle-open',size=diameter,color=color,line=dict(width=width)),hoverinfo='skip',showlegend=False))
        name='<br>'.join(escape(v) for v in textwrap.wrap(str(row['Name']),32)[:2])
        figure.add_annotation(x=x,y=y,text=name,showarrow=False,xshift=12,yshift=10,xanchor='left',bgcolor='rgba(255,255,255,.88)',borderpad=3,font=dict(size=12,family='Georgia',color='#2c2c2a'))
    return figure


def spread_section_labels(figure):
    """Keep true wheel anchors; separate their text in screen pixels."""
    from .scent_map import SECTION_ORDER
    from .profile_card import serif_font
    font=serif_font(14,bold=True)
    placed=[]
    labels=[(a,a.text[3:-4]) for a in figure.layout.annotations
            if a.text and a.text.startswith('<b>') and a.text.endswith('</b>') and a.text[3:-4] in SECTION_ORDER]
    # Conservative scale for the 520px full-wheel plot. Zoom-in increases
    # anchor spacing, while the local offsets stay fixed in pixels.
    for a,name in sorted(labels,key=lambda item:abs(float(item[0].x))):
        x,y=float(a.x)*190,float(a.y)*190
        w=float(font.getlength(name))+10
        h=22
        dx=dy=0
        sign=-1 if x<0 else 1
        def collides(dx,dy):
            return any(abs(x+dx-u)<(w+ow)/2 and abs(y+dy-v)<(h+oh)/2 for u,v,ow,oh in placed)
        for lane in range(3):
            for step in range(8):
                dx=step*8*sign
                dy=lane*17*(-1 if y>=0 else 1)
                if not collides(dx,dy):break
            if not collides(dx,dy):break
        a.update(xshift=dx,yshift=dy,font_family='Georgia, Times New Roman, serif')
        placed.append((x+dx,y+dy,w,h))
    return figure


def scoped_styles():
    st.html('''<style>
    .st-key-prism_unified .st-key-ui_rows,.st-key-prism_unified .st-key-ui_rows [data-testid="stVerticalBlock"]{gap:6px}
    .st-key-prism_unified .st-key-ui_rows button{position:relative;min-height:58px;justify-content:flex-start;text-align:left;border:1px solid #e8e7ed;border-radius:9px;background:white;padding:6px 64px 6px 10px}
    .st-key-prism_unified .st-key-ui_rows button[kind="primary"]{background:#eeedf9;border-color:#a9add8}
    .st-key-prism_unified .st-key-ui_rows button>div,.st-key-prism_unified .st-key-ui_rows button [data-has-shortcut]{width:100%;min-width:0;justify-content:flex-start}
    .st-key-prism_unified .st-key-ui_rows button [data-testid="stMarkdownContainer"]{width:100%;min-width:0}
    .st-key-prism_unified .st-key-ui_rows button p{font-size:12px!important;color:#777484;text-align:left!important;width:100%;position:relative;padding-left:52px;min-height:43px;margin:0!important}
    .st-key-prism_unified .st-key-ui_rows button img{height:42px!important;max-height:42px!important;width:40px!important;max-width:40px!important;object-fit:contain;position:absolute;left:0;top:0;background:white}
    .st-key-prism_unified .st-key-ui_rows button br{display:none}
    .st-key-prism_unified .st-key-ui_rows button strong:first-of-type{font-size:14px;color:#302e38;display:block;line-height:1.25;max-height:35px;overflow:hidden;margin-bottom:3px}
    .st-key-prism_unified .st-key-ui_rows button strong:last-of-type{position:absolute;right:-54px;top:50%;transform:translateY(-50%);font-size:14px;color:#514d60}
    .st-key-prism_unified .st-key-ui_detail{position:relative}
    .st-key-prism_unified .st-key-ui_close{position:absolute;right:10px;top:6px;z-index:3;width:28px}
    .st-key-prism_unified .st-key-ui_close button{font-size:18px;color:#6c6975;min-height:25px;padding:0 6px;background:transparent;border:0}
    .st-key-prism_unified .prism-detail-badges span{background:#e9e7f8;color:#4e5896;border-radius:14px;padding:4px 8px;font-size:12px;display:inline-block;margin:2px 2px 0 0}
    .st-key-prism_unified{gap:18px}
    .st-key-prism_unified .st-key-ui_filter_shell{border:1px solid #e2e1e8;border-radius:12px;padding:8px 14px;background:white;gap:8px}
    .st-key-prism_unified .st-key-ui_filter_header,.st-key-prism_unified .st-key-ui_filter_actions{gap:8px;align-items:center}
    .st-key-prism_unified .st-key-ui_filter_summary,.st-key-prism_unified .st-key-ui_filter_hint{margin-left:auto}
    .st-key-prism_unified .st-key-ui_filter_toggle button{border:0;background:transparent;font-weight:bold;min-height:32px;padding:3px 6px}
    .st-key-prism_unified .ui-filter-divider{height:1px;background:#ebeaf0}
    .st-key-prism_unified .st-key-ui_filter_actions button{min-height:34px;padding:4px 12px;font-size:14px}
    .st-key-prism_unified .st-key-ui_filter_grid [data-testid="stHorizontalBlock"]{align-items:stretch}
    .st-key-prism_unified .st-key-ui_filter_grid [data-testid="stColumn"]>div{height:100%}
    .st-key-prism_unified .st-key-ui_filter_grid [data-testid="stColumn"] [data-testid="stLayoutWrapper"]:has(>[class*="st-key-ui_section_"]){flex:1;min-height:0}
    .st-key-prism_unified .st-key-ui_filter_grid [class*="st-key-ui_section_"]{height:100%;border:1px solid #edecf1;border-left:4px solid var(--section-ink);border-radius:10px;background:#fcfcfd;padding:9px 11px;gap:8px}
    .st-key-prism_unified .ui-section-title{color:var(--section-ink);font-size:15px;white-space:nowrap}
    .st-key-prism_unified [class*="st-key-ui_group_"]{margin-left:auto}
    .st-key-prism_unified [class*="st-key-ui_group_"] button{font-size:12px;color:#5e68a8;background:transparent;border:0;min-height:25px;padding:2px;white-space:nowrap}
    .st-key-prism_unified [class*="st-key-ui_chips_"]{gap:5px}
    .st-key-prism_unified [class*="st-key-ui_chip_"] button[data-testid^="stBaseButton"]{min-height:28px;border-radius:16px;padding:2px 8px;background:white;border:1px solid #dddce4;color:#625f6a;font-size:14px}
    .st-key-prism_unified [class*="st-key-ui_chip_"] button[kind="primary"]{background:var(--section-pale);border-color:var(--section-ink);color:#2c2c2a}
    </style>''')
