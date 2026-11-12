"""Presentation-only helpers for the unified map. No artifact inputs changed."""
import json
from copy import deepcopy
from html import escape
from functools import lru_cache
import base64, re, textwrap, colorsys
from io import BytesIO
import plotly.graph_objects as go
import streamlit as st
from .i18n import t, TEXT, font_family, UI_FONT_FALLBACK, install_language_styles
from .scent_profile import pastel_colors, contrast_ratio, hsl_hex
from .scent_map import safe_eval, recommendation_marker_size, contrast_text_color


DETAIL_ADD_LABEL = "heart_add"
DETAIL_VIEW_LABEL = "rebase"
DETAIL_ADDED_LABEL = "heart_added"
DETAIL_FULL_LABEL = "heart_full"
DETAIL_ADD_HELP = "heart_add_help"
DETAIL_ADDED_HELP = "heart_remove_help"
DETAIL_FULL_REASON = "heart_full_help"
DETAIL_VIEW_HELP = "rebase_help"
DETAIL_ADD_ICON = ":material/favorite_border:"
DETAIL_ADDED_ICON = ":material/favorite:"
DETAIL_VIEW_ICON = ":material/search:"


def add_detail_signature(identifier):
    """Reuse profile add/remove callbacks without navigating away from the map."""
    from .profile_page import add_signature, remove_signature
    query = {key: st.query_params.get_all(key) for key in st.query_params}
    route = st.session_state.get('_prism_route_seen')
    if identifier in st.session_state.get('profile_signatures', []):
        remove_signature(identifier)
    else:
        st.session_state.detail_signature_candidate = identifier
        add_signature('detail_signature_candidate', (identifier,))
    st.query_params.clear()
    for key, values in query.items():
        st.query_params[key] = values
    st.session_state._profile_url_values = tuple(query.get('prism_scent', []))
    st.session_state._prism_route_seen = route


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


def accord_chip_style(section_class, accord, description):
    content = json.dumps(description, ensure_ascii=False).replace('<', r'\3c ')
    key = re.sub(r'[^a-zA-Z0-9_-]', '-', accord)
    return f'{section_class} .st-key-ui_chip_{key}{{--accord-description:{content}}}'


def accord_chip(accord, selected, toggle, section_index):
    st.button(accord, key='ui_chip_'+accord, type='primary' if selected else 'secondary',
              on_click=toggle, args=(section_index, accord), wrap=True)


def display_text_color(color):
    """Use the common contrast rule, with the profile palette's 4.5:1 safeguard."""
    foreground = contrast_text_color(color)
    background = '#' + ''.join(f'{int(channel.strip()):02x}' for channel in color[4:-1].split(','))
    return '#000000' if contrast_ratio(background, foreground) < 4.5 else foreground



def detail_surface_colors(hue, marker):
    """UI-only tones: shared card hue, reference edge lightness, bounded extremes."""
    channels = ([int(marker[i:i+2],16) for i in (1,3,5)] if marker.startswith('#')
                else [int(v) for v in re.findall(r'\d+',marker)[:3]])
    lightness = colorsys.rgb_to_hls(*(v/255 for v in channels))[1] * 100
    edge_l = max(64., min(76., lightness + 2.5))
    return hsl_hex(hue,45,edge_l), hsl_hex(hue,35,max(78.,min(88.,edge_l+14.)))


