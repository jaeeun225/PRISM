"""Unified UI only. Existing artifact, ranking and highlight functions are reused."""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from html import escape
from .catalog_search import find_perfumes
from .profile_labels import build_label_index, sorted_choices

STAGE = 'tooltip-ui-v1'
NATIVE_POINTS = False  # Measured browser click: 2.172s; use accessible list/search fallback.


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


@st.cache_resource(show_spinner=False, max_entries=4)
def figure_for(settings, identifier, filters, stage, _api, detail=None):
    original = _api.get_display_cache(settings, _api.MAP_LOGIC_VERSION)
    view = original['view']
    if detail:
        base_figure=figure_for(settings,identifier,filters,stage,_api)
        fig=go.Figure(base_figure.to_plotly_json(),_validate=False)
        for trace in reversed(fig.data):
            if trace.customdata is not None and len(trace.customdata)==1 and trace.customdata[0][-1]==detail:
                x,y=trace.x[0],trace.y[0];break
        else:
            row=view.loc[view['_id']==detail]
            x,y=(row.iloc[0].scent_map_x,row.iloc[0].scent_map_y) if not row.empty else (None,None)
        if x is not None:
            fig.add_trace(go.Scattergl(x=[x],y=[y],mode='markers',marker=dict(size=40,symbol='circle-open',color='#6E7BC9',line=dict(width=2)),hoverinfo='skip',showlegend=False,customdata=[[detail]]))
        return fig
    visible = view.loc[view.accord_values.map(lambda values: bool(set(filters).intersection(values)))] if filters else view
    full = _api.fast_figure(visible, original['template'], '') if filters else original['full_figure']
    cached = dict(original, full_figure=full)
    results = ranked(settings, identifier, _api, _api.RECOMMENDATION_LOGIC_VERSION) if identifier else []
    if identifier:
        fig, _ = _api.recommendation_figure(cached, results)
        recommendation_end=len(fig.data)
        base = _api.get_coordinates([identifier], view)
        if not base.empty:
            fig.add_trace(go.Scattergl(x=base.scent_map_x, y=base.scent_map_y, mode='markers',
                                      marker=dict(size=12, color='#2c2c2a'),hoverinfo='skip',showlegend=False))
            fig.add_trace(_api.build_highlight_trace(base,{identifier:1},marker_size=9,
                                                     show_rank=False,white_width=.7))
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
        bg.customdata = [[r['Name'],r['Brand'],r['_id']] for r in visible[['Name','Brand','_id']].to_dict('records')]
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
        fig.update_layout(clickmode='event+select' if NATIVE_POINTS else 'event',selectionrevision=str(identifier))
    # Preserve equal coordinate scale; let ranges expand, never shrink the plot domain.
    fig.update_layout(height=520,autosize=True,margin=dict(l=18,r=18,t=16,b=16),
                      xaxis=dict(domain=[0,1],constrain='range'),
                      yaxis=dict(domain=[0,1],constrain='range',scaleanchor='x',scaleratio=1),
                      uirevision=str(identifier)+str(filters))
    if not identifier:
        fig.update_layout(xaxis_range=[-1.22,1.22],yaxis_range=[-1.22,1.22])
    return fig


def point_identifier(event):
    points = event.get('selection',{}).get('points',[])
    if not points:return None
    data=points[-1].get('customdata')
    return data[-1] if isinstance(data,(list,tuple)) and data else None


def capture_map(key):
    identifier=point_identifier(st.session_state.get(key,{}))
    if identifier:st.session_state.integration_detail=identifier


def capture_row(key,results):
    rows=st.session_state.get(key,{}).get('selection',{}).get('rows',[])
    if rows and 0<=rows[-1]<len(results):
        st.session_state.integration_detail=results[rows[-1]]['id']


def capture_choice(key):
    st.session_state.integration_detail=st.session_state.get(key)


