"""UI-only localization. Data, artifact schemas and calculations are unchanged."""
from contextlib import AbstractContextManager
from types import FunctionType
from functools import lru_cache
import re
import json
import streamlit as st

PRETENDARD_CSS = 'https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css'
JOSEFIN_CSS = 'https://fonts.googleapis.com/css2?family=Josefin+Sans:wght@300;400;500;600&display=swap'
# Official Google Fonts faces; optical adjustment is confined to Josefin Sans.
JOSEFIN_FACE_CSS = "@font-face {\n  font-family: 'Josefin Sans';\n  font-style: normal;\n  font-weight: 300;\n  font-display: swap;\n  size-adjust: 108%;\n  src: url(https://fonts.gstatic.com/s/josefinsans/v34/Qw3PZQNVED7rKGKxtqIqX5E-AVSJrOCfjY46_GbQXME.ttf) format('truetype');\n}\n@font-face {\n  font-family: 'Josefin Sans';\n  font-style: normal;\n  font-weight: 400;\n  font-display: swap;\n  size-adjust: 108%;\n  src: url(https://fonts.gstatic.com/s/josefinsans/v34/Qw3PZQNVED7rKGKxtqIqX5E-AVSJrOCfjY46_DjQXME.ttf) format('truetype');\n}\n@font-face {\n  font-family: 'Josefin Sans';\n  font-style: normal;\n  font-weight: 500;\n  font-display: swap;\n  size-adjust: 108%;\n  src: url(https://fonts.gstatic.com/s/josefinsans/v34/Qw3PZQNVED7rKGKxtqIqX5E-AVSJrOCfjY46_ArQXME.ttf) format('truetype');\n}\n@font-face {\n  font-family: 'Josefin Sans';\n  font-style: normal;\n  font-weight: 600;\n  font-display: swap;\n  size-adjust: 108%;\n  src: url(https://fonts.gstatic.com/s/josefinsans/v34/Qw3PZQNVED7rKGKxtqIqX5E-AVSJrOCfjY46_ObXXME.ttf) format('truetype');\n}\n"
UI_FONT_FALLBACK = 'Pretendard Variable, Pretendard, Noto Sans KR, sans-serif'
TEXT = {}
def _entry(key, ko, en):
    TEXT[key] = {'ko': ko, 'en': en}