def card_html(identifier,catalog,view,results,api):
    row=catalog.loc[catalog['_id']==identifier].iloc[0]
    location=view.loc[view['_id']==identifier]
    record=location.iloc[0] if not location.empty else None
    hue=float(record['scent_map_hue']) if record is not None else 232.
    palette=pastel_colors(hue,(70,94))
    color=str(record['marker_rgb']) if record is not None else '#777777'
    edge, rule = detail_surface_colors(hue,color)
    match=next((r for r in results if r['id']==identifier),None)
    badges=(t('rank', rank=match['rank'])+'</span> <span>'+t('similarity', score=match['final_score']) if match else t('base') if identifier == st.session_state.get('integration_base') else t('selected_perfume'))
    picture=escape(image_source(row,api),quote=True)
    html = f'''<div class="prism-detail-card" data-perfume-id="{escape(str(identifier), quote=True)}" style="background:{palette['background']};color:{palette['foreground']};border-color:{edge};--detail-border:{edge};--detail-rule:{rule}">
    <div class="prism-detail-top">
    <div class="prism-detail-image" style="border-color:{color}"><img src="{picture}" alt=""></div>
    <div class="prism-detail-summary">
    <div class="prism-detail-brand">{escape(str(row['Brand']))}</div>
    <div class="prism-detail-name" title="{escape(str(row['Name']), quote=True)}">{escape(str(row['Name']))}</div>
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
            value = escape(", ".join(notes)) if notes else '—'
            html += f'<div class="prism-detail-note"><b>{t({"Top":"top","Middle":"middle","Base":"base_note"}[layer])}</b><div>{value}</div></div>'
        html += '</div>'
    return html+'</div>',dict(hue=hue,background=palette['background'],foreground=palette['foreground'],border=edge,rule=rule,contrast=contrast_ratio(palette['background'],palette['foreground']))


def detail_icon_color(marker, background):
    """Darken only the action glyph, preserving hue and 3:1 contrast."""
    channels = ([int(marker[index:index + 2], 16) for index in (1, 3, 5)]
                if marker.startswith('#') else [int(v) for v in re.findall(r'\d+', marker)[:3]])
    for step in range(1, 21):
        color = '#' + ''.join(f'{round(value * (1 - step * .05)):02x}' for value in channels)
        if contrast_ratio(background, color) >= 3:
            return color
    return '#000000'


def detail_panel(identifier,catalog,view,results,api,close,reference):
    with st.container(key='ui_detail'):
        st.button('×',key='ui_close',on_click=close,type='tertiary')
        html,palette=card_html(identifier,catalog,view,results,api)
        st.markdown(html,unsafe_allow_html=True)
        from .profile_state import MAX_SIGNATURES
        signatures = st.session_state.get('profile_signatures', [])
        added = identifier in signatures
        full = len(signatures) >= MAX_SIGNATURES
        label = DETAIL_ADDED_LABEL if added else DETAIL_FULL_LABEL if full else DETAIL_ADD_LABEL
        # A stable slot prevents actions from shifting the detail card's delta path.
        with st.container(key='ui_detail_actions', gap=None):
            st.button(t(label), key='ui_detail_add', disabled=full and not added,
                      on_click=add_detail_signature, args=(identifier,), width='stretch',
                      icon=DETAIL_ADDED_ICON if added else DETAIL_ADD_ICON)
            name = str(catalog.loc[catalog['_id'].eq(identifier), 'Name'].iloc[0])
            st.button(t(DETAIL_VIEW_LABEL), key='ui_detail_reference', width='stretch',
                      on_click=reference, args=(identifier, name),
                      icon=DETAIL_VIEW_ICON)
        location = view.loc[view['_id'].eq(identifier)]
        marker = str(location.iloc[0]['marker_rgb']) if not location.empty else '#777777'
        accent = detail_icon_color(marker, palette['background'])
        rgb = ','.join(str(int(accent[index:index + 2], 16)) for index in (1, 3, 5))
        add_help = json.dumps(t(DETAIL_ADDED_HELP if added else DETAIL_FULL_REASON if full else DETAIL_ADD_HELP), ensure_ascii=False).replace('<', r'\3c ')
        view_help = json.dumps(t(DETAIL_VIEW_HELP), ensure_ascii=False).replace('<', r'\3c ')
        st.markdown(f"<style>.st-key-ui_detail_add{{--detail-help:{add_help}}}"
                    f".st-key-ui_detail_reference{{--detail-help:{view_help}}}"
                    f".st-key-ui_detail_actions{{--detail-action-color:{accent};"
                    f"--detail-action-hover:rgba({rgb},.2);--detail-disabled-opacity:{1 if added else .35}}}"
                    f".st-key-prism_unified .st-key-ui_detail_actions .st-key-ui_detail_add [data-testid=stIconMaterial]{{font-variation-settings:"
                    f"'FILL' {1 if added else 0},'wght' 600,'GRAD' 0,'opsz' 28;"
                    f"color:{'transparent' if added else 'var(--detail-action-color)'}!important;"
                    f"--detail-heart-filled:{1 if added else 0}}}</style>",
                    unsafe_allow_html=True)


def map_hint(*, recommended):
    """One accessible tooltip for both the full map and recommendation map."""
    reset_label = t('range' if recommended else 'full_view')
    pairs = [('wheel','zoom'),('drag','box_zoom'),('point_click','details')]
    content = ''.join(f'<b>{t(left)}</b><span>{t(right)}</span>' for left,right in pairs)
    st.html(f'<span class="ui-map-info" tabindex="0" aria-label="{t("help_label")}" '
            'aria-describedby="prism-map-help">ⓘ'
            '<span class="ui-map-tooltip" id="prism-map-help" role="tooltip">'
            + content + f'<b>{t("reset")}</b><span>{reset_label}</span></span></span>')




def map_footer(name='', kind=None):
    """HTML-only current-fragrance footer; no language-dependent chart metadata."""
    label = name if name else t('footer_hint')
    tag = t('footer_'+kind) if kind else ''
    st.html('<div class="ui-map-footer" data-kind="'+(kind or 'hint')+'"><span class="ui-map-footer-name" title="'
            +escape(label,quote=True)+'">'+escape(label)+'</span><span class="ui-map-footer-tag">'+tag+'</span></div>')


def intro_banner():
    st.html('<div class="ui-atlas-intro"><div class="ui-atlas-line"><h2>'+t('atlas_headline')+'</h2></div></div>')


def markdown_text(value):
    return re.sub(r'([\\*\[\]_`])',r'\\\1',str(value)).replace('\n',' ')


def recommendation_rows(results,catalog,selected,api,select):
    reference = st.session_state.get('integration_base')
    result_ids = {result['id'] for result in results}
    if reference and results and (
            st.session_state.get('ui_default_card_reference') != reference or selected not in result_ids | {reference}):
        st.session_state.ui_default_card_reference = reference
        st.session_state.ui_default_card_epoch = st.session_state.get('ui_default_card_epoch', 0) + 1
        select(reference)
        # Rerun before painting the rows/card so map, row and card share one selection.
        st.rerun()
    lookup=catalog.set_index('_id')
    with st.container(height=214,border=False,key='ui_rows'):
        for result in results:
            row=lookup.loc[result['id']]
            label=f"![bottle]({image_source(row,api)}) **`{result['rank']:02d}` *{markdown_text(result['name'])}***  \n*{markdown_text(result['brand'])}* **{result['final_score']:.4f}**"
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


def localize_figure(base):
    """Prepare stable UI metadata; browser localization preserves chart identity."""
    figure = shallow_figure(base)
    figure._layout['height'] = 480
    figure._layout['margin'] = dict(figure._layout.get('margin', {}), t=40, b=56)
    figure._layout['paper_bgcolor'] = '#FFFFFF'
    figure._layout['plot_bgcolor'] = '#FFFFFF'
    figure._layout['modebar'] = dict(figure._layout.get('modebar', {}),
                                   color='#6B6B72', activecolor='#1A1A1A', bgcolor='#FFFFFF')
    family = UI_FONT_FALLBACK
    for i, original in enumerate(base._data):
        payload = dict(original)
        for field in ('textfont',):
            if field in payload: payload[field] = dict(payload[field], family=family)
        if 'hoverlabel' in payload:
            label = dict(payload['hoverlabel'])
            label['font'] = dict(label.get('font', {}), family=family)
            payload['hoverlabel'] = label
        cls = go.Scattergl if payload.get('type') == 'scattergl' else go.Scatter
        trace = cls(payload, _validate=False)
        figure._data[i] = payload
        figure._data_objs[i] = trace
        trace._parent = figure
        trace._trace_ind = i
    figure._layout['font'] = dict(figure._layout.get('font', {}), family=family)
    figure._layout['hoverlabel'] = dict(figure._layout.get('hoverlabel', {}), font=dict(family=family))
    for annotation in figure._layout.get('annotations', []):
        annotation['font'] = dict(annotation.get('font', {}), family=family)
    for menu in figure._layout.get('updatemenus', []):
        menu['font'] = dict(menu.get('font', {}), family=family, color='#1A1A1A', size=13)
        menu['bordercolor'] = '#D9D9DE'
        menu['bgcolor'] = '#FFFFFF'
        for button, key in zip(menu.get('buttons', []), ('range','full_map')): button['label'] = TEXT[key]['ko']
    return figure


def subset_figure(base,visible,reference,filters):
    figure=shallow_figure(base)
    payload=dict(base._data[0],x=visible.scent_map_x.tolist(),y=visible.scent_map_y.tolist())
    payload['marker']=dict(payload['marker'],color=visible.marker_rgb.tolist())
    if not reference:
        payload['hoverlabel'] = dict(
            payload['hoverlabel'], bgcolor=visible.marker_rgb.tolist(),
            bordercolor=visible.marker_border.tolist(),
            font=dict(payload['hoverlabel']['font'], color=visible.marker_text.tolist()),
        )
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
        hoverlabel=dict(align='left', bgcolor=locations.marker_rgb.tolist(),
                        bordercolor=locations.marker_border.tolist(),
                        font=dict(family=UI_FONT_FALLBACK, size=14, color=locations.marker_text.tolist())),
        selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=1)),
        showlegend=False,
    ))
    if show_label and len(locations) == 1:
        row = locations.iloc[0]
        figure.add_annotation(
            x=row.scent_map_x, y=row.scent_map_y, text=escape(str(row['Name'])),
            showarrow=False, xanchor='right' if row.scent_map_x > 0 else 'left',
            xshift=-12 if row.scent_map_x > 0 else 12, yshift=10, borderpad=3,
            bgcolor='rgba(255,255,255,.88)', font=dict(family=UI_FONT_FALLBACK, size=12, color='#2c2c2a'),
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
                          font=dict(size=12, family=UI_FONT_FALLBACK, color='#2c2c2a'))
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
        ring_indices = ','.join(f'[data-index="{index}"]'
                                for index, shape in enumerate(figure.layout.shapes)
                                if (shape.name or '').startswith('prism-selection-ring-'))
        if ring_indices:
            st.html(f'<style>.st-key-ui_recommendation_chart '
                    f'.layer-above .shape-group:is({ring_indices}) > path'
                    '{stroke-opacity:0!important}</style>')
        return
    for index, shape in enumerate(figure.layout.shapes):
        if shape.name == f'prism-selection-ring-{rank}':
            st.html(f'<style>.st-key-ui_recommendation_chart '
                    f'.layer-above .shape-group[data-index="{index}"] > path'
                    '{stroke:#1A1A1A!important;stroke-opacity:1!important;pointer-events:none!important}'
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
    // Keep click cadence across component updates caused by opening a card.
    const previousClick = Symbol.for('prism.recommendation.lastClick');
    const atRecommendation = Symbol.for('prism.recommendation.initialRange');

    function positionHelp() {
        const buttons = graph?.querySelectorAll('.updatemenu-button');
        const info = host.querySelector('.ui-map-info');
        if (buttons?.length && info) info.style.setProperty('left', (buttons[buttons.length-1].getBoundingClientRect().right-host.getBoundingClientRect().left+8)+'px', 'important');
    }
    function trackRange(changes) {
        const endpoints = ['xaxis.range[0]', 'xaxis.range[1]', 'yaxis.range[0]', 'yaxis.range[1]'];
        if (!Object.keys(changes).some(key => /^[xy]axis\.(range|autorange)/.test(key))) return;
        const [recommended, full] = graph.layout.updatemenus[0].buttons;
        const matches = button => endpoints.every(key => changes[key] === button.args[0][key]);
        graph[atRecommendation] = matches(recommended);
        graph.dataset.prismView = graph[atRecommendation] ? 'recommended' : matches(full) ? 'full' : 'custom';
    }

    function resetRecommendation() {
        positionHelp();
        const button = graph.querySelector('.updatemenu-button');
        if (!button) return false;
        // A repeated point click at the default range needs no Plotly redraw.
        if (graph[atRecommendation]) return true;
        button.dispatchEvent(new MouseEvent('click', {bubbles: true}));
        return true;
    }

    function resetFromToolbar(event) {
        if (event.target.closest('.modebar-btn:is([data-title="Reset axes"],[data-prism-original-title="Reset axes"])') && resetRecommendation()) {
            event.stopImmediatePropagation();
        }
    }
    // The component can be reinitialized between pointerdown and pointerup.
    // Keep the press on the chart, and only consume it for the same plot.
    const pressSlot = Symbol.for('prism.recommendation.press');
    function start(event) {
        if (event.button === 0 && event.target.closest('.nsewdrag')) {
            host[pressSlot] = {graph, id: event.pointerId, x: event.clientX, y: event.clientY};
        }
    }
    function cancelPress(event) {
        if (host[pressSlot]?.id === event.pointerId) delete host[pressSlot];
    }
    function finish(event) {
        const press = host[pressSlot];
        if (!press || event.pointerId !== press.id) return;
        delete host[pressSlot];
        const distance = Math.hypot(event.clientX - press.x, event.clientY - press.y);
        if (press.graph !== graph || distance > 5 || !graph?.isConnected) {
            delete host[previousClick];
            return;
        }

        const target = markerAt(event.clientX, event.clientY);
        if (!target) return;
        const {nearest, mouseX, mouseY} = target;
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
        const card = host.closest('.st-key-prism_unified')?.querySelector('.prism-detail-card');
        if (!id || (id === card?.dataset.perfumeId && !card.closest('[data-stale="true"]'))) return;
        setTriggerValue('point', nearest);
    }
    function markerAt(clientX, clientY) {
        // Hit test the few visible recommendations using the active axes.
        // Plotly's hover and selection event streams can suppress rapid clicks.
        const layout = graph._fullLayout;
        const bounds = graph.querySelector('.svg-container')?.getBoundingClientRect();
        if (!layout || !bounds) return;
        const mouseX = clientX - bounds.left - layout.xaxis._offset;
        const mouseY = clientY - bounds.top - layout.yaxis._offset;
        if (mouseX < 0 || mouseX > layout.xaxis._length ||
            mouseY < 0 || mouseY > layout.yaxis._length) return;
        let nearest;
        // Pick the first covering marker in front-to-back drawing order.
        const traces = [...graph.data.entries()].reverse();
        for (const [index, trace] of traces) {
            const customdata = trace.customdata?.[0];
            if (trace.hoverinfo === 'skip' || typeof customdata?.at(-1) !== 'string') continue;
            const x = trace.x[0];
            const y = trace.y[0];
            const delta = Math.hypot(mouseX - layout.xaxis.d2p(x), mouseY - layout.yaxis.d2p(y));
            const size = Number(Array.isArray(trace.marker.size) ? trace.marker.size[0] : trace.marker.size);
            if (delta <= size / 2 + 2) {
                nearest = {customdata, curve_number: index, x, y};
                break;
            }
        }
        return {nearest, mouseX, mouseY};
    }

    function updateHover(event) {
        const nearest = event.type === 'mouseleave' ? undefined
            : markerAt(event.clientX, event.clientY)?.nearest;
        graph._fullData?.forEach((trace, index) => {
            const source = graph.data[index];
            if (!source || source.hoverinfo === 'skip' ||
                typeof source.customdata?.[0]?.at(-1) !== 'string') return;
            trace.hoverinfo = index === nearest?.curve_number ? source.hoverinfo : 'skip';
        });
    }

    function detach() {
        graph?.removeEventListener('pointerdown', start, true);
        graph?.removeEventListener('mousemove', updateHover, true);
        graph?.removeEventListener('mouseleave', updateHover);
        graph?.removeEventListener('click', resetFromToolbar, true);
        graph?.removeListener?.('plotly_relayout', trackRange);
        document.removeEventListener('pointerup', finish, true);
        document.removeEventListener('pointercancel', cancelPress, true);
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
        graph.addEventListener('mousemove', updateHover, true);
        graph.addEventListener('mouseleave', updateHover);
        graph.addEventListener('click', resetFromToolbar, true);
        document.addEventListener('pointerup', finish, true);
        document.addEventListener('pointercancel', cancelPress, true);
    }
    const selectionSlot = Symbol.for('prism.recommendation.scrolledSelection');
    const defaultScrollSlot = Symbol.for('prism.recommendation.defaultScroll');
    function revealSelection() {
        positionHelp();
        graph?.data.forEach((trace, index) => {
            if (trace.mode !== 'markers' || trace.hoverinfo === 'skip' || !trace.customdata?.[0]) return;
            const point = graph.getElementsByClassName('trace' + graph._fullData[index].uid)[0]?.querySelector('.point');
            if (!point) return;
            const baseSelected = !data.rank && trace.customdata[0].at(-1) === data.selected;
            point.style.setProperty('stroke', baseSelected ? '#1A1A1A' : trace.marker.line.color, 'important');
            point.style.setProperty('stroke-width', (baseSelected ? 2.4 : trace.marker.line.width) + 'px', 'important');
        });
        const list = host.closest('.st-key-prism_unified')?.querySelector('.st-key-ui_rows');
        const buttons = list?.querySelectorAll('button');
        for (const row of buttons ?? []) {
            const heading = row.querySelector('strong:first-of-type > em');
            if (!heading || heading.title) continue;
            heading.title = heading.textContent.trim();
        }
        const button = buttons?.[data.rank - 1];
        if (data.defaultEpoch && (host[defaultScrollSlot] !== data.defaultEpoch || (!data.rank && data.selected))) {
            list.scrollTop = 0;
            host[defaultScrollSlot] = data.defaultEpoch;
        }
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
    _recommendation_click_component()(key=key, data={'selected': selected, 'rank': rank,
                                            'defaultEpoch': st.session_state.get('ui_default_card_epoch', 0)},
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
        annotation.update(xshift=dx, yshift=dy, font_family=UI_FONT_FALLBACK)
        if name == 'Woody Amber':
            annotation.update(bgcolor='rgba(250,250,248,0.8)', borderpad=1)
        placed.append((x, y, dx, dy, width, height))
    return figure


def scoped_styles():
    st.html('''<style>
    .st-key-prism_unified .st-key-ui_rows,.st-key-prism_unified .st-key-ui_rows [data-testid="stVerticalBlock"]{gap:10px}
    .st-key-prism_unified .st-key-ui_rows{padding:4px 0;overflow-y:auto!important;overscroll-behavior-y:contain;scrollbar-width:thin;scrollbar-color:#aca9be #f5f4f9}
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
    .st-key-prism_unified .st-key-ui_rows button p{font-size:12px!important;color:#777484;text-align:left!important;width:100%;position:relative;padding-left:44px;min-height:0;margin:0!important;line-height:15px;white-space:nowrap;overflow-wrap:normal}
    .st-key-prism_unified .st-key-ui_rows button img{height:36px!important;max-height:36px!important;width:34px!important;max-width:34px!important;object-fit:contain;position:absolute;left:0;top:0;background:white}
    .st-key-prism_unified .st-key-ui_rows button br{display:none}
    .st-key-prism_unified .st-key-ui_rows button strong:first-of-type{font-size:14px;color:#302e38;display:flex;align-items:baseline;gap:4px;min-width:0;line-height:18px;margin-bottom:1px}
    .st-key-prism_unified .st-key-ui_rows button strong:first-of-type > code{flex:none}
    .st-key-prism_unified .st-key-ui_rows button strong:first-of-type > em{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-style:normal}
    .st-key-prism_unified .st-key-ui_rows button p > em{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-style:normal;line-height:15px}
    .st-key-prism_unified .st-key-ui_rows button strong:last-of-type{position:absolute;right:-54px;top:50%;transform:translateY(-50%);font-size:14px;color:#514d60}
    .st-key-prism_unified .st-key-ui_detail{position:relative}
    .st-key-prism_unified .st-key-ui_close{position:absolute;right:10px;top:6px;z-index:3;width:28px}
    .st-key-prism_unified .st-key-ui_close button{font-size:18px;color:#6c6975;min-height:25px;padding:0 6px;background:transparent;border:0}
    .st-key-prism_unified .prism-detail-card{border:1px solid;border-radius:16px;box-shadow:0 3px 12px #38384b09;padding:8px 16px;box-sizing:border-box;min-height:254px}
    .st-key-prism_unified .prism-detail-top{display:flex;align-items:flex-start;gap:12px}
    .st-key-prism_unified .prism-detail-image{flex:0 0 auto;background:white;border:1px solid;border-radius:10px;padding:4px}
    .st-key-prism_unified .prism-detail-image img{display:block;width:120px;height:126px;object-fit:contain}
    .st-key-prism_unified .prism-detail-summary{flex:1;min-width:0;padding-right:24px}
    .st-key-prism_unified .prism-detail-name{font-size:22px;font-weight:bold;line-height:1.15;overflow-wrap:anywhere}
    .st-key-prism_unified .prism-detail-brand{font-size:13px;color:#61606b;margin:2px 0 4px;anchor-name:--prism-detail-brand;padding-right:68px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .st-key-prism_unified .prism-detail-accent{height:2px;margin-bottom:4px}
    .st-key-prism_unified .prism-detail-badges span{background:#e9e7f8;color:#4e5896;border-radius:14px;padding:2px 7px;font-size:12px;display:inline-block;margin:1px 2px 0 0}
    .st-key-prism_unified .prism-detail-chips{display:flex;flex-wrap:wrap;gap:3px;margin-top:5px}
    .st-key-prism_unified .prism-detail-chips span{border:1px solid;border-radius:16px;padding:1px 6px;color:#2c2c2a;font-size:12px}
    .st-key-prism_unified .prism-detail-notes{display:grid;grid-template-columns:52px 1fr;gap:4px 8px;font-size:13px;line-height:1.35;margin-top:6px}
    .st-key-prism_unified .st-key-ui_detail{anchor-scope:--prism-detail-brand}
    .st-key-prism_unified .st-key-ui_detail_actions{position:absolute;position-anchor:--prism-detail-brand;top:anchor(center);right:41px;transform:translateY(-50%);width:58px;height:28px;flex-direction:row;align-items:center;gap:2px;z-index:2}
    .st-key-prism_unified .st-key-ui_detail_actions > div{width:28px!important;flex:0 0 28px}
    .st-key-prism_unified .st-key-ui_detail_actions button{position:relative;display:flex!important;align-items:center!important;justify-content:center!important;width:28px!important;min-width:28px!important;max-width:28px!important;min-height:28px!important;max-height:28px!important;height:28px!important;box-sizing:border-box;margin:0!important;padding:0!important;border:0!important;border-radius:50%;box-shadow:none!important;background:transparent!important;color:var(--detail-action-color)!important;gap:0!important}
    .st-key-prism_unified .st-key-ui_detail_actions button:is(:hover,:focus-visible):not(:disabled){background:var(--detail-action-hover)!important}
    .st-key-prism_unified .st-key-ui_detail_actions button:focus-visible{outline:2px solid var(--detail-action-color);outline-offset:1px}
    .st-key-prism_unified .st-key-ui_detail_actions button:disabled{opacity:var(--detail-disabled-opacity)}
    .st-key-prism_unified .st-key-ui_detail_actions button [data-testid=stMarkdownContainer]{position:absolute!important;width:0!important;min-width:0!important;height:0;overflow:hidden;clip-path:inset(50%);margin:0!important;padding:0!important;flex:0 0 0!important}
    .st-key-prism_unified .st-key-ui_detail_actions button p{width:0;height:0;margin:0;padding:0;overflow:hidden}
    .st-key-prism_unified .st-key-ui_detail_actions [data-testid=stIconMaterial]{font-family:'Material Symbols Rounded'!important;font-size:18px!important;width:18px!important;height:18px!important;min-width:18px;max-width:18px;flex:0 0 18px;margin:0!important;padding:0!important;position:relative;display:inline-flex;align-items:center;justify-content:center;line-height:18px!important;transform:none;font-variation-settings:'FILL' 0,'wght' 600,'GRAD' 0,'opsz' 28}
    /* The bundled Material font has no variable FILL axis; use a solid mask only when registered. */
    .st-key-prism_unified .st-key-ui_detail_add [data-testid=stIconMaterial]::after{content:"";position:absolute;inset:0;pointer-events:none;opacity:var(--detail-heart-filled,0);background:var(--detail-action-color);mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54z'/%3E%3C/svg%3E") center/contain no-repeat}
    .st-key-prism_unified .prism-detail-notes b{color:#505b9c;white-space:nowrap}
    .st-key-prism_unified{gap:12px}
    @media(min-width:701px){
    .st-key-prism_unified [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] :is(.st-key-integration_search,[data-testid="stPlotlyChart"])){column-gap:20px}
    .st-key-prism_unified [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] :is(.st-key-integration_search,[data-testid="stPlotlyChart"])) > [data-testid="stColumn"]:first-child{flex:0 0 calc(60% - 28px);width:calc(60% - 28px)}
    .st-key-prism_unified [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] :is(.st-key-integration_search,[data-testid="stPlotlyChart"])) > [data-testid="stColumn"]:last-child{flex:1 1 0;min-width:0}
    }
    .st-key-prism_unified [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] [data-testid="stPlotlyChart"]) > [data-testid="stColumn"]:last-child > [data-testid="stVerticalBlock"]{gap:12px}
    .st-key-ui_recommendation_chart{position:relative}
    .st-key-ui_empty_chart{position:relative}
    .st-key-ui_empty_chart .ui-map-info{left:25px!important}
    [data-testid="stMainBlockContainer"]:has(.st-key-ui_empty_chart){padding-bottom:0!important}
    /* The recommendation chart paints the WebGL background below its SVG marker groups. */
    .st-key-ui_recommendation_chart .svg-container{background:#fafaf8}
    .st-key-ui_recommendation_chart .svg-container > .gl-container{position:absolute;inset:0;z-index:0;pointer-events:none}
    .st-key-ui_recommendation_chart .svg-container > .main-svg{z-index:2}
    .st-key-ui_recommendation_chart .svg-container > .main-svg:first-child{background:transparent!important;z-index:1}
    .st-key-ui_recommendation_chart .svg-container > .modebar-container{z-index:3}
    .st-key-ui_recommendation_chart .svg-container > .main-svg:last-child{z-index:4}

    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) > [data-testid="stElementContainer"]:has(.ui-map-info){position:static}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-info{position:absolute;left:211px;top:14.5px;z-index:20;color:#6b6573;font-size:18px;line-height:24px;cursor:default}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-info:is(:hover,:focus){color:#6e7bc9}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-tooltip{display:none;position:absolute;left:-14px;top:calc(100% + 7px);width:max-content;max-width:300px;grid-template-columns:auto auto;gap:5px 16px;word-break:keep-all;border-radius:10px;padding:12px 14px;background:#302e38;color:#fff;font-size:14px;line-height:1.4;box-shadow:0 6px 18px rgba(0,0,0,.18);pointer-events:none}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-tooltip::before{content:'';position:absolute;left:19px;top:-7px;border-inline:4px solid transparent;border-bottom:8px solid #302e38}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-tooltip b{font-weight:600}
    .st-key-ui_filter_grid [class*="st-key-ui_chip_"]{position:relative}
    .st-key-ui_filter_grid [class*="st-key-ui_chip_"]::after{
        content:var(--accord-description,none);position:absolute;z-index:30;pointer-events:none;
        top:calc(100% + 6px);left:50%;translate:-50% 0;width:max-content;max-width:min(320px,70vw);
        padding:9px 12px;text-align:left;white-space:normal;word-break:keep-all;
        border:1px solid color-mix(in srgb,var(--section-ink) 40%,white);
        background:color-mix(in srgb,var(--section-ink) 14%,white);
        color:#302e38;border-radius:10px;box-shadow:0 6px 18px rgba(0,0,0,.18);
        font-size:14px;font-weight:400;line-height:1.4;visibility:hidden;opacity:0;transition:none;
    }
    .st-key-ui_filter_grid [data-testid="stColumn"]:last-child [class*="st-key-ui_chip_"]::after{
        left:auto;right:0;translate:none
    }
    .st-key-ui_filter_grid [class*="st-key-ui_chip_"]:not([data-stale="true"],[data-stale="true"] *):has(button:hover:not(:active))::after{
        visibility:visible;opacity:1
    }
    .st-key-ui_filter_grid :is([data-testid="stColumn"],[data-testid="stElementContainer"]):has([class*="st-key-ui_chip_"] button:hover){
        position:relative;z-index:30
    }
    .st-key-ui_filter_grid [class*="st-key-ui_chip_"]:has(button:hover){z-index:31}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-info:is(:hover,:focus) .ui-map-tooltip{display:grid}
    @media(max-width:700px){.st-key-prism_unified [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] :is(.st-key-integration_search,[data-testid="stPlotlyChart"])){column-gap:16px}}
    .st-key-integration_picker [data-testid="stCaptionContainer"]{margin-top:8px}
    .st-key-integration_search [data-testid="InputInstructions"]{display:none!important}
    .st-key-integration_search_box{position:relative}
    .st-key-integration_search_box .st-key-integration_clear{position:absolute;right:8px;bottom:4.4px;width:26px;z-index:2}
    .st-key-integration_search_box:not(:has(input:not(:placeholder-shown))) .st-key-integration_clear{display:none}
    .st-key-integration_search_box input{padding-right:38px}
    .st-key-integration_search_box .st-key-integration_clear button{
        width:26px;height:26px;min-height:26px;padding:0;border:0;background:transparent;color:rgba(49,51,63,.6);box-shadow:none
    }
    .st-key-integration_search_box .st-key-integration_clear button:hover{color:rgba(49,51,63,.85)}
    .st-key-integration_search_box .st-key-integration_clear button p{position:absolute;clip-path:inset(50%)}
    .st-key-integration_search_box .st-key-integration_clear button::before{
        content:'';position:absolute;inset:50% auto auto 50%;translate:-50% -50%;width:16px;height:16px;background:currentColor;
        mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill-rule='evenodd' d='M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm4.29 12.89a.996.996 0 11-1.41 1.41L12 13.41 9.11 16.3a.996.996 0 11-1.41-1.41L10.59 12 7.71 9.11A.996.996 0 119.12 7.7L12 10.59l2.89-2.89a.996.996 0 111.41 1.41L13.41 12l2.88 2.89z'/%3E%3C/svg%3E") center/contain no-repeat
    }
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) [data-testid="stWidgetLabel"]{margin-bottom:5px;min-height:0}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) [data-testid="stWidgetLabel"] p{font-size:16px;font-weight:600;color:#302e38;line-height:1.25}
    .st-key-prism_unified :is(.ui-rec-title h3,.st-key-ui_rows button strong,.prism-detail-badges span,.st-key-ui_filter_toggle code){font-variant-numeric:lining-nums tabular-nums}
    .st-key-prism_unified :is(.ui-rec-title h3 span,.st-key-ui_rows button code,.st-key-ui_rows button strong:last-of-type,.prism-detail-badges span,.st-key-ui_filter_toggle code){font-family:var(--prism-ui-font),sans-serif!important;font-variant-numeric:lining-nums tabular-nums}
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

    /* White editorial surfaces only: existing widths, heights, padding and gaps stay intact. */
    .st-key-prism_unified{--prism-control-border:#D9D9DE;--prism-control-radius:2px}
    .st-key-prism_unified .st-key-ui_rows{scrollbar-color:#b7b7bc #fff}
    .st-key-prism_unified .st-key-ui_rows::after{background:linear-gradient(transparent,#fff)}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .ui-rec-title h3{color:#1A1A1A!important}
    .st-key-prism_unified .st-key-ui_rows button{border-radius:1px!important;background:#fff!important;border-color:transparent!important;border-bottom-color:#D9D9DE!important;box-shadow:none!important}
    .st-key-prism_unified .st-key-ui_rows button[kind="primary"]{border-color:#1A1A1A!important}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .st-key-ui_rows button[kind="primary"]::before{display:none}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .st-key-ui_rows button code,
    [data-testid="stAppViewContainer"] .st-key-prism_unified .st-key-ui_rows button strong:last-of-type{color:#1A1A1A!important}
    .st-key-prism_unified .prism-detail-card{border-radius:1px!important;border-color:#D9D9DE!important;box-shadow:none}
    .st-key-prism_unified .prism-detail-image{border-radius:1px;border-color:#D9D9DE!important}
    .st-key-prism_unified .prism-detail-accent{background:#D9D9DE!important}
    .st-key-prism_unified .prism-detail-badges span{background:#f1f1f2;color:#1A1A1A}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .prism-detail-note b{color:#1A1A1A!important}
    .st-key-prism_unified .st-key-ui_filter_shell{border-color:#D9D9DE;border-radius:1px}
    .st-key-prism_unified .st-key-ui_filter_toggle button,
    .st-key-prism_unified .st-key-ui_filter_shell:has(.st-key-ui_filter_body) .st-key-ui_filter_toggle button{border-radius:0}
    .st-key-prism_unified .st-key-ui_filter_toggle button:hover{background:#f7f7f7}
    .st-key-prism_unified .st-key-ui_filter_toggle button:focus-visible{outline-color:#1A1A1A}
    .st-key-prism_unified .st-key-ui_filter_body{border-top-color:#D9D9DE}
    .st-key-prism_unified .ui-filter-pending{color:#1A1A1A}
    .st-key-prism_unified .ui-filter-pending::before{background:#1A1A1A}
    .st-key-prism_unified .st-key-ui_filter_actions button[kind="primary"]{background:#1A1A1A;border-color:#1A1A1A;color:white}
    .st-key-prism_unified .st-key-ui_filter_actions button[kind="secondary"]:hover{border-color:#1A1A1A}
    .st-key-prism_unified .st-key-ui_filter_apply button[kind="secondary"]{border-color:#D9D9DE!important}
    .st-key-prism_unified [class*="st-key-ui_group_"] button{color:#1A1A1A}
    .st-key-prism_unified .st-key-ui_filter_grid [class*="st-key-ui_section_"]{background:white;border-top-color:#D9D9DE;border-right-color:#D9D9DE;border-bottom-color:#D9D9DE}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) :is([data-baseweb="input"],[data-baseweb="select"] > div,[data-testid="stTextInputRootElement"],.react-aria-ComboBox > [role="group"]){background:#FFFFFF!important;border-color:transparent transparent #D9D9DE!important;border-style:solid!important;border-width:1px!important;border-radius:0!important;box-shadow:none!important}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) :is([data-baseweb="input"],[data-baseweb="select"] > div,[data-testid="stTextInputRootElement"],.react-aria-ComboBox > [role="group"]):focus-within{border-bottom-color:#1A1A1A!important}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) input{background:transparent!important}
    [data-testid="stAppViewContainer"] .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) [data-testid="stWidgetLabel"] p{color:#666666!important;font-size:12px!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart){background:#FFFFFF;border-radius:1px;outline:1px solid #D9D9DE;outline-offset:-1px}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .svg-container{background:#FFFFFF}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-info:is(:hover,:focus){color:#1A1A1A}
    .st-key-ui_recommendation_chart [data-prism-view="recommended"] .updatemenu-button:not(.updatemenu-button + .updatemenu-button) .updatemenu-item-rect,
    .st-key-ui_recommendation_chart [data-prism-view="full"] .updatemenu-button + .updatemenu-button .updatemenu-item-rect{fill:#f1f1f2!important;stroke:#1A1A1A!important}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .st-key-ui_rows button code{white-space:nowrap!important;word-break:normal!important;overflow-wrap:normal!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart)::after{content:'';position:absolute;inset:0;border:1px solid #D9D9DE;border-radius:1px;z-index:5;pointer-events:none}

    /* White editorial pass 2. Geometry changes are confined to the requested headings/panel. */
    .st-key-prism_unified .st-key-integration_chart_slot{gap:0}
    .st-key-prism_unified .ui-rec-title{height:28px;min-height:28px;flex-wrap:nowrap;align-items:baseline;margin-bottom:12px}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .ui-rec-title h3{font-size:22px!important;line-height:28px!important;font-weight:500!important;white-space:nowrap;letter-spacing:.02em}
    .st-key-prism_unified .ui-rec-title p{font-size:12px;line-height:18px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
    .st-key-prism_unified .st-key-ui_rows,.st-key-prism_unified .st-key-ui_rows [data-testid="stVerticalBlock"]{gap:8px}
    .st-key-prism_unified .st-key-ui_rows button{height:44px;min-height:44px}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) [data-testid="stWidgetLabel"]{margin-bottom:4px}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) :is([data-testid="stTextInputRootElement"],.react-aria-ComboBox > [role="group"]){padding-left:0!important;background:#FFFFFF!important}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) input{padding-left:0!important;border:0!important;border-radius:0!important;box-shadow:none!important;background:#FFFFFF!important;opacity:1!important}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) input:-webkit-autofill{-webkit-box-shadow:0 0 0 1000px #FFFFFF inset!important;-webkit-text-fill-color:#1A1A1A!important}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) input::selection{background:#ececee}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) [role="group"]:is(:hover,[data-focused],[data-disabled]){background:#FFFFFF!important}
    .st-key-integration_search_box .st-key-integration_clear button::before,
    .st-key-integration_base button[aria-label="Clear value"]::before{content:'';position:absolute;left:50%;top:50%;translate:-50% -50%;width:14px;height:14px;background:currentColor;mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='m6 6 12 12M18 6 6 18' fill='none' stroke='black' stroke-width='1.7'/%3E%3C/svg%3E") center/contain no-repeat}
    .st-key-integration_base button[aria-label="Clear value"]{position:relative;color:#777777}
    .st-key-integration_base button[aria-label="Clear value"] svg{visibility:hidden}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .prism-detail-brand{font-size:10px;line-height:16px;letter-spacing:.12em;text-transform:uppercase;anchor-name:none;margin:0 0 4px;padding-right:12px}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .prism-detail-name{white-space:normal;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;line-height:23px;font-size:19px!important;overflow:hidden;overflow-wrap:normal;margin-bottom:6px}
    .st-key-prism_unified .prism-detail-badges{anchor-name:--prism-detail-brand;min-height:20px;line-height:20px;padding-right:64px;white-space:nowrap}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .prism-detail-badges span{background:transparent;color:#1A1A1A;padding:0;margin:0;border-radius:0;line-height:20px;font-size:12px;white-space:nowrap}
    .st-key-prism_unified .prism-detail-badges span + span::before{content:'';display:inline-block;height:10px;border-left:1px solid #D9D9DE;margin:0 8px;vertical-align:-1px}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .prism-detail-notes{display:flex;flex-direction:column;letter-spacing:.01em;gap:3px;border-top:1px solid #D9D9DE;margin-top:8px;padding-top:6px}
    .st-key-prism_unified .prism-detail-note{display:grid;grid-template-columns:52px minmax(0,1fr);column-gap:8px;align-items:baseline}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .prism-detail-note b{font-size:10px;line-height:18px;letter-spacing:.08em}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .prism-detail-note div{font-size:12px;line-height:18px;overflow-wrap:anywhere}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart)::before{content:'';position:absolute;left:0;right:0;top:51px;height:1px;background:#D9D9DE;z-index:5;pointer-events:none}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-footer{position:absolute;left:0;right:0;bottom:0;height:30px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 12px;box-sizing:border-box;border-top:1px solid #D9D9DE;background:white;color:#666666;font-size:11px;line-height:18px;z-index:6;pointer-events:none}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-footer span:last-child{text-transform:uppercase;white-space:nowrap;letter-spacing:.04em}
    .st-key-ui_recommendation_chart .updatemenu-item-rect{stroke:transparent!important;stroke-width:0!important;rx:2px;ry:2px;fill:#FFFFFF!important}
    .st-key-ui_recommendation_chart [data-prism-view="recommended"] .updatemenu-button:not(.updatemenu-button + .updatemenu-button) .updatemenu-item-rect,
    .st-key-ui_recommendation_chart [data-prism-view="full"] .updatemenu-button + .updatemenu-button .updatemenu-item-rect{fill:#F0F0F2!important;stroke:transparent!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn:is([data-prism-original-title="Zoom"],[data-prism-original-title="Pan"],[data-prism-original-title="Fullscreen"],[data-title="Zoom"],[data-title="Pan"],[data-title="Fullscreen"]){display:none!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn{color:#6B6B72!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn:hover{color:#1A1A1A!important}

    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) [data-testid="stWidgetLabel"]{margin-bottom:-6px}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) :is([data-testid="stTextInputRootElement"],.react-aria-ComboBox > [role="group"]){border-left-width:0!important;border-right-width:0!important}
    .st-key-prism_unified :is(.st-key-integration_search,.st-key-integration_base) input{height:38px!important;min-height:38px!important;line-height:38px!important;padding-top:0!important;padding-bottom:0!important;box-sizing:border-box}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart)::after{z-index:8}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar{opacity:1!important;top:15px!important;right:25px!important}
    .st-key-prism_unified .st-key-ui_rows{padding-top:0;padding-bottom:0}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-group{opacity:1!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn path{fill:#6B6B72!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn:hover path{fill:#1A1A1A!important}

    /* Atlas presentation: no recommendation, coordinate or selection-state changes. */
    .st-key-prism_unified{--prism-panel-height:480px}
    @media(max-height:820px){.st-key-prism_unified{--prism-panel-height:460px}}
    [data-testid="stMainBlockContainer"]:has(.st-key-prism_unified){padding-bottom:0!important}
    .st-key-prism_unified .ui-atlas-intro{height:57px;box-sizing:border-box;padding-top:19px}
    .st-key-prism_unified .ui-atlas-line{display:flex;align-items:baseline;justify-content:space-between;gap:20px;margin-top:0}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .ui-atlas-line h2{font-size:31px!important;font-weight:400!important;line-height:38px!important;letter-spacing:.02em;margin:0;padding:0;color:#1A1A1A;white-space:nowrap}
    .st-key-prism_unified [data-testid="stColumn"] > [data-testid="stVerticalBlock"]:has(.st-key-integration_results_slot){gap:0!important;padding-top:40px}
    .st-key-prism_unified [data-testid="stColumn"] > [data-testid="stVerticalBlock"]:is(:has(.st-key-ui_rows),:has(.prism-detail-card)){padding-top:0}
    .st-key-prism_unified [data-testid="stColumn"]:has(.st-key-ui_rows) .st-key-integration_detail_slot{margin-top:12px}
    .st-key-prism_unified [data-testid="stColumn"]:not(:has(.st-key-ui_rows)) .prism-detail-card{height:auto;min-height:0}
    .st-key-prism_unified [data-testid="stColumn"]:not(:has(.st-key-ui_rows)) .prism-detail-notes{margin-top:8px}
    .st-key-prism_unified .st-key-ui_rows{height:calc(var(--prism-panel-height) - 266px)!important;min-height:0!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart){height:var(--prism-panel-height);min-height:var(--prism-panel-height);max-height:var(--prism-panel-height)}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) [data-testid="stPlotlyChart"],
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) [data-testid="stPlotlyChart"] > div{height:var(--prism-panel-height)!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart)::before{top:39px}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-footer{height:40px;gap:16px;font-size:14px;color:#1A1A1A}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-footer-name{min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;line-height:20px}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-footer-tag{font-size:12px;color:#6B6B72;line-height:18px;letter-spacing:.06em;text-transform:none!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-footer[data-kind="hint"] .ui-map-footer-name{color:#6B6B72}
    .st-key-ui_recommendation_chart .updatemenu-button,.st-key-ui_recommendation_chart .updatemenu-button + .updatemenu-button{translate:none!important}
    .st-key-ui_recommendation_chart .updatemenu-button text{font-size:13px!important}
    .st-key-ui_recommendation_chart .updatemenu-item-rect{height:28px;fill:#FFFFFF!important;stroke:#D9D9DE!important;stroke-width:1px!important;rx:0;ry:0}
    .st-key-ui_recommendation_chart [data-prism-view="recommended"] .updatemenu-button:not(.updatemenu-button + .updatemenu-button) .updatemenu-item-rect,
    .st-key-ui_recommendation_chart [data-prism-view="full"] .updatemenu-button + .updatemenu-button .updatemenu-item-rect{fill:#F0F0F2!important;stroke:#D9D9DE!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-info{left:12px!important;top:11px;font-size:18px;line-height:18px;height:18px}
    .st-key-ui_recommendation_chart .ui-map-info{left:auto!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar{top:6px!important;right:12px!important;display:flex;gap:0;padding:0!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-group{display:flex;gap:20px;padding:0!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-group:not(:has(.modebar-btn:is([data-prism-original-title="Zoom in"],[data-prism-original-title="Zoom out"],[data-prism-original-title="Reset axes"],[data-title="Zoom in"],[data-title="Zoom out"],[data-title="Reset axes"]))){display:none!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn{position:relative;width:18px;height:28px;line-height:28px;padding:0!important;box-sizing:border-box}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn svg{visibility:hidden}
    .st-key-prism_unified .st-key-ui_filter_shell{border:0;border-bottom:1px solid #D9D9DE;border-radius:0;background:white}
    .st-key-prism_unified .st-key-ui_filter_toggle button{background:white!important;padding-left:0;padding-right:0;min-height:44px}
    .st-key-prism_unified .st-key-ui_filter_toggle p{font-size:15px;font-weight:500;color:#1A1A1A}
    .st-key-prism_unified .st-key-ui_filter_toggle code{font-size:13px;color:#6B6B72}
    .st-key-prism_unified .st-key-ui_rows button{display:flex;align-items:center!important}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .st-key-ui_rows button code{top:50%;transform:translateY(-50%);line-height:1;padding-top:1px;font-variant-numeric:lining-nums tabular-nums}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .st-key-ui_rows button strong:last-of-type{line-height:1;padding-top:1px;font-variant-numeric:lining-nums tabular-nums}
    .st-key-prism_unified .st-key-ui_rows button img{top:50%;transform:translateY(-50%)}
    .st-key-prism_unified .prism-detail-card,.st-key-prism_unified .prism-detail-image{border-color:var(--detail-border)!important}
    .st-key-prism_unified .prism-detail-accent{background:var(--detail-rule)!important}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .prism-detail-notes{border-top-color:var(--detail-rule)!important}

    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) div:has(> [data-testid="stPlotlyChart"]){height:var(--prism-panel-height)!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-group{display:flex!important;gap:20px!important;align-items:center!important;width:max-content}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn{height:28px!important;min-height:28px!important;max-height:28px!important;width:18px!important;line-height:28px!important}
    .st-key-prism_unified .prism-detail-badges span + span::before{border-left-color:var(--detail-rule)}
    .st-key-prism_unified div:has(> .st-key-ui_rows){height:calc(var(--prism-panel-height) - 266px)!important;min-height:0!important}
    [data-testid="stAppViewContainer"] .st-key-prism_unified .st-key-ui_rows,
    [data-testid="stAppViewContainer"] .st-key-prism_unified div:has(> .st-key-ui_rows){height:calc(var(--prism-panel-height) - 266px)!important;max-height:calc(var(--prism-panel-height) - 266px)!important;min-height:0!important;flex:0 0 auto!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) [data-testid="stElementContainer"]:has([data-testid="stPlotlyChart"]),
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) div:has(> [data-testid="stPlotlyChart"]){height:var(--prism-panel-height)!important;max-height:var(--prism-panel-height)!important;min-height:0!important;flex:0 0 auto!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) > [data-testid="stElementContainer"]:has(.ui-map-footer){position:static!important}
    .st-key-prism_unified .st-key-ui_detail{gap:0!important}

    /* Native modebar tooltips own ::before/::after. Draw icons as backgrounds instead.
       2 SVG units in a 24-unit viewBox at 18px yields a 1.5px stroke. */
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn{background-image:var(--prism-icon-neutral)!important;background-position:center!important;background-size:18px 18px!important;background-repeat:no-repeat!important;background-color:transparent!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn:hover{background-image:var(--prism-icon-ink)!important}
    .modebar-btn[data-prism-original-title="Zoom in"]{--prism-icon-neutral:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%3E%3Cpath%20d%3D%22M12%203v18M3%2012h18%22%20fill%3D%22none%22%20stroke%3D%22%236B6B72%22%20stroke-width%3D%222%22%20stroke-linejoin%3D%22round%22%2F%3E%3C%2Fsvg%3E");--prism-icon-ink:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%3E%3Cpath%20d%3D%22M12%203v18M3%2012h18%22%20fill%3D%22none%22%20stroke%3D%22%231A1A1A%22%20stroke-width%3D%222%22%20stroke-linejoin%3D%22round%22%2F%3E%3C%2Fsvg%3E")}
    .modebar-btn[data-prism-original-title="Zoom out"]{--prism-icon-neutral:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%3E%3Cpath%20d%3D%22M3%2012h18%22%20fill%3D%22none%22%20stroke%3D%22%236B6B72%22%20stroke-width%3D%222%22%20stroke-linejoin%3D%22round%22%2F%3E%3C%2Fsvg%3E");--prism-icon-ink:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%3E%3Cpath%20d%3D%22M3%2012h18%22%20fill%3D%22none%22%20stroke%3D%22%231A1A1A%22%20stroke-width%3D%222%22%20stroke-linejoin%3D%22round%22%2F%3E%3C%2Fsvg%3E")}
    .modebar-btn[data-prism-original-title="Reset axes"]{--prism-icon-neutral:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%3E%3Cpath%20d%3D%22m3%2011%209-8%209%208M6%2010v11h12V10M10%2021v-7h4v7%22%20fill%3D%22none%22%20stroke%3D%22%236B6B72%22%20stroke-width%3D%222%22%20stroke-linejoin%3D%22round%22%2F%3E%3C%2Fsvg%3E");--prism-icon-ink:url("data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20viewBox%3D%220%200%2024%2024%22%3E%3Cpath%20d%3D%22m3%2011%209-8%209%208M6%2010v11h12V10M10%2021v-7h4v7%22%20fill%3D%22none%22%20stroke%3D%22%231A1A1A%22%20stroke-width%3D%222%22%20stroke-linejoin%3D%22round%22%2F%3E%3C%2Fsvg%3E")}

    /* Same immediate, hover-only CSS tooltip behavior as the accord capsules. */
    .st-key-ui_detail_actions :is(.st-key-ui_detail_add,.st-key-ui_detail_reference)::after{
        content:var(--detail-help);position:absolute;top:calc(100% + 6px);right:0;
        width:max-content;max-width:320px;padding:9px 12px;box-sizing:border-box;
        white-space:normal;word-break:keep-all;text-align:left;
        background:color-mix(in srgb,var(--detail-action-color) 14%,white);
        border:1px solid color-mix(in srgb,var(--detail-action-color) 40%,white);
        color:#302e38;border-radius:10px;box-shadow:0 6px 18px rgba(0,0,0,.18);
        font-size:14px;font-weight:400;line-height:1.4;z-index:40;
        pointer-events:none;visibility:hidden;opacity:0;transition:none;
    }
    .st-key-ui_detail_actions :is(.st-key-ui_detail_add,.st-key-ui_detail_reference):not([data-stale="true"],[data-stale="true"] *):has(button:hover:not(:active))::after{visibility:visible;opacity:1}

    /* Neutral map help: same immediate CSS-only structure as detail actions. */
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-container{z-index:30!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) :is(.modebar,.modebar-group){overflow:visible!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn::before,
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-tooltip::before{content:none!important;display:none!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn::after,
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-tooltip{
        background:#F0F0F2!important;border:1px solid #D6D6DA!important;color:#1A1A1A!important;
        border-radius:10px!important;padding:9px 12px!important;box-shadow:0 6px 18px rgba(0,0,0,.18)!important;
        font-family:var(--prism-ui-font),system-ui,sans-serif!important;font-size:14px!important;font-weight:400!important;line-height:1.4!important;
        box-sizing:border-box;pointer-events:none!important;transition:none!important;animation:none!important;
        visibility:hidden!important;opacity:0!important;z-index:40;transform:none!important;margin:0!important;
    }
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn::after{
        content:attr(data-title)!important;display:block!important;position:absolute!important;
        top:40px!important;right:0!important;left:auto!important;bottom:auto!important;white-space:nowrap!important;width:max-content;max-width:300px;
    }
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .modebar-btn:hover:not(:active)::after{visibility:visible!important;opacity:1!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-tooltip{top:35px!important;left:-4px!important;display:none!important}
    :is(.st-key-ui_recommendation_chart,.st-key-ui_empty_chart) .ui-map-info:hover .ui-map-tooltip{display:grid!important;visibility:visible!important;opacity:1!important}
    </style>''')

