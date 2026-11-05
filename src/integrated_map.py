"""Unified UI only. Existing artifact, ranking and highlight functions are reused."""
import streamlit as st
import plotly.graph_objects as go
from html import escape
from .catalog_search import find_perfumes
from .profile_labels import build_label_index, sorted_choices
from .integrated_ui import (
    add_rank_ring, add_search_halo, detail_panel, overlay_figure, recommendation_rows, scoped_styles,
    recommendation_clicks, search_matches_figure, section_colors, show_rank_ring,
    spread_section_labels, subset_figure,
)

STAGE = 'ui-fix8-v1'
SEARCH_MARKER_LIMIT = 30
NATIVE_POINTS = True


def clear_details():
    st.session_state.integration_detail = None
    st.session_state.integration_epoch = st.session_state.get('integration_epoch', 0)+1


def reset_search():
    st.session_state.integration_base = None
    clear_details()


@st.cache_data(show_spinner=False, max_entries=64)
def ranked(settings, identifier, _api, recommendation_logic=""):
    # Include changed matrix logic in the ranking cache key.
    catalog, accords, notes = _api.get_recommendation_cache(settings, _api.RECOMMENDATION_LOGIC_VERSION)
    return _api.recommend(identifier, catalog, accords, notes)


@st.cache_resource(show_spinner=False,max_entries=8)
def visible_rows(settings,logic,filters,_view):
    if not filters:return _view
    selected=set(filters)
    return _view.loc[_view.accord_values.map(lambda values:bool(selected.intersection(values)))]


