"""Lazy profile page with validated bookmark URLs; no account/DB storage."""
from io import BytesIO
import hashlib
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st

from .catalog_search import find_perfumes, perfume_labels
from .scent_profile import summarize_profile
from .storage_data import DataLoadError
from .profile_state import MAX_SIGNATURES, restore_selection, save_selection


@st.cache_resource(max_entries=2, show_spinner=False)
def profile_context(settings_key, map_logic, _artifact_loader, _fallback_loader):
    artifact = _artifact_loader(settings_key, map_logic)
    if artifact is None:
        frame, angles = _fallback_loader(**dict(settings_key), calculation_logic=map_logic)
    else:
        frame, angles = artifact
    # Profiles need notes and wheel centers, never a full Plotly figure.
    return frame.set_index('_id')['Notes'].copy(), angles


@st.cache_data(ttl=86400, max_entries=128, show_spinner=False)
def fetch_bottle(url):
    if not url or not isinstance(url, str):
        return None
    try:
        request = Request(url, headers={'User-Agent': 'PRISM-Profile/1.0'})
        with urlopen(request, timeout=4) as response:
            data = response.read(8_000_001)
        return data if len(data) <= 8_000_000 else None
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, HTTPException):
        # An unavailable CDN image must not block a usable profile/PNG.
        return None


@st.cache_data(ttl=86400, max_entries=32, show_spinner=False)
def profile_png(profile, signatures, version):
    from .profile_card import render_card_png
    return render_card_png(profile, signatures, [fetch_bottle(row['image_url']) for row in signatures])


def add_signature(choice_key, allowed_ids):
    # The search widget is only an add candidate, never the canonical selection.
    selected = st.session_state.get(choice_key)
    values = list(st.session_state.get('profile_signatures', []))
    if selected in allowed_ids and selected not in values and len(values) < MAX_SIGNATURES:
        values.append(selected)
    save_selection(values)
    st.session_state[choice_key] = None


def remove_signature(identifier):
    save_selection([value for value in st.session_state.get('profile_signatures', []) if value != identifier])


