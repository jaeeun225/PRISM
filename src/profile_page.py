"""Lazy profile page with validated bookmark URLs; no account/DB storage."""
from io import BytesIO
import hashlib
import zlib
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit, urlencode
from urllib.request import Request, urlopen

import streamlit as st
import pandas as pd

from .catalog_search import find_perfumes
from .profile_labels import build_label_index, disambiguate_labels, sorted_choices
from .scent_profile import summarize_profile
from .storage_data import DataLoadError, StorageClient
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
def _fetch_bottle_cached(url):
    """Cache verified successes only; transient failures must remain retryable."""
    from PIL import Image
    for attempt in range(2):
        try:
            request = Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                              '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
                'Accept': 'image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.5',
            })
            with urlopen(request, timeout=5) as response:
                data = response.read(8_000_001)
            if len(data) > 8_000_000:
                raise ValueError('Bottle image exceeds size limit')
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > 16_000_000:
                    raise ValueError('Bottle image exceeds pixel limit')
                image.verify()
            return data
        except HTTPError as exc:
            if exc.code not in (408, 429) and exc.code < 500:
                break
        except (URLError, TimeoutError, OSError, ValueError, HTTPException, Image.DecompressionBombError):
            pass
    # Streamlit does not cache exceptions. The public wrapper renders a fallback.
    raise OSError('Bottle image unavailable')


def fetch_bottle(url):
    if not url or not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url)
        if parts.hostname == 'cdn.fragella.com':
            # Fragella filenames contain literal # and +; neither is URL syntax here.
            parts = urlsplit(url.replace('#', '%23'))
        if parts.scheme not in ('http', 'https'):
            return None
        url = urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe='/%'), parts.query, ''))
        return _fetch_bottle_cached(url)
    except (OSError, ValueError):
        return None


@st.cache_data(ttl=86400, max_entries=32, show_spinner=False)
def _profile_png_cached(profile, signatures, version, bottle_images, orientation):
    from .profile_card import render_card_png
    return render_card_png(profile, signatures, bottle_images, orientation=orientation)


def profile_png(profile, signatures, version, orientation='horizontal'):
    # Include image bytes in the PNG key so an earlier missing image cannot stick.
    return _profile_png_cached(profile, signatures, version,
                               [fetch_bottle(row['image_url']) for row in signatures], orientation)


@st.cache_resource(max_entries=2, show_spinner=False)
def profile_label_index(settings_key, recommendation_logic, _catalog):
    return build_label_index(_catalog)


@st.cache_data(ttl=86400, max_entries=2, show_spinner=False)
def profile_label_metadata(settings_key, duplicate_ids):
    """Only ambiguous labels need raw metadata; never load/parse notes here.

    The artifacts do not store Year/OilType. Read just four CSV columns and
    retain just duplicate rows, rather than caching another full raw catalog.
    """
    settings = dict(settings_key)
    try:
        if settings['source'] == 'local':
            source, compression = settings['csv_path'], 'infer'
        else:
            source = BytesIO(StorageClient(settings['url'], settings['service_key'], settings['bucket'],
                                           settings['object_path']).download())
            compression = 'gzip'
        frame = pd.read_csv(source, compression=compression, dtype=str,
                            usecols=lambda column: column in {'_id', 'Year', 'OilType', 'Gender'})
        if '_id' not in frame:
            return {}
        frame = frame.loc[frame['_id'].isin(duplicate_ids)].set_index('_id')
        return frame.to_dict('index')
    except (DataLoadError, OSError, ValueError, EOFError, zlib.error, pd.errors.ParserError):
        # Numbered same-name entries remain usable if optional metadata fails.
        return {}


def reset_profile_picker(clear_search=False):
    for key in list(st.session_state):
        if key.startswith('profile_candidate_'):
            del st.session_state[key]
    # Discard any delayed client value from the old (possibly disabled) picker.
    st.session_state.profile_picker_generation = st.session_state.get('profile_picker_generation', 0) + 1
    if clear_search:
        st.session_state.profile_search = ''


def add_signature(choice_key, allowed_ids):
    # The search widget is only an add candidate, never the canonical selection.
    selected = st.session_state.get(choice_key)
    values = list(st.session_state.get('profile_signatures', []))
    if selected in allowed_ids and selected not in values and len(values) < MAX_SIGNATURES:
        values.append(selected)
        save_selection(values)
        reset_profile_picker(clear_search=True)


def remove_signature(identifier):
    save_selection([value for value in st.session_state.get('profile_signatures', []) if value != identifier])
    reset_profile_picker()