def detail_panel(identifier,catalog,view,results,api):
    if not identifier:return
    rows=catalog.loc[catalog['_id']==identifier]
    if rows.empty:return
    row=rows.iloc[0]
    st.button('× 상세 닫기',on_click=clear_details,key='integration_close',type='tertiary')
    from urllib.parse import quote,urlsplit,urlunsplit
    image=row['Image URL']
    if isinstance(image,str) and image.startswith(('https://','http://')):
        parts=urlsplit(image.replace('#','%23'))
        url=urlunsplit((parts.scheme,parts.netloc,quote(parts.path,safe='/%'),parts.query,''))
    else:url=None
    match=next((r for r in results if r['id']==identifier),None)
    badges=(f"추천 {match['rank']}위 · 유사도 {match['final_score']:.4f}" if match else '선택한 향수')
    picture=f'<img src="{escape(url,quote=True)}" style="width:100px;height:120px;object-fit:contain;background:white;border-radius:8px;flex-shrink:0">' if url else ''
    content=f'<div style="display:flex;gap:12px;align-items:center">{picture}<div style="min-width:0;overflow-wrap:anywhere"><h3 style="font-size:18px;margin:0 0 4px">{escape(str(row["Name"]))}</h3><p style="margin:0 0 6px">{escape(str(row["Brand"]))}</p><span style="background:#eeedf9;color:#5867af;padding:3px 6px;border-radius:12px;font-size:13px">{badges}</span></div></div>'
    coords=view.loc[view['_id']==identifier]
    if not coords.empty:
        record=coords.iloc[0]
        chips=[]
        for accord in record['accord_values']:
            section=api.ACCORD_TO_SECTION.get(accord)
            color=api.marker_rgb(api.hsl_to_css(api.COLOR_HUE_ANCHOR[section],75,40)) if section else '#777777'
            chips.append(f'<span style="display:inline-block;margin:2px;padding:2px 6px;border-radius:12px;background:{color};color:{api.contrast_text_color(color)};font-size:13px">{escape(accord)}</span>')
        content+='<div style="margin:6px 0">'+''.join(chips)+'</div>'
        from .scent_map import safe_eval
        parsed=safe_eval(record['Notes']) if isinstance(record['Notes'],str) else record['Notes']
        for layer in ['Top','Middle','Base']:
            names=[str(item.get('name','')) for item in parsed.get(layer,[]) if isinstance(item,dict) and item.get('name')] if isinstance(parsed,dict) else []
            if names:content+=f'<div style="font-size:14px;line-height:1.45"><b>{layer}:</b> '+escape(', '.join(names))+'</div>'
    else:
        content+='<p>이 향수는 지도 좌표가 없어 지도 상세 노트를 표시할 수 없습니다.</p>'
    st.markdown(content,unsafe_allow_html=True)


def set_all_groups(groups, enabled):
    for i,(_,options) in enumerate(groups):
        st.session_state[f'integration_draft_{i}']=list(options) if enabled else []
    apply_groups(groups)


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