for key,ko,en in [
('nav_map','향 지도','Scent Map'),('nav_profile','내 프로필','My Profile'),
('search','향수·브랜드 검색','Search perfume or brand'),('placeholder','입력 후 Enter','Type, then press Enter'),
('plotly_zoom','영역 확대','Zoom'),('plotly_pan','이동','Pan'),('plotly_in','확대','Zoom in'),('plotly_out','축소','Zoom out'),('plotly_reset','범위 초기화','Reset axes'),('plotly_fullscreen','전체 화면','Fullscreen'),('choose_option','선택하세요','Select a perfume'),('base','기준 향수','Base perfume'),('filter','어코드 필터','Accord filter'),
('shown','{shown:,} / {total:,}개 표시','{shown:,} of {total:,} shown'),
('selected_count','{count}개 어코드 선택','{count} accords selected'),('select_all','전체 선택','Select all'),('clear_all','전체 해제','Clear all'),('apply','적용','Apply'),
('pending','변경 사항이 있습니다 — 적용을 눌러주세요','You have unapplied changes — select Apply'),('or_hint','OR 조건 · 미선택 시 전체 표시','Match any selected accord · none means all'),('section_all','섹션 전체','Entire section'),
('other_section','기타 (지도 미반영)','Other (not mapped)'),('map_loading','지도를 불러오는 중…','Loading the map…'),
('no_results','일치하는 향수가 없습니다.','No matching perfumes.'),('matches','{count:,}개 일치 — 목록에서 선택하세요','{count:,} matches — choose from the list'),
('filter_empty','조건에 맞는 향수가 없습니다','No perfumes match these filters'),('filter_note','필터는 배경 분포에 적용됩니다. 기준 향수와 추천 Top 10은 비교를 위해 유지합니다.','Filters affect the background. The base perfume and Top 10 remain visible.'),
('atlas_headline','나의 다음 시그니처가 기다리는 곳','Where your next signature awaits'),('details_title','향수 정보','Perfume Details'),
('footer_base','기준 향수','BASE'),('footer_selected','선택한 향수','SELECTED'),('footer_hint','점을 눌러 향수를 확인하세요','Click a dot to see its fragrance'),
('map_title','향 지도','Scent map'),('map_highlights','추천 {count}개 강조','{count} recommendations highlighted'),('map_fragrance_count','{count:,}개 향수','{count:,} fragrances'),
('recommend_title','추천 Top 10','Top 10 Recommendations'),('base_caption','기준 · {name}','Base · {name}'),
('choose_base','기준 향수를 고르면 추천 Top 10이 여기에 나타납니다.','Choose a base perfume to see your Top 10 here.'),
('rank','추천 {rank}위','Rank {rank}'),('similarity','유사도 {score:.4f}','Similarity {score:.4f}'),('selected_perfume','선택한 향수','Selected perfume'),
('top','탑','Top'),('middle','미들','Middle'),('base_note','베이스','Base'),
('heart_add','프로필에 추가','Add to profile'),('heart_added','프로필에 등록됨','In your profile'),('heart_full','시그니처 최대 3개','Maximum 3 signatures'),
('heart_add_help','시그니처 향수로 프로필에 추가','Add as a signature perfume'),('heart_remove_help','시그니처 향수에서 해제','Remove from signature perfumes'),('heart_full_help','프로필이 가득 찼습니다 (최대 3개)','Your profile is full (maximum 3)'),
('rebase','이 향수 기준으로 보기','Use as base perfume'),('rebase_help','이 향수 기준으로 다시 검색','Search again using this perfume'),('clear_search','검색어 지우기','Clear search'),
('range','추천 범위','Recommended range'),('full_map','전체 지도','Full map'),('help_label','지도 조작 안내','Map controls'),
('wheel','마우스 휠','Mouse wheel'),('zoom','확대·축소','Zoom in / out'),('drag','드래그','Drag'),('box_zoom','영역 확대','Zoom to area'),('point_click','점 클릭','Click a point'),('details','상세 정보','Show details'),('reset','더블클릭·홈','Double-click / Home'),('full_view','전체 보기','Full map'),
('load_error','데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.','Could not load the data. Please try again shortly.'),
('profile_loading','프로필을 준비하는 중...','Preparing your profile…'),('profile_title','내 향수 프로필','My scent profile'),
('profile_intro','향수를 최대 3개 골라 나만의 향수 카드를 만들어 보세요.','Choose up to 3 perfumes to create your scent profile.'),
('profile_already','검색 결과가 모두 이미 선택된 향수입니다.','All matching perfumes are already selected.'),('profile_candidate','추가할 시그니처 향수','Signature perfume to add'),('profile_add','시그니처에 추가','Add signature'),
('profile_reset','↻ 처음부터 다시','↻ Start over'),('profile_limit','최대 3개','Up to 3 perfumes'),('profile_orientation','카드 형태','Card format'),('horizontal','가로형','Landscape'),('vertical','세로형','Portrait'),
('profile_empty','시그니처 향수를 하나 이상 추가하면 프로필 카드가 표시됩니다.','Add at least one signature perfume to see your profile card.'),('profile_url','프로필 저장 URL','Profile URL'),('profile_drawing','나만의 향 프로필을 만드는 중...','Creating your scent profile…'),('profile_download','프로필 카드 PNG 다운로드','Download profile card PNG'),
('profile_blend','향 계열이 서로 상쇄되는 조합이라 {section} 계열색을 대표색으로 사용했습니다.','These scent families balance one another, so the {section} color represents this profile.'),('profile_unmapped','일부 향수는 휠에 매핑되는 accord가 없어 어코드 요약에서 제외했습니다. 노트는 포함됩니다.','Some perfumes have no mapped accords and are excluded from the accord summary. Their notes are included.'),
]: _entry(key,ko,en)
# Original page labels are recognized by the read-only profile adapter.
ALIASES = {v['ko']: key for key,v in TEXT.items() if '{' not in v['ko']}
ALIASES.update({'향수 이름 또는 브랜드 검색':'search','향수 이름 또는 브랜드 입력 후 Enter':'placeholder','기준 향수 선택':'base','Interactive Scent Map':'nav_map'})