@st.cache_resource(show_spinner=False, max_entries=4)
def figure_for(settings, identifier, filters, stage, _api):
    original = _api.get_display_cache(settings, _api.MAP_LOGIC_VERSION)
    view = original['view']
    visible=visible_rows(settings,_api.MAP_LOGIC_VERSION,filters,view)
    if filters:
        return subset_figure(figure_for(settings,identifier,(),stage,_api),visible,identifier,filters)
    full=original['full_figure']
    cached = dict(original, full_figure=full)
    results = ranked(settings, identifier, _api, _api.RECOMMENDATION_LOGIC_VERSION) if identifier else []
    if identifier:
        fig, _ = _api.recommendation_figure(cached, results)
        recommendation_end=len(fig.data)
        base = _api.get_coordinates([identifier], view)
        if not base.empty:
            add_search_halo(fig, base)
            fig.add_trace(go.Scattergl(x=base.scent_map_x, y=base.scent_map_y, mode='markers',
                                      marker=dict(size=12, color='#2c2c2a'),hoverinfo='skip',showlegend=False))
            fig.add_trace(_api.build_highlight_trace(base,{identifier:1},marker_size=9,
                                                     show_rank=False,white_width=.7))
            ref=base.iloc[0]
            fig.add_annotation(x=ref.scent_map_x,y=ref.scent_map_y,text=escape(str(ref['Name'])),
                               showarrow=False,xanchor='right',xshift=-10,yshift=8,borderpad=3,
                               bgcolor='rgba(255,255,255,.88)',font=dict(family='Georgia',size=12,color='#2c2c2a'))
            # Include the reference point without changing recommendation jitter.
            for axis, column in [('xaxis','scent_map_x'),('yaxis','scent_map_y')]:
                limits = list(fig.layout[axis].range or [-1.3,1.3])
                limits[0] = min(limits[0],float(base[column].min())-.08)
                limits[1] = max(limits[1],float(base[column].max())+.08)
                fig.update_layout(**{axis:dict(range=limits)})
    else:
        fig = go.Figure(full.to_plotly_json(), _validate=False)
        recommendation_end=1
    if stage != 'A':
        # UI-only payload: leave artifact tooltip text and hashed preparation intact.
        bg = fig.data[0]
        bg.hovertext = None
        bg.hoverlabel = dict(align='left',font=dict(family='Georgia',size=14))
        bg.customdata = None if identifier else list(zip(visible['Name'],visible['Brand'],visible['_id']))
        bg.hovertemplate = '<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>'
        bg.hoverinfo = 'skip' if identifier else None
        if identifier:bg.hovertemplate = None
        rank_ids = {r['rank']:r['id'] for r in results}
        for index, trace in enumerate(fig.data[1:],1):
            if index >= recommendation_end:
                point_id = identifier
            else:
                fill_index = 2+3*((index-1)//3)
                point_id = rank_ids[int(fig.data[fill_index].customdata[0][0])]
            if trace.customdata is not None:
                trace.customdata = [list(values)+[point_id] for values in trace.customdata]
            else:
                trace.customdata = [[point_id] for _ in trace.x]
            if trace.hoverinfo != 'skip':
                match = next((r for r in results if r['id']==point_id),None)
                row = view.loc[view['_id']==point_id].iloc[0]
                trace.hovertemplate = '<b>'+escape(str(row['Name']))+'</b><br>'+escape(str(row['Brand']))
                if match: trace.hovertemplate += f"<br>Rank: {match['rank']}<br>Similarity: {match['final_score']:.4f}"
                trace.hovertemplate += '<extra></extra>'
                trace.hovertext = None
        # Plotly's WebGL selection can drop text when a point is toggled
        # off. Keep ranks in non-interactive SVG annotations on the same
        # coordinates; the underlying fill remains the clickable point.
        marker_traces = []
        for trace in fig.data:
            if trace.mode == 'text':
                font = trace.textfont
                add_rank_ring(fig, int(trace.text[0]), float(trace.x[0]), float(trace.y[0]))
                fig.add_annotation(
                    x=float(trace.x[0]), y=float(trace.y[0]),
                    text=f"<b>{trace.text[0]}</b>", name="prism-rank-"+str(trace.text[0]),
                    showarrow=False, captureevents=False, borderpad=0,
                    xanchor='center', yanchor='middle',
                    font=dict(family=font.family, size=font.size, color=font.color[0]),
                )
            else:
                marker_traces.append(trace)
                neutral = dict(marker=dict(opacity=1))
                trace.update(selected=neutral, unselected=neutral)
        fig.data = tuple(marker_traces)
        fig.update_layout(clickmode='event+select' if NATIVE_POINTS and not identifier else 'event',selectionrevision=str(identifier))
    # Preserve equal coordinate scale; let ranges expand, never shrink the plot domain.
    fig.update_layout(height=520,autosize=True,margin=dict(l=12,r=12,t=16,b=16),
                      modebar=dict(color="#aaa9b5",activecolor="#6E7BC9",bgcolor="rgba(255,255,255,.45)"),
                      xaxis=dict(domain=[0,1],constrain='range'),
                      yaxis=dict(domain=[0,1],constrain='range',scaleanchor='x',scaleratio=1),
                      uirevision=str(identifier)+str(filters))
    full_range = [-1.22, 1.22]
    if identifier:
        def view_button(label, x_range, y_range):
            return dict(label=label, method='relayout', args=[{
                'xaxis.autorange': False, 'yaxis.autorange': False,
                # Scalar endpoints stay fixed even when Plotly mutates its live ranges.
                'xaxis.range[0]': float(x_range[0]), 'xaxis.range[1]': float(x_range[1]),
                'yaxis.range[0]': float(y_range[0]), 'yaxis.range[1]': float(y_range[1]),
            }])

        fig.update_layout(margin_t=52, updatemenus=[dict(
            type='buttons', direction='right', showactive=False, active=-1,
            x=0.0, y=1.0, xanchor='left', yanchor='top',
            pad=dict(t=0, r=0, b=0, l=0), bgcolor='#ffffff',
            bordercolor='#dedce8', borderwidth=1,
            font=dict(family='Georgia', size=14, color='#38364a'),
            buttons=[
                view_button('추천 범위', fig.layout.xaxis.range, fig.layout.yaxis.range),
                view_button('전체 지도', full_range, full_range),
            ],
        )])
    else:
        fig.update_layout(xaxis_range=full_range, yaxis_range=full_range)
    return spread_section_labels(fig)


def point_identifier(event):
    points = event.get('selection',{}).get('points',[])
    if not points:return None
    data=points[-1].get('customdata')
    return data[-1] if isinstance(data,(list,tuple)) and data else None


def select_detail(identifier):
    if identifier != st.session_state.get("integration_detail"):
        st.session_state.integration_detail = identifier


def capture_map(key, permitted, *, point_trigger=False):
    state = st.session_state.get(key, {})
    if point_trigger:
        point = state.get('point') or {}
        identifier = point_identifier({'selection': {'points': [point]}})
    else:
        identifier = point_identifier(state)
    if identifier and (permitted is None or identifier in permitted):
        select_detail(identifier)


def set_all_groups(groups, enabled):
    for i,(_,options) in enumerate(groups):
        st.session_state[f'integration_draft_{i}']=list(options) if enabled else []


def toggle_group(index,options):
    key=f'integration_draft_{index}'
    st.session_state[key]=[] if set(st.session_state.get(key,[]))==set(options) else list(options)


def toggle_accord(index,accord):
    key=f'integration_draft_{index}'
    values=list(st.session_state.get(key,[]))
    if accord in values:values.remove(accord)
    else:values.append(accord)
    st.session_state[key]=values


def apply_groups(groups):
    st.session_state.integration_active=sorted({value for i,_ in enumerate(groups) for value in st.session_state.get(f'integration_draft_{i}',[])})


def toggle_filter():
    st.session_state.ui_filter_open=not st.session_state.get('ui_filter_open',False)


@st.fragment
def filter_editor(api,groups):
    from .accord_descriptions import ACCORD_DESCRIPTIONS
    active=set(st.session_state.integration_active)
    draft={a for i,_ in enumerate(groups) for a in st.session_state.get(f'integration_draft_{i}',[])}
    has_changes = draft != active
    with st.container(horizontal=True,vertical_alignment='center',key='ui_filter_actions'):
        st.button('전체 선택',key='ui_filter_all',on_click=set_all_groups,args=(groups,True))
        st.button('전체 해제',key='ui_filter_clear',on_click=set_all_groups,args=(groups,False))
        if st.button('적용',type='primary' if has_changes else 'secondary',key='ui_filter_apply'):
            apply_groups(groups)
            st.rerun(scope='app')
        with st.container(key='ui_filter_hint',width='content'):
            if has_changes:
                st.html('<span class="ui-filter-pending" role="status">변경 사항이 있습니다 — 적용을 눌러주세요</span>')
            else:
                st.caption('OR 조건 · 미선택 시 전체 표시')
    css=[]
    for i,(section,_) in enumerate(groups):
        ink,pale=section_colors(section,api)
        section_class = f'.st-key-prism_unified .st-key-ui_section_{i}'
        css.append(f'{section_class}{{--section-ink:{ink};--section-pale:{pale}}}')
        trigger = f'{section_class} [class*="st-key-ui_chip_"] [data-testid="stTooltipHoverTarget"]'
        css.append(f':root:has({trigger}:hover, {trigger} button:focus-visible)'
                   f'{{--prism-accord-tooltip-ink:{ink}}}')
    st.html('<style>'+''.join(css)+'</style>')
    with st.container(key='ui_filter_grid'):
        # The dense Soft Amber group gets two grid units; remaining rows use four.
        starts=[(0,3,[1,2,1])]+[(i,min(i+4,len(groups)),[1,1,1,2] if len(groups)-i==4 else 4) for i in range(3,len(groups),4)]
        for start,end,widths in starts:
            cols=st.columns(widths,gap='small')
            for i in range(start,end):
                section,options=groups[i]
                with cols[i-start],st.container(key=f'ui_section_{i}'):
                    with st.container(horizontal=True,vertical_alignment='center',key=f'ui_heading_{i}'):
                        st.markdown(f'<span class="ui-section-title"><span>●</span> <b>{escape(section)}</b></span>',unsafe_allow_html=True)
                        st.button('섹션 전체',key=f'ui_group_{i}',type='tertiary',on_click=toggle_group,args=(i,options))
                    with st.container(horizontal=True,key=f'ui_chips_{i}'):
                        chosen=set(st.session_state.get(f'integration_draft_{i}',[]))
                        for accord in options:
                            st.button(accord,key='ui_chip_'+accord,type='primary' if accord in chosen else 'secondary',
                                      help=ACCORD_DESCRIPTIONS.get(accord),on_click=toggle_accord,args=(i,accord))


def filters_ui(api,settings,view):
    from .scent_map import SECTION_ORDER
    from .accord_descriptions import ACCORD_DESCRIPTIONS
    groups=[(section,sorted(a for a,s in api.ACCORD_TO_SECTION.items() if s==section)) for section in SECTION_ORDER]
    others=sorted(set(ACCORD_DESCRIPTIONS)-set(api.ACCORD_TO_SECTION))
    if others:groups.append(('기타 (지도 미반영)',others))
    all_options={a for _,options in groups for a in options}
    st.session_state.setdefault('integration_active',[])
    active=set(st.session_state.integration_active)&all_options
    for i,(_,options) in enumerate(groups):
        st.session_state.setdefault(f'integration_draft_{i}',sorted(active.intersection(options)))
    filters=() if not active or active==all_options else tuple(sorted(active))
    count=len(visible_rows(settings,api.MAP_LOGIC_VERSION,filters,view))
    opened=st.session_state.get('ui_filter_open',False)
    status='전체 선택' if not filters else f'{len(filters)}개 어코드 선택'
    with st.container(key='ui_filter_shell'):
        title = ('▾' if opened else '▸') + ' 어코드 필터'
        summary = f'현재: {status} · 표시 중 {count:,} / {len(view):,}개'
        st.button(f'{title} `{summary}`', type='tertiary', key='ui_filter_toggle',
                  width='stretch', on_click=toggle_filter)
        if opened:
            with st.container(key='ui_filter_body', gap=None):
                filter_editor(api, groups)
    return filters,count


@st.fragment
def render_integrated(api):
    with st.container(key="prism_unified"):
        scoped_styles()
        _render_integrated(api)


def _render_integrated(api):
    detail=st.session_state.get("integration_detail")
    search_column,selection_column=st.columns([3,2],gap="medium")
    with search_column:
        query = st.text_input('향수 이름 또는 브랜드 검색',key='integration_search',on_change=reset_search)
    try:
        settings = tuple(sorted(api.data_settings().items()))
        with st.spinner('지도를 불러오는 중…'):
            display=api.get_display_cache(settings,api.MAP_LOGIC_VERSION)
            catalog = api.get_recommendation_cache(settings,api.RECOMMENDATION_LOGIC_VERSION)[0] if query.strip() or detail else None
    except api.DataLoadError as exc:
        st.error(str(exc)); return
    identifier = None
    search_ids = ()
    if query.strip():
        choices = find_perfumes(catalog,query)
        index = build_label_index(choices)
        labels = index['labels']
        ordered_ids = sorted_choices(index,choices['_id'])
        if labels:
            with selection_column:
                identifier = st.selectbox('기준 향수 선택',ordered_ids,index=None,format_func=labels.get,
                                          key='integration_base',on_change=clear_details)
            if identifier is None:
                if len(choices) <= SEARCH_MARKER_LIMIT:
                    search_ids = ordered_ids
                else:
                    st.caption(f'{len(choices):,}개 일치 — 목록에서 선택하세요')
        else:
            st.caption('일치하는 향수가 없습니다.')
    filters,visible_count=filters_ui(api,settings,display['view'])
    results = ranked(settings,identifier,api,api.RECOMMENDATION_LOGIC_VERSION) if identifier else []
    detail=st.session_state.get('integration_detail')
    figure_version=STAGE+api.MAP_LOGIC_VERSION+api.RECOMMENDATION_LOGIC_VERSION
    base_figure=figure_for(settings,identifier,filters,figure_version,api)
    if search_ids:
        matches = api.get_coordinates([i for i in search_ids if i != detail], display['view'])
        base_figure = search_matches_figure(base_figure, matches, show_label=len(search_ids) == 1)
    fig = base_figure if identifier else overlay_figure(base_figure, detail, display['view'])
    permitted={identifier,*(r['id'] for r in results)} if identifier else None
    left,right = st.columns([3,2],gap='medium')
    with left:
        reset_hint = '더블클릭·홈: 추천 범위' if identifier else '더블클릭: 전체 보기'
        hint = '마우스 휠: 확대·축소 · 드래그: 영역 확대 · 점 클릭: 상세 정보 · ' + reset_hint
        if visible_count==0:st.caption('조건에 맞는 향수가 없습니다')
        chart_config = dict(scrollZoom=True, displaylogo=False, doubleClick='autosize',
                            modeBarButtonsToRemove=['toImage','select2d','lasso2d','autoScale2d'])
        if identifier:
            # A constant chart spec keeps the browser zoom and pan across detail updates.
            chart_config.update(doubleClick=False, doubleClickDelay=0)
            with st.container(key='ui_recommendation_chart', gap=None):
                st.plotly_chart(fig, key='integration_recommendation_map', width='stretch',
                                theme=None, config=chart_config)
                point_key = 'ui_recommendation_events'
                selected_rank = next((r['rank'] for r in results if r['id'] == detail), None)
                recommendation_clicks(
                    key=point_key, selected=detail, rank=selected_rank,
                    on_point=lambda: capture_map(point_key, permitted, point_trigger=True),
                )
                show_rank_ring(fig, selected_rank)
                st.html(
                    '<span class="ui-map-info" tabindex="0" aria-label="지도 조작 안내" '
                    'aria-describedby="prism-map-help">ⓘ'
                    '<span class="ui-map-tooltip" id="prism-map-help" role="tooltip">'
                    '<b>마우스 휠</b><span>확대·축소</span>'
                    '<b>드래그</b><span>영역 확대</span>'
                    '<b>점 클릭</b><span>상세 정보</span>'
                    '<b>더블클릭·홈</b><span>추천 범위</span>'
                    '</span></span>'
                )
        else:
            map_key = 'integration_map_' + str(st.session_state.get('integration_epoch', 0))
            st.plotly_chart(fig, key=map_key, width='stretch', theme=None,
                            on_select=lambda: capture_map(map_key, permitted),
                            selection_mode='points', config=chart_config)
            st.caption(hint)
        if filters: st.caption('필터는 배경 분포에 적용됩니다. 기준 향수와 추천 Top 10은 비교를 위해 유지합니다.')
    with right:
        if results:
            with st.container(key='ui_recommendation_heading', gap=None):
                name = escape(str(catalog.set_index('_id').loc[identifier, 'Name']))
                st.markdown(f'<div class="ui-rec-title"><h3>추천 Top <span>10</span></h3>'
                            f'<p>기준: {name}</p></div>', unsafe_allow_html=True)
                recommendation_rows(results,catalog,detail,api,select_detail)
        elif not detail:
            st.caption('향수를 검색하고 기준 향수를 선택하면 추천 Top 10이 표시됩니다.')
        if catalog is not None and detail and catalog['_id'].eq(detail).any():
            detail_panel(detail,catalog,display['view'],results,api,clear_details)
