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
    html = f'''<div class="prism-detail-card" style="background:{palette['background']};color:{palette['foreground']};border-color:{edge}">
    <div class="prism-detail-top">
    <div class="prism-detail-image" style="border-color:{color}"><img src="{picture}" alt=""></div>
    <div class="prism-detail-summary">
    <div class="prism-detail-name">{escape(str(row['Name']))}</div>
    <div class="prism-detail-brand">{escape(str(row['Brand']))}</div>
    <div class="prism-detail-accent" style="background:{color}"></div>
    <div class="prism-detail-badges"><span>{badges}</span></div>'''
    if record is not None:
        chips = []
        for accord in record['accord_values']:
            outline, pale = section_colors(api.ACCORD_TO_SECTION.get(accord), api)
            chips.append(f'<span style="background:{pale};border-color:{outline}">{escape(accord)}</span>')
        html += '<div class="prism-detail-chips">' + ''.join(chips) + '</div>'
    html += '</div></div>'
    if record is not None:
        parsed = safe_eval(record['Notes']) if isinstance(record['Notes'], str) else record['Notes']
        html += '<div class="prism-detail-notes">'
        for layer in ['Top', 'Middle', 'Base']:
            notes = [str(v['name']) for v in parsed.get(layer, []) if isinstance(v, dict) and v.get('name')] if isinstance(parsed, dict) else []
            if notes:
                html += f'<b>{layer}</b><div>{escape(", ".join(notes))}</div>'
        html += '</div>'
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
    with st.container(height=224,border=False,key='ui_rows'):
        for result in results:
            row=lookup.loc[result['id']]
            label=f"![bottle]({image_source(row,api)}) **`{result['rank']}.` {markdown_text(result['name'])}**  \n{markdown_text(result['brand'])} **{result['final_score']:.4f}**"
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


def add_search_halo(figure, locations):
    figure.add_trace(go.Scattergl(
        x=locations.scent_map_x, y=locations.scent_map_y, mode='markers',
        marker=dict(size=20, color='rgba(255,255,255,.8)'),
        hoverinfo='skip', showlegend=False,
    ))


def search_matches_figure(base, locations, *, show_label):
    if locations.empty:
        return base
    figure = shallow_figure(base)
    add_search_halo(figure, locations)
    figure.add_trace(go.Scattergl(
        x=locations.scent_map_x, y=locations.scent_map_y, mode='markers',
        marker=dict(size=12, color=locations.marker_rgb.tolist(),
                    line=dict(width=1.5, color='#2c2c2a')),
        customdata=list(zip(locations['Name'], locations['Brand'], locations['_id'])),
        hovertemplate='<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>',
        selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)),
        showlegend=False,
    ))
    if show_label and len(locations) == 1:
        row = locations.iloc[0]
        figure.add_annotation(
            x=row.scent_map_x, y=row.scent_map_y, text=escape(str(row['Name'])),
            showarrow=False, xanchor='right' if row.scent_map_x > 0 else 'left',
            xshift=-12 if row.scent_map_x > 0 else 12, yshift=10, borderpad=3,
            bgcolor='rgba(255,255,255,.88)', font=dict(family='Georgia', size=12, color='#2c2c2a'),
        )
    return figure


def overlay_figure(base, identifier, view):
    if not identifier:
        return base
    location = view.loc[view['_id'] == identifier]
    if location.empty:
        return base
    figure = shallow_figure(base)
    row = location.iloc[0]
    x, y = float(row.scent_map_x), float(row.scent_map_y)
    for diameter, color, width in [(13, '#2c2c2a', 1.5), (10, '#ffffff', 1)]:
        figure.add_trace(go.Scattergl(
            x=[x], y=[y], mode='markers', customdata=[[identifier]],
            marker=dict(symbol='circle-open', size=diameter, color=color, line=dict(width=width)),
            hoverinfo='skip', showlegend=False,
        ))
    name = '<br>'.join(escape(value) for value in textwrap.wrap(str(row['Name']), 32)[:2])
    figure.add_annotation(x=x, y=y, text=name, showarrow=False, xshift=12, yshift=10,
                          xanchor='left', bgcolor='rgba(255,255,255,.88)', borderpad=3,
                          font=dict(size=12, family='Georgia', color='#2c2c2a'))
    return figure