def filters_ui(api):
    from .scent_map import SECTION_ORDER
    from .accord_descriptions import ACCORD_DESCRIPTIONS
    groups=[(section,sorted(a for a,s in api.ACCORD_TO_SECTION.items() if s==section)) for section in SECTION_ORDER]
    others=sorted(set(ACCORD_DESCRIPTIONS)-set(api.ACCORD_TO_SECTION))
    if others:groups.append(('기타 (지도 미반영)',others))
    for i,(_,options) in enumerate(groups):
        st.session_state.setdefault(f'integration_draft_{i}',[a for a in st.session_state.get('selected_accords',[]) if a in options])
    st.session_state.setdefault('integration_active',list(st.session_state.get('selected_accords',[])))
    active=st.session_state.integration_active
    all_options=set(api.ACCORD_TO_SECTION)|set(ACCORD_DESCRIPTIONS)
    status='필터 없음 · 전체 표시' if not active else ('전체 선택' if set(active)==all_options else f'{len(active)}개 accord 적용 중')
    st.html('''<style>
    .st-key-integration_filters [data-testid="stIconMaterial"]{display:none}
    .st-key-integration_filters details>summary::before{content:"▸";margin-right:6px;font-family:Georgia,serif}
    .st-key-integration_filters details[open]>summary::before{content:"▾"}
    </style>''')
    with st.container(key='integration_filters'),st.expander('Accord 필터 · '+status+' · 열기/닫기',expanded=False):
        with st.form('integration_filter_form',border=False):
            controls=st.columns([1,1,1,5])
            with controls[0]:st.form_submit_button('전체 선택',on_click=set_all_groups,args=(groups,True))
            with controls[1]:st.form_submit_button('전체 해제',on_click=set_all_groups,args=(groups,False))
            with controls[2]:st.form_submit_button('적용',type='primary',on_click=apply_groups,args=(groups,))
            with controls[3]:st.caption('OR 필터 · 미선택 시 전체 표시 · 칩 변경 후 적용을 누르세요.')
            for start in range(0,len(groups),4):
                columns=st.columns(4)
                for i in range(start,min(start+4,len(groups))):
                    section,options=groups[i]
                    color=api.marker_rgb(api.hsl_to_css(api.COLOR_HUE_ANCHOR[section],75,40)) if section in api.COLOR_HUE_ANCHOR else 'rgb(119,119,119)'
                    rgb=[int(v.strip()) for v in color[4:-1].split(',')]
                    pale='rgb('+','.join(str(round(v*.15+255*.85)) for v in rgb)+')'
                    scope=f'.st-key-integration_section_{i}'
                    st.html(f'<style>{scope} button[data-variant="pills"]{{border:1px solid #d0d0d0;background:transparent;}}{scope} button[data-testid*="pillsActive"],{scope} button[data-variant="pills"][aria-pressed="true"]{{background:{pale}!important;color:#2c2c2a!important;border-color:{color}!important;}}</style>')
                    with columns[i-start],st.container(border=True,key=f'integration_section_{i}'):
                        st.markdown(f'<div style="border-left:4px solid {color};padding-left:8px;color:{color}"><b>{escape(section)}</b></div>',unsafe_allow_html=True)
                        st.form_submit_button('섹션 전체',key=f'integration_group_all_{i}',on_click=toggle_group,args=(i,options),help='섹션 선택/해제 전환 후 적용')
                        with st.container(horizontal=True):
                            for accord in options:
                                chosen=accord in st.session_state.get(f'integration_draft_{i}',[])
                                st.form_submit_button(accord,key='accord_chip_'+accord,
                                    help=ACCORD_DESCRIPTIONS.get(accord),
                                    type='primary' if chosen else 'secondary',
                                    on_click=toggle_accord,args=(i,accord))
                        st.html(f'<style>{scope} [class*="st-key-accord_chip_"] button{{border-radius:18px;border:1px solid #d0d0d0}}{scope} [class*="st-key-accord_chip_"] button[kind="primaryFormSubmit"]{{background:{pale};color:#2c2c2a;border-color:{color}}}</style>')
            draft_count=sum(len(st.session_state.get(f'integration_draft_{i}',[])) for i in range(len(groups)))
            st.caption(f'적용 {len(st.session_state.integration_active)}개 / {len(all_options)}개 · 선택 개수는 적용 후 갱신됩니다.')
    active=tuple(st.session_state.integration_active)
    return () if not active or set(active)==all_options else tuple(sorted(active))


