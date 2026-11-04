"""Namespaced, validated bookmark state; independent of search widget values."""
import streamlit as st

PAGE_PARAM = 'prism_page'
IDS_PARAM = 'prism_scent'
MAX_SIGNATURES = 3


def validate_ids(values, valid_ids):
    if not isinstance(values, (list, tuple)):
        return []
    result = []
    for value in values:
        if (not isinstance(value, str) or not 1 <= len(value) <= 512 or
                any(ord(character) < 32 or ord(character) == 127 for character in value)):
            continue
        if value in valid_ids and value not in result:
            result.append(value)
        if len(result) == MAX_SIGNATURES:
            break
    return result


def save_selection(values):
    """Write only our keys; unrelated query parameters are never cleared."""
    st.session_state.profile_signatures = list(values)
    if values and st.query_params.get_all(IDS_PARAM) != list(values):
        st.query_params[IDS_PARAM] = list(values)
    elif not values and IDS_PARAM in st.query_params:
        del st.query_params[IDS_PARAM]
    if st.query_params.get(PAGE_PARAM) != 'profile':
        st.query_params[PAGE_PARAM] = 'profile'
    st.session_state._profile_url_values = tuple(values)
    st.session_state._prism_route_seen = 'profile'


def restore_selection(valid_ids):
    incoming = tuple(st.query_params.get_all(IDS_PARAM))
    previous = st.session_state.get('_profile_url_values')
    if previous is None:
        # Preserve a live session created before URL persistence was introduced.
        source = incoming or st.session_state.get('profile_signatures', [])
    elif incoming != previous:
        source = incoming  # Address-bar changes/back/forward override old state.
    else:
        source = st.session_state.get('profile_signatures', [])
    values = validate_ids(source, valid_ids)
    save_selection(values)
    return values


def set_profile_route(active):
    if active:
        if st.query_params.get(PAGE_PARAM) != 'profile':
            st.query_params[PAGE_PARAM] = 'profile'
    elif st.query_params.get(PAGE_PARAM) == 'profile':
        del st.query_params[PAGE_PARAM]
    st.session_state._prism_route_seen = st.query_params.get(PAGE_PARAM)


def restore_route():
    route = st.query_params.get(PAGE_PARAM)
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 'profile' if route == 'profile' else 'home'
    elif route == 'profile' and st.session_state.get('_prism_route_seen') != route:
        st.session_state.current_page = 'profile'
    st.session_state._prism_route_seen = route