def add_rank_ring(figure, rank, x, y):
    """Add a stable Plotly shape that the selection can reveal without a redraw."""
    radius = (recommendation_marker_size(rank) + 6) / 2
    figure.add_shape(
        name=f'prism-selection-ring-{rank}', type='circle', layer='above',
        xref='x', yref='y', xsizemode='pixel', ysizemode='pixel',
        xanchor=x, yanchor=y, x0=-radius, x1=radius, y0=-radius, y1=radius,
        line=dict(color='rgba(110,123,201,0)', width=2),
    )


def show_rank_ring(figure, rank):
    if rank is None:
        return
    for index, shape in enumerate(figure.layout.shapes):
        if shape.name == f'prism-selection-ring-{rank}':
            st.html(f'<style>.st-key-ui_recommendation_chart '
                    f'.layer-above .shape-group[data-index="{index}"] > path'
                    '{stroke:#6e7bc9!important;stroke-opacity:1!important;pointer-events:none!important}'
                    '</style>')
            return


@lru_cache(maxsize=1)
def _recommendation_click_component():
    # The component forwards individual clicks, independent of Plotly's
    # toggleable selection.
    return st.components.v2.component(
        'prism_recommendation_clicks',
        html='<span hidden></span>',
        isolate_styles=False,
        js=r"""
export default function({data, parentElement, setTriggerValue}) {
    const host = parentElement.closest('.st-key-ui_recommendation_chart');
    if (!host) return;
    // Streamlit can rerun this initializer for new data on the same host.
    // Explicitly retire the old handlers before attaching their replacements.
    const slot = Symbol.for('prism.recommendation.clicks');
    host[slot]?.();
    let graph;
    let pending = data.selected;
    // Keep click cadence across component updates caused by opening a card.
    const previousClick = Symbol.for('prism.recommendation.lastClick');
    const atRecommendation = Symbol.for('prism.recommendation.initialRange');

    function trackRange(changes) {
        const endpoints = ['xaxis.range[0]', 'xaxis.range[1]', 'yaxis.range[0]', 'yaxis.range[1]'];
        if (!Object.keys(changes).some(key => /^[xy]axis\.(range|autorange)/.test(key))) return;
        const [recommended, full] = graph.layout.updatemenus[0].buttons;
        const matches = button => endpoints.every(key => changes[key] === button.args[0][key]);
        graph[atRecommendation] = matches(recommended);
        graph.dataset.prismView = graph[atRecommendation] ? 'recommended' : matches(full) ? 'full' : 'custom';
    }

    function resetRecommendation() {
        const button = [...graph.querySelectorAll('.updatemenu-button')]
            .find(element => element.textContent.trim() === '추천 범위');
        if (!button) return false;
        // A repeated point click at the default range needs no Plotly redraw.
        if (graph[atRecommendation]) return true;
        button.dispatchEvent(new MouseEvent('click', {bubbles: true}));
        return true;
    }

    function resetFromToolbar(event) {
        if (event.target.closest('.modebar-btn[data-title="Reset axes"]') && resetRecommendation()) {
            event.stopImmediatePropagation();
        }
    }
    let press;
    function start(event) {
        press = event.button === 0 && event.target.closest('.nsewdrag')
            ? {id: event.pointerId, x: event.clientX, y: event.clientY}
            : undefined;
    }
    function finish(event) {
        if (!press || event.pointerId !== press.id) return;
        const distance = Math.hypot(event.clientX - press.x, event.clientY - press.y);
        press = undefined;
        if (distance > 5 || !graph?.isConnected) {
            delete host[previousClick];
            return;
        }

        // Hit test the few visible recommendations using the active axes.
        // Plotly's hover and selection event streams can suppress rapid clicks.
        const layout = graph._fullLayout;
        const bounds = graph.querySelector('.svg-container')?.getBoundingClientRect();
        if (!layout || !bounds) return;
        const mouseX = event.clientX - bounds.left - layout.xaxis._offset;
        const mouseY = event.clientY - bounds.top - layout.yaxis._offset;
        if (mouseX < 0 || mouseX > layout.xaxis._length ||
            mouseY < 0 || mouseY > layout.yaxis._length) return;
        let nearest;
        let bestDistance = Infinity;
        for (const [index, trace] of graph.data.entries()) {
            const customdata = trace.customdata?.[0];
            if (trace.hoverinfo === 'skip' || typeof customdata?.at(-1) !== 'string') continue;
            const x = trace.x[0];
            const y = trace.y[0];
            const delta = Math.hypot(mouseX - layout.xaxis.d2p(x), mouseY - layout.yaxis.d2p(y));
            const size = Number(Array.isArray(trace.marker.size) ? trace.marker.size[0] : trace.marker.size);
            if (delta <= size / 2 + 2 && delta <= bestDistance) {
                nearest = {customdata, curve_number: index, x, y};
                bestDistance = delta;
            }
        }
        const id = nearest?.customdata.at(-1);
        const last = host[previousClick];
        const now = performance.now();
        if (last?.graph === graph && now - last.time <= 370 && last.id === id &&
            Math.hypot(mouseX - last.x, mouseY - last.y) <= 8) {
            delete host[previousClick];
            requestAnimationFrame(() => {
                if (graph?.isConnected) resetRecommendation();
            });
            return;
        }
        host[previousClick] = {graph, id, time: now, x: mouseX, y: mouseY};
        if (!id || id === pending) return;
        pending = id;
        setTriggerValue('point', nearest);
    }
    function detach() {
        graph?.removeEventListener('pointerdown', start, true);
        graph?.removeEventListener('click', resetFromToolbar, true);
        graph?.removeListener('plotly_relayout', trackRange);
        document.removeEventListener('pointerup', finish, true);
    }
    function attach() {
        const next = host.querySelector('[data-testid="stPlotlyChart"] .js-plotly-plot');
        if (next === graph || !next?.on) return;
        detach();
        graph = next;
        graph[atRecommendation] ??= true;
        graph.dataset.prismView ??= 'recommended';
        graph.on('plotly_relayout', trackRange);
        graph.addEventListener('pointerdown', start, true);
        graph.addEventListener('click', resetFromToolbar, true);
        document.addEventListener('pointerup', finish, true);
    }
    const selectionSlot = Symbol.for('prism.recommendation.scrolledSelection');
    function revealSelection() {
        const list = host.closest('.st-key-prism_unified')?.querySelector('.st-key-ui_rows');
        const buttons = list?.querySelectorAll('button');
        const button = buttons?.[data.rank - 1];
        if (host[selectionSlot] === data.selected && data.selected) return;
        if (!data.selected) {
            delete host[selectionSlot];
            return;
        }
        if (!button || button.getAttribute('kind') !== 'primary') return;
        const viewport = list.getBoundingClientRect();
        const row = button.getBoundingClientRect();
        if (!viewport.height || !row.height) return;
        host[selectionSlot] = data.selected;
        if (row.top < viewport.top) list.scrollTop -= viewport.top - row.top + 4;
        else if (row.bottom > viewport.bottom - 6) list.scrollTop += row.bottom - viewport.bottom + 6;
    }
    const frame = requestAnimationFrame(revealSelection);
    const observer = new MutationObserver(() => {
        if (!parentElement.isConnected) cleanup();
        else {
            attach();
            revealSelection();
        }
    });
    const cleanup = () => {
        cancelAnimationFrame(frame);
        observer.disconnect();
        detach();
        if (host[slot] === cleanup) delete host[slot];
    };
    host[slot] = cleanup;
    observer.observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['kind']});
    attach();
    return cleanup;
}
""",
    )