def reset_profile():
    save_selection([])  # Keeps prism_page=profile and unrelated URL parameters.
    reset_profile_picker(clear_search=True)


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
    .st-key-profile_controls [data-testid="stVerticalBlock"] {gap:0.5rem;}
    .st-key-profile_selected_chips [data-testid="stButton"] {width:max-content;max-width:100%;}
    .st-key-profile_selected_chips button {border-radius:999px;padding:0.25rem 0.65rem;min-height:2rem;}
    .st-key-profile_selected_chips button p {font-size:0.85rem;line-height:1.25;}
    .st-key-profile_preview {max-width:540px;width:100%;margin-inline:auto;}
    .st-key-profile_preview [data-testid="stVerticalBlock"] {gap:0.5rem;}
    .st-key-profile_preview [data-testid="stImage"] {width:100%!important;}
    .st-key-profile_preview img {display:block;width:auto!important;height:auto!important;
      max-width:100%!important;max-height:max(260px,min(640px,calc(100dvh - 450px)))!important;
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
            query = st.text_input('향수 이름 또는 브랜드 검색', key='profile_search',
                                  on_change=reset_profile_picker)
            index = profile_label_index(settings_key, recommendation_logic, catalog)
            matches = find_perfumes(catalog, query) if query.strip() else catalog.iloc[:0]
            relevant = set(matches['_id']) | set(values)
            metadata = (profile_label_metadata(settings_key, tuple(sorted(index['duplicate_ids'])))
                        if relevant & index['duplicate_ids'] else {})
            labels = disambiguate_labels(index, metadata) if metadata else index['labels']
            if query.strip():
                choices = matches
                choices = choices.loc[~choices['_id'].isin(values)]
                if matches.empty:
                    st.caption('일치하는 향수가 없습니다.')
                elif choices.empty:
                    st.caption('검색 결과가 모두 이미 선택된 향수입니다.')
                else:
                    choice_ids = sorted_choices(index, choices['_id'])
                    suffix = hashlib.sha256(query.strip().casefold().encode()).hexdigest()[:12]
                    choice_key = f"profile_candidate_{suffix}_{st.session_state.get('profile_picker_generation', 0)}"
                    candidate = st.selectbox('추가할 시그니처 향수', choice_ids, index=None,
                                             format_func=labels.get, key=choice_key,
                                             disabled=len(values) >= MAX_SIGNATURES)
                    st.button('시그니처에 추가', key='profile_add', type='primary',
                              disabled=candidate is None or len(values) >= MAX_SIGNATURES,
                              on_click=add_signature, args=(choice_key, tuple(choice_ids)))
            if values:
                selected = catalog.set_index('_id').loc[values]
                with st.container(horizontal=True, gap='small', key='profile_selected_chips'):
                    for identifier in values:
                        st.button(labels[identifier] + ' ×', key=f'profile_remove_{identifier}',
                                  use_container_width=False, on_click=remove_signature, args=(identifier,))
                st.button('↻ 처음부터 다시', key='profile_reset', on_click=reset_profile)
            st.caption('최대 3개')
            if values:
                address = urlsplit(st.context.url or '')
                query_string = urlencode([(key, value) for key in st.query_params
                                          for value in st.query_params.get_all(key)])
                st.caption('프로필 저장 URL:')
                st.code(urlunsplit((address.scheme, address.netloc, address.path, query_string, '')),
                        language=None, wrap_lines=False)
        with preview, st.container(key='profile_preview'):
            if not values:
                st.caption('시그니처 향수를 하나 이상 추가하면 프로필 카드가 표시됩니다.')
                return
            layout = st.radio('카드 형태', ['가로형', '세로형'], horizontal=True, key='profile_orientation')
            orientation = 'horizontal' if layout == '가로형' else 'vertical'
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
                                                            recommendation_logic, 'profile-v7-centered-signatures'), orientation)
            except DataLoadError as exc:
                st.error(str(exc))
                return
            st.image(BytesIO(png), use_container_width=True)
            st.download_button('Download profile PNG', data=png, file_name=f'prism_profile_{orientation}.png',
                               mime='image/png', type='primary', on_click='ignore')
            if profile['color_source'] == 'dominant_section':
                st.caption(f"향 계열이 서로 상쇄되는 조합이라 {profile['color_section']} 계열색을 대표색으로 사용했습니다.")
            if profile['unmapped_count']:
                st.caption('일부 향수는 휠에 매핑되는 accord가 없어 어코드 요약에서 제외했습니다. 노트는 포함됩니다.')
