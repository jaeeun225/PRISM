"""Lazy profile page with validated bookmark URLs; no account/DB storage."""
from io import BytesIO
from html import escape
from base64 import b64encode
from .i18n import t
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
def _profile_png_cached(profile, signatures, version, bottle_images, orientation, created_on):
    from .profile_card import render_card_png
    return render_card_png(profile, signatures, bottle_images, orientation=orientation, created_on=created_on)


def profile_png(profile, signatures, version, orientation='horizontal'):
    from .profile_card import profile_card_date, PROFILE_FONT_VERSION

    # Include image bytes in the PNG key so an earlier missing image cannot stick.
    return _profile_png_cached(profile, signatures, (version, PROFILE_FONT_VERSION),
                               [fetch_bottle(row['image_url']) for row in signatures], orientation, profile_card_date())


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



def signature_row_html(number, row=None):
    """Presentation only; the adjacent original button still performs deletion."""
    if row is None:
        label = t('profile_slot_first' if number == 1 else 'profile_slot_more')
        return f'<div class="profile-signature-row is-empty"><span class="profile-row-number">{number:02d}</span><span>{label}</span></div>'
    image = fetch_bottle(row['Image URL'])
    if image:
        from PIL import Image
        from .profile_card import trim_bottle_image
        with Image.open(BytesIO(image)) as source:
            thumbnail = trim_bottle_image(source)
            stream = BytesIO()
            thumbnail.save(stream, format='PNG')
            image = stream.getvalue()
    picture = ('<img alt="" src="data:image/png;base64,' + b64encode(image).decode() + '">' if image
               else '<span class="profile-bottle-outline" aria-hidden="true"></span>')
    return (f'<div class="profile-signature-row"><span class="profile-row-number">{number:02d}</span>'
            + '<div class="profile-row-image">' + picture + '</div><div class="profile-row-text">'
            + '<span class="profile-row-brand">' + escape(str(row['Brand'])) + '</span>'
            + '<span class="profile-row-name" title="' + escape(str(row['Name']),quote=True) + '">'
            + escape(str(row['Name'])) + '</span></div></div>')


def profile_empty_html():
    return ('<div class="profile-empty-card"><span class="profile-bottle-outline" aria-hidden="true"></span>'
            + '<h4>' + t('profile_empty_heading') + '</h4><p>' + t('profile_empty_hint') + '</p></div>')


