"""Profile-only labels; never alter catalog names, IDs or recommendation search."""
from collections import defaultdict
import re
import unicodedata


def sort_text(value):
    value = value if isinstance(value, str) else ''
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value)
                           if not unicodedata.combining(c)).casefold().split())


def display_name(name, brand):
    """Strip only a matching leading brand, retaining concentration/version words."""
    name = name.strip() if isinstance(name, str) else ''
    brand = brand.strip() if isinstance(brand, str) else ''
    folded, ends = '', []
    for i, char in enumerate(name):
        part = ''.join(c for c in unicodedata.normalize('NFKD', char)
                       if not unicodedata.combining(c)).casefold()
        for character in part:
            if character.isspace():
                if folded.endswith(' '):
                    continue
                character = ' '
            folded += character
            ends.append(i+1)
    prefix = sort_text(brand)
    if prefix and folded.startswith(prefix):
        next_char = folded[len(prefix):len(prefix)+1]
        if not next_char or not (next_char.isalnum() or next_char == '_'):
            stripped = name[ends[len(prefix)-1]:].lstrip(' \t-–—·:|')
            if stripped:
                return stripped
    return name


def build_label_index(catalog):
    rows, groups = [], defaultdict(list)
    for row in catalog[['_id', 'Name', 'Brand']].to_dict('records'):
        brand = row['Brand'].strip() if isinstance(row['Brand'], str) else ''
        name = display_name(row['Name'], brand)
        item = dict(id=row['_id'], name=name, brand=brand,
                    base=f'{brand} · {name}' if brand else name)
        rows.append(item)
        groups[sort_text(item['base'])].append(item)
    rows.sort(key=lambda row: (sort_text(row['brand']), sort_text(row['name']), row['id']))
    duplicates = [sorted(group, key=lambda row: row['id']) for group in groups.values() if len(group) > 1]
    index = dict(rows=rows, base={row['id']: row['base'] for row in rows},
                 duplicates=duplicates, duplicate_ids={row['id'] for group in duplicates for row in group})
    index['labels'] = disambiguate_labels(index, {})
    return index


def _value(value, field):
    value = str(value).strip() if value is not None else ''
    if value.casefold() in ('', 'nan', 'none', 'null', 'n/a', 'na', 'unknown'):
        return ''
    if field == 'Year':
        return value.split('.')[0] if re.fullmatch(r'\d{4}(?:\.0+)?', value) else ''
    return value


def disambiguate_labels(index, metadata):
    labels = dict(index['base'])
    for group in index['duplicates']:
        suffixes = {row['id']: [] for row in group}
        for field in ('Year', 'OilType', 'Gender'):
            values = [_value(metadata.get(row['id'], {}).get(field), field) for row in group]
            if any(values) and (field == 'Year' or len(set(map(sort_text, values))) > 1):
                for row, value in zip(group, values):
                    missing = {'Year': '연도 미상', 'OilType': '농도 정보 없음', 'Gender': '성별 정보 없음'}[field]
                    suffixes[row['id']].append(value or missing)
            for row in group:
                suffix = ' / '.join(suffixes[row['id']])
                labels[row['id']] = row['base'] + (' · ' + suffix if suffix else '')
            if len({sort_text(labels[row['id']]) for row in group}) == len(group):
                break
        remaining = defaultdict(list)
        for row in group:
            remaining[sort_text(labels[row['id']])].append(row['id'])
        for ids in remaining.values():
            if len(ids) > 1:
                for ordinal, identifier in enumerate(sorted(ids), 1):
                    labels[identifier] += f' · 동명 항목 {ordinal}'
    return labels


def sorted_choices(index, ids):
    ids = set(ids)
    return [row['id'] for row in index['rows'] if row['id'] in ids]