@st.fragment
def render_integrated(api):
    search_column,selection_column=st.columns(2)
    with search_column:
        query = st.text_input('향수 이름 또는 브랜드 검색',key='integration_search',on_change=reset_search)
    try:
        settings = tuple(sorted(api.data_settings().items()))
        with st.spinner('향수 데이터를 불러오고 지도를 계산하고 있습니다...'):
            api.get_display_cache(settings,api.MAP_LOGIC_VERSION)
            catalog = api.get_recommendation_cache(settings,api.RECOMMENDATION_LOGIC_VERSION)[0] if query.strip() else None
    except api.DataLoadError as exc:
        st.error(str(exc)); return
    identifier = None
    if query.strip():
        choices = find_perfumes(catalog,query)
        index = build_label_index(choices)
        labels = index['labels']
        ordered_ids = sorted_choices(index,choices['_id'])
        if labels:
            with selection_column:
                identifier = st.selectbox('기준 향수 선택',ordered_ids,index=None,format_func=labels.get,
                                          key='integration_base',on_change=clear_details)
        else:
            st.caption('일치하는 향수가 없습니다.')
    filters = filters_ui(api)
    results = ranked(settings,identifier,api,api.RECOMMENDATION_LOGIC_VERSION) if identifier else []
    detail=st.session_state.get('integration_detail')
    figure_version=STAGE+api.MAP_LOGIC_VERSION+api.RECOMMENDATION_LOGIC_VERSION
    fig = figure_for(settings,identifier,filters,figure_version,api,detail=detail)
    if detail and filters:
        # Keep the matching full view warm so clearing filters reuses it too.
        figure_for(settings,identifier,(),figure_version,api,detail=detail)
    left,right = st.columns([3,2],gap='medium')
    with left:
        st.caption('마우스 휠: 확대·축소 · 드래그: 영역 확대 · 목록/검색 선택: 상세 정보 · 더블클릭: 전체 보기')
        map_key='integration_map_'+str(identifier)+'_'+str(st.session_state.get('integration_epoch',0))
        st.plotly_chart(fig,key=map_key,width='stretch',theme=None,
                        on_select=(lambda:capture_map(map_key)) if NATIVE_POINTS else 'ignore',selection_mode='points',
                        config=dict(scrollZoom=True,displaylogo=False))
        if identifier: st.caption('기준 향수는 작은 이중 테두리, 추천 향수는 순위 번호로 표시됩니다.')
        if filters: st.caption('필터는 배경 분포에 적용됩니다. 기준 향수와 추천 Top 10은 비교를 위해 유지합니다.')
    with right:
      with st.container(border=False):
        if not results:
            st.caption('향수를 검색하고 기준 향수를 선택하면 추천 Top 10이 표시됩니다.')
        else:
            st.subheader('추천 Top 10')
            st.caption('기준: '+str(catalog.set_index('_id').loc[identifier,'Name']))
            images = catalog.set_index('_id')['Image URL']
            table = pd.DataFrame([{'순위':r['rank'],'이미지':images.get(r['id']),
                                   '향수명':r['name'],'브랜드':r['brand'],'유사도':r['final_score']} for r in results])
            table_key='integration_rows_'+str(identifier)+'_'+str(st.session_state.get('integration_epoch',0))
            st.dataframe(table,height=205,row_height=34,width='stretch',hide_index=True,
                         key=table_key,on_select=lambda:capture_row(table_key,results),selection_mode='single-row',
                         column_config={'순위':st.column_config.NumberColumn(width=45),
                                        '이미지':st.column_config.ImageColumn(width=45),
                                        '향수명':st.column_config.TextColumn(width=170),
                                        '브랜드':st.column_config.TextColumn(width=100),
                                        '유사도':st.column_config.NumberColumn(format='%.4f',width=75)})
        if catalog is not None:
            detail_ids=list(dict.fromkeys([r['id'] for r in results]+list(choices['_id'])))
            detail_labels=catalog.set_index('_id')
            choice_key='integration_detail_picker_'+str(identifier)+'_'+str(st.session_state.get('integration_epoch',0))
            st.selectbox('추천 목록 / 검색 결과 상세 선택',detail_ids,index=None,
                         format_func=lambda value: str(detail_labels.loc[value,'Name'])+' · '+str(detail_labels.loc[value,'Brand']),
                         key=choice_key,on_change=capture_choice,args=(choice_key,),label_visibility='collapsed',
                         placeholder='추천 목록 / 검색 결과 상세 선택')
        if catalog is not None and detail:
            with st.container(border=True):
                detail_panel(detail,catalog,api.get_display_cache(settings,api.MAP_LOGIC_VERSION)['view'],results,api)