def language():
    value = st.session_state.setdefault('lang', 'ko')
    return value if value in ('ko', 'en') else 'ko'

def set_language(value):
    if value in ('ko', 'en'):
        st.session_state['lang'] = value

def t(key, **values):
    return TEXT[key][language()].format(**values)

def font_family():
    return 'Josefin Sans, Pretendard, Pretendard Variable, Noto Sans KR, sans-serif'

def literal(value):
    if not isinstance(value, str):
        return value
    key = ALIASES.get(value)
    if key:
        return t(key)
    match = re.fullmatch(r'향 계열이 서로 상쇄되는 조합이라 (.*) 계열색을 대표색으로 사용했습니다\.', value)
    return t('profile_blend', section=match[1]) if match else value

class _LocalizedDelta(AbstractContextManager):
    def __init__(self, target): self.target = target
    def __enter__(self): self.target.__enter__(); return self
    def __exit__(self, *args): return self.target.__exit__(*args)
    def __getattr__(self, name):
        target = getattr(self.target, name)
        if not callable(target): return target
        def call(*args, **kwargs):
            if name in {'caption','subheader','header','title','info','warning','error','spinner','button','text_input','selectbox','radio','download_button','markdown'}:
                if args: args = (literal(args[0]), *args[1:])
                for field in ('placeholder','help'):
                    if field in kwargs:
                        # Keep the profile's existing shared-key copy unchanged.
                        if name == 'text_input' and field == 'placeholder' and kwargs[field] == '향수 이름 또는 브랜드 입력 후 Enter':
                            kwargs[field] = '향수·브랜드 입력 후 Enter' if language() == 'ko' else 'Enter perfume or brand, then press Enter'
                        else: kwargs[field] = literal(kwargs[field])
                if name == 'selectbox': kwargs.setdefault('placeholder', '선택하세요' if language() == 'ko' else 'Choose an option')
                if name == 'error' and args:
                    args = (t('load_error'), *args[1:])
            result = target(*args, **kwargs)
            if name in {'container','empty','spinner'}: return _LocalizedDelta(result)
            if name == 'columns': return [_LocalizedDelta(item) for item in result]
            return result
        return call

def render_localized_profile(function, **kwargs):
    """Clone only the renderer globals; never patch the shared profile module."""
    install_chart_language()
    namespace = dict(function.__globals__, st=_LocalizedDelta(st))
    localized = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    localized.__kwdefaults__ = function.__kwdefaults__
    return localized(**kwargs)