def profile_surface_styles():
    st.html("""<style>
    .st-key-profile_layout{--profile-frame-height:430px;gap:18px!important;color:#1A1A1A}
    .profile-intro{height:38px;display:flex;align-items:center}
    [data-testid=stAppViewContainer] .profile-intro h2{margin:0;padding:0;font-size:31px!important;font-weight:400!important;line-height:38px;letter-spacing:.02em;color:#1A1A1A;white-space:nowrap}
    .st-key-profile_layout [data-testid=stHorizontalBlock]:has(> [data-testid=stColumn] .st-key-profile_controls){column-gap:36px!important}
    [data-testid=stAppViewContainer] .st-key-profile_controls{padding-top:0!important;gap:12px!important}
    .profile-section-heading{height:28px;display:flex;align-items:baseline;justify-content:space-between;gap:8px}
    [data-testid=stAppViewContainer] .profile-section-heading h3{margin:0;padding:0;font-size:22px!important;line-height:28px!important;font-weight:500!important;color:#1A1A1A;letter-spacing:.02em;white-space:nowrap}
    .profile-section-heading span{color:#6B6B72;font-size:14px;font-weight:400;white-space:nowrap}
    .st-key-profile_controls [data-testid=stCaptionContainer] p{color:#6B6B72!important}
    [data-testid=stAppViewContainer] .st-key-profile_search input{padding-left:0!important;background:white!important}
    [data-testid=stAppViewContainer] .st-key-profile_search [data-testid=stTextInputRootElement]{padding-left:0!important;border-color:transparent transparent #D6D6DA!important}
    .st-key-profile_search [data-testid=stWidgetLabel]{margin-bottom:-6px}
    [data-testid=stAppViewContainer] .st-key-profile_search input{height:38px!important;min-height:38px!important;line-height:38px!important;padding-top:0!important;padding-bottom:0!important}
    [data-testid=stAppViewContainer] .st-key-profile_controls [data-testid=stWidgetLabel] p{font-size:12px!important;color:#6B6B72!important;line-height:20px!important}
    .st-key-profile_selection_slot,.st-key-profile_selected_chips{gap:0!important;min-width:0}
    [class*=st-key-profile_signature_row_]{position:relative;gap:0!important;height:62px;min-height:62px;border-bottom:1px solid #D6D6DA}
    .profile-signature-row{height:61px;display:flex;align-items:center;gap:12px;padding:4px 32px 4px 8px;box-sizing:border-box;min-width:0}
    .profile-row-number{width:18px;flex:none;font-size:13px;font-weight:500;font-variant-numeric:lining-nums tabular-nums}
    .profile-row-image{width:34px;height:48px;display:flex;align-items:center;justify-content:center;flex:none}
    .profile-row-image img{width:100%;height:100%;object-fit:contain}
    .profile-row-text{display:flex;flex-direction:column;min-width:0;gap:2px}
    .profile-row-brand{font-size:10px;line-height:14px;letter-spacing:.1em;text-transform:uppercase;color:#6B6B72;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .profile-row-name{font-size:15px;line-height:20px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .profile-signature-row.is-empty{color:#6B6B72;font-size:13px;padding-right:8px}
    .profile-signature-row.is-empty .profile-row-number{color:#1A1A1A}
    [class*=st-key-profile_signature_row_] [data-testid=stButton]{position:absolute;right:0;top:14px;width:28px!important;max-width:28px}
    [data-testid=stAppViewContainer] [class*=st-key-profile_signature_row_] button{width:28px!important;min-width:28px!important;height:28px;min-height:28px;padding:0!important;border:0!important;border-radius:0;background:transparent!important;color:#6B6B72}
    [data-testid=stAppViewContainer] .st-key-profile_reset button{background:transparent!important;border:0!important;border-radius:0;padding:0!important;min-height:28px;color:#1A1A1A!important}
    .st-key-profile_reset{margin-top:8px}
    [data-testid=stAppViewContainer] .st-key-profile_url_slot [data-testid=stCaptionContainer] p{font-size:12px!important;line-height:18px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:#6B6B72!important}
    .st-key-profile_url_slot{gap:8px!important}
    .st-key-profile_url_slot [data-testid=stCode]{background:white!important;border:1px solid #D6D6DA;border-radius:0!important}
    .st-key-profile_url_slot pre{background:white!important;padding:9px 38px 9px 10px!important;font-size:12px!important;line-height:18px}
    .st-key-profile_url_slot code{font-size:12px!important;line-height:18px!important}
    .st-key-profile_url_slot button{opacity:1!important}
    .profile-bookmark{font-size:12px;line-height:17px;color:#6B6B72;margin:0}
    .st-key-profile_preview{gap:12px!important;max-width:none!important}
    .st-key-profile_orientation [data-testid=stWidgetLabel]{display:none}
    [data-testid=stAppViewContainer] .st-key-profile_orientation [data-testid=stRadioOption]{border-radius:1px!important;min-height:28px;height:28px;padding:3px 12px;border:1px solid #D6D6DA!important;background:white!important}
    [data-testid=stAppViewContainer] .st-key-profile_orientation [data-testid=stRadioOption][data-selected=true]{background:#F0F0F2!important}
    .st-key-profile_orientation [data-testid=stRadioOption] p{font-size:13px!important}
    .profile-empty-formats{height:28px;display:flex;gap:8px;font-size:13px}
    .profile-empty-formats span{display:flex;align-items:center;padding:3px 12px;border:1px solid #D6D6DA;box-sizing:border-box}
    .profile-empty-formats span:first-child{background:#F0F0F2}
    .st-key-profile_card_slot{height:var(--profile-frame-height);min-height:var(--profile-frame-height);box-sizing:border-box;border:1px solid #D6D6DA;padding:12px;display:flex;align-items:center;justify-content:center;gap:0!important}
    .st-key-profile_card_slot > div{width:100%;min-height:0}
    [data-testid=stAppViewContainer] .st-key-profile_preview .st-key-profile_card_slot img{max-height:calc(var(--profile-frame-height) - 26px)!important;max-width:100%!important;width:auto!important;height:auto!important;margin:auto;box-shadow:none!important;object-fit:contain}
    .profile-empty-card{height:calc(var(--profile-frame-height) - 26px);border:1px solid #D6D6DA;border-radius:10px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;box-sizing:border-box;text-align:center}
    .profile-bottle-outline{display:block;position:relative;width:38px;height:48px;border:1px solid #D6D6DA;border-radius:8px;margin:16px 0 8px}
    .profile-bottle-outline::before{content:'';position:absolute;width:14px;height:20px;border:1px solid #D6D6DA;top:-23px;left:10px}
    .profile-empty-card h4{font-size:21px;line-height:28px;font-weight:600;margin:0;padding:0;color:#1A1A1A}
    .profile-empty-card p{font-size:13px;color:#6B6B72;margin:0;line-height:20px}
    .st-key-profile_download_footer{justify-content:space-between!important;align-items:center!important;gap:12px!important;width:100%}
    .st-key-profile_download_footer > div{width:fit-content!important;flex:none}
    .st-key-profile_download_footer [data-testid=stCaptionContainer] p{font-size:12px;color:#6B6B72!important;white-space:nowrap}
    [data-testid=stAppViewContainer] .st-key-profile_layout [data-testid=stDownloadButton] button{border-radius:1px!important;min-height:32px;padding:4px 14px;border:1px solid #1A1A1A!important;background:#1A1A1A!important;color:white!important}
    [data-testid=stAppViewContainer] .st-key-profile_layout [data-testid=stDownloadButton] button p{color:inherit!important;font-size:13px}
    [data-testid=stAppViewContainer] .st-key-profile_layout [data-testid=stDownloadButton] button:disabled{border-color:#D6D6DA!important;background:#F0F0F2!important;color:#6B6B72!important;opacity:1}

    .st-key-profile_layout{gap:23px!important}
    [data-testid=stMainBlockContainer]:has(.st-key-profile_layout){padding-bottom:16px!important}
    .st-key-profile_card_slot [data-testid=stElementContainer]:has([data-testid=stImage]) > div{display:flex;justify-content:center;align-items:center}

    @media(min-width:901px){
      .st-key-profile_layout [data-testid=stColumn]:has(.st-key-profile_controls){flex:450 1 0%!important;width:0!important}
      .st-key-profile_layout [data-testid=stColumn]:has(.st-key-profile_preview){flex:790 1 0%!important;width:0!important}
    }
    [class*=st-key-profile_signature_row_] > [class*=st-key-profile_remove_]{position:absolute!important;top:17px!important;right:0!important;width:28px!important;height:28px!important}
    [class*=st-key-profile_signature_row_] [data-testid=stButton]{position:static!important;top:auto!important;right:auto!important}
    .st-key-profile_orientation [data-testid=stRadioGroup]{margin:0!important;padding:0!important;height:28px;min-height:28px}
    .st-key-profile_orientation [data-testid=stRadio]{gap:0!important}
    .st-key-profile_card_slot [data-testid=stImage]{display:flex!important;align-items:center!important;justify-content:center!important;width:100%!important}
    .st-key-profile_url_slot [data-testid=stCode] > div{opacity:1!important;visibility:visible!important;top:50%!important;right:6px!important;transform:translateY(-50%)!important}
    .st-key-profile_url_slot [aria-label="Copy to clipboard"]{height:28px!important;min-height:28px!important;width:24px!important;padding:0!important;border:0!important;background:transparent!important;color:#6B6B72!important}
    /* Search-result picker: profile-only presentation; native widget/state unchanged. */
    .st-key-profile_controls:has(.st-key-profile_reset) .st-key-profile_url_slot{margin-top:2px}
    .st-key-profile_search_results{gap:14px!important;margin-bottom:2px}
    .st-key-profile_search_results [data-testid=stSelectbox]{display:flex;flex-direction:column;gap:8px}
    .st-key-profile_search_results [data-testid=stWidgetLabel]{margin:0!important;min-height:20px;padding:0}
    .st-key-profile_search_results .react-aria-ComboBox > [role=group]{background:#FFFFFF!important;border:0!important;border-bottom:1px solid #D6D6DA!important;border-radius:0!important;box-shadow:none!important;padding-left:0!important;min-height:38px}
    .st-key-profile_search_results .react-aria-ComboBox > [role=group]:focus-within{border-bottom-color:#1A1A1A!important}
    .st-key-profile_search_results input[role=combobox]{padding-left:0!important;background:transparent!important;border:0!important;border-radius:0!important;box-shadow:none!important;height:38px;min-height:38px}
    .st-key-profile_search_results input[role=combobox]::placeholder{color:#6B6B72!important;opacity:1}
    .st-key-profile_search_results .react-aria-ComboBox button{background:transparent!important;border:0!important;border-radius:0!important;box-shadow:none!important;color:#6B6B72!important}
    .st-key-profile_search_results .react-aria-ComboBox button svg{width:18px;height:18px}
    body:has(.st-key-profile_layout) [data-testid=stSelectboxVirtualDropdown]{background:#FFFFFF!important;border:1px solid #D6D6DA!important;border-radius:0!important;box-shadow:none!important}
    body:has(.st-key-profile_layout) [data-testid=stSelectboxVirtualDropdown] [role=listbox]{background:#FFFFFF!important;border-radius:0!important}
    body:has(.st-key-profile_layout) [data-testid=stSelectboxVirtualDropdown] [role=option]{background:#FFFFFF!important;color:#1A1A1A!important;font-family:var(--prism-ui-font),system-ui,sans-serif!important;font-weight:400!important;border-radius:0!important}
    body:has(.st-key-profile_layout) [data-testid=stSelectboxVirtualDropdown] [role=option]:is(:hover,[data-hovered],[data-focused],[aria-selected=true]){background:#F0F0F2!important}
    [data-testid=stAppViewContainer] .st-key-profile_layout .st-key-profile_add button{border:1px solid #D6D6DA!important;border-radius:0!important;background:#FFFFFF!important;color:#1A1A1A!important;height:28px!important;min-height:28px!important;padding:0 12px!important;box-shadow:none!important}
    [data-testid=stAppViewContainer] .st-key-profile_layout .st-key-profile_add button p{font-size:13px!important;line-height:20px!important;color:inherit!important}
    [data-testid=stAppViewContainer] .st-key-profile_layout .st-key-profile_add button:hover:not(:disabled){background:#F0F0F2!important}
    [data-testid=stAppViewContainer] .st-key-profile_layout .st-key-profile_add button:disabled{color:#6B6B72!important;border-color:#D6D6DA!important;background:#FFFFFF!important}
    [data-testid=stAppViewContainer] .st-key-profile_layout .st-key-profile_add button:focus:not(:focus-visible){outline:none!important;box-shadow:none!important}
    [data-testid=stAppViewContainer] .st-key-profile_layout .st-key-profile_add button:focus-visible{outline:2px solid #1A1A1A!important;outline-offset:2px}
    @media(max-width:900px){.st-key-profile_layout{--profile-frame-height:380px}}
    </style>""")


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
    .st-key-profile_layout{width:100%;min-width:0;font-variant-numeric:lining-nums tabular-nums}
    .st-key-profile_layout [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-profile_controls){column-gap:56px}
    .st-key-profile_layout [data-testid="stColumn"]:has(.st-key-profile_controls){min-width:0}
    .st-key-profile_controls [data-testid="stVerticalBlock"],
    .st-key-profile_preview [data-testid="stVerticalBlock"]{gap:12px}
    .st-key-profile_layout [data-testid="stLayoutWrapper"]:has(>
        :is(.st-key-profile_search_results,.st-key-profile_selection_slot,.st-key-profile_url_slot,
            .st-key-profile_orientation_slot,.st-key-profile_card_status)):not(:has([data-testid="stElementContainer"]:not(:has([data-testid="stEmpty"])))){
        display:none
    }
    .st-key-profile_controls h3{font-size:20px;font-weight:600;color:#302e38;line-height:1.3;padding:0}
    .st-key-profile_layout [data-testid="stWidgetLabel"] p,
    .st-key-profile_url_slot [data-testid="stCaptionContainer"] p{font-size:16px;font-weight:600;color:#302e38}
    .st-key-profile_url_slot [data-testid="stCaptionContainer"] p{line-height:1.4}
    @media (min-width:901px) {
      .st-key-profile_controls{padding-top:2px}
    }
    .st-key-profile_layout [data-testid="stCaptionContainer"]{font-size:14px;font-weight:400;color:#6c6975}
    .st-key-profile_layout button p{font-size:14px;white-space:normal;overflow-wrap:anywhere}
    .st-key-profile_layout :is([data-testid="stButton"],[data-testid="stDownloadButton"]) button,
    .st-key-profile_orientation [data-testid="stRadioOption"]{
        border-radius:8px;min-height:34px;padding:4px 12px;border-width:1px
    }
    .st-key-profile_orientation [data-testid="stRadioGroup"]{gap:8px}
    .st-key-profile_orientation [data-testid="stRadioOption"]{
        display:flex;align-items:center;border:1px solid rgba(49,51,63,.2);background:white
    }
    .st-key-profile_orientation [data-testid="stRadioOption"] > div > div:first-child{display:none}
    .st-key-profile_orientation [data-testid="stRadioOption"][data-selected="true"]{background:#eeedf9;border-color:#6e7bc9}
    .st-key-profile_orientation [data-testid="stRadioOption"]:hover{border-color:#6e7bc9}
    .st-key-profile_orientation [data-testid="stRadioOption"][data-focus-visible="true"]{outline:2px solid #6e7bc9;outline-offset:2px}
    .st-key-profile_selected_chips [data-testid="stButton"]{width:max-content;max-width:100%}
    .st-key-profile_controls pre{overflow-wrap:anywhere;padding-right:42px}
    .st-key-profile_preview{width:100%;min-width:0;margin-inline:auto}
    .st-key-profile_preview [data-testid="stImage"]{width:100%!important}
    .st-key-profile_preview img{display:block;width:auto!important;height:auto!important;
        max-width:100%!important;max-height:clamp(250px,calc(100dvh - 235px),720px)!important;
        object-fit:contain;margin-inline:auto;box-shadow:0 4px 14px rgba(48,46,56,.09)}
    @media (max-width:900px) {
      .st-key-profile_layout [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-profile_controls) {
        flex-direction:column!important;row-gap:24px}
      .st-key-profile_layout [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .st-key-profile_controls) > [data-testid="stColumn"] {
        width:100%!important;flex:1 1 100%!important;min-width:0!important}
      .st-key-profile_preview img {max-height:none!important}
    }
    </style>""")
    profile_surface_styles()
    values = restore_selection(set(catalog['_id']))
    with st.container(key='profile_layout'):
        st.html('<div class="profile-intro"><h2>'+t('profile_headline')+'</h2></div>')
        controls, preview = st.columns([450, 790], gap='large')
        with controls, st.container(key='profile_controls'):
            st.html('<div class="profile-section-heading"><h3>'+t('profile_signatures_title')+'</h3><span>'+str(len(values))+' / 3</span></div>')
            query = st.text_input('향수 이름 또는 브랜드 검색', key='profile_search',
                                  placeholder='향수 이름 또는 브랜드 입력 후 Enter', on_change=reset_profile_picker)
            index = profile_label_index(settings_key, recommendation_logic, catalog)
            matches = find_perfumes(catalog, query) if query.strip() else catalog.iloc[:0]
            relevant = set(matches['_id']) | set(values)
            metadata = (profile_label_metadata(settings_key, tuple(sorted(index['duplicate_ids'])))
                        if relevant & index['duplicate_ids'] else {})
            labels = disambiguate_labels(index, metadata) if metadata else index['labels']
            # Fixed siblings keep their Streamlit element paths as results and chips change.
            with st.container(key='profile_search_results'):
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
            with st.container(key='profile_selection_slot'):
                if values:
                    selected = catalog.set_index('_id').loc[values]
                with st.container(key='profile_selected_chips', gap=None):
                    for position in range(MAX_SIGNATURES):
                        with st.container(key=f'profile_signature_row_{position}', gap=None):
                            if position < len(values):
                                identifier = values[position]
                                st.html(signature_row_html(position + 1, selected.loc[identifier]))
                                st.button('×', key=f'profile_remove_{identifier}',
                                          use_container_width=False, on_click=remove_signature, args=(identifier,))
                            else:
                                st.html(signature_row_html(position + 1))
                if values:
                    st.button('↻ 처음부터 다시', key='profile_reset', on_click=reset_profile)
            url_slot = st.container(key='profile_url_slot')
        with preview, st.container(key='profile_preview'):
            st.html('<div class="profile-section-heading"><h3>'+t('profile_card_title')+'</h3></div>')
            with st.container(key='profile_orientation_slot'):
                if values:
                    layout = st.radio('카드 형태', ['가로형', '세로형'], horizontal=True, key='profile_orientation', label_visibility='collapsed')
                else:
                    st.html('<div class="profile-empty-formats" aria-disabled="true"><span>'+t('horizontal')+'</span><span>'+t('vertical')+'</span></div>')
            status_slot = st.container(key='profile_card_status', gap=None)
            card_slot = st.container(key='profile_card_slot', gap=None)
            if not values:
                st.session_state.profile_preview_key = None
                card_slot.html(profile_empty_html())
                with st.container(horizontal=True, key='profile_download_footer'):
                    st.caption('PNG · '+t('horizontal'))
                    st.download_button('프로필 카드 PNG 다운로드', data=b'', file_name='prism_profile_horizontal.png', mime='image/png', type='primary', disabled=True, on_click='ignore')
                url_slot.empty()
                return
            orientation = 'horizontal' if layout == '가로형' else 'vertical'
            preview_key = (tuple(values), orientation)
            # Retire the previous portrait while a different one is being prepared.
            # Search-only reruns can keep showing the current portrait.
            image_slot = card_slot
            if st.session_state.get('profile_preview_key') != preview_key:
                image_slot = card_slot.empty()
            with url_slot:
                address = urlsplit(st.context.url or '')
                query_string = urlencode([(key, value) for key in st.query_params if key != 'logo'
                                          for value in st.query_params.get_all(key)])
                st.caption('프로필 저장 URL')
                st.code(urlunsplit((address.scheme, address.netloc, address.path, query_string, '')),
                        language=None, wrap_lines=True)
                st.html('<p class="profile-bookmark">'+t('profile_bookmark')+'</p>')
            try:
                with status_slot, st.spinner('나만의 향 프로필을 만드는 중...'):
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
                                                            recommendation_logic, 'profile-v13-vertical-spacing'), orientation)
            except DataLoadError as exc:
                st.error(str(exc))
                return
            image_slot.image(BytesIO(png), use_container_width=True)
            st.session_state.profile_preview_key = preview_key
            with st.container(horizontal=True, key='profile_download_footer'):
                st.caption('PNG · '+t('horizontal' if orientation == 'horizontal' else 'vertical'))
                st.download_button('프로필 카드 PNG 다운로드', data=png, file_name=f'prism_profile_{orientation}.png',
                                   mime='image/png', type='primary', on_click='ignore')
            if profile['color_source'] == 'dominant_section':
                st.caption(f"향 계열이 서로 상쇄되는 조합이라 {profile['color_section']} 계열색을 대표색으로 사용했습니다.")
            if profile['unmapped_count']:
                st.caption('일부 향수는 휠에 매핑되는 accord가 없어 어코드 요약에서 제외했습니다. 노트는 포함됩니다.')