def recommendation_clicks(*, key, selected, rank, on_point):
    _recommendation_click_component()(key=key, data={'selected': selected, 'rank': rank},
                                      on_point_change=on_point)


def spread_section_labels(figure):
    """Keep true wheel anchors; separate their text in screen pixels."""
    from .scent_map import SECTION_ORDER
    from .profile_card import serif_font
    font=serif_font(14,bold=True)
    placed=[]
    labels=[(a,a.text[3:-4]) for a in figure.layout.annotations
            if a.text and a.text.startswith('<b>') and a.text.endswith('</b>') and a.text[3:-4] in SECTION_ORDER]
    # Check the same pixel offsets across narrow and wide full-map scales.
    scales = range(160, 206, 5)
    offsets = sorted(((dx, dy) for dx in range(-40, 41, 4) for dy in range(-36, 37, 4)),
                     key=lambda shift: shift[0] ** 2 + shift[1] ** 2)
    for annotation, name in sorted(labels, key=lambda item: abs(float(item[0].x))):
        x, y = float(annotation.x), float(annotation.y)
        width, height = float(font.getlength(name)) + 12, 22

        def fits(dx, dy):
            return not any(
                abs((x-u)*scale + dx-ox) < (width+ow)/2 and
                abs((y-v)*scale + dy-oy) < (height+oh)/2
                for u, v, ox, oy, ow, oh in placed for scale in scales
            )

        dx, dy = next((shift for shift in offsets if fits(*shift)), (0, 0))
        annotation.update(xshift=dx, yshift=dy, font_family='Georgia, Times New Roman, serif')
        if name == 'Woody Amber':
            annotation.update(bgcolor='rgba(250,250,248,0.8)', borderpad=1)
        placed.append((x, y, dx, dy, width, height))
    return figure