# Descriptions remain full Korean originals; English has UI-only translations.
_ACCORD_EN = '''woody|The full family of woody scents. The impression varies greatly with the material: cedarwood (dry, pencil shavings), sandalwood (creamy, soft), or vetiver (roots, earthy and smoky).
citrus|The fresh, zesty scent of citrus peel, such as lemon, orange and bergamot. Highly volatile, it is mainly used in top notes and brings a refreshing lift to the whole perfume.
powdery|A soft, velvety scent like cosmetic powder. Often found in iris, violet and aldehydic materials, it gives a classic, elegant impression.
sweet|The broad sweetness of sugar, fruit, vanilla and similar materials. It describes the overall sweet impression created by several ingredients rather than a specific material.
aromatic|The fragrant, green impression of herbs such as lavender, rosemary and sage.
floral|A floral scent of ordinary intensity, with a subtle, soft impression.
warm spicy|A warm, piquant spicy scent, like cinnamon. Often used in winter and oriental perfumes.
fresh spicy|A spicy yet refreshing, light scent, like pink pepper or cardamom. In contrast to warm spicy, it does not feel heavy.
amber|A warm, sweet, long-lasting resinous accord blending benzoin, labdanum and vanilla. A key base accord in oriental perfumery.
fruity|A fresh-fruit scent with the sweetness of fresh juice.
musky|A musk-like scent. Most modern musks are synthetic, leaving a soft, warm trail on the skin. Depending on the material, the impression ranges from clean to sensual.
white floral|A rich, languid, sensual floral scent from flowers such as jasmine, orange blossom and tuberose. Heavier and more opulent than a general floral accord.
gourmand|An edible scent that evokes desserts and confectionery, such as caramel and vanilla.
vanilla|The sweet, creamy scent of vanilla beans. One of the most widely used base materials in perfumery.
fresh|A broad description of scents that feel fresh and clean, rather than a specific material.
green|The fresh, slightly bitter scent of newly cut grass and leaves. Galbanum is a characteristic material.
rose|The scent of roses, one of the most classic and widely used notes in perfumery.
earthy|The damp, dark scent of soil or a forest floor after rain. Often paired with mossy: while mossy suggests the distinctive scent of moss, earthy emphasizes the soil itself.
balsamic|The warm, rich, slightly sweet scent of tree resins. Similar to amber, but closer to the raw resin material itself.
patchouli|The deep, earthy scent of patchouli leaves, slightly reminiscent of traditional herbal medicine. It feels sensual and heavy.
animalic|A sensual scent with animal-like nuances: pungent and primal in character.
soft spicy|A subtle, softly spicy scent, less intense than warm spicy.
leather|The smoky, somewhat rugged scent of leather. A characteristic note with a masculine, powerful impression.
oud|A costly woody material obtained from agarwood, with a deep, smoky, animalic character. Central to Middle Eastern perfume culture.
aquatic|A refreshing scent impression evoking water and the sea.
herbal|The fragrant scent of culinary herbs such as rosemary, thyme and basil.
lavender|The scent of lavender, a key material in aromatic and fougère perfumes.
iris|The powdery, calm, refined scent of orris (iris root). Costly to extract, it is often used in expensive perfumes.
violet|The scent of violets: powdery, subtle and slightly sweet.
yellow floral|The warm, radiant floral scent of flowers such as mimosa, narcissus and freesia.
mossy|The scent of oakmoss, suggesting a dark, damp forest floor. A key material in chypre perfumes.
smoky|A scent of smoke or burning. Often blended with leather, tobacco and woody accords.
tropical|The exotic, juicy sweetness of tropical fruits such as pineapple and mango.
ozonic|A scent like the air just after rain or a passing storm, with a distinctly sharp, clean impression.
lactonic|A soft, comforting scent reminiscent of dairy products such as milk and cream.
tuberose|The scent of tuberose: rich, creamy and sensual, among the heaviest of white floral notes.
cinnamon|The scent of cinnamon: warm, sweet and piquantly spicy.
marine|A salty, cool scent evoking the sea.
tobacco|The sweetish, smoky, dry scent of tobacco leaves, like a cigar.
honey|The scent of honey: sticky, warm and sweet.
caramel|The rich, slightly bitter sweetness of caramel made by heating sugar.
almond|An almond scent: a nutty note with slight bitterness and a marzipan-like sweetness.
nutty|The rich, nutty scent of nuts in general, such as hazelnuts and almonds.
coconut|The creamy, sweet scent of coconut, often used in summer and tropical perfumes.
aldehydic|A clean, transparent, coolly sparkling scent created by aldehydes. It evokes soap, detergent, a clean shirt and freshly laundered bedding, and is mainly used in classic perfumes such as Chanel No.5. It can also feel bright and sharp.
salty|A salty scent like sea salt. Often used with marine and aquatic accords.
metallic|A cool, sharp scent like the smell left on the hands after touching metal. Some people perceive it as cold iron or blood.
anis|A scent mainly extracted from star anise, combining licorice-like sweetness with a slightly bitter, aromatic character.
cacao|The scent of cacao beans: closer to the raw material than chocolate, with a hint of bitterness.
coffee|The rich, bitter, roasted scent of coffee beans.
conifer|A fresh, forest-like scent from conifers such as pine. Resinous like pine sap, it evokes pine needles and cones.
cherry|The sweet, tart fruit scent of cherries.
chocolate|The scent of chocolate: more processed and sweeter than cacao.
mineral|A cool, clean, slightly salty impression evoked by natural minerals, such as wet stones and pebbles, rather than the actual odor of minerals.
rum|The distinctive sweet, alcoholic scent of rum.
soapy|A clean, slightly powdery scent, like skin just washed with soap.
sour|A scent that suggests a sour taste.
camphor|The scent of camphor, a natural resinous substance extracted from the camphor tree. Fresh and cooling, similar to menthol or eucalyptus.
bitter|A scent that suggests a bitter taste.
whiskey|The scent of whiskey: smoky and sweet, as though matured in oak casks.
savory|A salty, umami-like scent, evoking savory foods such as canapés.
beeswax|The scent of beeswax: honey-like sweetness, warmth and softness, with a slightly slick nuance.
cannabis|The scent of cannabis: a distinctive, strongly grassy herbal character, sometimes with a spicy facet.
champagne|The bright, effervescent scent of champagne with a hint of grapes.
terpenic|A sharp, fresh scent with a pine character created by terpenes. It evokes freshly applied paint or varnish.
sand|A mineral scent evoking hot sand and the desert.
wine|The scent of wine: grapes and alcohol with a slightly tart, sweet, fermented character.
oily|A scent suggesting a greasy texture rather than a particular scent family.
alcohol|The distinctive cooling, volatile scent of alcohol, close to the residual smell of the perfume's base solvent itself.
vodka|The scent of vodka: a distilled-spirit note with a clean, cold impression.
clay|A scent with mineral nuances that evoke potter's clay.
coca-cola|The scent of the carbonated drink, blending Coca-Cola's distinctive caramel with the spiciness of cinnamon and nutmeg.
vinyl|The distinctive scent released when opening a new vinyl record (LP).
paper|The scent of new paper or a new book.
plastic|The distinctive chemical scent of plastic.
asphault|The tar-like scent of a hot asphalt road.
gasoline|The scent of gasoline.
rubber|The distinctive scent of rubber.
tennis ball|The distinctive rubber and felt scent of a new tennis ball.
pear|The gently sweet, soft, juicy fruit scent of pears.
bacon|The distinctive smoked, salty scent of bacon.
hot iron|The metallic, scorched scent of heated iron.
industrial glue|The chemical scent of industrial adhesive.
sake|The subtle scent of fermented grain found in sake, the Japanese alcoholic drink.
milky|A scent suggesting a soft, creamy texture, like milk.'''
from .accord_descriptions import ACCORD_DESCRIPTIONS
for _line in filter(None, _ACCORD_EN.splitlines()):
    _accord, _english = _line.split('|', 1)
    _entry('accord:' + _accord, ACCORD_DESCRIPTIONS.get(_accord, ''), _english)

