"""Shared literal name/brand search; keep the recommendation picker semantics."""


def find_perfumes(catalog, query):
    query = query.strip()
    mask = (catalog.Name.fillna('').str.contains(query, case=False, regex=False) |
            catalog.Brand.fillna('').str.contains(query, case=False, regex=False))
    return catalog.loc[mask]


def perfume_labels(choices):
    return {row['_id']: f"{row['Name']} · {row['Brand']} · {row['_id']}"
            for row in choices.to_dict('records')}
