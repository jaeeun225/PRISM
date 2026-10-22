"""Content-based recommendations; matrix rows follow DataFrame positional order."""
from collections import Counter
import re
import unicodedata

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity

from .scent_map import ACCORD_TO_SECTION, SECTION_ORDER, STRENGTH_WEIGHT, safe_eval


def build_accord_matrix(df):
    """Sum original accord strength weights into SECTION_ORDER's 14 columns."""
    matrix = np.zeros((len(df), len(SECTION_ORDER)), dtype=np.float32)
    columns = {section: i for i, section in enumerate(SECTION_ORDER)}
    for row, (accords, strengths) in enumerate(zip(df['Main Accords'], df['Main Accords Percentage'])):
        accords = safe_eval(accords) if isinstance(accords, str) else accords
        strengths = safe_eval(strengths) if isinstance(strengths, str) else strengths
        strengths = strengths if isinstance(strengths, dict) else {}
        for accord in accords if isinstance(accords, list) else []:
            section = ACCORD_TO_SECTION.get(accord)
            if section is not None:
                matrix[row, columns[section]] += STRENGTH_WEIGHT.get(strengths.get(accord), 1)
    return matrix


def build_note_matrix(df):
    """Top 400 notes by perfume document frequency; ties sorted alphabetically.

    A note occurs once per layer (multi-hot), accumulating across layers.
    Unused columns are zero when the vocabulary has fewer than 400 notes.
    """
    documents, frequency = [], Counter()
    for value in df['Notes']:
        notes = safe_eval(value) if isinstance(value, str) else value
        weighted = Counter()
        for layer, weight in [('Top', 1), ('Middle', 2), ('Base', 3)]:
            items = notes.get(layer, []) if isinstance(notes, dict) else []
            names = {str(item.get('name', '')).strip().lower() for item in items
                     if isinstance(item, dict)}
            for name in names - {'', 'n/a', 'na', 'none', 'null'}:
                weighted[name] += weight
        documents.append(weighted)
        frequency.update(weighted.keys())
    vocabulary = {name: i for i, (name, _) in enumerate(
        sorted(frequency.items(), key=lambda item: (-item[1], item[0]))[:400])}
    rows, cols, values = [], [], []
    for row, weighted in enumerate(documents):
        for name, weight in weighted.items():
            if name in vocabulary:
                rows.append(row); cols.append(vocabulary[name]); values.append(weight)
    return csr_matrix((values, (rows, cols)), shape=(len(df), 400), dtype=np.float32)


def normalize_name(name, brand):
    name = name if isinstance(name, str) else ''
    brand = brand if isinstance(brand, str) else ''
    if brand and name.startswith(brand) and (len(name) == len(brand) or not name[len(brand)].isalnum()):
        name = name[len(brand):]
    name = ''.join(' ' if unicodedata.category(c).startswith('P') else c for c in name.lower())
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'\b(?:eau de parfum|eau de toilette|edp|edt|extrait|parfum|cologne|for men|for women|unisex|for her|for him)\b', '', name)
    return re.sub(r'\s+', ' ', name).strip()


def recommend(query_id, df, accord_matrix, note_matrix, top_n=10):
    if accord_matrix.shape != (len(df), 14) or note_matrix.shape != (len(df), 400):
        raise ValueError('Matrices must align with df rows and have 14/400 columns.')
    matches = np.flatnonzero(df['_id'].to_numpy() == query_id)
    if len(matches) != 1:
        raise ValueError('query_id must identify exactly one row.')
    if top_n <= 0:
        return []
    index = int(matches[0])
    accord = cosine_similarity(accord_matrix[index:index+1], accord_matrix).ravel()
    notes = cosine_similarity(note_matrix[index:index+1], note_matrix).ravel()
    scores = .8 * accord + .2 * notes
    seen, results = set(), []
    # Stable order resolves exact score ties by original row order.
    for i in np.argsort(-scores, kind='stable'):
        if i == index:
            continue
        row = df.iloc[int(i)]
        brand = row['Brand'] if isinstance(row['Brand'], str) else ''
        key = (brand.lower(), normalize_name(row['Name'], brand))
        if key in seen:
            continue
        seen.add(key)
        results.append(dict(id=row['_id'], name=row['Name'], brand=brand,
                            final_score=float(scores[i]), accord_similarity=float(accord[i]),
                            note_similarity=float(notes[i]), rank=len(results)+1))
        if len(results) == top_n:
            break
    return results