def accord_description(accord):
    key = 'accord:' + accord
    return t(key) if key in TEXT else ''

def install_language_styles():
    family = font_family()
    ko = language() == 'ko'
    weight = 300 if ko else 400
    spacing = '.01em' if ko else '.03em'
    label_size = 13 if ko else 12
    label_weight = 500 if ko else 600
    transform = 'none' if ko else 'uppercase'
    label_space = '.02em' if ko else '.14em'
    st.html(f'''<style>
@import url("{PRETENDARD_CSS}");
{JOSEFIN_FACE_CSS}
:root{{--prism-ui-font:{family};--prism-letter-space:{spacing}}}
html,body,[data-testid="stAppViewContainer"]{{font-family:var(--prism-ui-font),system-ui,sans-serif!important;font-weight:{weight};letter-spacing:{spacing};font-variant-numeric:lining-nums}}
[data-testid="stAppViewContainer"] *:not([data-testid="stIconMaterial"]):not(.js-plotly-plot,.js-plotly-plot *),[data-baseweb="popover"],[role="tooltip"]{{font-family:var(--prism-ui-font),system-ui,sans-serif!important;font-variant-numeric:lining-nums}}
.st-key-prism_unified{{font-weight:400}}
[data-testid=stAppViewContainer] .st-key-ui_filter_toggle p{{column-gap:0!important;justify-content:flex-start!important}}
[data-testid=stAppViewContainer] .st-key-ui_filter_toggle p > :is(em,strong){{font:inherit!important}}
[data-testid=stAppViewContainer] .st-key-ui_filter_toggle p > em{{flex:none;margin-right:9.140625px;position:relative;top:{-1.5 if ko else -2.5}px}}
[data-testid=stAppViewContainer] .st-key-ui_filter_shell:has(.st-key-ui_filter_body) .st-key-ui_filter_toggle p > em{{top:{-6 if ko else -7}px}}

[data-testid="stAppViewContainer"] .st-key-prism_unified .ui-atlas-intro{{height:{33 if ko else 38}px;padding-top:{0 if ko else .5}px}}
[data-testid=stAppViewContainer] .st-key-prism_unified .st-key-ui_filter_toggle button{{min-height:{37 if ko else 36}px!important;padding-top:4px!important;padding-bottom:4px!important}}
[data-testid=stAppViewContainer] .st-key-prism_unified .st-key-ui_filter_shell{{margin-top:{-8 if ko else -7}px!important;margin-bottom:0!important}}
[data-testid=stAppViewContainer] .st-key-prism_unified .ui-rec-title{{margin-bottom:{8 if ko else 11}px!important}}
[data-testid=stAppViewContainer] .st-key-prism_unified [data-testid=stColumn] > [data-testid=stVerticalBlock]:has(.st-key-integration_results_slot):not(:has(.prism-detail-card,.st-key-ui_rows)){{padding-top:{36 if ko else 39}px!important}}
[data-testid="stAppViewContainer"] .st-key-prism_unified [data-testid="stWidgetLabel"] p{{font-weight:600!important}}
.st-key-prism_nav_tabs button p{{font-size:19px!important;letter-spacing:.04em;font-weight:600!important;color:#4b4f6b}}
.st-key-prism_nav_tabs button[kind="primary"] p{{color:#25283c}}
.st-key-prism_nav_tabs{{gap:2px 40px!important}}
[data-testid="stAppViewContainer"] .st-key-prism_nav .st-key-nav_home button p{{font-family:'Josefin Sans',sans-serif!important;font-size:32px!important;font-weight:600!important;letter-spacing:.06em!important;position:relative;top:3px}}
.st-key-prism_nav_right{{height:64px;gap:28px!important;width:fit-content!important;align-items:center!important;flex-wrap:nowrap!important}}
.st-key-prism_lang{{height:30px;align-items:center!important;gap:8px!important;width:fit-content!important;border-left:1px solid #d2d2df;padding-left:22px}}
.st-key-prism_lang > div{{width:fit-content!important;flex:none}}
.st-key-prism_lang button{{padding:0!important;min-height:28px!important;color:#8a8ea8!important}}
.st-key-prism_lang button p{{font-size:14px!important;letter-spacing:.03em;font-weight:400!important;color:#8a8ea8!important}}
.st-key-prism_lang button[kind="primary"]{{color:#25283c!important}}
.st-key-prism_lang button[kind="primary"] p{{font-weight:600!important;color:#25283c!important}}
.st-key-prism_lang p{{margin:0;color:#b6b8cb;font-size:14px}}
.st-key-prism_lang > div:has(.prism-lang-divider){{height:28px;display:flex;align-items:center;justify-content:center}}
.prism-lang-divider{{display:block;width:1px;height:14px;background:#b6b8cb;flex:none;transform:translateY(-2.6px)}}
[data-testid="stAppViewContainer"] [data-testid="stWidgetLabel"] p{{font-size:{label_size}px!important;font-weight:{label_weight}!important;line-height:20px!important;letter-spacing:{label_space};text-transform:{transform};color:#6a6f9a!important}}
[data-testid="stAppViewContainer"] .st-key-prism_unified .ui-rec-title h3{{font-size:22px!important;font-weight:500!important;letter-spacing:{'.02em' if ko else '.04em'}}}
.st-key-prism_unified .st-key-ui_rows button{{padding-left:10px}}
.st-key-prism_unified .st-key-ui_rows button p{{padding-left:60px}}
.st-key-prism_unified .st-key-ui_rows button code{{position:absolute;left:0;top:0;width:16px;color:#7d84d2!important;font-weight:600!important}}
.st-key-prism_unified .st-key-ui_rows button img{{left:24px}}
.st-key-prism_unified .st-key-ui_rows button strong:first-of-type{{font-weight:500!important}}
.st-key-prism_unified .st-key-ui_rows button strong:last-of-type{{color:#4a52a8;font-weight:600}}
.st-key-prism_unified .st-key-ui_rows button[kind="primary"]::before{{content:'';position:absolute;left:0;top:6px;bottom:6px;width:3px;border-radius:2px;background:linear-gradient(#6e7bc9,#8f99d8)}}
.st-key-prism_unified .prism-detail-name{{font-size:19px!important;font-weight:500;line-height:25px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;letter-spacing:{spacing}}}
.st-key-prism_unified .prism-detail-accent{{height:1.5px}}
.st-key-prism_unified .prism-detail-notes{{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:8px}}
.st-key-prism_unified .prism-detail-note{{min-width:0}}
.st-key-prism_unified .prism-detail-note b{{display:block;font-size:11px;color:#4a52a8;font-weight:600;text-transform:uppercase;line-height:17px}}
.st-key-prism_unified .prism-detail-note div{{font-size:13px;line-height:18px;overflow-wrap:anywhere}}
.st-key-prism_unified .prism-detail-badges span{{font-weight:500}}
.st-key-prism_unified .st-key-ui_detail_add [data-testid="stIconMaterial"]::after{{background:#c03060!important}}
.st-key-prism_unified .st-key-ui_detail_add [data-testid="stIconMaterial"]::before{{content:'';position:absolute;inset:0;background:#c03060;opacity:calc(1 - var(--detail-heart-filled,0));mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath d='M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z' fill='none' stroke='black' stroke-width='1.6'/%3E%3C/svg%3E") center/contain no-repeat}}
[data-testid="stAppViewContainer"] .st-key-prism_unified .st-key-ui_detail_actions [data-testid="stIconMaterial"]{{color:transparent!important}}
.st-key-ui_detail_reference [data-testid="stIconMaterial"]::after{{content:'';position:absolute;inset:0;background:#6b6f85;mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Ccircle cx='10' cy='10' r='6.5' fill='none' stroke='black' stroke-width='1.6'/%3E%3Cpath d='m15 15 6 6' stroke='black' stroke-width='1.6'/%3E%3C/svg%3E") center/contain no-repeat}}
.st-key-prism_unified .js-plotly-plot text,.st-key-prism_unified .annotation-text tspan{{font-weight:500!important;letter-spacing:.04em}}
[data-testid="stLayoutWrapper"]:has(> .st-key-ui_chart_language),.st-key-ui_chart_language{{display:none}}
.st-key-profile_layout h3{{font-weight:600}}
.st-key-profile_layout [data-testid="InputInstructions"]{{display:none}}

.prism-lang-divider{{transform:translateY(-.6px)}}
[data-testid="stAppViewContainer"] .st-key-prism_lang{{border-left:0;padding-left:0;gap:10px!important;flex-wrap:nowrap!important}}
[data-testid="stAppViewContainer"] .st-key-prism_lang > div:has(.prism-lang-divider){{width:1px!important;min-width:1px!important;max-width:1px!important;flex:0 0 1px!important}}
</style>''')