def scoped_styles():
    st.html('''<style>
    .st-key-prism_unified .st-key-ui_rows,.st-key-prism_unified .st-key-ui_rows [data-testid="stVerticalBlock"]{gap:10px}
    .st-key-prism_unified .st-key-ui_rows{padding:4px 2px;overflow-y:scroll!important;overscroll-behavior-y:contain;scrollbar-width:thin;scrollbar-color:#aca9be #f5f4f9}
    .st-key-prism_unified .st-key-ui_rows::after{content:'';position:sticky;bottom:0;flex:none;height:6px;margin-top:-6px;background:linear-gradient(transparent,#ebe9f4);pointer-events:none}
    .st-key-prism_unified [data-testid="stMarkdownContainer"]:has(> .ui-rec-title){margin-bottom:0}
    .st-key-prism_unified .ui-rec-title{display:flex;justify-content:space-between;align-items:baseline;gap:6px 16px;flex-wrap:wrap;margin-bottom:7px}
    .st-key-prism_unified .ui-rec-title h3{font-size:20px!important;font-weight:600!important;color:#302e38;line-height:1.2;margin:0;padding:0}
    .st-key-prism_unified{--prism-control-radius:8px;--prism-control-stroke:1px;--prism-control-border:rgba(49,51,63,.2);--prism-control-font:14px}
    .st-key-ui_recommendation_chart .updatemenu-button{translate:12px -43px}
    .st-key-ui_recommendation_chart .updatemenu-item-rect{rx:var(--prism-control-radius);ry:var(--prism-control-radius);height:32px;stroke:var(--prism-control-border)!important;stroke-width:var(--prism-control-stroke)!important}
    .st-key-ui_recommendation_chart .updatemenu-button text{font-size:var(--prism-control-font)!important}
    .st-key-ui_recommendation_chart .updatemenu-button + .updatemenu-button{translate:18px -43px}
    .st-key-ui_recommendation_chart .modebar{top:12.4px!important;right:25px!important}
    .st-key-ui_recommendation_chart .modebar-btn svg{width:18px;height:18px}
    .st-key-ui_recommendation_chart [data-prism-view="recommended"] .updatemenu-button:not(.updatemenu-button + .updatemenu-button) .updatemenu-item-rect,
    .st-key-ui_recommendation_chart [data-prism-view="full"] .updatemenu-button + .updatemenu-button .updatemenu-item-rect{fill:#eeedf9!important}
    .st-key-prism_unified .ui-rec-title p{line-height:1.35;margin:0 0 0 auto;color:#6c6975;font-size:14px;font-weight:400;overflow-wrap:anywhere}
    .st-key-prism_unified [data-testid="stLayoutWrapper"]:has(> .st-key-ui_recommendation_events),
    .st-key-prism_unified .st-key-ui_recommendation_events{display:none}
    .st-key-prism_unified .st-key-ui_rows button{position:relative;height:46px;min-height:46px;justify-content:flex-start;text-align:left;border:1px solid #e8e7ed;border-radius:9px;background:white;padding:3px 64px 3px 10px}
    .st-key-prism_unified .st-key-ui_rows button[kind="primary"]{background:#eeedf9;border-color:#a9add8}
    .st-key-prism_unified .st-key-ui_rows button>div,.st-key-prism_unified .st-key-ui_rows button [data-has-shortcut]{width:100%;min-width:0;justify-content:flex-start}
    .st-key-prism_unified .st-key-ui_rows button [data-testid="stMarkdownContainer"]{width:100%;min-width:0}
    .st-key-prism_unified .st-key-ui_rows button p{font-size:12px!important;color:#777484;text-align:left!important;width:100%;position:relative;padding-left:44px;min-height:35px;margin:0!important}
    .st-key-prism_unified .st-key-ui_rows button img{height:36px!important;max-height:36px!important;width:34px!important;max-width:34px!important;object-fit:contain;position:absolute;left:0;top:0;background:white}
    .st-key-prism_unified .st-key-ui_rows button br{display:none}
    .st-key-prism_unified .st-key-ui_rows button strong:first-of-type{font-size:14px;color:#302e38;display:block;line-height:1.25;white-space:nowrap;text-overflow:ellipsis;overflow:hidden;margin-bottom:2px}
    .st-key-prism_unified .st-key-ui_rows button strong:last-of-type{position:absolute;right:-54px;top:50%;transform:translateY(-50%);font-size:14px;color:#514d60}
    .st-key-prism_unified .st-key-ui_detail{position:relative}
    .st-key-prism_unified .st-key-ui_close{position:absolute;right:10px;top:6px;z-index:3;width:28px}
    .st-key-prism_unified .st-key-ui_close button{font-size:18px;color:#6c6975;min-height:25px;padding:0 6px;background:transparent;border:0}
    .st-key-prism_unified .prism-detail-card{border:1px solid;border-radius:16px;box-shadow:0 3px 12px #38384b09;padding:8px 16px;box-sizing:border-box}
    .st-key-prism_unified .prism-detail-top{display:flex;align-items:flex-start;gap:12px}
    .st-key-prism_unified .prism-detail-image{flex:0 0 auto;background:white;border:1px solid;border-radius:10px;padding:4px}
    .st-key-prism_unified .prism-detail-image img{display:block;width:120px;height:126px;object-fit:contain}
    .st-key-prism_unified .prism-detail-summary{flex:1;min-width:0;padding-right:24px}
    .st-key-prism_unified .prism-detail-name{font-size:22px;font-weight:bold;line-height:1.15;overflow-wrap:anywhere}
    .st-key-prism_unified .prism-detail-brand{font-size:13px;color:#61606b;margin:2px 0 4px}
    .st-key-prism_unified .prism-detail-accent{height:2px;margin-bottom:4px}
    .st-key-prism_unified .prism-detail-badges span{background:#e9e7f8;color:#4e5896;border-radius:14px;padding:2px 7px;font-size:12px;display:inline-block;margin:1px 2px 0 0}
    .st-key-prism_unified .prism-detail-chips{display:flex;flex-wrap:wrap;gap:3px;margin-top:5px}
    .st-key-prism_unified .prism-detail-chips span{border:1px solid;border-radius:16px;padding:1px 6px;color:#2c2c2a;font-size:12px}
    .st-key-prism_unified .prism-detail-notes{display:grid;grid-template-columns:52px 1fr;gap:4px 8px;font-size:13px;line-height:1.35;margin-top:6px}
    .st-key-prism_unified .prism-detail-notes b{color:#505b9c;white-space:nowrap}
    .st-key-prism_unified{gap:16px}
    .st-key-prism_unified [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] :is(.st-key-integration_search,[data-testid="stPlotlyChart"])){column-gap:56px}
    .st-key-ui_recommendation_chart{position:relative}
    .st-key-ui_recommendation_chart > [data-testid="stElementContainer"]:has(.ui-map-info){position:static}
    .st-key-ui_recommendation_chart .ui-map-info{position:absolute;left:211px;top:14.5px;z-index:20;color:#6b6573;font-size:18px;line-height:24px;cursor:default}
    .st-key-ui_recommendation_chart .ui-map-info:is(:hover,:focus){color:#6e7bc9}
    .st-key-ui_recommendation_chart .ui-map-tooltip{display:none;position:absolute;left:-14px;top:calc(100% + 7px);width:max-content;max-width:300px;grid-template-columns:auto auto;gap:5px 16px;word-break:keep-all;border-radius:10px;padding:12px 14px;background:#302e38;color:#fff;font-size:14px;line-height:1.4;box-shadow:0 6px 18px rgba(0,0,0,.18);pointer-events:none}
    .st-key-ui_recommendation_chart .ui-map-tooltip::before{content:'';position:absolute;left:19px;top:-7px;border-inline:4px solid transparent;border-bottom:8px solid #302e38}
    .st-key-ui_recommendation_chart .ui-map-tooltip b{font-weight:600}
    .st-key-ui_recommendation_chart .ui-map-info:is(:hover,:focus) .ui-map-tooltip{display:grid}
    @media(max-width:700px){.st-key-prism_unified [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] :is(.st-key-integration_search,[data-testid="stPlotlyChart"])){column-gap:16px}}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) [data-testid="stWidgetLabel"]{margin-bottom:5px;min-height:0}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) [data-testid="stWidgetLabel"] p{font-size:16px;font-weight:600;color:#302e38;line-height:1.25}
    .st-key-prism_unified :is(.ui-rec-title h3,.st-key-ui_rows button strong,.prism-detail-badges span,.st-key-ui_filter_toggle code){font-variant-numeric:lining-nums tabular-nums}
    .st-key-prism_unified :is(.ui-rec-title h3 span,.st-key-ui_rows button code,.st-key-ui_rows button strong:last-of-type,.prism-detail-badges span,.st-key-ui_filter_toggle code){font-family:'Times New Roman',Georgia,serif!important;font-variant-numeric:lining-nums tabular-nums}
    .st-key-prism_unified .st-key-ui_rows button code{font-size:inherit;font-weight:inherit;color:inherit;background:transparent;padding:0}
    .st-key-prism_unified .st-key-ui_filter_shell{border:1px solid #e2e1e8;border-radius:12px;background:white;gap:0}
    .st-key-prism_unified .st-key-ui_filter_actions{gap:8px;align-items:center}
    .st-key-prism_unified .st-key-ui_filter_hint{margin-left:auto}
    .st-key-prism_unified .ui-filter-pending{display:inline-flex;align-items:center;gap:8px;color:#465394;font-size:14px;font-weight:600}
    .st-key-prism_unified .ui-filter-pending::before{content:'';width:8px;height:8px;flex:none;border-radius:50%;background:#6e7bc9}
    .st-key-prism_unified .st-key-ui_filter_toggle button{border:0;border-radius:11px;background:white;color:#302e38;font-weight:600;min-height:44px;padding:8px 14px}
    .st-key-prism_unified .st-key-ui_filter_toggle button:hover{background:#f5f4fa;color:inherit}
    .st-key-prism_unified .st-key-ui_filter_toggle button:focus-visible{outline:2px solid #6e7bc9;outline-offset:-2px}
    .st-key-prism_unified .st-key-ui_filter_toggle button *{pointer-events:none}
    .st-key-prism_unified .st-key-ui_filter_toggle button>div,
    .st-key-prism_unified .st-key-ui_filter_toggle [data-has-shortcut],
    .st-key-prism_unified .st-key-ui_filter_toggle [data-testid="stMarkdownContainer"]{width:100%;max-width:none}
    .st-key-prism_unified .st-key-ui_filter_toggle p{display:flex;align-items:center;justify-content:space-between;gap:4px 12px;flex-wrap:wrap;width:100%;text-align:left;font-size:16px;font-weight:600}
    .st-key-prism_unified .st-key-ui_filter_toggle code{background:none;color:#6c6975;font:inherit;font-size:13px;font-weight:400;padding:0;margin-left:auto;white-space:normal}
    @media(max-width:639px){
        .st-key-prism_unified .st-key-ui_filter_toggle code{flex-basis:100%;margin-left:0}
    }
    .st-key-prism_unified .st-key-ui_filter_shell:has(.st-key-ui_filter_body) .st-key-ui_filter_toggle button{border-radius:11px 11px 0 0}
    .st-key-prism_unified .st-key-ui_filter_body{border-top:1px solid #ebeaf0;padding:14px}
    .st-key-prism_unified .st-key-ui_filter_body [data-testid="stVerticalBlock"]:has(> [data-testid="stLayoutWrapper"] > .st-key-ui_filter_actions){gap:12px}
    .st-key-prism_unified .st-key-ui_filter_actions button{min-height:34px;padding:4px 12px;font-size:var(--prism-control-font)}
    .st-key-prism_unified .st-key-ui_filter_actions button[kind="secondary"]{border-radius:var(--prism-control-radius);border:var(--prism-control-stroke) solid var(--prism-control-border)}
    .st-key-prism_unified .st-key-ui_filter_actions button[kind="secondary"]:hover{border-color:var(--primary-color,#6E7BC9)}
    .st-key-prism_unified .st-key-ui_filter_apply button[kind="secondary"]{background:#fff;color:#797582;border-color:#e2e1e8!important}
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