def render_profile(*, settings_factory, recommendation_loader, recommendation_logic,
                   map_artifact_loader, map_logic, map_fallback_loader, catalog_loader):
    try:
        settings_key = tuple(sorted(settings_factory().items()))
        with st.spinner('프로필을 준비하는 중...'):
            catalog, accord_matrix, _ = recommendation_loader(settings_key, recommendation_logic)
    except DataLoadError as exc:
        st.error(str(exc))
        return
    st.html("""<style>
    .st-key-profile_layout {max-width:1120px;margin-inline:auto;}
    .st-key-profile_controls button p {white-space:normal;overflow-wrap:anywhere;}
    .st-key-profile_preview {max-width:540px;width:100%;margin-inline:auto;}
    .st-key-profile_preview [data-testid="stImage"] {width:100%!important;}
    .st-key-profile_preview img {display:block;width:auto!important;height:auto!important;
      max-width:100%!important;max-height:max(260px,min(640px,calc(100dvh - 330px)))!important;
      object-fit:contain;margin-inline:auto;}
    @media (max-width:900px) {
      .st-key-profile_layout [data-testid="stHorizontalBlock"]:has(.st-key-profile_controls) {
        flex-direction:column!important;}
      .st-key-profile_layout [data-testid="stHorizontalBlock"]:has(.st-key-profile_controls) > [data-testid="stColumn"] {
        width:100%!important;flex:1 1 100%!important;min-width:0!important;}
      .st-key-profile_preview img {max-height:none!important;}
    }
    </style>""")
    values = restore_selection(set(catalog['_id']))
    with st.container(key='profile_layout'):
        controls, preview = st.columns([1, 1.15], gap='large')
        with controls, st.container(key='profile_controls'):
            st.subheader('My Profile')
            st.caption('향수를 검색해 최대 3개까지 추가하세요.')
            query = st.text_input('향수 이름 또는 브랜드 검색', key='profile_search')
            if query.strip():
                choices = find_perfumes(catalog, query)
                choices = choices.loc[~choices['_id'].isin(values)]
                if choices.empty:
                    st.info('일치하는 추가 향수가 없습니다.')
                else:
                    labels = perfume_labels(choices)
                    suffix = hashlib.sha256(query.strip().casefold().encode()).hexdigest()[:12]
                    choice_key = 'profile_candidate_' + suffix
                    candidate = st.selectbox('추가할 시그니처 향수', list(labels), index=None,
                                             format_func=labels.get, key=choice_key,
                                             disabled=len(values) >= MAX_SIGNATURES)
                    st.button('시그니처에 추가', key='profile_add', type='primary',
                              disabled=candidate is None or len(values) >= MAX_SIGNATURES,
                              on_click=add_signature, args=(choice_key, tuple(labels)))
            if values:
                selected = catalog.set_index('_id').loc[values]
                for identifier, row in selected.iterrows():
                    st.button(f"{row['Name']} · {row['Brand']} ×", key=f'profile_remove_{identifier}',
                              on_click=remove_signature, args=(identifier,))
            download_slot = st.empty()
            if len(values) == MAX_SIGNATURES:
                st.caption('최대 3개입니다. 바꾸려면 선택한 향수를 먼저 삭제하세요.')
            st.caption('주소(URL)를 북마크하면 같은 프로필을 다시 열 수 있습니다.')
            detail_slot = st.empty()
        with preview, st.container(key='profile_preview'):
            if not values:
                st.info('시그니처 향수를 하나 이상 추가하면 프로필 카드가 표시됩니다.')
                return
            try:
                with st.spinner('나만의 향 프로필을 만드는 중...'):
                    notes, angles = profile_context(settings_key, map_logic, map_artifact_loader, map_fallback_loader)
                    missing = [identifier for identifier in values if identifier not in notes.index]
                    missing_notes = {}
                    if missing:
                        raw = catalog_loader(**dict(settings_key))
                        missing_notes = raw.loc[raw['_id'].isin(missing)].set_index('_id')['Notes'].to_dict()
                    positions = {identifier: i for i, identifier in enumerate(catalog['_id'])}
                    profile = summarize_profile(accord_matrix[[positions[value] for value in values]],
                                                [notes.get(value, missing_notes.get(value)) for value in values], angles)
                    signatures = [dict(id=identifier, name=row['Name'] if isinstance(row['Name'], str) else '',
                                       brand=row['Brand'] if isinstance(row['Brand'], str) else '', image_url=row['Image URL'])
                                  for identifier, row in selected.iterrows()]
                    png = profile_png(profile, signatures, (dict(settings_key)['version'], map_logic,
                                                            recommendation_logic, 'pastel-bookmark-v3-compact'))
            except DataLoadError as exc:
                st.error(str(exc))
                return
            st.image(BytesIO(png), use_container_width=True)
        with download_slot.container():
            st.download_button('Download profile PNG', data=png, file_name='prism-scent-profile.png',
                               mime='image/png', type='primary', on_click='ignore')
        with detail_slot.container():
            st.caption('카드 하단의 작은 칩은 Scent Map 색입니다. 배경은 같은 색조의 파스텔 표현입니다.')
            if profile['color_source'] == 'dominant_section':
                st.caption(f"향 계열이 서로 상쇄되는 조합이라 {profile['color_section']} 계열색을 대표색으로 사용했습니다.")
            if profile['unmapped_count']:
                st.caption('일부 향수는 휠에 매핑되는 accord가 없어 어코드 요약에서 제외했습니다. 노트는 포함됩니다.')
            with st.expander('Profile details'):
                st.write('Top accords: ' + ', '.join(f"{item['section']} {item['percent']:.1f}%" for item in profile['sections']))
                st.write('Top notes: ' + ', '.join(item['name'] for item in profile['notes']))