@lru_cache(maxsize=1)
def _chart_language_component():
    return st.components.v2.component('prism_chart_language', html='<span hidden></span>',
                                      isolate_styles=False, js=r"""
export default function({data}) {
 const slot = Symbol.for('prism.chart.language');
 window[slot]?.();
 const settings = data;
 let busy = false, retired = false;
 function localizeProfile() {
  const labels = document.querySelectorAll('.st-key-profile_orientation [data-testid="stRadioGroup"] > div [data-testid="stMarkdownContainer"] p');
  labels.forEach((label,i) => {
   const translated = data.cardFormats[i];
   if (translated && label.textContent !== translated) label.textContent = translated;
  });
 }
 function localizeModebar(g) {
  for (const button of g?.querySelectorAll('.modebar-btn[data-title]') ?? []) {
   const original = button.dataset.prismOriginalTitle ?? button.dataset.title;
   button.dataset.prismOriginalTitle = original;
   const title = settings.modebar[original];
   if (title && button.dataset.title !== title) {
    button.dataset.title = title;
    button.setAttribute('aria-label', title);
   }
  }
 }

 function placeTools(g) {
  const host = g.closest('.st-key-ui_recommendation_chart,.st-key-ui_empty_chart');
  if (!host) return;
  const bounds = host.getBoundingClientRect();
  let cursor = 12;
  const buttons = [...g.querySelectorAll('.updatemenu-button')];
  for (const button of buttons) {
   const text=button.querySelector('text'), rect=button.querySelector('rect');
   if (!text || !rect) continue;
   text.setAttribute('text-anchor','start');text.setAttribute('x','0');text.setAttribute('y','0');text.setAttribute('dy','0');
   const box=text.getBBox(), width=Math.ceil(box.width+24);
   text.setAttribute('x',String(12-box.x));text.setAttribute('y',String(14-box.y-box.height/2));
   rect.setAttribute('x','0');rect.setAttribute('y','0');rect.setAttribute('width',String(width));rect.setAttribute('height','28');
   const matrix=button.parentNode.getScreenCTM();
   if (matrix) {
    const target=new DOMPoint(bounds.left+cursor,bounds.top+6).matrixTransform(matrix.inverse());
    button.setAttribute('transform',`translate(${target.x},${target.y})`);
   }
   cursor+=width+6;
  }
  const info=host.querySelector('.ui-map-info');
  if (info) info.style.setProperty('left',(buttons.length?cursor-6+8:12)+'px','important');
 }
 async function syncGeometry(g) {
  const host=g.closest('.st-key-prism_unified');
  const height=parseFloat(getComputedStyle(host).getPropertyValue('--prism-panel-height'))||480;
  if (g._fullLayout.height!==height) await window.Plotly.relayout(g,{height});
  placeTools(g);
 }

 async function sync() {
  const g = document.querySelector('.st-key-prism_unified .js-plotly-plot');
  if (retired) return;
  localizeProfile();
  for (const text of g?.querySelectorAll('text') ?? []) {
   if (text.style.fontVariantNumeric !== 'lining-nums') text.style.fontVariantNumeric = 'lining-nums';
  }
  localizeModebar(g);
  if (busy || !g?._fullLayout || !window.Plotly) return;
  busy = true;
  try {
   await syncGeometry(g);
   if (g.dataset.prismLanguage === settings.lang) return;
   const layout = {'font.family':settings.family,'hoverlabel.font.family':settings.family,'xaxis.tickfont.family':settings.family,'xaxis.title.font.family':settings.family,'yaxis.tickfont.family':settings.family,'yaxis.title.font.family':settings.family,'legend.font.family':settings.family,'legend.title.font.family':settings.family};
   (g.layout.annotations ?? []).forEach((a,i) => layout[`annotations[${i}].font.family`] = settings.family);
   (g.layout.updatemenus ?? []).forEach((menu,i) => {
    layout[`updatemenus[${i}].font.family`] = settings.family;
    (menu.buttons ?? []).forEach((button,j) => layout[`updatemenus[${i}].buttons[${j}].label`] = j === 0 ? settings.range : settings.full);
   });
   const source = Symbol.for('prism.chart.originalTooltips');
   g[source] ??= g.data.map(t => t.hovertemplate);
   const templates = g[source].map(text => typeof text !== 'string' ? text : text
      .replace(/<br>Rank: (\d+)/g, (_,n) => '<br>'+settings.rank.replace('{rank}',n))
      .replace(/<br>Similarity: ([\d.]+)/g, (_,n) => '<br>'+settings.similarity.replace('{score:.4f}',n)));
   await window.Plotly.relayout(g, layout);
   await window.Plotly.restyle(g, {'hovertemplate':templates,'textfont.family':settings.family,'hoverlabel.font.family':settings.family});
   localizeModebar(g);
   g.dataset.prismLanguage = settings.lang;
   placeTools(g);
  } finally { busy = false; }
 }
 const observer = new MutationObserver(sync);
 observer.observe(document.body, {childList:true,subtree:true});
 const timer = setInterval(sync, 250);
 window[slot] = () => {retired=true;observer.disconnect();clearInterval(timer)};
 sync(); document.fonts.ready.then(sync);
 return window[slot];
}
""")


def install_chart_language():
    """Localize live chart metadata without changing Streamlit's chart identity."""
    _chart_language_component()(key='ui_chart_language', data=dict(
        lang=language(), family=font_family(), range=t('range'), full=t('full_map'),
        cardFormats=[t('horizontal'),t('vertical')],
        rank=TEXT['rank'][language()], similarity=TEXT['similarity'][language()],
        modebar={title:t(key) for title,key in [('Zoom','plotly_zoom'),('Pan','plotly_pan'),('Zoom in','plotly_in'),('Zoom out','plotly_out'),('Reset axes','plotly_reset'),('Fullscreen','plotly_fullscreen')]},
    ))
